"""Phase 3 — the environment variable, and what it must not disturb.

The load-bearing claim here is that adding visibility left Phases 1 and 2
bit-for-bit intact. That depends entirely on the visibility draw coming last
in the random stream, which is easy to break and silent when broken, so it is
pinned from both directions: the earlier phases' numbers, and the pairing
between Phase 2 and Phase 3.
"""

from __future__ import annotations

import numpy as np
import pytest

from market_sim.acceptance import evaluate_phase3, position_effect_by_tier
from market_sim.config import PHASE1_MAIN, PHASE2_MAIN, PHASE3_MAIN
from market_sim.engine import run_seeds, run_single

SEEDS = [0, 1, 7, 29]


def test_visibility_probability_follows_the_spec_formula():
    """visibility_prob = 0.5 + 0.5 * position_score."""
    assert PHASE3_MAIN.visibility_prob_of() == [0.95, 0.95, 0.65, 0.90, 0.65]
    for c in PHASE3_MAIN.seller_classes:
        assert c.visibility_prob == pytest.approx(0.5 + 0.5 * c.position_score)


def test_phases_without_positions_are_always_visible():
    """Phases 1-2 have no environment, so nothing is ever skipped."""
    assert not PHASE1_MAIN.has_environment
    assert not PHASE2_MAIN.has_environment
    assert PHASE3_MAIN.has_environment
    assert PHASE2_MAIN.visibility_prob_of() == [1.0] * PHASE2_MAIN.n_sellers
    assert run_single(PHASE2_MAIN, 0).blocked_counts["not_noticed"] == 0


def test_adding_visibility_did_not_move_phase1_or_phase2():
    """The whole reason the visibility draw is taken last.

    If someone moves it earlier in run_single, these two numbers shift and both
    validated tags stop reproducing.
    """
    p1 = run_seeds(PHASE1_MAIN)
    assert float(np.mean([r.participation_rate for r in p1])) == pytest.approx(
        0.8216666666666667, abs=1e-12
    )
    p2 = run_seeds(PHASE2_MAIN)
    assert float(np.mean([r.participation_rate for r in p2])) == pytest.approx(
        0.8183333333333334, abs=1e-12
    )


@pytest.mark.parametrize("seed", SEEDS)
def test_phase3_is_paired_with_phase2(seed):
    """Same seed must mean same preferences, visit orders and purchase draws.

    Visibility can only ever remove an opportunity, never add one, so Phase 3
    can never sell more in total than Phase 2 on the same seed.
    """
    p2 = run_single(PHASE2_MAIN, seed)
    p3 = run_single(PHASE3_MAIN, seed)
    assert p3.seller_n_sold.sum() <= p2.seller_n_sold.sum()
    assert p3.participation_rate <= p2.participation_rate


@pytest.mark.parametrize("seed", SEEDS)
def test_realized_visibility_tracks_the_configured_probability(seed):
    result = run_single(PHASE3_MAIN, seed)
    realized = result.visibility_rate_by_seller(PHASE3_MAIN.n_buyers)
    configured = np.array(PHASE3_MAIN.visibility_prob_of())
    # 100 buyers per seller, so a few points of sampling slack is expected.
    assert np.abs(realized - configured).max() < 0.12


@pytest.mark.parametrize("seed", SEEDS)
def test_unnoticed_stalls_are_not_recorded_as_declined_purchases(seed):
    """A buyer who never saw a stall has expressed no preference about it.

    Folding those into the utility-decline count would overstate how often
    buyers considered and rejected a seller.
    """
    result = run_single(PHASE3_MAIN, seed)
    assert result.blocked_counts["not_noticed"] > 0
    total = sum(result.blocked_counts.values()) + len(result.transactions)
    assert total == PHASE3_MAIN.n_buyers * PHASE3_MAIN.n_sellers


@pytest.mark.parametrize("seed", SEEDS)
def test_no_sales_from_a_stall_nobody_noticed(seed):
    result = run_single(PHASE3_MAIN, seed)
    for seller_id in range(PHASE3_MAIN.n_sellers):
        if result.seller_noticed[seller_id] == 0:
            assert result.seller_n_sold[seller_id] == 0


def test_far_stalls_sell_less_than_near_stalls_in_both_tiers():
    """The phase's graded criterion, at the level the spec states it."""
    effects = position_effect_by_tier(PHASE3_MAIN, run_seeds(PHASE3_MAIN))
    assert set(effects) == {"Slow", "Shigh"}
    for tier, (mean, lo, hi, _) in effects.items():
        assert mean > 0, tier
        assert lo > 0, tier


def test_tier_naming_deduplicates_split_position_entries():
    """Phase 3 lists a tier twice - once per position - but it is one tier."""
    assert len(PHASE3_MAIN.seller_classes) == 4
    assert PHASE3_MAIN.n_sellers == 5
    assert PHASE3_MAIN.seller_tier_names() == ["Slow", "Shigh"]
    assert PHASE3_MAIN.seller_class_of() == ["Slow", "Slow", "Slow", "Shigh", "Shigh"]


def test_price_reference_is_unchanged_by_adding_position():
    """Position is not a price. The normalizer must not notice it."""
    assert PHASE3_MAIN.price_reference == PHASE2_MAIN.price_reference == 6.0


def test_poor_is_still_walled_out_of_the_premium_tier():
    """Environment does not open a tier that affordability closed."""
    for seed in SEEDS:
        assert run_single(PHASE3_MAIN, seed).tier_share("Poor", "Shigh") == 0.0


def test_all_graded_criteria_pass():
    criteria = evaluate_phase3(PHASE3_MAIN, run_seeds(PHASE3_MAIN))
    assert len(criteria) == 3  # participation + one position effect per tier
    assert all(c.passed for c in criteria)
