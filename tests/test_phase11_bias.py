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
