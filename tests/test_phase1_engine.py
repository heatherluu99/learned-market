"""Phase 1 engine invariants.

The budget test here is the same hard invariant listed in the spec's
acceptance criteria. It is a test as well as a criterion on purpose: a
criterion checked only at report time tells you a run was wrong after you
already ran it.
"""

from __future__ import annotations

import numpy as np
import pytest

from market_sim.config import (
    PHASE1_INVENTORY_PRESSURE,
    PHASE1_MAIN,
    BuyerParams,
    Phase1Config,
    SellerParams,
)
from market_sim.engine import purchase_probability, run_seeds, run_single

SEEDS = [0, 1, 7, 29]


@pytest.mark.parametrize("seed", SEEDS)
def test_no_buyer_exceeds_budget(seed):
    result = run_single(PHASE1_MAIN, seed)
    assert result.buyer_total_spent.max() <= PHASE1_MAIN.buyer.budget_per_visit
    assert result.buyer_budget_remaining.min() >= 0


@pytest.mark.parametrize("seed", SEEDS)
def test_inventory_never_negative(seed):
    result = run_single(PHASE1_MAIN, seed)
    assert result.seller_inventory_remaining.min() >= 0
    sold = result.seller_n_sold + result.seller_inventory_remaining
    assert (sold == PHASE1_MAIN.seller.inventory).all()


@pytest.mark.parametrize("seed", SEEDS)
def test_transactions_reconcile_with_summaries(seed):
    """The transaction log and the aggregate tables must tell the same story."""
    result = run_single(PHASE1_MAIN, seed)
    assert len(result.transactions) == int(result.buyer_n_purchases.sum())
    assert len(result.transactions) == int(result.seller_n_sold.sum())
    assert result.total_revenue == pytest.approx(result.buyer_total_spent.sum())


@pytest.mark.parametrize("seed", SEEDS)
def test_budget_bookkeeping_matches_each_transaction(seed):
    result = run_single(PHASE1_MAIN, seed)
    for t in result.transactions:
        assert t.budget_after == pytest.approx(t.budget_before - t.price)
        assert t.budget_after >= 0


def test_run_is_deterministic_for_a_seed():
    first = run_single(PHASE1_MAIN, 3)
    second = run_single(PHASE1_MAIN, 3)
    assert first.total_revenue == second.total_revenue
    assert np.array_equal(first.buyer_n_purchases, second.buyer_n_purchases)
    assert np.array_equal(first.seller_n_sold, second.seller_n_sold)


def test_different_seeds_give_different_runs():
    assert not np.array_equal(
        run_single(PHASE1_MAIN, 0).buyer_n_purchases,
        run_single(PHASE1_MAIN, 1).buyer_n_purchases,
    )


@pytest.mark.parametrize("seed", SEEDS)
def test_each_buyer_can_afford_at_most_one_unit(seed):
    """Budget 5 and price 3 cap every buyer at one purchase.

    This is what makes participation_rate and avg_purchases_per_buyer
    identical in Phase 1, and what makes market-wide demand cap out at
    n_buyers - the reason the main run's inventory can never bind.
    """
    result = run_single(PHASE1_MAIN, seed)
    assert result.buyer_n_purchases.max() <= 1
    assert result.participation_rate == pytest.approx(result.avg_purchases_per_buyer)


def test_main_run_inventory_cannot_bind():
    """Guards the stated reason the side experiment exists."""
    max_possible_demand = PHASE1_MAIN.n_buyers  # one unit per buyer, see above
    total_stock = PHASE1_MAIN.n_sellers * PHASE1_MAIN.seller.inventory
    assert max_possible_demand < total_stock


@pytest.mark.parametrize("seed", SEEDS)
def test_inventory_pressure_actually_binds(seed):
    """The side experiment is only informative if stock genuinely runs out."""
    result = run_single(PHASE1_INVENTORY_PRESSURE, seed)
    assert result.blocked_counts["inventory_empty"] > 0
    assert result.seller_inventory_remaining.min() == 0


@pytest.mark.parametrize("seed", SEEDS)
def test_pressure_run_is_paired_with_main_run(seed):
    """Same seed must mean same random inputs, so the two runs are comparable.

    Only the inventory differs between the configs, and all random draws are
    made before any decision, so the pressure run can never sell more than the
    main run on the same seed.
    """
    main = run_single(PHASE1_MAIN, seed)
    pressure = run_single(PHASE1_INVENTORY_PRESSURE, seed)
    assert pressure.seller_n_sold.sum() <= main.seller_n_sold.sum()


def test_purchase_probability_falls_as_price_rises():
    cfg = PHASE1_MAIN
    ref = cfg.price_reference
    cheap = purchase_probability(cfg, 5.0, 1.0, 0.5, ref)
    dear = purchase_probability(cfg, 5.0, 4.0, 0.5, ref)
    assert cheap > dear


def test_purchase_probability_rises_with_preference():
    cfg = PHASE1_MAIN
    ref = cfg.price_reference
    low = purchase_probability(cfg, 5.0, 3.0, 0.1, ref)
    high = purchase_probability(cfg, 5.0, 3.0, 0.9, ref)
    assert high > low


def test_purchase_probability_matches_spec_formula():
    """Recompute the spec's formula by hand and compare."""
    cfg = PHASE1_MAIN
    budget, price, pref = 5.0, 3.0, 0.4
    utility = 1.0 + 0.05 * (budget - price) - 0.5 * (price / 3.0) + 1.5 * pref
    expected = 1.0 / (1.0 + np.exp(-(utility - 2.0)))
    assert purchase_probability(cfg, budget, price, pref, 3.0) == pytest.approx(expected)


def test_price_reference_is_highest_posted_price_not_budget():
    """The rule from "Price Normalization Convention".

    Guarded because the two candidate values are both plausible small numbers
    sitting next to each other in the same config (price 3, budget 5), and
    picking the wrong one changes every result quietly rather than raising.
    """
    for cfg in (PHASE1_MAIN, PHASE1_INVENTORY_PRESSURE):
        assert cfg.price_reference == cfg.seller.price
        assert cfg.price_reference != cfg.buyer.budget_per_visit


def test_price_reference_follows_posted_price_not_budget():
    """Changing posted price moves the reference; changing budget does not."""
    dearer = Phase1Config(
        name="dearer",
        n_buyers=10,
        n_sellers=2,
        buyer=BuyerParams(budget_per_visit=99.0, price_sensitivity=0.5),
        seller=SellerParams(price=7.0, inventory=10),
        seeds=(0,),
    )
    assert dearer.price_reference == 7.0


def test_seller_params_does_not_know_the_price_reference():
    """A seller must not carry the market-wide normalizer.

    Holding it on the seller is what makes "divide by this seller's own price"
    easy to write; the convention puts it on the market config instead.
    """
    assert not hasattr(PHASE1_MAIN.seller, "price_reference")
    assert "price_reference" in vars(PHASE1_MAIN)


def test_price_reference_is_stored_not_recomputed_from_live_sellers():
    """Locked at configuration time, per the Phase 7 / Phase 8 requirement.

    Phase 8 can admit an entrant priced above every incumbent. This asserts the
    value is a plain stored field, so nothing recomputed from a live seller set
    can move it: run-state prices have no path back into the frozen config.
    """
    cfg = PHASE1_MAIN
    before = cfg.price_reference
    assert isinstance(vars(cfg)["price_reference"], float)
    with pytest.raises(Exception):  # frozen dataclass rejects assignment
        cfg.price_reference = 999.0
    assert cfg.price_reference == before


def test_using_each_sellers_own_price_would_delete_the_price_term():
    """Documents the failure mode the convention exists to prevent.

    With price_reference = the seller's own price, price/price_reference is 1.0
    at every stall, so the price term becomes the same constant everywhere.
    Isolated by zeroing the budget coefficient — the only other route by which
    price reaches utility — the two stalls then score *identically* despite one
    charging three times the other. Under the convention they separate.

    Prices 2 and 6 are Phase 2's Slow and Shigh, the configuration where this
    mistake would actually bite.
    """
    no_budget_term = Phase1Config(
        name="price_term_isolated",
        n_buyers=1,
        n_sellers=2,
        buyer=BuyerParams(budget_per_visit=10.0, price_sensitivity=0.5),
        seller=SellerParams(price=6.0, inventory=1),
        seeds=(0,),
        budget_coef=0.0,
    )
    slow, shigh = 2.0, 6.0

    # Broken: each seller normalized by its own price.
    assert purchase_probability(no_budget_term, 10.0, slow, 0.5, slow) == pytest.approx(
        purchase_probability(no_budget_term, 10.0, shigh, 0.5, shigh)
    )

    # Correct: one market-wide reference, max(2, 6) = 6.
    reference = no_budget_term.price_reference
    assert reference == 6.0
    assert purchase_probability(
        no_budget_term, 10.0, slow, 0.5, reference
    ) > purchase_probability(no_budget_term, 10.0, shigh, 0.5, reference)


def test_zero_inventory_market_sells_nothing():
    cfg = Phase1Config(
        name="sold_out",
        n_buyers=10,
        n_sellers=2,
        buyer=BuyerParams(budget_per_visit=5.0, price_sensitivity=0.5),
        seller=SellerParams(price=3.0, inventory=0),
        seeds=(0,),
    )
    result = run_single(cfg, 0)
    assert result.transactions == []
    assert result.participation_rate == 0.0
    assert result.blocked_counts["inventory_empty"] == 10 * 2


def test_run_seeds_covers_every_configured_seed():
    results = run_seeds(PHASE1_MAIN)
    assert [r.seed for r in results] == list(PHASE1_MAIN.seeds)
