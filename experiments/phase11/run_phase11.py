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
PROMPT_VERSION = "9d-2"
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
    prompts = [agent.describe_choice(r["alternatives"], {"last": None, "top": None,
                                                         "top_share": 0.0})
               for r in records]
    distinct = [p for p in dict.fromkeys(prompts) if f"{key}|{p}" not in cache]
    print(f"    {len(prompts):,} occasions, {len(set(prompts)):,} distinct, "
          f"{len(distinct):,} to fetch", flush=True)
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


def score(records, predicted, contexts, keep):
    """Held-out error: weighted absolute cell gap, and log-loss."""
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
    return {"cell_gap": float((gaps * weights).sum() / weights.sum()), "log_loss": ll}


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
    per_cell = {r.context: -r.gap for r in train.itertuples()}
    print(f"\n  global offset fitted on training households: {global_offset:+.4f}")

    rows = []
    for label, offsets, default in (("none", {}, 0.0),
                                    ("global", {}, global_offset),
                                    ("per-cell", per_cell, global_offset)):
        agg = {"cell_gap": [], "log_loss": [], "n": []}
        for name, (records, predicted, contexts, households, _) in panels.items():
            keep = np.isin([r["household"] for r in records], households["test"])
            corrected = (predicted if label == "none"
                         else apply_correction(predicted, contexts, offsets, default))
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

    none, glob, cell = result.cell_gap
    print(f"\n  global vs none : {none - glob:+.4f}  "
          f"({'helps' if glob < none else 'does not help'})")
    print(f"  per-cell vs global: {glob - cell:+.4f}  "
          f"({'a map is warranted' if cell < glob * 0.9 else 'the constant is enough'})")

    # Stability: does a cell's gap survive the split?
    wide = bias.pivot_table(index=["category", "context"], columns="split",
                            values="gap").dropna()
    wide["swing"] = (wide["test"] - wide["train"]).abs()
    wide.to_csv(RESULTS_ROOT / "stability.csv")
    stable = wide[wide.swing < 0.05]
    print(f"\n  {len(stable)} of {len(wide)} cells hold their gap within 0.05 "
          f"across the split")

    plot(bias, result, wide)
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
            f"none {none:.4f}, global {glob:.4f}, per-cell {cell:.4f}; "
            f"global offset {global_offset:+.4f}. "
            f"{len(stable)}/{len(wide)} cells stable within 0.05 across the split."),
        "decision_implication": (
            "Whether a synthetic-consumer correction layer needs a map or a "
            "single constant"),
        "next_experiment": "Phase 12 - cross-model comparison",
    })
    print(f"\n  Wrote {RESULTS_ROOT}\n")
    return 0


def plot(bias, result, wide) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.6))
    ax = axes[0]
    test = bias[bias.split == "test"]
    for cat, sub in test.groupby("category"):
        ax.barh([f"{c[:16]}" for c in sub.context], sub.gap, label=cat, alpha=0.75)
    ax.axvline(0, c="0.3", lw=1)
    ax.set_xlabel("Agent probability minus human share")
    ax.set_title("The gap, by context and category", fontsize=10)
    ax.legend(fontsize=7)

    ax = axes[1]
    ax.bar(result.correction, result.cell_gap, color=["0.6", "tab:blue", "tab:green"])
    for i, v in enumerate(result.cell_gap):
        ax.text(i, v, f"{v:.4f}", ha="center", va="bottom", fontsize=9)
    ax.set_ylabel("held-out weighted cell gap")
    ax.set_title("Does a map beat a constant?", fontsize=10)

    ax = axes[2]
    ax.scatter(wide["train"], wide["test"], s=34, alpha=0.75)
    lim = [min(wide.min().min(), -0.1), max(wide.max().max(), 0.1)]
    ax.plot(lim, lim, ls="--", c="0.4", lw=1)
    ax.axhline(0, c="0.85", lw=0.8); ax.axvline(0, c="0.85", lw=0.8)
    ax.set_xlabel("gap on training households")
    ax.set_ylabel("gap on held-out households")
    ax.set_title("A gap that does not survive the split is not one", fontsize=10)

    fig.suptitle("Phase 11 — is the gap systematic, and does correcting it need "
                 "a map?", fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    fig.savefig(RESULTS_ROOT / "bias_map.png", dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    raise SystemExit(main())
