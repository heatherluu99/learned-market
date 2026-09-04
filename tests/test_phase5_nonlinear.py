"""Phase 5 — the budget cliff, and the materiality test it establishes.

The equivalence test written here is reused verbatim at Phases 7b-7d, so its
three-way verdict logic is pinned directly rather than only through Phase 5's
own numbers.
"""

from __future__ import annotations

import numpy as np
import pytest

from market_sim.acceptance import (
    MATERIALITY_PP,
    equivalence_verdict,
    evaluate_phase5,
    share_shift_table,
)
from market_sim.config import (
    PHASE4_MAIN,
    PHASE5_ADDITIVE,
    PHASE5_CLIFF_ONLY,
    PHASE5_LINEAR,
)
from market_sim.engine import purchase_probability, run_seeds, run_single

SEEDS = [0, 1, 7, 29]


def test_linear_arm_reproduces_phase4_exactly():
    """The baseline arm is Phase 4 renamed; the cliff must consume no draws."""
    for seed in SEEDS:
        a = run_single(PHASE4_MAIN, seed)
        b = run_single(PHASE5_LINEAR, seed)
        assert np.array_equal(a.seller_n_sold, b.seller_n_sold)
        assert a.participation_rate == b.participation_rate


def test_cliff_is_off_before_phase5():
    for cfg in (PHASE4_MAIN, PHASE5_LINEAR):
        assert not cfg.has_budget_cliff
    assert PHASE5_ADDITIVE.has_budget_cliff
    assert PHASE5_CLIFF_ONLY.has_budget_cliff


def test_cliff_penalty_applies_exactly_at_the_threshold():
    cfg = PHASE5_ADDITIVE
    ref = cfg.price_reference
    # gap 0.6 -> no penalty; gap 0.4 -> penalty. Same price, so only the cliff
    # and the linear budget term differ between them.
    above = purchase_probability(cfg, 2.6, 2.0, 0.5, 0.5, ref)
    below = purchase_probability(cfg, 2.4, 2.0, 0.5, 0.5, ref)
    assert above > below
    linear = PHASE5_LINEAR
    # Without the cliff the same two gaps differ only by the small linear term.
    assert purchase_probability(linear, 2.6, 2.0, 0.5, 0.5, ref) - purchase_probability(
        linear, 2.4, 2.0, 0.5, 0.5, ref
    ) < (above - below)


def test_cliff_only_arm_drops_the_linear_budget_term():
    cfg = PHASE5_CLIFF_ONLY
    ref = cfg.price_reference
    # Well clear of the cliff, remaining budget must not affect utility at all.
    assert purchase_probability(cfg, 9.0, 2.0, 0.5, 0.5, ref) == pytest.approx(
        purchase_probability(cfg, 5.0, 2.0, 0.5, 0.5, ref)
    )
    # The linear arm does respond to it.
    assert purchase_probability(
        PHASE5_LINEAR, 9.0, 2.0, 0.5, 0.5, ref
    ) != pytest.approx(purchase_probability(PHASE5_LINEAR, 5.0, 2.0, 0.5, 0.5, ref))


def test_cliff_never_fires_on_a_first_purchase_at_these_parameters():
    """Explains the size of the result, and guards the claim in the spec."""
    cfg = PHASE5_ADDITIVE
    for b in cfg.buyer_classes:
        for s in cfg.seller_classes:
            for price in (s.price, cfg.discounted_price(s.price)):
                if price > b.budget_per_visit:
                    continue  # unaffordable, never evaluated as a purchase
                assert (b.budget_per_visit - price) >= cfg.budget_cliff_gap, (
                    b.name,
                    s.name,
                    price,
                )


def test_equivalence_verdict_three_outcomes():
    """The rule Phases 7b-7d reuse. An inconclusive result must not read as no effect."""
    assert equivalence_verdict(-0.01, 0.02) == "equivalent"
    assert equivalence_verdict(0.06, 0.09) == "material"
    assert equivalence_verdict(-0.09, -0.06) == "material"
    assert equivalence_verdict(0.03, 0.064) == "inconclusive"
    assert equivalence_verdict(-0.064, 0.03) == "inconclusive"
    # Exactly on the boundary counts as inside.
    assert equivalence_verdict(-MATERIALITY_PP / 100, MATERIALITY_PP / 100) == "equivalent"


def test_point_estimate_alone_would_have_misjudged_the_cliff_only_arm():
    """Why the bar is the interval and not the point estimate.

    At 30 seeds this arm's point estimate sits under 5 pp while its CI reaches
    past it. A point-estimate rule would call that immaterial; the interval
    rule correctly refuses to decide.
    """
    linear = run_seeds(PHASE5_LINEAR)
    cliff_only = run_seeds(PHASE5_CLIFF_ONLY)
    table = share_shift_table(PHASE5_CLIFF_ONLY, cliff_only, linear)
    mean, lo, hi, verdict = table["Middle_to_Shigh_share"]
    assert abs(mean) * 100 < MATERIALITY_PP  # a point-estimate rule would pass it
    assert hi * 100 > MATERIALITY_PP  # but the interval reaches past the bar
    assert verdict == "inconclusive"


def test_additive_arm_is_equivalent_and_triggers_rollback():
    linear = run_seeds(PHASE5_LINEAR)
    additive = run_seeds(PHASE5_ADDITIVE)
    table = share_shift_table(PHASE5_ADDITIVE, additive, linear)
    assert {v[3] for v in table.values()} == {"equivalent"}
    # Poor and Middle are untouched to the last decimal: their purchase
    # sequences never reach the cliff.
    for metric in (
        "Poor_to_Slow_share",
        "Poor_to_Shigh_share",
        "Middle_to_Slow_share",
        "Middle_to_Shigh_share",
    ):
        assert table[metric][0] == pytest.approx(0.0, abs=1e-12)


def test_phase5_criteria_grade_decisiveness_not_direction():
    linear = run_seeds(PHASE5_LINEAR)
    additive = run_seeds(PHASE5_ADDITIVE)
    criteria = evaluate_phase5(PHASE5_ADDITIVE, additive, linear, "additive")
    assert all(c.passed for c in criteria)
    decisive = next(c for c in criteria if "decisive" in c.name)
    assert "rolls back to the linear model" in decisive.note
