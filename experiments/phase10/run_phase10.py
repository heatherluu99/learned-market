"""Run Phase 10 — a real human panel, an Agent, and two baselines it must beat.

Observed-history one-step evaluation: at each occasion the model is given the
household's *real* history up to t-1 and the shelf it actually faced, and asked
for a distribution over the four brands. Everything is conditioned on
participation - the panel has no no-purchase outcome, so the simulator's
purchase mechanism is not in play and cannot leak into a brand-choice number.

The Agent is not compared against a straw baseline. It has to beat a
conditional choice model that already carries household preference, price,
display and feature, because beating a marginal-share baseline would say
almost nothing.

    GROQ_API_KEY=... python experiments/phase10/run_phase10.py [--limit N]
"""

from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
warnings.filterwarnings("ignore", message="Degrees of freedom <= 0")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from market_sim import agent, experiment_log, human  # noqa: E402

RESULTS_ROOT = REPO_ROOT / "results" / "phase10"
LOG_PATH = REPO_ROOT / "experiment_log.csv"

#: Two providers, because their free tiers cap different things and only one
#: shape of cap this phase can actually finish under. Groq's binds on tokens
#: per day and this prompt set costs about three days of it; Gemini's binds on
#: requests per day, and this phase is a fixed number of short requests.
#:
#: Both are listed as **arms**, not as alternatives to pick between after
#: seeing a result. Which model is queried is chosen on the command line and
#: recorded in every row the run writes; the cache is namespaced by model so
#: one provider's answers can never be served for another's.
#:
#: Each settings block is frozen before any comparison. The thinking budget -
#: `reasoning_effort` on Groq, `thinking_budget` on Gemini - changes the
#: answer: the same prompt returns 35 at gpt-oss's default budget and 45 at
#: "low". It is a condition of the experiment and is recorded, not a
#: convenience.
PROVIDERS = {
    "groq": {
        "model": "openai/gpt-oss-120b",
        "settings": {"temperature": 0.0, "reasoning_effort": "low",
                     "max_tokens": 512},
        "limits": {"tokens_per_minute": 8000, "requests_per_minute": 30},
    },
    # gemini-2.5-flash, the obvious pick, is retired for new users. Of what
    # this account can reach, 3.8-flash is the newest that accepts
    # `thinking_budget = 0` at all: 3.6-flash rejects it outright with a 400.
    # An exact version, never `gemini-flash-latest` - a floating alias points
    # at different models in different months and would make the arm
    # unreproducible, which is the thing the freeze exists to prevent.
    "gemini": {
        "model": "gemini-3.8-flash",
        "settings": {"temperature": 0.0, "thinking_budget": 0,
                     "max_tokens": 512},
        "limits": {"requests_per_minute": 10},
    },
}
BRANDS = tuple(sorted(human.BRANDS))

RESEARCH_QUESTION = (
    "Given the same choice sets and the same household history, does an LLM "
    "Agent recover sequential structure in real purchase behaviour that a "
    "conditional choice model does not already capture?"
)


def occasions(panel: pd.DataFrame) -> list[dict]:
    """One record per occasion: the shelf, the real history, the real choice."""
    wide = panel.sort_values(["occasion", "brand"])
    n = len(BRANDS)
    per = wide.iloc[::n][["occasion", "household"]].reset_index(drop=True)
    brands = wide["brand"].to_numpy().reshape(-1, n)
    chosen = wide["chosen"].to_numpy().reshape(-1, n)
    price = wide["price"].to_numpy().reshape(-1, n)
    display = wide["display"].to_numpy().reshape(-1, n)
    feature = wide["feature"].to_numpy().reshape(-1, n)
    picked = brands[np.arange(len(brands)), chosen.argmax(1)]

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
                {"brand": brands[i][j], "price": float(price[i][j]),
                 "display": int(display[i][j]), "feature": int(feature[i][j])}
                for j in range(n)
            ],
            "history": hist, "chosen": picked[i],
            "chosen_index": int(chosen[i].argmax()),
        })
        history.setdefault(household, []).append(picked[i])
    return out


#: The provider's free tier caps *tokens* per minute, not requests, so the run
#: is throughput-bound rather than latency-bound: at roughly 220 tokens a call
#: an 8,000 TPM cap allows about 36 calls a minute however many workers there
#: are. Concurrency past a handful only converts throughput into 429s, so a
#: shared token budget paces the calls and a few workers hide the round trip.
WORKERS = 4


#: Answers are cached on disk between runs, because every free tier caps some
#: quantity per day and this phase's 2,212 distinct prompts can exceed a day's
#: worth of it. A run that started from zero each day could never finish.
#:
#: Keyed on **(model, prompt)**, not on the prompt alone. Keyed on the prompt
#: alone, pointing the run at a second model would silently serve the first
#: model's answers under the second model's name - an arm that never ran,
#: reported as though it had. The prompt half also invalidates the cache for
#: free if prompt construction changes.
#: One file per provider, not one shared file keyed by model. Each run does a
#: single read-modify-write when it finishes, so two providers running at once
#: - which is the natural way to use two arms - would have the later finisher
#: overwrite whatever the earlier one had just paid for.
LEGACY_CACHE = RESULTS_ROOT / "agent_cache.json"


def cache_path(provider: str) -> Path:
    return RESULTS_ROOT / provider / "agent_cache.json"


def load_cache(provider: str, model: str) -> dict[str, list[float]]:
    import json
    path = cache_path(provider)
    if path.exists():
        return json.loads(path.read_text()).get(model, {})
    # A run that finished under the shared-file layout still has answers worth
    # keeping; they are read from there once and rewritten split.
    if LEGACY_CACHE.exists():
        return json.loads(LEGACY_CACHE.read_text()).get(model, {})
    return {}


def save_cache(provider: str, model: str, answers: dict[str, list[float]]) -> None:
    import json
    path = cache_path(provider)
    path.parent.mkdir(parents=True, exist_ok=True)
    everything = json.loads(path.read_text()) if path.exists() else {}
    everything[model] = answers
    path.write_text(json.dumps(everything))


def agent_distributions(records, client, usage, provider: str, model: str, rpm: int) -> tuple[np.ndarray, int]:
    """One distribution per occasion, querying each distinct prompt once.

    Deduplicated *before* querying rather than cached during it, so the work is
    a flat set of independent calls that can run concurrently and the
    accounting does not depend on the order occasions happen to arrive in.
    """
    import time
    from concurrent.futures import ThreadPoolExecutor

    prompts = [agent.describe_choice(r["alternatives"], r["history"]) for r in records]
    distinct = list(dict.fromkeys(prompts))
    usage.cached = len(prompts) - len(distinct)
    cache = load_cache(provider, model)
    todo = [p for p in distinct if p not in cache]
    if cache:
        print(f"    {len(cache):,} answers already on disk; {len(todo):,} to fetch",
              flush=True)
    distinct = todo
    print(f"    {len(prompts):,} occasions -> {len(distinct):,} distinct prompts "
          f"({usage.cached / len(prompts):.1%} deduplicated)", flush=True)
    print(f"    request-paced at {rpm}/min: expect about "
          f"{len(distinct) / (rpm * 0.85):.0f} minutes", flush=True)

    done = {"n": 0}

    def query(prompt: str):
        started = time.perf_counter()
        text, tin, tout = client(agent.CHOICE_SYSTEM, prompt)
        elapsed = time.perf_counter() - started
        done["n"] += 1
        if done["n"] % 250 == 0:
            print(f"    {done['n']}/{len(distinct)} calls", flush=True)
        return prompt, agent.parse_distribution(text, len(BRANDS)), tin, tout, elapsed

    started = time.perf_counter()
    results, exhausted = [], None
    try:
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            for result in pool.map(query, distinct):
                results.append(result)
    except agent.QuotaExhausted as error:
        # The daily cap is not something to retry through. Keep what was paid
        # for, say so, and let the next run resume from the cache.
        exhausted = str(error)
    wall = time.perf_counter() - started

    unparsed = 0
    for prompt, parsed, tin, tout, _ in results:
        usage.calls += 1
        usage.input_tokens += tin
        usage.output_tokens += tout
        if parsed is None:
            unparsed += 1
            # A uniform fallback is a stated choice, not a silent repair: the
            # count is reported and logged so it can be weighed.
            parsed = [1 / len(BRANDS)] * len(BRANDS)
        cache[prompt] = parsed
    usage.seconds = wall
    save_cache(provider, model, cache)
    if exhausted is not None:
        remaining = len(distinct) - len(results)
        print(f"\n    Daily quota reached with {remaining:,} prompts still to "
              f"fetch. {len(cache):,} answers are saved; re-run tomorrow and it "
              f"resumes.\n    {exhausted[:160]}", flush=True)
        raise SystemExit(2)
    if unparsed:
        print(f"    {unparsed} of {len(distinct)} replies could not be parsed and "
              f"were given a uniform distribution", flush=True)
    return np.array([cache[p] for p in prompts]), unparsed


def js_divergence(p: np.ndarray, q: np.ndarray) -> float:
    """Jensen-Shannon divergence in bits. Bounded, symmetric."""
    p, q = np.clip(p, 1e-12, 1), np.clip(q, 1e-12, 1)
    m = 0.5 * (p + q)
    kl = lambda a, b: float((a * np.log2(a / b)).sum())
    return 0.5 * kl(p, m) + 0.5 * kl(q, m)


def cells(records) -> np.ndarray:
    """Scenario labels: previous brand x whether any brand is featured.

    JS against a single occasion is degenerate - the human side is a one-hot -
    so the comparison is between *distributions within a scenario*, which is
    what the phase specification asks for.
    """
    out = []
    for r in records:
        featured = any(a["feature"] for a in r["alternatives"])
        out.append(f"{r['history']['last'] or 'none'}|{'feat' if featured else 'plain'}")
    return np.array(out)


def scenario_js(records, predicted: np.ndarray, min_n: int = 30) -> dict:
    """Mean JS between the human and predicted choice distribution per cell."""
    label = cells(records)
    observed = np.zeros((len(records), len(BRANDS)))
    observed[np.arange(len(records)), [r["chosen_index"] for r in records]] = 1
    rows = []
    for value in np.unique(label):
        mask = label == value
        if mask.sum() < min_n:
            continue
        rows.append({"cell": value, "n": int(mask.sum()),
                     "js": js_divergence(observed[mask].mean(0), predicted[mask].mean(0))})
    table = pd.DataFrame(rows)
    weighted = float((table["js"] * table["n"]).sum() / table["n"].sum())
    return {"per_cell": table, "weighted_js": weighted}


def contrasts(records, predicted: np.ndarray) -> dict[str, float]:
    """Four pre-registered mechanism directions, as share differences.

    A model can match a distribution and still have a mechanism backwards, so
    sign agreement is required before magnitude is discussed.
    """
    n = len(BRANDS)
    price = np.array([[a["price"] for a in r["alternatives"]] for r in records])
    display = np.array([[a["display"] for a in r["alternatives"]] for r in records])
    feature = np.array([[a["feature"] for a in r["alternatives"]] for r in records])
    previous = np.zeros((len(records), n), dtype=bool)
    for i, r in enumerate(records):
        if r["history"]["last"] is not None:
            previous[i, BRANDS.index(r["history"]["last"])] = True
    dear = price > np.median(price, axis=0)
    return {
        "price": float(predicted[dear].mean() - predicted[~dear].mean()),
        "display": float(predicted[display == 1].mean() - predicted[display == 0].mean()),
        "feature": float(predicted[feature == 1].mean() - predicted[feature == 0].mean()),
        "repeat": float(predicted[previous].mean() - predicted[~previous].mean()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None,
                        help="pilot on the first N occasions")
    parser.add_argument("--provider", choices=sorted(PROVIDERS), default="groq",
                        help="which Agent arm to query")
    args = parser.parse_args()
    provider = PROVIDERS[args.provider]
    model, settings = provider["model"], provider["settings"]

    # Keys come from a gitignored .env, so they never pass through a shell
    # history or a chat transcript.
    agent.load_env()
    commit = experiment_log.git_commit(REPO_ROOT)
    # Each Agent arm writes into its own directory. Sharing one would have the
    # second run silently overwrite the first's table and figure, leaving two
    # arms declared in the spec and one arm's evidence on disk.
    out = RESULTS_ROOT / args.provider
    out.mkdir(parents=True, exist_ok=True)
    panel = human.load()
    records = occasions(panel)
    if args.limit:
        records = records[: args.limit]
    print(f"\n=== Phase 10 — human panel, Agent, and two baselines ===")
    print(f"  {RESEARCH_QUESTION}\n")
    print(f"  {len(records):,} occasions, conditioned on participation.")
    print(f"  Agent: {model}, settings frozen at {settings}\n")

    observed = np.zeros((len(records), len(BRANDS)))
    observed[np.arange(len(records)), [r["chosen_index"] for r in records]] = 1

    # ---- B0: marginal shares, the floor -----------------------------------
    shares = observed.mean(0)
    b0 = np.tile(shares, (len(records), 1))

    # ---- B1: the conditional model that already knows the household -------
    l2, _ = human.select_l2(panel)
    fit = human.fit_memoryless_choice(panel, household_effects=True, l2=l2)
    held = fit["held_out"]
    b1_full = np.tile(shares, (len(records), 1))
    b1_full[held[: len(records)]] = fit["probabilities"][: held[: len(records)].sum()]

    # ---- A: the Agent ------------------------------------------------------
    usage = agent.Usage()
    build = agent.gemini_client if args.provider == "gemini" else agent.groq_client
    client = build(model, **provider["limits"], **settings)
    print("  Querying the Agent (cached on model and bucketed prompt)...", flush=True)
    a, unparsed = agent_distributions(records, client, usage, args.provider, model,
                                     provider["limits"]["requests_per_minute"])
    print(f"  {usage.as_row()}\n")

    arms = {"B0 marginal shares": b0, "B1 conditional model": b1_full,
            f"A agent ({model})": a}
    human_contrasts = contrasts(records, observed)

    print(f"  {'arm':32s} {'weighted JS':>12s} {'log-loss':>10s}  direction signs")
    rows = []
    for name, predicted in arms.items():
        js = scenario_js(records, predicted)
        ll = float(-np.log(np.clip((predicted * observed).sum(1), 1e-12, 1)).mean())
        c = contrasts(records, predicted)
        signs = {k: (np.sign(c[k]) == np.sign(human_contrasts[k])) for k in c}
        rows.append({"arm": name, "weighted_js": js["weighted_js"], "log_loss": ll,
                     **{f"contrast_{k}": v for k, v in c.items()},
                     **{f"sign_ok_{k}": bool(v) for k, v in signs.items()},
                     "signs_matched": int(sum(signs.values()))})
        print(f"  {name:32s} {js['weighted_js']:12.4f} {ll:10.4f}  "
              + " ".join(f"{k}{'+' if signs[k] else 'X'}" for k in c))

    print(f"\n  human contrasts: "
          + "  ".join(f"{k} {v:+.4f}" for k, v in human_contrasts.items()))
    frame = pd.DataFrame(rows)
    frame.to_csv(out / "arms.csv", index=False)
    # The human contrasts are a property of the panel, not of the run, so they
    # stay at the top level rather than being copied under each provider.
    pd.DataFrame([{"metric": k, "human": v} for k, v in human_contrasts.items()]).to_csv(
        RESULTS_ROOT / "human_contrasts.csv", index=False)
    pd.DataFrame([usage.as_row() | {"model": model, **settings}]).to_csv(
        out / "agent_usage.csv", index=False)
    plot(frame, human_contrasts, out, model)

    best = frame.loc[frame["weighted_js"].idxmin()]
    experiment_log.append_row(LOG_PATH, {
        "experiment_id": f"phase10_human_vs_agent_{args.provider}",
        "git_commit": commit,
        "config_file": "experiments/phase10/run_phase10.py",
        "phase": 10, "seed": f"{len(records)} occasions, observed-history one-step",
        "n_buyers": panel["household"].nunique(), "n_sellers": len(BRANDS),
        "model_used": model, "decision_type": "brand_choice",
        "human_benchmark_id": "Ecdat::Cracker",
        "synthetic_cost_usd": usage.as_row()["synthetic_cost_usd"],
        "synthetic_latency_seconds": usage.as_row()["synthetic_latency_seconds"],
        "research_question": RESEARCH_QUESTION,
        "changed_mechanism": (
            f"brand choice by an LLM Agent ({model}, {settings}) against a "
            f"marginal-share floor and a conditional model carrying household "
            f"preference, price, display and feature"
        ),
        "transaction_count": len(records),
        "human_benchmark_status": "compared_to_published_panel",
        "participation_rate": "N/A - conditioned on participation",
        "result_summary": (
            "; ".join(f"{r['arm']}: JS {r['weighted_js']:.4f}, "
                      f"{r['signs_matched']}/4 directions"
                      for _, r in frame.iterrows())
            + f". Lowest JS: {best['arm']}. {unparsed} agent replies unparsed."
        ),
        "decision_implication": "N/A - first external comparison, no decision yet",
        "next_experiment": "Phase 10 free-running closed loop",
    })
    print(f"\n  Wrote {out}\n")
    return 0


def plot(frame, human_contrasts, out, model: str) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(12.5, 4.4))
    ax = axes[0]
    ax.barh(range(len(frame)), frame["weighted_js"],
            color=["0.6", "tab:orange", "tab:blue"], height=0.6)
    ax.set_yticks(range(len(frame)))
    ax.set_yticklabels(frame["arm"], fontsize=8)
    ax.invert_yaxis()
    for i, v in enumerate(frame["weighted_js"]):
        ax.text(v, i, f"  {v:.4f}", va="center", fontsize=8)
    ax.set_xlabel("weighted Jensen-Shannon divergence (bits), lower is closer")
    ax.set_title("Distributional distance to the human panel", fontsize=10)

    ax = axes[1]
    keys = list(human_contrasts)
    width = 0.8 / (len(frame) + 1)
    x = np.arange(len(keys))
    ax.bar(x - 0.4 + width / 2, [human_contrasts[k] for k in keys], width,
           label="human", color="black")
    for i, (_, r) in enumerate(frame.iterrows()):
        ax.bar(x - 0.4 + width * (i + 1.5),
               [r[f"contrast_{k}"] for k in keys], width, label=r["arm"],
               color=["0.6", "tab:orange", "tab:blue"][i])
    ax.axhline(0, c="0.3", lw=1)
    ax.set_xticks(x)
    ax.set_xticklabels(keys)
    ax.set_ylabel("share difference")
    ax.set_title("Mechanism direction: sign must match before magnitude", fontsize=10)
    ax.legend(fontsize=7)

    fig.suptitle(f"Phase 10 — same choice sets, same history, different policies"
                 f"\nAgent: {model}", fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, 0.90))
    fig.savefig(out / "human_vs_agent.png", dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    raise SystemExit(main())
