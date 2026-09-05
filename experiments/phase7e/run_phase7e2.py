"""Run Phase 7e-2 — the intertemporal headroom gate. Still no learner.

Asks whether any hand-designed schedule beats the best standing price in the
calibrated environment. If none does, there is nothing for a multi-week policy
to find and 7e-3's horizon arm is not run - the context arm still is, because
gate 1 licensed it.

Schedules are selected on a discovery seed block and the selected one alone is
tested on the evaluation block, because a maximum over ~150 comparisons is
significant by construction. See docs/phase_specifications.md, Phase 7e-2.

    python experiments/phase7e/run_phase7e2.py
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
from market_sim.config import PHASE7E_RHO, phase7e_cell  # noqa: E402
from market_sim.engine import run_season  # noqa: E402

RESULTS_ROOT = REPO_ROOT / "results" / "phase7e2"
LOG_PATH = REPO_ROOT / "experiment_log.csv"

#: Carried from 7e-1: the calibrated ceiling and the oracle standing price.
CARRIED_LMAX = 3.30
ORACLE_PRICE = 2.65
DELTAS = (0.0, 0.25, 0.5, 1.0)
DISCOVERY_SEEDS = tuple(range(2000, 2060))
EVAL_SEEDS = tuple(range(30))
TARGET = 0

RESEARCH_QUESTION = (
    "In an environment where loyalty persists as a stock, can any pricing "
    "schedule beat the best standing price - is there anything for a "
    "multi-week policy to find?"
)


def environment(delta: float):
    """The carried 7e-1 cell, standing price at its own oracle optimum."""
    cell = phase7e_cell(rho=PHASE7E_RHO, delta=delta, max_bonus=CARRIED_LMAX)
    return acceptance.split_target_config(cell, ORACLE_PRICE, name=f"d{delta:g}")


def main() -> int:
    commit = experiment_log.git_commit(REPO_ROOT)
    RESULTS_ROOT.mkdir(parents=True, exist_ok=True)

    base = environment(DELTAS[0])
    schedules = {
        **acceptance.one_shot_schedules(base.price_arms, base.weeks),
        **acceptance.cyclic_schedules(base.price_arms, base.weeks),
    }
    flat_plan = schedules.pop("flat")
    family = {
        name: ("cyclic" if name.startswith("cycle") else "one-shot")
        for name in schedules
    }

    print("\n=== Phase 7e-2 — intertemporal headroom ===")
    print(f"  {RESEARCH_QUESTION}\n")
    print(f"  Environment: rho={PHASE7E_RHO:g}, L_max={CARRIED_LMAX:.2f} (7e-1's "
          f"calibration), target stall's standing price {ORACLE_PRICE:.2f}.")
    print(f"  {len(schedules)} schedules x {len(DELTAS)} deltas, selected on seeds "
          f"{DISCOVERY_SEEDS[0]}-{DISCOVERY_SEEDS[-1]}, tested on 0-29.\n")

    rows = []
    for delta in DELTAS:
        env = environment(delta)
        flat = acceptance.schedule_profit(env, flat_plan, DISCOVERY_SEEDS, TARGET)
        for name, plan in schedules.items():
            profit = acceptance.schedule_profit(env, plan, DISCOVERY_SEEDS, TARGET)
            gain, lo, hi = acceptance.mean_difference_ci(profit, flat)
            scale = float(flat.mean())
            rows.append({
                "delta": delta, "schedule": name, "family": family[name],
                "flat": scale, "scheduled": float(profit.mean()),
                "gain_pct": gain / scale * 100,
                "ci_lo_pct": lo / scale * 100, "ci_hi_pct": hi / scale * 100,
            })
        best = max((r for r in rows if r["delta"] == delta), key=lambda r: r["gain_pct"])
        print(f"  delta={delta:<4g} flat {best['flat']:6.2f}/wk   best of "
              f"{len(schedules)}: {best['gain_pct']:+6.1f}%  {best['schedule']}")

    discovery = pd.DataFrame(rows)
    selected = discovery.loc[discovery["gain_pct"].idxmax()]
    print(f"\n  Best over the whole search: {selected['schedule']} at "
          f"delta={selected['delta']:g}, {selected['gain_pct']:+.1f}% on discovery.")
    print("  Every schedule in the search, discovery block, ranked:")
    for _, r in discovery.sort_values("gain_pct", ascending=False).head(6).iterrows():
        print(f"    {r['gain_pct']:+6.1f}%  delta={r['delta']:<4g} {r['schedule']}")
    print("    ...")
    for _, r in discovery.sort_values("gain_pct").head(2).iterrows():
        print(f"    {r['gain_pct']:+6.1f}%  delta={r['delta']:<4g} {r['schedule']}")

    # ---- the held-out verdict ---------------------------------------------
    env = environment(float(selected["delta"]))
    flat_eval = acceptance.schedule_profit(env, flat_plan, EVAL_SEEDS, TARGET)
    sel_eval = acceptance.schedule_profit(
        env, schedules[selected["schedule"]], EVAL_SEEDS, TARGET
    )
    criteria = acceptance.evaluate_phase7e2(
        str(selected["schedule"]), sel_eval, flat_eval
    )
    print(f"\n  Held-out block, seeds 0-29:")
    for c in criteria:
        print(f"    [{'PASS' if c.passed else 'FAIL'}] {c.name}")
        print(f"           {c.measured}")
        print(f"           threshold: {c.threshold}")

    passed = all(c.passed for c in criteria)
    print(f"\n  Gate 2 {'PASSES' if passed else 'FAILS'}. "
          + ("7e-3 runs both the context arm and the horizon arm."
             if passed else
             "7e-3 runs the context arm only - gate 1 licensed it and gate 2 did "
             "not license the horizon arm."))

    # ---- artefacts ---------------------------------------------------------
    discovery.to_csv(RESULTS_ROOT / "discovery.csv", index=False)
    pd.DataFrame({
        "seed": EVAL_SEEDS, "flat": flat_eval, "scheduled": sel_eval,
    }).to_csv(RESULTS_ROOT / "held_out.csv", index=False)
    plot(discovery, selected, schedules, flat_eval, sel_eval, env)

    gain, lo, hi = acceptance.mean_difference_ci(sel_eval, flat_eval)
    scale = float(flat_eval.mean())
    experiment_log.append_row(LOG_PATH, {
        "experiment_id": "phase7e2_headroom", "git_commit": commit,
        "config_file": "src/market_sim/config.py::phase7e_cell",
        "phase": 7,
        "seed": f"discover {DISCOVERY_SEEDS[0]}-{DISCOVERY_SEEDS[-1]}, evaluate 0-29",
        "n_buyers": env.n_buyers, "n_sellers": env.n_sellers,
        "model_used": "rule_based", "decision_type": "N/A",
        "human_benchmark_id": "N/A", "human_benchmark_status": "not_applicable",
        "synthetic_cost_usd": "N/A", "synthetic_latency_seconds": "N/A",
        "research_question": RESEARCH_QUESTION,
        "changed_mechanism": (
            f"{len(schedules)} hand-designed pricing schedules (one-shot and "
            f"cyclic) against the oracle standing price of {ORACLE_PRICE:.2f}, "
            f"across a delta ladder of {list(DELTAS)}"
        ),
        "transaction_count": "N/A",
        "participation_rate": "N/A",
        "result_summary": (
            f"Gate 2 {'passes' if passed else 'fails'}. Best on discovery: "
            f"{selected['schedule']} at delta={selected['delta']:g}, "
            f"{selected['gain_pct']:+.1f}%. On held-out seeds 0-29: "
            f"{scale:.2f} -> {sel_eval.mean():.2f} per week, {gain / scale:+.1%} "
            f"(95% CI [{lo / scale:+.1%}, {hi / scale:+.1%}])."
        ),
        "decision_implication": "N/A - infrastructure phase, no business decision",
        "next_experiment": (
            "Phase 7e-3: contextual bandit and Q-network"
            if passed else
            "Phase 7e-3: contextual bandit only - no intertemporal headroom to license "
            "the horizon arm"
        ),
    })
    print(f"\n  Wrote {RESULTS_ROOT}\n")
    return 0


def plot(discovery, selected, schedules, flat_eval, sel_eval, env) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(15.5, 4.4))

    ax = axes[0]
    for fam, colour in (("one-shot", "tab:orange"), ("cyclic", "tab:blue")):
        sub = discovery[discovery["family"] == fam]
        ax.scatter(sub["delta"] + (0.012 if fam == "cyclic" else -0.012),
                   sub["gain_pct"], s=14, alpha=0.55, c=colour, label=fam)
    ax.axhline(0, c="0.4", lw=1)
    ax.axhline(acceptance.GATE2_MIN_GAIN_PCT, ls="--", c="firebrick", lw=1)
    ax.text(discovery["delta"].min(), acceptance.GATE2_MIN_GAIN_PCT + 0.4,
            f"gate 2 needs ≥ +{acceptance.GATE2_MIN_GAIN_PCT:g}%",
            fontsize=7.5, color="firebrick")
    worst = discovery["gain_pct"].min()
    ax.set_ylim(-22, max(6, discovery["gain_pct"].max() + 2))
    ax.text(0.02, 0.03, f"{(discovery['gain_pct'] < -22).sum()} schedules fall below "
            f"this axis, to {worst:.0f}%", transform=ax.transAxes, fontsize=7,
            color="0.35")
    ax.set_xlabel("delta (how much a discount builds loyalty)")
    ax.set_ylabel("profit vs the best standing price (%)")
    ax.set_title("Every schedule, discovery block", fontsize=10)
    ax.legend(fontsize=8, loc="lower left", bbox_to_anchor=(0.0, 0.10))

    # The causal argument: the same price path, only the investment channel
    # changing. At delta = 0 it loses money, which is what makes the gain at
    # delta = 1 attributable to loyalty rather than to the path itself.
    ax = axes[1]
    same = discovery[discovery["schedule"] == selected["schedule"]].sort_values("delta")
    ax.errorbar(same["delta"], same["gain_pct"],
                yerr=[same["gain_pct"] - same["ci_lo_pct"],
                      same["ci_hi_pct"] - same["gain_pct"]],
                marker="o", lw=1.6, capsize=3, color="tab:blue")
    ax.axhline(0, c="0.4", lw=1)
    ax.axhline(acceptance.GATE2_MIN_GAIN_PCT, ls="--", c="firebrick", lw=1)
    ax.scatter([0], [same.iloc[0]["gain_pct"]], s=90, facecolors="none",
               edgecolors="firebrick", lw=1.6, zorder=4)
    ax.annotate("delta = 0: the same price path,\nno investment channel, loses money",
                (0, same.iloc[0]["gain_pct"]), textcoords="offset points",
                xytext=(10, -2), fontsize=7.5, color="firebrick")
    ax.set_xlabel("delta")
    ax.set_ylabel("profit vs the best standing price (%)")
    ax.set_title(f"{selected['schedule']}, across the ladder", fontsize=10)

    ax = axes[2]
    diff = (sel_eval - flat_eval) / flat_eval.mean() * 100
    ax.axhline(0, c="0.4", lw=1)
    ax.scatter(range(len(diff)), diff, s=18, c="tab:blue", zorder=3)
    mean = float(diff.mean())
    sem = float(diff.std(ddof=1) / np.sqrt(len(diff)))
    ax.axhline(mean, color="tab:blue", lw=1.4)
    ax.fill_between([-1, len(diff)], mean - 1.96 * sem, mean + 1.96 * sem,
                    color="tab:blue", alpha=0.15, lw=0)
    ax.axhline(acceptance.GATE2_MIN_GAIN_PCT, ls="--", c="firebrick", lw=1)
    ax.set_xlim(-1, len(diff))
    ax.set_xlabel("evaluation seed")
    ax.set_ylabel("schedule vs flat (%)")
    ax.set_title(f"Held-out: {mean:+.1f}% (95% CI ±{1.96 * sem:.1f})", fontsize=10)

    fig.suptitle(
        "Phase 7e-2 — is there an intertemporal trade-off to learn?", fontsize=12
    )
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(RESULTS_ROOT / "headroom.png", dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    raise SystemExit(main())
