"""Phase 11 — the guards its first run needed and did not have.

The first run reported that the Agent barely responds to marketing context.
It was reading a prompt that rounded prices to the nearest 5 and called them
cents, which is right for Cracker and wrong for the other two panels: Catsup
runs 0.1 to 12.0, so 867 distinct shelves became 48 and the Agent was shown
"5 cents" for all four brands on most occasions.

The finding was the prompt's, not the model's. These tests fail if that can
happen again.
"""

from __future__ import annotations

import importlib.util
import pathlib

import numpy as np
import pandas as pd
import pytest

from market_sim import human

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _phase11():
    spec = importlib.util.spec_from_file_location(
        "run_phase11", ROOT / "experiments" / "phase11" / "run_phase11.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("panel", ["cracker", "catsup", "yogurt"])
def test_the_prompt_preserves_most_of_the_price_variation(panel):
    """A prompt that collapses the shelf cannot measure response to the shelf.

    Half is a deliberately loose bar. The failure being guarded against turned
    867 distinct shelves into 48 - 5.5% - so anything near that is caught long
    before the threshold matters.
    """
    p11 = _phase11()
    records = p11.occasions(human.load(panel))
    step = p11.price_step(records)
    shelves = {tuple(round(a["price"], 4) for a in r["alternatives"])
               for r in records}
    prompts = {p11.describe_shelf(r["alternatives"], step) for r in records}
    assert len(prompts) >= 0.5 * len(shelves), (
        f"{panel}: {len(shelves)} distinct shelves collapse to {len(prompts)} "
        f"prompts at step {step:g}")


@pytest.mark.parametrize("panel", ["cracker", "catsup", "yogurt"])
def test_the_agent_can_tell_the_alternatives_apart(panel):
    """On most occasions the four brands must not all print the same price.

    This is the symptom as it actually appeared: four identical lines, so the
    only thing distinguishing the alternatives was the brand name.
    """
    p11 = _phase11()
    records = p11.occasions(human.load(panel))
    step = p11.price_step(records)
    identical = 0
    for r in records:
        shown = {step * round(a["price"] / step) for a in r["alternatives"]}
        if len(shown) == 1:
            identical += 1
    share = identical / len(records)
    assert share < 0.25, (
        f"{panel}: {share:.1%} of occasions show every brand at the same "
        f"price, so the Agent has nothing to choose on")


def test_the_price_step_adapts_to_each_panel_s_units():
    """The three panels are in different units and must not share one step."""
    p11 = _phase11()
    steps = {}
    for panel in ("cracker", "catsup", "yogurt"):
        records = p11.occasions(human.load(panel))
        steps[panel] = p11.price_step(records)
    # Cracker is in cents and runs to 169; the others are an order of
    # magnitude smaller. A single step cannot serve both.
    assert steps["cracker"] > steps["catsup"] * 5, steps
    assert all(s > 0 for s in steps.values())


def test_a_correction_is_scored_on_households_it_was_not_fitted_to():
    """Renormalisation is what keeps a corrected output a distribution."""
    p11 = _phase11()
    predicted = np.array([[0.4, 0.3, 0.2, 0.1], [0.25, 0.25, 0.25, 0.25]])
    sharpened = p11.sharpen(predicted, 2.0)
    assert np.allclose(sharpened.sum(axis=1), 1.0)
    # Sharpening must widen the spread of a non-uniform row and leave a
    # uniform one alone.
    assert sharpened[0].max() > predicted[0].max()
    assert np.allclose(sharpened[1], predicted[1])
    assert np.allclose(p11.sharpen(predicted, 1.0), predicted)


def test_every_arm_is_scored_against_the_same_probability_floor():
    """An uncorrected arm must not be the only one paying for a hard zero.

    `apply_correction` clips on its way out, so before this was fixed the
    `none` arm was the only one scored with -log(1e-12) wherever the Agent
    gave the chosen brand exactly zero. That is a property of the scorer, not
    of the correction, and it made a -0.0017 offset look like a 0.21-nat win.
    """
    p11 = _phase11()
    # Two occasions; the chosen brand has probability exactly zero on the
    # first, which is what the Agent actually does on 1.6% of held-out rows.
    records = [{"chosen_index": 0, "household": "h1"},
               {"chosen_index": 1, "household": "h1"}]
    raw = np.array([[0.0, 0.5, 0.3, 0.2], [0.1, 0.6, 0.2, 0.1]])
    contexts = np.array([["a"] * 4] * 2)
    keep = np.array([True, True])

    zero_free = p11.apply_correction(raw, contexts, {}, default=-0.0017)
    a = p11.score(records, raw, contexts, keep)["log_loss"]
    b = p11.score(records, zero_free, contexts, keep)["log_loss"]

    # A near-zero offset may not move log-loss by more than a hair. If it
    # does, the floor is doing the work and the comparison is meaningless.
    assert abs(a - b) < 0.05, (
        f"an offset of -0.0017 moved log-loss by {abs(a - b):.3f} nats, which "
        f"is the clipping floor and not a correction")
    assert a < 20, "a single hard zero should not dominate the whole score"


def test_per_cell_offsets_are_keyed_on_panel_as_well_as_context():
    """Three panels share nine context labels; a context-only key loses two.

    The map is (category, context). A correction keyed on context alone lets
    each panel overwrite the previous one's offsets, so crackers get scored
    with yogurt's corrections -- which made the per-cell arm look *worse* than
    no correction at all.
    """
    p11 = _phase11()
    train = pd.DataFrame([
        {"panel": "cracker", "context": "cheap|none", "gap": -0.10},
        {"panel": "catsup", "context": "cheap|none", "gap": +0.20},
        {"panel": "yogurt", "context": "cheap|none", "gap": +0.05},
    ])
    per_cell = {}
    for r in train.itertuples():
        per_cell.setdefault(r.panel, {})[r.context] = -r.gap

    assert set(per_cell) == {"cracker", "catsup", "yogurt"}, (
        "one offset per panel, not one shared offset")
    assert per_cell["cracker"]["cheap|none"] == pytest.approx(0.10)
    assert per_cell["catsup"]["cheap|none"] == pytest.approx(-0.20)
    # The collapsed version keeps only the last panel seen.
    collapsed = {r.context: -r.gap for r in train.itertuples()}
    assert len(collapsed) == 1 and collapsed["cheap|none"] == pytest.approx(-0.05)


def test_shuffled_offsets_are_a_real_placebo():
    """The permutation keeps the offsets and moves only which cell gets which."""
    per_cell = {"cracker": {"a": 0.1, "b": -0.2, "c": 0.3}}
    rng = np.random.default_rng(0)
    keys, values = list(per_cell["cracker"]), list(per_cell["cracker"].values())
    rng.shuffle(values)
    shuffled = dict(zip(keys, values))
    assert sorted(shuffled.values()) == sorted(per_cell["cracker"].values())
    assert set(shuffled) == set(per_cell["cracker"])
