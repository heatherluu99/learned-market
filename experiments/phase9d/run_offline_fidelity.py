"""Phase 9d diagnostic — is the Agent wrong, or is the loop wrong?

The closed-loop run left two explanations standing. Either the Agent is simply
more conservative than the rule at every state, or it agrees with the rule on
the states the rule visits and only collapses once its own behaviour starts
feeding its observations.

Phase 9 already has the instrument for this. `D_offline` is the policy
distance measured on the **teacher's** state distribution; `D_shadow` is the
same distance on the student's own. 9a-9c used it for a distilled network, and
it applies unchanged to an Agent.

So: draw encounters from a rule-only market, where `history_rate` takes the
values the rule actually produces, ask the Agent for its probability at each,
and compare against the rule's own. No engine change and no change to the
observation set - only the distribution the questions are drawn from.

Reads as: **if the Agent tracks the rule here, the closed-loop collapse is the
loop's doing and not the model's.**
"""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from market_sim import agent, experiment_log  # noqa: E402
from market_sim.config import PHASE6_MAIN  # noqa: E402
from market_sim.engine import ENCOUNTER_FIELDS, run_season  # noqa: E402

RESULTS_ROOT = REPO_ROOT / "results" / "phase9d"
LOG_PATH = REPO_ROOT / "experiment_log.csv"
MODEL = "gpt-oss:20b"
AGENT_SETTINGS = {"temperature": 0.0, "think": "low", "max_tokens": 512}
PROMPT_VERSION = "9d-2"
SEEDS = (0, 1, 2)

OBS = ("buyer_class", "price", "is_premium", "streak_here",
       "purchases_this_week", "spent_this_week", "season_fraction",
       "history_rate")

RESEARCH_QUESTION = (
    "On the states the hand-written rule actually visits, does the Agent agree "
    "with it - so that the closed-loop collapse is the feedback loop's doing "
    "rather than the model's?"
)


def main() -> int:
    commit = experiment_log.git_commit(REPO_ROOT)
    RESULTS_ROOT.mkdir(parents=True, exist_ok=True)
    print("\n=== Phase 9d diagnostic — the Agent on the rule's own states ===")
    print(f"  {RESEARCH_QUESTION}\n")

    index = {f: ENCOUNTER_FIELDS.index(f) for f in OBS}
    p_teacher = ENCOUNTER_FIELDS.index("p_teacher")
    rows = []
    for seed in SEEDS:
        cfg = dataclasses.replace(PHASE6_MAIN, record_encounters=True, seeds=(seed,))
        rows.append(np.asarray(run_season(cfg, seed).encounters))
    encounters = np.vstack(rows)
    print(f"  {len(encounters):,} encounters drawn from a rule-only market")

    # One prompt per distinct bucketed state, which is what the Agent can
    # distinguish - asking the same question twice measures nothing.
    prompts: dict[str, float] = {}
    for row in encounters:
        prompt = agent.describe(*(row[index[f]] for f in OBS))
        prompts.setdefault(prompt, [])
        prompts[prompt].append(float(row[p_teacher]))
    print(f"  {len(prompts):,} distinct prompts "
          f"({1 - len(prompts) / len(encounters):.1%} deduplicated)\n")

    reasoning: dict[str, str] = {}
    client = agent.ollama_client(MODEL, reasoning_sink=reasoning, **AGENT_SETTINGS)
    out = []
    for i, (prompt, teacher_ps) in enumerate(sorted(prompts.items()), 1):
        text, _, _ = client(agent.SYSTEM, prompt)
        p_agent = agent.parse_probability(text)
        out.append({"prompt": prompt, "p_agent": p_agent,
                    "p_rule": float(np.mean(teacher_ps)), "n": len(teacher_ps),
                    "reasoning": reasoning.get(prompt, "")})
        if i % 60 == 0:
            print(f"    {i}/{len(prompts)}", flush=True)
    frame = pd.DataFrame(out).dropna(subset=["p_agent"])
    frame.to_csv(RESULTS_ROOT / "offline_fidelity.csv", index=False)

    # Weighted by how often each state occurs, so a rare bucket does not count
    # as much as a common one.
    w = frame["n"] / frame["n"].sum()
    d_offline = float((w * (frame.p_agent - frame.p_rule).abs()).sum())
    bias = float((w * (frame.p_agent - frame.p_rule)).sum())
    corr = float(np.corrcoef(frame.p_agent, frame.p_rule)[0, 1])

    print(f"\n  rule's mean probability   {float((w * frame.p_rule).sum()):.4f}")
    print(f"  Agent's mean probability  {float((w * frame.p_agent).sum()):.4f}")
    print(f"  D_offline (weighted |diff|) {d_offline:.4f}")
    print(f"  signed bias                 {bias:+.4f}")
    print(f"  correlation across states   {corr:+.4f}")

    experiment_log.append_row(LOG_PATH, {
        "experiment_id": "phase9d_offline_fidelity",
        "git_commit": commit,
        "config_file": "experiments/phase9d/run_offline_fidelity.py",
        "phase": 9.4, "seed": f"{len(SEEDS)} seeds of rule-only encounters",
        "n_buyers": 100, "n_sellers": 5,
        "model_used": f"{MODEL} (local, ollama), prompt {PROMPT_VERSION}",
        "decision_type": "purchase",
        "human_benchmark_id": "N/A",
        "synthetic_cost_usd": 0.0, "synthetic_latency_seconds": 0.0,
        "research_question": RESEARCH_QUESTION,
        "changed_mechanism": (
            "the Agent is asked for its probability on the state distribution "
            "the rule produces, rather than on the one its own behaviour "
            "produces - the D_offline half of the decomposition Phases 9a-9c "
            "used for a distilled network"),
        "transaction_count": len(frame),
        "human_benchmark_status": "not_compared",
        "participation_rate": "N/A",
        "result_summary": (
            f"On {len(frame)} distinct rule-visited states: rule mean "
            f"{float((w * frame.p_rule).sum()):.4f}, Agent mean "
            f"{float((w * frame.p_agent).sum()):.4f}, D_offline {d_offline:.4f}, "
            f"signed bias {bias:+.4f}, across-state correlation {corr:+.4f}"),
        "decision_implication": (
            "Whether Phase 9d's closed-loop collapse is attributable to the "
            "feedback loop or to the model's own calibration"),
        "next_experiment": "N/A",
    })
    plot(frame, w)
    print(f"\n  Wrote {RESULTS_ROOT}\n")
    return 0


def plot(frame, w) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.5))
    ax = axes[0]
    ax.scatter(frame.p_rule, frame.p_agent, s=8 + 400 * w, alpha=0.6)
    lim = [0, max(frame.p_rule.max(), frame.p_agent.max()) * 1.05]
    ax.plot(lim, lim, ls="--", c="0.4", lw=1, label="agreement")
    ax.set_xlabel("the rule's probability")
    ax.set_ylabel("the Agent's probability")
    ax.set_title("On the states the rule visits", fontsize=10)
    ax.legend(fontsize=8)
    ax = axes[1]
    ax.hist((frame.p_agent - frame.p_rule), bins=30, weights=w, color="tab:blue")
    ax.axvline(0, c="0.3", lw=1)
    ax.set_xlabel("Agent minus rule")
    ax.set_ylabel("share of encounters")
    ax.set_title("Signed disagreement", fontsize=10)
    fig.suptitle("Phase 9d — is the Agent wrong, or is the loop?", fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    fig.savefig(RESULTS_ROOT / "offline_fidelity.png", dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    raise SystemExit(main())
