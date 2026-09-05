"""Phase 7b — the context-blind bandit, and what actually bounds it.

The interesting property of this sub-stage is negative: the bandit cannot
reach the profit optimum, and the reason is its arm set rather than its
learning rule. Both are pinned, because widening the arms would silently
encode the answer into the hypothesis space.
"""

from __future__ import annotations

import numpy as np
import pytest

from market_sim.acceptance import equivalence_verdict, evaluate_phase7b
from market_sim.config import (
    PHASE6_MAIN,
    PHASE7A_HILL,
    PHASE7B_EPS,
    PHASE7B_UCB,
)
from market_sim.engine import run_season, run_season_seeds

SEEDS = [0, 1, 7, 29]
ARMS = (0.8, 0.9, 1.0, 1.1, 1.2)


def test_arm_set_is_the_specified_local_range():
    """Not widened. The Slow optimum at 1.5x is deliberately out of reach."""
    for cfg in (PHASE7B_EPS, PHASE7B_UCB):
        assert cfg.price_arms == ARMS
    slow_price = next(c.price for c in PHASE7B_UCB.seller_classes if c.name == "Slow")
    assert slow_price * max(ARMS) == pytest.approx(2.4)
    assert 3.0 > slow_price * max(ARMS)  # the optimum is above the ceiling


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("cfg", [PHASE7B_EPS, PHASE7B_UCB])
def test_prices_only_ever_take_arm_values(cfg, seed):
    season = run_season(cfg, seed)
    initial = np.array([c.price for c in cfg.seller_classes for _ in range(c.count)])
    allowed = {round(p * m, 9) for p in initial for m in ARMS}
    seen = {round(float(v), 9) for v in season.posted_prices.ravel()}
    assert seen <= allowed


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("cfg", [PHASE7B_EPS, PHASE7B_UCB])
def test_every_arm_is_pulled_before_any_is_exploited(cfg, seed):
    """Initialization, not the algorithm, is what moved the verdict.

    Without this sweep epsilon-greedy commits early to whichever arm its first
    pull favoured and swings 12.8 profit per week; UCB1 requires the sweep by
    definition. Both are initialized the same way so the comparison is about
    the learning rules.
    """
    season = run_season(cfg, seed)
    first = season.posted_prices[: len(ARMS)]
    for seller in range(cfg.n_sellers):
        assert len(set(np.round(first[:, seller], 9))) == len(ARMS)


def test_bandit_randomness_does_not_disturb_the_market():
    """The policy has its own generator, so arms stay paired with each other."""
    a, b = run_season(PHASE7B_EPS, 3), run_season(PHASE7B_UCB, 3)
    assert np.array_equal(a.attended, b.attended)
    seasons = run_season_seeds(PHASE6_MAIN)
    assert float(np.mean([s.purchase_rate().mean() for s in seasons])) == pytest.approx(
        0.6916, abs=5e-4
    )


def test_the_arm_ceiling_binds_not_the_learning_rule():
    """Both algorithms stop at the ceiling, well short of the 3.00 optimum."""
    slow = [i for i, n in enumerate(PHASE7B_UCB.seller_class_of()) if n == "Slow"]
    ceiling = 2.0 * max(ARMS)
    for cfg in (PHASE7B_EPS, PHASE7B_UCB):
        seasons = run_season_seeds(cfg)
        final = np.array([s.posted_prices[-1, slow] for s in seasons]).mean()
        assert final <= ceiling
        assert final < 3.0


def test_profit_margin_is_relative_and_shares_stay_in_points():
    """Profit is not measured in percentage points; the margins differ."""
    # 6% of a baseline is material for profit...
    assert equivalence_verdict(0.055, 0.065, 5.0) == "material"
    # ...and a 6pp share shift is material too, but they are different scales:
    # a 4% profit change is equivalent, while a 4pp share change also is.
    assert equivalence_verdict(0.01, 0.04, 5.0) == "equivalent"
    assert equivalence_verdict(0.03, 0.07, 5.0) == "inconclusive"


def test_graduation_is_decisive_and_shares_do_not_move():
    """The bandit raises the seller's profit without changing market structure.

    Graded at 30 seeds this comparison is inconclusive on profit; the Phase 5
    protocol escalates such an arm rather than reading the point estimate, and
    the runner does that. Here the structural half is checked, which is
    decisive at 30 and is the part that bears on Phase 7's research question.
    """
    baseline = run_season_seeds(PHASE7A_HILL)
    arms = {c.name: run_season_seeds(c) for c in (PHASE7B_EPS, PHASE7B_UCB)}
    criteria = evaluate_phase7b(PHASE7B_UCB, arms, baseline)
    share_criteria = [c for c in criteria if "class-share" in c.name]
    assert len(share_criteria) == 2
    assert all(c.passed for c in share_criteria)
    assert all("equivalent on every tracked share" in c.note for c in share_criteria)
