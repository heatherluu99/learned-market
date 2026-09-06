"""Run Phase 7e-3b — can a learner find the schedule a hand search found?

7e-2 established that investing sixteen weeks at 0.90x the standing price and
then returning to it beats flat pricing by 2.6%, and that the same path with
the investment channel switched off loses money. So the thing to find is known
to exist, its value is known, and it is expressible in the policy's own state -
`season_fraction` alone encodes "discount early, stop later". A null here is a
statement about learning, not about the market, which is what makes this a
sharper test than 7d's.

    python experiments/phase7e/run_phase7e3b.py
"""

from __future__ import annotations

import dataclasses
import functools
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

from market_sim import acceptance, bandits, experiment_log, rl  # noqa: E402
from market_sim.config import PHASE7E_RHO, phase7e_cell  # noqa: E402

RESULTS_ROOT = REPO_ROOT / "results" / "phase7e3b"
LOG_PATH = REPO_ROOT / "experiment_log.csv"

CARRIED_LMAX, CARRIED_DELTA, ORACLE_PRICE = 3.30, 1.0, 2.65
#: Disjoint from 7e-3a's tuning block (2000-2059) and from every evaluation
#: seed below. Reused from 7d so the two phases train on the same block.
TRAIN_SEEDS = tuple(range(1000, 1120))
EVAL_SEEDS = tuple(range(30))
RESOLUTION_SEEDS = tuple(range(300))
TARGET = 0
#: The target stall earns about 43 a week here against Phase 7d's 13, so the
#: scale that kept 7d's value targets in range would leave these near 1.5.
REWARD_SCALE = 50.0
#: 7e-2's winner, the policy class's known-attainable ceiling.
BEST_SCHEDULE = "invest 16wk @0.90x -> 1.00x"

RESEARCH_QUESTION = (
    "A sustained investment schedule is known to beat the best standing price "
    "here by 2.6%. Can a multi-week learner find it?"
)


def environment():
    cell = phase7e_cell(rho=PHASE7E_RHO, delta=CARRIED_DELTA, max_bonus=CARRIED_LMAX)
    return acceptance.split_target_config(cell, ORACLE_PRICE, name="7e3b")


def tuned_alpha() -> float:
    """The blind LinUCB's alpha, as tuned on 7e-3a's discovery block."""
    tune = pd.read_csv(REPO_ROOT / "results/phase7e3a/tuning.csv")
    blind = tune[tune["learner"] == "LinUCB blind"]
    return float(blind.loc[blind["profit"].idxmax(), "param"])


def rl_profit(env, net, seeds) -> tuple[np.ndarray, np.ndarray]:
    """Per seed: the target's mean weekly profit, and its weekly price path."""
    scheduled = dataclasses.replace(env, price_rule="policy")
    seasons = rl.evaluate(scheduled, net, tuple(seeds), rl.FEATURES_7E,
                          REWARD_SCALE, TARGET, env.price_arms.index(1.0))
    profit = np.array([float(s.profits[:, TARGET].mean()) for s in seasons])
    prices = np.array([s.posted_prices[:, TARGET] for s in seasons])
    return profit, prices


def main() -> int:
    commit = experiment_log.git_commit(REPO_ROOT)
    RESULTS_ROOT.mkdir(parents=True, exist_ok=True)
    env = environment()
    plans = {
        **acceptance.one_shot_schedules(env.price_arms, env.weeks),
        **acceptance.cyclic_schedules(env.price_arms, env.weeks),
    }
    alpha = tuned_alpha()

    print("\n=== Phase 7e-3b — can a learner find the schedule? ===")
    print(f"  {RESEARCH_QUESTION}\n")
    print(f"  Training on seeds {TRAIN_SEEDS[0]}-{TRAIN_SEEDS[-1]}, disjoint from "
          f"the 2000-2059 tuning block and every evaluation seed.")
    print(f"  Features: {', '.join(rl.FEATURES_7E)}. gamma = 0.9, about a "
          f"ten-week horizon.\n")

    net = rl.train_policy(
        dataclasses.replace(env, price_rule="policy"), TRAIN_SEEDS,
        gamma=0.9, epochs=6, features=rl.FEATURES_7E, reward_scale=REWARD_SCALE,
        target=TARGET, flat_arm=env.price_arms.index(1.0),
    )

    def score(seeds):
        rl_p, rl_prices = rl_profit(env, net, seeds)
        return {
            "7e-2 schedule": acceptance.schedule_profit(env, plans[BEST_SCHEDULE], seeds, TARGET),
            "flat at the oracle price": acceptance.schedule_profit(env, plans["flat"], seeds, TARGET),
            "LinUCB blind": bandits.run(
                env, functools.partial(bandits.LinUCB, alpha=alpha,
                                       features=bandits.BLIND), seeds, TARGET),
            "Q-network (7e-3b)": rl_p,
        }, rl_prices

    scored, prices = score(EVAL_SEEDS)
    seed_block = EVAL_SEEDS
    print(f"  Held-out block, seeds {seed_block[0]}-{seed_block[-1]}:")
    for name, v in scored.items():
        print(f"    {name:28s} {v.mean():6.2f}/wk")
    criteria = acceptance.evaluate_phase7e3b(
        scored["Q-network (7e-3b)"], scored["LinUCB blind"],
        scored["7e-2 schedule"], scored["flat at the oracle price"])
    for c in criteria:
        mark = "----" if not c.graded else ("PASS" if c.passed else "FAIL")
        print(f"\n    [{mark}] {c.name}\n           {c.measured}")

    if not criteria[0].passed:
        print(f"\n  Inconclusive at {len(EVAL_SEEDS)} seeds. Widening to "
              f"{len(RESOLUTION_SEEDS)}, once, as registered at 7e-3a.")
        scored, prices = score(RESOLUTION_SEEDS)
        seed_block = RESOLUTION_SEEDS
        for name, v in scored.items():
            print(f"    {name:28s} {v.mean():6.2f}/wk")
        criteria = acceptance.evaluate_phase7e3b(
            scored["Q-network (7e-3b)"], scored["LinUCB blind"],
            scored["7e-2 schedule"], scored["flat at the oracle price"])
        for c in criteria:
            mark = "----" if not c.graded else ("PASS" if c.passed else "FAIL")
            print(f"\n    [{mark}] {c.name}\n           {c.measured}")

    passed = criteria[0].passed and criteria[1].passed
    print(f"\n  Gate 3b {'PASSES' if passed else 'does NOT pass'}.")
    if not passed:
        print("  Stopping rule: the finding is recorded as measured. No parameter "
              "is tuned, no arm widened, no network enlarged until it wins.")

    # ---- artefacts ---------------------------------------------------------
    pd.DataFrame({"seed": seed_block, **scored}).to_csv(
        RESULTS_ROOT / "held_out.csv", index=False)
    pd.DataFrame(
        {"week": np.arange(prices.shape[1]),
         "q_network_mean_price": prices.mean(axis=0),
         "schedule_price": np.array(env.price_arms)[plans[BEST_SCHEDULE]] * ORACLE_PRICE}
    ).to_csv(RESULTS_ROOT / "price_paths.csv", index=False)
    plot(scored, prices, plans, env)

    gain, lo, hi = acceptance.mean_difference_ci(
        scored["Q-network (7e-3b)"], scored["LinUCB blind"])
    scale = float(scored["LinUCB blind"].mean())
    verdict = acceptance.equivalence_verdict(
        lo / scale, hi / scale, acceptance.MATERIALITY_PROFIT_PCT)
    ceiling = float(scored["7e-2 schedule"].mean())
    experiment_log.append_row(LOG_PATH, {
        "experiment_id": "phase7e3b_horizon", "git_commit": commit,
        "config_file": "src/market_sim/rl.py::train_policy",
        "phase": 7,
        "seed": (f"train {TRAIN_SEEDS[0]}-{TRAIN_SEEDS[-1]}, evaluate "
                 f"{seed_block[0]}-{seed_block[-1]}"),
        "n_buyers": env.n_buyers, "n_sellers": env.n_sellers,
        "model_used": "rule_based", "decision_type": "N/A",
        "human_benchmark_id": "N/A", "human_benchmark_status": "not_applicable",
        "synthetic_cost_usd": "N/A", "synthetic_latency_seconds": "N/A",
        "research_question": RESEARCH_QUESTION,
        "changed_mechanism": (
            "Q-network on a ten-week discounted return with the loyalty stock "
            "added to its features, one seller learning against a flat market, "
            "in the environment where a hand-found schedule is worth +2.6%"
        ),
        "transaction_count": "N/A", "participation_rate": "N/A",
        "result_summary": (
            f"Q-network {scored['Q-network (7e-3b)'].mean():.2f} vs the better "
            f"bandit {scale:.2f} per week, {gain / scale:+.1%} (95% CI "
            f"[{lo / scale:+.1%}, {hi / scale:+.1%}]), verdict {verdict}. The "
            f"attainable ceiling - 7e-2's hand-found schedule - is {ceiling:.2f}, "
            f"and flat at the oracle price is "
            f"{scored['flat at the oracle price'].mean():.2f}."
        ),
        "decision_implication": "N/A - infrastructure phase, no business decision",
        "next_experiment": "Phase 8 — endogenous market structure",
    })
    print(f"\n  Wrote {RESULTS_ROOT}\n")
    return 0


def plot(scored, prices, plans, env) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(15.5, 4.4))

    ax = axes[0]
    weeks = np.arange(prices.shape[1])
    ax.plot(weeks, np.array(env.price_arms)[plans[BEST_SCHEDULE]] * ORACLE_PRICE,
            lw=2.0, color="seagreen", label=f"7e-2's schedule (+2.6%)")
    ax.plot(weeks, prices.mean(axis=0), lw=1.6, color="tab:blue",
            label="Q-network, mean over seeds")
    ax.fill_between(weeks, np.percentile(prices, 25, axis=0),
                    np.percentile(prices, 75, axis=0), color="tab:blue",
                    alpha=0.15, lw=0)
    ax.axhline(ORACLE_PRICE, ls="--", c="black", lw=1.1, label="flat at the optimum")
    ax.set_xlabel("week")
    ax.set_ylabel("posted price")
    ax.set_title("Did it find 'discount early, then stop'?", fontsize=10)
    ax.legend(fontsize=7.5)

    ax = axes[1]
    names = list(scored)
    means = [scored[n].mean() for n in names]
    sems = [scored[n].std(ddof=1) / np.sqrt(len(scored[n])) for n in names]
    colours = ["seagreen", "0.3", "tab:orange", "tab:blue"]
    ax.barh(range(len(names)), means, xerr=[1.96 * s for s in sems],
            color=colours, height=0.6, capsize=4)
    ax.set_yticks(range(len(names)))
    ax.set_yticklabels(names, fontsize=8.5)
    ax.invert_yaxis()
    ax.set_xlim(min(means) * 0.93, max(means) * 1.03)
    ax.set_xlabel("profit per week, held-out seeds")
    ax.set_title("The ladder: two rungs a learner could reach", fontsize=10)

    ax = axes[2]
    rl_p, blind = scored["Q-network (7e-3b)"], scored["LinUCB blind"]
    diff = (rl_p - blind) / blind.mean() * 100
    ax.axhline(0, c="0.4", lw=1)
    ax.scatter(range(len(diff)), diff, s=14, c="tab:blue", zorder=3, alpha=0.7)
    mean = float(diff.mean())
    sem = float(diff.std(ddof=1) / np.sqrt(len(diff)))
    ax.axhline(mean, color="tab:blue", lw=1.5)
    ax.fill_between([-1, len(diff)], mean - 1.96 * sem, mean + 1.96 * sem,
                    color="tab:blue", alpha=0.18, lw=0)
    for bound in (-acceptance.MATERIALITY_PROFIT_PCT, acceptance.MATERIALITY_PROFIT_PCT):
        ax.axhline(bound, ls="--", c="firebrick", lw=1)
    ax.set_xlim(-1, len(diff))
    ax.set_xlabel("evaluation seed")
    ax.set_ylabel("Q-network vs the better bandit (%)")
    ax.set_title(f"{mean:+.1f}% (95% CI ±{1.96 * sem:.1f}), band is ±5%", fontsize=10)

    fig.suptitle("Phase 7e-3b — a trade-off that exists, and a learner sent to find it",
                 fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(RESULTS_ROOT / "horizon.png", dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    raise SystemExit(main())
