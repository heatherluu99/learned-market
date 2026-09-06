"""Phase 9a — distilling a stochastic teacher.

The claims that need pinning are about the *measurement*, not the model. That
the student and the teacher are coupled on the same draw, so one-step agreement
is a policy distance rather than an accuracy; that the student is fitted and
scored on exactly the same feature layout; and that the gate rejects the
model which is aggregate-calibrated and conditionally empty.
"""

from __future__ import annotations

import dataclasses

import numpy as np
import pytest

from market_sim import acceptance, buyer
from market_sim.config import PHASE1_MAIN, PHASE6_MAIN
from market_sim.engine import ENCOUNTER_FIELDS, run_season, run_seeds

I_P = ENCOUNTER_FIELDS.index("p_teacher")
I_ACT = ENCOUNTER_FIELDS.index("p_acting")
I_A = ENCOUNTER_FIELDS.index("action")


def _recording():
    return dataclasses.replace(PHASE6_MAIN, record_encounters=True)


def test_recording_is_opt_in_and_changes_nothing():
    assert not PHASE6_MAIN.record_encounters
    assert run_season(PHASE6_MAIN, 0).encounters is None
    plain, recorded = run_season(PHASE6_MAIN, 0), run_season(_recording(), 0)
    assert np.array_equal(plain.chosen_seller, recorded.chosen_seller)
    p1 = run_seeds(PHASE1_MAIN)
    assert float(np.mean([r.participation_rate for r in p1])) == pytest.approx(
        0.8216666666666667, abs=1e-12
    )


def test_only_affordable_encounters_are_recorded():
    """An unaffordable stall is a constraint, not a preference.

    Training on it would teach the student the budget wall, which the engine
    already enforces, and dilute every stratum with a structural zero.
    """
    season = run_season(_recording(), 0)
    data = np.asarray(season.encounters)
    price = data[:, ENCOUNTER_FIELDS.index("price")]
    premium = data[:, ENCOUNTER_FIELDS.index("is_premium")]
    poor = data[:, ENCOUNTER_FIELDS.index("buyer_class_index")] == 0
    # Poor's mean budget is 3.0 against a premium price of 6.0, so essentially
    # no Poor buyer should appear against a premium stall.
    assert (premium[poor] == 1).mean() < 0.01
    assert price.min() > 0


def test_the_acting_probability_is_the_teachers_when_no_policy_is_deployed():
    data = np.asarray(run_season(_recording(), 0).encounters)
    assert np.array_equal(data[:, I_P], data[:, I_ACT])


def test_the_wrapper_and_the_training_matrix_agree_on_feature_order():
    """Two orderings of the same eight columns would fail silently.

    The student would be fitted on one layout and act on another, and the only
    symptom would be a policy that is worse in closed loop than offline - which
    is precisely the effect this phase exists to measure.
    """
    train = buyer.encounters(PHASE6_MAIN, range(1000, 1002))
    net = buyer.train(train, epochs=2, hidden=8, depth=1)
    policy = buyer.as_engine_policy(net)
    columns = [ENCOUNTER_FIELDS.index(f) for f in buyer.OBSERVED]
    for row in train[:25]:
        assert policy(*row[columns]) == pytest.approx(
            buyer.predict(net, row[None, :])[0], abs=1e-6
        )


def test_one_step_agreement_is_the_policy_distance_under_shared_draws():
    """The claim that makes E|p_T - p_theta| a distance and not an accuracy.

    Compared on each buyer's *first* encounter of week 0 - the only point
    guaranteed coupled. Budgets deplete within a week, so one differing
    purchase changes what is affordable at the next stall and the encounter
    sets diverge before week 0 is over. That divergence is the phenomenon the
    phase measures; here it has to be excluded to isolate the coupling.
    """
    train = buyer.encounters(PHASE6_MAIN, range(1000, 1010))
    net = buyer.train(train, epochs=8, hidden=32, depth=2)
    deployed = dataclasses.replace(_recording(), buyer_policy=buyer.as_engine_policy(net))

    def first_of_week_zero(rows):
        rows = rows[rows[:, 0] == 0]
        _, keep = np.unique(rows[:, 1], return_index=True)
        return rows[np.sort(keep)]

    differed, gap, n = 0, 0.0, 0
    for seed in range(6):
        a = first_of_week_zero(np.asarray(run_season(_recording(), seed).encounters))
        b = first_of_week_zero(np.asarray(run_season(deployed, seed).encounters))
        assert np.array_equal(a[:, 1:3], b[:, 1:3])   # same buyer and same stall
        assert np.array_equal(a[:, I_P], b[:, I_P])   # the teacher agrees with itself
        differed += int((a[:, I_A] != b[:, I_A]).sum())
        gap += float(np.abs(a[:, I_P] - b[:, I_ACT]).sum())
        n += len(a)
    # Both are estimates of the same quantity; the sampling error over n
    # coupled Bernoulli comparisons is about 1/sqrt(n).
    assert abs(differed / n - gap / n) < 4 / np.sqrt(n)
    assert gap / n > 0.01, "a student this close would make the test vacuous"


def test_calibration_catches_the_model_that_learned_only_the_marginal():
    """A constant predictor is aggregate-calibrated and conditionally empty."""
    held = buyer.encounters(PHASE6_MAIN, range(200, 206))
    constant = np.full(len(held), held[:, I_P].mean())
    assert abs(constant.mean() - held[:, I_P].mean()) < 0.001   # passes aggregate
    cal = buyer.calibration(held, constant)
    assert max(cal.values()) > 0.2                              # fails stratified
    assert max(cal, key=cal.get) == "loyalty streak"


def test_the_entropy_floor_bounds_the_log_loss_from_below():
    held = buyer.encounters(PHASE6_MAIN, range(200, 204))
    floor = buyer.entropy_floor(held)
    # Scoring with the teacher's own probabilities cannot beat its entropy.
    assert buyer.log_loss(held, held[:, I_P]) >= floor - 1e-9
    assert buyer.log_loss(held, np.full(len(held), held[:, I_P].mean())) > floor


def test_the_gate_requires_all_three_and_rejects_a_constant_predictor():
    ok = acceptance.evaluate_phase9a_offline(
        distance=0.086, floor=0.084,
        calibration={"buyer class": 0.004, "loyalty streak": 0.006},
        log_loss=0.6625, constant_log_loss=0.6904, entropy_floor=0.6424)
    assert all(c.passed for c in ok)

    # Criterion 3 is a share of what is available, not a number of nats. Where
    # the teacher is nearly a coin flip the whole available range is 0.012, and
    # an absolute threshold of 0.02 would be larger than it - which is how
    # Phase 9b's tau = 2.0 regime failed a gate nothing could pass.
    thin = acceptance.evaluate_phase9a_offline(
        distance=0.045, floor=0.045,
        calibration={"buyer class": 0.005},
        log_loss=0.6800, constant_log_loss=0.6857, entropy_floor=0.6739)
    assert thin[2].passed, thin[2].measured
    assert "48%" in thin[2].measured

    # aggregate-calibrated, conditionally empty: criteria 1 and 2 must fail
    constant = acceptance.evaluate_phase9a_offline(
        distance=0.124, floor=0.084,
        calibration={"buyer class": 0.038, "loyalty streak": 0.305},
        log_loss=0.6904, constant_log_loss=0.6904, entropy_floor=0.6424)
    assert [c.passed for c in constant] == [False, False, False]

    # fits well overall but is miscalibrated in one stratum: only 2 fails
    lopsided = acceptance.evaluate_phase9a_offline(
        distance=0.086, floor=0.084,
        calibration={"buyer class": 0.004, "loyalty streak": 0.09},
        log_loss=0.6625, constant_log_loss=0.6904, entropy_floor=0.6424)
    assert [c.passed for c in lopsided] == [True, False, True]


def test_state_drift_is_zero_between_a_distribution_and_itself():
    data = buyer.encounters(PHASE6_MAIN, range(200, 202))
    cols = {"streak_here": ENCOUNTER_FIELDS.index("streak_here")}
    assert acceptance.state_drift(data, data, cols)["streak_here"] == 0.0
    shifted = data.copy()
    shifted[:, cols["streak_here"]] += 1.0
    assert acceptance.state_drift(data, shifted, cols)["streak_here"] == pytest.approx(1.0)


# --------------------------------------------------------------------------
# Phase 9b — the entropy axis
# --------------------------------------------------------------------------


def test_temperature_of_one_is_every_earlier_phase_exactly():
    """The sweep's knob must be inert at its default or Phases 1-9a all move."""
    assert PHASE6_MAIN.teacher_temperature == 1.0
    explicit = dataclasses.replace(PHASE6_MAIN, teacher_temperature=1.0)
    for seed in (0, 3):
        a, b = run_season(PHASE6_MAIN, seed), run_season(explicit, seed)
        assert np.array_equal(a.chosen_seller, b.chosen_seller)
    p1 = run_seeds(PHASE1_MAIN)
    assert float(np.mean([r.participation_rate for r in p1])) == pytest.approx(
        0.8216666666666667, abs=1e-12
    )


@pytest.mark.parametrize("tau,expected", [(0.25, "sharper"), (4.0, "flatter")])
def test_temperature_sharpens_without_reordering_preferences(tau, expected):
    """It changes how decisively a buyer acts, never what it prefers."""
    hot = dataclasses.replace(PHASE6_MAIN, teacher_temperature=tau,
                              record_encounters=True)
    base = np.asarray(run_season(_recording(), 0).encounters)
    other = np.asarray(run_season(hot, 0).encounters)
    # Week 0's first encounter per buyer is coupled, so the two are comparable.
    def first(rows):
        rows = rows[rows[:, 0] == 0]
        _, keep = np.unique(rows[:, 1], return_index=True)
        return rows[np.sort(keep)]
    a, b = first(base), first(other)
    assert np.array_equal(a[:, 1:3], b[:, 1:3])
    # Above and below 0.5 is the preference; distance from 0.5 is the sharpness.
    assert np.array_equal(a[:, I_P] > 0.5, b[:, I_P] > 0.5)
    spread_a = np.abs(a[:, I_P] - 0.5).mean()
    spread_b = np.abs(b[:, I_P] - 0.5).mean()
    assert (spread_b > spread_a) if expected == "sharper" else (spread_b < spread_a)


def test_lower_temperature_lowers_entropy_and_the_intrinsic_noise():
    seeds = range(3)
    previous_h, previous_noise = 1.1, 1.0
    for tau in (1.0, 0.5, 0.2):
        cfg = dataclasses.replace(PHASE6_MAIN, teacher_temperature=tau)
        data = buyer.encounters(cfg, seeds)
        h, noise = buyer.teacher_entropy_bits(data), buyer.intrinsic_noise(data)
        assert h < previous_h and noise < previous_noise
        previous_h, previous_noise = h, noise


def test_the_offset_calibration_holds_the_level_while_entropy_moves():
    """Without it a low-entropy regime is a different market, not a sharper one.

    The confound this rules out is the whole reason the sweep can be read: a
    change in purchase volume would move loyalty, seller profit and entry, and
    any divergence measured against it would be the market having changed.
    """
    seeds = range(4)
    target = buyer.mean_purchase_probability(PHASE6_MAIN, seeds)
    raw = dataclasses.replace(PHASE6_MAIN, teacher_temperature=0.2)
    uncalibrated = buyer.mean_purchase_probability(raw, seeds)
    fixed = buyer.calibrate_offset(raw, target, seeds)
    calibrated = buyer.mean_purchase_probability(fixed, seeds)

    # Stated against the tolerance rather than an absolute: what matters is
    # that the drift calibration removes is an order of magnitude larger than
    # the drift it leaves.
    tolerance = 0.005
    assert abs(uncalibrated - target) > 8 * tolerance
    assert abs(calibrated - target) <= tolerance
    # ... while the entropy stays where the temperature put it
    assert buyer.teacher_entropy_bits(buyer.encounters(fixed, seeds)) < 0.6
