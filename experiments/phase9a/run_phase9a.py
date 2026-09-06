"""Run Phase 9a — distil the hand-written buyer, then deploy it.

Five measurements in the order the gate requires: offline conditional fidelity,
held-out calibration, the gate, closed-loop trajectory fidelity, and the state
distribution the student itself produces. See docs/phase_specifications.md,
Phase 9a.

    python experiments/phase9a/run_phase9a.py
"""

from __future__ import annotations

import dataclasses
import sys
import warnings
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
warnings.filterwarnings("ignore", message="Degrees of freedom <= 0")
warnings.filterwarnings("ignore", message="Mean of empty slice")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from market_sim import acceptance, buyer, experiment_log  # noqa: E402
from market_sim.config import PHASE6_MAIN  # noqa: E402
from market_sim.engine import ENCOUNTER_FIELDS, run_season  # noqa: E402

RESULTS_ROOT = REPO_ROOT / "results" / "phase9a"
LOG_PATH = REPO_ROOT / "experiment_log.csv"

BASE = PHASE6_MAIN
TRAIN_SEEDS = tuple(range(1000, 1120))
HELD_OUT_SEEDS = tuple(range(200, 240))
EVAL_SEEDS = tuple(range(30))
#: Capacity sweep, to measure the observation set's floor rather than assume it.
CAPACITIES = ((16, 1), (32, 2), (64, 2), (128, 3), (256, 3))
CANONICAL = (64, 2)

RESEARCH_QUESTION = (
    "Can a learned policy recover the conditional behaviour of the rule-based "
    "buyer it replaces, and does that one-step fidelity survive endogenous "
    "distribution shift when it is deployed in closed loop?"
)


def main() -> int:
    commit = experiment_log.git_commit(REPO_ROOT)
    RESULTS_ROOT.mkdir(parents=True, exist_ok=True)
    i_p = ENCOUNTER_FIELDS.index("p_teacher")
    i_a = ENCOUNTER_FIELDS.index("p_acting")

    print("\n=== Phase 9a — distil the hand-written buyer, then deploy it ===")
    print(f"  {RESEARCH_QUESTION}\n")
    print(f"  Observed: {', '.join(buyer.OBSERVED)}")
    print(f"  Hidden:   {', '.join(buyer.HIDDEN)}\n")

    train = buyer.encounters(BASE, TRAIN_SEEDS)
    held = buyer.encounters(BASE, HELD_OUT_SEEDS)
    print(f"  {len(train):,} training encounters, {len(held):,} held-out "
          f"(seeds {TRAIN_SEEDS[0]}-{TRAIN_SEEDS[-1]} / "
          f"{HELD_OUT_SEEDS[0]}-{HELD_OUT_SEEDS[-1]}, disjoint from evaluation).\n")

    # ---- 1-2. offline fidelity, and the floor ------------------------------
    constant = np.full(len(held), train[:, i_p].mean())
    floor_row = {
        "model": "constant predictor", "hidden": 0, "depth": 0, "soft_labels": True,
        "distance": buyer.policy_distance(held, constant),
        "log_loss": buyer.log_loss(held, constant),
        **{f"cal_{k}": v for k, v in buyer.calibration(held, constant).items()},
    }
    rows = [floor_row]
    print(f"  {'model':22s} {'E|dp|':>8s} {'log-loss':>9s} {'worst stratum':>14s}")
    print(f"  {'constant predictor':22s} {floor_row['distance']:8.4f} "
          f"{floor_row['log_loss']:9.4f} "
          f"{max(v for k, v in floor_row.items() if k.startswith('cal_')):14.4f}")

    nets = {}
    for hidden, depth in CAPACITIES:
        for soft in (True, False):
            net = buyer.train(train, soft_labels=soft, hidden=hidden, depth=depth)
            pred = buyer.predict(net, held)
            cal = buyer.calibration(held, pred)
            row = {"model": f"{hidden}x{depth} {'soft' if soft else 'sampled'}",
                   "hidden": hidden, "depth": depth, "soft_labels": soft,
                   "distance": buyer.policy_distance(held, pred),
                   "log_loss": buyer.log_loss(held, pred),
                   **{f"cal_{k}": v for k, v in cal.items()}}
            rows.append(row)
            nets[(hidden, depth, soft)] = net
            print(f"  {row['model']:22s} {row['distance']:8.4f} "
                  f"{row['log_loss']:9.4f} {max(cal.values()):14.4f}")

    offline = pd.DataFrame(rows)
    soft = offline[(offline.soft_labels) & (offline.hidden > 0)]
    measured_floor = float(soft["distance"].min())
    print(f"\n  Capacity plateaus at E|dp| = {measured_floor:.4f} -> that is the "
          f"observation set's floor.\n  The hidden taste draw accounts for the "
          f"rest: a constant predictor scores {floor_row['distance']:.4f}.")

    # ---- 3. the gate --------------------------------------------------------
    net = nets[(*CANONICAL, True)]
    pred = buyer.predict(net, held)
    criteria = acceptance.evaluate_phase9a_offline(
        distance=buyer.policy_distance(held, pred),
        floor=measured_floor,
        calibration=buyer.calibration(held, pred),
        log_loss=buyer.log_loss(held, pred),
        constant_log_loss=float(floor_row["log_loss"]),
        entropy_floor=buyer.entropy_floor(held),
    )
    print(f"\n  Gate, on the canonical {CANONICAL[0]}x{CANONICAL[1]} soft-label "
          f"student:")
    for c in criteria:
        print(f"    [{'PASS' if c.passed else 'FAIL'}] {c.name}\n"
              f"           {c.measured}")
    passed = all(c.passed for c in criteria)
    print(f"\n  Gate 9a {'PASSES' if passed else 'FAILS'}. "
          + ("Deploying." if passed else
             "Not deployed: a model that cannot match its teacher on the "
             "teacher's own\n  states has nothing to say about changing them."))
    if not passed:
        offline.to_csv(RESULTS_ROOT / "offline.csv", index=False)
        return 1

    # ---- 4-5. closed loop, and the drift it causes --------------------------
    policy = buyer.as_engine_policy(net)
    recording = dataclasses.replace(BASE, record_encounters=True)
    deployed = dataclasses.replace(recording, buyer_policy=policy)
    teacher_runs = [run_season(recording, s) for s in EVAL_SEEDS]
    student_runs = [run_season(deployed, s) for s in EVAL_SEEDS]

    teacher_data = np.asarray([e for s in teacher_runs for e in s.encounters])
    student_data = np.asarray([e for s in student_runs for e in s.encounters])
    # Per seed, so the difference between them carries an interval. A ratio of
    # 1.07 means nothing without one - the whole hypothesis is about whether
    # D_shadow exceeds D_offline, and "it is bigger" is not a measurement.
    per_seed_offline = np.array([
        buyer.policy_distance(np.asarray(s.encounters),
                              buyer.predict(net, np.asarray(s.encounters)))
        for s in teacher_runs
    ])
    per_seed_shadow = np.array([
        float(np.abs(np.asarray(s.encounters)[:, i_p]
                     - np.asarray(s.encounters)[:, i_a]).mean())
        for s in student_runs
    ])
    d_offline, d_shadow = float(per_seed_offline.mean()), float(per_seed_shadow.mean())
    excess, ex_lo, ex_hi = acceptance.mean_difference_ci(
        per_seed_shadow, per_seed_offline)

    drift_columns = {f: ENCOUNTER_FIELDS.index(f) for f in
                     ("streak_here", "purchases_this_week", "spent_this_week",
                      "history_rate")}
    drift = acceptance.state_drift(teacher_data, student_data, drift_columns)
    fidelity = acceptance.trajectory_fidelity(teacher_runs, student_runs, BASE)

    print(f"\n  Closed loop, seeds {EVAL_SEEDS[0]}-{EVAL_SEEDS[-1]}:")
    print(f"    D_offline (teacher's states) = {d_offline:.4f}")
    print(f"    D_shadow  (student's states) = {d_shadow:.4f}   "
          f"{d_shadow / d_offline:.2f}x")
    print(f"    excess, paired by seed      = {excess:+.4f} "
          f"95% CI [{ex_lo:+.4f}, {ex_hi:+.4f}]"
          f"{'  (excludes zero)' if ex_lo > 0 or ex_hi < 0 else '  (includes zero)'}")
    print(f"    state drift, Wasserstein-1 per feature:")
    for k, v in drift.items():
        print(f"      {k:22s} {v:.4f}")
    print(f"    trajectory:")
    for k, v in fidelity.items():
        verdict = f"  {v['verdict']}" if "verdict" in v else ""
        print(f"      {k:22s} {v['teacher']:.4f} -> {v['student']:.4f}  "
              f"({v['diff']:+.4f} CI [{v['lo']:+.4f}, {v['hi']:+.4f}]){verdict}")

    # ---- artefacts ----------------------------------------------------------
    offline.to_csv(RESULTS_ROOT / "offline.csv", index=False)
    pd.DataFrame([{"quantity": k, **v} for k, v in fidelity.items()]).to_csv(
        RESULTS_ROOT / "closed_loop.csv", index=False)
    pd.DataFrame([{"feature": k, "wasserstein_1": v} for k, v in drift.items()]
                 + [{"feature": "D_offline", "wasserstein_1": d_offline},
                    {"feature": "D_shadow", "wasserstein_1": d_shadow},
                    {"feature": "D_excess", "wasserstein_1": excess},
                    {"feature": "D_excess_lo", "wasserstein_1": ex_lo},
                    {"feature": "D_excess_hi", "wasserstein_1": ex_hi}]).to_csv(
        RESULTS_ROOT / "drift.csv", index=False)
    plot(offline, teacher_data, student_data, d_offline, d_shadow, drift,
         fidelity, ex_lo, ex_hi)

    experiment_log.append_row(LOG_PATH, {
        "experiment_id": "phase9a_distillation", "git_commit": commit,
        "config_file": "src/market_sim/buyer.py",
        "phase": 9,
        "seed": (f"train {TRAIN_SEEDS[0]}-{TRAIN_SEEDS[-1]}, held-out "
                 f"{HELD_OUT_SEEDS[0]}-{HELD_OUT_SEEDS[-1]}, deploy 0-29"),
        "n_buyers": BASE.n_buyers, "n_sellers": BASE.n_sellers,
        "model_used": "learned_policy", "decision_type": "N/A",
        "human_benchmark_id": "N/A", "human_benchmark_status": "not_applicable",
        "synthetic_cost_usd": "N/A", "synthetic_latency_seconds": "N/A",
        "research_question": RESEARCH_QUESTION,
        "changed_mechanism": (
            "buyers act on a distilled policy over 8 observable features "
            "instead of the hand-written rule; the rule is still evaluated for "
            "shadow comparison"
        ),
        "transaction_count": sum(len(w.transactions) for s in student_runs
                                 for w in s.weeks),
        "participation_rate": round(fidelity["purchase_rate"]["student"], 4),
        "result_summary": (
            f"Gate passes. Floor {measured_floor:.4f}, student "
            f"{buyer.policy_distance(held, pred):.4f}, constant predictor "
            f"{floor_row['distance']:.4f}. Closed loop: D_offline {d_offline:.4f} "
            f"-> D_shadow {d_shadow:.4f} ({d_shadow / d_offline:.2f}x, excess "
            f"{excess:+.4f} CI [{ex_lo:+.4f}, {ex_hi:+.4f}]) on the "
            f"student's own state distribution. Purchase rate "
            f"{fidelity['purchase_rate']['teacher']:.4f} -> "
            f"{fidelity['purchase_rate']['student']:.4f}, pair stability "
            f"{fidelity['pair_stability']['teacher']:.4f} -> "
            f"{fidelity['pair_stability']['student']:.4f}."
        ),
        "decision_implication": "N/A - infrastructure phase, no business decision",
        "next_experiment": "Phase 9b — LLM agents against the trained policy",
    })
    print(f"\n  Wrote {RESULTS_ROOT}\n")
    return 0


def plot(offline, teacher_data, student_data, d_offline, d_shadow, drift,
         fidelity, ex_lo_p, ex_hi_p) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(15.5, 4.4))
    i_p = ENCOUNTER_FIELDS.index("p_teacher")

    ax = axes[0]
    const = offline[offline.hidden == 0]["distance"].iloc[0]
    for soft, colour, label in ((True, "tab:blue", "soft labels p_T(s)"),
                                (False, "tab:orange", "sampled actions a_T")):
        sub = offline[(offline.soft_labels == soft) & (offline.hidden > 0)]
        ax.plot(sub["hidden"] * sub["depth"], sub["distance"], marker="o",
                lw=1.6, color=colour, label=label)
    ax.axhline(const, ls="--", c="0.35", lw=1.2)
    ax.text(20, const + 0.002, f"constant predictor {const:.3f}", fontsize=7.5,
            color="0.35")
    floor = offline[(offline.soft_labels) & (offline.hidden > 0)]["distance"].min()
    ax.axhline(floor, ls=":", c="firebrick", lw=1.2)
    ax.text(20, floor - 0.004, f"floor {floor:.3f} — the hidden taste draw",
            fontsize=7.5, color="firebrick")
    ax.set_xscale("log")
    ax.set_xlabel("model capacity (hidden x depth)")
    ax.set_ylabel(r"$E|p_T - p_\theta|$, held out")
    ax.set_title("Capacity plateaus: the floor is the observation set", fontsize=10)
    ax.legend(fontsize=8)

    ax = axes[1]
    ax.bar([0, 1], [d_offline, d_shadow], color=["tab:blue", "tab:red"], width=0.55)
    ax.set_xticks([0, 1])
    ax.set_xticklabels([r"$D_{offline}$" + "\nteacher's states",
                        r"$D_{shadow}$" + "\nstudent's states"], fontsize=9)
    for x, v in ((0, d_offline), (1, d_shadow)):
        ax.text(x, v + 0.0012, f"{v:.4f}", ha="center", fontsize=9)
    ax.set_ylim(0, max(d_offline, d_shadow) * 1.25)
    ax.set_ylabel(r"$E|p_T - p_\theta|$")
    ax.set_title(f"Same student, {d_shadow / d_offline:.2f}x the error where it goes",
                 fontsize=10)
    ax.errorbar([1], [d_shadow], yerr=[[d_shadow - d_offline - ex_lo_p],
                                       [ex_hi_p - (d_shadow - d_offline)]],
                fmt="none", ecolor="0.25", capsize=4, lw=1.4)

    ax = axes[2]
    shares = {k: v for k, v in fidelity.items() if "verdict" in v}
    names = list(shares)
    diffs = [shares[k]["diff"] * 100 for k in names]
    los = [(shares[k]["diff"] - shares[k]["lo"]) * 100 for k in names]
    his = [(shares[k]["hi"] - shares[k]["diff"]) * 100 for k in names]
    colours = ["seagreen" if shares[k]["verdict"] == "equivalent" else "firebrick"
               for k in names]
    ax.errorbar(diffs, range(len(names)), xerr=[los, his], fmt="o", ms=5,
                capsize=3, ecolor="0.5", lw=0, elinewidth=1.2)
    for i, c in enumerate(colours):
        ax.plot(diffs[i], i, "o", ms=6, color=c)
    ax.axvline(0, c="0.4", lw=1)
    for bound in (-acceptance.MATERIALITY_PP, acceptance.MATERIALITY_PP):
        ax.axvline(bound, ls="--", c="firebrick", lw=1)
    ax.set_yticks(range(len(names)))
    ax.set_yticklabels([n.replace("_", " ") for n in names], fontsize=8)
    ax.invert_yaxis()
    ax.set_xlabel("student − teacher (percentage points)")
    ax.set_title("Closed-loop class-to-tier shares, band is ±5pp", fontsize=10)

    fig.suptitle("Phase 9a — distilling a stochastic teacher, and deploying it",
                 fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(RESULTS_ROOT / "distillation.png", dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    raise SystemExit(main())
