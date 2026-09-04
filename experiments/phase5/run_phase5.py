"""Run Phase 5 — Nonlinear Behavioural Effects.

Three-way comparison on identical seeds: the linear model, the linear model
plus a budget cliff, and the cliff with the linear budget term removed. The
spec is self-contradictory about which of the last two it means, so both are
run rather than one being guessed at.

The decision rule is an equivalence test against the project's 5pp materiality
margin, and this is the template Phases 7b-7d reuse verbatim.

    python experiments/phase5/run_phase5.py
"""

from __future__ import annotations

import dataclasses
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
    PHASE5_ADDITIVE,
    PHASE5_CLIFF_ONLY,
    PHASE5_LINEAR,
    MarketConfig,
)
from market_sim.engine import run_seeds  # noqa: E402

RESULTS_ROOT = REPO_ROOT / "results" / "phase5"
LOG_PATH = REPO_ROOT / "experiment_log.csv"

#: Seeds used to resolve an arm the 30-seed comparison leaves inconclusive.
#: Not a change to the phase's headline sample - the 30-seed result is reported
#: alongside - but an inconclusive test decides nothing, and this phase exists
#: to decide.
EXTENDED_SEEDS = tuple(range(1000))

RESEARCH_QUESTION = (
    "Does adding one nonlinear mechanism (a budget-cliff threshold effect) "
    "materially change conclusions vs. the linear model used in Phases 2-4?"
)


def print_table(name: str, table: dict) -> None:
    print(f"\n  {name}")
    print(
        f"    {'metric':26s} {'shift (pp)':>11s} {'95% CI (pp)':>22s}  verdict"
    )
    for metric, (mean, lo, hi, verdict) in table.items():
        print(
            f"    {metric:26s} {mean * 100:+11.3f}   "
            f"[{lo * 100:+7.3f}, {hi * 100:+7.3f}]  {verdict}"
        )


def with_seeds(cfg: MarketConfig, seeds: tuple[int, ...]) -> MarketConfig:
    return dataclasses.replace(cfg, name=f"{cfg.name}_extended", seeds=seeds)


def plot_arms(tables: dict[str, dict], out_path: Path) -> None:
    metrics = list(next(iter(tables.values())))
    fig, ax = plt.subplots(figsize=(11, 5))
    offsets = np.linspace(-0.2, 0.2, len(tables))
    for (arm, table), off in zip(tables.items(), offsets):
        xs = np.arange(len(metrics)) + off
        means = [table[m][0] * 100 for m in metrics]
        errs = [
            [table[m][0] * 100 - table[m][1] * 100 for m in metrics],
            [table[m][2] * 100 - table[m][0] * 100 for m in metrics],
        ]
        ax.errorbar(xs, means, yerr=errs, fmt="o", capsize=4, label=arm)
    for y in (-acceptance.MATERIALITY_PP, acceptance.MATERIALITY_PP):
        ax.axhline(y, color="firebrick", linestyle="--", linewidth=1)
    ax.axhline(0, color="grey", linewidth=0.8)
    ax.set_xticks(np.arange(len(metrics)))
    ax.set_xticklabels([m.replace("_share", "") for m in metrics], rotation=20, ha="right")
    ax.set_ylabel("shift vs linear model (percentage points)")
    ax.set_title(
        "Phase 5 — class-share shift vs the linear model "
        f"(dashed = ±{acceptance.MATERIALITY_PP:g} pp materiality margin)"
    )
    ax.legend(fontsize=9)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def main() -> int:
    commit = experiment_log.git_commit(REPO_ROOT)

    linear = run_seeds(PHASE5_LINEAR)
    outputs.write_all(PHASE5_LINEAR, linear, RESULTS_ROOT / "linear")

    arms = {}
    tables = {}
    for cfg in (PHASE5_ADDITIVE, PHASE5_CLIFF_ONLY):
        results = run_seeds(cfg)
        outputs.write_all(cfg, results, RESULTS_ROOT / cfg.name)
        arms[cfg.name] = results
        tables[cfg.name] = acceptance.share_shift_table(cfg, results, linear)

    print(f"\n=== Phase 5 — three-way comparison, {len(PHASE5_LINEAR.seeds)} seeds, paired ===")
    print(f"  cliff: utility -= {PHASE5_ADDITIVE.budget_cliff_penalty:g} when "
          f"(budget_remaining - price) < {PHASE5_ADDITIVE.budget_cliff_gap:g}")
    for arm, table in tables.items():
        print_table(arm, table)

    # Resolve any arm the 30-seed comparison could not decide, then grade each
    # arm on the strongest evidence available for it rather than on the
    # 30-seed table it was already shown to be unable to settle.
    extended_tables = {}
    all_criteria = []
    for cfg in (PHASE5_ADDITIVE, PHASE5_CLIFF_ONLY):
        results, base = arms[cfg.name], linear
        if any(v[3] == "inconclusive" for v in tables[cfg.name].values()):
            print(
                f"\n  {cfg.name} is inconclusive at {len(PHASE5_LINEAR.seeds)} seeds. "
                f"Re-running both arms at {len(EXTENDED_SEEDS)} seeds to decide."
            )
            base = run_seeds(with_seeds(PHASE5_LINEAR, EXTENDED_SEEDS))
            results = run_seeds(with_seeds(cfg, EXTENDED_SEEDS))
            extended_tables[cfg.name] = acceptance.share_shift_table(cfg, results, base)
            print_table(
                f"{cfg.name} @ {len(EXTENDED_SEEDS)} seeds", extended_tables[cfg.name]
            )
        all_criteria += acceptance.evaluate_phase5(cfg, results, base, cfg.name)

    print("\n  acceptance criteria:")
    for c in all_criteria:
        print(f"    [{'PASS' if c.passed else 'FAIL'}] {c.name}")
        print(f"           measured: {c.measured}  (required: {c.threshold})")
        if c.note:
            print(f"           note: {c.note}")

    plot_arms(tables, RESULTS_ROOT / "share_shift.png")

    additive = tables[PHASE5_ADDITIVE.name]
    verdicts = {v[3] for v in additive.values()}
    decision = (
        "roll back to the linear model for Phase 6 onward"
        if verdicts == {"equivalent"}
        else "keep the nonlinearity"
        if "material" in verdicts
        else "undecided"
    )
    worst_pp = max(abs(v[0]) for v in additive.values()) * 100

    for cfg, table, note in (
        (PHASE5_ADDITIVE, additive, "additive reading: linear term kept, cliff added"),
        (
            PHASE5_CLIFF_ONLY,
            tables[PHASE5_CLIFF_ONLY.name],
            "replacement reading: linear budget term removed, cliff only",
        ),
    ):
        ext = extended_tables.get(cfg.name)
        final = ext or table
        experiment_log.append_row(
            LOG_PATH,
            {
                "experiment_id": cfg.name,
                "git_commit": commit,
                "config_file": f"src/market_sim/config.py::{cfg.name.upper()}",
                "phase": 5,
                "seed": f"0-{len(EXTENDED_SEEDS) - 1}" if ext else "0-29",
                "n_buyers": cfg.n_buyers,
                "n_sellers": cfg.n_sellers,
                "model_used": "rule_based",
                "decision_type": "N/A",
                "human_benchmark_id": "N/A",
                "human_benchmark_status": "not_applicable",
                "synthetic_cost_usd": "N/A",
                "synthetic_latency_seconds": "N/A",
                "research_question": RESEARCH_QUESTION,
                "changed_mechanism": note,
                "transaction_count": sum(len(r.transactions) for r in arms[cfg.name]),
                "participation_rate": round(
                    float(np.mean([r.participation_rate for r in arms[cfg.name]])), 4
                ),
                "result_summary": (
                    f"{note}. Largest class-share shift vs linear "
                    f"{max(abs(v[0]) for v in final.values()) * 100:.3f} pp; verdicts "
                    f"{sorted({v[3] for v in final.values()})}"
                    + (
                        f" (resolved at {len(EXTENDED_SEEDS)} seeds after being "
                        f"inconclusive at 30)"
                        if ext
                        else ""
                    )
                    + "."
                ),
                "decision_implication": "N/A - infrastructure phase, no business decision",
                "next_experiment": "Phase 6 repeated interaction",
            },
        )

    print(f"\n=== decision ===")
    print(f"  Largest class-share shift under the additive reading: {worst_pp:.3f} pp")
    print(f"  Materiality margin: {acceptance.MATERIALITY_PP:g} pp")
    print(f"  -> {decision}")
    print(f"\nWrote {LOG_PATH.relative_to(REPO_ROOT)}")
    return 0 if all(c.passed for c in all_criteria) else 1


if __name__ == "__main__":
    raise SystemExit(main())
