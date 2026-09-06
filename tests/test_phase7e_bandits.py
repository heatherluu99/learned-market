"""Phase 7e-3a — the two learners, and the fairness of the comparison.

Gate 3a is only meaningful if the contextual policy and its control differ in
exactly one thing. Most of what is pinned here is that they do not differ in
anything else: same initial sweep, same reward timing, same plumbing, fresh
state per season.
"""

from __future__ import annotations

import dataclasses
import functools

import numpy as np
import pytest

from market_sim import acceptance, bandits
from market_sim.config import PHASE7E_RHO, phase7e_cell
from market_sim.engine import run_season


def _env():
    cell = phase7e_cell(rho=PHASE7E_RHO, delta=1.0, max_bonus=3.30)
    return acceptance.split_target_config(cell, 2.65, name="bandit_test")


def _play(policy, seed=0):
    env = _env()
    season = run_season(dataclasses.replace(env, price_rule="policy"), seed,
                        policy=policy)
    return season, [a for a, _ in policy.history]


@pytest.mark.parametrize("factory", [
    bandits.UCB1,
    functools.partial(bandits.LinUCB, features=bandits.BLIND),
    functools.partial(bandits.LinUCB, features=bandits.CONTEXT),
])
def test_every_learner_sweeps_every_arm_before_judging_any(factory):
    """Phase 7b found the initial sweep decided its verdict, so it is shared.

    Without it LinUCB never leaves its first arm: rewards here are strictly
    positive and large next to a ridge prior of zero, so a played arm outscores
    every untried arm's optimism term forever.
    """
    env = _env()
    policy = factory(0, len(env.price_arms), env.price_arms.index(1.0))
    _, arms = _play(policy)
    assert arms[: len(env.price_arms)] == list(range(len(env.price_arms)))
    assert set(arms) == set(range(len(env.price_arms)))


@pytest.mark.parametrize("factory", [
    bandits.UCB1, functools.partial(bandits.LinUCB, alpha=0.5)])
def test_only_the_target_seller_learns(factory):
    env = _env()
    flat_arm = env.price_arms.index(1.0)
    policy = factory(0, len(env.price_arms), flat_arm)
    season, _ = _play(policy)
    others = season.posted_prices[:, 1:]
    assert np.allclose(others, others[0], atol=0, rtol=0)
    assert not np.allclose(season.posted_prices[:, 0], season.posted_prices[0, 0])


def test_the_reward_lands_one_week_late_and_week_zero_is_not_credited():
    """`last_profit` is last week's, so the final week's reward never arrives.

    Crediting week 0 with the zero the engine passes before any week has run
    would teach every learner that its first arm earns nothing.
    """
    env = _env()
    policy = bandits.UCB1(0, len(env.price_arms), env.price_arms.index(1.0))
    _play(policy)
    assert len(policy.history) == env.weeks - 1
    assert all(r != 0.0 for _, r in policy.history)


def test_the_blind_control_cannot_see_the_context():
    state = {"loyalty_stock": 0.42, "season_fraction": 0.75, "last_arm": 3, "n_arms": 5}
    other = {**state, "loyalty_stock": 0.01, "season_fraction": 0.02}
    assert bandits.context_vector(state, bandits.BLIND) == pytest.approx([1.0])
    assert bandits.context_vector(other, bandits.BLIND) == pytest.approx([1.0])
    assert bandits.context_vector(state) != pytest.approx(bandits.context_vector(other))


def test_the_context_actually_varies_during_a_season():
    """A control that beats a constant feature would prove nothing."""
    env = _env()
    seen = []
    run_season(dataclasses.replace(env, price_rule="policy"), 0,
               policy=lambda s, st: (seen.append(st["loyalty_stock"]), 2)[1])
    stock = np.array([v for v in seen[::env.n_sellers]])
    assert stock.std() > 0.05
    assert stock.max() > 0.3


def test_centering_makes_a_constant_reward_carry_no_signal():
    """The fix for a prior of zero against rewards of about 0.9.

    Under constant rewards every arm is equally good and the fitted deviation
    must be zero, so an unexplored arm stays competitive.
    """
    policy = bandits.LinUCB(0, 3, 1, alpha=0.5)
    context = np.array([1.0, 0.4, 0.5])
    for arm in (0, 1, 2, 0, 1, 2):
        policy._update(arm, context, 0.9)
    assert np.abs(policy.b).max() == pytest.approx(0.0)
    assert policy.reward_mean == pytest.approx(0.9)
    # The first reward is the baseline, not evidence for the arm that drew it -
    # otherwise whichever arm the initial sweep starts with keeps a standing
    # advantage worth the whole reward.
    fresh = bandits.LinUCB(0, 3, 1, alpha=0.5)
    fresh._update(0, context, 0.9)
    assert np.abs(fresh.b).max() == pytest.approx(0.0)
    assert fresh.A[0][0, 0] == pytest.approx(2.0)  # the observation is still recorded


def test_each_season_gets_a_learner_that_knows_nothing():
    """Carrying estimates across seeds would be cross-season training."""
    env = _env()
    seeds = (0, 1, 2)
    a = bandits.run(env, functools.partial(bandits.LinUCB, alpha=0.5), seeds)
    b = bandits.run(env, functools.partial(bandits.LinUCB, alpha=0.5), seeds)
    assert np.array_equal(a, b)
    # ... and running the seeds in a different order gives the same per-seed
    # numbers, which it could not if state leaked between them.
    reversed_run = bandits.run(
        env, functools.partial(bandits.LinUCB, alpha=0.5), tuple(reversed(seeds)))
    assert np.allclose(a, reversed_run[::-1], atol=0, rtol=0)


def test_ucb1_default_is_phase_7b_s_rule():
    policy = bandits.UCB1(0, 4, 2)
    assert policy.c == 1.0
    policy.pulls = np.array([4.0, 1.0, 2.0, 3.0])
    policy.value = np.array([0.5, 0.4, 0.45, 0.55])
    policy.t = 9
    expected = np.argmax(policy.value + np.sqrt(2.0 * np.log(10) / policy.pulls))
    assert policy._choose(np.array([1.0])) == expected


def test_gate3a_grades_decisiveness_and_reports_the_unreachable_reference():
    flat = np.full(30, 44.0)
    blind = np.full(30, 40.0) + np.linspace(-0.3, 0.3, 30)
    criteria = acceptance.evaluate_phase7e3a(blind * 1.002, blind, blind * 0.9, flat)
    assert criteria[0].passed  # a tight equivalent verdict is decisive
    assert "equivalent" in criteria[0].measured
    assert not criteria[1].graded
    wide = blind + np.tile([-6.0, 6.0], 15)
    assert not acceptance.evaluate_phase7e3a(wide, blind, blind, flat)[0].passed
