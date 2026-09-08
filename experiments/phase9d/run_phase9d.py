"""Phase 9d — three decision mechanisms in one market.

    N = 30 buyers run as Agents. The remaining 70 are split between the Phase
    9a trained policy and the hand-written rule, so all three mechanisms
    appear in the same run against the same seeds, prices and draws.

**The 30 are stratified within class, not taken off the front.** Buyer ids
0-69 are Poor, 70-89 Middle, 90-99 Rich, so "the first 30" would have been an
all-Poor Agent arm facing a mixed rule arm, and every difference between them
would have been class rather than mechanism. Each arm gets 30% / 35% / 35% of
*each* class instead.

Two comparisons are reported. The **between-arm** one the gate registered -
Agent subset against rule subset inside the same run - and a **within-buyer**
one that is strictly stronger: the same market re-run with every buyer on the
rule, on the same seeds down to the draw, so each Agent buyer is compared
against itself. Between-arm differences still carry the residual of which
buyers landed in which arm; the paired one does not.

The control the gate insists on is Phase 9a's *trained* policy, not the rule:
beating a set of hand-picked coefficients answers nothing.
"""

from __future__ import annotations

import dataclasses
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

from market_sim import acceptance, agent, buyer, experiment_log  # noqa: E402
from market_sim.config import PHASE6_MAIN  # noqa: E402
from market_sim.engine import ENCOUNTER_FIELDS, run_season  # noqa: E402

ENCOUNTER_P_TEACHER = ENCOUNTER_FIELDS.index("p_teacher")

RESULTS_ROOT = REPO_ROOT / "results" / "phase9d"
LOG_PATH = REPO_ROOT / "experiment_log.csv"

MODEL = "gpt-oss:20b"
AGENT_SETTINGS = {"temperature": 0.0, "think": "low", "max_tokens": 512}
#: Bumped whenever `agent.describe` or `agent.SYSTEM` changes, because either
#: changes what the Agent saw and invalidates every cached answer.
PROMPT_VERSION = "9d-1"

SHARES = {"agent": 0.30, "policy": 0.35, "rule": 0.35}
SEEDS = tuple(range(8))
TRAIN_SEEDS = tuple(range(1000, 1030))
HELD_OUT_SEEDS = tuple(range(200, 212))
CAPACITIES = ((64, 2, 40), (128, 3, 40), (256, 3, 80))

RESEARCH_QUESTION = (
    "What does replacing the buyer decision function with an LLM-driven Agent "
    "change, holding the rest of the simulation fixed - measured against a "
    "policy trained to reproduce the same behaviour, not against the "
    "hand-written rule alone?"
)


def assign(cfg, seed: int = 0) -> dict[str, np.ndarray]:
    """Arm membership, stratified inside each buyer class."""
    rng = np.random.default_rng(seed)
    out: dict[str, list[int]] = {k: [] for k in SHARES}
    start = 0
    for klass in cfg.buyer_classes:
        ids = np.arange(start, start + klass.count)
        rng.shuffle(ids)
        cut_a = round(SHARES["agent"] * klass.count)
        cut_p = cut_a + round(SHARES["policy"] * klass.count)
        out["agent"] += list(ids[:cut_a])
        out["policy"] += list(ids[cut_a:cut_p])
        out["rule"] += list(ids[cut_p:])
        start += klass.count
    return {k: np.array(sorted(v)) for k, v in out.items()}


def summarise(season, ids: np.ndarray) -> dict[str, float]:
    """What a subset of buyers did, from the shared season."""
    chosen = season.chosen_seller[:, ids]
    attended = season.attended[:, ids]
    bought = chosen >= 0
    premium = np.array([c == "Shigh" for c in season.weeks[0].seller_classes])
    picked_premium = np.where(bought, premium[np.clip(chosen, 0, None)], False)
    a, b = chosen[1:], chosen[:-1]
    both = (a >= 0) & (b >= 0)
    return {
        "purchase_rate": float(bought.sum() / max(attended.sum(), 1)),
        "premium_share": float(picked_premium.sum() / max(bought.sum(), 1)),
        "pair_stability": float((a[both] == b[both]).mean()) if both.any() else float("nan"),
        "n_buyers": int(len(ids)),
    }


def main() -> int:
    commit = experiment_log.git_commit(REPO_ROOT)
    RESULTS_ROOT.mkdir(parents=True, exist_ok=True)
    cfg = PHASE6_MAIN
    arms = assign(cfg)
    print("\n=== Phase 9d — Agent, trained policy, and rule in one market ===")
    print(f"  {RESEARCH_QUESTION}\n")
    print("  arm membership, stratified within class:")
    for name, ids in arms.items():
        classes = [cfg.buyer_classes[0].name if i < 70
                   else cfg.buyer_classes[1].name if i < 90
                   else cfg.buyer_classes[2].name for i in ids]
        mix = {k: classes.count(k) for k in ("Poor", "Middle", "Rich")}
        print(f"    {name:7s} n={len(ids):3d}  {mix}")

    # The control has to be a student that passes Phase 9a's own offline gate,
    # not one trained at a capacity picked here. The gate is what makes it
    # "Phase 9a's trained policy" rather than "a network"; a weaker one would
    # hand the Agent an easier control and quietly flatter it.
    print(f"\n  Training the Phase 9a control on {len(TRAIN_SEEDS)} seeds, "
          f"smallest gate-passing capacity...", flush=True)
    train = buyer.encounters(cfg, TRAIN_SEEDS)
    held = buyer.encounters(cfg, HELD_OUT_SEEDS)
    constant = np.full(len(held), train[:, ENCOUNTER_P_TEACHER].mean())
    fits = []
    for hidden, depth, epochs in CAPACITIES:
        candidate = buyer.train(train, hidden=hidden, depth=depth, epochs=epochs)
        prediction = buyer.predict(candidate, held)
        fits.append((f"{hidden}x{depth}", candidate, prediction,
                     buyer.policy_distance(held, prediction)))
    floor = min(d for *_, d in fits)
    net, capacity = None, None
    for name, candidate, prediction, distance in fits:
        checks = acceptance.evaluate_phase9a_offline(
            distance=distance, floor=floor,
            calibration=buyer.calibration(held, prediction),
            log_loss=buyer.log_loss(held, prediction),
            constant_log_loss=buyer.log_loss(held, constant),
            entropy_floor=buyer.entropy_floor(held))
        if all(c.passed for c in checks):
            net, capacity = candidate, name
            break
    if net is None:
        name, net, _, _ = min(fits, key=lambda f: f[3])
        capacity = f"{name} (failed 9a's gate)"
    print(f"    control capacity: {capacity}", flush=True)
    student = buyer.as_engine_policy(net)

    usage = agent.Usage()
    reasoning: dict[str, str] = {}
    client = agent.ollama_client(MODEL, reasoning_sink=reasoning, **AGENT_SETTINGS)
    llm = agent.AgentPolicy(client, usage=usage)

    n_buyers = sum(b.count for b in cfg.buyer_classes)
    per_buyer: list = [None] * n_buyers
    for i in arms["agent"]:
        per_buyer[i] = llm
    for i in arms["policy"]:
        per_buyer[i] = student

    print(f"  Querying {MODEL} locally ({AGENT_SETTINGS}); "
          f"answers cached on the bucketed prompt.", flush=True)
    started = time.perf_counter()
    treated, control = [], []
    for seed in SEEDS:
        one = dataclasses.replace(cfg, seeds=(seed,))
        treated.append(run_season(dataclasses.replace(one, buyer_policy=per_buyer), seed))
        # Same seeds down to the draw, every buyer on the rule.
        control.append(run_season(one, seed))
        print(f"    seed {seed}: {len(llm.cache):,} prompts cached, "
              f"{usage.calls:,} calls, {time.perf_counter() - started:.0f}s",
              flush=True)
    usage.seconds = time.perf_counter() - started

    rows = []
    print(f"\n  {'arm':8s} {'purchase':>9s} {'premium':>9s} {'stability':>10s}"
          f"   vs the same buyers under the rule")
    for name, ids in arms.items():
        t = {k: np.mean([summarise(s, ids)[k] for s in treated])
             for k in ("purchase_rate", "premium_share", "pair_stability")}
        c = {k: np.mean([summarise(s, ids)[k] for s in control])
             for k in ("purchase_rate", "premium_share", "pair_stability")}
        paired = {k: np.array([summarise(a, ids)[k] - summarise(b, ids)[k]
                               for a, b in zip(treated, control)])
                  for k in ("purchase_rate", "premium_share", "pair_stability")}
        row = {"arm": name, **{f"{k}": v for k, v in t.items()},
               **{f"{k}_paired": float(paired[k].mean()) for k in paired}}
        for k in paired:
            mean, lo, hi = acceptance.mean_difference_ci(
                np.array([summarise(a, ids)[k] for a in treated]),
                np.array([summarise(b, ids)[k] for b in control]))
            row[f"{k}_lo"], row[f"{k}_hi"] = lo, hi
            row[f"{k}_verdict"] = acceptance.equivalence_verdict(lo, hi)
        rows.append(row)
        print(f"  {name:8s} {t['purchase_rate']:9.4f} {t['premium_share']:9.4f} "
              f"{t['pair_stability']:10.4f}   "
              f"purchase {row['purchase_rate_paired']:+.4f} "
              f"[{row['purchase_rate_lo']:+.4f}, {row['purchase_rate_hi']:+.4f}] "
              f"{row['purchase_rate_verdict']}")

    # Every distinct prompt with the probability it produced and the model's
    # own account of why. Written out because it is the only evidence that
    # speaks to *why* the level is what it is, and none of the aggregates do.
    import hashlib
    pd.DataFrame([
        {"prompt": prompt,
         "probability": llm.cache.get(
             hashlib.sha1(prompt.encode()).hexdigest()),
         "reasoning": text}
        for prompt, text in sorted(reasoning.items())
    ]).to_csv(RESULTS_ROOT / "reasoning.csv", index=False)

    frame = pd.DataFrame(rows)
    frame.to_csv(RESULTS_ROOT / "arms.csv", index=False)
    pd.DataFrame([usage.as_row() | {"model": MODEL, "prompt_version": PROMPT_VERSION,
                                    **AGENT_SETTINGS}]).to_csv(
        RESULTS_ROOT / "agent_usage.csv", index=False)
    plot(frame)

    per_decision = usage.seconds / max(usage.calls, 1)
    print(f"\n  {usage.calls:,} model calls, {usage.seconds:.0f}s wall, "
          f"{per_decision:.1f}s per distinct decision")
    print("  Cost is reported in the log at the local marginal rate (zero) and "
          "is not\n  comparable to a hosted per-token figure; see the Phase 9d "
          "gate.")

    experiment_log.append_row(LOG_PATH, {
        "experiment_id": "phase9d_three_mechanisms",
        "git_commit": commit,
        "config_file": "experiments/phase9d/run_phase9d.py",
        "phase": 9.4, "seed": f"{len(SEEDS)} seeds, arms stratified within class",
        "n_buyers": n_buyers,
        "n_sellers": sum(s.count for s in cfg.seller_classes),
        "model_used": f"{MODEL} (local, ollama)",
        "decision_type": "purchase",
        "human_benchmark_id": "N/A - no human comparison in this phase",
        "synthetic_cost_usd": 0.0,
        "synthetic_latency_seconds": float(usage.seconds),
        "research_question": RESEARCH_QUESTION,
        "changed_mechanism": (
            f"buyer decision function for 30% of buyers replaced by "
            f"{MODEL}, prompt {PROMPT_VERSION}, against Phase 9a's trained "
            f"policy on 35% and the hand-written rule on 35%, all in one market"
        ),
        "transaction_count": int(usage.calls),
        "human_benchmark_status": "not_compared",
        "participation_rate": "N/A",
        "result_summary": "; ".join(
            f"{r.arm}: purchase {r.purchase_rate:.4f} "
            f"(paired {r.purchase_rate_paired:+.4f} {r.purchase_rate_verdict}), "
            f"premium {r.premium_share:.4f}, stability {r.pair_stability:.4f}"
            for r in frame.itertuples()),
        "decision_implication": (
            "Whether an LLM buyer differs from a policy trained to reproduce "
            "the same rule, which is what Phase 10's agent comparison assumes"
        ),
        "next_experiment": "Phase 9d cost/speed KPI - blocked on sourcing "
                           "human_baseline.csv",
    })
    print(f"\n  Wrote {RESULTS_ROOT}\n")
    return 0


def plot(frame) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(13.5, 4.2))
    for ax, key, name in zip(axes,
                             ("purchase_rate", "premium_share", "pair_stability"),
                             ("purchase rate", "premium share", "pair stability")):
        ax.bar(frame["arm"], frame[key],
               color=["tab:red", "tab:blue", "0.6"], width=0.55)
        for i, v in enumerate(frame[key]):
            ax.text(i, v, f"{v:.3f}", ha="center", va="bottom", fontsize=9)
        ax.set_title(name, fontsize=10)
    fig.suptitle("Phase 9d — Agent, trained policy and rule in one market",
                 fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, 0.91))
    fig.savefig(RESULTS_ROOT / "arms.png", dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    raise SystemExit(main())
