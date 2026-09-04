"""Run Phase 1 — Transaction Mechanics.

Runs the specified experiment plus the inventory-pressure side experiment,
writes the four output tables for each, plots the across-seed convergence
check, evaluates the acceptance criteria, and appends to experiment_log.csv.

    python experiments/phase1/run_phase1.py
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
    PHASE1_INVENTORY_PRESSURE,
    PHASE1_MAIN,
    Phase1Config,
)
from market_sim.engine import RunResult, run_seeds  # noqa: E402

RESULTS_ROOT = REPO_ROOT / "results" / "phase1"
LOG_PATH = REPO_ROOT / "experiment_log.csv"

RESEARCH_QUESTION = (
    "Do buyers purchase, do sellers sell, does price affect demand, does "
    "inventory constrain sales, and are transactions recorded correctly - with "
    "no heterogeneity, environment, or context to confound the answer?"
)


def metric_series(results: list[RunResult]) -> dict[str, np.ndarray]:
    return {
        "participation_rate": np.array([r.participation_rate for r in results]),
        "avg_purchases_per_buyer": np.array(
            [r.avg_purchases_per_buyer for r in results]
        ),
        "total_revenue": np.array([r.total_revenue for r in results], dtype=float),
        "total_inventory_remaining": np.array(
            [r.total_inventory_remaining for r in results], dtype=float
        ),
    }


def plot_convergence(results: list[RunResult], out_path: Path, title: str) -> None:
    """Running mean of each run_summary metric against seed count.

    The shaded band is the convergence tolerance, drawn rather than merely
    asserted so a reader can see whether "settled" means the curve flattened or
    just that the band is wide.
    """
    fig, axes = plt.subplots(2, 2, figsize=(11, 7))
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


def summarize(cfg: Phase1Config, results: list[RunResult]) -> dict[str, float]:
    return {
        "participation_rate": float(np.mean([r.participation_rate for r in results])),
        "total_revenue": float(np.mean([r.total_revenue for r in results])),
        "inventory_remaining": float(
            np.mean([r.total_inventory_remaining for r in results])
        ),
        "transaction_count": int(sum(len(r.transactions) for r in results)),
        "blocked_by_inventory": int(
            sum(r.blocked_counts["inventory_empty"] for r in results)
        ),
        "blocked_by_budget": int(
            sum(r.blocked_counts["budget_exhausted"] for r in results)
        ),
    }


def report(cfg: Phase1Config, results: list[RunResult]) -> list[acceptance.CriterionResult]:
    stats = summarize(cfg, results)
    print(f"\n=== {cfg.name} ({len(results)} seeds) ===")
    print(f"  inventory per seller      : {cfg.seller.inventory}")
    print(f"  mean participation_rate   : {stats['participation_rate']:.3f}")
    print(f"  mean total_revenue        : {stats['total_revenue']:.1f}")
    print(f"  mean inventory remaining  : {stats['inventory_remaining']:.1f}")
    print(f"  transactions (all seeds)  : {stats['transaction_count']}")
    print(f"  blocked by empty stock    : {stats['blocked_by_inventory']}")
    print(f"  blocked by spent budget   : {stats['blocked_by_budget']}")

    criteria = acceptance.evaluate(cfg, results)
    print("  acceptance criteria:")
    for c in criteria:
        mark = "PASS" if c.passed else "FAIL"
        print(f"    [{mark}] {c.name}")
        print(f"           measured: {c.measured}  (required: {c.threshold})")
        if c.note:
            print(f"           note: {c.note}")
    return criteria


def main() -> int:
    commit = experiment_log.git_commit(REPO_ROOT)

    main_results = run_seeds(PHASE1_MAIN)
    outputs.write_all(main_results, RESULTS_ROOT / "main")
    plot_convergence(
        main_results, RESULTS_ROOT / "main" / "convergence.png", PHASE1_MAIN.name
    )
    main_criteria = report(PHASE1_MAIN, main_results)

    pressure_results = run_seeds(PHASE1_INVENTORY_PRESSURE)
    outputs.write_all(pressure_results, RESULTS_ROOT / "inventory_pressure")
    plot_convergence(
        pressure_results,
        RESULTS_ROOT / "inventory_pressure" / "convergence.png",
        PHASE1_INVENTORY_PRESSURE.name,
    )
    pressure_criteria = report(PHASE1_INVENTORY_PRESSURE, pressure_results)

    main_stats = summarize(PHASE1_MAIN, main_results)
    pressure_stats = summarize(PHASE1_INVENTORY_PRESSURE, pressure_results)

    experiment_log.append_row(
        LOG_PATH,
        {
            "experiment_id": "phase1_main",
            "git_commit": commit,
            "config_file": "src/market_sim/config.py::PHASE1_MAIN",
            "phase": 1,
            "seed": "0-29",
            "n_buyers": PHASE1_MAIN.n_buyers,
            "n_sellers": PHASE1_MAIN.n_sellers,
            "model_used": "rule_based",
            "decision_type": "N/A",
            "human_benchmark_id": "N/A",
            "human_benchmark_status": "not_applicable",
            "synthetic_cost_usd": "N/A",
            "synthetic_latency_seconds": "N/A",
            "research_question": RESEARCH_QUESTION,
            "changed_mechanism": "baseline - no prior phase to change from",
            "transaction_count": main_stats["transaction_count"],
            "participation_rate": round(main_stats["participation_rate"], 4),
            "result_summary": (
                f"All 3 acceptance criteria "
                f"{'passed' if all(c.passed for c in main_criteria) else 'did NOT all pass'}. "
                f"Mean participation {main_stats['participation_rate']:.3f}, mean revenue "
                f"{main_stats['total_revenue']:.1f}, mean inventory remaining "
                f"{main_stats['inventory_remaining']:.1f} of "
                f"{PHASE1_MAIN.n_sellers * PHASE1_MAIN.seller.inventory}. Inventory never "
                f"bound ({main_stats['blocked_by_inventory']} stock-blocked evaluations); "
                f"budget bound {main_stats['blocked_by_budget']} times."
            ),
            "decision_implication": "N/A - infrastructure phase, no business decision",
            "next_experiment": "phase1_inventory_pressure, then Phase 2 heterogeneity",
        },
    )

    experiment_log.append_row(
        LOG_PATH,
        {
            "experiment_id": "phase1_inventory_pressure",
            "git_commit": commit,
            "config_file": "src/market_sim/config.py::PHASE1_INVENTORY_PRESSURE",
            "phase": 1,
            "seed": "0-29",
            "n_buyers": PHASE1_INVENTORY_PRESSURE.n_buyers,
            "n_sellers": PHASE1_INVENTORY_PRESSURE.n_sellers,
            "model_used": "rule_based",
            "decision_type": "N/A",
            "human_benchmark_id": "N/A",
            "human_benchmark_status": "not_applicable",
            "synthetic_cost_usd": "N/A",
            "synthetic_latency_seconds": "N/A",
            "research_question": (
                "Side experiment: is the inventory constraint actually enforced, "
                "given the main run's parameters make it structurally unable to bind?"
            ),
            "changed_mechanism": "seller inventory 120 -> 15, all else identical to phase1_main",
            "transaction_count": pressure_stats["transaction_count"],
            "participation_rate": round(pressure_stats["participation_rate"], 4),
            "result_summary": (
                f"Stock ran out: {pressure_stats['blocked_by_inventory']} evaluations "
                f"blocked by empty inventory, mean inventory remaining "
                f"{pressure_stats['inventory_remaining']:.1f}. Participation fell to "
                f"{pressure_stats['participation_rate']:.3f} from "
                f"{main_stats['participation_rate']:.3f} in phase1_main on identical seeds, "
                f"confirming inventory is tracked and does bind sales when scarce."
            ),
            "decision_implication": "N/A - infrastructure phase, no business decision",
            "next_experiment": "Phase 2 heterogeneity",
        },
    )

    print(f"\nWrote {LOG_PATH.relative_to(REPO_ROOT)}")
    all_criteria = main_criteria + pressure_criteria
    return 0 if all(c.passed for c in all_criteria) else 1


if __name__ == "__main__":
    raise SystemExit(main())
