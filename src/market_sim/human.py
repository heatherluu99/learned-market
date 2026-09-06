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
    """P(same brand as the previous occasion), against a *marginal-share* baseline.

    The baseline is the rate expected if each occasion were an independent draw
    from the observed brand shares - `sum_j s_j^2`. It removes the fact that
    one brand dominates and **nothing else**: persistent household preference
    and repeating price and promotion patterns are all still inside the excess.

    So the quantity returned is an **excess repeat over the marginal-share
    baseline**, and it must not be called a memory or loyalty effect. For the
    counterpart of Phase 6's memory-OFF control see
    `conditional_repeat_baseline`, which removes household preference and
    current marketing conditions as well - and finds most of this excess is
    them.
    """
    chosen = long[long["chosen"] == 1].sort_values(["household", "order"])
    previous = chosen.groupby("household")["brand"].shift(1)
    paired = previous.notna()
    observed = float((chosen["brand"][paired] == previous[paired]).mean())
    shares = brand_shares(long)
    return {
        "repeat_rate": observed,
        "marginal_share_baseline": float((shares**2).sum()),
        "marginal_excess": observed - float((shares**2).sum()),
        "n_pairs": int(paired.sum()),
    }


def provenance() -> dict[str, str]:
    return {"source_url": SOURCE_URL, "citation": CITATION,
            "retrieved": "2026-09-06", "n_occasions": "3292", "n_households": "136",
            "dropped": "3 occasions carrying a price of 0 - a coding artefact"}


# --------------------------------------------------------------------------
# Level 2 — a conditional memory-OFF baseline
# --------------------------------------------------------------------------
#
# The marginal-share baseline above answers "how often would the same brand
# recur if occasions were independent draws from the observed shares?". It
# removes nothing else, so the excess over it still contains persistent
# household preference and whatever price and promotion patterns happen to
# repeat. Naming it a memory effect would claim more than it measures.
#
# This is the counterpart of Phase 6's memory-OFF control: a brand-choice model
# given every observable *except* the previous choice, and asked how often it
# expects the previous brand to recur. What is left over is closer to state
# dependence, though - as Fader & Lattin (1993) and Keane (1997) argue on this
# exact class of data - separating it from unobserved heterogeneity is a
# harder identification problem than any single baseline settles.

import torch  # noqa: E402


def _design(long: pd.DataFrame):
    """(occasions, 4) tensors of features, brand ids, household ids, choices."""
    wide = long.sort_values(["occasion", "brand"])
    n_alt = len(BRANDS)
    brand_code = {b: i for i, b in enumerate(sorted(BRANDS))}
    occasions = wide["occasion"].to_numpy().reshape(-1, n_alt)
    features = torch.tensor(
        wide[["relative_price", "display", "feature"]].to_numpy(dtype=np.float64)
        .reshape(-1, n_alt, 3), dtype=torch.float32)
    brands = torch.tensor(
        wide["brand"].map(brand_code).to_numpy().reshape(-1, n_alt), dtype=torch.long)
    households = torch.tensor(
        wide["household"].to_numpy().reshape(-1, n_alt)[:, 0], dtype=torch.long)
    chosen = torch.tensor(
        wide["chosen"].to_numpy().reshape(-1, n_alt).argmax(axis=1), dtype=torch.long)
    return occasions[:, 0], features, brands, households, chosen


def fit_memoryless_choice(
    long: pd.DataFrame, *, household_effects: bool = True, l2: float = 1.0,
    epochs: int = 400, lr: float = 0.05, seed: int = 0,
):
    """A conditional logit with no previous-choice term, by construction.

    Utility is `alpha_brand + u[household, brand] + beta . (price, display,
    feature)`. The household deviations `u` are what absorb "this household
    always buys Nabisco"; they are L2-penalized because 136 households x 4
    brands on ~1,600 training occasions would otherwise fit the noise.

    Occasions are split within household by alternating order, so each
    household's own intercepts are estimated on half its history and scored on
    the other half. Scoring in-sample would inflate the baseline and shrink the
    excess it is being used to measure.
    """
    torch.manual_seed(seed)
    _, features, brands, households, chosen = _design(long)
    order = torch.tensor(
        long.sort_values(["occasion", "brand"])["order"]
        .to_numpy().reshape(-1, len(BRANDS))[:, 0], dtype=torch.long)
    train = order % 2 == 0
    n_households = int(households.max()) + 1

    alpha = torch.zeros(len(BRANDS), requires_grad=True)
    beta = torch.zeros(3, requires_grad=True)
    u = torch.zeros(n_households, len(BRANDS), requires_grad=True)
    params = [alpha, beta] + ([u] if household_effects else [])
    optimizer = torch.optim.Adam(params, lr=lr)

    def utilities(mask):
        base = alpha[brands[mask]] + (features[mask] * beta).sum(-1)
        if household_effects:
            base = base + u[households[mask].unsqueeze(1), brands[mask]]
        return base

    for _ in range(epochs):
        loss = torch.nn.functional.cross_entropy(utilities(train), chosen[train])
        if household_effects:
            loss = loss + l2 * (u ** 2).mean()
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()

    with torch.no_grad():
        logits = utilities(~train)
        probabilities = torch.softmax(logits, dim=1).numpy()
        held_out_loss = float(
            torch.nn.functional.cross_entropy(logits, chosen[~train])
        )
    return {
        "probabilities": probabilities,
        "held_out": (~train).numpy(),
        "held_out_log_loss": held_out_loss,
        "beta": beta.detach().numpy(),
        "alpha": alpha.detach().numpy(),
    }


#: The grid `l2` is selected over. It has to be selected rather than chosen:
#: the conditional excess runs from +0.02 to +0.32 across this range, which is
#: the whole distance between "no memory at all" and the marginal-share answer,
#: so a hand-picked value would be picking the finding.
#: Extended below 0.03 after the selection landed on the grid's first point.
#: A minimum at a boundary is not a minimum, and the held-out loss does turn
#: over: 0.5447 at no penalty at all, 0.4722 at 0.03, 0.4832 at 0.1.
L2_GRID = (0.003, 0.01, 0.03, 0.1, 0.3, 1.0, 3.0)


def select_l2(long: pd.DataFrame, grid=L2_GRID) -> tuple[float, pd.DataFrame]:
    """Choose the penalty by held-out predictive log-loss, not by hand.

    The criterion is how well the memoryless model predicts *held-out choices*
    - which is what it is for - and never anything about the repeat rate it
    implies. Selecting on the latter would be choosing the answer.
    """
    rows = []
    for l2 in grid:
        fit = fit_memoryless_choice(long, household_effects=True, l2=l2)
        rows.append({"l2": l2, "held_out_log_loss": fit["held_out_log_loss"]})
    table = pd.DataFrame(rows)
    return float(table.loc[table["held_out_log_loss"].idxmin(), "l2"]), table


def conditional_repeat_baseline(
    long: pd.DataFrame, *, household_effects: bool = True, l2: float = 1.0,
) -> dict[str, float]:
    """Observed repeat rate against what a memoryless model expects, held out.

    Returns both, on the *same* held-out occasions, so the difference is not
    partly a difference in which occasions each was measured on.
    """
    fit = fit_memoryless_choice(long, household_effects=household_effects, l2=l2)
    wide = long.sort_values(["occasion", "brand"])
    n_alt = len(BRANDS)
    brand_code = {b: i for i, b in enumerate(sorted(BRANDS))}
    per_occasion = wide.iloc[::n_alt]
    chosen_code = (wide["chosen"].to_numpy().reshape(-1, n_alt).argmax(axis=1))
    households = per_occasion["household"].to_numpy()
    previous = np.full(len(per_occasion), -1)
    previous[1:] = np.where(households[1:] == households[:-1], chosen_code[:-1], -1)

    held = fit["held_out"] & (previous >= 0)
    predicted = fit["probabilities"][held[fit["held_out"]], previous[held]]
    observed = (chosen_code[held] == previous[held]).astype(float)
    shares = brand_shares(long)
    return {
        "observed_repeat": float(observed.mean()),
        "memoryless_predicted_repeat": float(predicted.mean()),
        "conditional_excess": float(observed.mean() - predicted.mean()),
        "marginal_share_baseline": float((shares ** 2).sum()),
        "marginal_excess": float(observed.mean() - (shares ** 2).sum()),
        "n_held_out": int(held.sum()),
        "household_effects": household_effects,
        "beta_price": float(fit["beta"][0]),
        "beta_display": float(fit["beta"][1]),
        "beta_feature": float(fit["beta"][2]),
    }
