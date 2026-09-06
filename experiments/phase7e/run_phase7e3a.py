"""Run Phase 7e-3a — does conditioning on the loyalty state pay?

Phase 7c's question, asked in the environment 7c was skipped for lacking. Two
measurements, because a learned null on its own cannot distinguish "there is no
context" from "context is real but costs more to learn than 66 weeks return":

  1. an oracle diagnostic - does the profit-maximizing arm actually depend on
     the loyalty state, when the state is measured and the arm is chosen with
     hindsight?
  2. the learned comparison - LinUCB with the context against the identical
     algorithm with the context removed, both tuned on a discovery block.

    python experiments/phase7e/run_phase7e3a.py
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

from market_sim import acceptance, bandits, experiment_log  # noqa: E402
from market_sim.config import PHASE7E_RHO, phase7e_cell  # noqa: E402
from market_sim.engine import run_season  # noqa: E402

RESULTS_ROOT = REPO_ROOT / "results" / "phase7e3a"
LOG_PATH = REPO_ROOT / "experiment_log.csv"

CARRIED_LMAX, CARRIED_DELTA, ORACLE_PRICE = 3.30, 1.0, 2.65
DISCOVERY_SEEDS = tuple(range(2000, 2060))
EVAL_SEEDS = tuple(range(30))
TARGET = 0

ALPHAS = (0.1, 0.25, 0.5, 1.0)
UCB_CS = (0.25, 0.5, 1.0)

#: The oracle deviation window: one week on a chosen arm, scored over that week
#: and the eight that follow - about two and a half stock half-lives, so an
#: arm's effect on the stock lands inside the window instead of being discarded.
DEVIATION_WINDOW = 9
DEVIATION_WEEKS = tuple(range(10, 56, 2))
DEVIATION_SEEDS = tuple(range(20))

RESEARCH_QUESTION = (
    "Now that a persistent, dispersed loyalty state exists, does a policy that "
    "conditions on it beat one that ignores it?"
)


def environment():
    cell = phase7e_cell(rho=PHASE7E_RHO, delta=CARRIED_DELTA, max_bonus=CARRIED_LMAX)
    return acceptance.split_target_config(cell, ORACLE_PRICE, name="7e3a")


def oracle_context(env) -> pd.DataFrame:
    """Does the best arm depend on the loyalty state, chosen with hindsight?

    7c compared parallel full seasons because its state did not depend on the
    price path. Here it does - running an arm all season *creates* a different
    loyalty state - so the measurement is a one-week deviation from an
    otherwise flat season, scored over the following weeks.
    """
    flat_arm = env.price_arms.index(1.0)
    n_weeks = env.weeks
    scheduled = dataclasses.replace(env, price_rule="policy")
    reference_cfg = dataclasses.replace(env, record_loyalty_bonus=True)

    rows = []
    for seed in DEVIATION_SEEDS:
        reference = run_season(reference_cfg, seed)
        # The seller's own view of its loyalty: mean bonus its buyers hold
        # toward it, the same quantity the learners are handed as context.
        stock = reference.loyalty_bonus[:, :, TARGET].mean(axis=1) / env.loyalty_max_bonus
        base = reference.profits[:, TARGET]
        for week in DEVIATION_WEEKS:
            window = slice(week, week + DEVIATION_WINDOW)
            gains = []
            for arm in range(len(env.price_arms)):
                plan = [flat_arm] * n_weeks
                plan[week] = arm
                policy = acceptance.schedule_policy(TARGET, plan, n_weeks, flat_arm)
                season = run_season(scheduled, seed, policy=policy)
                gains.append(float(season.profits[window, TARGET].sum()
                                   - base[window].sum()))
            rows.append({
                "seed": seed, "week": week, "loyalty_stock": float(stock[week]),
                "best_arm": int(np.argmax(gains)),
                **{f"arm_{env.price_arms[a]:.2f}": g for a, g in enumerate(gains)},
            })
    return pd.DataFrame(rows)


def main() -> int:
    commit = experiment_log.git_commit(REPO_ROOT)
    RESULTS_ROOT.mkdir(parents=True, exist_ok=True)
    env = environment()
    flat_plan = acceptance.one_shot_schedules(env.price_arms, env.weeks)["flat"]

    print("\n=== Phase 7e-3a — does context pay? ===")
    print(f"  {RESEARCH_QUESTION}\n")

    # ---- 1. the oracle diagnostic ------------------------------------------
    dev = oracle_context(env)
    median = float(dev["loyalty_stock"].median())
    low, high = dev[dev["loyalty_stock"] <= median], dev[dev["loyalty_stock"] > median]
    arm_cols = [c for c in dev.columns if c.startswith("arm_")]

    print(f"  Oracle diagnostic — {len(dev)} seller-weeks, one-week deviations "
          f"scored over {DEVIATION_WINDOW} weeks.")
    print(f"  {'loyalty state':26s} {'n':>5s}   " + "  ".join(f"{c[4:]:>7s}" for c in arm_cols) + "   best")
    for label, sub in (("all weeks", dev),
                       (f"stock <= median ({median:.3f})", low),
                       ("stock > median", high)):
        means = sub[arm_cols].mean()
        best = arm_cols[int(np.argmax(means.to_numpy()))][4:]
        print(f"  {label:26s} {len(sub):5d}   "
              + "  ".join(f"{v:7.2f}" for v in means) + f"   {best}")
    invariant = (
        arm_cols[int(np.argmax(low[arm_cols].mean().to_numpy()))]
        == arm_cols[int(np.argmax(high[arm_cols].mean().to_numpy()))]
    )
    print(f"  -> the profit-maximizing arm is "
          f"{'the same on both sides' if invariant else 'DIFFERENT across the split'}"
          f" of the loyalty state.")

    # ---- 2. tuning on the discovery block ----------------------------------
    print(f"\n  Tuning on seeds {DISCOVERY_SEEDS[0]}-{DISCOVERY_SEEDS[-1]}:")
    flat_disc = acceptance.schedule_profit(env, flat_plan, DISCOVERY_SEEDS, TARGET)
    tuning = []
    for c in UCB_CS:
        v = bandits.run(env, functools.partial(bandits.UCB1, c=c), DISCOVERY_SEEDS, TARGET)
        tuning.append({"learner": "UCB1", "param": c, "profit": float(v.mean())})
    for alpha in ALPHAS:
        for features, name in ((bandits.BLIND, "LinUCB blind"),
                               (bandits.CONTEXT, "LinUCB context")):
            v = bandits.run(
                env, functools.partial(bandits.LinUCB, alpha=alpha, features=features),
                DISCOVERY_SEEDS, TARGET)
            tuning.append({"learner": name, "param": alpha, "profit": float(v.mean())})
    tune = pd.DataFrame(tuning)
    best = tune.loc[tune.groupby("learner")["profit"].idxmax()].set_index("learner")
    print(f"  {'learner':16s} {'best param':>11s} {'profit':>8s}")
    for name, row in best.iterrows():
        print(f"  {name:16s} {row['param']:11g} {row['profit']:8.2f}")
    print(f"  {'flat @ oracle':16s} {'-':>11s} {flat_disc.mean():8.2f}")

    # ---- 3. the held-out verdict -------------------------------------------
    flat_eval = acceptance.schedule_profit(env, flat_plan, EVAL_SEEDS, TARGET)
    scored = {"flat at the oracle price": flat_eval}
    for name in ("UCB1", "LinUCB blind", "LinUCB context"):
        param = float(best.loc[name, "param"])
        factory = (functools.partial(bandits.UCB1, c=param) if name == "UCB1"
                   else functools.partial(
                       bandits.LinUCB, alpha=param,
                       features=bandits.BLIND if "blind" in name else bandits.CONTEXT))
        scored[name] = bandits.run(env, factory, EVAL_SEEDS, TARGET)

    print(f"\n  Held-out block, seeds 0-29:")
    for name, v in scored.items():
        print(f"    {name:26s} {v.mean():6.2f}/wk")

    criteria = acceptance.evaluate_phase7e3a(
        scored["LinUCB context"], scored["LinUCB blind"], scored["UCB1"], flat_eval
    )
    for c in criteria:
        mark = "----" if not c.graded else ("PASS" if c.passed else "FAIL")
        print(f"\n    [{mark}] {c.name}\n           {c.measured}")

    # ---- artefacts ---------------------------------------------------------
    dev.to_csv(RESULTS_ROOT / "oracle_context.csv", index=False)
    tune.to_csv(RESULTS_ROOT / "tuning.csv", index=False)
    pd.DataFrame({"seed": EVAL_SEEDS, **scored}).to_csv(
        RESULTS_ROOT / "held_out.csv", index=False)
    plot(dev, tune, scored, arm_cols, median, env)

    gain, lo, hi = acceptance.mean_difference_ci(
        scored["LinUCB context"], scored["LinUCB blind"])
    scale = float(scored["LinUCB blind"].mean())
    verdict = acceptance.equivalence_verdict(
        lo / scale, hi / scale, acceptance.MATERIALITY_PROFIT_PCT)
    experiment_log.append_row(LOG_PATH, {
        "experiment_id": "phase7e3a_context", "git_commit": commit,
        "config_file": "src/market_sim/bandits.py",
        "phase": 7,
        "seed": f"tune {DISCOVERY_SEEDS[0]}-{DISCOVERY_SEEDS[-1]}, evaluate 0-29",
        "n_buyers": env.n_buyers, "n_sellers": env.n_sellers,
        "model_used": "rule_based", "decision_type": "N/A",
        "human_benchmark_id": "N/A", "human_benchmark_status": "not_applicable",
        "synthetic_cost_usd": "N/A", "synthetic_latency_seconds": "N/A",
        "research_question": RESEARCH_QUESTION,
        "changed_mechanism": (
            "LinUCB conditioned on the loyalty stock and the week, against the "
            "identical algorithm restricted to an intercept; both tuned on the "
            "discovery block, both given the same initial arm sweep"
        ),
        "transaction_count": "N/A", "participation_rate": "N/A",
        "result_summary": (
            f"Oracle diagnostic: the profit-maximizing arm is "
            f"{'invariant to' if invariant else 'sensitive to'} the loyalty state "
            f"across a median split of {len(dev)} seller-weeks. Learned: context "
            f"{scored['LinUCB context'].mean():.2f} vs blind {scale:.2f} per week, "
            f"{gain / scale:+.1%} (95% CI [{lo / scale:+.1%}, {hi / scale:+.1%}]), "
            f"verdict {verdict}. Every learner loses to flat pricing at the oracle "
            f"price ({flat_eval.mean():.2f})."
        ),
        "decision_implication": "N/A - infrastructure phase, no business decision",
        "next_experiment": "Phase 7e-3b: the Q-network, which gate 2 licensed",
    })
    print(f"\n  Wrote {RESULTS_ROOT}\n")
    return 0


def plot(dev, tune, scored, arm_cols, median, env) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(15.5, 4.4))

    ax = axes[0]
    prices = [float(c[4:]) * ORACLE_PRICE for c in arm_cols]
    for label, sub, style in (
        ("loyalty stock ≤ median", dev[dev["loyalty_stock"] <= median],
         dict(color="tab:blue", marker="o")),
        ("loyalty stock > median", dev[dev["loyalty_stock"] > median],
         dict(color="tab:red", marker="s")),
    ):
        means = sub[arm_cols].mean().to_numpy()
        sems = sub[arm_cols].sem().to_numpy()
        ax.errorbar(prices, means, yerr=1.96 * sems, lw=1.5, capsize=3,
                    label=label, **style)
        ax.scatter([prices[int(np.argmax(means))]], [means.max()], s=110,
                   facecolors="none", edgecolors=style["color"], lw=1.8, zorder=4)
    ax.axhline(0, c="0.5", lw=1)
    ax.set_xlabel("price posted for one week")
    ax.set_ylabel(f"profit over the next {DEVIATION_WINDOW} weeks, vs flat")
    ax.set_title("Oracle: does the best arm move with the state?", fontsize=10)
    ax.legend(fontsize=7.5)

    ax = axes[1]
    for name, style in (("UCB1", dict(color="0.45", ls=":")),
                        ("LinUCB blind", dict(color="tab:orange")),
                        ("LinUCB context", dict(color="tab:blue"))):
        sub = tune[tune["learner"] == name].sort_values("param")
        ax.plot(sub["param"], sub["profit"], marker="o", lw=1.5, label=name, **style)
    ax.set_xscale("log")
    ax.set_xlabel("exploration parameter (alpha, or c for UCB1)")
    ax.set_ylabel("profit per week, discovery block")
    ax.set_title("Tuned on discovery, so neither wins on a knob", fontsize=10)
    ax.legend(fontsize=7.5)

    ax = axes[2]
    names = list(scored)
    means = [scored[n].mean() for n in names]
    sems = [scored[n].std(ddof=1) / np.sqrt(len(scored[n])) for n in names]
    colours = ["0.25", "0.6", "tab:orange", "tab:blue"]
    ax.barh(range(len(names)), means, xerr=[1.96 * s for s in sems],
            color=colours, height=0.6, capsize=4)
    ax.set_yticks(range(len(names)))
    ax.set_yticklabels(names, fontsize=8.5)
    ax.invert_yaxis()
    ax.set_xlim(min(means) * 0.9, max(means) * 1.04)
    ax.set_xlabel("profit per week, held-out seeds")
    ax.set_title("Every learner loses to the price it was hunting", fontsize=10)

    fig.suptitle("Phase 7e-3a — does conditioning on the loyalty state pay?",
                 fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(RESULTS_ROOT / "context.png", dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    raise SystemExit(main())
