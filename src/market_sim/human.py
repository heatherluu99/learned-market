"""Phase 10 — real human purchase data, and what it can and cannot check.

The first real people in this project. Everything in Phases 1-9 is simulated,
including the "teacher", so nothing before this point makes any claim about
human behaviour.

The dataset is a scanner panel of cracker brand choices: 3,292 purchase
occasions by 136 households, with each brand's price and its display and
newspaper-feature promotions recorded at every occasion. It is used because it
is the same *kind* of object this project simulates - repeated discrete choices
by identified individuals, under varying price and promotion - and because it
is the data the McFadden random-utility framework in `engine.purchase_probability`
was built for.

**What it cannot check is as important as what it can.** The panel records
brand choice *conditional on a purchase being made*: every occasion has a
chosen brand and there is no "bought nothing" outcome. So `participation_rate`,
the budget wall, and every result in this project that rests on someone *not*
buying have no counterpart here and are not compared. Nor does the panel carry
household income or budget, so Phase 2's class stratification has no direct
analogue either.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

#: Retrieved 2026-09-06 from Rdatasets, which mirrors the `Ecdat` R package.
SOURCE_URL = "https://vincentarelbundock.github.io/Rdatasets/csv/Ecdat/Cracker.csv"
CITATION = (
    "Jain, Dipak C., Naufel J. Vilcassim and Pradeep K. Chintagunta (1994), "
    "'A random-coefficients logit brand-choice model applied to panel data', "
    "Journal of Business and Economic Statistics 12(3), 317. Also Paap, R. and "
    "Philip Hans Franses (2000), Journal of Applied Econometrics 15(6), 717-744."
)
#: The dataset spells this brand "kleebler"; the company is Keebler. Kept as
#: the file has it so a reader can match the column names.
BRANDS = ("sunshine", "kleebler", "nabisco", "private")

#: Quantities this project measures that the panel *cannot* speak to, recorded
#: here so a comparison is never quietly extended to them.
NOT_COMPARABLE = {
    "participation_rate": "the panel has no no-purchase outcome",
    "budget_wall": "no household income or budget is recorded",
    "class_stratification": "no demographics; buyer class has no analogue",
    "inventory": "stock-outs are not observed",
}


#: Three of 13,168 rows carry a price of 0, all Nabisco and all chosen,
#: against a Nabisco 1st percentile of 74 and a median of 109. That is a
#: coding artefact rather than a free cracker, and a zero price left in a
#: utility model is the most attractive option in the dataset. The whole
#: occasion is dropped, not just the row, so every remaining occasion keeps a
#: complete choice set and exactly one chosen brand.
DROP_ZERO_PRICE = True


def load(path: Path | str = "data/cracker/Cracker.csv",
         drop_zero_price: bool = DROP_ZERO_PRICE) -> pd.DataFrame:
    """Long format: one row per (occasion, brand), as the engine sees encounters."""
    wide = pd.read_csv(path)
    wide = wide.rename(columns={"rownames": "occasion"})
    wide["order"] = wide.groupby("id").cumcount()
    rows = []
    for brand in BRANDS:
        rows.append(pd.DataFrame({
            "occasion": wide["occasion"], "household": wide["id"],
            "order": wide["order"], "brand": brand,
            # Prices are recorded in cents; kept as given and normalized below
            # rather than rescaled here, so the file and the frame agree.
            "price": wide[f"price.{brand}"],
            "display": wide[f"disp.{brand}"].astype(int),
            "feature": wide[f"feat.{brand}"].astype(int),
            "chosen": (wide["choice"] == brand).astype(int),
        }))
    long = pd.concat(rows).sort_values(["household", "order", "brand"])
    if drop_zero_price:
        bad = long.loc[long["price"] <= 0, "occasion"].unique()
        long = long[~long["occasion"].isin(bad)]
        long.attrs["dropped_occasions"] = len(bad)
    # The project's normalizer, applied the way its own convention requires:
    # the highest price in the data, fixed once, never per-occasion.
    long["price_reference"] = float(long["price"].max())
    long["relative_price"] = long["price"] / long["price_reference"]
    return long.reset_index(drop=True)


def brand_shares(long: pd.DataFrame) -> pd.Series:
    """Share of occasions each brand wins. Compares to `tier_share`."""
    chosen = long[long["chosen"] == 1]
    return chosen["brand"].value_counts(normalize=True).sort_index()


def promotion_lift(long: pd.DataFrame) -> pd.DataFrame:
    """Choice share of a brand with and without each promotion type.

    The counterpart of Phase 4, which found promotion to be an *interaction*
    rather than a level shift. Here there is no buyer class to interact with,
    so only the main effect is available.
    """
    rows = []
    for kind in ("display", "feature"):
        for brand in BRANDS:
            sub = long[long["brand"] == brand]
            on = sub[sub[kind] == 1]["chosen"].mean()
            off = sub[sub[kind] == 0]["chosen"].mean()
            rows.append({"promotion": kind, "brand": brand,
                         "share_on": on, "share_off": off, "lift": on - off,
                         "n_on": int((sub[kind] == 1).sum())})
    return pd.DataFrame(rows)


def price_response(long: pd.DataFrame, bins: int = 6) -> pd.DataFrame:
    """Choice share against the brand's own relative price.

    The empirical analogue of `- alpha * (price / price_reference)` in the
    utility. A downward slope is the minimum the simulator has to reproduce.
    """
    sub = long.copy()
    sub["band"] = pd.qcut(sub["relative_price"], bins, duplicates="drop")
    out = sub.groupby("band", observed=True).agg(
        relative_price=("relative_price", "mean"),
        share=("chosen", "mean"), n=("chosen", "size")).reset_index(drop=True)
    return out


def repeat_rate(long: pd.DataFrame) -> dict[str, float]:
    """P(same brand as the previous occasion), and a no-memory baseline.

    The counterpart of Phase 6's `pair_stability`, and the reason that phase
    insisted on a control: an unequal brand share produces repeat purchasing
    with no memory at all, so the raw rate is not evidence of loyalty. The
    baseline is the rate expected if each occasion were drawn independently
    from the observed brand shares.
    """
    chosen = long[long["chosen"] == 1].sort_values(["household", "order"])
    previous = chosen.groupby("household")["brand"].shift(1)
    paired = previous.notna()
    observed = float((chosen["brand"][paired] == previous[paired]).mean())
    shares = brand_shares(long)
    return {
        "repeat_rate": observed,
        "no_memory_baseline": float((shares**2).sum()),
        "excess": observed - float((shares**2).sum()),
        "n_pairs": int(paired.sum()),
    }


def provenance() -> dict[str, str]:
    return {"source_url": SOURCE_URL, "citation": CITATION,
            "retrieved": "2026-09-06", "n_occasions": "3292", "n_households": "136",
            "dropped": "3 occasions carrying a price of 0 - a coding artefact"}
