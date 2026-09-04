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


def position_effect_by_tier(
    cfg: MarketConfig, results: list[RunResult]
) -> dict[str, tuple[float, float, float, int]]:
    """Per tier: (mean near-minus-far n_sold, CI low, CI high, seeds positive).

    "Near" and "far" are the highest- and lowest-position entries within a
    tier, compared as per-seller means so tiers with unequal numbers of near
    and far stalls are still comparable.
    """
    positions = np.array(
        [
            c.position_score if c.position_score is not None else 1.0
            for c in cfg.seller_classes
            for _ in range(c.count)
        ]
    )
    tiers = np.array(cfg.seller_class_of())
    sold = np.array([r.seller_n_sold for r in results], dtype=float)

    out = {}
    for tier in cfg.seller_tier_names():
        in_tier = tiers == tier
        tier_positions = positions[in_tier]
        if tier_positions.max() == tier_positions.min():
            continue  # no position contrast inside this tier
        near = in_tier & (positions == tier_positions.max())
        far = in_tier & (positions == tier_positions.min())
        diff = sold[:, near].mean(axis=1) - sold[:, far].mean(axis=1)
        mean, lo, hi = mean_difference_ci(diff, np.zeros_like(diff))
        out[tier] = (mean, lo, hi, int((diff > 0).sum()))
    return out


def evaluate_phase3(
    cfg: MarketConfig, results: list[RunResult]
) -> list[CriterionResult]:
    """Phase 3 acceptance criteria.

    The position criterion is stated as a paired CI rather than the spec's
    original "measurably lower", which set no bar at all. The class-share
    shift and the participation shift are reported here as ungraded; the
    spec pre-registers a null share shift as an acceptable outcome, so it must
    not be gradeable.
    """
    criteria = [_participation_criterion(results)]

    effects = position_effect_by_tier(cfg, results)
    for tier, (mean, lo, hi, n_pos) in effects.items():
        criteria.append(
            CriterionResult(
                name=f"position effect in {tier}: near sells more than far",
                passed=bool(mean > 0 and lo > 0),
                measured=f"near-far {mean:+.2f} per seller, 95% CI [{lo:+.2f}, {hi:+.2f}]",
                threshold="mean > 0 and CI lower bound > 0",
                note=f"positive in {n_pos} of {len(results)} seeds",
            )
        )
    return criteria


def promotion_lift(
    forced: list[RunResult], baseline: list[RunResult], seller_id: int
) -> tuple[float, float, float]:
    """Paired (mean lift, CI low, CI high) in a seller's n_sold when promoted."""
    return mean_difference_ci(
        np.array([r.seller_n_sold[seller_id] for r in forced], dtype=float),
        np.array([r.seller_n_sold[seller_id] for r in baseline], dtype=float),
    )


def class_promotion_lift(
    forced: list[RunResult],
    baseline: list[RunResult],
    seller_id: int,
    buyer_class: str,
) -> np.ndarray:
    """Per-seed lift in one class's purchases from one promoted seller."""
    return np.array(
        [
            f.n_sold_by(buyer_class, seller_id) - b.n_sold_by(buyer_class, seller_id)
            for f, b in zip(forced, baseline)
        ],
        dtype=float,
    )


def evaluate_phase4(
    cfg: MarketConfig,
    forced_by_seller: dict[int, list[RunResult]],
    baseline: list[RunResult],
) -> list[CriterionResult]:
    """Phase 4 acceptance criteria, graded on the paired forced arms.

    The market's own 0.2 promotion lottery cannot support these comparisons —
    about one promoted run per seller over 30 seeds — so measurement is done
    on forced arms paired against a promotion-free arm on identical seeds. See
    docs/phase_specifications.md, Phase 4.
    """
    criteria = [_participation_criterion(baseline)]
    seller_classes = cfg.seller_class_of()

    for seller_id, forced in sorted(forced_by_seller.items()):
        mean, lo, hi = promotion_lift(forced, baseline, seller_id)
        criteria.append(
            CriterionResult(
                name=f"promotion lift at seller {seller_id} ({seller_classes[seller_id]})",
                passed=bool(mean > 0 and lo > 0),
                measured=f"{mean:+.2f} units, 95% CI [{lo:+.2f}, {hi:+.2f}]",
                threshold="mean > 0 and CI lower bound > 0",
            )
        )

    # Class interaction, one check per tier, using the tier's lowest-position
    # promoted seller as the representative (any seller of the tier would do;
    # the prediction is about the tier's price, not the stall).
    for tier in cfg.seller_tier_names():
        responder = cfg.expected_responder(tier)
        if responder is None:
            continue
        seller_id = next(
            i for i, name in enumerate(seller_classes)
            if name == tier and i in forced_by_seller
        )
        forced = forced_by_seller[seller_id]
        responder_lift = class_promotion_lift(forced, baseline, seller_id, responder)
        others = [c.name for c in cfg.buyer_classes if c.name != responder]
        worst_name, worst = None, None
        for other in others:
            other_lift = class_promotion_lift(forced, baseline, seller_id, other)
            mean, lo, hi = mean_difference_ci(responder_lift, other_lift)
            if worst is None or lo < worst[1]:
                worst_name, worst = other, (mean, lo, hi)
        mean, lo, hi = worst
        criteria.append(
            CriterionResult(
                name=(
                    f"class interaction at {tier}: {responder} responds more than "
                    f"every other class"
                ),
                passed=bool(mean > 0 and lo > 0),
                measured=(
                    f"{responder} lift {responder_lift.mean():+.2f}; narrowest margin "
                    f"vs {worst_name}: {mean:+.2f}, 95% CI [{lo:+.2f}, {hi:+.2f}]"
                ),
                threshold="every pairwise margin > 0 with CI excluding 0",
                note=(
                    f"{responder} is the lowest-budget class that can afford "
                    f"{tier} at its discounted price - predicted from the "
                    f"parameters, not chosen after seeing the result."
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
