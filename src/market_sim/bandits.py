"""Pricing bandits for Phase 7e-3a, as policies rather than engine branches.

Phase 7b's bandits live inside `run_season` and drive every seller at once.
Phase 7e compares one seller's pricing against a flat market and against
hand-designed schedules, so the learners here go through the same policy hook
those schedules use. That keeps the comparison honest in a way an engine
branch would not: schedule, bandit and Q-network all enter the market through
one door, and none of them can see anything the others cannot.

Both learn online inside a single season and start each season knowing
nothing, which is Phase 7b's protocol. The only difference between them is
whether the context is visible, which is what makes gate 3a a clean paired
comparison rather than a comparison of learning budgets.
"""

from __future__ import annotations

import numpy as np

#: Profits here run to about 45 a week. LinUCB's ridge prior and its
#: exploration term are both stated in reward units, so an unscaled reward
#: would make the prior negligible and alpha meaningless.
REWARD_SCALE = 50.0

#: The context, in order. `loyalty_stock` is the state gate 1 established
#: exists; `season_fraction` is what lets a policy express "invest early, stop
#: later", which is the shape 7e-2 found actually pays.
CONTEXT = ("bias", "loyalty_stock", "season_fraction")
#: The control: the same algorithm with the context removed, leaving only an
#: intercept. Comparing against UCB1 instead would confound context with
#: exploration mechanics, since UCB1's exploration constant is fixed and
#: LinUCB's is a free parameter.
BLIND = ("bias",)


def context_vector(state: dict, features: tuple[str, ...] = CONTEXT) -> np.ndarray:
    values = {
        "bias": 1.0,
        "loyalty_stock": float(state["loyalty_stock"]),
        "season_fraction": float(state["season_fraction"]),
        "last_arm": float(state["last_arm"]) / max(state["n_arms"] - 1, 1),
    }
    return np.array([values[f] for f in features])


class _OneSellerPolicy:
    """Shared plumbing: only `target` learns, everyone else holds the flat arm.

    The reward for the arm played last week arrives on the next call as
    `last_profit`, so the update is applied one call late. Week 0 has no
    previous arm and is skipped rather than credited with a zero.
    """

    def __init__(self, target: int, n_arms: int, flat_arm: int):
        self.target = target
        self.n_arms = n_arms
        self.flat_arm = flat_arm
        self.last_arm: int | None = None
        self.last_context: np.ndarray | None = None
        self.history: list[tuple[int, float]] = []
        self.pulled = 0

    def __call__(self, seller_id: int, state: dict) -> int:
        if seller_id != self.target:
            return self.flat_arm
        if self.last_arm is not None:
            reward = float(state["last_profit"]) / REWARD_SCALE
            self._update(self.last_arm, self.last_context, reward)
            self.history.append((self.last_arm, reward))
        context = self._context(state)
        # Every arm is tried once before any of them is judged. UCB1 does this
        # by definition; LinUCB does not, and without it an untried arm's
        # ridge prior of zero is never optimistic enough to be tried at all
        # once a played arm has returned a large positive reward. Phase 7b
        # found the initial sweep decided its verdict, so the two learners
        # here are given exactly the same one.
        arm = self.pulled if self.pulled < self.n_arms else self._choose(context)
        self.pulled += 1
        self.last_arm, self.last_context = arm, context
        return arm

    def _context(self, state: dict) -> np.ndarray:
        return context_vector(state)

    def _update(self, arm: int, context, reward: float) -> None:
        raise NotImplementedError

    def _choose(self, context) -> int:
        raise NotImplementedError


class UCB1(_OneSellerPolicy):
    """Context-blind UCB1, the same rule Phase 7b's engine branch applies.

    `c` scales the exploration term and is 1.0 by default, which is exactly
    7b's rule. It is exposed because leaving it fixed while LinUCB's alpha is
    free would hand the contextual policy an advantage that has nothing to do
    with context; both are tuned on the discovery block instead.
    """

    def __init__(self, target: int, n_arms: int, flat_arm: int, c: float = 1.0):
        super().__init__(target, n_arms, flat_arm)
        self.pulls = np.zeros(n_arms)
        self.value = np.zeros(n_arms)
        self.c = c
        self.t = 0

    def _update(self, arm: int, context, reward: float) -> None:
        self.pulls[arm] += 1
        self.value[arm] += (reward - self.value[arm]) / self.pulls[arm]

    def _choose(self, context) -> int:
        self.t += 1
        bonus = self.c * np.sqrt(2.0 * np.log(self.t) / np.maximum(self.pulls, 1))
        return int(np.argmax(self.value + bonus))


class LinUCB(_OneSellerPolicy):
    """Disjoint LinUCB (Li et al. 2010): one ridge model per arm.

    Used in its original linear form rather than over a learned
    representation, because the state here is three interpretable numbers
    rather than raw observations - a representation learner would be fitting
    an encoder to three features and its failure would be uninterpretable.
    """

    def __init__(
        self,
        target: int,
        n_arms: int,
        flat_arm: int,
        alpha: float = 0.5,
        features: tuple[str, ...] = CONTEXT,
    ):
        super().__init__(target, n_arms, flat_arm)
        self.features = features
        d = len(features)
        self.alpha = alpha
        self.A = np.array([np.eye(d) for _ in range(n_arms)])
        self.b = np.zeros((n_arms, d))
        # Rewards here are strictly positive and about 0.9 after scaling,
        # while the ridge prior predicts 0. Fitting the raw reward makes every
        # arm's estimate large and positive and the differences between them
        # negligible next to alpha. Centering on the running mean puts the
        # prior where it belongs: an untried arm is worth what the seller has
        # been earning, and the model fits the deviation from that.
        self.reward_mean = 0.0
        self.n_rewards = 0

    def _context(self, state: dict) -> np.ndarray:
        return context_vector(state, self.features)

    def _update(self, arm: int, context, reward: float) -> None:
        # The first reward establishes the baseline and carries no signal.
        # Centering it against a mean of zero would credit the whole ~0.9 to
        # whichever arm the initial sweep happened to start with, which is a
        # standing advantage for arm 0 and nothing to do with that arm.
        centred = 0.0 if self.n_rewards == 0 else reward - self.reward_mean
        self.n_rewards += 1
        self.reward_mean += (reward - self.reward_mean) / self.n_rewards
        self.A[arm] += np.outer(context, context)
        self.b[arm] += centred * context

    def _choose(self, context) -> int:
        scores = np.empty(self.n_arms)
        for a in range(self.n_arms):
            inverse = np.linalg.inv(self.A[a])
            theta = inverse @ self.b[a]
            scores[a] = theta @ context + self.alpha * np.sqrt(
                context @ inverse @ context
            )
        return int(np.argmax(scores))


def run(cfg, policy_factory, seeds, target: int = 0) -> np.ndarray:
    """Per seed: the target stall's mean weekly profit under a fresh learner.

    A new policy per season, because a learner that carried its estimates
    across seeds would be reporting cross-season training under a name that
    says online.
    """
    import dataclasses

    from .engine import run_season

    flat_arm = cfg.price_arms.index(1.0)
    scheduled = dataclasses.replace(cfg, price_rule="policy")
    out = []
    for seed in seeds:
        policy = policy_factory(target, len(cfg.price_arms), flat_arm)
        out.append(
            float(run_season(scheduled, seed, policy=policy).profits[:, target].mean())
        )
    return np.array(out)
