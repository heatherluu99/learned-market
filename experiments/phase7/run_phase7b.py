"""Run Phase 7b — Multi-Armed Bandit (context-blind).

Two bandit arms against the 7a heuristic on identical seeds. Both algorithms
are run because the spec left the choice open; they turn out to agree once
both are initialized by pulling every arm once, and the agreement is the
point. See docs/phase_specifications.md, Phase 7b.

    python experiments/phase7/run_phase7b.py
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

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from market_sim import acceptance, experiment_log, outputs  # noqa: E402
from market_sim.config import (  # noqa: E402
    PHASE7A_HILL,
    PHASE7B_EPS,
    PHASE7B_UCB,
)
from market_sim.engine import run_season_seeds  # noqa: E402

RESULTS_ROOT = REPO_ROOT / "results" / "phase7b"
LOG_PATH = REPO_ROOT / "experiment_log.csv"
#: Seeds used to resolve an arm the 30-seed comparison leaves inconclusive.
#: The escalation size is fixed by the Phase 5 protocol rather than chosen
#: after seeing which n first yields a verdict, which would be optional
#: stopping. See docs/phase_specifications.md, Phase 5's decision rule.
EXTENDED_SEEDS = tuple(range(1000))

RESEARCH_QUESTION = (
    "Does treating price choice as a bandit problem outperform the 7a heuristic "
    "without using any market context?"
)


def plot(arms, baseline, out_path: Path) -> None:
    cfg = PHASE7B_UCB
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    ax = axes[0]
    for data, label, colour in (
        (baseline, "7a hill climbing", "tab:grey"),
        (arms["phase7b_eps"], "7b ε-greedy", "tab:orange"),
        (arms["phase7b_ucb"], "7b UCB1", "tab:blue"),
    ):
        arr = np.array([s.profits.sum(axis=1) for s in data])
        mean = arr.mean(axis=0)
        sem = arr.std(axis=0, ddof=1) / np.sqrt(arr.shape[0])
        ax.plot(mean, color=colour, label=label)
        ax.fill_between(range(len(mean)), mean - sem, mean + sem, color=colour, alpha=0.13)
    ax.set_xlabel("week"); ax.set_ylabel("total profit per week")
    ax.set_title("Profit: bandit arms vs the heuristic (±1 SEM)")
    ax.legend(fontsize=9)

    ax = axes[1]
    slow = [i for i, n in enumerate(cfg.seller_class_of()) if n == "Slow"]
    ceiling = 2.0 * max(cfg.price_arms)
    for data, label, colour in (
        (baseline, "7a hill climbing", "tab:grey"),
        (arms["phase7b_eps"], "7b ε-greedy", "tab:orange"),
        (arms["phase7b_ucb"], "7b UCB1", "tab:blue"),
    ):
        px = np.array([s.posted_prices[:, slow].mean(axis=1) for s in data]).mean(axis=0)
        ax.plot(px, color=colour, label=label)
    ax.axhline(3.0, ls="--", c="firebrick", lw=1)
    ax.text(1, 3.03, "profit optimum 3.00 = Poor's budget", fontsize=8, color="firebrick")
    ax.axhline(ceiling, ls=":", c="tab:blue", lw=1.2)
    ax.text(1, ceiling + 0.03, f"bandit arm ceiling {ceiling:.2f}", fontsize=8, color="tab:blue")
    ax.set_xlabel("week"); ax.set_ylabel("mean Slow posted price")
    ax.set_title("The arm ceiling, not the learning rule, is the binding limit")
    ax.legend(fontsize=9)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def main() -> int:
    commit = experiment_log.git_commit(REPO_ROOT)
    baseline = run_season_seeds(PHASE7A_HILL)
    arms = {c.name: run_season_seeds(c) for c in (PHASE7B_EPS, PHASE7B_UCB)}

    for cfg in (PHASE7B_EPS, PHASE7B_UCB):
        out = RESULTS_ROOT / cfg.name
        out.mkdir(parents=True, exist_ok=True)
        data = arms[cfg.name]
        outputs.weekly_summary_frame(cfg, data).to_csv(out / "weekly_summary.csv", index=False)
        outputs.write_all(cfg, [w for s in data for w in s.weeks], out)

    criteria = acceptance.evaluate_phase7b(PHASE7B_UCB, arms, baseline)
    bp = np.mean([s.profits.sum(axis=1).mean() for s in baseline])
    slow = [i for i, n in enumerate(PHASE7B_UCB.seller_class_of()) if n == "Slow"]
    ceiling = 2.0 * max(PHASE7B_UCB.price_arms)

    print(f"\n=== phase7b — {PHASE7B_UCB.weeks} weeks, {len(PHASE7B_UCB.seeds)} seeds ===")
    print(f"  arms {list(PHASE7B_UCB.price_arms)} → Slow ceiling {ceiling:.2f}, "
          f"profit optimum 3.00")
    print(f"\n  {'arm':16s} {'profit/wk':>10s} {'vs 7a':>8s} {'final Slow px':>14s}")
    print(f"  {'7a hill climb':16s} {bp:10.1f} {'--':>8s} "
          f"{np.array([s.posted_prices[-1, slow] for s in baseline]).mean():14.2f}")
    for name, data in arms.items():
        pf = np.mean([s.profits.sum(axis=1).mean() for s in data])
        px = np.array([s.posted_prices[-1, slow] for s in data]).mean()
        print(f"  {name:16s} {pf:10.1f} {pf - bp:+8.1f} {px:14.2f}")

    if any(not c.passed for c in criteria):
        print(f"\n  Inconclusive at {len(PHASE7B_UCB.seeds)} seeds. Re-running all arms "
              f"at {len(EXTENDED_SEEDS)} seeds, per the Phase 5 protocol.")
        baseline = run_season_seeds(
            dataclasses.replace(PHASE7A_HILL, seeds=EXTENDED_SEEDS)
        )
        arms = {
            c.name: run_season_seeds(dataclasses.replace(c, seeds=EXTENDED_SEEDS))
            for c in (PHASE7B_EPS, PHASE7B_UCB)
        }
        criteria = acceptance.evaluate_phase7b(PHASE7B_UCB, arms, baseline)
        bp = np.mean([s.profits.sum(axis=1).mean() for s in baseline])

    print("\n  graduation criteria:")
    for c in criteria:
        print(f"    [{'PASS' if c.passed else 'FAIL'}] {c.name}")
        print(f"           measured: {c.measured}")
        if c.note:
            print(f"           note: {c.note}")

    plot(arms, baseline, RESULTS_ROOT / "bandit.png")

    materials = [c for c in criteria if "-> material" in c.measured or
                 (c.note or "").startswith("material on")]
    verdict = "graduate to 7c" if materials else "stop at 7a - no material gain"
    print(f"\n  => {verdict}")

    for cfg in (PHASE7B_EPS, PHASE7B_UCB):
        data = arms[cfg.name]
        pf = np.mean([s.profits.sum(axis=1).mean() for s in data])
        experiment_log.append_row(LOG_PATH, {
            "experiment_id": cfg.name, "git_commit": commit,
            "config_file": f"src/market_sim/config.py::{cfg.name.upper()}",
            "phase": 7, "seed": "0-29",
            "n_buyers": cfg.n_buyers, "n_sellers": cfg.n_sellers,
            "model_used": "rule_based", "decision_type": "N/A",
            "human_benchmark_id": "N/A", "human_benchmark_status": "not_applicable",
            "synthetic_cost_usd": "N/A", "synthetic_latency_seconds": "N/A",
            "research_question": RESEARCH_QUESTION,
            "changed_mechanism": f"context-blind bandit over arms {list(cfg.price_arms)}, "
                                 f"{'epsilon-greedy' if 'eps' in cfg.name else 'UCB1'}",
            "transaction_count": sum(len(w.transactions) for s in data for w in s.weeks),
            "participation_rate": round(float(np.mean([s.purchase_rate().mean() for s in data])), 4),
            "result_summary": (
                f"Profit {bp:.1f} (7a) -> {pf:.1f} per week, {pf - bp:+.1f}. Verdict: {verdict}. "
                f"The arm set tops out at {ceiling:.2f} for a Slow seller while the profit "
                f"optimum is 3.00, so the bandit's binding limit is its fixed local "
                f"hypothesis space rather than its learning rule."
            ),
            "decision_implication": "N/A - infrastructure phase, no business decision",
            "next_experiment": "Phase 7c contextual bandit with a learned representation",
        })
    print(f"\nWrote {LOG_PATH.relative_to(REPO_ROOT)}")
    return 0 if all(c.passed for c in criteria) else 1


if __name__ == "__main__":
    raise SystemExit(main())
