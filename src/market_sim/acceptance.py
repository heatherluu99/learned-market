"""Phase 1 acceptance criteria, evaluated as written in the spec.

Each criterion reports its own measured value so a failure says what was
actually observed, not just that something failed.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .config import Phase1Config
from .engine import RunResult


@dataclass
class CriterionResult:
    name: str
    passed: bool
    measured: str
    threshold: str
    note: str = ""


def evaluate(cfg: Phase1Config, results: list[RunResult]) -> list[CriterionResult]:
    participation = np.array([r.participation_rate for r in results])
    mean_participation = float(participation.mean())

    # 1. participation_rate in [0.6, 1.0]. Checked on the mean across seeds,
    #    with the per-seed range reported so a wide spread cannot hide behind a
    #    comfortable average.
    criteria = [
        CriterionResult(
            name="participation_rate in [0.6, 1.0]",
            passed=0.6 <= mean_participation <= 1.0,
            measured=f"mean {mean_participation:.3f} "
            f"(per-seed {participation.min():.3f}-{participation.max():.3f})",
            threshold="0.6 - 1.0",
        )
    ]

    # 2. Inventory remaining > 0 for at least some sellers.
    sellers_with_stock = int(
        sum(int(np.sum(r.seller_inventory_remaining > 0)) for r in results)
    )
    total_sellers = sum(len(r.seller_inventory_remaining) for r in results)
    stock_note = ""
    if all(r.blocked_counts.get("inventory_empty", 0) == 0 for r in results):
        stock_note = (
            "Inventory never ran out in any seed, so this criterion passed "
            "without exercising the inventory constraint. See the "
            "inventory-pressure run for evidence that stock is actually tracked."
        )
    criteria.append(
        CriterionResult(
            name="inventory_remaining > 0 for at least some sellers",
            passed=sellers_with_stock > 0,
            measured=f"{sellers_with_stock}/{total_sellers} seller-runs left stock",
            threshold="> 0",
            note=stock_note,
        )
    )

    # 3. Hard invariant: no buyer ever spends more than budget_per_visit.
    max_spent = max(float(r.buyer_total_spent.max()) for r in results)
    min_budget_left = min(float(r.buyer_budget_remaining.min()) for r in results)
    criteria.append(
        CriterionResult(
            name="no buyer spends more than budget_per_visit",
            passed=max_spent <= cfg.buyer.budget_per_visit and min_budget_left >= 0,
            measured=f"max spent {max_spent:.2f}, "
            f"min budget remaining {min_budget_left:.2f}",
            threshold=f"<= {cfg.buyer.budget_per_visit:.2f}, and never negative",
        )
    )
    return criteria


def convergence_band(values: np.ndarray) -> float:
    """Convergence tolerance for a metric: one standard error of its mean.

    The answer to "by which seed has the running mean settled" is entirely
    determined by this band, and on Phase 1's main run it ranges from seed 1 to
    seed 29 across defensible-looking choices:

        0.05 SD -> 29    0.10 SD -> 21    0.25 SD -> 11
        0.5 SEM -> 21    1 SEM   -> 11    2 SEM   -> 1

    So the band cannot be picked by eye, and it especially cannot be picked
    after seeing which value lands on the spec's "roughly seed 15" - that is
    the post-hoc rationalization this project's pre-registration discipline
    exists to prevent.

    One SEM is used because it is the natural scale of uncertainty in the
    quantity actually being watched: the running mean is an estimate of the
    mean, and SEM is that estimate's own noise level. Asking it to sit inside
    its own standard error is a statement about the estimator, not a threshold
    tuned to a target. An absolute hand-picked band is worse than useless -
    make it wider than the running mean's whole excursion, as an earlier
    version of this code did, and every metric "converges at seed 1", which
    says nothing about the data and everything about the band.
    """
    return float(np.std(values, ddof=1) / np.sqrt(len(values)))


def convergence_seed(values: np.ndarray, tolerance: float) -> int | None:
    """First seed count after which the running mean stays within `tolerance`
    of the final running mean. Returns None if it never settles.

    This operationalizes the spec's "confirm convergence (curve flattens) by
    roughly seed 15" — the spec asks for a visual check, and this is the
    numeric companion to the plot, not a replacement for it. Pass
    `convergence_band(values)` as the tolerance unless there is a specific
    reason to use an absolute one.
    """
    running = np.cumsum(values) / np.arange(1, len(values) + 1)
    final = running[-1]
    within = np.abs(running - final) <= tolerance
    for i in range(len(within)):
        if within[i:].all():
            return i + 1  # 1-based seed count
    return None
