"""Phase 2 — heterogeneity mechanics and the claims the spec rests on.

Several of these pin facts that are easy to state in prose and easy to get
silently wrong in code: which classes can reach which tier, that class
assignment is fixed rather than randomized, and that the attribution
diagnostic really differs from the main run in alpha and nothing else.
"""

from __future__ import annotations

import numpy as np
import pytest

from market_sim.acceptance import evaluate_phase2, mean_difference_ci
from market_sim.config import PHASE2_COMMON_ALPHA, PHASE2_MAIN
from market_sim.engine import run_seeds, run_single

SEEDS = [0, 1, 7, 29]


def test_population_matches_spec():
    assert PHASE2_MAIN.n_buyers == 100
    assert PHASE2_MAIN.n_sellers == 5
    assert [(c.name, c.count) for c in PHASE2_MAIN.buyer_classes] == [
        ("Poor", 70),
        ("Middle", 20),
        ("Rich", 10),
    ]
    assert [(c.name, c.count) for c in PHASE2_MAIN.seller_classes] == [
        ("Slow", 3),
        ("Shigh", 2),
    ]
    # 20:1, the RI DEM-informed ratio held from Phase 1 through Phase 15.
    assert PHASE2_MAIN.n_buyers / PHASE2_MAIN.n_sellers == 20


def test_class_assignment_is_fixed_not_randomized():
    """The spec says fixed assignment. Same labels regardless of seed."""
    a = run_single(PHASE2_MAIN, 0).buyer_classes
    b = run_single(PHASE2_MAIN, 17).buyer_classes
    assert a == b
    assert a[:70] == ["Poor"] * 70
    assert a[70:90] == ["Middle"] * 20
    assert a[90:] == ["Rich"] * 10


def test_price_reference_is_max_of_two_seller_classes():
    assert PHASE2_MAIN.price_reference == 6.0  # max(2, 6)
    assert PHASE2_MAIN.price_reference != PHASE2_MAIN.buyer_classes[1].budget_per_visit


@pytest.mark.parametrize("seed", SEEDS)
def test_poor_can_never_buy_from_shigh(seed):
    """Budget 3 against price 6 — an affordability wall, by arithmetic.

    Pinned as a test because the spec's finding depends on this being a hard
    constraint rather than a behavioural tendency: it must stay 0.000 exactly,
    never "small".
    """
    result = run_single(PHASE2_MAIN, seed)
    assert result.tier_share("Poor", "Shigh") == 0.0
    assert not any(
        t.buyer_class == "Poor" and t.seller_class == "Shigh" for t in result.transactions
    )
    # And every one of those evaluations is recorded as affordability-blocked.
    assert result.blocked_by_budget_pairs.get(("Poor", "Shigh"), 0) == 70 * 2


@pytest.mark.parametrize("seed", SEEDS)
def test_middle_can_reach_shigh_after_the_budget_correction(seed):
    """Budget 7 >= price 6. At the original 5 this share was 0.000 by arithmetic."""
    result = run_single(PHASE2_MAIN, seed)
    assert result.tier_share("Middle", "Shigh") > 0.0


@pytest.mark.parametrize("seed", SEEDS)
def test_tier_shares_sum_to_one_per_class(seed):
    result = run_single(PHASE2_MAIN, seed)
    for bc in ("Poor", "Middle", "Rich"):
        total = result.tier_share(bc, "Slow") + result.tier_share(bc, "Shigh")
        assert total == pytest.approx(1.0)


@pytest.mark.parametrize("seed", SEEDS)
def test_no_buyer_exceeds_their_own_class_budget(seed):
    result = run_single(PHASE2_MAIN, seed)
    budgets = np.array(
        [c.budget_per_visit for c in PHASE2_MAIN.buyer_classes for _ in range(c.count)]
    )
    assert (result.buyer_total_spent <= budgets).all()
    assert result.buyer_budget_remaining.min() >= 0


@pytest.mark.parametrize("seed", SEEDS)
def test_inventory_conserved_per_seller(seed):
    result = run_single(PHASE2_MAIN, seed)
    starting = np.array(
        [c.inventory for c in PHASE2_MAIN.seller_classes for _ in range(c.count)]
    )
    assert (result.seller_n_sold + result.seller_inventory_remaining == starting).all()
    assert result.seller_inventory_remaining.min() >= 0


def test_common_alpha_config_differs_only_in_alpha():
    """The attribution diagnostic must be a clean one-variable comparison."""
    main, diag = PHASE2_MAIN, PHASE2_COMMON_ALPHA
    assert diag.seller_classes == main.seller_classes
    assert diag.seeds == main.seeds
    assert diag.price_reference == main.price_reference
    for a, b in zip(main.buyer_classes, diag.buyer_classes):
        assert (a.name, a.count, a.budget_per_visit) == (b.name, b.count, b.budget_per_visit)
    assert {c.price_sensitivity for c in diag.buyer_classes} == {0.5}
    assert len({c.price_sensitivity for c in main.buyer_classes}) == 3


def test_equalizing_alpha_does_not_move_poors_wall():
    """Poor's 0.000 is budget, not price sensitivity — the spec's central caveat."""
    for seed in SEEDS:
        assert run_single(PHASE2_COMMON_ALPHA, seed).tier_share("Poor", "Shigh") == 0.0


def test_stratification_survives_equalizing_alpha_but_shrinks():
    """Documents the attribution the spec requires reporting.

    Budget heterogeneity alone still produces a positive Rich-Middle gap, so
    "heterogeneity produces stratification" holds without price sensitivity;
    the gap is nonetheless larger when alpha varies.
    """
    def gap(cfg):
        results = run_seeds(cfg)
        return mean_difference_ci(
            np.array([r.tier_share("Rich", "Shigh") for r in results]),
            np.array([r.tier_share("Middle", "Shigh") for r in results]),
        )[0]

    heterogeneous, common = gap(PHASE2_MAIN), gap(PHASE2_COMMON_ALPHA)
    assert common > 0
    assert heterogeneous > common


def test_graded_and_observation_criteria_are_separated():
    """Poor's share and Middle's split are reported, never counted as passes."""
    criteria = evaluate_phase2(PHASE2_MAIN, run_seeds(PHASE2_MAIN))
    graded = [c.name for c in criteria if c.graded]
    observed = [c.name for c in criteria if not c.graded]
    assert len(graded) == 3
    assert any("Poor" in n for n in observed)
    assert any("Middle" in n for n in observed)
    assert all(c.passed for c in criteria if c.graded)


def test_mean_difference_ci_drops_undefined_pairs():
    """A class that bought nothing has an undefined share, not a zero one."""
    a = np.array([0.5, 0.6, np.nan, 0.4])
    b = np.array([0.3, 0.3, 0.3, np.nan])
    mean, lo, hi = mean_difference_ci(a, b)
    assert mean == pytest.approx(0.25)  # only the first two pairs survive
    assert lo < mean < hi


def test_middle_and_rich_can_buy_more_than_one_unit():
    """Unlike Phase 1, participation and avg purchases diverge here."""
    result = run_single(PHASE2_MAIN, 0)
    assert result.avg_purchases_per_buyer > result.participation_rate
