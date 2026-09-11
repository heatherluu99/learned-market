"""Phase 11 — is the human-Agent gap systematic, and can one number fix it?

Three categories from one source: Cracker, Catsup and Yogurt, all citing Jain,
Vilcassim & Chintagunta (1994). The Agent is `gpt-oss:20b` run locally, because
Groq's free tier took four days to answer one panel.

**This does not reuse Phase 10's helpers.** That module pins `BRANDS` to
Cracker's four and does `BRANDS.index(...)` on a household's previous brand,
which raises on Catsup rather than misreading it. Phase 10 is frozen and
tagged; its code is left exactly as the result was produced.

The map is over `(category, context)`, where context is the marketing
condition of an *alternative* - on display, on feature, price tercile within
its category. Those are the levers a client asks about and the only contextual
variables all three panels record. The registered `demographic` dimension is
dropped: none of the panels carries a household attribute.

Three corrections are compared on **held-out households**, and the ordering is
the finding. Phase 9d found the Agent's error against a known rule was
essentially one number, so if that carries here a single global constant beats
nothing and a per-cell map does not beat the constant by much.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from market_sim import agent, experiment_log, human  # noqa: E402

RESULTS_ROOT = REPO_ROOT / "results" / "phase11"
LOG_PATH = REPO_ROOT / "experiment_log.csv"
CACHE = RESULTS_ROOT / "agent_cache.json"

MODEL = "gpt-oss:20b"
SETTINGS = {"temperature": 0.0, "think": "low", "max_tokens": 512}
#: Not "9d-2", which this runner carried until it was caught: that is Phase
#: 9d's per-stall Bernoulli prompt (`agent.SYSTEM` + `describe`). This phase
#: sends `agent.CHOICE_SYSTEM` + `describe_shelf` - a four-way brand choice on
#: the shelf alone, no history - and a label shared with 9d made two different
#: decision problems read as one prompt in the log. The cache is keyed on
#: panel and prompt text, not on this label, so correcting it moves no answer.
PROMPT_VERSION = "11-shelf-1"
SEED = 0

RESEARCH_QUESTION = (
    "Is the human-Agent gap systematic and predictable across product "
    "categories and marketing contexts, and is it correctable by a single "
    "constant or does it need a map?"
)


def occasions(panel: pd.DataFrame) -> list[dict]:
    """One record per occasion. Brand names come from the frame, not a constant."""
    brands = human.brands_of(panel)
    n = len(brands)
    wide = panel.sort_values(["occasion", "brand"])
    per = wide.iloc[::n][["occasion", "household"]].reset_index(drop=True)
    cols = {c: wide[c].to_numpy().reshape(-1, n)
            for c in ("brand", "chosen", "price", "display", "feature")}
    picked = cols["brand"][np.arange(len(per)), cols["chosen"].argmax(1)]

    history: dict[int, list[str]] = {}
    out = []
    for i in range(len(per)):
        household = int(per["household"][i])
        past = history.get(household, [])
        if past:
            counts = pd.Series(past).value_counts(normalize=True)
            hist = {"last": past[-1], "top": counts.index[0],
                    "top_share": float(counts.iloc[0])}
        else:
            hist = {"last": None, "top": None, "top_share": 0.0}
        out.append({
            "occasion": int(per["occasion"][i]), "household": household,
            "alternatives": [
                {"brand": cols["brand"][i][j], "price": float(cols["price"][i][j]),
                 "display": int(cols["display"][i][j]),
                 "feature": int(cols["feature"][i][j])}
                for j in range(n)],
            "chosen_index": int(cols["chosen"][i].argmax()),
        })
        history.setdefault(household, []).append(picked[i])
    return out


def price_step(records) -> float:
    """A rounding step giving every panel comparable price resolution.

    `agent.describe_choice` rounds to the nearest 5 and calls the result
    "cents", which is right for Cracker - 38 to 169, and 92% of its distinct
    shelves survive. The other two panels are in different units. Catsup runs
    0.1 to 12.0, so rounding to the nearest 5 collapsed **867 distinct shelves
    to 48**, and the Agent was shown "5 cents" for all four brands on most
    occasions. It had nothing to discriminate on, and its flatness there was
    this function's doing rather than the model's.

    The step is chosen from a 1/2/5 series to give roughly 26 buckets across
    the panel's own range, which is what Cracker already had.
    """
    prices = np.array([[a["price"] for a in r["alternatives"]] for r in records])
    target = (prices.max() - prices.min()) / 26
    power = 10.0 ** np.floor(np.log10(target))
    for multiple in (1, 2, 5, 10):
        if multiple * power >= target:
            return float(multiple * power)
    return float(10 * power)


def describe_shelf(alternatives, step: float) -> str:
    """Phase 11's own prompt: the shelf, at a resolution the panel can carry.

    Deliberately not `agent.describe_choice`. That function is Phase 10's,
    Phase 10 is frozen and tagged, and its fixed 5-unit rounding is what broke
    two of these three panels. It also says "cents", which is false for two of
    them; this says "price" and lets the number speak.
    """
    decimals = max(0, -int(np.floor(np.log10(step))))
    lines = []
    for a in alternatives:
        promos = [k for k in ("display", "feature") if a[k]]
        tag = f", on {' and '.join(promos)}" if promos else ""
        rounded = step * round(a["price"] / step)
        lines.append(f"- {a['brand']}: price {rounded:.{decimals}f}{tag}")
    return ("Shelf today:\n" + "\n".join(lines)
            + "\nPick one. This household has no recorded history.")


def load_cache() -> dict:
    import json
    return json.loads(CACHE.read_text()) if CACHE.exists() else {}


def save_cache(cache: dict) -> None:
    import json
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(cache))


def agent_probabilities(records, client, key: str) -> np.ndarray:
    """One distribution per occasion, one model call per distinct prompt."""
    cache = load_cache()
    step = price_step(records)
    # **The Agent is given the shelf and no household history.** That is a
    # weaker task than Phase 10 set it, and it is deliberate: this map
    # attributes the gap to *marketing context*, and a history term would
    # confound context with each household's idiosyncratic past. The human
    # side of every cell is an aggregate share, which is history-free in the
    # same way. It also collapses Cracker from 2,212 distinct prompts to 909,
    # which is a consequence and not the reason.
    prompts = [describe_shelf(r["alternatives"], step) for r in records]
    distinct = [p for p in dict.fromkeys(prompts) if f"{key}|{p}" not in cache]
    print(f"    {len(prompts):,} occasions, {len(set(prompts)):,} distinct "
          f"(price step {step:g}), {len(distinct):,} to fetch", flush=True)
    started = time.perf_counter()
    for i, prompt in enumerate(distinct, 1):
        text, _, _ = client(agent.CHOICE_SYSTEM, prompt)
        parsed = agent.parse_distribution(text, len(records[0]["alternatives"]))
        # A uniform fallback is a stated choice, not a silent repair.
        cache[f"{key}|{prompt}"] = parsed or [1 / len(records[0]["alternatives"])] * \
            len(records[0]["alternatives"])
        if i % 100 == 0:
            print(f"      {i}/{len(distinct)}  {time.perf_counter()-started:.0f}s",
                  flush=True)
    save_cache(cache)
    return np.array([cache[f"{key}|{p}"] for p in prompts])


def context_of(records, panel_name: str) -> np.ndarray:
    """A label per (occasion, alternative): its marketing condition."""
    prices = np.array([[a["price"] for a in r["alternatives"]] for r in records])
    lo, hi = np.percentile(prices, [33.333, 66.667])
    out = []
    for r in records:
        row = []
        for a in r["alternatives"]:
            band = "cheap" if a["price"] < lo else "mid" if a["price"] < hi else "dear"
            promo = ("display+feature" if a["display"] and a["feature"]
                     else "display" if a["display"]
                     else "feature" if a["feature"] else "none")
            row.append(f"{band}|{promo}")
        out.append(row)
    return np.array(out)


def build_map(records, predicted, contexts, panel_name, category, households):
    """Human share and Agent probability per (category, context), per household set."""
    observed = np.zeros_like(predicted)
    observed[np.arange(len(records)), [r["chosen_index"] for r in records]] = 1
    hh = np.array([r["household"] for r in records])
    rows = []
    for label in sorted(set(contexts.ravel())):
        mask = contexts == label
        for split, keep in (("train", np.isin(hh, households["train"])),
                            ("test", np.isin(hh, households["test"]))):
            m = mask & keep[:, None]
            if m.sum() < 30:
                continue
            rows.append({
                "panel": panel_name, "category": category, "context": label,
                "split": split, "n": int(m.sum()),
                "human": float(observed[m].mean()),
                "agent": float(predicted[m].mean()),
                "gap": float(predicted[m].mean() - observed[m].mean()),
            })
    return rows


def apply_correction(predicted, contexts, offsets, default=0.0):
    """Add an offset per alternative, then renormalise each occasion.

    Renormalising matters: an additive shift leaves the simplex, and a
    "corrected" set of probabilities that no longer sums to one is not a
    distribution and cannot be scored against one.
    """
    shifted = predicted.copy()
    for label, value in offsets.items():
        shifted[contexts == label] += value
    if default:
        known = np.isin(contexts, list(offsets))
        shifted[~known] += default
    shifted = np.clip(shifted, 1e-6, None)
    return shifted / shifted.sum(axis=1, keepdims=True)


def sharpen(predicted, gamma: float):
    """`p ** gamma`, renormalised. The natural correction for compression.

    An additive constant moves a distribution's centre and cannot change its
    spread, so it is powerless against an Agent whose output is near-uniform
    whatever the context. Raising to a power and renormalising is the
    one-parameter correction that does change spread: `gamma > 1` sharpens,
    `gamma < 1` flattens, `gamma = 1` is the identity. It is the multiplicative
    half of the adjustment the phase registered.
    """
    out = np.clip(predicted, 1e-9, None) ** gamma
    return out / out.sum(axis=1, keepdims=True)


def fit_sharpening(records, predicted, contexts, keep, grid=None):
    """Choose gamma on the training households, by the metric being corrected."""
    grid = grid if grid is not None else np.arange(1.0, 8.01, 0.25)
    best, best_gamma = None, 1.0
    for gamma in grid:
        s = score(records, sharpen(predicted, gamma), contexts, keep)["cell_gap"]
        if best is None or s < best:
            best, best_gamma = s, float(gamma)
    return best_gamma


FLOOR = 1e-6


def evaluate(panels, offsets_by_panel, default):
    """Weighted held-out cell gap and log-loss for one set of per-panel offsets."""
    gaps, lls, ns = [], [], []
    for name, (records, predicted, contexts, households, _) in panels.items():
        keep = np.isin([r["household"] for r in records], households["test"])
        corrected = apply_correction(predicted, contexts,
                                     offsets_by_panel.get(name, {}), default)
        s = score(records, corrected, contexts, keep)
        gaps.append(s["cell_gap"]); lls.append(s["log_loss"]); ns.append(int(keep.sum()))
    w = np.array(ns, dtype=float)
    return ((np.array(gaps) * w).sum() / w.sum(),
            (np.array(lls) * w).sum() / w.sum())


def permutation_test(panels, per_cell, default, draws=200, seed=7):
    """Shuffle the offsets across cells, within panel, and re-score.

    The phase pre-registered "per-cell beats global" as the outcome that would
    justify the phase and would therefore be the tempting one to find. If a map
    of the same offsets in the wrong cells corrects just as well, the map holds
    no information about *which* cell and the win is an artifact of shifting
    probability around. This is the check that separates those.
    """
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(draws):
        shuffled = {}
        for panel, table in per_cell.items():
            keys, values = list(table), list(table.values())
            rng.shuffle(values)
            shuffled[panel] = dict(zip(keys, values))
        out.append(evaluate(panels, shuffled, default))
    return np.array(out)


def score(records, predicted, contexts, keep):
    """Held-out error: weighted absolute cell gap, and log-loss.

    Every arm is floored at the same `FLOOR` before scoring, including the
    uncorrected one. This is not cosmetic. `apply_correction` clips at 1e-6 on
    its way out, so an unfloored `none` arm was the only one paying
    -log(1e-12) = 27.6 nats wherever the Agent gave the chosen brand exactly
    zero -- 1.56% of held-out occasions. That alone made a -0.0017 offset look
    like a 0.21-nat improvement. The floor is an evaluation convention; it has
    to be the same convention for everyone being compared.
    """
    predicted = np.clip(predicted, FLOOR, None)
    predicted = predicted / predicted.sum(axis=1, keepdims=True)
    observed = np.zeros_like(predicted)
    observed[np.arange(len(records)), [r["chosen_index"] for r in records]] = 1
    gaps, weights = [], []
    for label in sorted(set(contexts.ravel())):
        m = (contexts == label) & keep[:, None]
        if m.sum() < 30:
            continue
        gaps.append(abs(predicted[m].mean() - observed[m].mean()))
        weights.append(m.sum())
    gaps, weights = np.array(gaps), np.array(weights, dtype=float)
    ll = float(-np.log(np.clip((predicted * observed)[keep].sum(1), 1e-12, 1)).mean())
    # No cell cleared the 30-observation floor: say so, rather than dividing by
    # zero and letting a nan travel silently into the results table.
    gap = float((gaps * weights).sum() / weights.sum()) if weights.size else float("nan")
    return {"cell_gap": gap, "log_loss": ll}


def main() -> int:
    commit = experiment_log.git_commit(REPO_ROOT)
    RESULTS_ROOT.mkdir(parents=True, exist_ok=True)
    print("\n=== Phase 11 — bias across three categories ===")
    print(f"  {RESEARCH_QUESTION}\n")
    print(f"  {MODEL} locally, {SETTINGS}\n")

    client = agent.ollama_client(MODEL, **SETTINGS)
    rng = np.random.default_rng(SEED)
    everything, panels = [], {}

    for name, spec in human.PANELS.items():
        print(f"  {name} ({spec['category']}):", flush=True)
        panel = human.load(name)
        records = occasions(panel)
        predicted = agent_probabilities(records, client, name)
        contexts = context_of(records, name)
        hh = np.unique([r["household"] for r in records])
        rng.shuffle(hh)
        cut = len(hh) // 2
        households = {"train": hh[:cut], "test": hh[cut:]}
        panels[name] = (records, predicted, contexts, households, spec["category"])
        everything += build_map(records, predicted, contexts, name,
                                spec["category"], households)

    bias = pd.DataFrame(everything)
    bias.to_csv(RESULTS_ROOT / "bias_map.csv", index=False)

    print(f"\n  Bias map: {len(bias)} cells across "
          f"{bias['category'].nunique()} categories\n")
    print(f"  {'category':12s} {'context':22s} {'n':>6s} {'human':>7s} "
          f"{'agent':>7s} {'gap':>8s}")
    for r in bias[bias.split == "test"].sort_values("gap").itertuples():
        print(f"  {r.category:12s} {r.context:22s} {r.n:6d} {r.human:7.3f} "
              f"{r.agent:7.3f} {r.gap:+8.3f}")

    # ---- the three corrections, fit on train and scored on test -----------
    train = bias[bias.split == "train"]
    global_offset = float(-(train.gap * train.n).sum() / train.n.sum())
    # Keyed on (panel, context), because the map is. A dict keyed on context
    # alone lets each panel overwrite the previous one's offsets -- three
    # panels share the same nine context labels -- and silently scores
    # crackers with yogurt's corrections.
    per_cell = {}
    for r in train.itertuples():
        per_cell.setdefault(r.panel, {})[r.context] = -r.gap
    print(f"\n  global offset fitted on training households: {global_offset:+.4f}")

    # The sharpening exponent is fitted on the *training* households of every
    # panel pooled, so it is one number for the whole map, like the offset.
    gammas = []
    for name, (records, predicted, contexts, households, _) in panels.items():
        train_keep = np.isin([r["household"] for r in records], households["train"])
        gammas.append(fit_sharpening(records, predicted, contexts, train_keep))
    gamma = float(np.mean(gammas))
    print(f"  sharpening exponent fitted on training households: {gamma:.2f} "
          f"(per panel {[round(g, 2) for g in gammas]})")

    rows = []
    for label, default in (("none", 0.0),
                           ("global", global_offset),
                           ("per-cell", global_offset),
                           ("sharpen", None)):
        agg = {"cell_gap": [], "log_loss": [], "n": []}
        for name, (records, predicted, contexts, households, _) in panels.items():
            keep = np.isin([r["household"] for r in records], households["test"])
            offsets = per_cell.get(name, {}) if label == "per-cell" else {}
            if label == "none":
                corrected = predicted
            elif label == "sharpen":
                corrected = sharpen(predicted, gamma)
            else:
                corrected = apply_correction(predicted, contexts, offsets, default)
            s = score(records, corrected, contexts, keep)
            agg["cell_gap"].append(s["cell_gap"]); agg["log_loss"].append(s["log_loss"])
            agg["n"].append(int(keep.sum()))
        w = np.array(agg["n"], dtype=float)
        rows.append({"correction": label,
                     "cell_gap": float((np.array(agg["cell_gap"]) * w).sum() / w.sum()),
                     "log_loss": float((np.array(agg["log_loss"]) * w).sum() / w.sum())})

    result = pd.DataFrame(rows)
    result.to_csv(RESULTS_ROOT / "corrections.csv", index=False)
    print(f"\n  Held-out households only:")
    print(f"  {'correction':12s} {'cell gap':>10s} {'log-loss':>10s}")
    for r in result.itertuples():
        print(f"  {r.correction:12s} {r.cell_gap:10.4f} {r.log_loss:10.4f}")

    real = evaluate(panels, per_cell, global_offset)
    placebo = permutation_test(panels, per_cell, global_offset)
    p_gap = float((placebo[:, 0] <= real[0]).mean())
    p_ll = float((placebo[:, 1] <= real[1]).mean())
    pd.DataFrame({"metric": ["cell_gap", "log_loss"],
                  "per_cell": [real[0], real[1]],
                  "placebo_mean": [placebo[:, 0].mean(), placebo[:, 1].mean()],
                  "placebo_sd": [placebo[:, 0].std(), placebo[:, 1].std()],
                  "p_value": [p_gap, p_ll]}).to_csv(
        RESULTS_ROOT / "permutation.csv", index=False)
    print(f"\n  Offsets shuffled across cells within panel, {len(placebo)} draws:")
    print(f"  {'':12s} {'per-cell':>10s} {'shuffled':>10s} {'':>8s} {'p':>7s}")
    print(f"  {'cell gap':12s} {real[0]:10.4f} {placebo[:, 0].mean():10.4f} "
          f"+-{placebo[:, 0].std():6.4f} {p_gap:7.3f}")
    print(f"  {'log-loss':12s} {real[1]:10.4f} {placebo[:, 1].mean():10.4f} "
          f"+-{placebo[:, 1].std():6.4f} {p_ll:7.3f}")

    none, glob, cell, sharp = result.cell_gap
    print(f"\n  global vs none : {none - glob:+.4f}  "
          f"({'helps' if glob < none else 'does not help'})")
    print(f"  per-cell vs global: {glob - cell:+.4f}  "
          f"({'a map is warranted' if cell < glob * 0.9 else 'the constant is enough'})")
    print(f"  sharpen vs none   : {none - sharp:+.4f}  "
          f"({'helps' if sharp < none else 'does not help'})")

    # Stability: does a cell's gap survive the split?
    wide = bias.pivot_table(index=["category", "context"], columns="split",
                            values="gap").dropna()
    wide["swing"] = (wide["test"] - wide["train"]).abs()
    wide.to_csv(RESULTS_ROOT / "stability.csv")
    stable = wide[wide.swing < 0.05]
    print(f"\n  {len(stable)} of {len(wide)} cells hold their gap within 0.05 "
          f"across the split")

    plot(bias, result, wide, placebo, real)
    experiment_log.append_row(LOG_PATH, {
        "experiment_id": "phase11_bias_map",
        "git_commit": commit,
        "config_file": "experiments/phase11/run_phase11.py",
        "phase": 11, "seed": f"households split 50/50, seed {SEED}",
        "n_buyers": int(sum(len(np.unique([r['household'] for r in p[0]]))
                            for p in panels.values())),
        "n_sellers": 4,
        "model_used": f"{MODEL} (local, ollama), prompt {PROMPT_VERSION}",
        "decision_type": "brand_choice",
        "human_benchmark_id": "Ecdat::Cracker, Ecdat::Catsup, Ecdat::Yogurt",
        "synthetic_cost_usd": 0.0, "synthetic_latency_seconds": 0.0,
        "research_question": RESEARCH_QUESTION,
        "changed_mechanism": (
            "the Agent is compared against three human panels rather than one, "
            "and a correction fitted on half the households is scored on the "
            "other half"),
        "transaction_count": int(bias.n.sum()),
        "human_benchmark_status": "compared_to_published_panel",
        "participation_rate": "N/A - conditional on participation",
        "result_summary": (
            f"{len(bias)} cells over 3 categories. Held-out weighted cell gap: "
            f"none {none:.4f}, global {glob:.4f}, per-cell {cell:.4f}, sharpen {sharp:.4f} (gamma {gamma:.2f}); "
            f"global offset {global_offset:+.4f}. "
            f"{len(stable)}/{len(wide)} cells stable within 0.05 across the split."),
        "decision_implication": (
            "Whether a synthetic-consumer correction layer needs a map or a "
            "single constant"),
        "next_experiment": "Phase 12 - cross-model comparison",
    })
    print(f"\n  Wrote {RESULTS_ROOT}\n")
    return 0


def plot(bias, result, wide, placebo, real) -> None:
    fig, axes = plt.subplots(1, 4, figsize=(19, 4.8))

    # Dodged, not overlaid. Three categories share the same nine context
    # labels, so drawing them on the same rows with alpha made the bars sit on
    # top of one another and the figure unreadable.
    ax = axes[0]
    test = bias[bias.split == "test"]
    contexts = sorted(test.context.unique())
    cats = sorted(test.category.unique())
    colours = {"condiments": "tab:blue", "crackers": "tab:orange", "dairy": "tab:green"}
    height = 0.8 / len(cats)
    for k, cat in enumerate(cats):
        sub = test[test.category == cat].set_index("context")
        ys = [contexts.index(c) + (k - (len(cats) - 1) / 2) * height
              for c in sub.index]
        ax.barh(ys, sub.gap, height=height * 0.92, label=cat,
                color=colours.get(cat))
    ax.set_yticks(range(len(contexts)))
    ax.set_yticklabels([c.replace("display+feature", "disp+feat") for c in contexts],
                       fontsize=8)
    ax.axvline(0, c="0.3", lw=1)
    ax.set_xlabel("Agent probability minus human share")
    ax.set_title("The gap, by context and category", fontsize=10)
    ax.legend(fontsize=7, loc="lower right")

    ax = axes[1]
    colour = ["0.6", "tab:blue", "tab:green", "tab:orange"][:len(result)]
    ax.bar(result.correction, result.cell_gap, color=colour)
    for i, v in enumerate(result.cell_gap):
        ax.text(i, v, f"{v:.4f}", ha="center", va="bottom", fontsize=9)
    ax.set_ylabel("held-out weighted cell gap")
    ax.set_title("Does a map beat a constant?", fontsize=10)

    # The phase registered "per-cell wins" as the tempting outcome, so the
    # figure has to carry the check as well as the claim.
    ax = axes[2]
    ax.hist(placebo[:, 0], bins=22, color="0.75", edgecolor="0.55",
            label=f"offsets shuffled\nacross cells ({len(placebo)} draws)")
    ax.axvline(real[0], c="tab:green", lw=2.2,
               label=f"the fitted map ({real[0]:.4f})")
    ax.set_xlabel("held-out weighted cell gap")
    ax.set_ylabel("draws")
    ax.set_title("Does the map know which cell?", fontsize=10)
    ax.legend(fontsize=7.5, loc="upper right")

    ax = axes[3]
    swing = (wide["test"] - wide["train"]).abs()
    stable = swing < 0.05
    ax.scatter(wide["train"][stable], wide["test"][stable], s=38,
               c="tab:green", label=f"holds within 0.05  ({stable.sum()})")
    ax.scatter(wide["train"][~stable], wide["test"][~stable], s=38,
               c="0.65", marker="x", label=f"does not  ({(~stable).sum()})")
    lim = [min(wide.min().min(), -0.1), max(wide.max().max(), 0.1)]
    ax.plot(lim, lim, ls="--", c="0.4", lw=1)
    ax.axhline(0, c="0.85", lw=0.8); ax.axvline(0, c="0.85", lw=0.8)
    ax.set_xlabel("gap on training households")
    ax.set_ylabel("gap on held-out households")
    ax.set_title("A gap that does not survive the split is not one", fontsize=10)
    ax.legend(fontsize=7.5, loc="upper left")

    fig.suptitle("Phase 11 — is the gap systematic, and does correcting it need "
                 "a map?", fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    fig.savefig(RESULTS_ROOT / "bias_map.png", dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    raise SystemExit(main())
