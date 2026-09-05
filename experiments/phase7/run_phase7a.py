"""Run Phase 7a — Heuristic Seller Pricing.

Profit hill-climbing against a fixed-price arm on identical seeds, three
seasons. 7a does not have to beat anything except degeneracy: it is the
baseline 7b-7d are graded against, so what it has to be is a market that still
works. The criteria are written around the specific way the originally
specified rule was not - see docs/phase_specifications.md, Phase 7a.

    python experiments/phase7/run_phase7a.py
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

from market_sim import acceptance, experiment_log, outputs  # noqa: E402
from market_sim.config import PHASE7A_FIXED, PHASE7A_HILL  # noqa: E402
from market_sim.engine import run_season_seeds  # noqa: E402

RESULTS_ROOT = REPO_ROOT / "results" / "phase7a"
LOG_PATH = REPO_ROOT / "experiment_log.csv"

RESEARCH_QUESTION = (
    "Does stateful policy learning produce market structures that cannot emerge "
    "from myopic bandit optimization? 7a establishes the heuristic baseline the "
    "later sub-stages are graded against."
)


def plot(hill, fixed, out_path: Path) -> None:
    cfg = PHASE7A_HILL
    classes = cfg.seller_class_of()
    prices = np.array([s.posted_prices for s in hill])           # (seed, week, seller)
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))

    ax = axes[0]
    poor_budget = min(c.budget_per_visit for c in cfg.buyer_classes)
    for i, name in enumerate(classes):
        colour = "tab:green" if name == "Slow" else "tab:purple"
        ax.plot(prices[:, :, i].mean(axis=0), color=colour, alpha=0.75,
                label=f"{name} #{i}" if i in (0, 3) else None)
    ax.axhline(3.0, ls="--", c="firebrick", lw=1)
    ax.text(1, 3.05, "profit optimum for Slow (3.00) = Poor's budget",
            fontsize=8, color="firebrick")
    ax.axhline(poor_budget, ls=":", c="grey", lw=1)
    for s in range(0, 66, 22):
        ax.axvline(s, ls=":", c="#cccccc", lw=1)
    ax.set_xlabel("week"); ax.set_ylabel("posted price")
    ax.set_title("Prices under hill climbing (season boundaries dotted)")
    ax.legend(fontsize=8)

    ax = axes[1]
    for data, label, colour in ((hill, "hill climbing", "tab:blue"),
                                (fixed, "fixed price", "tab:grey")):
        arr = np.array([s.profits.sum(axis=1) for s in data])
        mean = arr.mean(axis=0)
        sem = arr.std(axis=0, ddof=1) / np.sqrt(arr.shape[0])
        ax.plot(mean, color=colour, label=label)
        ax.fill_between(range(len(mean)), mean - sem, mean + sem, color=colour, alpha=0.15)
    ax.set_xlabel("week"); ax.set_ylabel("total profit per week")
    ax.set_title("Market profit (shaded = ±1 SEM)")
    ax.legend(fontsize=9)

    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def main() -> int:
    commit = experiment_log.git_commit(REPO_ROOT)
    hill = run_season_seeds(PHASE7A_HILL)
    fixed = run_season_seeds(PHASE7A_FIXED)

    for cfg, data in ((PHASE7A_HILL, hill), (PHASE7A_FIXED, fixed)):
        out = RESULTS_ROOT / cfg.name
        out.mkdir(parents=True, exist_ok=True)
        outputs.weekly_summary_frame(cfg, data).to_csv(out / "weekly_summary.csv", index=False)
        outputs.write_all(cfg, [w for s in data for w in s.weeks], out)

    criteria = acceptance.evaluate_phase7a(PHASE7A_HILL, hill, fixed)
    classes = PHASE7A_HILL.seller_class_of()
    prices = np.array([s.posted_prices for s in hill])

    print(f"\n=== phase7a — {PHASE7A_HILL.weeks} weeks, {len(PHASE7A_HILL.seeds)} seeds ===")
    print(f"  unit cost {PHASE7A_HILL.unit_cost_of()}, fixed weekly cost "
          f"{PHASE7A_HILL.fixed_weekly_cost:g}, step ±{PHASE7A_HILL.price_step:.0%}")
    print(f"\n  {'week':>5s} " + " ".join(f"{c + ' #' + str(i):>10s}" for i, c in enumerate(classes))
          + f"  {'profit/wk':>10s}")
    for w in (0, 10, 21, 43, 65):
        pf = np.mean([s.profits[w].sum() for s in hill])
        print(f"  {w:5d} " + " ".join(f"{prices[:, w, i].mean():10.3f}" for i in range(len(classes)))
              + f"  {pf:10.1f}")

    print("\n  acceptance criteria:")
    for c in criteria:
        print(f"    [{'PASS' if c.passed else 'FAIL'}] {c.name}")
        print(f"           measured: {c.measured}  (required: {c.threshold})")
        if c.note:
            print(f"           note: {c.note}")

    print("\n  reported, not graded — class-to-tier shares vs the fixed-price arm:")
    for bc in ("Poor", "Middle", "Rich"):
        for sc in ("Slow", "Shigh"):
            a = np.array([s.tier_share(bc, sc) for s in hill])
            b = np.array([s.tier_share(bc, sc) for s in fixed])
            m, lo, hi = acceptance.mean_difference_ci(a, b)
            print(f"    {bc}_to_{sc}_share {np.nanmean(b):.4f} -> {np.nanmean(a):.4f}  "
                  f"shift {m:+.4f}  95% CI [{lo:+.4f}, {hi:+.4f}]")

    plot(hill, fixed, RESULTS_ROOT / "pricing.png")

    hp = np.array([s.profits.sum(axis=1).mean() for s in hill])
    fp = np.array([s.profits.sum(axis=1).mean() for s in fixed])
    gain, glo, ghi = acceptance.mean_difference_ci(hp, fp)
    for cfg, data, note in (
        (PHASE7A_HILL, hill, "profit hill-climbing, ±5% weekly step, floored at unit cost"),
        (PHASE7A_FIXED, fixed, "baseline arm: identical market, prices held fixed"),
    ):
        experiment_log.append_row(LOG_PATH, {
            "experiment_id": cfg.name, "git_commit": commit,
            "config_file": f"src/market_sim/config.py::{cfg.name.upper()}",
            "phase": 7, "seed": "0-29",
            "n_buyers": cfg.n_buyers, "n_sellers": cfg.n_sellers,
            "model_used": "rule_based", "decision_type": "N/A",
            "human_benchmark_id": "N/A", "human_benchmark_status": "not_applicable",
            "synthetic_cost_usd": "N/A", "synthetic_latency_seconds": "N/A",
            "research_question": RESEARCH_QUESTION, "changed_mechanism": note,
            "transaction_count": sum(len(w.transactions) for s in data for w in s.weeks),
            "participation_rate": round(float(np.mean([s.purchase_rate().mean() for s in data])), 4),
            "result_summary": (
                f"Weekly profit {fp.mean():.1f} fixed -> {hp.mean():.1f} hill-climbing, "
                f"{gain:+.1f} 95% CI [{glo:+.1f}, {ghi:+.1f}]. Slow prices climb toward but "
                f"do not reach the 3.00 optimum, which sits exactly on Poor's budget; that "
                f"headroom is what 7b-7d have to win. "
                f"{sum(c.passed for c in criteria)}/{len(criteria)} criteria passed."
            ),
            "decision_implication": "N/A - infrastructure phase, no business decision",
            "next_experiment": "Phase 7b multi-armed bandit",
        })
    print(f"\nWrote {LOG_PATH.relative_to(REPO_ROOT)}")
    return 0 if all(c.passed for c in criteria) else 1


if __name__ == "__main__":
    raise SystemExit(main())
