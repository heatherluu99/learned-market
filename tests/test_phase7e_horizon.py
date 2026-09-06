"""Phase 7e-3b — the Q-network in the mechanism-enabled environment.

Most of what is pinned here protects Phase 7d: its module is reused rather than
copied, and a parameterization that quietly changed its feature set or its
training loop would move a tagged result without failing anything else.
"""

from __future__ import annotations

import dataclasses
import importlib.util
import pathlib

import numpy as np
import pytest
import torch

from market_sim import acceptance, rl
from market_sim.config import PHASE7D, PHASE7E_RHO, phase7e_cell
from market_sim.engine import run_season


def _env():
    cell = phase7e_cell(rho=PHASE7E_RHO, delta=1.0, max_bonus=3.30)
    return acceptance.split_target_config(cell, 2.65, name="horizon_test")


def test_phase7d_s_feature_set_is_untouched():
    """7e appends to a separate constant, because FEATURES is a tagged contract."""
    assert rl.FEATURES == ("loyal_fraction", "last_arm", "last_profit",
                           "season_fraction")
    assert rl.FEATURES_7E == rl.FEATURES + ("loyalty_stock",)
    assert rl.QNetwork(5).net[0].in_features == len(rl.FEATURES)
    assert rl.QNetwork(5, len(rl.FEATURES_7E)).net[0].in_features == 5


def test_features_are_built_in_the_order_requested_and_only_those():
    """A dict comprehension over every feature would break 7d's states.

    Phase 7d's tests build states by hand with four keys and no `loyalty_stock`,
    and evaluating a key that is not asked for turns that into a KeyError.
    """
    state = {"loyal_fraction": 0.3, "last_arm": 2, "last_profit": 60.0,
             "season_fraction": 0.5, "n_arms": 5}
    four = rl._features(state, rl.FEATURES, reward_scale=30.0)
    assert four == pytest.approx([0.3, 0.5, 2.0, 0.5])
    with pytest.raises(KeyError):
        rl._features(state, rl.FEATURES_7E)
    five = rl._features({**state, "loyalty_stock": 0.42}, rl.FEATURES_7E,
                        reward_scale=30.0)
    assert five == pytest.approx(four + [0.42])
    # order follows the tuple, not the dict literal
    assert rl._features({**state, "loyalty_stock": 0.42},
                        ("loyalty_stock", "season_fraction")) == pytest.approx([0.42, 0.5])


def test_only_the_target_seller_is_priced_by_the_policy():
    env = _env()
    flat_arm = env.price_arms.index(1.0)
    net = rl.QNetwork(len(env.price_arms), len(rl.FEATURES_7E))
    policy = rl.greedy_policy(net, rl.FEATURES_7E, 50.0, target=0, flat_arm=flat_arm)
    season = run_season(dataclasses.replace(env, price_rule="policy"), 0, policy=policy)
    others = season.posted_prices[:, 1:]
    assert np.allclose(others, others[0], atol=0, rtol=0)


def test_training_survives_more_than_one_epoch_with_a_target():
    """Regression: the TD target used to be named `target` and shadow the seller.

    Rebinding it inside the gradient loop left the next epoch constructing a
    recording policy with a tensor for a seller id, and the failure only
    appeared from epoch 1 onward.
    """
    env = dataclasses.replace(_env(), price_rule="policy")
    net = rl.train_policy(
        env, tuple(range(1000, 1002)), epochs=2, features=rl.FEATURES_7E,
        reward_scale=50.0, target=0, flat_arm=env.price_arms.index(1.0),
    )
    assert isinstance(net, rl.QNetwork)


def test_the_trained_network_can_express_a_time_varying_price():
    """7e-2's winner is 'discount early, then stop', so the class must allow it.

    A network that cannot vary its output with `season_fraction` would return a
    null for reasons having nothing to do with the market.
    """
    torch.manual_seed(0)
    net = rl.QNetwork(5, len(rl.FEATURES_7E))
    base = {"loyal_fraction": 0.2, "last_arm": 2, "last_profit": 43.0,
            "loyalty_stock": 0.4, "n_arms": 5}
    outputs = [
        net(torch.tensor(rl._features({**base, "season_fraction": w}, rl.FEATURES_7E),
                         dtype=torch.float32))
        for w in (0.0, 0.5, 1.0)
    ]
    assert not torch.allclose(outputs[0], outputs[-1])


def test_the_three_seed_blocks_are_mutually_disjoint():
    path = (pathlib.Path(__file__).resolve().parents[1]
            / "experiments" / "phase7e" / "run_phase7e3b.py")
    spec = importlib.util.spec_from_file_location("run_phase7e3b", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    train, evaluate, resolve = (set(mod.TRAIN_SEEDS), set(mod.EVAL_SEEDS),
                                set(mod.RESOLUTION_SEEDS))
    tune = set(range(2000, 2060))  # 7e-3a's, which chose the bandit's alpha
    assert not train & resolve
    assert not train & tune
    assert not resolve & tune
    assert evaluate < resolve  # the escalation widens the same block


def test_gate3b_separates_beating_the_bandit_from_finding_the_schedule():
    """A learner can clear the first criterion and still have found nothing."""
    bandit = np.full(60, 40.0) + np.linspace(-0.2, 0.2, 60)
    schedule = np.full(60, 44.3)
    flat = np.full(60, 43.4)

    # material gain, most of the way to the schedule: both criteria pass
    good = acceptance.evaluate_phase7e3b(bandit * 1.09, bandit, schedule, flat)
    assert good[0].passed and good[1].passed

    # equivalent: a verdict was reached, but nothing was found
    null = acceptance.evaluate_phase7e3b(bandit * 1.001, bandit, schedule, flat)
    assert null[0].passed
    assert not null[1].passed
    assert "of the way from the bandit" in null[1].measured

    # an interval straddling the margin decides nothing
    noisy = bandit * 1.05 + np.tile([-5.0, 5.0], 30)
    assert not acceptance.evaluate_phase7e3b(noisy, bandit, schedule, flat)[0].passed
