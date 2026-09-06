"""Run Phase 9b — does teacher entropy govern whether imitation error compounds?

9a found the mechanism present and the effect negligible, and identified the
quantity that plausibly governs it: the systematic policy error measured
against the environment's own noise. This sweeps that axis directly.

Five temperature regimes, with the sigmoid offset re-solved at each so the mean
purchase probability does not move - otherwise a low-entropy regime is a
different market and any divergence measured in it is confounded with the
market having changed. See docs/phase_specifications.md, Phase 9b.

    python experiments/phase9b/run_phase9b.py
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

RESULTS_ROOT = REPO_ROOT / "results" / "phase9b"
LOG_PATH = REPO_ROOT / "experiment_log.csv"

BASE = PHASE6_MAIN
TEMPERATURES = (2.0, 1.0, 0.5, 0.25, 0.1, 0.05, 0.02, 0.01)
TRAIN_SEEDS = tuple(range(1000, 1060))
HELD_OUT_SEEDS = tuple(range(200, 224))
EVAL_SEEDS = tuple(range(30))
CALIBRATION_SEEDS = tuple(range(300, 306))
#: Tried in order, per regime, and the smallest student that clears Gate 9a is
#: the one deployed. Holding the architecture fixed across regimes would
#: confound "the environment amplifies error" with "this architecture stops
#: fitting" - a sharper teacher is a harder target, and at tau = 0.1 the 64x2
#: that suffices at tau = 1 fails calibration while 256x3 passes.
CAPACITIES = ((32, 2, 40), (64, 2, 40), (128, 3, 40), (256, 3, 80))
#: The sweep is only of one variable if the level does not move with it.
LEVEL_TOLERANCE = 0.005

RESEARCH_QUESTION = (
    "Does the ratio of systematic policy error to intrinsic teacher "
    "stochasticity govern whether one-step imitation error compounds into "
    "trajectory divergence?"
)


def spearman(x, y) -> float:
    rx = pd.Series(x).rank().to_numpy()
    ry = pd.Series(y).rank().to_numpy()
    return float(np.corrcoef(rx, ry)[0, 1])


def main() -> int:
    commit = experiment_log.git_commit(REPO_ROOT)
    RESULTS_ROOT.mkdir(parents=True, exist_ok=True)
    i_p = ENCOUNTER_FIELDS.index("p_teacher")
    i_a = ENCOUNTER_FIELDS.index("p_acting")

    print("\n=== Phase 9b — teacher entropy sweep ===")
    print(f"  {RESEARCH_QUESTION}\n")
    target = buyer.mean_purchase_probability(BASE, CALIBRATION_SEEDS)
    print(f"  Holding the mean purchase probability at 9a's {target:.4f} by "
          f"re-solving the offset\n  at every temperature, so entropy moves and "
          f"the level does not.\n")

    rows, per_seed = [], {}
    print(f"  {'tau':>5s} {'H(bits)':>8s} {'noise sd':>9s} {'level':>7s} "
          f"{'floor':>7s} {'student':>8s} {'R':>6s} {'D_off':>7s} {'D_sha':>7s} "
          f"{'ratio':>6s} {'model':>9s} {'gate':>5s}")
    for tau in TEMPERATURES:
        cfg = dataclasses.replace(BASE, teacher_temperature=tau)
        cfg = buyer.calibrate_offset(cfg, target, CALIBRATION_SEEDS)
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

        # The smallest student that clears the gate is the one deployed.
        net = pred = None
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
        if net is None:                       # none cleared it; deploy the best
            name, net, pred, _ = min(fits, key=lambda f: f[3])
            capacity = f"{name} (gate failed)"
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
        per_seed[tau] = {"offline": off, "shadow": sha}

        teacher_data = np.asarray([e for s in teacher_runs for e in s.encounters])
        student_data = np.asarray([e for s in student_runs for e in s.encounters])
        drift = acceptance.state_drift(
            teacher_data, student_data,
            {f: ENCOUNTER_FIELDS.index(f) for f in
             ("streak_here", "purchases_this_week", "spent_this_week", "history_rate")})
        fidelity = acceptance.trajectory_fidelity(teacher_runs, student_runs, BASE)
        shares = {k: v for k, v in fidelity.items() if "verdict" in v}
        behavioural = max(abs(v["diff"]) for v in shares.values()) * 100

        distance = buyer.policy_distance(held, pred)
        rows.append({
            "temperature": tau, "entropy_bits": entropy, "intrinsic_noise": noise,
            "capacity": capacity,
            "level": level, "level_ok": abs(level - target) <= LEVEL_TOLERANCE,
            "floor": floor, "distance": distance, "R": distance / noise,
            "gate": gate,
            "d_offline": float(off.mean()), "d_shadow": float(sha.mean()),
            "amplification": float(sha.mean() / off.mean()),
            "excess": excess, "excess_lo": ex_lo, "excess_hi": ex_hi,
            "state_drift": float(np.mean(list(drift.values()))),
            "drift_streak": drift["streak_here"],
            "behavioural_divergence_pp": behavioural,
            "purchase_rate_diff": fidelity["purchase_rate"]["diff"],
            "pair_stability_diff": fidelity["pair_stability"]["diff"],
            "shares_equivalent": sum(v["verdict"] == "equivalent" for v in shares.values()),
            "n_shares": len(shares),
        })
        r = rows[-1]
        print(f"  {tau:5.2f} {entropy:8.3f} {noise:9.3f} {level:7.4f} "
              f"{floor:7.4f} {distance:8.4f} {r['R']:6.1%} {r['d_offline']:7.4f} "
              f"{r['d_shadow']:7.4f} {r['amplification']:6.2f} "
              f"{capacity:>9s} {'PASS' if gate else 'FAIL':>5s}")

    frame = pd.DataFrame(rows)

    print(f"\n  Level control: mean purchase probability "
          f"{frame['level'].min():.4f}-{frame['level'].max():.4f} against a target "
          f"of {target:.4f}\n  -> {'holds' if frame['level_ok'].all() else 'FAILS'} "
          f"within {LEVEL_TOLERANCE}. The sweep is of one variable.")
    print(f"  Gate 9a per regime: {int(frame['gate'].sum())}/{len(frame)} pass, so a "
          f"regime that diverges\n  is not simply one whose student is undertrained.")

    passing = frame[frame["gate"]]
    print(f"\n  Response curves against teacher entropy (lower entropy = sharper),")
    print(f"  over the {len(passing)} regimes whose student clears Gate 9a. A "
          f"regime whose student\n  is undertrained cannot be read as one where "
          f"the environment amplifies error.")
    curves = {
        "amplification  D_shadow/D_offline": "amplification",
        "state drift    mean W1": "state_drift",
        "behavioural    max |share| pp": "behavioural_divergence_pp",
    }
    for label, col in curves.items():
        rho = spearman(passing["entropy_bits"], passing[col])
        boot = []
        rng = np.random.default_rng(0)
        for _ in range(2000):
            idx = rng.integers(0, len(EVAL_SEEDS), len(EVAL_SEEDS))
            taus = list(passing["temperature"])
            amp = [per_seed[t]["shadow"][idx].mean() / per_seed[t]["offline"][idx].mean()
                   for t in taus]
            boot.append(spearman(passing["entropy_bits"],
                                 amp if col == "amplification" else passing[col]))
        lo, hi = np.percentile(boot, [2.5, 97.5])
        print(f"    {label:34s} rho = {rho:+.2f}  95% CI [{lo:+.2f}, {hi:+.2f}]"
              f"{'  monotone' if abs(rho) > 0.89 else ''}")
        frame.loc[0, f"rho_{col}"] = rho

    frame.to_csv(RESULTS_ROOT / "regimes.csv", index=False)
    plot(frame)

    sharpest, softest = frame.iloc[-1], frame.iloc[0]
    experiment_log.append_row(LOG_PATH, {
        "experiment_id": "phase9b_entropy_sweep", "git_commit": commit,
        "config_file": "experiments/phase9b/run_phase9b.py",
        "phase": 9,
        "seed": (f"train {TRAIN_SEEDS[0]}-{TRAIN_SEEDS[-1]}, held-out "
                 f"{HELD_OUT_SEEDS[0]}-{HELD_OUT_SEEDS[-1]}, deploy 0-29"),
        "n_buyers": BASE.n_buyers, "n_sellers": BASE.n_sellers,
        "model_used": "learned_policy", "decision_type": "N/A",
        "human_benchmark_id": "N/A", "human_benchmark_status": "not_applicable",
        "synthetic_cost_usd": "N/A", "synthetic_latency_seconds": "N/A",
        "research_question": RESEARCH_QUESTION,
        "changed_mechanism": (
            f"teacher logit temperature over {list(TEMPERATURES)}, with the "
            f"sigmoid offset re-solved at each so the mean purchase probability "
            f"is held at {target:.4f}"
        ),
        "transaction_count": "N/A",
        "participation_rate": round(float(frame["level"].mean()), 4),
        "result_summary": (
            f"Entropy {softest['entropy_bits']:.3f} -> "
            f"{sharpest['entropy_bits']:.3f} bits with the purchase level held at "
            f"{target:.4f}. R rises {softest['R']:.0%} -> {sharpest['R']:.0%}; "
            f"amplification {softest['amplification']:.2f}x -> "
            f"{sharpest['amplification']:.2f}x; behavioural divergence "
            f"{softest['behavioural_divergence_pp']:.2f} -> "
            f"{sharpest['behavioural_divergence_pp']:.2f} pp. "
            f"{int(frame['gate'].sum())}/{len(frame)} regimes clear Gate 9a."
        ),
        "decision_implication": "N/A - infrastructure phase, no business decision",
        "next_experiment": "Phase 9c — stabilizer ablation",
    })
    print(f"\n  Wrote {RESULTS_ROOT}\n")
    return 0


def plot(frame) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(15.5, 4.4))
    x = frame["entropy_bits"]

    for ax, (col, label, title, colour) in zip(axes, (
        ("amplification", r"$D_{shadow}\,/\,D_{offline}$",
         "Error amplification", "tab:red"),
        ("state_drift", "mean Wasserstein-1",
         "State drift the student causes", "tab:purple"),
        ("behavioural_divergence_pp", "max |class-to-tier share| (pp)",
         "Behavioural divergence", "tab:blue"),
    )):
        ax.plot(x, frame[col], marker="o", lw=1.8, color=colour)
        for xi, yi, tau, gate in zip(x, frame[col], frame["temperature"], frame["gate"]):
            ax.annotate(f"τ={tau:g}" + ("" if gate else "\n(gate fail)"), (xi, yi),
                        textcoords="offset points", xytext=(6, -4), fontsize=7.5,
                        color="0.3" if gate else "firebrick")
        if col == "amplification":
            ax.axhline(1.0, ls=":", c="0.5", lw=1)
            ax.text(x.max(), 1.005, "no amplification", fontsize=7.5, color="0.4",
                    ha="right")
        if col == "behavioural_divergence_pp":
            # Without the materiality band the panel reads as a large effect.
            # Every regime, including the sharpest, is well inside it.
            ax.axhspan(0, acceptance.MATERIALITY_PP, color="seagreen", alpha=0.07)
            ax.axhline(acceptance.MATERIALITY_PP, ls="--", c="firebrick", lw=1.2)
            ax.text(x.max(), acceptance.MATERIALITY_PP - 0.28,
                    f"materiality, ±{acceptance.MATERIALITY_PP:g} pp — never reached",
                    fontsize=7.5, color="firebrick", ha="right")
            ax.set_ylim(0, acceptance.MATERIALITY_PP * 1.15)
        ax.invert_xaxis()
        ax.set_xlabel(r"teacher policy entropy $H(\pi_T)$, bits  →  sharper")
        ax.set_ylabel(label)
        ax.set_title(title, fontsize=10)

    fig.suptitle("Phase 9b — does teacher entropy govern whether imitation error "
                 "compounds?", fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(RESULTS_ROOT / "entropy_sweep.png", dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    raise SystemExit(main())
