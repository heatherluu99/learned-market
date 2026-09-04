"""Run Phase 2 — Linear Consumer Heterogeneity.

Runs the main heterogeneous market, the common-alpha attribution diagnostic,
and the Phase 1 comparison the spec requires; writes the output tables, plots
the across-seed convergence check, evaluates the acceptance criteria, and
appends to experiment_log.csv.

    python experiments/phase2/run_phase2.py
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
    PHASE1_MAIN,
    PHASE2_COMMON_ALPHA,
    PHASE2_MAIN,
    MarketConfig,
)
from market_sim.engine import RunResult, run_seeds  # noqa: E402

RESULTS_ROOT = REPO_ROOT / "results" / "phase2"
LOG_PATH = REPO_ROOT / "experiment_log.csv"

RESEARCH_QUESTION = (
    "Does person-level heterogeneity alone (holding environment and context "
    "fixed) produce different purchasing patterns, and specifically basic "
    "economic stratification - and how does the middle class split its "
    "patronage between tiers?"
)


def gap_series(results: list[RunResult]) -> np.ndarray:
    """Per-seed Rich_to_Shigh - Middle_to_Shigh, the graded quantity."""
    return np.array(
        [r.tier_share("Rich", "Shigh") - r.tier_share("Middle", "Shigh") for r in results]
    )


def metric_series(results: list[RunResult]) -> dict[str, np.ndarray]:
    return {
        "participation_rate": np.array([r.participation_rate for r in results]),
        "avg_purchases_per_buyer": np.array(
            [r.avg_purchases_per_buyer for r in results]
        ),
        "total_revenue": np.array([r.total_revenue for r in results], dtype=float),
        "Middle_to_Shigh_share": np.array(
            [r.tier_share("Middle", "Shigh") for r in results]
        ),
        "Rich_to_Shigh_share": np.array(
            [r.tier_share("Rich", "Shigh") for r in results]
        ),
        "Rich - Middle gap (graded)": gap_series(results),
    }


def plot_convergence(results: list[RunResult], out_path: Path, title: str) -> None:
    """Running mean of each key metric against seed count.

    The shaded band is the convergence tolerance (1 SEM), drawn rather than
    merely asserted so a reader can see whether "settled" means the curve
    flattened or just that the band is wide.
    """
    series = metric_series(results)
    fig, axes = plt.subplots(2, 3, figsize=(15, 7))
    for ax, (name, values) in zip(axes.flat, series.items()):
        seeds = np.arange(1, len(values) + 1)
        running = np.cumsum(values) / seeds
        band = acceptance.convergence_band(values)
        ax.axhspan(
            running[-1] - band,
            running[-1] + band,
            color="tab:blue",
            alpha=0.12,
            label=f"±{band:.3g} (1 SEM)",
        )
        ax.plot(seeds, running, marker="o", markersize=3, linewidth=1.5)
        ax.axhline(running[-1], linestyle="--", linewidth=1, color="grey")
        ax.axvline(15, linestyle=":", linewidth=1, color="firebrick")
        if "gap" in name:
            ax.axhline(0.0, linestyle="-", linewidth=1, color="firebrick", alpha=0.5)
        settled = acceptance.convergence_seed(values, band)
        ax.set_title(
            f"{name}\nsettles at seed {settled}" if settled else f"{name}\nnot settled",
            fontsize=10,
        )
        ax.set_xlabel("seeds included")
        ax.set_ylabel("running mean")
        ax.legend(fontsize=7, loc="best")
    fig.suptitle(f"{title} - across-seed convergence (dotted red = seed 15)")
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def class_table(cfg: MarketConfig, results: list[RunResult]) -> list[dict]:
    rows = []
    for bc in cfg.buyer_classes:
        row = {
            "class": bc.name,
            "n": bc.count,
            "budget": bc.budget_per_visit,
            "alpha": bc.price_sensitivity,
            "participation": float(
                np.nanmean([r.participation_rate_of(bc.name) for r in results])
            ),
        }
        for sc in cfg.seller_classes:
            row[f"to_{sc.name}"] = float(
                np.nanmean([r.tier_share(bc.name, sc.name) for r in results])
            )
            row[f"blocked_at_{sc.name}"] = int(
                sum(r.blocked_by_budget_pairs.get((bc.name, sc.name), 0) for r in results)
            )
        rows.append(row)
    return rows


def report(cfg: MarketConfig, results: list[RunResult], criteria) -> None:
    print(f"\n=== {cfg.name} ({len(results)} seeds) ===")
    print(
        f"  {'class':8s} {'n':>4s} {'budget':>7s} {'alpha':>6s} "
        f"{'particip':>9s} {'to Slow':>8s} {'to Shigh':>9s} {'blocked@Shigh':>14s}"
    )
    for row in class_table(cfg, results):
        print(
            f"  {row['class']:8s} {row['n']:4d} {row['budget']:7.1f} {row['alpha']:6.2f} "
            f"{row['participation']:9.3f} {row['to_Slow']:8.3f} {row['to_Shigh']:9.3f} "
            f"{row['blocked_at_Shigh']:14,d}"
        )
    print("\n  acceptance criteria:")
    for c in criteria:
        mark = "PASS" if c.passed else "FAIL"
        mark = mark if c.graded else "obs "
        print(f"    [{mark}] {c.name}")
        print(f"           measured: {c.measured}  (required: {c.threshold})")
        if c.note:
            print(f"           note: {c.note}")


def main() -> int:
    commit = experiment_log.git_commit(REPO_ROOT)

    main_results = run_seeds(PHASE2_MAIN)
    outputs.write_all(PHASE2_MAIN, main_results, RESULTS_ROOT / "main")
    plot_convergence(
        main_results, RESULTS_ROOT / "main" / "convergence.png", PHASE2_MAIN.name
    )
    criteria = acceptance.evaluate_phase2(PHASE2_MAIN, main_results)
    report(PHASE2_MAIN, main_results, criteria)

    # --- Attribution diagnostic: how much of the gap is price sensitivity? ---
    alpha_results = run_seeds(PHASE2_COMMON_ALPHA)
    outputs.write_all(
        PHASE2_COMMON_ALPHA, alpha_results, RESULTS_ROOT / "common_alpha"
    )
    gap_main, lo_main, hi_main = acceptance.mean_difference_ci(
        np.array([r.tier_share("Rich", "Shigh") for r in main_results]),
        np.array([r.tier_share("Middle", "Shigh") for r in main_results]),
    )
    gap_alpha, lo_alpha, hi_alpha = acceptance.mean_difference_ci(
        np.array([r.tier_share("Rich", "Shigh") for r in alpha_results]),
        np.array([r.tier_share("Middle", "Shigh") for r in alpha_results]),
    )
    alpha_contribution = gap_main - gap_alpha
    share_from_alpha = alpha_contribution / gap_main if gap_main else float("nan")

    print("\n=== attribution diagnostic (required, not graded) ===")
    print(f"  Rich-Middle gap, heterogeneous alpha (.85/.5/.2): {gap_main:+.3f} "
          f"[{lo_main:+.3f}, {hi_main:+.3f}]")
    print(f"  Rich-Middle gap, common alpha (0.5 for all)     : {gap_alpha:+.3f} "
          f"[{lo_alpha:+.3f}, {hi_alpha:+.3f}]")
    print(f"  attributable to price sensitivity               : {alpha_contribution:+.3f} "
          f"({share_from_alpha:.0%} of the gap)")
    print(f"  attributable to budget heterogeneity alone      : {gap_alpha:+.3f} "
          f"({1 - share_from_alpha:.0%} of the gap)")

    # --- Phase 1 comparison required by the spec ---
    p1_results = run_seeds(PHASE1_MAIN)
    p1_part = float(np.mean([r.participation_rate for r in p1_results]))
    p1_avg = float(np.mean([r.avg_purchases_per_buyer for r in p1_results]))
    p2_part = float(np.mean([r.participation_rate for r in main_results]))
    p2_avg = float(np.mean([r.avg_purchases_per_buyer for r in main_results]))
    print("\n=== homogeneous (Phase 1) vs heterogeneous (Phase 2) ===")
    print(f"  {'':28s} {'Phase 1':>10s} {'Phase 2':>10s}")
    print(f"  {'participation_rate':28s} {p1_part:10.3f} {p2_part:10.3f}")
    print(f"  {'avg_purchases_per_buyer':28s} {p1_avg:10.3f} {p2_avg:10.3f}")
    print("  NOTE: populations differ (80 buyers/4 sellers vs 100/5) and prices")
    print("  differ (3 vs 2 and 6), so this is a descriptive side-by-side, not a")
    print("  controlled comparison. Heterogeneity is not the only thing that changed.")

    graded = [c for c in criteria if c.graded]
    stats_tx = sum(len(r.transactions) for r in main_results)
    experiment_log.append_row(
        LOG_PATH,
        {
            "experiment_id": "phase2_main",
            "git_commit": commit,
            "config_file": "src/market_sim/config.py::PHASE2_MAIN",
            "phase": 2,
            "seed": "0-29",
            "n_buyers": PHASE2_MAIN.n_buyers,
            "n_sellers": PHASE2_MAIN.n_sellers,
            "model_used": "rule_based",
            "decision_type": "N/A",
            "human_benchmark_id": "N/A",
            "human_benchmark_status": "not_applicable",
            "synthetic_cost_usd": "N/A",
            "synthetic_latency_seconds": "N/A",
            "research_question": RESEARCH_QUESTION,
            "changed_mechanism": "buyer classes (Poor/Middle/Rich) and seller classes (Slow/Shigh) introduced",
            "transaction_count": stats_tx,
            "participation_rate": round(p2_part, 4),
            "result_summary": (
                f"{sum(c.passed for c in graded)}/{len(graded)} graded criteria passed. "
                f"Stratification gap Rich-Middle to Shigh {gap_main:+.3f} "
                f"95% CI [{lo_main:+.3f}, {hi_main:+.3f}]. Poor_to_Shigh_share is 0.000 "
                f"by affordability wall (budget 3 < price 6), not by price sensitivity. "
                f"Middle splits {float(np.nanmean([r.tier_share('Middle','Slow') for r in main_results])):.3f} "
                f"Slow / {float(np.nanmean([r.tier_share('Middle','Shigh') for r in main_results])):.3f} Shigh."
            ),
            "decision_implication": "N/A - infrastructure phase, no business decision",
            "next_experiment": "phase2_common_alpha attribution diagnostic, then Phase 3 environment",
        },
    )

    experiment_log.append_row(
        LOG_PATH,
        {
            "experiment_id": "phase2_common_alpha",
            "git_commit": commit,
            "config_file": "src/market_sim/config.py::PHASE2_COMMON_ALPHA",
            "phase": 2,
            "seed": "0-29",
            "n_buyers": PHASE2_COMMON_ALPHA.n_buyers,
            "n_sellers": PHASE2_COMMON_ALPHA.n_sellers,
            "model_used": "rule_based",
            "decision_type": "N/A",
            "human_benchmark_id": "N/A",
            "human_benchmark_status": "not_applicable",
            "synthetic_cost_usd": "N/A",
            "synthetic_latency_seconds": "N/A",
            "research_question": (
                "Attribution: how much of Phase 2's stratification comes from "
                "price-sensitivity heterogeneity rather than budget heterogeneity?"
            ),
            "changed_mechanism": "all classes share alpha=0.5; budgets unchanged at 3/7/10",
            "transaction_count": sum(len(r.transactions) for r in alpha_results),
            "participation_rate": round(
                float(np.mean([r.participation_rate for r in alpha_results])), 4
            ),
            "result_summary": (
                f"Rich-Middle gap falls from {gap_main:+.3f} to {gap_alpha:+.3f} when "
                f"alpha is equalized, so roughly {share_from_alpha:.0%} of the "
                f"stratification is attributable to price sensitivity and "
                f"{1 - share_from_alpha:.0%} to budget heterogeneity alone. "
                f"'Heterogeneity produces stratification' holds; the narrower "
                f"'price sensitivity produces stratification' mostly does not."
            ),
            "decision_implication": "N/A - infrastructure phase, no business decision",
            "next_experiment": "Phase 3 environment",
        },
    )

    print(f"\nWrote {LOG_PATH.relative_to(REPO_ROOT)}")
    return 0 if all(c.passed for c in graded) else 1


if __name__ == "__main__":
    raise SystemExit(main())
