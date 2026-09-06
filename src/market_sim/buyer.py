"""Phase 9a — a buyer policy distilled from the hand-written rule.

The teacher is this project's own hand-coded buyer, so what is fitted here is
policy distillation of a simulator, not learning of human behaviour. It is also
a *stochastic* teacher - a Bernoulli policy whose action is a draw - so the fit
targets its probability and the metrics are distributional. See
docs/phase_specifications.md, Phase 9a.

The student does not see what the teacher sees. That is deliberate and is the
phase's whole point: a synthetic user conditions on observable behavioural
context, not on the latent taste draw and exact budget the simulator happens to
hold. What cannot be recovered from the observation set is an irreducible
floor, and the floor is measured rather than assumed.
"""

from __future__ import annotations

import dataclasses

import numpy as np
import torch
from torch import nn

from .config import MarketConfig
from .engine import ENCOUNTER_FIELDS, run_season

#: What a synthetic user could plausibly condition on: the buyer's segment, the
#: offer in front of it, its own relationship with this seller, how much it has
#: already done this week, and a persona proxy for the latent traits.
OBSERVED = (
    "buyer_class_index", "price", "is_premium", "streak_here",
    "purchases_this_week", "spent_this_week", "season_fraction", "history_rate",
)
#: Deliberately absent, and the reason the floor is not zero:
#:   preference[b, s]  - the latent taste draw, fixed for the season
#:   budget_remaining  - the buyer's own dispersed budget
#:   price_sensitivity - its exact alpha
HIDDEN = ("preference", "budget_remaining", "price_sensitivity")


def encounters(cfg: MarketConfig, seeds) -> np.ndarray:
    """Collect every affordable encounter across `seeds` as a float array."""
    recording = dataclasses.replace(cfg, record_encounters=True)
    rows = []
    for seed in seeds:
        rows.extend(run_season(recording, seed).encounters)
    return np.asarray(rows, dtype=np.float64)


def design_matrix(data: np.ndarray) -> torch.Tensor:
    """Observation columns, with the buyer segment one-hot rather than ordinal.

    Left as an index, a network would be free to read Poor < Middle < Rich as a
    magnitude, which is an ordering the segments do not carry.
    """
    idx = {f: ENCOUNTER_FIELDS.index(f) for f in OBSERVED}
    cls = data[:, idx["buyer_class_index"]].astype(int)
    onehot = np.zeros((len(data), 3))
    onehot[np.arange(len(data)), cls] = 1.0
    rest = np.stack([data[:, idx[f]] for f in OBSERVED if f != "buyer_class_index"], 1)
    return torch.tensor(np.concatenate([onehot, rest], axis=1), dtype=torch.float32)


def targets(data: np.ndarray) -> tuple[torch.Tensor, torch.Tensor]:
    p = torch.tensor(data[:, ENCOUNTER_FIELDS.index("p_teacher")], dtype=torch.float32)
    a = torch.tensor(data[:, ENCOUNTER_FIELDS.index("action")], dtype=torch.float32)
    return p, a


class BuyerPolicy(nn.Module):
    """P(buy | observed context). Outputs a probability, never an argmax."""

    def __init__(self, n_features: int, hidden: int = 64, depth: int = 2):
        super().__init__()
        layers: list[nn.Module] = []
        width = n_features
        for _ in range(depth):
            layers += [nn.Linear(width, hidden), nn.ReLU()]
            width = hidden
        layers.append(nn.Linear(width, 1))
        self.net = nn.Sequential(*layers)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return torch.sigmoid(self.net(x)).squeeze(-1)


def train(
    data: np.ndarray,
    *,
    soft_labels: bool = True,
    hidden: int = 64,
    depth: int = 2,
    epochs: int = 40,
    lr: float = 3e-3,
    batch_size: int = 4096,
    torch_seed: int = 0,
) -> BuyerPolicy:
    """Fit the student with a proper scoring rule.

    `soft_labels=True` fits `p_T(s)` directly, which the simulator makes
    available and which removes label noise rather than averaging it away.
    `False` fits the sampled 0/1 action, which is what ordinary behavioural
    cloning would have. Both minimize at `p_theta = p_T`; the difference is
    variance, and running both is what separates a label-noise explanation from
    a distribution-shift one.
    """
    torch.manual_seed(torch_seed)
    x = design_matrix(data)
    p, a = targets(data)
    y = p if soft_labels else a
    net = BuyerPolicy(x.shape[1], hidden, depth)
    optimizer = torch.optim.Adam(net.parameters(), lr=lr)
    generator = torch.Generator().manual_seed(torch_seed)
    for _ in range(epochs):
        order = torch.randperm(len(x), generator=generator)
        for start in range(0, len(x), batch_size):
            batch = order[start : start + batch_size]
            predicted = net(x[batch]).clamp(1e-6, 1 - 1e-6)
            loss = nn.functional.binary_cross_entropy(predicted, y[batch])
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
    return net


@torch.no_grad()
def predict(net: BuyerPolicy, data: np.ndarray) -> np.ndarray:
    return net(design_matrix(data)).numpy().astype(np.float64)


def as_engine_policy(net: BuyerPolicy):
    """Wrap a fitted student for `cfg.buyer_policy`.

    The engine hands over the observation columns positionally, in the order
    `OBSERVED` declares, so the same feature layout is used for fitting and for
    acting. Building it twice from two orderings is the silent failure this
    avoids.
    """
    net.eval()

    def policy(class_index, price, is_premium, streak, purchases, spent,
               season_fraction, history_rate) -> float:
        onehot = [0.0, 0.0, 0.0]
        onehot[int(class_index)] = 1.0
        x = torch.tensor(
            [onehot + [price, is_premium, streak, purchases, spent,
                       season_fraction, history_rate]],
            dtype=torch.float32,
        )
        with torch.no_grad():
            return float(net(x)[0])

    return policy


def policy_distance(data: np.ndarray, predicted: np.ndarray) -> float:
    """E|p_T - p_theta|.

    Under the engine's shared purchase_draw this is exactly the probability
    that teacher and student take different actions on an encounter, and it is
    the expected total variation distance between two Bernoulli policies - not
    an accuracy. See docs/phase_specifications.md, Phase 9a.
    """
    p = data[:, ENCOUNTER_FIELDS.index("p_teacher")]
    return float(np.abs(p - predicted).mean())


def log_loss(data: np.ndarray, predicted: np.ndarray) -> float:
    """Against the sampled action, in nats. Floored by the teacher's entropy."""
    a = data[:, ENCOUNTER_FIELDS.index("action")]
    q = np.clip(predicted, 1e-9, 1 - 1e-9)
    return float(-(a * np.log(q) + (1 - a) * np.log(1 - q)).mean())


def entropy_floor(data: np.ndarray) -> float:
    """The teacher's own entropy: no model can score below this on samples."""
    p = np.clip(data[:, ENCOUNTER_FIELDS.index("p_teacher")], 1e-9, 1 - 1e-9)
    return float(-(p * np.log(p) + (1 - p) * np.log(1 - p)).mean())


STRATA = {
    "buyer class": lambda d: d[:, ENCOUNTER_FIELDS.index("buyer_class_index")],
    "seller tier": lambda d: d[:, ENCOUNTER_FIELDS.index("is_premium")],
    "loyalty streak": lambda d: np.minimum(
        d[:, ENCOUNTER_FIELDS.index("streak_here")], 3
    ),
    "season third": lambda d: np.minimum(
        (d[:, ENCOUNTER_FIELDS.index("season_fraction")] * 3).astype(int), 2
    ),
    "spend so far": lambda d: np.minimum(
        (d[:, ENCOUNTER_FIELDS.index("spent_this_week")] / 2.0).astype(int), 3
    ),
}


def calibration(data: np.ndarray, predicted: np.ndarray) -> dict[str, float]:
    """Worst |mean p_theta - mean p_T| within any cell of each stratum.

    Aggregate calibration is passed by a constant predictor, which is the
    failure this is built to catch: a model emitting the market's mean rate is
    globally calibrated and conditionally empty.
    """
    p = data[:, ENCOUNTER_FIELDS.index("p_teacher")]
    out = {}
    for name, key in STRATA.items():
        k = key(data)
        worst = 0.0
        for value in np.unique(k):
            mask = k == value
            if mask.sum() < 50:
                continue
            worst = max(worst, abs(predicted[mask].mean() - p[mask].mean()))
        out[name] = float(worst)
    return out
