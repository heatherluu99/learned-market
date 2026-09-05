"""Phase 6 — the week axis, persistent memory, and what must not leak into it.

The distinction this phase turns on is between a market repeated for
statistics and a market repeated as a timeline. Several tests here pin state
that must persist across weeks and state that must not.
"""

from __future__ import annotations

import numpy as np
import pytest

from market_sim.acceptance import (
    evaluate_phase6,
    perturbation_persistence,
    plateau_week,
    shock_metrics,
)
from market_sim.config import (
    PHASE1_MAIN,
    PHASE4_MAIN,
    PHASE6_MAIN,
    PHASE6_NO_LOYALTY,
)
from market_sim.engine import _choice_of_week, run_season, run_season_seeds, run_single

SEEDS = [0, 1, 7, 29]


def test_phases_without_a_week_axis_reject_run_season():
    assert not PHASE4_MAIN.has_weeks
    assert PHASE6_MAIN.has_weeks
    with pytest.raises(ValueError, match="no week axis"):
        run_season(PHASE4_MAIN, 0)


def test_adding_the_week_axis_did_not_move_phase1():
    """The season loop is a separate entry point; run_single is untouched."""
    results = [run_single(PHASE1_MAIN, s) for s in PHASE1_MAIN.seeds]
    assert float(np.mean([r.participation_rate for r in results])) == pytest.approx(
        0.8216666666666667, abs=1e-12
    )


def test_max_loyalty_bonus_equals_the_preference_range():
    """The cap is derived from preference_coef, not tuned.

    Habit can match the strongest possible taste difference and never exceed
    it. If preference_coef or the bonus changes, this must be revisited.
    """
    assert PHASE6_MAIN.max_loyalty_bonus() == pytest.approx(PHASE6_MAIN.preference_coef)
    assert PHASE6_MAIN.loyalty_streak_cap == 3


def test_control_arm_has_no_loyalty_and_is_otherwise_identical():
    assert PHASE6_MAIN.has_loyalty
    assert not PHASE6_NO_LOYALTY.has_loyalty
    assert PHASE6_NO_LOYALTY.buyer_classes == PHASE6_MAIN.buyer_classes
    assert PHASE6_NO_LOYALTY.seller_classes == PHASE6_MAIN.seller_classes
    assert PHASE6_NO_LOYALTY.weeks == PHASE6_MAIN.weeks
    assert PHASE6_NO_LOYALTY.seeds == PHASE6_MAIN.seeds


@pytest.mark.parametrize("seed", SEEDS)
def test_budget_and_inventory_reset_every_week(seed):
    """Weekly resets are what make a week a fresh market session."""
    season = run_season(PHASE6_MAIN, seed)
    starting_inventory = np.array(
        [c.inventory for c in PHASE6_MAIN.seller_classes for _ in range(c.count)]
    )
    budgets = PHASE6_MAIN.buyer_budgets(seed)  # per buyer, not per class
    for week in season.weeks:
        assert (week.seller_n_sold + week.seller_inventory_remaining == starting_inventory).all()
        assert (week.buyer_total_spent <= budgets).all()
        assert week.buyer_budget_remaining.min() >= 0


@pytest.mark.parametrize("seed", SEEDS)
def test_memory_persists_across_weeks_but_absence_does_not_reset_it(seed):
    """A buyer who skips a week keeps their streak, they do not restart at 1."""
    season = run_season(PHASE6_MAIN, seed)
    for w in range(1, season.n_weeks):
        skipped = season.chosen_seller[w] < 0
        assert (season.streaks[w][skipped] == season.streaks[w - 1][skipped]).all()


@pytest.mark.parametrize("seed", SEEDS)
def test_streak_grows_against_the_last_purchase_not_the_last_week(seed):
    """A streak continues across weeks the buyer skipped.

    The comparison is against the buyer's most recent *purchase*, not against
    the previous week: a buyer who bought from X, sat out a week, then bought
    from X again has a streak of 2, not a reset. Comparing against the
    previous week's slot would treat every absence as a switch, which is the
    same confound `pair_stability` avoids in its denominator.
    """
    season = run_season(PHASE6_MAIN, seed)
    assert season.streaks.max() <= season.n_weeks

    n_buyers = season.chosen_seller.shape[1]
    last_choice = np.full(n_buyers, -1)
    last_streak = np.zeros(n_buyers, dtype=int)
    for w in range(season.n_weeks):
        chosen = season.chosen_seller[w]
        for b in range(n_buyers):
            if chosen[b] < 0:
                assert season.streaks[w][b] == last_streak[b]
                continue
            expected = last_streak[b] + 1 if chosen[b] == last_choice[b] else 1
            assert season.streaks[w][b] == expected, (w, b)
            last_choice[b], last_streak[b] = chosen[b], expected


def test_choice_of_week_takes_the_most_purchased_not_the_most_recent():
    """Most-recent would depend on the random stall order that week."""
    assert _choice_of_week([]) == -1
    assert _choice_of_week([3]) == 3
    assert _choice_of_week([1, 2, 2]) == 2  # not 2 by recency - by count
    assert _choice_of_week([2, 2, 1]) == 2
    # Tie: first encountered wins, deterministically.
    assert _choice_of_week([4, 1, 1, 4]) == 4


@pytest.mark.parametrize("seed", SEEDS)
def test_attendance_and_purchase_are_different_quantities(seed):
    """A buyer can show up and buy nothing; conflating them hides that."""
    season = run_season(PHASE6_MAIN, seed)
    assert (season.purchase_rate() <= season.attendance_rate() + 1e-12).all()
    assert season.purchase_rate().mean() < season.attendance_rate().mean()


@pytest.mark.parametrize("seed", SEEDS)
def test_absent_buyers_make_no_purchase_decision(seed):
    """Not shopping is recorded separately from shopping and declining."""
    season = run_season(PHASE6_MAIN, seed)
    for w, week in enumerate(season.weeks):
        absent = int((~season.attended[w]).sum())
        assert week.blocked_counts["did_not_shop"] == absent * PHASE6_MAIN.n_sellers
        assert not any(
            t.buyer_id == b for t in week.transactions
            for b in np.flatnonzero(~season.attended[w])
        )


@pytest.mark.parametrize("seed", SEEDS)
def test_pair_stability_ignores_weeks_a_buyer_did_not_buy(seed):
    """Skipping a week is not a switch; counting it as one would confound
    attendance with loyalty."""
    season = run_season(PHASE6_MAIN, seed)
    stability = season.pair_stability()
    assert np.isnan(stability[0])  # nothing precedes week 0
    assert not np.isnan(stability[1:]).any()
    assert ((stability[1:] >= 0) & (stability[1:] <= 1)).all()


def test_loyalty_raises_stability_above_the_control():
    """The phase's substantive finding, and the one that needs no window."""
    seasons = run_season_seeds(PHASE6_MAIN)
    control = run_season_seeds(PHASE6_NO_LOYALTY)
    loyal = np.mean([np.nanmean(s.pair_stability()[1:]) for s in seasons])
    plain = np.mean([np.nanmean(s.pair_stability()[1:]) for s in control])
    assert loyal > plain


def test_control_stability_is_well_above_chance():
    """Guards the reason a control arm exists at all.

    Popularity concentration and season-long fixed preference produce
    substantial stability with no memory whatsoever, so the raw level must
    never be read as evidence about memory.
    """
    control = run_season_seeds(PHASE6_NO_LOYALTY)
    plain = np.mean([np.nanmean(s.pair_stability()[1:]) for s in control])
    assert plain > 1.0 / PHASE6_MAIN.n_sellers  # far above uniform-random 0.2
    assert plain > 0.25


def test_all_graded_criteria_pass():
    seasons = run_season_seeds(PHASE6_MAIN)
    control = run_season_seeds(PHASE6_NO_LOYALTY)
    criteria = evaluate_phase6(PHASE6_MAIN, seasons, control)
    # purchase rate, memory-vs-control, path dependence, within-season rise
    assert len(criteria) == 4
    assert all(c.passed for c in criteria), [
        (c.name, c.measured) for c in criteria if not c.passed
    ]


def test_plateau_week_is_reported_and_inside_the_season():
    seasons = run_season_seeds(PHASE6_MAIN)
    week = plateau_week(seasons)
    assert week is not None
    assert 1 <= week <= PHASE6_MAIN.weeks


# --- second gate: path dependence and shock recovery ----------------------


def test_perturbation_leaves_the_random_stream_untouched():
    """The butterfly test is only valid if nothing but the memory state moves.

    The attendance draw is made and then overridden, so under memory OFF the
    perturbed run must be bit-identical after the perturbed week - a buyer who
    skipped week 0 has nowhere for that fact to persist.
    """
    import dataclasses

    victim = 40
    base = run_season(PHASE6_NO_LOYALTY, 3)
    shifted = run_season(
        dataclasses.replace(PHASE6_NO_LOYALTY, perturb_buyer=victim, perturb_week=0), 3
    )
    assert not shifted.attended[0, victim]
    assert np.array_equal(base.chosen_seller[1:], shifted.chosen_seller[1:])


def test_perturbation_can_only_move_the_perturbed_buyer_under_memory():
    """Memory ON may diverge - but only for the buyer whose history changed."""
    import dataclasses

    victim = 40
    base = run_season(PHASE6_MAIN, 3)
    shifted = run_season(
        dataclasses.replace(PHASE6_MAIN, perturb_buyer=victim, perturb_week=0), 3
    )
    others = [b for b in range(PHASE6_MAIN.n_buyers) if b != victim]
    assert np.array_equal(
        base.chosen_seller[1:][:, others], shifted.chosen_seller[1:][:, others]
    )


def test_path_dependence_is_absent_as_pre_registered():
    """A three-week-capped memory does not produce trajectory lock-in.

    Recorded as a null rather than engineered away: relaxing the cap to make
    divergence appear would be changing the mechanism after seeing the result,
    and the cap exists so habit cannot override taste.
    """
    victims = (5, 40, 75, 95)
    on = perturbation_persistence(PHASE6_MAIN, victims)
    off = perturbation_persistence(PHASE6_NO_LOYALTY, victims)
    assert off.max() == 0.0           # nowhere for a perturbation to persist
    assert on.mean() == pytest.approx(0.0, abs=1e-9)  # and it does not persist


def test_a_closed_stall_sells_nothing_and_is_counted_separately():
    """The shock is exogenous and one week long; Phase 8 owns entry and exit."""
    import dataclasses

    shocked = run_season(
        dataclasses.replace(PHASE6_MAIN, shock_seller=0, shock_week=12), 0
    )
    assert shocked.weeks[12].seller_n_sold[0] == 0
    assert shocked.weeks[12].blocked_counts["stall_closed"] > 0
    assert shocked.weeks[11].seller_n_sold[0] > 0
    assert shocked.weeks[13].seller_n_sold[0] > 0
    for w, week in enumerate(shocked.weeks):
        if w != 12:
            assert week.blocked_counts["stall_closed"] == 0


def test_memory_does_not_confer_shock_resilience():
    """The second null, and consistent with the first.

    Permanent switching is if anything slightly higher with memory on: a buyer
    pushed off its usual stall starts a fresh streak with the substitute, and
    the mechanism that built the first relationship then holds it in the new
    one.
    """
    import dataclasses

    seeds = tuple(range(10))
    on = shock_metrics(dataclasses.replace(PHASE6_MAIN, seeds=seeds), 0, 12)
    off = shock_metrics(dataclasses.replace(PHASE6_NO_LOYALTY, seeds=seeds), 0, 12)
    assert abs(on["return_rate_3wk"] - off["return_rate_3wk"]) < 0.10
    assert on["permanent_switch_rate"] >= off["permanent_switch_rate"] - 0.05


def test_recovery_is_measured_against_the_unshocked_counterfactual():
    """Not against the cohort's own pre-shock level, which is 1.0 by definition.

    The cohort is *defined* as the buyers with that seller the week before, so
    a recovery bar set against its own pre-shock share is unreachable and
    returns NaN - which is how the first version of this metric failed.
    """
    import dataclasses

    m = shock_metrics(dataclasses.replace(PHASE6_MAIN, seeds=tuple(range(10))), 0, 12)
    assert not np.isnan(m["recovery_weeks"])
    assert m["recovery_weeks"] >= 1.0
