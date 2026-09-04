"""Acceptance criteria, evaluated as written in the spec.

Each criterion reports its own measured value so a failure says what was
actually observed, not just that something failed. Criteria that the spec
records as observations rather than bars are returned with `graded=False` and
must not be counted toward pass/fail.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .config import MarketConfig
from .engine import RunResult


@dataclass
class CriterionResult:
    name: str
    passed: bool
    measured: str
    threshold: str
    note: str = ""
    #: False for items the spec deliberately leaves ungraded (Phase 2's Middle
    #: split, Poor's affordability-walled share). They are reported, never
    #: counted.
    graded: bool = True


def _budget_by_buyer(cfg: MarketConfig) -> np.ndarray:
    return np.array(
        [c.budget_per_visit for c in cfg.buyer_classes for _ in range(c.count)],
        dtype=float,
    )


def _participation_criterion(results: list[RunResult]) -> CriterionResult:
    participation = np.array([r.participation_rate for r in results])
    mean_participation = float(participation.mean())
    return CriterionResult(
        name="participation_rate in [0.6, 1.0]",
        passed=0.6 <= mean_participation <= 1.0,
        measured=f"mean {mean_participation:.3f} "
        f"(per-seed {participation.min():.3f}-{participation.max():.3f})",
        threshold="0.6 - 1.0",
    )


def _budget_invariant_criterion(
    cfg: MarketConfig, results: list[RunResult]
) -> CriterionResult:
    """Hard invariant: no buyer outspends their own class's budget."""
    budgets = _budget_by_buyer(cfg)
    worst_overspend = max(
        float(np.max(r.buyer_total_spent - budgets)) for r in results
    )
    min_budget_left = min(float(r.buyer_budget_remaining.min()) for r in results)
    return CriterionResult(
        name="no buyer spends more than their class budget",
        passed=worst_overspend <= 0 and min_budget_left >= 0,
        measured=f"largest overspend {worst_overspend:+.2f}, "
        f"min budget remaining {min_budget_left:.2f}",
        threshold="<= 0.00 overspend, and budget never negative",
    )


def evaluate(cfg: MarketConfig, results: list[RunResult]) -> list[CriterionResult]:
    """Phase 1 acceptance criteria."""
    criteria = [_participation_criterion(results)]

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
    criteria.append(_budget_invariant_criterion(cfg, results))
    return criteria


def mean_difference_ci(
    a: np.ndarray, b: np.ndarray, confidence: float = 0.95
) -> tuple[float, float, float]:
    """(mean difference, lower bound, upper bound) for a - b, paired by seed.

    Normal-approximation interval on the across-seed mean. Pairs where either
    side is NaN — a class that bought nothing that seed, so its share is
    undefined — are dropped rather than treated as zero.
    """
    diff = np.asarray(a, dtype=float) - np.asarray(b, dtype=float)
    diff = diff[~np.isnan(diff)]
    if len(diff) < 2:
        return float("nan"), float("nan"), float("nan")
    z = 1.959963985 if confidence == 0.95 else abs(float(confidence))
    mean = float(diff.mean())
    half = z * float(diff.std(ddof=1)) / np.sqrt(len(diff))
    return mean, mean - half, mean + half


def evaluate_phase2(
    cfg: MarketConfig, results: list[RunResult]
) -> list[CriterionResult]:
    """Phase 2 acceptance criteria.

    The stratification bar is cross-class (Rich vs Middle) and graded on the
    across-seed mean, never per seed. Both original within-class bars were
    unusable: the Poor one was vacuous because Poor_to_Shigh_share is 0.000 by
    the affordability wall, and the Rich one demanded a Shigh share above 0.667,
    which is unreachable because price only ever lowers utility. See
    docs/phase_specifications.md, Phase 2.
    """
    criteria = [_participation_criterion(results)]

    rich_hi = np.array([r.tier_share("Rich", "Shigh") for r in results])
    mid_hi = np.array([r.tier_share("Middle", "Shigh") for r in results])
    gap, lo, hi = mean_difference_ci(rich_hi, mid_hi)
    n_negative = int(np.sum((rich_hi - mid_hi) < 0))
    criteria.append(
        CriterionResult(
            name="stratification: mean(Rich_to_Shigh - Middle_to_Shigh) > 0, 95% CI excludes 0",
            passed=bool(gap > 0 and lo > 0),
            measured=f"gap {gap:+.3f}, 95% CI [{lo:+.3f}, {hi:+.3f}]",
            threshold="mean > 0 and CI lower bound > 0",
            note=(
                f"Graded on the across-seed mean only: the per-seed gap is "
                f"negative in {n_negative} of {len(results)} seeds, so a "
                f"per-seed bar would be noise. Rich is only 10 buyers."
            ),
        )
    )

    shigh_min = min(
        int(
            np.min(
                [
                    inv
                    for inv, sc in zip(r.seller_inventory_remaining, r.seller_classes)
                    if sc == "Shigh"
                ]
            )
        )
        for r in results
    )
    criteria.append(
        CriterionResult(
            name="Shigh sellers do not fully sell out",
            passed=shigh_min > 0,
            measured=f"lowest Shigh inventory across all seeds: {shigh_min}",
            threshold="> 0",
        )
    )

    # Reported, never graded.
    mid_lo_mean = float(np.nanmean([r.tier_share("Middle", "Slow") for r in results]))
    mid_hi_mean = float(np.nanmean(mid_hi))
    criteria.append(
        CriterionResult(
            name="Middle tier split (observation, no bar)",
            passed=True,
            graded=False,
            measured=f"to Slow {mid_lo_mean:.3f}, to Shigh {mid_hi_mean:.3f}",
            threshold="none - no direction is encoded for Middle",
        )
    )

    poor_hi = np.array([r.tier_share("Poor", "Shigh") for r in results])
    poor_blocked = sum(
        r.blocked_by_budget_pairs.get(("Poor", "Shigh"), 0) for r in results
    )
    criteria.append(
        CriterionResult(
            name="Poor to Shigh share (observation, no bar)",
            passed=True,
            graded=False,
            measured=f"{np.nanmean(poor_hi):.3f}, with {poor_blocked:,} "
            f"evaluations blocked by affordability",
            threshold="none - affordability wall, not a price_sensitivity result",
            note=(
                "Poor's budget of 3 cannot reach the Shigh price of 6, so this "
                "is 0.000 by arithmetic. It would be 0.000 with alpha set to 0, "
                "or with Poor made the least price-sensitive class. Never cite "
                "it as evidence that price sensitivity produces stratification."
            ),
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
    values = np.asarray(values, dtype=float)
    values = values[~np.isnan(values)]
    if len(values) < 2:
        return float("nan")
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
    values = np.asarray(values, dtype=float)
    running = np.cumsum(values) / np.arange(1, len(values) + 1)
    final = running[-1]
    within = np.abs(running - final) <= tolerance
    for i in range(len(within)):
        if within[i:].all():
            return i + 1  # 1-based seed count
    return None
