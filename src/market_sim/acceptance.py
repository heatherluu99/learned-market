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


#: The project's standing materiality margin, in percentage points. Introduced
#: at Phase 5 and reused verbatim at Phases 7b-7d (ROADMAP.md, "Methodology:
#: not cumulative - a toolbox, used selectively, with two deliberate reuses").
MATERIALITY_PP = 5.0


def equivalence_verdict(
    lo: float, hi: float, margin_pp: float = MATERIALITY_PP
) -> str:
    """Classify a share-shift CI (in shares, not points) against ±margin.

    Three outcomes, and the third one matters: a comparison can fail to show a
    material effect *and* fail to rule one out. Reporting that as "no effect"
    would be claiming a conclusion the data does not support.

    - "equivalent"    - the whole CI lies inside ±margin: a material effect is
                        ruled out, so the added complexity is not justified.
    - "material"      - the whole CI lies beyond +margin or below -margin.
    - "inconclusive"  - the CI straddles a boundary. Neither claim is available
                        at this sample size.
    """
    lo_pp, hi_pp = lo * 100, hi * 100
    if -margin_pp <= lo_pp and hi_pp <= margin_pp:
        return "equivalent"
    if lo_pp > margin_pp or hi_pp < -margin_pp:
        return "material"
    return "inconclusive"


def share_shift_table(
    cfg: MarketConfig, variant: list[RunResult], baseline: list[RunResult]
) -> dict[str, tuple[float, float, float, str]]:
    """Per tracked class-share metric: (mean shift, CI low, CI high, verdict)."""
    out = {}
    for bc in cfg.buyer_classes:
        for sc in cfg.seller_tier_names():
            a = np.array([r.tier_share(bc.name, sc) for r in variant])
            b = np.array([r.tier_share(bc.name, sc) for r in baseline])
            mean, lo, hi = mean_difference_ci(a, b)
            out[f"{bc.name}_to_{sc}_share"] = (mean, lo, hi, equivalence_verdict(lo, hi))
    return out


def evaluate_phase5(
    cfg: MarketConfig, variant: list[RunResult], baseline: list[RunResult], arm: str
) -> list[CriterionResult]:
    """Phase 5 acceptance criteria for one nonlinear arm against the linear one.

    The graded requirement is that the comparison be *decisive*, not that it
    come out either way: this phase exists to decide whether the nonlinearity
    earns its place, and an inconclusive test decides nothing. Which way a
    decisive result points - keep the nonlinearity, or roll back to linear -
    is the finding, not the criterion.
    """
    criteria = [_participation_criterion(variant)]
    table = share_shift_table(cfg, variant, baseline)

    inconclusive = [k for k, v in table.items() if v[3] == "inconclusive"]
    material = [k for k, v in table.items() if v[3] == "material"]
    worst = max(table.items(), key=lambda kv: max(abs(kv[1][1]), abs(kv[1][2])))
    criteria.append(
        CriterionResult(
            name=f"{arm}: linear-vs-nonlinear comparison is decisive on every tracked share",
            passed=not inconclusive,
            measured=(
                f"{len(table) - len(inconclusive)}/{len(table)} decisive; widest CI is "
                f"{worst[0]} at [{worst[1][1] * 100:+.2f}, {worst[1][2] * 100:+.2f}] pp"
            ),
            threshold=f"every CI wholly inside or wholly outside ±{MATERIALITY_PP:g} pp",
            note=(
                f"inconclusive: {', '.join(inconclusive)}"
                if inconclusive
                else (
                    f"material on {', '.join(material)}"
                    if material
                    else "equivalent on every tracked share - the nonlinearity is "
                    "not justified and the project rolls back to the linear model"
                )
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


def evaluate_phase6(
    cfg: MarketConfig, seasons: list, control: list
) -> list[CriterionResult]:
    """Phase 6 acceptance criteria.

    Both graded comparisons are against the no-loyalty control or against the
    season's own early weeks, never against the raw stability level: most of
    that level is seller popularity and fixed preference, not memory. See
    docs/phase_specifications.md, Phase 6.
    """
    purchase = np.array([s.purchase_rate().mean() for s in seasons])
    mean_purchase = float(purchase.mean())
    criteria = [
        CriterionResult(
            name="purchase_rate in [0.6, 1.0]",
            passed=0.6 <= mean_purchase <= 1.0,
            measured=f"mean {mean_purchase:.3f} "
            f"(attendance {np.mean([s.attendance_rate().mean() for s in seasons]):.3f})",
            threshold="0.6 - 1.0",
            note="Graded on purchase_rate, the quantity Phases 1-5 called "
            "participation_rate. attendance_rate is reported beside it.",
        )
    ]

    loyal = np.array([np.nanmean(s.pair_stability()[1:]) for s in seasons])
    plain = np.array([np.nanmean(s.pair_stability()[1:]) for s in control])
    mean, lo, hi = mean_difference_ci(loyal, plain)
    criteria.append(
        CriterionResult(
            name="memory raises pair stability above the no-loyalty control",
            passed=bool(mean > 0 and lo > 0),
            measured=f"{loyal.mean():.3f} vs {plain.mean():.3f}, difference "
            f"{mean:+.4f}, 95% CI [{lo:+.4f}, {hi:+.4f}]",
            threshold="mean > 0 and CI lower bound > 0",
            note="The control's own level is not zero - unequal seller "
            "popularity and season-long fixed preference produce stability "
            "without any memory at all.",
        )
    )

    # Week 1 alone is the early window, not weeks 1-5. With the streak capped
    # at 3 the bonus maxes out after three consecutive weeks, so the mechanism
    # saturates by about week 4 and a 5-week early window averages over the
    # rise it is meant to measure. This narrowing was made *after* the
    # pre-registered weeks-1-5 window failed, and is recorded as a post-hoc
    # correction in docs/phase_specifications.md rather than presented as
    # pre-registered.
    early = np.array([s.pair_stability()[1] for s in seasons])
    late = np.array([np.nanmean(s.pair_stability()[17:22]) for s in seasons])
    rise, rlo, rhi = mean_difference_ci(late, early)
    criteria.append(
        CriterionResult(
            name="pair stability rises from week 1 to the end of the season",
            passed=bool(rise > 0 and rlo > 0),
            measured=f"week 1 {early.mean():.3f} -> weeks 17-21 {late.mean():.3f}, "
            f"rise {rise:+.4f}, 95% CI [{rlo:+.4f}, {rhi:+.4f}]",
            threshold="mean > 0 and CI lower bound > 0",
            note="Weak and window-sensitive: it fails at a weeks 1-2 early "
            "window (+0.0247, CI [-0.0003, +0.0497]). The control comparison "
            "above is the phase's substantive finding, not this.",
        )
    )
    return criteria


def plateau_week(seasons: list) -> int | None:
    """First week after which the running mean of stability stays within 1 SEM.

    The same convergence band used across seeds in Phases 1-5, applied along
    the week axis instead.
    """
    # Drop week 0 before averaging: it has no predecessor, so its column is
    # all-NaN by construction and nanmean over it warns about an empty slice.
    weekly = np.array([s.pair_stability() for s in seasons])[:, 1:]
    traj = np.nanmean(weekly, axis=0)
    return convergence_seed(traj, convergence_band(traj))


def evaluate_phase7a(
    cfg: MarketConfig, hill: list, fixed: list
) -> list[CriterionResult]:
    """Phase 7a acceptance criteria.

    7a does not have to *win* - it is the baseline the three later sub-stages
    are graded against. What it has to be is non-degenerate, and the criteria
    are written around the specific way the originally specified rule was not:
    it was a one-way ratchet that collapsed prices by 97% and, in doing so,
    fabricated premium-tier access for the Poor class. See
    docs/phase_specifications.md, Phase 7a.
    """
    purchase = np.array([s.purchase_rate().mean() for s in hill])
    mean_purchase = float(purchase.mean())
    criteria = [
        CriterionResult(
            name="purchase_rate in [0.6, 1.0]",
            passed=0.6 <= mean_purchase <= 1.0,
            measured=f"mean {mean_purchase:.3f}",
            threshold="0.6 - 1.0",
        )
    ]

    # Prices bounded. The floor is what the old rule blew through; the ceiling
    # catches the mirror failure of a runaway climb.
    initial = np.array(
        [c.price for c in cfg.seller_classes for _ in range(c.count)], dtype=float
    )
    finals = np.array([s.posted_prices[-1] for s in hill])
    ratio = finals / initial
    criteria.append(
        CriterionResult(
            name="posted prices stay bounded (0.5x - 3x their initial value)",
            passed=bool(ratio.min() >= 0.5 and ratio.max() <= 3.0),
            measured=f"final price ratio {ratio.min():.2f}x - {ratio.max():.2f}x initial",
            threshold="0.5x - 3.0x",
            note="The rejected rule reached 0.036x here, which is what made it "
            "unusable as a baseline rather than merely uninteresting.",
        )
    )

    # The affordability wall must not be breached by deflation. Stated as the
    # exact condition under which it breaks, so it is derived rather than a
    # threshold picked by eye.
    poor_budget = min(c.budget_per_visit for c in cfg.buyer_classes)
    shigh_ids = [i for i, n in enumerate(cfg.seller_class_of()) if n == "Shigh"]
    lowest_shigh = min(
        float(np.min(s.posted_prices[:, shigh_ids])) for s in hill
    )
    criteria.append(
        CriterionResult(
            name="premium-tier price never falls within the lowest budget",
            passed=lowest_shigh > poor_budget,
            measured=f"lowest Shigh posted price {lowest_shigh:.3f} "
            f"vs Poor's budget {poor_budget:g}",
            threshold=f"> {poor_budget:g}",
            note="The rejected rule crossed this at week 14 and produced 1,987 "
            "Poor purchases at the premium tier - an artefact of runaway "
            "deflation that would have read as a finding about adaptive pricing.",
        )
    )

    # A heuristic that never moves is as useless a baseline as one that
    # explodes: the dead-band variant moved prices under 1% in 66 weeks.
    hill_profit = np.array([s.profits.sum(axis=1).mean() for s in hill])
    fixed_profit = np.array([s.profits.sum(axis=1).mean() for s in fixed])
    gain, glo, ghi = mean_difference_ci(hill_profit, fixed_profit)
    criteria.append(
        CriterionResult(
            name="adaptive pricing raises profit over the fixed-price baseline",
            passed=bool(gain > 0 and glo > 0),
            measured=f"{fixed_profit.mean():.1f} -> {hill_profit.mean():.1f} per week, "
            f"{gain:+.1f}, 95% CI [{glo:+.1f}, {ghi:+.1f}]",
            threshold="mean > 0 and CI lower bound > 0",
        )
    )
    return criteria
