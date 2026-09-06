"""Phase 8 — entry, exit, and the two claims the phase rests on.

The first is that switching the mechanism on moved nothing before it: the
market now allocates fixed slots and draws at slot width, and if that leaks
into Phases 1-7 every validated tag stops reproducing. The second is that the
stratification is *emergent* - that no class label enters any decision - which
is pinned behaviourally rather than asserted.
"""

from __future__ import annotations

import dataclasses

import numpy as np
import pytest

from market_sim import acceptance
from market_sim.config import (
    PHASE1_MAIN,
    PHASE7A_FIXED,
    PHASE8_CELLS,
    phase8_cell,
)
from market_sim.engine import run_season, run_seeds

SEEDS = [0, 1, 7]


def _cell(**kw):
    base = phase8_cell("capital", 10.0)
    return dataclasses.replace(base, **kw) if kw else base


def test_slot_allocation_is_inert_without_entry_and_exit():
    assert not PHASE7A_FIXED.has_entry_exit
    assert PHASE7A_FIXED.n_slots == PHASE7A_FIXED.n_sellers
    assert _cell().n_slots == _cell().max_sellers
    p1 = run_seeds(PHASE1_MAIN)
    assert float(np.mean([r.participation_rate for r in p1])) == pytest.approx(
        0.8216666666666667, abs=1e-12
    )


@pytest.mark.parametrize("seed", SEEDS)
def test_a_market_with_no_spare_slots_reproduces_phase_7(seed):
    """With capacity equal to the starting count, week 0 must be Phase 7's.

    Entry cannot fire without a free slot, so any divergence in the first week
    is the slot machinery leaking rather than the mechanism working.
    """
    narrow = _cell(max_sellers=PHASE7A_FIXED.n_sellers, weeks=PHASE7A_FIXED.weeks)
    a, b = run_season(PHASE7A_FIXED, seed), run_season(narrow, seed)
    assert np.array_equal(a.weeks[0].seller_n_sold, b.weeks[0].seller_n_sold)
    assert np.array_equal(a.chosen_seller[0], b.chosen_seller[0])


@pytest.mark.parametrize("seed", SEEDS)
def test_empty_slots_are_neither_shopped_at_nor_charged_rent(seed):
    season = run_season(_cell(), seed)
    for week, result in enumerate(season.weeks):
        active = season.active[week]
        idle = ~active
        assert result.seller_n_sold[idle].sum() == 0
        assert result.seller_revenue[idle].sum() == 0
        # An empty slot is not a stall anyone declined, and it pays no fixed cost.
        assert np.all(result.seller_profit[idle] == 0.0)
        total = sum(result.blocked_counts.values()) + len(result.transactions)
        assert total == _cell().n_buyers * int(active.sum())


@pytest.mark.parametrize("seed", SEEDS)
def test_the_capital_rule_exits_exactly_when_the_balance_runs_out(seed):
    cfg = _cell()
    season = run_season(cfg, seed)
    # Keyed on firm rather than slot: an entrant can take the seat a departing
    # seller just vacated, so the slot's own `active` flag never goes down.
    balance: dict[int, float] = {}
    for week in range(season.n_weeks - 1):
        here, then = season.firm_id[week], season.firm_id[week + 1]
        for slot in np.flatnonzero(season.active[week]):
            firm = int(here[slot])
            balance[firm] = (balance.get(firm, cfg.seller_endowment)
                             + float(season.weeks[week].seller_profit[slot]))
            survived = firm in set(then[then >= 0].tolist())
            if survived:
                assert balance[firm] > 0, (week, firm, balance[firm])
            else:
                assert balance[firm] <= 0, (week, firm, balance[firm])


@pytest.mark.parametrize("seed", SEEDS)
def test_the_streak_rule_exits_after_three_consecutive_losses(seed):
    cfg = phase8_cell("streak", 10.0)
    season = run_season(cfg, seed)
    streak: dict[int, int] = {}
    for week in range(season.n_weeks - 1):
        here, then = season.firm_id[week], season.firm_id[week + 1]
        alive_next = set(then[then >= 0].tolist())
        for slot in np.flatnonzero(season.active[week]):
            firm = int(here[slot])
            losing = season.weeks[week].seller_profit[slot] < 0
            streak[firm] = streak.get(firm, 0) + 1 if losing else 0
            if firm in alive_next:
                assert streak[firm] < cfg.exit_loss_weeks, (week, firm)
            else:
                assert streak[firm] >= cfg.exit_loss_weeks, (week, firm)


def test_the_market_never_exceeds_its_capacity():
    for cfg in PHASE8_CELLS:
        season = run_season(cfg, 0)
        assert season.active.sum(axis=1).max() <= cfg.max_sellers


@pytest.mark.parametrize("seed", SEEDS)
def test_renaming_the_tiers_changes_nothing_at_all(seed):
    """The emergent claim, tested behaviourally rather than asserted.

    Every numeric parameter is held and only the class *names* are swapped. If
    any decision - entry, exit or purchase - read a class label, the two runs
    would diverge. They must be identical to the last slot.
    """
    cfg = _cell()
    renamed = dataclasses.replace(cfg, seller_classes=tuple(
        dataclasses.replace(c, name={"Slow": "Shigh", "Shigh": "Slow"}[c.name])
        for c in cfg.seller_classes
    ))
    a, b = run_season(cfg, seed), run_season(renamed, seed)
    assert np.array_equal(a.active, b.active)
    assert np.array_equal(a.chosen_seller, b.chosen_seller)
    assert np.allclose(a.profits, b.profits, atol=0, rtol=0)
    assert [e["week"] for e in a.events] == [e["week"] for e in b.events]


@pytest.mark.parametrize("seed", SEEDS)
def test_a_weeks_seller_mix_is_that_weeks_not_the_final_one(seed):
    """The class list is copied per week; aliasing it would rewrite history."""
    season = run_season(_cell(), seed)
    first, last = season.weeks[0], season.weeks[-1]
    assert first.seller_classes is not last.seller_classes
    # slots beyond the starting five are unnamed in week 0 and named later
    starting = PHASE7A_FIXED.n_sellers
    assert all(name == "" for name in first.seller_classes[starting:])
    assert any(name != "" for name in last.seller_classes[starting:])


def test_entrants_copy_an_incumbent_exactly():
    season = run_season(_cell(), 0)
    entries = [e for e in season.events if e["event"] == "entry"]
    assert entries
    prices = {c.price for c in PHASE7A_FIXED.seller_classes}
    for e in entries:
        assert e["price"] in prices  # never an invented configuration
        assert e["tier"] in {c.name for c in PHASE7A_FIXED.seller_classes}
    # every occupancy has its own identity, so a replacement is never mistaken
    # for a survivor
    firms = [e["firm"] for e in entries]
    assert len(firms) == len(set(firms))


def test_the_reference_market_volatility_is_read_from_the_real_counts():
    assert acceptance.RI_DEM_VENDOR_COUNTS == (24, 31, 25, 24, 26)
    assert acceptance.real_market_volatility() == pytest.approx(0.152, abs=0.001)
    assert acceptance.real_market_volatility((10, 10, 10)) == 0.0


def test_phase8_criteria_grade_validity_not_direction():
    cfg = _cell()
    seasons = [run_season(cfg, s) for s in range(6)]
    criteria = acceptance.evaluate_phase8(dataclasses.replace(cfg, seeds=tuple(range(6))),
                                          seasons)
    names = [c.name for c in criteria]
    assert "the market does not go extinct" in names
    assert sum(1 for c in criteria if not c.graded) == 1  # the plausibility flag
    settled = next(c for c in criteria if c.name.startswith("the seller count"))
    assert "verdict is reached" in settled.note
