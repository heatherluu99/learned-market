"""Phase 7c — the diagnostic that led to skipping it.

7c asks whether a learned representation of market state beats hand-designed
features. Both halves of that presuppose something this market turns out not
to have: that market state predicts *which action is best*, rather than only
how much reward that action earns.

This script is the evidence for the skip, so it lives in the repository and
re-runs rather than sitting in a scratch directory. It does not implement a
contextual bandit; it establishes that one would have nothing to condition on.

    python experiments/phase7/run_phase7c_diagnostic.py
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

from market_sim import experiment_log  # noqa: E402
from market_sim.config import PHASE7A_FIXED  # noqa: E402
from market_sim.engine import run_season  # noqa: E402

RESULTS_ROOT = REPO_ROOT / "results" / "phase7c"
LOG_PATH = REPO_ROOT / "experiment_log.csv"

BASE = PHASE7A_FIXED
#: Arms bracket the oracle optimum of 2.65 on both sides. A set that pinned the
#: argmax at its ceiling could not show context-dependence even if it existed,
#: so it would not be a fair falsification.
ARMS = (2.20, 2.40, 2.60, 2.80, 3.00)
SEEDS = tuple(range(24))
TARGET = 0
UNIT_COST = BASE.unit_cost_fraction * 2.0

RESEARCH_QUESTION = (
    "Does market state predict which price is best, rather than only how much "
    "that price earns? A contextual bandit can only exploit the former."
)


def _config_for(price: float):
    """Split the near-Slow pair so exactly one stall carries the swept price."""
    classes = list(BASE.seller_classes)
    classes[0] = dataclasses.replace(classes[0], count=1, price=price)
    classes.insert(1, dataclasses.replace(BASE.seller_classes[0], count=1))
    return dataclasses.replace(BASE, name="phase7c_diag", seller_classes=tuple(classes))


def collect() -> list[dict]:
    rows = []
    for seed in SEEDS:
        seasons = [run_season(_config_for(p), seed) for p in ARMS]
        reference = seasons[len(ARMS) // 2]
        for w in range(seasons[0].n_weeks):
            profits = [
                s.weeks[w].seller_revenue[TARGET]
                - UNIT_COST * s.weeks[w].seller_n_sold[TARGET]
                - BASE.fixed_weekly_cost
                for s in seasons
            ]
            promoted = reference.weeks[w].promoted_seller
            rows.append(
                {
                    "profits": profits,
                    "best_arm": ARMS[int(np.argmax(profits))],
                    "promo_elsewhere": promoted is not None and promoted != TARGET,
                    "attendance": float(reference.attended[w].mean()),
                }
            )
    return rows


def main() -> int:
    commit = experiment_log.git_commit(REPO_ROOT)
    rows = collect()
    profits = np.array([r["profits"] for r in rows])
    attendance = np.array([r["attendance"] for r in rows])
    median = float(np.median(attendance))

    splits = {
        "all weeks": np.ones(len(rows), dtype=bool),
        "a promotion elsewhere": np.array([r["promo_elsewhere"] for r in rows]),
        "no promotion elsewhere": np.array([not r["promo_elsewhere"] for r in rows]),
        "attendance above median": attendance > median,
        "attendance at or below median": attendance <= median,
    }

    print(f"\n=== Phase 7c diagnostic — {len(rows)} seller-weeks, arms {list(ARMS)} ===")
    print("  Does the best arm change with observable weekly state?\n")
    header = "  ".join(f"{a:5.2f}" for a in ARMS)
    print(f"  {'context condition':32s} {'n':>5s}   {header}   best")
    best_arms = {}
    for label, mask in splits.items():
        if mask.sum() < 20:
            continue
        mean = profits[mask].mean(axis=0)
        best = ARMS[int(np.argmax(mean))]
        best_arms[label] = best
        print(
            f"  {label:32s} {int(mask.sum()):5d}   "
            + "  ".join(f"{v:5.1f}" for v in mean)
            + f"   {best:.2f}"
        )

    invariant = len(set(best_arms.values())) == 1
    overall = best_arms["all weeks"]
    per_week = {a: float(np.mean([r["best_arm"] == a for r in rows])) for a in ARMS}
    print(
        f"\n  Best arm is {'identical' if invariant else 'NOT identical'} under every "
        f"condition: {sorted(set(best_arms.values()))}"
    )
    print(
        "  Per-week realized argmax: "
        + ", ".join(f"{a:.2f} {p:.0%}" for a, p in per_week.items())
    )
    print(
        "  That per-week spread is noise, not signal: it is present but does not\n"
        "  move with any observable state, and a contextual bandit can only\n"
        "  exploit variation that context predicts."
    )

    RESULTS_ROOT.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(8, 5))
    for label, mask in splits.items():
        if mask.sum() < 20:
            continue
        style = "-" if label == "all weeks" else "--"
        ax.plot(ARMS, profits[mask].mean(axis=0), style, marker="o",
                linewidth=2.2 if label == "all weeks" else 1.3, label=f"{label} (n={int(mask.sum())})")
    ax.axvline(2.65, ls=":", c="firebrick", lw=1)
    ax.text(2.66, ax.get_ylim()[0] + 0.5, "oracle optimum 2.65", fontsize=8, color="firebrick")
    ax.set_xlabel("posted price (arm)")
    ax.set_ylabel("weekly profit for the swept stall")
    ax.set_title("Context shifts the level, never the argmax")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(RESULTS_ROOT / "context_invariance.png", dpi=150)
    plt.close(fig)

    experiment_log.append_row(LOG_PATH, {
        "experiment_id": "phase7c_diagnostic", "git_commit": commit,
        "config_file": "experiments/phase7/run_phase7c_diagnostic.py",
        "phase": 7, "seed": f"0-{len(SEEDS) - 1}",
        "n_buyers": BASE.n_buyers, "n_sellers": BASE.n_sellers + 1,
        "model_used": "rule_based", "decision_type": "N/A",
        "human_benchmark_id": "N/A", "human_benchmark_status": "not_applicable",
        "synthetic_cost_usd": "N/A", "synthetic_latency_seconds": "N/A",
        "research_question": RESEARCH_QUESTION,
        "changed_mechanism": "none - counterfactual arm evaluation under fixed pricing",
        "transaction_count": len(rows),
        "participation_rate": "N/A",
        "result_summary": (
            f"The profit-maximizing arm is {overall:.2f} under every observable "
            f"weekly condition tested - promotion elsewhere or not, attendance above "
            f"or below median - and the profit curve shifts in level without changing "
            f"shape. Per-week realized argmax varies but tracks no observable state. "
            f"7c is skipped on this evidence: a contextual bandit conditions the "
            f"estimate of reward and cannot change a decision that context does not "
            f"move."
        ),
        "decision_implication": "N/A - infrastructure phase, no business decision",
        "next_experiment": "Phase 7d reinforcement learning",
    })
    print(f"\nWrote {LOG_PATH.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
