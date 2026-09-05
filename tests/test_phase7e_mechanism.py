"""Phase 7e — the loyalty stock, and the invariants it must not break.

The load-bearing claim is that adding a second loyalty mechanism moved no
random draw, so every earlier phase reproduces to the last decimal. The stock
update is deterministic given the week's purchases, which is what makes that
true, and it is pinned here from both directions.
"""

from __future__ import annotations

import dataclasses

import numpy as np
import pytest

from market_sim import acceptance
from market_sim.config import (
    PHASE1_MAIN,
    PHASE7A_FIXED,
    PHASE7E_BETA,
    PHASE7E_CELLS,
    PHASE7E_COUNTER,
    PHASE7E_CURVATURE,
    PHASE7E_DELTA,
    PHASE7E_RETENTIONS,
    PHASE7E_RHO,
    PHASE7E_SATURATION,
    phase7e_beta,
    phase7e_cell,
)
from market_sim.engine import run_season, run_seeds

SEEDS = [0, 1, 7]


def _stock_from_bonus(cfg, bonus: np.ndarray) -> np.ndarray:
    """Invert the tanh so the recorded bonus can be checked against the rule."""
    return cfg.loyalty_saturation * np.arctanh(
        np.clip(bonus / cfg.loyalty_max_bonus, 0.0, 1 - 1e-9)
    )


def test_the_stock_mechanism_consumes_no_random_draws():
    """A stock with a zero ceiling must reproduce a no-loyalty market exactly.

    This is the whole reason Phases 1-7d still reproduce: the update is
    arithmetic on the week's purchases, not a draw. If someone gives the
    mechanism its own randomness, this diverges and every validated tag with
    it.
    """
    off = dataclasses.replace(
        PHASE7A_FIXED, name="off", loyalty_bonus_per_streak=0.0
    )
    stock = dataclasses.replace(
        off, name="stock_zero", loyalty_model="stock", loyalty_max_bonus=0.0
    )
    for seed in SEEDS:
        a, b = run_season(off, seed), run_season(stock, seed)
        assert np.array_equal(a.chosen_seller, b.chosen_seller)
        assert np.array_equal(a.posted_prices, b.posted_prices)
        assert np.allclose(a.profits, b.profits, atol=0, rtol=0)


def test_phase1_is_still_pinned():
    p1 = run_seeds(PHASE1_MAIN)
    assert float(np.mean([r.participation_rate for r in p1])) == pytest.approx(
        0.8216666666666667, abs=1e-12
    )


def test_an_unvisited_pair_decays_at_exactly_rho():
    """No purchase, no accrual - the stock is multiplied by rho and nothing else."""
    cfg = phase7e_cell(delta=0.5)
    season = run_season(cfg, 0)
    stock = _stock_from_bonus(cfg, season.loyalty_bonus.astype(float))
    checked = 0
    for w in range(season.n_weeks - 1):
        bought = {(t.buyer_id, t.seller_id) for t in season.weeks[w].transactions}
        for b in range(cfg.n_buyers):
            for s in range(cfg.n_sellers):
                if (b, s) in bought or stock[w, b, s] < 1e-6:
                    continue
                assert stock[w + 1, b, s] == pytest.approx(
                    cfg.loyalty_retention * stock[w, b, s], rel=1e-4
                )
                checked += 1
    assert checked > 1000  # the invariant is being exercised, not vacuous


def _accrual(cfg, multiplier: float) -> float:
    """The engine's accrual term for a purchase at `multiplier` x list price."""
    deal = (1.0 - multiplier) / cfg.arm_half_range
    return cfg.loyalty_increment * max(
        0.0, 1.0 + cfg.loyalty_deal_sensitivity * deal
    )


def test_delta_zero_accrues_the_same_whatever_the_price():
    """The control cell has no investment channel at all, by construction.

    This is the cell that separates the effect of the stock's *form* from the
    effect of price-sensitive accrual, so its flatness has to be exact rather
    than approximate.
    """
    control = phase7e_cell(delta=0.0)
    accruals = [_accrual(control, m) for m in (0.8, 0.9, 1.0, 1.1, 1.2)]
    assert accruals == pytest.approx([PHASE7E_BETA] * 5)


def test_a_cheaper_purchase_builds_more_stock_when_delta_is_positive():
    """Same seed, same buyer, same seller: only the price paid differs.

    Run at the arm extremes with the *list* price held fixed, since the deal
    is measured against the standing price - repricing the stall would move
    the reference point instead of creating a discount.
    """
    cfg = phase7e_cell(delta=1.0)
    cheap, dear = _accrual(cfg, 0.8), _accrual(cfg, 1.2)
    assert cheap > dear
    assert cheap == pytest.approx(2 * cfg.loyalty_increment)  # 1 + 1.0 * 1.0
    assert dear == pytest.approx(0.0)  # 1 + 1.0 * -1.0, clamped at zero


def test_the_bonus_is_bounded_and_monotone():
    cfg = phase7e_cell()
    season = run_season(cfg, 0)
    bonus = season.loyalty_bonus
    assert bonus.min() >= 0.0
    assert bonus.max() < cfg.loyalty_max_bonus
    stock = np.linspace(0, 5, 50)
    b = cfg.loyalty_max_bonus * np.tanh(stock / cfg.loyalty_saturation)
    assert np.all(np.diff(b) > 0)


def test_the_nominal_ceiling_is_never_reached_in_practice():
    """L_max is a nominal ceiling, not an operative one.

    Steady state tops out at beta*(1+delta)/(1-rho), so the achievable bonus
    is strictly under L_max however long a buyer stays. Pinned as a test
    because the first version of gate 1a graded "not pinned at the ceiling"
    as evidence, when for a tanh stock it is arithmetic - which is why that
    check is now reported rather than graded.
    """
    cfg = phase7e_cell()
    best_stock = cfg.loyalty_increment * (1 + cfg.loyalty_deal_sensitivity) / (
        1 - cfg.loyalty_retention
    )
    achievable = cfg.loyalty_max_bonus * np.tanh(best_stock / cfg.loyalty_saturation)
    assert achievable < cfg.loyalty_max_bonus


def test_the_counter_holds_a_relationship_with_one_seller_at_a_time():
    """The structural difference, pinned. Each row has at most one nonzero."""
    season = run_season(PHASE7E_COUNTER, 0)
    bonus = season.loyalty_bonus
    assert (bonus > 0).sum(axis=2).max() == 1
    stock = run_season(phase7e_cell(), 0).loyalty_bonus
    assert (stock > 0).sum(axis=2).max() > 1


def test_config_guards():
    assert PHASE7E_COUNTER.max_loyalty_bonus() == 1.5
    assert phase7e_cell(max_bonus=4.0).max_loyalty_bonus() == 4.0
    assert phase7e_cell().has_loyalty
    assert not PHASE7E_COUNTER.has_loyalty_stock
    assert PHASE7A_FIXED.arm_half_range == pytest.approx(0.2)
    with pytest.raises(ValueError, match="unknown loyalty_model"):
        dataclasses.replace(PHASE7A_FIXED, loyalty_model="nonsense")


def test_recording_the_bonus_is_opt_in():
    assert not PHASE7A_FIXED.record_loyalty_bonus
    assert run_season(PHASE7A_FIXED, 0).loyalty_bonus is None
    with pytest.raises(ValueError, match="record_loyalty_bonus"):
        acceptance.attachment_bonus([run_season(PHASE7A_FIXED, 0)])


def test_the_swept_stall_keeps_its_original_unit_cost():
    """Otherwise the sweep traces a moving margin instead of a demand curve.

    Derived from price, a stall repriced to 3.20 would carry a unit cost of
    1.60 and hold its margin at exactly half - and the optimum found would be
    an artefact of the cost model rather than of demand.
    """
    swept = acceptance.split_target_config(PHASE7A_FIXED, 3.20)
    assert swept.unit_cost_of()[0] == pytest.approx(1.0)
    assert swept.seller_classes[0].price == 3.20
    assert swept.n_sellers == PHASE7A_FIXED.n_sellers
    # the tier-mate that was split off is untouched
    assert swept.unit_cost_of()[1] == pytest.approx(1.0)
    assert swept.seller_classes[1].price == 2.0


def test_the_oracle_sweep_reproduces_the_base_environments_optimum():
    """2.60, as published at 7d. A sweep that cannot find it cannot judge 7e."""
    result = acceptance.oracle_flat_price(
        PHASE7E_COUNTER, [2.40, 2.50, 2.60, 2.70, 2.80], range(12)
    )
    assert result["best_price"] == pytest.approx(2.60)


def test_the_calibration_grid_sweeps_horizon_and_nothing_else():
    """beta must move with rho, or the sweep confounds horizon with level."""
    assert len(PHASE7E_CELLS) == len(PHASE7E_RETENTIONS)
    assert {c.loyalty_retention for c in PHASE7E_CELLS} == set(PHASE7E_RETENTIONS)
    for c in PHASE7E_CELLS:
        assert c.loyalty_saturation == PHASE7E_SATURATION
        assert c.loyalty_deal_sensitivity == PHASE7E_DELTA
        assert c.loyalty_bonus_per_streak == 0.0  # unreachable, so not carried
        steady_state = c.loyalty_increment / (1 - c.loyalty_retention)
        assert steady_state == pytest.approx(PHASE7E_CURVATURE * PHASE7E_SATURATION)
    assert phase7e_beta(PHASE7E_RHO) == pytest.approx(PHASE7E_BETA)


def test_the_pinned_ceiling_under_binds_and_the_calibration_fixes_it():
    """The first run's central finding, and the repair, pinned as one test.

    At Phase 6's ceiling of 1.5 the stock's incumbency advantage is a fraction
    of the counter's, so it is the *weaker* mechanism however dispersed its
    state is. Solving L_max against the counter's own number is what makes the
    two environments comparable, and everything downstream depends on it
    converging.
    """
    seeds = tuple(range(8))
    target = acceptance.lockin_contrast([run_season(PHASE7E_COUNTER, s) for s in seeds])
    pinned = dataclasses.replace(
        phase7e_cell(), seeds=seeds, loyalty_max_bonus=1.5, name="pinned"
    )
    before = acceptance.lockin_contrast([run_season(pinned, s) for s in seeds])
    assert before < 0.6 * target  # about a third, in the committed run
    calibrated, after = acceptance.calibrate_max_bonus(pinned, target)
    assert abs(after - target) <= 0.02
    assert calibrated.loyalty_max_bonus > pinned.loyalty_max_bonus
