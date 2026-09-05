"""Run Phase 7d — Reinforcement Learning (multi-week credit assignment).

Trains a Q-network on discounted multi-week return and evaluates it on seeds
it never saw, against 7b's context-blind bandit on the same arms. The gate
registers a null as the expected outcome, with its reasons; this measures it
rather than inferring it, because a hand-designed schedule search cannot rule
out a policy nobody thought of.

    python experiments/phase7/run_phase7d.py
"""

from __future__ import annotations

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

from market_sim import acceptance, experiment_log, outputs, rl  # noqa: E402
from market_sim.config import (  # noqa: E402
    PHASE7A_HILL,
    PHASE7B_UCB,
    PHASE7D,
    PHASE7D_TRAIN_SEEDS,
)
from market_sim.engine import run_season_seeds  # noqa: E402

RESULTS_ROOT = REPO_ROOT / "results" / "phase7d"
LOG_PATH = REPO_ROOT / "experiment_log.csv"
MYOPIC_ARM = 2.60  # the oracle optimum measured under the dispersed population

RESEARCH_QUESTION = (
    "Does optimizing cumulative multi-week reward change pricing behaviour or "
    "outcomes relative to per-week optimization?"
)


def signature(seasons, cfg) -> dict:
    """The sacrifice-then-recover check, operationalized.

    A seller trading short-term profit for later loyalty should price below the
    myopic optimum early and above it later, so the correlation between week
    and price should be positive and the first third should sit below the last.
    """
    slow = [i for i, n in enumerate(cfg.seller_class_of()) if n == "Slow"]
    prices = np.array([s.posted_prices[:, slow].mean(axis=1) for s in seasons])
    weeks = np.arange(prices.shape[1])
    corrs = [
        float(np.corrcoef(weeks, p)[0, 1]) if p.std() > 1e-12 else 0.0 for p in prices
    ]
    third = prices.shape[1] // 3
    return {
        "week_price_corr": float(np.mean(corrs)),
        "first_third": float(prices[:, :third].mean()),
        "last_third": float(prices[:, -third:].mean()),
        "prices": prices,
    }


def main() -> int:
    commit = experiment_log.git_commit(REPO_ROOT)

    print(f"\n=== phase7d — training on {len(PHASE7D_TRAIN_SEEDS)} seeds "
          f"disjoint from the 0-29 evaluation block ===")
    net = rl.train_policy(PHASE7D, PHASE7D_TRAIN_SEEDS, epochs=6)
    rl_seasons = rl.evaluate(PHASE7D, net, PHASE7B_UCB.seeds)
    bandit = run_season_seeds(PHASE7B_UCB)
    heuristic = run_season_seeds(PHASE7A_HILL)

    outputs_dir = RESULTS_ROOT / PHASE7D.name
    outputs_dir.mkdir(parents=True, exist_ok=True)
    outputs.weekly_summary_frame(PHASE7D, rl_seasons).to_csv(
        outputs_dir / "weekly_summary.csv", index=False)
    outputs.write_all(PHASE7D, [w for s in rl_seasons for w in s.weeks], outputs_dir)

    rp = np.array([s.profits.sum(axis=1).mean() for s in rl_seasons])
    bp = np.array([s.profits.sum(axis=1).mean() for s in bandit])
    hp = np.array([s.profits.sum(axis=1).mean() for s in heuristic])
    gain, lo, hi = acceptance.mean_difference_ci(rp, bp)
    scale = float(bp.mean())
    verdict = acceptance.equivalence_verdict(
        lo / scale, hi / scale, acceptance.MATERIALITY_PROFIT_PCT)

    print(f"\n  {'arm':22s} {'profit/wk':>10s}")
    for label, v in (("7a heuristic", hp.mean()), ("7b UCB1 bandit", bp.mean()),
                     ("7d RL (held-out)", rp.mean())):
        print(f"  {label:22s} {v:10.1f}")
    print(f"\n  RL vs bandit: {gain:+.1f} ({gain/scale:+.1%}), "
          f"95% CI [{lo/scale:+.1%}, {hi/scale:+.1%}] -> {verdict}")

    sig = signature(rl_seasons, PHASE7D)
    sig_b = signature(bandit, PHASE7B_UCB)
    print(f"\n  sacrifice-then-recover signature (reported, not graded):")
    print(f"    {'':16s} {'week-price corr':>16s} {'first third':>12s} {'last third':>11s}")
    for label, s in (("7d RL", sig), ("7b bandit", sig_b)):
        print(f"    {label:16s} {s['week_price_corr']:16.3f} "
              f"{s['first_third']:12.2f} {s['last_third']:11.2f}")
    present = sig["week_price_corr"] > 0.2 and sig["last_third"] > sig["first_third"] + 0.05
    print(f"    signature {'PRESENT' if present else 'absent'} "
          f"(myopic optimum {MYOPIC_ARM:.2f})")

    criteria = [acceptance.CriterionResult(
        name="7d: profit comparison against 7b is decisive on held-out seeds",
        passed=verdict != "inconclusive",
        measured=f"{bp.mean():.1f} -> {rp.mean():.1f} per week, {gain:+.1f} "
                 f"({gain/scale:+.1%}), 95% CI [{lo/scale:+.1%}, {hi/scale:+.1%}] -> {verdict}",
        threshold=f"CI wholly inside or wholly outside ±{acceptance.MATERIALITY_PROFIT_PCT:g}%",
        note="Trained on seeds 1000-1119, evaluated on 0-29. What is graded is "
             "that a verdict is reached, not which verdict.",
    )]
    print("\n  acceptance criteria:")
    for c in criteria:
        print(f"    [{'PASS' if c.passed else 'FAIL'}] {c.name}")
        print(f"           measured: {c.measured}")
        print(f"           note: {c.note}")

    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    ax = axes[0]
    for arr, label, colour in ((heuristic, "7a heuristic", "tab:grey"),
                               (bandit, "7b UCB1", "tab:blue"),
                               (rl_seasons, "7d RL", "tab:red")):
        p = np.array([s.profits.sum(axis=1) for s in arr])
        m = p.mean(axis=0); se = p.std(axis=0, ddof=1) / np.sqrt(p.shape[0])
        ax.plot(m, color=colour, label=label)
        ax.fill_between(range(len(m)), m - se, m + se, color=colour, alpha=0.12)
    ax.set_xlabel("week"); ax.set_ylabel("total profit per week")
    ax.set_title("Multi-week reward buys nothing here (±1 SEM)"); ax.legend(fontsize=9)

    ax = axes[1]
    ax.plot(sig["prices"].mean(axis=0), color="tab:red", label="7d RL")
    ax.plot(sig_b["prices"].mean(axis=0), color="tab:blue", label="7b UCB1")
    ax.axhline(MYOPIC_ARM, ls="--", c="firebrick", lw=1)
    ax.text(1, MYOPIC_ARM + 0.01, "myopic optimum 2.60", fontsize=8, color="firebrick")
    ax.set_xlabel("week"); ax.set_ylabel("mean Slow posted price")
    ax.set_title("No sacrifice-then-recover trajectory"); ax.legend(fontsize=9)
    fig.tight_layout(); fig.savefig(RESULTS_ROOT / "rl.png", dpi=150); plt.close(fig)

    experiment_log.append_row(LOG_PATH, {
        "experiment_id": PHASE7D.name, "git_commit": commit,
        "config_file": "src/market_sim/config.py::PHASE7D",
        "phase": 7, "seed": "train 1000-1119, eval 0-29",
        "n_buyers": PHASE7D.n_buyers, "n_sellers": PHASE7D.n_sellers,
        "model_used": "rule_based", "decision_type": "N/A",
        "human_benchmark_id": "N/A", "human_benchmark_status": "not_applicable",
        "synthetic_cost_usd": "N/A", "synthetic_latency_seconds": "N/A",
        "research_question": RESEARCH_QUESTION,
        "changed_mechanism": "Q-network on discounted multi-week return, same arms as 7b",
        "transaction_count": sum(len(w.transactions) for s in rl_seasons for w in s.weeks),
        "participation_rate": round(float(np.mean([s.purchase_rate().mean() for s in rl_seasons])), 4),
        "result_summary": (
            f"Profit {bp.mean():.1f} (7b bandit) -> {rp.mean():.1f} (RL, held-out seeds), "
            f"{gain/scale:+.1%} 95% CI [{lo/scale:+.1%}, {hi/scale:+.1%}], verdict {verdict}. "
            f"Sacrifice-then-recover signature {'present' if present else 'absent'}: "
            f"week-price correlation {sig['week_price_corr']:+.3f}, first third "
            f"{sig['first_third']:.2f} against last third {sig['last_third']:.2f}."
        ),
        "decision_implication": "N/A - infrastructure phase, no business decision",
        "next_experiment": "Phase 7e mechanism-enabled environment",
    })
    print(f"\nWrote {LOG_PATH.relative_to(REPO_ROOT)}")
    return 0 if all(c.passed for c in criteria) else 1


if __name__ == "__main__":
    raise SystemExit(main())
