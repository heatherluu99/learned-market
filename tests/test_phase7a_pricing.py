"""Phase 7a — adaptive pricing, and the two ways it can go wrong.

The rejected rule collapsed prices and the ungated hill climber inflated them
on noise. Both failure modes are pinned here, because either one silently
poisons the 7b, 7c and 7d graduation gates that are all measured against 7a.
"""

from __future__ import annotations

import numpy as np
import pytest

from market_sim.acceptance import evaluate_phase7a
from market_sim.config import (
    PHASE6_MAIN,
    PHASE7A_FIXED,
    PHASE7A_HILL,
    PHASE7_WEEKS,
)
from market_sim.engine import run_season, run_season_seeds

SEEDS = [0, 1, 7, 29]


def test_phases_before_7_have_no_cost_model():
    """"profit" was undefined before this phase, and is now defined once."""
    assert not PHASE6_MAIN.has_costs
    assert PHASE6_MAIN.unit_cost_of() == [0.0] * PHASE6_MAIN.n_sellers
    assert PHASE7A_HILL.has_costs
    assert PHASE7A_HILL.unit_cost_of() == [1.0, 1.0, 1.0, 3.0, 3.0]


def test_unit_cost_is_derived_from_price_not_set_separately():
    """One margin parameter, so cost cannot drift away from the price."""
    for cfg in (PHASE7A_HILL, PHASE7A_FIXED):
        costs = cfg.unit_cost_of()
        prices = [c.price for c in cfg.seller_classes for _ in range(c.count)]
        for cost, price in zip(costs, prices):
            assert cost == pytest.approx(price * cfg.unit_cost_fraction)


def test_fixed_arm_holds_its_prices_for_the_whole_run():
    assert not PHASE7A_FIXED.has_adaptive_pricing
    season = run_season(PHASE7A_FIXED, 0)
    assert (season.posted_prices == season.posted_prices[0]).all()


def test_adding_pricing_did_not_move_phase6():
    """The hill climber consumes no random draws, so Phase 6 is untouched."""
    seasons = run_season_seeds(PHASE6_MAIN)
    assert float(np.mean([s.purchase_rate().mean() for s in seasons])) == pytest.approx(
        0.6934, abs=5e-4
    )
    assert run_season(PHASE6_MAIN, 0).profits is None


@pytest.mark.parametrize("seed", SEEDS)
def test_price_persists_across_weeks_while_stock_and_budget_reset(seed):
    """Persistence of price is the phase's changed dimension; the rest resets."""
    season = run_season(PHASE7A_HILL, seed)
    assert season.posted_prices.shape == (PHASE7_WEEKS, PHASE7A_HILL.n_sellers)
    assert not np.array_equal(season.posted_prices[0], season.posted_prices[-1])
    starting = np.array(
        [c.inventory for c in PHASE7A_HILL.seller_classes for _ in range(c.count)]
    )
    for week in season.weeks:
        assert (week.seller_n_sold + week.seller_inventory_remaining == starting).all()


@pytest.mark.parametrize("seed", SEEDS)
def test_price_never_falls_below_unit_cost(seed):
    """Below cost a further cut is irrational, not merely bad."""
    season = run_season(PHASE7A_HILL, seed)
    cost = np.array(PHASE7A_HILL.unit_cost_of())
    assert (season.posted_prices >= cost).all()


@pytest.mark.parametrize("seed", SEEDS)
def test_profit_matches_its_definition(seed):
    season = run_season(PHASE7A_HILL, seed)
    cost = np.array(PHASE7A_HILL.unit_cost_of())
    for w, week in enumerate(season.weeks):
        expected = (
            week.seller_revenue
            - cost * week.seller_n_sold
            - PHASE7A_HILL.fixed_weekly_cost
        )
        assert week.seller_profit == pytest.approx(expected)
        assert season.profits[w] == pytest.approx(expected)


def test_prices_stay_bounded_where_the_rejected_rule_collapsed():
    """The rejected rule reached 0.036x initial; this must not go near that."""
    seasons = run_season_seeds(PHASE7A_HILL)
    initial = np.array(
        [c.price for c in PHASE7A_HILL.seller_classes for _ in range(c.count)]
    )
    ratio = np.array([s.posted_prices[-1] for s in seasons]) / initial
    assert ratio.min() >= 0.5
    assert ratio.max() <= 3.0


def test_the_noise_gate_stops_thin_stalls_random_walking():
    """Without it the quietest stall drifted to 3.5x its price on noise.

    Volume, not price, is what separates the stalls that can learn from the
    ones that cannot: the busiest sells about 27 units a week, the quietest 3.
    """
    seasons = run_season_seeds(PHASE7A_HILL)
    sold = np.array([[w.seller_n_sold for w in s.weeks] for s in seasons]).mean(axis=(0, 1))
    initial = np.array(
        [c.price for c in PHASE7A_HILL.seller_classes for _ in range(c.count)]
    )
    ratio = np.array([s.posted_prices[-1] for s in seasons]) / initial
    thinnest = int(np.argmin(sold))
    assert sold[thinnest] < 5              # genuinely thin signal
    assert ratio[:, thinnest].max() < 2.0  # and it does not run away on it


def test_the_affordability_wall_is_not_breached_by_deflation():
    """The rejected rule crossed this at week 14 and fabricated a finding."""
    seasons = run_season_seeds(PHASE7A_HILL)
    poor_budget = min(c.budget_per_visit for c in PHASE7A_HILL.buyer_classes)
    shigh = [i for i, n in enumerate(PHASE7A_HILL.seller_class_of()) if n == "Shigh"]
    assert min(float(s.posted_prices[:, shigh].min()) for s in seasons) > poor_budget
    assert all(s.tier_share("Poor", "Shigh") == 0.0 for s in seasons)


def test_all_graded_criteria_pass():
    hill = run_season_seeds(PHASE7A_HILL)
    fixed = run_season_seeds(PHASE7A_FIXED)
    criteria = evaluate_phase7a(PHASE7A_HILL, hill, fixed)
    assert len(criteria) == 4
    assert all(c.passed for c in criteria), [
        (c.name, c.measured) for c in criteria if not c.passed
    ]


def test_heuristic_leaves_headroom_for_the_later_sub_stages():
    """7a must not reach the optimum, or 7b-7d have nothing to win.

    The profit-maximising Slow price is 3.00 - which is also Poor's budget,
    the cliff the later sub-stages are supposed to be able to exploit.
    """
    seasons = run_season_seeds(PHASE7A_HILL)
    slow = [i for i, n in enumerate(PHASE7A_HILL.seller_class_of()) if n == "Slow"]
    final_slow = np.array([s.posted_prices[-1, slow] for s in seasons]).mean()
    assert 2.0 < final_slow < 3.0
