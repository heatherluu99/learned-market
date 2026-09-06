"""Run Phase 9c — which environment characteristics suppress divergence?

9b established that teacher entropy governs error amplification exactly, and
that amplification alone does not carry through to material behavioural
divergence. What sits between them is the environment. 9a named two suspects
and could not separate them: a hard budget wall that closes most of the action
space regardless of policy, and a season-long preference draw that pulls a
wandering buyer back toward the same stalls.

Removed one at a time and then together, at the sharpest entropy 9b measured.
See docs/phase_specifications.md, Phase 9c.

    python experiments/phase9c/run_phase9c.py
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
from market_sim.config import PHASE6_MAIN, PHASE9C_CELLS  # noqa: E402
from market_sim.engine import ENCOUNTER_FIELDS, run_season  # noqa: E402

RESULTS_ROOT = REPO_ROOT / "results" / "phase9c"
LOG_PATH = REPO_ROOT / "experiment_log.csv"

TRAIN_SEEDS = tuple(range(1000, 1060))
HELD_OUT_SEEDS = tuple(range(200, 224))
EVAL_SEEDS = tuple(range(30))
CALIBRATION_SEEDS = tuple(range(300, 306))
CAPACITIES = ((64, 2, 40), (128, 3, 40), (256, 3, 80))

RESEARCH_QUESTION = (
    "Which environment characteristics suppress the trajectory divergence that "
    "imitation error would otherwise produce - the budget wall, the season-long "
    "preference draw, or neither?"
)


def label_of(cfg) -> str:
    wall = "wall" if cfg.buyer_classes[0].budget_per_visit < 6.0 else "OPEN"
    taste = "weekly" if cfg.weekly_preference else "fixed"
    return f"tau={cfg.teacher_temperature:g}  budget={wall}  taste={taste}"


def main() -> int:
    commit = experiment_log.git_commit(REPO_ROOT)
    RESULTS_ROOT.mkdir(parents=True, exist_ok=True)
    i_p = ENCOUNTER_FIELDS.index("p_teacher")
    i_a = ENCOUNTER_FIELDS.index("p_acting")

    print("\n=== Phase 9c — stabilizer ablation ===")
    print(f"  {RESEARCH_QUESTION}\n")
    target = buyer.mean_purchase_probability(PHASE6_MAIN, CALIBRATION_SEEDS)
    print(f"  Every cell's offset is re-solved to hold the mean purchase "
          f"probability at {target:.4f},\n  so an ablation opens the action space "
          f"without also changing how much buying happens.\n")

    rows = []
    print(f"  {'cell':40s} {'H':>6s} {'floor':>7s} {'R':>6s} {'D_off':>7s} "
          f"{'D_sha':>7s} {'ratio':>6s} {'drift':>7s} {'behav':>7s} {'gate':>5s}")
    for base in PHASE9C_CELLS:
        cfg = buyer.calibrate_offset(base, target, CALIBRATION_SEEDS)
        level = buyer.mean_purchase_probability(cfg, CALIBRATION_SEEDS)
        train = buyer.encounters(cfg, TRAIN_SEEDS)
        held = buyer.encounters(cfg, HELD_OUT_SEEDS)
        entropy = buyer.teacher_entropy_bits(held)
        noise = buyer.intrinsic_noise(held)
        constant = np.full(len(held), train[:, i_p].mean())

        fits = []
        for hidden, depth, epochs in CAPACITIES:
            candidate = buyer.train(train, hidden=hidden, depth=depth, epochs=epochs)
            prediction = buyer.predict(candidate, held)
            fits.append((f"{hidden}x{depth}", candidate, prediction,
                         buyer.policy_distance(held, prediction)))
        floor = min(d for *_, d in fits)

        net = None
        for name, candidate, prediction, distance in fits:
            checks = acceptance.evaluate_phase9a_offline(
                distance=distance, floor=floor,
                calibration=buyer.calibration(held, prediction),
                log_loss=buyer.log_loss(held, prediction),
                constant_log_loss=buyer.log_loss(held, constant),
                entropy_floor=buyer.entropy_floor(held))
            if all(c.passed for c in checks):
                net, pred, criteria, capacity = candidate, prediction, checks, name
                break
        if net is None:
            name, net, pred, _ = min(fits, key=lambda f: f[3])
            capacity = f"{name} (failed)"
            criteria = acceptance.evaluate_phase9a_offline(
                distance=buyer.policy_distance(held, pred), floor=floor,
                calibration=buyer.calibration(held, pred),
                log_loss=buyer.log_loss(held, pred),
                constant_log_loss=buyer.log_loss(held, constant),
                entropy_floor=buyer.entropy_floor(held))
        gate = all(c.passed for c in criteria)

        recording = dataclasses.replace(cfg, record_encounters=True)
        deployed = dataclasses.replace(recording, buyer_policy=buyer.as_engine_policy(net))
        teacher_runs = [run_season(recording, s) for s in EVAL_SEEDS]
        student_runs = [run_season(deployed, s) for s in EVAL_SEEDS]

        off = np.array([buyer.policy_distance(np.asarray(s.encounters),
                                              buyer.predict(net, np.asarray(s.encounters)))
                        for s in teacher_runs])
        sha = np.array([float(np.abs(np.asarray(s.encounters)[:, i_p]
                                     - np.asarray(s.encounters)[:, i_a]).mean())
                        for s in student_runs])
        excess, ex_lo, ex_hi = acceptance.mean_difference_ci(sha, off)

        teacher_data = np.asarray([e for s in teacher_runs for e in s.encounters])
        student_data = np.asarray([e for s in student_runs for e in s.encounters])
        drift = acceptance.state_drift(
            teacher_data, student_data,
            {f: ENCOUNTER_FIELDS.index(f) for f in
             ("streak_here", "purchases_this_week", "spent_this_week", "history_rate")})
        fidelity = acceptance.trajectory_fidelity(teacher_runs, student_runs, cfg)
        shares = {k: v for k, v in fidelity.items() if "verdict" in v}
        behavioural = max(abs(v["diff"]) for v in shares.values()) * 100

        distance = buyer.policy_distance(held, pred)
        rows.append({
            "cell": cfg.name, "label": label_of(base),
            "temperature": base.teacher_temperature,
            "budget_wall": base.buyer_classes[0].budget_per_visit < 6.0,
            "fixed_preference": not base.weekly_preference,
            "entropy_bits": entropy, "intrinsic_noise": noise, "level": level,
            "floor": floor, "distance": distance, "R": distance / noise,
            "capacity": capacity, "gate": gate,
            "d_offline": float(off.mean()), "d_shadow": float(sha.mean()),
            "amplification": float(sha.mean() / off.mean()),
            "excess": excess, "excess_lo": ex_lo, "excess_hi": ex_hi,
            "state_drift": float(np.mean(list(drift.values()))),
            "behavioural_divergence_pp": behavioural,
            "shares_equivalent": sum(v["verdict"] == "equivalent" for v in shares.values()),
            "n_shares": len(shares),
            "worst_share": max(shares, key=lambda k: abs(shares[k]["diff"])),
        })
        r = rows[-1]
        print(f"  {r['label']:40s} {entropy:6.3f} {floor:7.4f} {r['R']:6.1%} "
              f"{r['d_offline']:7.4f} {r['d_shadow']:7.4f} {r['amplification']:6.2f} "
              f"{r['state_drift']:7.4f} {behavioural:6.2f}pp "
              f"{'PASS' if gate else 'FAIL':>5s}")

    frame = pd.DataFrame(rows)
    reference, baseline = frame.iloc[0], frame.iloc[1]
    print(f"\n  Gate 9a: {int(frame['gate'].sum())}/{len(frame)} cells pass, so no "
          f"cell's divergence is\n  simply an undertrained student.")
    print(f"  Level held at {frame['level'].min():.4f}-{frame['level'].max():.4f} "
          f"against a target of {target:.4f}.")

    print(f"\n  Against the low-entropy baseline (both stabilizers on):")
    for _, r in frame.iloc[2:].iterrows():
        print(f"    {r['label']:40s} behavioural {baseline['behavioural_divergence_pp']:5.2f} "
              f"-> {r['behavioural_divergence_pp']:5.2f} pp   "
              f"amplification {baseline['amplification']:.2f} -> {r['amplification']:.2f}   "
              f"{int(r['shares_equivalent'])}/{int(r['n_shares'])} shares equivalent")

    frame.to_csv(RESULTS_ROOT / "cells.csv", index=False)
    plot(frame)

    worst = frame.loc[frame["behavioural_divergence_pp"].idxmax()]
    experiment_log.append_row(LOG_PATH, {
        "experiment_id": "phase9c_stabilizers", "git_commit": commit,
        "config_file": "src/market_sim/config.py::PHASE9C_CELLS",
        "phase": 9,
        "seed": (f"train {TRAIN_SEEDS[0]}-{TRAIN_SEEDS[-1]}, held-out "
                 f"{HELD_OUT_SEEDS[0]}-{HELD_OUT_SEEDS[-1]}, deploy 0-29"),
        "n_buyers": PHASE6_MAIN.n_buyers, "n_sellers": PHASE6_MAIN.n_sellers,
        "model_used": "learned_policy", "decision_type": "N/A",
        "human_benchmark_id": "N/A", "human_benchmark_status": "not_applicable",
        "synthetic_cost_usd": "N/A", "synthetic_latency_seconds": "N/A",
        "research_question": RESEARCH_QUESTION,
        "changed_mechanism": (
            "the budget wall (Poor's budget 3.0 -> 8.0) and season-long fixed "
            "preference (redrawn weekly) removed one at a time and together, at "
            "the sharpest teacher entropy Phase 9b measured"
        ),
        "transaction_count": "N/A",
        "participation_rate": round(float(frame["level"].mean()), 4),
        "result_summary": (
            f"Low-entropy baseline: amplification {baseline['amplification']:.2f}x, "
            f"behavioural {baseline['behavioural_divergence_pp']:.2f} pp. "
            + "; ".join(
                f"{r['label']}: {r['behavioural_divergence_pp']:.2f} pp, "
                f"{int(r['shares_equivalent'])}/{int(r['n_shares'])} equivalent"
                for _, r in frame.iloc[2:].iterrows()
            )
            + f". Worst anywhere: {worst['behavioural_divergence_pp']:.2f} pp in "
            f"{worst['label']}. {int(frame['gate'].sum())}/{len(frame)} cells clear "
            f"Gate 9a."
        ),
        "decision_implication": "N/A - infrastructure phase, no business decision",
        "next_experiment": "Phase 9d — LLM agents against the trained policy",
    })
    print(f"\n  Wrote {RESULTS_ROOT}\n")
    return 0


def plot(frame) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(15.5, 4.6))
    labels = [l.replace("  ", "\n") for l in frame["label"]]
    colours = ["0.45"] + ["tab:blue", "tab:orange", "tab:green", "tab:red"]

    for ax, (col, title, band) in zip(axes, (
        ("amplification", r"Error amplification  $D_{shadow}/D_{offline}$", None),
        ("state_drift", "State drift the student causes", None),
        ("behavioural_divergence_pp", "Behavioural divergence (pp)",
         acceptance.MATERIALITY_PP),
    )):
        ax.barh(range(len(frame)), frame[col], color=colours, height=0.62)
        ax.set_yticks(range(len(frame)))
        ax.set_yticklabels(labels, fontsize=7.5)
        ax.invert_yaxis()
        if col == "amplification":
            ax.axvline(1.0, ls=":", c="0.5", lw=1)
        if band is not None:
            ax.axvspan(0, band, color="seagreen", alpha=0.07)
            ax.axvline(band, ls="--", c="firebrick", lw=1.2)
            ax.text(band * 0.98, len(frame) - 0.4, f"±{band:g} pp",
                    fontsize=7.5, color="firebrick", ha="right")
            ax.set_xlim(0, max(band * 1.15, frame[col].max() * 1.15))
        for i, v in enumerate(frame[col]):
            ax.text(v, i, f"  {v:.2f}", va="center", fontsize=7.5)
        ax.set_title(title, fontsize=10)

    fig.suptitle("Phase 9c — persistence carries the divergence rather than "
                 "suppressing it", fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.savefig(RESULTS_ROOT / "stabilizers.png", dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    raise SystemExit(main())
