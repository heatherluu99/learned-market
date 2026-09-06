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

MODEL = "openai/gpt-oss-120b"
#: Frozen before any comparison. reasoning_effort changes the answer - the same
#: prompt returns 35 at the default budget and 45 at "low" - so it is a
#: condition of the experiment and is recorded, not a convenience.
AGENT_SETTINGS = {"temperature": 0.0, "reasoning_effort": "low", "max_tokens": 512}
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


def agent_distributions(records, client, usage) -> np.ndarray:
    """One distribution per occasion, cached on the bucketed prompt."""
    cache: dict[str, list[float]] = {}
    out, unparsed = [], 0
    for k, record in enumerate(records):
        prompt = agent.describe_choice(record["alternatives"], record["history"])
        if prompt not in cache:
            import time
            started = time.perf_counter()
            text, tin, tout = client(agent.CHOICE_SYSTEM, prompt)
            usage.seconds += time.perf_counter() - started
            usage.calls += 1
            usage.input_tokens += tin
            usage.output_tokens += tout
            parsed = agent.parse_distribution(text, len(BRANDS))
            if parsed is None:
                unparsed += 1
                parsed = [1 / len(BRANDS)] * len(BRANDS)
            cache[prompt] = parsed
        else:
            usage.cached += 1
        out.append(cache[prompt])
        if (k + 1) % 250 == 0:
            print(f"    {k + 1}/{len(records)} occasions, {usage.calls} calls, "
                  f"{usage.seconds:.0f}s", flush=True)
    if unparsed:
        print(f"    warning: {unparsed} replies could not be parsed and were "
              f"given a uniform distribution")
    return np.array(out)


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
    args = parser.parse_args()

    commit = experiment_log.git_commit(REPO_ROOT)
    RESULTS_ROOT.mkdir(parents=True, exist_ok=True)
    panel = human.load()
    records = occasions(panel)
    if args.limit:
        records = records[: args.limit]
    print(f"\n=== Phase 10 — human panel, Agent, and two baselines ===")
    print(f"  {RESEARCH_QUESTION}\n")
    print(f"  {len(records):,} occasions, conditioned on participation.")
    print(f"  Agent: {MODEL}, settings frozen at {AGENT_SETTINGS}\n")

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
    client = agent.groq_client(MODEL, **AGENT_SETTINGS)
    print("  Querying the Agent (cached on the bucketed prompt)...", flush=True)
    a = agent_distributions(records, client, usage)
    print(f"  {usage.as_row()}\n")

    arms = {"B0 marginal shares": b0, "B1 conditional model": b1_full,
            f"A agent ({MODEL})": a}
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
    frame.to_csv(RESULTS_ROOT / "arms.csv", index=False)
    pd.DataFrame([{"metric": k, "human": v} for k, v in human_contrasts.items()]).to_csv(
        RESULTS_ROOT / "human_contrasts.csv", index=False)
    pd.DataFrame([usage.as_row() | {"model": MODEL, **AGENT_SETTINGS}]).to_csv(
        RESULTS_ROOT / "agent_usage.csv", index=False)
    plot(frame, human_contrasts)

    best = frame.loc[frame["weighted_js"].idxmin()]
    experiment_log.append_row(LOG_PATH, {
        "experiment_id": "phase10_human_vs_agent", "git_commit": commit,
        "config_file": "experiments/phase10/run_phase10.py",
        "phase": 10, "seed": f"{len(records)} occasions, observed-history one-step",
        "n_buyers": panel["household"].nunique(), "n_sellers": len(BRANDS),
        "model_used": MODEL, "decision_type": "brand_choice",
        "human_benchmark_id": "Ecdat::Cracker",
        "human_benchmark_status": "compared_to_published_panel",
        "synthetic_cost_usd": usage.as_row()["synthetic_cost_usd"],
        "synthetic_latency_seconds": usage.as_row()["synthetic_latency_seconds"],
        "research_question": RESEARCH_QUESTION,
        "changed_mechanism": (
            f"brand choice by an LLM Agent ({MODEL}, {AGENT_SETTINGS}) against a "
            f"marginal-share floor and a conditional model carrying household "
            f"preference, price, display and feature"
        ),
        "transaction_count": len(records),
        "participation_rate": "N/A - conditioned on participation",
        "result_summary": (
            "; ".join(f"{r['arm']}: JS {r['weighted_js']:.4f}, "
                      f"{r['signs_matched']}/4 directions"
                      for _, r in frame.iterrows())
            + f". Lowest JS: {best['arm']}."
        ),
        "decision_implication": "N/A - first external comparison, no decision yet",
        "next_experiment": "Phase 10 free-running closed loop",
    })
    print(f"\n  Wrote {RESULTS_ROOT}\n")
    return 0


def plot(frame, human_contrasts) -> None:
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

    fig.suptitle("Phase 10 — same choice sets, same history, different policies",
                 fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.savefig(RESULTS_ROOT / "human_vs_agent.png", dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    raise SystemExit(main())
