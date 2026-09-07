"""Loyalty v2, Gate B — dynamic validity across the whole grid.

Two of Gate B's three tests are here: path dependence and shock recovery. The
third, Phase 9c's amplification as `A(R, rho, gamma)`, needs the distillation
pipeline per cell and is run separately.

**All nine cells are run.** Gate A1 excluded one on a one-step level criterion,
and A1 was then shown not to identify long-run persistence, so dropping that
cell would discard the longest-memory behaviour in the grid on a test that
cannot see long memory. Cells inside the A2b decay-shape region are marked
primary; the rest are reported alongside.

The pre-registered reading, fixed before this ran: if streak memory shows no
path dependence while primary stock cells do, that is not a robustness failure
but the substantive finding that finite streak memory suppresses history
dependence which persistent relationship memory produces. If the null survives
across the grid it is strengthened rather than repeated, since it would then
hold under a mechanism built to be more persistent than the one that first
produced it.
"""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from market_sim import acceptance, config, experiment_log  # noqa: E402

RESULTS_ROOT = REPO_ROOT / "results" / "loyalty_v2"
LOG_PATH = REPO_ROOT / "experiment_log.csv"

#: Phase 6's victims and shock week, unchanged, so the two branches' path
#: dependence numbers are the same measurement on different mechanisms.
VICTIMS = (5, 40, 75, 95)
SHOCK_WEEK = 40

#: From Gate A2b: the human decay ratio's interval excludes ratios above
#: 0.591, which excludes the whole rho = 0.95 row. Fixed before this ran.
PRIMARY_RHOS = (0.50, 0.80)

RESEARCH_QUESTION = (
    "Among loyalty specifications consistent with observed human state "
    "dependence, which generate persistent market-level dynamics?"
)


def path_dependence(cfg) -> dict[str, float]:
    """The butterfly test: one buyer skips week 0, every draw left untouched."""
    on = acceptance.perturbation_persistence(cfg, VICTIMS)
    off = acceptance.perturbation_persistence(acceptance.memory_off(cfg), VICTIMS)
    mean, lo, hi = acceptance.mean_difference_ci(on, off)
    return {"path_on": float(on.mean()), "path_off": float(off.mean()),
            "path_diff": mean, "path_lo": lo, "path_hi": hi,
            "path_verdict": acceptance.equivalence_verdict(lo, hi)}


def shock(cfg) -> dict[str, float]:
    """One seller closed for a single week, averaged over every seller."""
    out = {}
    for label, c in (("on", cfg), ("off", acceptance.memory_off(cfg))):
        rows = [acceptance.shock_metrics(c, s, SHOCK_WEEK) for s in range(c.n_sellers)]
        for key in ("return_rate_3wk", "permanent_switch_rate", "recovery_weeks"):
            out[f"{key}_{label}"] = float(np.nanmean([r[key] for r in rows]))
    for key in ("return_rate_3wk", "permanent_switch_rate", "recovery_weeks"):
        out[f"{key}_diff"] = out[f"{key}_on"] - out[f"{key}_off"]
    return out


def main() -> int:
    commit = experiment_log.git_commit(REPO_ROOT)
    RESULTS_ROOT.mkdir(parents=True, exist_ok=True)
    print("\n=== Loyalty v2, Gate B — dynamic validity ===")
    print(f"  {RESEARCH_QUESTION}\n")
    print(f"  All 9 cells plus M1. Primary region: rho in {PRIMARY_RHOS} "
          f"(A2b decay shape).\n")

    arms = [(cfg, cfg.loyalty_retention, cfg.loyalty_gamma)
            for cfg in config.LOYALTY_V2_CELLS]
    arms.append((config.LOYALTY_V2_STREAK, np.nan, np.nan))

    rows = []
    print(f"  {'cell':24s} {'prim':>5s} {'path ON':>8s} {'path OFF':>9s} "
          f"{'diff':>8s}  {'verdict':>12s}")
    for cfg, rho, gamma in arms:
        primary = rho in PRIMARY_RHOS
        row = {"cell": cfg.name, "rho": rho, "gamma": gamma, "primary": bool(primary)}
        row |= path_dependence(cfg)
        rows.append(row)
        print(f"  {cfg.name:24s} {'yes' if primary else '-':>5s} "
              f"{row['path_on']:8.4f} {row['path_off']:9.4f} "
              f"{row['path_diff']:+8.4f}  {row['path_verdict']:>12s}")

    print(f"\n  Shock at week {SHOCK_WEEK}, averaged over every seller, "
          f"memory ON minus OFF:")
    print(f"  {'cell':24s} {'return3wk':>10s} {'permanent':>10s} {'recovery':>9s}")
    for row, (cfg, _, _) in zip(rows, arms):
        row |= shock(cfg)
        print(f"  {row['cell']:24s} {row['return_rate_3wk_diff']:+10.4f} "
              f"{row['permanent_switch_rate_diff']:+10.4f} "
              f"{row['recovery_weeks_diff']:+9.4f}")

    frame = pd.DataFrame(rows)
    frame.to_csv(RESULTS_ROOT / "gate_b.csv", index=False)
    plot(frame)

    grid = frame[frame["rho"].notna()]
    primary = grid[grid["primary"]]
    any_path = (grid["path_on"] > 1e-9).sum()
    m1 = frame[frame["cell"] == config.LOYALTY_V2_STREAK.name].iloc[0]
    print(f"\n  Path dependence: {any_path}/9 cells show any late-week divergence "
          f"at all; M1 shows {m1['path_on']:.4f}.")
    print(f"  Primary cells range {primary['path_on'].min():.4f} to "
          f"{primary['path_on'].max():.4f}.")

    experiment_log.append_row(LOG_PATH, {
        "experiment_id": "loyaltyv2_gate_b_dynamics",
        "git_commit": commit,
        "config_file": "experiments/loyalty_v2/run_gate_b.py",
        "phase": 10.5,
        "seed": f"{len(config.PHASE7A_FIXED.seeds)} seeds, victims {VICTIMS}, "
                f"shock week {SHOCK_WEEK}",
        "n_buyers": sum(b.count for b in config.PHASE7A_FIXED.buyer_classes),
        "n_sellers": sum(s.count for s in config.PHASE7A_FIXED.seller_classes),
        "model_used": "relationship loyalty (Guadagni-Little), M2, plus M1 streak",
        "decision_type": "purchase",
        "human_benchmark_id": "Ecdat::Cracker via Gate A2b decay shape",
        "synthetic_cost_usd": 0.0,
        "synthetic_latency_seconds": 0.0,
        "research_question": RESEARCH_QUESTION,
        "changed_mechanism": (
            "path dependence and shock recovery measured across the full "
            "(rho, gamma) grid under the v2 mechanism, with the A2b-compatible "
            "region marked primary rather than the rest being dropped"
        ),
        "transaction_count": len(arms) * len(config.PHASE7A_FIXED.seeds),
        "human_benchmark_status": "compared_to_published_panel",
        "participation_rate": "N/A",
        "result_summary": (
            f"{any_path}/9 cells show any late-week perturbation divergence; "
            f"M1 streak {m1['path_on']:.4f}. "
            + "; ".join(f"rho={r.rho:.2f} gamma={r.gamma:.2f}: path {r.path_on:.4f} "
                        f"({r.path_verdict}), permanent switch diff "
                        f"{r.permanent_switch_rate_diff:+.4f}"
                        for r in grid.itertuples())
        ),
        "decision_implication": (
            "Whether the Phase 6 path-dependence null survives a mechanism "
            "built to be more persistent than the one that produced it"
        ),
        "next_experiment": "Loyalty v2 Gate B3 - Phase 9c amplification A(R, rho, gamma)",
    })
    print(f"\n  Wrote {RESULTS_ROOT}\n")
    return 0


def plot(frame) -> None:
    grid = frame[frame["rho"].notna()]
    m1 = frame[frame["rho"].isna()].iloc[0]
    fig, axes = plt.subplots(1, 2, figsize=(12.5, 4.6))

    ax = axes[0]
    for gamma, sub in grid.groupby("gamma"):
        ax.plot(sub["rho"], sub["path_on"], marker="o", label=f"gamma = {gamma:.2f}")
    ax.axhline(m1["path_on"], ls="--", c="0.4", lw=1,
               label=f"M1 streak ({m1['path_on']:.4f})")
    ax.axvspan(0.45, 0.85, color="tab:green", alpha=0.12,
               label="A2b primary region")
    ax.set_xlabel("rho — memory retention")
    ax.set_ylabel("late-week divergence after a week-0 perturbation")
    ax.set_title("Path dependence: does a perturbation survive?", fontsize=10)
    ax.legend(fontsize=7)

    ax = axes[1]
    width = 0.25
    x = np.arange(len(grid))
    for i, (key, name) in enumerate((
            ("return_rate_3wk_diff", "return within 3 wk"),
            ("permanent_switch_rate_diff", "permanent switch"))):
        ax.bar(x + (i - 0.5) * width, grid[key], width, label=name)
    ax.axhline(0, c="0.3", lw=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels([f"{r.rho:.2f}/{r.gamma:.2f}" for r in grid.itertuples()],
                       rotation=45, fontsize=7)
    ax.set_xlabel("rho / gamma")
    ax.set_ylabel("memory ON minus OFF")
    ax.set_title(f"Shock recovery at week {SHOCK_WEEK}", fontsize=10)
    ax.legend(fontsize=7)

    fig.suptitle("Loyalty v2 Gate B — dynamics across the whole grid", fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(RESULTS_ROOT / "gate_b.png", dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    raise SystemExit(main())
