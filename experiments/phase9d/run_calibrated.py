"""Phase 9d diagnostic — does the collapse survive correcting the intercept?

The offline fit is

    agent = -0.219 + 0.954 x rule        (weighted least squares, 447 states)

A slope of 0.954 is not compression; it is a line of essentially the right
gradient shifted down by a constant. So the Agent's error is close to *one
number*, and one number is the easiest thing to correct.

This adds that correction as a calibration layer - the Agent's own probability
plus 0.219, clipped to [0, 1] - and changes nothing else. It is an attribution
arm in the same sense as Phase 2's common-alpha run: not a better Agent, a way
of asking how much of the closed-loop collapse the intercept accounts for.

If the purchase rate recovers, the collapse was the offset compounding. If it
does not, something the offline fit cannot see is carrying it.
"""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from market_sim import acceptance, agent, experiment_log  # noqa: E402
from market_sim.config import PHASE6_MAIN  # noqa: E402
from market_sim.engine import run_season  # noqa: E402

RESULTS_ROOT = REPO_ROOT / "results" / "phase9d"
LOG_PATH = REPO_ROOT / "experiment_log.csv"
MODEL = "gpt-oss:20b"
AGENT_SETTINGS = {"temperature": 0.0, "think": "low", "max_tokens": 512}
OFFSET = 0.219
SEEDS = tuple(range(8))

RESEARCH_QUESTION = (
    "How much of Phase 9d's closed-loop purchase collapse is accounted for by "
    "the Agent's constant offset against the rule, and how much is not?"
)


class Calibrated:
    """The Agent's probability plus a fixed offset, clipped to [0, 1]."""

    def __init__(self, inner, offset: float):
        self.inner, self.offset = inner, offset

    def __call__(self, *observation) -> float:
        return float(np.clip(self.inner(*observation) + self.offset, 0.0, 1.0))


def summarise(season, ids):
    chosen, attended = season.chosen_seller[:, ids], season.attended[:, ids]
    bought = chosen >= 0
    a, b = chosen[1:], chosen[:-1]
    both = (a >= 0) & (b >= 0)
    return {"purchase_rate": float(bought.sum() / max(attended.sum(), 1)),
            "pair_stability": float((a[both] == b[both]).mean()) if both.any()
            else float("nan")}


def main() -> int:
    commit = experiment_log.git_commit(REPO_ROOT)
    cfg = PHASE6_MAIN
    print("\n=== Phase 9d — does correcting the intercept undo the collapse? ===")
    print(f"  {RESEARCH_QUESTION}\n")
    print(f"  offset {OFFSET:+.3f}, from the offline fit's intercept. Nothing "
          f"else changes.\n")

    rng = np.random.default_rng(0)
    start, agent_ids = 0, []
    for klass in cfg.buyer_classes:
        ids = np.arange(start, start + klass.count)
        agent_ids += list(rng.choice(ids, size=round(0.30 * klass.count),
                                     replace=False))
        start += klass.count
    agent_ids = np.array(sorted(agent_ids))
    n_buyers = sum(b.count for b in cfg.buyer_classes)

    raw = agent.AgentPolicy(agent.ollama_client(MODEL, **AGENT_SETTINGS))
    arms = {"Agent, as it answers": raw,
            "Agent + intercept correction": Calibrated(raw, OFFSET)}

    rows = []
    print(f"  {'arm':30s} {'purchase':>9s} {'stability':>10s}   paired against the rule")
    control = [run_season(dataclasses.replace(cfg, seeds=(s,)), s) for s in SEEDS]
    base = np.array([summarise(s, agent_ids)["purchase_rate"] for s in control])
    for name, policy in arms.items():
        per = [policy if i in set(agent_ids) else None for i in range(n_buyers)]
        runs = [run_season(dataclasses.replace(cfg, seeds=(s,), buyer_policy=per), s)
                for s in SEEDS]
        got = np.array([summarise(s, agent_ids)["purchase_rate"] for s in runs])
        stab = float(np.mean([summarise(s, agent_ids)["pair_stability"] for s in runs]))
        mean, lo, hi = acceptance.mean_difference_ci(got, base)
        rows.append({"arm": name, "purchase_rate": float(got.mean()),
                     "pair_stability": stab, "paired": mean, "lo": lo, "hi": hi,
                     "verdict": acceptance.equivalence_verdict(lo, hi)})
        print(f"  {name:30s} {got.mean():9.4f} {stab:10.4f}   "
              f"{mean:+.4f} [{lo:+.4f}, {hi:+.4f}] {rows[-1]['verdict']}")
    print(f"  {'rule (control)':30s} {base.mean():9.4f}")

    frame = pd.DataFrame(rows)
    frame.to_csv(RESULTS_ROOT / "calibrated.csv", index=False)
    recovered = ((frame.purchase_rate.iloc[1] - frame.purchase_rate.iloc[0])
                 / (base.mean() - frame.purchase_rate.iloc[0]))
    print(f"\n  the correction recovers {recovered:.1%} of the gap to the rule")

    experiment_log.append_row(LOG_PATH, {
        "experiment_id": "phase9d_intercept_correction",
        "git_commit": commit,
        "config_file": "experiments/phase9d/run_calibrated.py",
        "phase": 9.4, "seed": f"{len(SEEDS)} seeds, offset {OFFSET:+.3f}",
        "n_buyers": n_buyers, "n_sellers": sum(s.count for s in cfg.seller_classes),
        "model_used": f"{MODEL} (local, ollama) with a fixed probability offset",
        "decision_type": "purchase",
        "human_benchmark_id": "N/A",
        "synthetic_cost_usd": 0.0, "synthetic_latency_seconds": 0.0,
        "research_question": RESEARCH_QUESTION,
        "changed_mechanism": (
            f"the Agent's returned probability is shifted by {OFFSET:+.3f}, the "
            f"intercept of its offline fit against the rule, and nothing else - "
            f"an attribution arm in the sense of Phase 2's common-alpha run"),
        "transaction_count": len(SEEDS) * len(agent_ids),
        "human_benchmark_status": "not_compared",
        "participation_rate": "N/A",
        "result_summary": (
            "; ".join(f"{r.arm}: purchase {r.purchase_rate:.4f}, paired "
                      f"{r.paired:+.4f} [{r.lo:+.4f}, {r.hi:+.4f}] {r.verdict}"
                      for r in frame.itertuples())
            + f"; rule {base.mean():.4f}; correction recovers {recovered:.1%} "
              f"of the gap"),
        "decision_implication": (
            "Whether an LLM agent's closed-loop failure here is a calibration "
            "problem with a one-number fix or something structural"),
        "next_experiment": "N/A",
    })
    print(f"\n  Wrote {RESULTS_ROOT}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
