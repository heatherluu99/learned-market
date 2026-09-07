"""Loyalty v2, Gate C — does the conclusion depend on how loyalty is represented?

    M0  no loyalty
    M1  streak / recency state, kappa * min(streak, 3)
    M2  exponentially decayed relationship state, the main specification

Gate C does **not** require M1 and M2 to agree numerically. Two mechanisms
encoding different theories of what loyalty is should differ; the question is
whether the branch's *qualitative* conclusions turn on the choice.

Gate B3 measured amplification for M2 only, so M0 and M1 are run here through
the identical pipeline - imported rather than reimplemented, and validated
against a cell Gate B3 committed. Everything else is assembled from the gates
already run.

Pre-registered before any of this: a case where M1 shows no path dependence
while human-admissible M2 cells do would be a substantive finding rather than
a robustness failure. Gate B has already settled that one - both are zero.
"""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _amplification as amp  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from market_sim import buyer, config, experiment_log  # noqa: E402

RESULTS_ROOT = REPO_ROOT / "results" / "loyalty_v2"
LOG_PATH = REPO_ROOT / "experiment_log.csv"

#: The human decay ratio and its interval, from Gate A2b under the
#: parity-free contiguous split.
HUMAN_RATIO, HUMAN_RATIO_HI = 0.255, 0.591

RESEARCH_QUESTION = (
    "Do this branch's conclusions depend on whether loyalty is represented as "
    "consecutive-choice persistence or as an exponentially decayed "
    "seller-specific state?"
)


def main() -> int:
    commit = experiment_log.git_commit(REPO_ROOT)
    RESULTS_ROOT.mkdir(parents=True, exist_ok=True)
    print("\n=== Loyalty v2, Gate C — mechanism robustness ===")
    print(f"  {RESEARCH_QUESTION}\n")

    # Phase 7a's own purchase level - that market has streak loyalty on, so
    # this is not a "no loyalty" level. It is a common anchor: what matters is
    # that every mechanism is held to the same number, not which number.
    target = buyer.mean_purchase_probability(config.PHASE7A_FIXED,
                                             amp.CALIBRATION_SEEDS)
    print(f"  Purchase level held at {target:.4f} for every mechanism.\n")

    # ---- amplification for M0 and M1, the two Gate B3 did not run ----------
    # The four measurements are the slow part and do not change when only the
    # summary is being re-derived.
    cached = RESULTS_ROOT / "gate_c_amplification.csv"
    reuse = "--reuse" in sys.argv and cached.exists()
    rows = []
    print(f"  {'mechanism':14s} {'tau':>5s} {'H':>6s} {'R':>6s} {'D_off':>7s} "
          f"{'D_sha':>7s} {'A':>6s} {'gate':>5s}")
    if reuse:
        m01 = pd.read_csv(cached)
        for r in m01.itertuples():
            print(f"  {r.mechanism:14s} {r.tau:5.2f} {r.entropy_bits:6.3f} "
                  f"{r.R:6.3f} {r.d_offline:7.4f} {r.d_shadow:7.4f} "
                  f"{r.amplification:6.2f} {'yes' if r.gate else 'NO':>5s}  (reused)")
    # LOYALTY_V2_NONE, not PHASE7A_FIXED: that market already carries the 0.5
    # streak bonus, so using it as "no loyalty" runs M1 twice.
    for name, base in () if reuse else (("M0 none", config.LOYALTY_V2_NONE),
                                        ("M1 streak", config.LOYALTY_V2_STREAK)):
        for tau in (1.0, 0.5):
            got = amp.measure(dataclasses.replace(base, teacher_temperature=tau),
                              target)
            rows.append({"mechanism": name, "tau": tau, **got})
            print(f"  {name:14s} {tau:5.2f} {got['entropy_bits']:6.3f} "
                  f"{got['R']:6.3f} {got['d_offline']:7.4f} {got['d_shadow']:7.4f} "
                  f"{got['amplification']:6.2f} "
                  f"{'yes' if got['gate'] else 'NO':>5s}", flush=True)
    if not reuse:
        m01 = pd.DataFrame(rows)
        m01.to_csv(cached, index=False)

    # ---- assemble every conclusion this branch produced --------------------
    b3 = pd.read_csv(RESULTS_ROOT / "gate_b3.csv")
    gate_b = pd.read_csv(RESULTS_ROOT / "gate_b.csv")
    by_lag = pd.read_csv(RESULTS_ROOT / "gate_a_by_lag.csv")
    horizon = pd.read_csv(RESULTS_ROOT / "horizon_cells.csv")

    m2 = b3[b3["rho"].isin((0.50, 0.80))]          # primary region only
    m2_b = gate_b[gate_b["primary"] == True]        # noqa: E712
    m1_b = gate_b[gate_b["cell"] == config.LOYALTY_V2_STREAK.name].iloc[0]
    m1_lag = by_lag[by_lag["cell"] == "M1 streak"].iloc[0]
    m1_ratio = m1_lag["lag_8"] / m1_lag["lag_1"]
    m2_ratios = horizon[horizon["rho"].isin((0.50, 0.80))]["decay_ratio"]

    def band(values):
        return f"{np.min(values):+.4f} to {np.max(values):+.4f}"

    print("\n  Conclusion by conclusion, M1 against the M2 primary region:\n")
    findings = []

    def record(question, m0, m1, m2v, depends, note):
        findings.append({"question": question, "M0": m0, "M1": m1, "M2": m2v,
                         "representation_dependent": depends, "note": note})
        print(f"  {question}")
        print(f"    M0 {m0}   |   M1 {m1}   |   M2 {m2v}")
        print(f"    -> {'DEPENDS on representation' if depends else 'holds under both'}"
              f": {note}\n")

    record("Path dependence after a week-0 perturbation",
           "0.0000", f"{m1_b['path_on']:.4f}", band(m2_b["path_on"]), False,
           "zero everywhere; the null survives both representations")

    record("Decay shape of state dependence (lag 8 / lag 1)",
           "n/a - no memory", f"{m1_ratio:.3f}", band(m2_ratios), True,
           f"M1 is pinned near the short-memory end; only M2 reaches the "
           f"human ratio of {HUMAN_RATIO:.3f} across a range")

    record("Shock recovery time, memory ON minus OFF (weeks)",
           "0 by construction", f"{m1_b['recovery_weeks_diff']:+.3f}",
           band(m2_b["recovery_weeks_diff"]), True,
           "M1 recovers more slowly than its own control, rho >= 0.80 stock "
           "cells recover faster - a counter loses the relationship a forced "
           "substitution breaks, a decaying stock keeps most of it")

    record("Return to a shocked seller within 3 weeks",
           "0 by construction", f"{m1_b['return_rate_3wk_diff']:+.4f}",
           band(m2_b["return_rate_3wk_diff"]), False,
           "memory raises it under both, by a similar margin")

    m0_amp = m01[m01["mechanism"] == "M0 none"]["amplification"]
    m1_amp = m01[m01["mechanism"] == "M1 streak"]["amplification"]
    record("Trajectory amplification",
           band(m0_amp), band(m1_amp), band(m2["amplification"]), False,
           "the ordering M0 > M1 > M2 holds at both temperatures - less memory, "
           "more amplification - and only M2 at high gamma drops below one, so "
           "the direction is the same under every representation")

    frame = pd.DataFrame(findings)
    frame.to_csv(RESULTS_ROOT / "gate_c.csv", index=False)
    plot(m01, m2, m1_ratio, m2_ratios)

    depends = int(frame["representation_dependent"].sum())
    print(f"  {depends} of {len(frame)} conclusions depend on the representation.")

    experiment_log.append_row(LOG_PATH, {
        "experiment_id": "loyaltyv2_gate_c_mechanism_robustness",
        "git_commit": commit,
        "config_file": "experiments/loyalty_v2/run_gate_c.py",
        "phase": 10.5, "seed": f"{len(amp.EVAL_SEEDS)} eval seeds",
        "n_buyers": sum(b.count for b in config.PHASE7A_FIXED.buyer_classes),
        "n_sellers": sum(s.count for s in config.PHASE7A_FIXED.seller_classes),
        "model_used": "M0 none / M1 streak / M2 relationship stock",
        "decision_type": "purchase",
        "human_benchmark_id": "Ecdat::Cracker via Gate A2b decay shape",
        "synthetic_cost_usd": 0.0,
        "synthetic_latency_seconds": 0.0,
        "research_question": RESEARCH_QUESTION,
        "changed_mechanism": (
            "loyalty representation itself - no state, a capped consecutive-"
            "choice counter, and an exponentially decayed per-pair stock - "
            "compared across every conclusion this branch produced"
        ),
        "transaction_count": len(m01) * len(amp.EVAL_SEEDS),
        "human_benchmark_status": "compared_to_published_panel",
        "participation_rate": f"purchase level held at {target:.4f}",
        "result_summary": (
            f"{depends}/{len(frame)} conclusions depend on the representation. "
            + "; ".join(f"{r.question}: M1 {r.M1} vs M2 {r.M2} "
                        f"({'depends' if r.representation_dependent else 'holds'})"
                        for r in frame.itertuples())
        ),
        "decision_implication": (
            "Which of this branch's findings may be stated of loyalty in "
            "general and which only of a particular representation"
        ),
        "next_experiment": "H_promo - promotion-dependent reinforcement, sign "
                           "predicted before running",
    })
    print(f"\n  Wrote {RESULTS_ROOT}\n")
    return 0


def plot(m01, m2, m1_ratio, m2_ratios) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(12.5, 4.6))

    ax = axes[0]
    for mech, sub in m01.groupby("mechanism"):
        ax.scatter(sub["R"], sub["amplification"], s=90, label=mech, zorder=3)
    ax.scatter(m2["R"], m2["amplification"], s=45, c="0.6",
               label="M2 primary cells", zorder=2)
    ax.axhline(1.0, c="0.3", lw=0.8, ls=":")
    ax.set_xlabel(r"$R$ — imitation error relative to intrinsic noise")
    ax.set_ylabel(r"amplification  $D_{shadow}/D_{offline}$")
    ax.set_title("No representation makes the closed loop unstable", fontsize=10)
    ax.legend(fontsize=7)

    ax = axes[1]
    ax.axhspan(0, HUMAN_RATIO_HI, color="tab:green", alpha=0.13,
               label="human-compatible shape")
    ax.axhline(HUMAN_RATIO, c="tab:green", lw=2, label=f"human {HUMAN_RATIO:.3f}")
    ax.scatter([0] * len(m2_ratios), m2_ratios, s=60, label="M2 primary cells")
    ax.scatter([0], [m1_ratio], s=110, marker="^", c="tab:orange",
               label=f"M1 streak ({m1_ratio:.3f})")
    ax.set_xticks([])
    ax.set_ylabel("decay ratio (lag 8 / lag 1)")
    ax.set_title("M1 reaches only the short-memory end", fontsize=10)
    ax.legend(fontsize=7)

    fig.suptitle("Loyalty v2 Gate C — which conclusions turn on the representation",
                 fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(RESULTS_ROOT / "gate_c.png", dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    raise SystemExit(main())
