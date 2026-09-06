"""Phase 7d — a pricing policy trained on multi-week return.

The point of this module is to answer Phase 7's headline question by
measurement rather than by diagnostic: does optimizing cumulative reward find
anything that per-week optimization does not? The gate expects a null, with
its reasons recorded, but a hand-designed schedule search cannot rule out a
policy nobody thought of - which is why this is built.

The policy sees only what a seller could observe about itself. Phase 7c
established that no external market state predicts which arm is best, so
conditioning on one would add parameters without adding information.
"""

from __future__ import annotations

import dataclasses
from collections import deque

import numpy as np
import torch
from torch import nn

from .config import MarketConfig
from .engine import run_season

#: Order is load-bearing: the same layout is built in `_features` for training
#: and for evaluation, and a mismatch would be silent.
FEATURES = ("loyal_fraction", "last_arm", "last_profit", "season_fraction")
#: Phase 7e-3b adds the mechanism's own state. Kept as a separate constant so
#: Phase 7d still trains on exactly the four features it was validated with -
#: appending to FEATURES would silently change a tagged result.
FEATURES_7E = FEATURES + ("loyalty_stock",)
#: Weekly profit is order-10; scaling keeps the value targets in a range the
#: network trains on without a learning-rate fight.
REWARD_SCALE = 30.0


class QNetwork(nn.Module):
    """Small MLP over the seller's self-observed features, one output per arm."""

    def __init__(self, n_arms: int, n_features: int = len(FEATURES), hidden: int = 64):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(n_features, hidden),
            nn.ReLU(),
            nn.Linear(hidden, hidden),
            nn.ReLU(),
            nn.Linear(hidden, n_arms),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


def _features(
    state: dict,
    features: tuple[str, ...] = FEATURES,
    reward_scale: float = REWARD_SCALE,
) -> list[float]:
    # Looked up one at a time rather than built as a dict: a dict evaluates
    # every key, so asking for Phase 7d's four features would fail on a state
    # that has no `loyalty_stock` - which is every hand-built state in a test.
    def value(name: str) -> float:
        if name == "last_arm":
            return state["last_arm"] / max(state["n_arms"] - 1, 1)
        if name == "last_profit":
            return state["last_profit"] / reward_scale
        return state[name]

    return [value(f) for f in features]


class _RecordingPolicy:
    """Chooses arms and remembers what it saw, so transitions can be rebuilt.

    The engine's policy hook is called before the week runs, so the reward and
    the next state do not exist yet. Rather than complicate the hook, the
    policy records (state, action) per seller and the caller zips that with the
    season's realized profits afterwards.
    """

    def __init__(
        self,
        net: QNetwork,
        n_sellers: int,
        epsilon: float,
        rng: np.random.Generator,
        features: tuple[str, ...] = FEATURES,
        reward_scale: float = REWARD_SCALE,
        target: int | None = None,
        flat_arm: int = 0,
    ):
        self.net, self.epsilon, self.rng = net, epsilon, rng
        self.features, self.reward_scale = features, reward_scale
        self.target, self.flat_arm = target, flat_arm
        self.log: list[list[tuple[list[float], int]]] = [[] for _ in range(n_sellers)]

    def __call__(self, seller_id: int, state: dict) -> int:
        # Phase 7e trains one seller against an otherwise flat market, the same
        # setup its schedules and bandits are measured in. `target=None` keeps
        # Phase 7d's behaviour, where every seller runs the policy.
        if self.target is not None and seller_id != self.target:
            return self.flat_arm
        feats = _features(state, self.features, self.reward_scale)
        if self.rng.random() < self.epsilon:
            arm = int(self.rng.integers(0, state["n_arms"]))
        else:
            with torch.no_grad():
                arm = int(torch.argmax(self.net(torch.tensor(feats, dtype=torch.float32))))
        self.log[seller_id].append((feats, arm))
        return arm


def greedy_policy(
    net: QNetwork,
    features: tuple[str, ...] = FEATURES,
    reward_scale: float = REWARD_SCALE,
    target: int | None = None,
    flat_arm: int = 0,
):
    """Evaluation policy: no exploration, no recording."""

    def policy(seller_id: int, state: dict) -> int:
        if target is not None and seller_id != target:
            return flat_arm
        feats = _features(state, features, reward_scale)
        with torch.no_grad():
            return int(torch.argmax(net(torch.tensor(feats, dtype=torch.float32))))

    return policy


def train_policy(
    cfg: MarketConfig,
    train_seeds: tuple[int, ...],
    *,
    gamma: float = 0.9,
    epochs: int = 3,
    lr: float = 1e-3,
    batch_size: int = 256,
    torch_seed: int = 0,
    features: tuple[str, ...] = FEATURES,
    reward_scale: float = REWARD_SCALE,
    target: int | None = None,
    flat_arm: int = 0,
) -> QNetwork:
    """Fit a Q-network on multi-week discounted return.

    gamma of 0.9 over weeks is roughly a ten-week horizon - long enough that a
    discount paid now to build loyalty could be recovered, which is precisely
    the trade-off this phase is testing for.
    """
    torch.manual_seed(torch_seed)
    net = QNetwork(len(cfg.price_arms), len(features))
    optimizer = torch.optim.Adam(net.parameters(), lr=lr)
    buffer: deque = deque(maxlen=200_000)
    rng = np.random.default_rng(torch_seed)

    for epoch in range(epochs):
        # Exploration decays across epochs: broad early,近-greedy by the end.
        epsilon = max(0.05, 0.5 * (1 - epoch / max(epochs - 1, 1)))
        for seed in train_seeds:
            policy = _RecordingPolicy(net, cfg.n_sellers, epsilon, rng, features,
                                      reward_scale, target, flat_arm)
            season = run_season(cfg, seed, policy=policy)
            for seller_id, steps in enumerate(policy.log):
                if not steps:
                    continue  # a seller held flat, so it generated no decisions
                rewards = season.profits[:, seller_id] / reward_scale
                for w, (feats, arm) in enumerate(steps):
                    nxt = steps[w + 1][0] if w + 1 < len(steps) else None
                    buffer.append((feats, arm, float(rewards[w]), nxt))

        for _ in range(200):
            if len(buffer) < batch_size:
                break
            idx = rng.integers(0, len(buffer), size=batch_size)
            batch = [buffer[i] for i in idx]
            states = torch.tensor([b[0] for b in batch], dtype=torch.float32)
            actions = torch.tensor([b[1] for b in batch], dtype=torch.int64)
            rewards = torch.tensor([b[2] for b in batch], dtype=torch.float32)
            has_next = torch.tensor([b[3] is not None for b in batch])
            next_states = torch.tensor(
                [b[3] if b[3] is not None else [0.0] * len(features) for b in batch],
                dtype=torch.float32,
            )
            with torch.no_grad():
                bootstrap = net(next_states).max(dim=1).values * has_next
            # Named `td_target`, not `target`: the seller being trained is also
            # called target, and rebinding it here left epoch 1 constructing a
            # policy with a tensor for a seller id.
            td_target = rewards + gamma * bootstrap
            predicted = net(states).gather(1, actions.unsqueeze(1)).squeeze(1)
            loss = nn.functional.smooth_l1_loss(predicted, td_target)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
    return net


def evaluate(
    cfg: MarketConfig,
    net: QNetwork,
    seeds: tuple[int, ...],
    features: tuple[str, ...] = FEATURES,
    reward_scale: float = REWARD_SCALE,
    target: int | None = None,
    flat_arm: int = 0,
) -> list:
    """Run the greedy policy on seeds it was never fitted to."""
    policy = greedy_policy(net, features, reward_scale, target, flat_arm)
    return [run_season(dataclasses.replace(cfg, seeds=(s,)), s, policy=policy) for s in seeds]
