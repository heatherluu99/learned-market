"""Export one season of Agent decisions, with the model's own reasoning.

Phase 9d's spec asks for an Agent Inspector: click a buyer, see its persona,
the decisions it made that week, and - since this model returns one - the
reasoning behind each. The stated research value is a cheap qualitative check
on whether the Agent's logic matches the profile it was given, ahead of any
formal comparison.

It is built as its own page rather than an extension of the Phase 6 market
view. That view is driven by week-level aggregates and a canvas of sprites;
the Inspector needs per-decision records with text attached, which is a
different shape of data, and bolting one onto the other would risk a working
page for no gain. Both read the same market.

    python tools/export_agent_inspector.py --seed 0
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from market_sim import agent  # noqa: E402
from market_sim.config import PHASE6_MAIN  # noqa: E402
from market_sim.engine import ENCOUNTER_FIELDS, run_season  # noqa: E402

MODEL = "gpt-oss:20b"
SETTINGS = {"temperature": 0.0, "think": "low", "max_tokens": 512}
OBS = ("buyer_class_index", "price", "is_premium", "streak_here",
       "purchases_this_week", "spent_this_week", "season_fraction",
       "history_rate")
CLASSES = ("Poor", "Middle", "Rich")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out", type=Path,
                        default=REPO_ROOT / "viz" / "agent_inspector_data.json")
    args = parser.parse_args()

    cfg = PHASE6_MAIN
    n_buyers = sum(b.count for b in cfg.buyer_classes)
    rng = np.random.default_rng(0)
    start, agent_ids = 0, []
    for klass in cfg.buyer_classes:
        ids = np.arange(start, start + klass.count)
        agent_ids += list(rng.choice(ids, size=round(0.30 * klass.count),
                                     replace=False))
        start += klass.count
    agent_ids = sorted(int(i) for i in agent_ids)

    reasoning: dict[str, str] = {}
    client = agent.ollama_client(MODEL, reasoning_sink=reasoning, **SETTINGS)
    policy = agent.AgentPolicy(client)
    per_buyer = [policy if i in set(agent_ids) else None for i in range(n_buyers)]

    print(f"Running seed {args.seed} with {len(agent_ids)} Agent buyers...",
          flush=True)
    season = run_season(
        dataclasses.replace(cfg, record_encounters=True,
                            buyer_policy=per_buyer, seeds=(args.seed,)),
        args.seed)
    e = np.asarray(season.encounters)
    index = {f: ENCOUNTER_FIELDS.index(f) for f in ENCOUNTER_FIELDS}
    mine = e[np.isin(e[:, index["buyer_id"]], agent_ids)]
    print(f"  {len(mine):,} Agent decisions, {len(reasoning):,} distinct prompts")

    decisions = []
    for row in mine:
        prompt = agent.describe(*(row[index[f]] for f in OBS))
        decisions.append({
            "week": int(row[index["week"]]),
            "buyer": int(row[index["buyer_id"]]),
            "seller": int(row[index["seller_id"]]),
            "class": CLASSES[int(row[index["buyer_class_index"]])],
            "price": round(float(row[index["price"]]), 2),
            "premium": bool(row[index["is_premium"]]),
            "streak": int(row[index["streak_here"]]),
            "p_agent": round(float(row[index["p_acting"]]), 3),
            "p_rule": round(float(row[index["p_teacher"]]), 3),
            "bought": bool(row[index["action"]]),
            "prompt": prompt,
            # The model's own account. This is the part no aggregate carries.
            "reasoning": (reasoning.get(prompt) or "").strip(),
        })

    fidelity = pd.read_csv(REPO_ROOT / "results" / "phase9d"
                           / "fidelity_decomposition.csv").iloc[0].to_dict()
    kpi = pd.read_csv(REPO_ROOT / "results" / "phase9d" / "kpi.csv")
    kpi = dict(zip(kpi.metric, kpi.value))
    baseline = pd.read_csv(REPO_ROOT / "data" / "human_baseline.csv")

    payload = {
        "meta": {
            "model": MODEL, "settings": SETTINGS, "seed": args.seed,
            "weeks": cfg.weeks, "agent_buyers": len(agent_ids),
            "total_buyers": n_buyers, "decisions": len(decisions),
            "distinct_prompts": len(reasoning),
        },
        "fidelity": {k: (None if pd.isna(v) else round(float(v), 4))
                     for k, v in fidelity.items()},
        "kpi": {k: (None if pd.isna(v) else float(v)) for k, v in kpi.items()},
        "baseline": baseline.fillna("").to_dict(orient="records"),
        "decisions": decisions,
    }
    args.out.write_text(json.dumps(payload, separators=(",", ":")))
    print(f"Wrote {args.out} ({args.out.stat().st_size / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
