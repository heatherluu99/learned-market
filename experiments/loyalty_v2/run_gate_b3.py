"""Loyalty v2, Gate B3 — amplification as A(R, rho, gamma).

Phase 9c concluded that amplification goes as `R x state persistence`, but
persistence had no name there: it was whatever the budget wall and the
season-long preference draw happened to supply. Loyalty v2 names it. `rho` is
how long memory lasts and `gamma` is how hard it pushes, so 9c's qualitative
statement becomes a measurable surface.

Pre-registered signs, fixed before this ran:

    dA/drho > 0        longer memory amplifies more
    dA/dgamma > 0      stronger memory amplifies more
    d2A/(dR drho) > 0  and the two reinforce: when imitation error is larger
                       relative to the teacher's own noise, persistence should
                       cost disproportionately more

`R` is varied by teacher temperature, which 9b established governs entropy and
therefore amplification, giving a 3 x 3 x 2 factorial. Every cell's sigmoid
offset is re-solved to hold the mean purchase probability at the no-loyalty
market's level, so loyalty changes *who* is bought from and not *how much* -
otherwise gamma would move amplification through the purchase rate.
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

from market_sim import acceptance, buyer, config, experiment_log  # noqa: E402
from market_sim.engine import ENCOUNTER_FIELDS, run_season  # noqa: E402

RESULTS_ROOT = REPO_ROOT / "results" / "loyalty_v2"
LOG_PATH = REPO_ROOT / "experiment_log.csv"

TRAIN_SEEDS = tuple(range(1000, 1060))
HELD_OUT_SEEDS = tuple(range(200, 224))
EVAL_SEEDS = tuple(range(30))
CALIBRATION_SEEDS = tuple(range(300, 306))
CAPACITIES = ((64, 2, 40), (128, 3, 40), (256, 3, 80))

#: Two temperatures, not 9b's full ladder. 9b established the entropy-to-
#: amplification relation itself; this only needs R to take two values so the
#: interaction with rho is estimable.
TEMPERATURES = (1.0, 0.5)

RESEARCH_QUESTION = (
    "Does trajectory amplification increase with buyer memory persistence and "
    "strength, and does persistence cost disproportionately more when "
    "imitation error is larger relative to the teacher's own noise?"
)


def main() -> int:
    commit = experiment_log.git_commit(REPO_ROOT)
    RESULTS_ROOT.mkdir(parents=True, exist_ok=True)
    i_p = ENCOUNTER_FIELDS.index("p_teacher")
    i_a = ENCOUNTER_FIELDS.index("p_acting")

    print("\n=== Loyalty v2, Gate B3 — amplification A(R, rho, gamma) ===")
    print(f"  {RESEARCH_QUESTION}\n")
    print("  Pre-registered: dA/drho > 0, dA/dgamma > 0, d2A/(dR drho) > 0\n")

    # Phase 7a's own purchase level. That market has streak loyalty on, so
    # this is NOT a no-loyalty level - it is a common anchor, and what matters
    # is that every cell is held to the same number rather than which number.
    # Holding it means gamma cannot move amplification by moving how much
    # buying happens.
    target = buyer.mean_purchase_probability(config.PHASE7A_FIXED, CALIBRATION_SEEDS)
    print(f"  Purchase level held at {target:.4f} (Phase 7a's own level)\n")

    rows = []
    print(f"  {'cell':28s} {'tau':>5s} {'H':>6s} {'R':>6s} {'D_off':>7s} "
          f"{'D_sha':>7s} {'A':>6s} {'gate':>5s}")
    for tau in TEMPERATURES:
        for cell in config.LOYALTY_V2_CELLS:
            base = dataclasses.replace(cell, teacher_temperature=tau)
            cfg = buyer.calibrate_offset(base, target, CALIBRATION_SEEDS)
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
                    net, pred, capacity = candidate, prediction, name
                    break
            if net is None:
                name, net, pred, _ = min(fits, key=lambda f: f[3])
                capacity = f"{name} (failed)"
            gate = net is not None and not capacity.endswith("(failed)")

            recording = dataclasses.replace(cfg, record_encounters=True)
            deployed = dataclasses.replace(
                recording, buyer_policy=buyer.as_engine_policy(net))
            teacher_runs = [run_season(recording, s) for s in EVAL_SEEDS]
            student_runs = [run_season(deployed, s) for s in EVAL_SEEDS]

            off = np.array([
                buyer.policy_distance(np.asarray(s.encounters),
                                      buyer.predict(net, np.asarray(s.encounters)))
                for s in teacher_runs])
            sha = np.array([
                float(np.abs(np.asarray(s.encounters)[:, i_p]
                             - np.asarray(s.encounters)[:, i_a]).mean())
                for s in student_runs])
            excess, ex_lo, ex_hi = acceptance.mean_difference_ci(sha, off)
            distance = buyer.policy_distance(held, pred)

            rows.append({
                "cell": cell.name, "tau": tau,
                "rho": cell.loyalty_retention, "gamma": cell.loyalty_gamma,
                "primary": cell.loyalty_retention in (0.50, 0.80),
                "entropy_bits": entropy, "intrinsic_noise": noise,
                "distance": distance, "R": distance / noise,
                "capacity": capacity, "gate": bool(gate),
                "d_offline": float(off.mean()), "d_shadow": float(sha.mean()),
                "amplification": float(sha.mean() / off.mean()),
                "excess": excess, "excess_lo": ex_lo, "excess_hi": ex_hi,
            })
            r = rows[-1]
            print(f"  {cell.name:28s} {tau:5.2f} {entropy:6.3f} {r['R']:6.3f} "
                  f"{r['d_offline']:7.4f} {r['d_shadow']:7.4f} "
                  f"{r['amplification']:6.2f} {'yes' if gate else 'NO':>5s}",
                  flush=True)

    frame = pd.DataFrame(rows)
    frame.to_csv(RESULTS_ROOT / "gate_b3.csv", index=False)

    # The three pre-registered signs. Partials are taken as OLS slopes across
    # the factorial rather than differences of two cells, so every cell
    # contributes and a single noisy one cannot decide a sign.
    print("\n  Pre-registered signs:")
    signs = {}
    for name, col in (("dA/drho", "rho"), ("dA/dgamma", "gamma")):
        slope = np.polyfit(frame[col], frame["amplification"], 1)[0]
        signs[name] = float(slope)
        print(f"    {name:18s} {slope:+8.4f}  "
              f"{'as registered' if slope > 0 else 'AGAINST registration'}")
    # Interaction: does the rho slope steepen as R rises? Fitted within each
    # temperature and compared, since tau is what moves R.
    by_tau = {}
    for tau, sub in frame.groupby("tau"):
        by_tau[tau] = (float(np.polyfit(sub["rho"], sub["amplification"], 1)[0]),
                       float(sub["R"].mean()))
    hi_R = max(by_tau, key=lambda t: by_tau[t][1])
    lo_R = min(by_tau, key=lambda t: by_tau[t][1])
    interaction = by_tau[hi_R][0] - by_tau[lo_R][0]
    signs["d2A/dRdrho"] = interaction
    print(f"    {'d2A/dRdrho':18s} {interaction:+8.4f}  "
          f"(rho slope {by_tau[lo_R][0]:+.4f} at R={by_tau[lo_R][1]:.3f} -> "
          f"{by_tau[hi_R][0]:+.4f} at R={by_tau[hi_R][1]:.3f})  "
          f"{'as registered' if interaction > 0 else 'AGAINST registration'}")

    plot(frame)
    n_gate = int(frame["gate"].sum())
    print(f"\n  {n_gate}/{len(frame)} cells passed the 9a offline gate.")

    experiment_log.append_row(LOG_PATH, {
        "experiment_id": "loyaltyv2_gate_b3_amplification",
        "git_commit": commit,
        "config_file": "experiments/loyalty_v2/run_gate_b3.py",
        "phase": 10.5,
        "seed": f"{len(TRAIN_SEEDS)} train, {len(HELD_OUT_SEEDS)} held out, "
                f"{len(EVAL_SEEDS)} eval",
        "n_buyers": sum(b.count for b in config.PHASE7A_FIXED.buyer_classes),
        "n_sellers": sum(s.count for s in config.PHASE7A_FIXED.seller_classes),
        "model_used": "distilled buyer policy over relationship loyalty (M2)",
        "decision_type": "purchase",
        "human_benchmark_id": "N/A - internal amplification measurement",
        "synthetic_cost_usd": 0.0,
        "synthetic_latency_seconds": 0.0,
        "research_question": RESEARCH_QUESTION,
        "changed_mechanism": (
            "Phase 9c's qualitative 'amplification ~ R x state persistence' "
            "measured as a surface A(R, rho, gamma) over a 3x3x2 factorial, "
            "with persistence a named parameter rather than a property of the "
            "environment"
        ),
        "transaction_count": len(frame) * len(EVAL_SEEDS),
        "human_benchmark_status": "not_compared",
        "participation_rate": f"purchase level held at {target:.4f}",
        "result_summary": (
            "; ".join(f"{k} {v:+.4f}" for k, v in signs.items())
            + f". Amplification {frame['amplification'].min():.2f} to "
              f"{frame['amplification'].max():.2f}; {n_gate}/{len(frame)} passed "
              f"the offline gate."
        ),
        "decision_implication": (
            "Whether buyer memory persistence is a lever on trajectory "
            "divergence, which decides if loyalty specification matters for "
            "downstream imitation work"
        ),
        "next_experiment": "Loyalty v2 Gate C - mechanism robustness M0/M1/M2",
    })
    print(f"\n  Wrote {RESULTS_ROOT}\n")
    return 0


def plot(frame) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(16, 4.4))

    ax = axes[0]
    for (tau, gamma), sub in frame.groupby(["tau", "gamma"]):
        ax.plot(sub["rho"], sub["amplification"], marker="o",
                ls="-" if tau == 1.0 else "--",
                label=f"tau={tau:g}, gamma={gamma:g}")
    ax.set_xlabel("rho — memory retention")
    ax.set_ylabel(r"amplification  $D_{shadow}/D_{offline}$")
    ax.set_title("Does longer memory amplify more?", fontsize=10)
    ax.legend(fontsize=6.5)

    ax = axes[1]
    for (tau, rho), sub in frame.groupby(["tau", "rho"]):
        ax.plot(sub["gamma"], sub["amplification"], marker="o",
                ls="-" if tau == 1.0 else "--",
                label=f"tau={tau:g}, rho={rho:g}")
    ax.set_xlabel("gamma — loyalty strength")
    ax.set_ylabel("amplification")
    ax.set_title("Does stronger memory amplify more?", fontsize=10)
    ax.legend(fontsize=6.5)

    ax = axes[2]
    for tau, sub in frame.groupby("tau"):
        ax.scatter(sub["R"], sub["amplification"], label=f"tau = {tau:g}",
                   s=40 + 60 * (sub["rho"] - 0.45))
    ax.set_xlabel(r"$R$ — imitation error relative to intrinsic noise")
    ax.set_ylabel("amplification")
    ax.set_title("Marker size is rho", fontsize=10)
    ax.legend(fontsize=7)

    fig.suptitle("Loyalty v2 Gate B3 — amplification as a surface over "
                 "memory persistence and strength", fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    fig.savefig(RESULTS_ROOT / "gate_b3.png", dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    raise SystemExit(main())
