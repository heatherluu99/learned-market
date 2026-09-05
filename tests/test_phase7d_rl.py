"""Phase 7d — the RL policy, and the two things that make its null credible.

A null is only worth reporting if the setup could have produced a positive.
The two ways it could have been hollow are pinned here: training and
evaluation seeds must be disjoint, and the policy must actually be able to
express a non-constant, state-dependent price.
"""

from __future__ import annotations

import numpy as np
import pytest
import torch

from market_sim import rl
from market_sim.config import PHASE7B_UCB, PHASE7D, PHASE7D_TRAIN_SEEDS
from market_sim.engine import run_season


def test_training_and_evaluation_seeds_are_disjoint():
    """A policy scored on the seeds it was fitted to measures memorization."""
    assert not set(PHASE7D_TRAIN_SEEDS) & set(PHASE7D.seeds)
    assert min(PHASE7D_TRAIN_SEEDS) >= 1000


def test_7d_uses_the_same_arms_as_7b():
    """The comparison isolates the reward horizon, not the action space."""
    assert PHASE7D.price_arms == PHASE7B_UCB.price_arms
    assert PHASE7D.buyer_classes == PHASE7B_UCB.buyer_classes
    assert PHASE7D.seller_classes == PHASE7B_UCB.seller_classes
    assert PHASE7D.weeks == PHASE7B_UCB.weeks


def test_policy_rule_requires_a_policy():
    with pytest.raises(ValueError, match="needs a policy"):
        run_season(PHASE7D, 0)


def test_the_policy_sees_only_the_sellers_own_state():
    """Phase 7c found no external state worth conditioning on, so none is given."""
    seen = []

    def spy(seller_id, state):
        seen.append(set(state))
        return 0

    run_season(PHASE7D, 0, policy=spy)
    assert seen
    for keys in seen:
        assert keys == {"loyal_fraction", "last_arm", "last_profit",
                        "season_fraction", "n_arms"}


def test_a_constant_policy_pins_the_price_to_its_arm():
    for arm, price in enumerate(PHASE7D.price_arms):
        season = run_season(PHASE7D, 0, policy=lambda s, st, a=arm: a)
        expected = np.array(
            [c.price * price for c in PHASE7D.seller_classes for _ in range(c.count)]
        )
        assert np.allclose(season.posted_prices[-1], expected)


def test_the_network_can_express_a_state_dependent_price():
    """Guards against a null produced by a policy that could only be constant.

    A network whose output does not vary with its input could return an
    equivalent verdict for reasons having nothing to do with the market.
    """
    torch.manual_seed(0)
    net = rl.QNetwork(len(PHASE7D.price_arms))
    states = [
        {"loyal_fraction": f, "last_arm": a, "last_profit": p,
         "season_fraction": w, "n_arms": len(PHASE7D.price_arms)}
        for f, a, p, w in ((0.0, 0, 0.0, 0.0), (0.4, 4, 30.0, 1.0), (0.2, 2, 15.0, 0.5))
    ]
    outputs = [net(torch.tensor(rl._features(s), dtype=torch.float32)) for s in states]
    assert not torch.allclose(outputs[0], outputs[1], atol=1e-4)


def test_training_runs_and_the_result_is_usable():
    """A short fit, only checking the pipeline produces a working policy."""
    net = rl.train_policy(PHASE7D, PHASE7D_TRAIN_SEEDS[:6], epochs=1, torch_seed=1)
    seasons = rl.evaluate(PHASE7D, net, (0, 1))
    assert len(seasons) == 2
    for s in seasons:
        assert s.profits is not None
        assert set(np.round(s.posted_prices[:, 0], 6)) <= {
            round(2.0 * m, 6) for m in PHASE7D.price_arms
        }


def test_greedy_policy_is_deterministic():
    torch.manual_seed(0)
    net = rl.QNetwork(len(PHASE7D.price_arms))
    a = run_season(PHASE7D, 3, policy=rl.greedy_policy(net))
    b = run_season(PHASE7D, 3, policy=rl.greedy_policy(net))
    assert np.array_equal(a.posted_prices, b.posted_prices)
