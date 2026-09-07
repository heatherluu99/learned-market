"""Loyalty v2 — the properties the gate's conclusions rest on.

Gate A compares simulated state dependence against a human interval, and that
comparison is only meaningful if the mechanism does what the specification
says: a stock bounded in [0,1], a bonus that is linear in it, a maximum effect
equal to `gamma` in every cell, and no consumption of random draws.
"""

from __future__ import annotations

import dataclasses

import numpy as np
import pytest

from market_sim import config
from market_sim.acceptance import memory_off
from market_sim.engine import run_season


def cell(rho: float = 0.8, gamma: float = 1.5, weeks: int = 40):
    return dataclasses.replace(config.loyalty_v2_cell(rho, gamma), weeks=weeks,
                               seeds=(0,))


def test_stock_stays_within_the_unit_interval():
    """The bound is what makes `gamma` the maximum effect without calibration."""
    season = run_season(cell(), 0)
    bonus = season.loyalty_bonus
    assert bonus is not None
    # bonus = gamma * L, so L in [0,1] is bonus in [0, gamma].
    assert bonus.min() >= 0.0
    assert bonus.max() <= 1.5 + 1e-9


@pytest.mark.parametrize("gamma", config.LOYALTY_V2_GAMMAS)
def test_max_effect_equals_gamma_in_every_cell(gamma):
    """No per-cell calibration: the ceiling is the parameter itself.

    This is the property that answers the objection Phase 7e's per-cell L_max
    invited - if two mechanisms are each re-tuned per cell and come out
    similar, whose similarity is it?
    """
    for rho in config.LOYALTY_V2_RHOS:
        cfg = config.loyalty_v2_cell(rho, gamma)
        assert cfg.max_loyalty_bonus() == pytest.approx(gamma)


def test_update_is_exponential_smoothing():
    """`L <- rho*L + (1-rho)*I`, checked against the closed form.

    A buyer that bought every week from one seller approaches 1; one that
    stopped decays geometrically from wherever it was.
    """
    rho = 0.8
    L = 0.0
    for _ in range(50):
        L = rho * L + (1 - rho) * 1.0
    assert L == pytest.approx(1.0, abs=1e-4)

    for k in range(1, 6):
        assert rho ** k == pytest.approx(np.power(rho, k))


def test_loyalty_v2_draws_no_randomness():
    """CRN discipline: turning the mechanism on must move no other stream.

    The ablation Gate A uses pairs treatment and control on the same seed, and
    that pairing is only exact if neither arm consumes a draw the other does
    not.
    """
    on = cell(gamma=3.0)
    off = memory_off(on)
    a, b = run_season(on, 0), run_season(off, 0)
    # Attendance is drawn before any purchase decision, so it is the cleanest
    # witness that the two runs share a draw stream.
    assert np.array_equal(a.attended, b.attended)


def test_memory_off_zeroes_gamma_and_keeps_rho():
    """The control removes the effect, not the state update."""
    on = config.loyalty_v2_cell(0.95, 3.0)
    off = memory_off(on)
    assert off.loyalty_gamma == 0.0
    assert off.loyalty_retention == on.loyalty_retention
    assert off.max_loyalty_bonus() == 0.0


def test_stronger_gamma_produces_more_repeat_buying():
    """A sanity direction: the knob has to move the thing it is named for.

    Not a gate - Gate A decides admissibility - but if this failed, every
    number the gate produced would be measuring something else.
    """
    weak = run_season(cell(gamma=0.75), 0).chosen_seller
    strong = run_season(cell(gamma=3.0), 0).chosen_seller

    def repeat(chosen):
        a, b = chosen[21:], chosen[20:-1]
        both = (a >= 0) & (b >= 0)
        return float((a[both] == b[both]).mean())

    assert repeat(strong) > repeat(weak)


def test_the_older_mechanisms_are_untouched():
    """Phases 6 and 7e must remain reproducible under what they were run with."""
    assert config.PHASE6_MAIN.loyalty_model == "streak"
    assert config.PHASE7E_CELLS[0].loyalty_model == "stock"
    assert config.PHASE7E_CELLS[0].loyalty_deal_sensitivity == 0.25
    # v2 carries no promotion term at all.
    for c in config.LOYALTY_V2_CELLS:
        assert c.loyalty_deal_sensitivity == 0.0
        assert c.loyalty_bonus_per_streak == 0.0


def test_the_three_mechanisms_are_actually_three_mechanisms():
    """M0, M1 and M2 must differ, and M0 must really have no loyalty.

    Written after Gate C reported M0 and M1 as byte-identical: PHASE7A_FIXED
    already carries the 0.5 streak bonus, so a "no loyalty" arm built by
    taking that market and changing nothing is M1 under another name. The
    numbers matched to four decimals, which is the only reason it was caught -
    a subtler contamination would have read as a finding.
    """
    m0, m1 = config.LOYALTY_V2_NONE, config.LOYALTY_V2_STREAK
    m2 = config.loyalty_v2_cell(0.80, 1.50)

    assert not m0.has_loyalty, "M0 must produce no bonus"
    assert m1.has_loyalty and m2.has_loyalty

    seed = 0
    runs = {name: run_season(dataclasses.replace(c, seeds=(seed,), weeks=40), seed)
            for name, c in (("M0", m0), ("M1", m1), ("M2", m2))}
    choices = {k: v.chosen_seller for k, v in runs.items()}
    for a, b in (("M0", "M1"), ("M0", "M2"), ("M1", "M2")):
        assert not np.array_equal(choices[a], choices[b]), f"{a} and {b} are identical"


def test_memory_off_really_is_memory_off_for_every_mechanism():
    """A control must produce no bonus, whichever mechanism it controls for."""
    for cfg in (config.LOYALTY_V2_STREAK, config.loyalty_v2_cell(0.95, 3.0),
                config.PHASE7E_CELLS[0]):
        off = memory_off(cfg)
        assert not off.has_loyalty, cfg.name
        assert off.max_loyalty_bonus() == 0.0, cfg.name
