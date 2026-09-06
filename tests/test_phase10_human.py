"""Phase 10 — the first real people in this project.

What is pinned here is mostly what the panel *cannot* be used for. The
comparable quantities are few and the tempting ones are unavailable, and the
failure mode this guards against is a comparison quietly extended to a
quantity the data does not contain.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pytest

from market_sim import human

ROOT = pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def panel():
    return human.load()


def test_the_panel_is_the_shape_its_documentation_claims(panel):
    assert panel["occasion"].nunique() == 3292 - 3      # three dropped, below
    assert panel["household"].nunique() == 136
    assert len(panel) == panel["occasion"].nunique() * len(human.BRANDS)
    # exactly one brand chosen per occasion - it is a conditional brand choice
    per_occasion = panel.groupby("occasion")["chosen"].sum()
    assert set(per_occasion.unique()) == {1}


def test_there_is_no_no_purchase_outcome_and_that_is_recorded(panel):
    """The structural difference from this project's buyer, in one assertion.

    Every occasion ends in a purchase, so participation, the budget wall and
    every result resting on someone *not* buying have no counterpart here.
    Recorded in NOT_COMPARABLE so a later phase cannot quietly compare them.
    """
    assert panel["chosen"].sum() == panel["occasion"].nunique()
    assert "participation_rate" in human.NOT_COMPARABLE
    assert "budget_wall" in human.NOT_COMPARABLE
    assert "class_stratification" in human.NOT_COMPARABLE
    assert "income" not in panel.columns and "budget" not in panel.columns


def test_the_price_normalizer_follows_this_project_s_own_convention(panel):
    """Fixed once from the whole panel, never per-occasion.

    The same rule the simulator uses, and for the same reason: a normalizer
    that moves with the thing being measured makes the scale a function of the
    result. See docs/phase_specifications.md, "Price Normalization Convention".
    """
    assert panel["price_reference"].nunique() == 1
    assert panel["price_reference"].iloc[0] == panel["price"].max()
    assert panel["relative_price"].max() == pytest.approx(1.0)
    assert panel["relative_price"].min() > 0


def test_brand_shares_sum_to_one_and_are_concentrated(panel):
    shares = human.brand_shares(panel)
    assert shares.sum() == pytest.approx(1.0)
    assert set(shares.index) == set(human.BRANDS)
    assert shares.max() > 0.5           # one brand dominates, as in this market


def test_the_marginal_baseline_is_named_for_what_it_actually_removes(panel):
    """It removes brand-share concentration and nothing else.

    Persistent household preference and repeating price and promotion patterns
    are all still inside the excess, so the field is called `marginal_excess`
    and not `memory_effect`. Naming it the latter is the overclaim this test
    exists to prevent.
    """
    r = human.repeat_rate(panel)
    shares = human.brand_shares(panel)
    assert r["marginal_share_baseline"] == pytest.approx(float((shares ** 2).sum()))
    assert r["marginal_excess"] == pytest.approx(
        r["repeat_rate"] - r["marginal_share_baseline"])
    assert "no_memory_baseline" not in r and "excess" not in r
    assert 0 < r["marginal_share_baseline"] < r["repeat_rate"] <= 1
    assert r["n_pairs"] == panel["occasion"].nunique() - panel["household"].nunique()


def test_household_preference_absorbs_most_of_the_marginal_excess(panel):
    """The correction that matters, pinned as a number.

    A memoryless model given household-specific brand preferences plus current
    price, display and feature predicts nearly all the observed repeat rate.
    Almost none of the marginal excess survives as anything memory-like.
    """
    l2, table = human.select_l2(panel)
    assert table["held_out_log_loss"].idxmin() not in (0, len(table) - 1), \
        "the penalty was selected at a grid boundary; extend the grid"
    conditional = human.conditional_repeat_baseline(panel, l2=l2)
    assert conditional["marginal_excess"] > 0.3
    assert conditional["conditional_excess"] < 0.1
    assert conditional["conditional_excess"] < conditional["marginal_excess"] / 3


def test_the_penalty_is_selected_on_prediction_and_not_on_the_answer(panel):
    """Choosing l2 by hand chooses the finding.

    The conditional excess spans nearly the whole distance between "no memory"
    and the marginal-share answer across this grid, so the selection criterion
    has to be held-out predictive log-loss and never anything about the repeat
    rate it implies.
    """
    excesses = [
        human.conditional_repeat_baseline(panel, l2=v)["conditional_excess"]
        for v in (0.0, 0.3)
    ]
    assert excesses[1] - excesses[0] > 0.08, "the knob must visibly move the answer"
    l2, table = human.select_l2(panel)
    assert set(table.columns) == {"l2", "held_out_log_loss"}
    assert l2 in human.L2_GRID


def test_price_response_slopes_downward(panel):
    """The minimum the simulator's price term has to reproduce."""
    response = human.price_response(panel)
    assert len(response) >= 4
    cheapest, dearest = response.iloc[0], response.iloc[-1]
    assert cheapest["relative_price"] < dearest["relative_price"]
    assert cheapest["share"] > dearest["share"]


def test_promotion_lift_is_positive_and_feature_beats_display(panel):
    lift = human.promotion_lift(panel)
    assert (lift["lift"] > 0).all()
    by_kind = lift.groupby("promotion")["lift"].mean()
    assert by_kind["feature"] > by_kind["display"]
    # every cell has enough observations to mean something
    assert (lift["n_on"] > 100).all()


def test_the_zero_price_artefact_is_dropped_and_the_drop_is_recorded():
    """Three rows priced 0, all one brand, all chosen, against a 1st percentile
    of 74 for that brand. A zero price left in a utility model is the most
    attractive option in the dataset, so the whole occasion goes - and it is
    recorded rather than silently removed."""
    kept = human.load()
    raw = human.load(drop_zero_price=False)
    assert (raw["price"] <= 0).sum() == 3
    assert (kept["price"] <= 0).sum() == 0
    assert raw["occasion"].nunique() - kept["occasion"].nunique() == 3
    # the choice set stays complete: one chosen brand per surviving occasion
    assert set(kept.groupby("occasion")["chosen"].sum().unique()) == {1}
    assert "3 occasions" in human.provenance()["dropped"]


def test_provenance_is_recorded_rather_than_assumed():
    p = human.provenance()
    assert p["source_url"].startswith("https://")
    assert "Jain" in p["citation"] and "1994" in p["citation"]
    assert p["retrieved"] == "2026-09-06"


def test_agent_cache_cannot_serve_one_model_s_answers_for_another(tmp_path, monkeypatch):
    """Answers are keyed on (provider, model), and each provider owns a file.

    Two failures are guarded here. Keyed on the prompt alone, pointing the run
    at a second provider would return the first provider's answers under the
    second's name: an arm that never ran, reported as though it had. Sharing
    one file, two providers running at once - the natural way to use two arms -
    would each do a single read-modify-write at the end, and the later finisher
    would overwrite what the earlier one had just paid for.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "run_phase10", ROOT / "experiments" / "phase10" / "run_phase10.py")
    run = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(run)
    monkeypatch.setattr(run, "RESULTS_ROOT", tmp_path)
    monkeypatch.setattr(run, "LEGACY_CACHE", tmp_path / "nonexistent.json")

    s0 = {"temperature": 0.0}
    run.save_cache("groq", "model-a", s0, {"a prompt": [1.0, 0.0]})
    run.save_cache("gemini", "model-b", s0, {"a prompt": [0.0, 1.0]})

    assert run.load_cache("groq", "model-a", s0) == {"a prompt": [1.0, 0.0]}
    assert run.load_cache("gemini", "model-b", s0) == {"a prompt": [0.0, 1.0]}
    # Separate files, so neither run's single final write can clobber the other.
    assert run.cache_path("groq") != run.cache_path("gemini")
    assert run.cache_path("groq").exists() and run.cache_path("gemini").exists()
    # A model that has never run has no answers, rather than inheriting them.
    assert run.load_cache("groq", "model-never-queried", s0) == {}
    assert run.load_cache("gemini", "model-a", s0) == {}
    # Decoding settings are conditions, not conveniences: the thinking budget
    # changes the answer, so answers produced under one setting are not
    # served under another.
    assert run.load_cache("groq", "model-a", {"temperature": 1.0}) == {}


def test_legacy_shared_cache_is_still_readable(tmp_path, monkeypatch):
    """Answers paid for under the shared-file layout are not stranded."""
    import json
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "run_phase10", ROOT / "experiments" / "phase10" / "run_phase10.py")
    run = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(run)
    monkeypatch.setattr(run, "RESULTS_ROOT", tmp_path)
    legacy = tmp_path / "agent_cache.json"
    legacy.write_text(json.dumps({"model-a": {"a prompt": [1.0, 0.0]}}))
    monkeypatch.setattr(run, "LEGACY_CACHE", legacy)

    assert run.load_cache("groq", "model-a", {}) == {"a prompt": [1.0, 0.0]}
    assert run.load_cache("groq", "model-b", {}) == {}


def test_both_providers_are_declared_arms_with_frozen_settings():
    """Both providers carry a recorded thinking budget.

    It changes the answer, so a provider entry that omitted it would leave the
    condition to the SDK's default and out of the run's provenance.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "run_phase10", ROOT / "experiments" / "phase10" / "run_phase10.py")
    run = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(run)

    assert set(run.PROVIDERS) == {"groq", "gemini"}
    for name, provider in run.PROVIDERS.items():
        settings = provider["settings"]
        assert settings["temperature"] == 0.0, name
        assert "reasoning_effort" in settings or "thinking_budget" in settings, name
        assert provider["limits"]["requests_per_minute"] > 0, name


def test_each_agent_arm_writes_into_its_own_directory(tmp_path):
    """The figure lands where it is told and carries the model's name.

    Both arms produce structurally identical charts. Written to one shared
    path the second would overwrite the first, leaving two arms declared in
    the spec and one arm's evidence on disk; written unlabelled, the surviving
    file would not say which model made it.
    """
    import importlib.util

    import pandas as pd

    spec = importlib.util.spec_from_file_location(
        "run_phase10", ROOT / "experiments" / "phase10" / "run_phase10.py")
    run = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(run)

    contrasts = {"price": -0.16, "display": 0.18, "feature": 0.30, "repeat": 0.62}
    frame = pd.DataFrame([
        {"arm": name, "weighted_js": js,
         **{f"contrast_{k}": v for k, v in contrasts.items()}}
        for name, js in [("B0", 0.17), ("B1", 0.06), ("A agent", 0.29)]
    ])

    for provider, model in [("groq", "openai/gpt-oss-120b"),
                            ("gemini", "gemini-2.5-flash")]:
        out = tmp_path / provider
        out.mkdir()
        run.plot(frame, contrasts, out, model)
        assert (out / "human_vs_agent.png").exists()

    assert not (tmp_path / "human_vs_agent.png").exists()
    assert len(list(tmp_path.glob("*/human_vs_agent.png"))) == 2


def test_the_agent_prompt_is_pinned():
    """A canary on the exact prompt text, because the run is spread over days.

    The cache is keyed on the prompt, which invalidates it correctly but
    silently: an innocent-looking edit to `describe_choice` would discard a
    week of paid-for answers and start again at zero, and nothing would say
    so. Changing the prompt is allowed - it is a registered change to the
    Agent's observation set - but it should take deleting this expectation,
    not a wording tweak nobody noticed.
    """
    from market_sim import agent

    alternatives = [
        {"brand": b, "price": p, "display": 0, "feature": 0}
        for b, p in [("kleebler", 90), ("nabisco", 120),
                     ("private", 70), ("sunshine", 100)]
    ]

    first = agent.describe_choice(alternatives, {"last": None, "top": None,
                                                 "top_share": 0.0})
    assert first == (
        "Shelf today:\n"
        "- kleebler: 90 cents\n"
        "- nabisco: 120 cents\n"
        "- private: 70 cents\n"
        "- sunshine: 100 cents\n"
        "This is the first recorded trip for this household."
    )

    repeat = agent.describe_choice(alternatives, {"last": "nabisco",
                                                  "top": "nabisco",
                                                  "top_share": 1.0})
    assert repeat.endswith(
        "Last trip it bought nabisco. Over its recent trips it bought "
        "nabisco most often (100% of the time)."
    )
