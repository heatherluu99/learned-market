"""Phase 9d's cost and speed KPI, against sourced human reference points.

The gate's formula is

    synthetic_cost_usd / (n_agent_decisions x cost_per_respondent_usd)

and three things about it need saying before any number is quoted.

**The local arm's marginal cost is zero**, so the ratio is zero whatever the
denominator is. A hosted-equivalent estimate for the same token counts is
reported alongside, labelled as the estimate it is.

**`n_agent_decisions` is the wrong denominator.** 98.8% of this run's decisions
were served from the prompt cache: the model answered 223 distinct questions
and the other 18,152 were lookups. A human panel cannot cache - each respondent
is a fresh person - so dividing by 18,375 would credit the Agent with 18,152
interviews it never conducted. The distinct-prompt count is the honest basis
and both are shown.

**And the caching is free only because the Agent has no individual variation.**
At temperature 0 two buyers in the same bucketed state give the same answer, by
construction. That is the same property Phase 10's S arm found to be the
expensive one: a model that knows no individual matched the aggregate almost as
well as one that did, while being twice as wrong per household. The cost saving
and the individual-fidelity failure are the same fact seen twice.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from market_sim import experiment_log  # noqa: E402

RESULTS_ROOT = REPO_ROOT / "results" / "phase9d"
LOG_PATH = REPO_ROOT / "experiment_log.csv"

#: Published hosted rates per million tokens, used only to say what this run
#: would have cost hosted. Two points rather than one because the rate varies
#: by provider and tier, and a single figure would imply a precision the
#: estimate does not have.
HOSTED_RATES = ((0.15, 0.60), (1.00, 3.00))


def main() -> int:
    usage = pd.read_csv(RESULTS_ROOT / "agent_usage.csv").iloc[0]
    baseline = pd.read_csv(REPO_ROOT / "data" / "human_baseline.csv")

    calls, cached = int(usage.calls), int(usage.cached)
    decisions = calls + cached
    seconds = float(usage.synthetic_latency_seconds)
    tin, tout = float(usage.input_tokens), float(usage.output_tokens)

    print("\n=== Phase 9d — cost and speed against sourced human baselines ===\n")
    print(f"  decisions        {decisions:,}  ({calls} distinct prompts, "
          f"{usage.cache_hit_rate:.1%} from cache)")
    print(f"  wall clock       {seconds:.0f}s")
    print(f"  local cost       $0.00 marginal - the model ran on this machine\n")

    hosted = [(tin / 1e6 * a + tout / 1e6 * b, a, b) for a, b in HOSTED_RATES]
    for cost, a, b in hosted:
        print(f"  hosted-equivalent @ ${a}/${b} per Mtok: ${cost:.4f} for the run, "
              f"${cost / calls:.6f} per distinct prompt")

    low = baseline.cost_per_respondent_usd_low.dropna().min()
    high = baseline.cost_per_respondent_usd_high.dropna().max()
    print(f"\n  human per-respondent, verified sources only: "
          f"${low:.2f} to ${high:,.2f} - a {high / low:,.0f}x span")
    print("  A single cost ratio is therefore not a meaningful number, and none "
          "is quoted.")

    days = baseline[["typical_turnaround_days_low",
                     "typical_turnaround_days_high"]].dropna().iloc[0]
    run_days = seconds / 86400
    lo_x, hi_x = days.iloc[0] / run_days, days.iloc[1] / run_days
    print(f"\n  human turnaround {days.iloc[0]:.0f}-{days.iloc[1]:.0f} days "
          f"against this run's {seconds:.0f}s")
    print(f"  study against study: {lo_x:,.0f}x to {hi_x:,.0f}x faster")

    rows = [{"metric": "decisions", "value": decisions},
            {"metric": "distinct_prompts", "value": calls},
            {"metric": "cache_hit_rate", "value": float(usage.cache_hit_rate)},
            {"metric": "wall_seconds", "value": seconds},
            {"metric": "local_marginal_cost_usd", "value": 0.0},
            {"metric": "hosted_equivalent_usd_low", "value": min(c for c, *_ in hosted)},
            {"metric": "hosted_equivalent_usd_high", "value": max(c for c, *_ in hosted)},
            {"metric": "human_cost_per_respondent_low", "value": float(low)},
            {"metric": "human_cost_per_respondent_high", "value": float(high)},
            {"metric": "speed_ratio_low", "value": float(lo_x)},
            {"metric": "speed_ratio_high", "value": float(hi_x)}]
    pd.DataFrame(rows).to_csv(RESULTS_ROOT / "kpi.csv", index=False)

    experiment_log.append_row(LOG_PATH, {
        "experiment_id": "phase9d_cost_speed_kpi",
        "git_commit": experiment_log.git_commit(REPO_ROOT),
        "config_file": "experiments/phase9d/run_kpi.py",
        "phase": 9.4, "seed": "N/A - derived from the 9d run's usage",
        "n_buyers": 100, "n_sellers": 5,
        "model_used": f"{usage.model} (local, ollama)",
        "decision_type": "purchase",
        "human_benchmark_id": "data/human_baseline.csv",
        "synthetic_cost_usd": 0.0,
        "synthetic_latency_seconds": seconds,
        "research_question": (
            "How does the Agent's cost and speed compare against sourced human "
            "research reference points?"),
        "changed_mechanism": (
            "cost and speed measured against published rate cards and a "
            "peer-reviewed order-of-magnitude claim, with no figure used that "
            "was not verified at its own source"),
        "transaction_count": decisions,
        "human_benchmark_status": "compared_to_published_rate_cards",
        "participation_rate": "N/A",
        "result_summary": (
            f"{decisions:,} decisions from {calls} distinct prompts "
            f"({usage.cache_hit_rate:.1%} cached) in {seconds:.0f}s at zero local "
            f"marginal cost; hosted-equivalent ${min(c for c, *_ in hosted):.4f}-"
            f"${max(c for c, *_ in hosted):.4f} for the run. Human per-respondent "
            f"spans ${low:.2f}-${high:,.0f} across verified sources, a "
            f"{high / low:,.0f}x range, so no single cost ratio is quoted. Speed, "
            f"study against study, {lo_x:,.0f}x-{hi_x:,.0f}x."),
        "decision_implication": (
            "The cost advantage is real but its size is unquotable from public "
            "sources, and the caching that produces most of it exists only "
            "because the Agent has no individual variation - the same property "
            "Phase 10's S arm found to be the expensive one"),
        "next_experiment": "N/A - completes Phase 9d's acceptance criteria",
    })
    print(f"\n  Wrote {RESULTS_ROOT / 'kpi.csv'}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
