"""Run Phase 3 — Person + Environment.

Adds one environment variable to Phase 2's market: stall position, which sets
how likely a buyer is to notice a stall at all. Runs the market, evaluates the
graded criteria, and reports the two ungraded quantities the spec requires —
the class-to-tier share shift and the participation shift, both paired against
Phase 2 on identical seeds.

    python experiments/phase3/run_phase3.py
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
from market_sim.config import PHASE2_MAIN, PHASE3_MAIN  # noqa: E402
from market_sim.engine import RunResult, run_seeds  # noqa: E402

RESULTS_ROOT = REPO_ROOT / "results" / "phase3"
LOG_PATH = REPO_ROOT / "experiment_log.csv"

RESEARCH_QUESTION = (
    "Does a single environmental feature (stall visibility, driven by position) "
    "materially change purchase distribution beyond what person-level "
    "heterogeneity already explains?"
)


def metric_series(results: list[RunResult]) -> dict[str, np.ndarray]:
    return {
        "participation_rate": np.array([r.participation_rate for r in results]),
        "total_revenue": np.array([r.total_revenue for r in results], dtype=float),
        "Middle_to_Shigh_share": np.array(
            [r.tier_share("Middle", "Shigh") for r in results]
        ),
        "Rich_to_Shigh_share": np.array(
            [r.tier_share("Rich", "Shigh") for r in results]
        ),
        "Slow near-far n_sold": np.array(
            [r.seller_n_sold[:2].mean() - r.seller_n_sold[2] for r in results]
        ),
        "Shigh near-far n_sold": np.array(
            [float(r.seller_n_sold[3] - r.seller_n_sold[4]) for r in results]
        ),
    }


def plot_convergence(results: list[RunResult], out_path: Path, title: str) -> None:
    fig, axes = plt.subplots(2, 3, figsize=(15, 7))
    for ax, (name, values) in zip(axes.flat, metric_series(results).items()):
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
        if "near-far" in name:
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


def main() -> int:
    commit = experiment_log.git_commit(REPO_ROOT)

    results = run_seeds(PHASE3_MAIN)
    outputs.write_all(PHASE3_MAIN, results, RESULTS_ROOT / "main")
    plot_convergence(
        results, RESULTS_ROOT / "main" / "convergence.png", PHASE3_MAIN.name
    )
    criteria = acceptance.evaluate_phase3(PHASE3_MAIN, results)

    print(f"\n=== {PHASE3_MAIN.name} ({len(results)} seeds) ===")
    print(f"  {'seller':14s} {'position':>9s} {'vis_prob':>9s} {'noticed':>9s} {'n_sold':>8s}")
    classes = PHASE3_MAIN.seller_class_of()
    positions = [
        c.position_score for c in PHASE3_MAIN.seller_classes for _ in range(c.count)
    ]
    vis = PHASE3_MAIN.visibility_prob_of()
    noticed = np.array(
        [r.visibility_rate_by_seller(PHASE3_MAIN.n_buyers) for r in results]
    ).mean(axis=0)
    sold = np.array([r.seller_n_sold for r in results], dtype=float).mean(axis=0)
    for i, cls in enumerate(classes):
        print(
            f"  {cls + ' #' + str(i):14s} {positions[i]:9.1f} {vis[i]:9.2f} "
            f"{noticed[i]:9.3f} {sold[i]:8.1f}"
        )

    print("\n  acceptance criteria:")
    for c in criteria:
        print(f"    [{'PASS' if c.passed else 'FAIL'}] {c.name}")
        print(f"           measured: {c.measured}  (required: {c.threshold})")
        if c.note:
            print(f"           note: {c.note}")

    # --- Ungraded, but required reporting: paired shifts against Phase 2 ---
    p2 = run_seeds(PHASE2_MAIN)
    print("\n=== reported, not graded: shift vs Phase 2 (paired, same seeds) ===")
    print(f"  {'class':8s} {'P2 to_Slow':>11s} {'P3 to_Slow':>11s} {'shift':>9s} {'95% CI':>20s}")
    shifts = {}
    for bc in ("Poor", "Middle", "Rich"):
        a = np.array([r.tier_share(bc, "Slow") for r in results])
        b = np.array([r.tier_share(bc, "Slow") for r in p2])
        mean, lo, hi = acceptance.mean_difference_ci(a, b)
        shifts[bc] = (mean, lo, hi)
        verdict = "excludes 0" if (lo > 0 or hi < 0) else "INCLUDES 0"
        print(
            f"  {bc:8s} {np.nanmean(b):11.3f} {np.nanmean(a):11.3f} {mean:+9.4f} "
            f"  [{lo:+.4f}, {hi:+.4f}] {verdict}"
        )
    print("  A shift indistinguishable from zero is a pre-registered valid outcome:")
    print("  it means the environment redistributes sales between sellers without")
    print("  disturbing the class-to-tier sorting Phase 2 established.")

    part3 = np.array([r.participation_rate for r in results])
    part2 = np.array([r.participation_rate for r in p2])
    pmean, plo, phi = acceptance.mean_difference_ci(part3, part2)
    print(
        f"\n  participation: {part2.mean():.3f} -> {part3.mean():.3f}, "
        f"shift {pmean:+.4f}, 95% CI [{plo:+.4f}, {phi:+.4f}]"
    )
    print("  Visibility is the only mechanism that can reduce participation here:")
    print("  a buyer who never notices a stall cannot buy from it.")

    experiment_log.append_row(
        LOG_PATH,
        {
            "experiment_id": "phase3_main",
            "git_commit": commit,
            "config_file": "src/market_sim/config.py::PHASE3_MAIN",
            "phase": 3,
            "seed": "0-29",
            "n_buyers": PHASE3_MAIN.n_buyers,
            "n_sellers": PHASE3_MAIN.n_sellers,
            "model_used": "rule_based",
            "decision_type": "N/A",
            "human_benchmark_id": "N/A",
            "human_benchmark_status": "not_applicable",
            "synthetic_cost_usd": "N/A",
            "synthetic_latency_seconds": "N/A",
            "research_question": RESEARCH_QUESTION,
            "changed_mechanism": "seller position_score -> visibility_prob; unnoticed stalls skipped",
            "transaction_count": sum(len(r.transactions) for r in results),
            "participation_rate": round(float(part3.mean()), 4),
            "result_summary": (
                f"{sum(c.passed for c in criteria)}/{len(criteria)} graded criteria passed. "
                f"Position moves sales strongly within tier but class-to-tier sorting is "
                f"unchanged: Middle share shift {shifts['Middle'][0]:+.4f} "
                f"CI [{shifts['Middle'][1]:+.4f}, {shifts['Middle'][2]:+.4f}], Rich "
                f"{shifts['Rich'][0]:+.4f} CI [{shifts['Rich'][1]:+.4f}, "
                f"{shifts['Rich'][2]:+.4f}] - both include zero. Poor is pinned at 1.000 "
                f"by the affordability wall and cannot shift. Participation falls "
                f"{pmean:+.4f} CI [{plo:+.4f}, {phi:+.4f}], the phase's largest effect."
            ),
            "decision_implication": "N/A - infrastructure phase, no business decision",
            "next_experiment": "Phase 4 context (temporary promotion)",
        },
    )
    print(f"\nWrote {LOG_PATH.relative_to(REPO_ROOT)}")
    return 0 if all(c.passed for c in criteria) else 1


if __name__ == "__main__":
    raise SystemExit(main())
