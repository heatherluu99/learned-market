"""Phase 10 — the first real people in this project.

What is pinned here is mostly what the panel *cannot* be used for. The
comparable quantities are few and the tempting ones are unavailable, and the
failure mode this guards against is a comparison quietly extended to a
quantity the data does not contain.
"""

from __future__ import annotations

import numpy as np
import pytest

from market_sim import human


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


def test_repeat_purchase_is_reported_against_a_no_memory_baseline(panel):
    """Phase 6's lesson, applied to real data.

    An unequal brand share produces repeat purchasing with no memory at all, so
    a raw repeat rate is not evidence of loyalty. The baseline is what
    independent draws from the observed shares would give.
    """
    r = human.repeat_rate(panel)
    shares = human.brand_shares(panel)
    assert r["no_memory_baseline"] == pytest.approx(float((shares ** 2).sum()))
    assert r["excess"] == pytest.approx(r["repeat_rate"] - r["no_memory_baseline"])
    assert 0 < r["no_memory_baseline"] < r["repeat_rate"] <= 1
    assert r["n_pairs"] == panel["occasion"].nunique() - panel["household"].nunique()


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
