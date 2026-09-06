"""Run Phase 8 — endogenous market structure.

Entry and exit are switched on and nothing else changes from Phase 7. Two exit
rules run as a contrast, across a four-point sweep of the fixed weekly cost,
because that parameter was set three phases ago for a different reason and sits
exactly on the weakest seller's break-even. See docs/phase_specifications.md,
"Phase 8 design gate".

    python experiments/phase8/run_phase8.py
"""

from __future__ import annotations

import dataclasses
import sys
import warnings
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
warnings.filterwarnings("ignore", message="Degrees of freedom <= 0")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from market_sim import acceptance, experiment_log  # noqa: E402
from market_sim.config import (  # noqa: E402
    PHASE8_CELLS,
    PHASE8_EXIT_RULES,
    PHASE8_FIXED_COSTS,
)
from market_sim.engine import run_season_seeds  # noqa: E402

RESULTS_ROOT = REPO_ROOT / "results" / "phase8"
LOG_PATH = REPO_ROOT / "experiment_log.csv"

#: Applied once, to every cell, if any cell's settling interval straddles the
#: materiality boundary - all eight so the comparison across them stays
#: uniform. See docs/phase_specifications.md, Phase 8.
RESOLUTION_SEEDS = tuple(range(300))

RESEARCH_QUESTION = (
    "Can repeated micro-level interaction produce macro-level market "
    "structure - concentration, niche formation, persistent inequality - "
    "without that structure being programmed in?"
)


def collect(cfg, rows, trajectories, criteria_by_cell, premium_shares) -> None:
    """Run one cell and record it. Shared by the first pass and the escalation."""
    seasons = run_season_seeds(cfg)
    criteria = acceptance.evaluate_phase8(cfg, seasons)
    counts = acceptance.seller_counts_by_season(cfg, seasons)
    mix = acceptance.class_mix(seasons)
    active = np.array([s.active.sum(axis=1) for s in seasons])
    entries = float(np.mean([sum(e["event"] == "entry" for e in s.events)
                             for s in seasons]))
    exits = float(np.mean([sum(e["event"] == "exit" for e in s.events)
                           for s in seasons]))
    volatility = float(np.abs(np.diff(counts, axis=1) / counts[:, :-1]).mean())
    # A flat count is not a static market: measure whether firms are still
    # turning over once the count has stopped moving.
    turnover = acceptance.stationary_turnover(cfg, seasons, cfg.weeks - 22)
    # Share of active sellers in the premium tier, week by week. The endpoint
    # alone is four identical full bars; what the phase found is the path from
    # 40% to nothing, and when it happens.
    premium = np.zeros((len(seasons), cfg.weeks))
    for i, s in enumerate(seasons):
        for w in range(cfg.weeks):
            slots = np.flatnonzero(s.active[w])
            tiers = s.weeks[w].seller_classes
            premium[i, w] = np.mean([tiers[j] == "Shigh" for j in slots])
    label = f"{cfg.exit_rule}, F={cfg.fixed_weekly_cost:g}"
    trajectories[label] = active
    premium_shares[label] = premium
    criteria_by_cell[label] = criteria

    print(f"  {label:22s} {active[:, -1].mean():5.1f} {active.max():5d} "
          f"{entries:8.1f} {exits:7.1f} {volatility:10.1%} "
          f"{turnover['firm_survival']:8.0%}   "
          + "  ".join(f"{k} {v:.0%}" for k, v in mix.items()))
    rows.append({
        "cell": cfg.name, "exit_rule": cfg.exit_rule,
        "fixed_cost": cfg.fixed_weekly_cost, "seeds": len(cfg.seeds),
        "final_sellers": float(active[:, -1].mean()),
        "peak_sellers": int(active.max()),
        "entries": entries, "exits": exits, "volatility": volatility,
        **{f"final_season_{k}": v for k, v in turnover.items()},
        **{f"share_{k}": v for k, v in mix.items()},
        "passed": all(c.passed for c in criteria if c.graded),
    })


def report(criteria_by_cell) -> list:
    """Print the graded marks and return the failures."""
    print("\n  Graded criteria, per cell:")
    for label, criteria in criteria_by_cell.items():
        marks = "".join("P" if c.passed else "F" for c in criteria if c.graded)
        print(f"    {label:22s} {marks}")
    failing = [
        (label, c) for label, cs in criteria_by_cell.items()
        for c in cs if c.graded and not c.passed
    ]
    for label, c in failing:
        print(f"\n    [FAIL] {label} — {c.name}\n           {c.measured}")
    if not failing:
        print("    all graded criteria pass in every cell.")
    return failing


def main() -> int:
    commit = experiment_log.git_commit(REPO_ROOT)
    RESULTS_ROOT.mkdir(parents=True, exist_ok=True)

    print("\n=== Phase 8 — endogenous market structure ===")
    print(f"  {RESEARCH_QUESTION}\n")
    print(f"  5 starting sellers, {PHASE8_CELLS[0].weeks} weeks, "
          f"{len(PHASE8_CELLS[0].seeds)} seeds, {PHASE8_CELLS[0].max_sellers} slots.")
    print("  Entry: copy a stall that is making money, after two consecutive "
          "weeks of\n  mean profit above zero. The rule never reads a class label.\n")

    rows, trajectories, criteria_by_cell, premium_shares = [], {}, {}, {}
    print(f"  {'cell':22s} {'end':>5s} {'peak':>5s} {'entries':>8s} {'exits':>7s} "
          f"{'volatility':>11s} {'survive':>8s}   class mix at the end")
    cells = PHASE8_CELLS
    seed_block = cells[0].seeds
    for cfg in cells:
        collect(cfg, rows, trajectories, criteria_by_cell, premium_shares)

    failing = report(criteria_by_cell)

    reference = criteria_by_cell["capital, F=10"]
    print(f"\n  {[c.measured for c in reference if not c.graded][0]}")

    if failing and len(cells[0].seeds) < len(RESOLUTION_SEEDS):
        print(f"\n  {len(failing)} cell(s) inconclusive at {len(cells[0].seeds)} "
              f"seeds. Re-measuring every cell at {len(RESOLUTION_SEEDS)}, once, "
              f"so the eight stay comparable.\n")
        seed_block = RESOLUTION_SEEDS
        rows, trajectories, criteria_by_cell, premium_shares = [], {}, {}, {}
        print(f"  {'cell':22s} {'end':>5s} {'peak':>5s} {'entries':>8s} "
              f"{'exits':>7s} {'volatility':>11s} {'survive':>8s}   class mix at the end")
        for cfg in cells:
            cfg = dataclasses.replace(cfg, seeds=RESOLUTION_SEEDS)
            collect(cfg, rows, trajectories, criteria_by_cell, premium_shares)
        failing = report(criteria_by_cell)
        reference = criteria_by_cell["capital, F=10"]
        print(f"\n  {[c.measured for c in reference if not c.graded][0]}")

    # ---- artefacts ---------------------------------------------------------
    frame = pd.DataFrame(rows)
    frame.to_csv(RESULTS_ROOT / "cells.csv", index=False)
    pd.DataFrame(
        [{"cell": label, "week": w, "seed": i, "active": int(v)}
         for label, arr in trajectories.items()
         for i, row in enumerate(arr) for w, v in enumerate(row)]
    ).to_csv(RESULTS_ROOT / "trajectories.csv", index=False)
    plot(trajectories, frame, premium_shares)

    settled = [c for cs in criteria_by_cell.values() for c in cs
               if c.name.startswith("the seller count has settled")]
    experiment_log.append_row(LOG_PATH, {
        "experiment_id": "phase8_entry_exit", "git_commit": commit,
        "config_file": "src/market_sim/config.py::PHASE8_CELLS",
        "phase": 8, "seed": f"{seed_block[0]}-{seed_block[-1]}",
        "n_buyers": PHASE8_CELLS[0].n_buyers, "n_sellers": PHASE8_CELLS[0].n_sellers,
        "model_used": "rule_based", "decision_type": "N/A",
        "human_benchmark_id": "N/A",
        "human_benchmark_status": "compared_to_published_reference",
        "synthetic_cost_usd": "N/A", "synthetic_latency_seconds": "N/A",
        "research_question": RESEARCH_QUESTION,
        "changed_mechanism": (
            "seller entry and exit: free entry by imitation on two consecutive "
            "weeks of positive mean profit, exit by capital exhaustion or by "
            "three consecutive losing weeks, across fixed costs "
            f"{list(PHASE8_FIXED_COSTS)}"
        ),
        "transaction_count": "N/A",
        "participation_rate": "N/A",
        "result_summary": (
            "Final seller count by fixed cost: "
            + "; ".join(
                f"{r['exit_rule']} F={r['fixed_cost']:g} -> {r['final_sellers']:.1f}"
                for r in rows
            )
            + f". Stationary rather than static: in the final season entry and "
            f"exit run at {frame['final_season_entries_per_week'].min():.2f}-"
            f"{frame['final_season_entries_per_week'].max():.2f} firms a week and "
            f"{frame['final_season_firm_survival'].min():.0%}-"
            f"{frame['final_season_firm_survival'].max():.0%} of firms survive it. "
            f"Season-over-season change {frame['volatility'].mean():.1%} against the "
            f"RI DEM reference series' {acceptance.real_market_volatility():.1%} - a "
            f"comparable order of magnitude only, the two are not like-for-like. "
            f"{sum(c.passed for c in settled)}/{len(settled)} cells decided."
        ),
        "decision_implication": "N/A - infrastructure phase, no business decision",
        "next_experiment": "Phase 9a — learned buyer policy",
    })
    print(f"\n  Wrote {RESULTS_ROOT}\n")
    return 0 if not failing else 1


def plot(trajectories, frame, premium_shares) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(15.5, 4.4))
    colours = dict(zip(PHASE8_FIXED_COSTS, ("tab:blue", "tab:green", "tab:orange",
                                            "tab:red")))

    for ax, rule in zip(axes[:2], PHASE8_EXIT_RULES):
        for cost in PHASE8_FIXED_COSTS:
            arr = trajectories[f"{rule}, F={cost:g}"]
            weeks = np.arange(arr.shape[1])
            ax.plot(weeks, arr.mean(axis=0), lw=1.6, color=colours[cost],
                    label=f"fixed cost {cost:g}")
            ax.fill_between(weeks, np.percentile(arr, 25, axis=0),
                            np.percentile(arr, 75, axis=0), color=colours[cost],
                            alpha=0.12, lw=0)
        for boundary in range(22, arr.shape[1], 22):
            ax.axvline(boundary, c="0.85", lw=0.8, zorder=0)
        ax.axhline(5, ls=":", c="0.4", lw=1)
        ax.set_xlabel("week")
        ax.set_ylabel("active sellers")
        ax.set_title(f"Exit on {rule}", fontsize=10)
        ax.legend(fontsize=7.5)
    top = max(a.max() for a in trajectories.values())
    for ax in axes[:2]:
        ax.set_ylim(0, top * 1.05)

    ax = axes[2]
    for rule, style in zip(PHASE8_EXIT_RULES, (dict(ls="-"), dict(ls="--"))):
        for cost in PHASE8_FIXED_COSTS:
            arr = premium_shares[f"{rule}, F={cost:g}"]
            ax.plot(np.arange(arr.shape[1]), arr.mean(axis=0), lw=1.5,
                    color=colours[cost], alpha=0.95 if rule == "capital" else 0.55,
                    label=f"F={cost:g} ({rule})", **style)
    ax.axhline(2 / 5, ls=":", c="0.4", lw=1)
    ax.text(2, 2 / 5 + 0.012, "starting share: 2 of 5 stalls", fontsize=7.5,
            color="0.35")
    ax.set_ylim(0, 0.47)
    ax.set_xlabel("week")
    ax.set_ylabel("share of active sellers in the premium tier")
    ax.set_title("The premium tier is competed out", fontsize=10)
    ax.legend(fontsize=6.5, ncol=2)

    fig.suptitle("Phase 8 — entry and exit, and what the market settles into",
                 fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(RESULTS_ROOT / "structure.png", dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    raise SystemExit(main())
