"""Phase 4 — the promotion mechanism, and the arms that make it measurable.

Two things are pinned hardest here. First, that adding promotions left every
earlier phase untouched: the promotion draws come last in the random stream
and are taken unconditionally, so all arms stay paired. Second, that the
"expected responder" prediction is derived from parameters rather than from
the observed result, which is what makes the interaction criterion a
prediction rather than a description.
"""

from __future__ import annotations

import numpy as np
import pytest

from market_sim.acceptance import (
    class_promotion_lift,
    evaluate_phase4,
    promotion_lift,
)
from market_sim.config import (
    PHASE1_MAIN,
    PHASE2_MAIN,
    PHASE3_MAIN,
    PHASE4_FORCED,
    PHASE4_MAIN,
    PHASE4_NO_PROMOTION,
)
from market_sim.engine import run_seeds, run_single

SEEDS = [0, 1, 7, 29]


def test_earlier_phases_are_untouched_by_adding_promotions():
    """Promotion draws are taken last, so nothing before Phase 4 moves."""
    assert not PHASE1_MAIN.has_promotions
    assert not PHASE3_MAIN.has_promotions
    p1 = run_seeds(PHASE1_MAIN)
    assert float(np.mean([r.participation_rate for r in p1])) == pytest.approx(
        0.8216666666666667, abs=1e-12
    )
    p2 = run_seeds(PHASE2_MAIN)
    assert float(np.mean([r.participation_rate for r in p2])) == pytest.approx(
        0.8163333333333334, abs=1e-12
    )


def test_no_promotion_arm_reproduces_phase3_exactly():
    """The baseline arm is Phase 3 with a promotion mechanism that never fires.

    If this diverges, the promotion draws are being consumed in a way that
    perturbs the market rather than sitting inertly at the end of the stream.
    """
    for seed in SEEDS:
        p3 = run_single(PHASE3_MAIN, seed)
        p4 = run_single(PHASE4_NO_PROMOTION, seed)
        assert np.array_equal(p3.seller_n_sold, p4.seller_n_sold)
        assert p3.participation_rate == p4.participation_rate
        assert p4.promoted_seller is None


@pytest.mark.parametrize("seller_id", range(5))
@pytest.mark.parametrize("seed", [0, 29])
def test_forced_arm_promotes_exactly_the_named_seller(seller_id, seed):
    result = run_single(PHASE4_FORCED[seller_id], seed)
    assert result.promoted_seller == seller_id
    prices = result.effective_prices
    posted = [c.price for c in PHASE4_MAIN.seller_classes for _ in range(c.count)]
    for i, price in enumerate(prices):
        expected = posted[i] * 0.7 if i == seller_id else posted[i]
        assert price == pytest.approx(expected)


def test_discount_is_30_percent():
    assert PHASE4_MAIN.discounted_price(2.0) == pytest.approx(1.4)
    assert PHASE4_MAIN.discounted_price(6.0) == pytest.approx(4.2)


def test_expected_responder_is_derived_from_parameters_only():
    """The interaction prediction must be computable before any run.

    Slow discounts to 1.4, which Poor (budget 3) can reach; Shigh discounts to
    4.2, which Poor cannot, so the prediction moves up to Middle.
    """
    assert PHASE4_MAIN.expected_responder("Slow") == "Poor"
    assert PHASE4_MAIN.expected_responder("Shigh") == "Middle"


def test_a_30_percent_discount_barely_opens_shigh_to_poor():
    """4.2 exceeds Poor's *mean* budget of 3, and almost every draw from it.

    This was an exact zero when every Poor buyer held exactly 3.0. With
    budgets dispersed the discounted price sits in the extreme upper tail of
    Poor's distribution, so it reaches a vanishing number of buyers rather
    than none - which is the more honest statement, and the hard zero was
    itself an artefact of the degenerate population.
    """
    poor = next(c for c in PHASE4_MAIN.buyer_classes if c.name == "Poor")
    assert PHASE4_MAIN.discounted_price(6.0) > poor.budget_per_visit
    baseline = run_seeds(PHASE4_NO_PROMOTION)
    forced = run_seeds(PHASE4_FORCED[3])  # a Shigh stall
    lift = class_promotion_lift(forced, baseline, 3, "Poor")
    total_poor = sum(len([t for t in r.transactions if t.buyer_class == "Poor"])
                     for r in forced)
    assert lift.sum() / total_poor < 0.001


def test_the_market_arm_cannot_support_a_per_seller_comparison():
    """Documents why the criteria are graded on the forced arms instead.

    Pinned as a test because the whole design of this phase rests on it, and
    a future change to seeds or probability could quietly make the claim in
    the spec false without anything failing.
    """
    market = run_seeds(PHASE4_MAIN)
    promoted = [r.promoted_seller for r in market if r.promoted_seller is not None]
    per_seller = [promoted.count(i) for i in range(PHASE4_MAIN.n_sellers)]
    assert len(promoted) < 10  # about 0.2 * 30
    assert min(per_seller) == 0  # at least one seller never promoted at all


@pytest.mark.parametrize("seller_id", range(5))
def test_forcing_a_promotion_never_reduces_that_sellers_sales(seller_id):
    """Paired on identical seeds, a discount can only help the discounted stall."""
    baseline = run_seeds(PHASE4_NO_PROMOTION)
    forced = run_seeds(PHASE4_FORCED[seller_id])
    mean, lo, _ = promotion_lift(forced, baseline, seller_id)
    assert mean > 0
    assert lo > 0


def test_promotion_lift_concentrates_in_the_predicted_class():
    """The phase's second research question: interaction, not level shift."""
    baseline = run_seeds(PHASE4_NO_PROMOTION)
    for seller_id, tier in ((0, "Slow"), (3, "Shigh")):
        forced = run_seeds(PHASE4_FORCED[seller_id])
        responder = PHASE4_MAIN.expected_responder(tier)
        lifts = {
            c.name: class_promotion_lift(forced, baseline, seller_id, c.name).mean()
            for c in PHASE4_MAIN.buyer_classes
        }
        assert max(lifts, key=lifts.get) == responder, (tier, lifts)


def test_all_graded_criteria_pass():
    baseline = run_seeds(PHASE4_NO_PROMOTION)
    forced = {i: run_seeds(PHASE4_FORCED[i]) for i in range(PHASE4_MAIN.n_sellers)}
    criteria = evaluate_phase4(PHASE4_MAIN, forced, baseline)
    # participation + 5 per-seller lifts + 2 tier interactions
    assert len(criteria) == 8
    assert all(c.passed for c in criteria)
