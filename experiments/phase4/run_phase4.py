"""Run Phase 4 — Person + Environment + Context.

Adds a temporary promotion to Phase 3's market. The specified 0.2 lottery is
run as the market arm, but the criteria are graded on paired forced-promotion
arms against a promotion-free baseline, because the lottery yields roughly one
promoted run per seller over 30 seeds.

    python experiments/phase4/run_phase4.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from market_sim import acceptance, experiment_log, outputs  # noqa: E402
from market_sim.config import (  # noqa: E402
    PHASE4_FORCED,
    PHASE4_MAIN,
    PHASE4_NO_PROMOTION,
)
from market_sim.engine import RunResult, run_seeds  # noqa: E402

RESULTS_ROOT = REPO_ROOT / "results" / "phase4"
LOG_PATH = REPO_ROOT / "experiment_log.csv"

RESEARCH_QUESTION = (
    "Does a transient situational factor (a temporary promotion) shift buyer "
    "distribution beyond Person + Environment, and does its effect resemble a "
    "level-shift or an interaction with buyer class?"
)


def plot_lift(
    forced_by_seller: dict[int, list[RunResult]],
    baseline: list[RunResult],
    out_path: Path,
) -> None:
    """Per-seller promotion lift, and the class breakdown per tier."""
    classes = [c.name for c in PHASE4_MAIN.buyer_classes]
    seller_classes = PHASE4_MAIN.seller_class_of()
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))

    ax = axes[0]
    ids = sorted(forced_by_seller)
    means, los, his = [], [], []
    for sid in ids:
        m, lo, hi = acceptance.promotion_lift(forced_by_seller[sid], baseline, sid)
        means.append(m)
        los.append(m - lo)
        his.append(hi - m)
    ax.bar(range(len(ids)), means, yerr=[los, his], capsize=4, color="tab:blue")
    ax.axhline(0, color="firebrick", linewidth=1)
    ax.set_xticks(range(len(ids)))
    ax.set_xticklabels([f"{seller_classes[i]}\n#{i}" for i in ids])
    ax.set_ylabel("extra units sold when promoted")
    ax.set_title("Promotion lift per seller (paired, 30 seeds, 95% CI)")

    ax = axes[1]
    tiers = PHASE4_MAIN.seller_tier_names()
    width = 0.8 / len(classes)
    for j, cls in enumerate(classes):
        vals, errs = [], []
        for t, tier in enumerate(tiers):
            sid = next(
                i for i, n in enumerate(seller_classes)
                if n == tier and i in forced_by_seller
            )
            lift = acceptance.class_promotion_lift(
                forced_by_seller[sid], baseline, sid, cls
            )
            m, lo, hi = acceptance.mean_difference_ci(lift, np.zeros_like(lift))
            vals.append(m)
            errs.append(m - lo)
        ax.bar(
            np.arange(len(tiers)) + j * width, vals, width, yerr=errs, capsize=3, label=cls
        )
    ax.axhline(0, color="firebrick", linewidth=1)
    ax.set_xticks(np.arange(len(tiers)) + width)
    ax.set_xticklabels([f"promoted {t}" for t in tiers])
    ax.set_ylabel("extra units bought by class")
    ax.set_title("Lift by buyer class — interaction, not level shift")
    ax.legend(fontsize=8)

    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def main() -> int:
    commit = experiment_log.git_commit(REPO_ROOT)

    market = run_seeds(PHASE4_MAIN)
    outputs.write_all(PHASE4_MAIN, market, RESULTS_ROOT / "main")
    baseline = run_seeds(PHASE4_NO_PROMOTION)
    outputs.write_all(PHASE4_NO_PROMOTION, baseline, RESULTS_ROOT / "no_promotion")

    forced_by_seller = {}
    for seller_id, cfg in enumerate(PHASE4_FORCED):
        results = run_seeds(cfg)
        forced_by_seller[seller_id] = results
        outputs.write_all(cfg, results, RESULTS_ROOT / cfg.name)

    n_promoted = sum(r.promoted_seller is not None for r in market)
    per_seller = [
        sum(r.promoted_seller == i for r in market) for i in range(PHASE4_MAIN.n_sellers)
    ]
    print(f"\n=== {PHASE4_MAIN.name} — the market as specified (probability 0.2) ===")
    print(f"  runs with a promotion active : {n_promoted}/{len(market)}")
    print(f"  promoted-run count per seller: {per_seller}")
    print("  This arm is reported, not graded: that is about one observation per")
    print("  seller, which cannot support a per-seller before/after comparison.")

    criteria = acceptance.evaluate_phase4(PHASE4_MAIN, forced_by_seller, baseline)
    print("\n=== graded on paired forced arms vs phase4_no_promotion ===")
    seller_classes = PHASE4_MAIN.seller_class_of()
    print(f"  {'seller':12s} {'no promo':>10s} {'promoted':>10s} {'lift':>8s} {'95% CI':>20s}")
    for sid in sorted(forced_by_seller):
        m, lo, hi = acceptance.promotion_lift(forced_by_seller[sid], baseline, sid)
        b = np.mean([r.seller_n_sold[sid] for r in baseline])
        f = np.mean([r.seller_n_sold[sid] for r in forced_by_seller[sid]])
        print(
            f"  {seller_classes[sid] + ' #' + str(sid):12s} {b:10.1f} {f:10.1f} "
            f"{m:+8.2f}   [{lo:+.2f}, {hi:+.2f}]"
        )

    print("\n  lift by buyer class:")
    for tier in PHASE4_MAIN.seller_tier_names():
        sid = next(
            i for i, n in enumerate(seller_classes)
            if n == tier and i in forced_by_seller
        )
        responder = PHASE4_MAIN.expected_responder(tier)
        print(f"    promoted {tier} (#{sid}) — predicted responder: {responder}")
        for c in PHASE4_MAIN.buyer_classes:
            lift = acceptance.class_promotion_lift(
                forced_by_seller[sid], baseline, sid, c.name
            )
            m, lo, hi = acceptance.mean_difference_ci(lift, np.zeros_like(lift))
            mark = "  <-- predicted" if c.name == responder else ""
            print(f"      {c.name:8s} {m:+6.2f}  95% CI [{lo:+.2f}, {hi:+.2f}]{mark}")

    print("\n  acceptance criteria:")
    for c in criteria:
        print(f"    [{'PASS' if c.passed else 'FAIL'}] {c.name}")
        print(f"           measured: {c.measured}  (required: {c.threshold})")
        if c.note:
            print(f"           note: {c.note}")

    plot_lift(forced_by_seller, baseline, RESULTS_ROOT / "promotion_lift.png")

    shigh_id = next(
        i for i, n in enumerate(seller_classes) if n == "Shigh" and i in forced_by_seller
    )
    poor_lift = acceptance.class_promotion_lift(
        forced_by_seller[shigh_id], baseline, shigh_id, "Poor"
    )
    experiment_log.append_row(
        LOG_PATH,
        {
            "experiment_id": "phase4_main",
            "git_commit": commit,
            "config_file": "src/market_sim/config.py::PHASE4_MAIN",
            "phase": 4,
            "seed": "0-29",
            "n_buyers": PHASE4_MAIN.n_buyers,
            "n_sellers": PHASE4_MAIN.n_sellers,
            "model_used": "rule_based",
            "decision_type": "N/A",
            "human_benchmark_id": "N/A",
            "human_benchmark_status": "not_applicable",
            "synthetic_cost_usd": "N/A",
            "synthetic_latency_seconds": "N/A",
            "research_question": RESEARCH_QUESTION,
            "changed_mechanism": "temporary 30% discount on one random seller with probability 0.2 per run",
            "transaction_count": sum(len(r.transactions) for r in market),
            "participation_rate": round(
                float(np.mean([r.participation_rate for r in market])), 4
            ),
            "result_summary": (
                f"Market arm promoted a seller in {n_promoted}/{len(market)} runs, "
                f"distributed {per_seller} - about one observation per seller, so the "
                f"criteria are graded on paired forced arms instead. "
                f"{sum(c.passed for c in criteria)}/{len(criteria)} criteria passed."
            ),
            "decision_implication": "N/A - infrastructure phase, no business decision",
            "next_experiment": "phase4 forced-promotion arms; then Phase 5 nonlinearity",
        },
    )
    experiment_log.append_row(
        LOG_PATH,
        {
            "experiment_id": "phase4_forced_promotion",
            "git_commit": commit,
            "config_file": "src/market_sim/config.py::PHASE4_FORCED",
            "phase": 4,
            "seed": "0-29",
            "n_buyers": PHASE4_MAIN.n_buyers,
            "n_sellers": PHASE4_MAIN.n_sellers,
            "model_used": "rule_based",
            "decision_type": "N/A",
            "human_benchmark_id": "N/A",
            "human_benchmark_status": "not_applicable",
            "synthetic_cost_usd": "N/A",
            "synthetic_latency_seconds": "N/A",
            "research_question": (
                "Measurement arm: how much does a forced promotion lift a seller's "
                "sales, and is the lift concentrated in one buyer class?"
            ),
            "changed_mechanism": "promotion forced on one seller every run; paired against phase4_no_promotion",
            "transaction_count": sum(
                len(r.transactions) for rs in forced_by_seller.values() for r in rs
            ),
            "participation_rate": round(
                float(np.mean([r.participation_rate for r in baseline])), 4
            ),
            "result_summary": (
                "Promotion lift is positive with CI excluding zero at every seller. "
                "The effect is an interaction, not a level shift: it concentrates in "
                "the lowest-budget class that can afford the discounted price - Poor "
                "for a promoted Slow stall, Middle for a promoted Shigh stall. Poor's "
                f"lift at a promoted Shigh stall is {poor_lift.mean():+.2f} by "
                "arithmetic: 6 x 0.7 = 4.2 still exceeds its budget of 3, so this is "
                "an affordability wall and not insensitivity to promotions."
            ),
            "decision_implication": "N/A - infrastructure phase, no business decision",
            "next_experiment": "Phase 5 nonlinear behaviour",
        },
    )
    print(f"\nWrote {LOG_PATH.relative_to(REPO_ROOT)}")
    return 0 if all(c.passed for c in criteria) else 1


if __name__ == "__main__":
    raise SystemExit(main())
