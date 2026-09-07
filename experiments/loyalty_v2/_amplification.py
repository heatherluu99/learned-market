"""The Gate B3 amplification measurement, shared so Gate C runs identical code.

Extracted rather than copied. Gate C compares mechanisms against numbers Gate
B3 produced, and a second implementation that drifted by a detail would make
that comparison meaningless in a way nothing would flag.
"""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from market_sim import acceptance, buyer  # noqa: E402
from market_sim.engine import ENCOUNTER_FIELDS, run_season  # noqa: E402

TRAIN_SEEDS = tuple(range(1000, 1060))
HELD_OUT_SEEDS = tuple(range(200, 224))
EVAL_SEEDS = tuple(range(30))
CALIBRATION_SEEDS = tuple(range(300, 306))
CAPACITIES = ((64, 2, 40), (128, 3, 40), (256, 3, 80))


def measure(base, target: float) -> dict:
    """Distil a buyer policy for one cell and return its amplification.

    `target` is the mean purchase probability every cell is held at, so a
    mechanism cannot move amplification by moving how much buying happens.
    """
    i_p = ENCOUNTER_FIELDS.index("p_teacher")
    i_a = ENCOUNTER_FIELDS.index("p_acting")

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
    gate = not capacity.endswith("(failed)")

    recording = dataclasses.replace(cfg, record_encounters=True)
    deployed = dataclasses.replace(recording, buyer_policy=buyer.as_engine_policy(net))
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

    return {
        "entropy_bits": entropy, "intrinsic_noise": noise,
        "distance": distance, "R": distance / noise,
        "capacity": capacity, "gate": bool(gate),
        "d_offline": float(off.mean()), "d_shadow": float(sha.mean()),
        "amplification": float(sha.mean() / off.mean()),
        "excess": excess, "excess_lo": ex_lo, "excess_hi": ex_hi,
    }
