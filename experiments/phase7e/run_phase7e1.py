"""Run Phase 7e-1 — mechanism calibration. No learner is trained here.

Sweeps the loyalty stock's investment channel (delta) and saturation scale
(L*) at flat prices, and asks gate 1 of each cell: is there a persistent,
non-saturated state at all? A cell that fails gate 1 cannot support a
contextual policy, and saying so before training one is the point of the
whole sub-stage.

Also runs an exhaustive oracle price sweep per cell, which supplies gate 2's
baseline and answers on its own whether the mechanism moved the static
optimum away from the base environment's 2.60.

    python experiments/phase7e/run_phase7e1.py
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
warnings.filterwarnings("ignore", message="Degrees of freedom <= 0")
warnings.filterwarnings("ignore", message="Mean of empty slice")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from market_sim import acceptance, experiment_log  # noqa: E402
from market_sim.config import (  # noqa: E402
    PHASE7E_BETA,
    PHASE7E_CELLS,
    PHASE7E_COUNTER,
    PHASE7E_LMAX,
    PHASE7E_RHO,
    PHASE7E_SHOCK_WEEK,
)
from market_sim.engine import run_season_seeds  # noqa: E402

RESULTS_ROOT = REPO_ROOT / "results" / "phase7e1"
LOG_PATH = REPO_ROOT / "experiment_log.csv"

#: Wide enough that a mechanism-induced shift in the optimum shows up as a
#: peak rather than as a boundary. A boundary argmax is reported as such.
SWEEP_PRICES = np.round(np.arange(1.80, 3.61, 0.05), 2)
SWEEP_SEEDS = tuple(range(20))
BASE_OPTIMUM = 2.60  # the base environment's, for reference

RESEARCH_QUESTION = (
    "Does a persistent, price-sensitive loyalty stock produce a market state "
    "that is neither saturated nor erased by one interruption - the existence "
    "condition a contextual policy needs?"
)


def label(cfg) -> str:
    if cfg.loyalty_model == "streak":
        return "counter (7a-7d)"
    return f"delta={cfg.loyalty_deal_sensitivity:g}, L*={cfg.loyalty_saturation:g}"


def bonus_trajectory(seasons) -> tuple[np.ndarray, np.ndarray]:
    """Per week: median and IQR of the bonus each buyer holds toward its choice.

    Measured on the seller the buyer actually picked that week, so it is the
    bonus that was in force on a live decision rather than an average over
    relationships nobody acted on.
    """
    n_weeks = seasons[0].n_weeks
    med = np.zeros(n_weeks)
    iqr = np.zeros(n_weeks)
    for w in range(n_weeks):
        vals = []
        for s in seasons:
            picked = s.chosen_seller[w]
            live = np.flatnonzero(picked >= 0)
            vals.extend(s.loyalty_bonus[w, live, picked[live]].tolist())
        if vals:
            q1, med[w], q3 = np.percentile(vals, [25, 50, 75])
            iqr[w] = q3 - q1
    return med, iqr


def main() -> int:
    commit = experiment_log.git_commit(REPO_ROOT)
    RESULTS_ROOT.mkdir(parents=True, exist_ok=True)

    print(f"\n=== Phase 7e-1 — mechanism calibration "
          f"(rho={PHASE7E_RHO}, beta={PHASE7E_BETA}, L_max={PHASE7E_LMAX}) ===")
    print(f"  {RESEARCH_QUESTION}\n")
    print(f"  Stock half-life {np.log(0.5) / np.log(PHASE7E_RHO):.1f} weeks; a buyer "
          f"who buys every week converges to L={PHASE7E_BETA / (1 - PHASE7E_RHO):.2f}.\n")

    # ---- the reference cell, which every gate is scored against -------------
    counter_seasons = run_season_seeds(PHASE7E_COUNTER)
    counter_stats = acceptance.saturation_share(PHASE7E_COUNTER, counter_seasons)
    counter_stats["permanent_switch_rate"] = acceptance.permanent_switch_rate(
        PHASE7E_COUNTER, PHASE7E_SHOCK_WEEK
    )
    counter_oracle = acceptance.oracle_flat_price(
        PHASE7E_COUNTER, SWEEP_PRICES, SWEEP_SEEDS
    )

    rows = []
    trajectories = {"counter (7a-7d)": bonus_trajectory(counter_seasons)}
    oracles = {"counter (7a-7d)": counter_oracle}

    print(f"  {'cell':22s} {'saturated':>9s} {'IQR':>6s} {'mean':>6s} "
          f"{'perm.switch':>11s} {'oracle p*':>9s} {'profit':>7s}  gate 1")
    print(f"  {'counter (7a-7d)':22s} {counter_stats['saturated_share']:8.1%} "
          f"{counter_stats['iqr']:6.3f} {counter_stats['mean']:6.3f} "
          f"{counter_stats['permanent_switch_rate']:10.1%} "
          f"{counter_oracle['best_price']:9.2f} {counter_oracle['best_profit']:7.2f}"
          f"  reference")

    for cfg in PHASE7E_CELLS:
        seasons = run_season_seeds(cfg)
        stats = acceptance.saturation_share(cfg, seasons)
        switch = acceptance.permanent_switch_rate(cfg, PHASE7E_SHOCK_WEEK)
        oracle = acceptance.oracle_flat_price(cfg, SWEEP_PRICES, SWEEP_SEEDS)
        criteria = acceptance.evaluate_phase7e1(cfg, seasons, counter_stats, switch)
        passed = all(c.passed for c in criteria)
        trajectories[label(cfg)] = bonus_trajectory(seasons)
        oracles[label(cfg)] = oracle

        boundary = oracle["best_price"] in (SWEEP_PRICES[0], SWEEP_PRICES[-1])
        print(f"  {label(cfg):22s} {stats['saturated_share']:8.1%} "
              f"{stats['iqr']:6.3f} {stats['mean']:6.3f} {switch:10.1%} "
              f"{oracle['best_price']:9.2f} {oracle['best_profit']:7.2f}"
              f"  {'PASS' if passed else 'fail'}"
              f"{'  (p* at sweep boundary)' if boundary else ''}")

        rows.append({
            "cell": cfg.name,
            "delta": cfg.loyalty_deal_sensitivity,
            "saturation": cfg.loyalty_saturation,
            "saturated_share": stats["saturated_share"],
            "bonus_iqr": stats["iqr"],
            "bonus_mean": stats["mean"],
            "permanent_switch_rate": switch,
            "oracle_price": oracle["best_price"],
            "oracle_profit": oracle["best_profit"],
            "gate1a": criteria[0].passed,
            "gate1b": criteria[1].passed,
            "gate1": passed,
            "criteria": criteria,
            "cfg": cfg,
        })

    print("\n  Gate 1 detail, per cell:")
    for row in rows:
        print(f"\n  {label(row['cfg'])}")
        for c in row["criteria"]:
            print(f"    [{'PASS' if c.passed else 'FAIL'}] {c.name}")
            print(f"           {c.measured}")

    survivors = [r for r in rows if r["gate1"]]
    print(f"\n  {len(survivors)} of {len(rows)} cells pass gate 1 and carry to 7e-2.")
    if survivors:
        print("  " + ", ".join(label(r["cfg"]) for r in survivors))

    # ---- artefacts ---------------------------------------------------------
    pd.DataFrame(
        [{k: v for k, v in r.items() if k not in ("criteria", "cfg")} for r in rows]
    ).to_csv(RESULTS_ROOT / "gate1.csv", index=False)
    pd.DataFrame(
        [
            {"cell": name, "price": float(pr), "profit": float(v)}
            for name, o in oracles.items()
            for pr, v in zip(o["prices"], o["profit"])
        ]
    ).to_csv(RESULTS_ROOT / "oracle_sweep.csv", index=False)
    pd.DataFrame(
        {
            "week": np.arange(len(next(iter(trajectories.values()))[0])),
            **{f"{name} median": med for name, (med, _) in trajectories.items()},
            **{f"{name} IQR": iqr for name, (_, iqr) in trajectories.items()},
        }
    ).to_csv(RESULTS_ROOT / "bonus_trajectory.csv", index=False)
    plot(rows, trajectories, oracles, counter_stats)

    best = max(rows, key=lambda r: r["oracle_profit"])
    experiment_log.append_row(LOG_PATH, {
        "experiment_id": "phase7e_calibration", "git_commit": commit,
        "config_file": "src/market_sim/config.py::PHASE7E_CELLS",
        "phase": 7, "seed": "0-29 (gate 1), 0-19 (oracle sweep)",
        "n_buyers": PHASE7E_COUNTER.n_buyers, "n_sellers": PHASE7E_COUNTER.n_sellers,
        "model_used": "rule_based", "decision_type": "N/A",
        "human_benchmark_id": "N/A", "human_benchmark_status": "not_applicable",
        "synthetic_cost_usd": "N/A", "synthetic_latency_seconds": "N/A",
        "research_question": RESEARCH_QUESTION,
        "changed_mechanism": (
            f"loyalty as a per-pair stock (rho={PHASE7E_RHO}, beta={PHASE7E_BETA}, "
            f"L_max={PHASE7E_LMAX}) instead of a bounded streak counter, swept "
            f"over delta x L*"
        ),
        "transaction_count": sum(
            len(w.transactions) for s in counter_seasons for w in s.weeks
        ),
        "participation_rate": round(
            float(np.mean([s.purchase_rate().mean() for s in counter_seasons])), 4
        ),
        "result_summary": (
            f"{len(survivors)}/{len(rows)} cells pass gate 1. Counter reference: "
            f"{counter_stats['saturated_share']:.0%} of attached buyers pinned at "
            f"L_max, permanent switching {counter_stats['permanent_switch_rate']:.0%}, "
            f"oracle optimum {counter_oracle['best_price']:.2f}. Best stock cell "
            f"(delta={best['delta']:g}, L*={best['saturation']:g}): "
            f"{best['saturated_share']:.0%} pinned, switching "
            f"{best['permanent_switch_rate']:.0%}, oracle optimum "
            f"{best['oracle_price']:.2f}."
        ),
        "decision_implication": "N/A - infrastructure phase, no business decision",
        "next_experiment": (
            "Phase 7e-2 intertemporal headroom gate on the surviving cells"
            if survivors else
            "Phase 7e stops: no cell supports a contextual policy"
        ),
    })
    print(f"\n  Wrote {RESULTS_ROOT}\n")
    return 0


def plot(rows, trajectories, oracles, counter_stats) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(15.5, 4.4))

    ax = axes[0]
    for name, (med, iqr) in trajectories.items():
        weeks = np.arange(len(med))
        style = dict(lw=2.0, color="black", ls="--") if "counter" in name else dict(lw=1.2)
        (line,) = ax.plot(weeks, med, label=name, **style)
        if "counter" not in name:
            ax.fill_between(weeks, med - iqr / 2, med + iqr / 2, alpha=0.10,
                            color=line.get_color(), lw=0)
    ax.axhline(PHASE7E_LMAX, ls=":", c="firebrick", lw=1)
    ax.text(1, PHASE7E_LMAX - 0.07, "L_max", fontsize=8, color="firebrick")
    ax.set_xlabel("week")
    ax.set_ylabel("loyalty bonus on the chosen seller")
    ax.set_title("The state, week by week (median, band = IQR)", fontsize=10)
    ax.legend(fontsize=6.5, ncol=2)

    ax = axes[1]
    sat = [r["saturated_share"] for r in rows]
    swi = [r["permanent_switch_rate"] for r in rows]
    ax.axvspan(acceptance.GATE1_MAX_SATURATED_SHARE, 1.0, color="firebrick", alpha=0.06)
    ax.axhspan(
        counter_stats["permanent_switch_rate"]
        - acceptance.GATE1_MIN_SWITCH_ADVANTAGE_PP / 100,
        1.0,
        color="firebrick", alpha=0.06,
    )
    for r in rows:
        ax.scatter(r["saturated_share"], r["permanent_switch_rate"],
                   s=38, c="seagreen" if r["gate1"] else "firebrick", zorder=3)
        ax.annotate(f"{r['delta']:g}/{r['saturation']:g}",
                    (r["saturated_share"], r["permanent_switch_rate"]),
                    textcoords="offset points", xytext=(5, 3), fontsize=6.5)
    ax.scatter(counter_stats["saturated_share"], counter_stats["permanent_switch_rate"],
               s=60, marker="X", c="black", zorder=4, label="counter (7a-7d)")
    ax.set_xlabel("share of attached buyers pinned at L_max  (gate 1a)")
    ax.set_ylabel("permanent switching after one closure  (gate 1b)")
    ax.set_title("Gate 1: shaded is failing. Labels are delta/L*", fontsize=10)
    ax.legend(fontsize=7, loc="lower right")

    ax = axes[2]
    for name, o in oracles.items():
        style = dict(lw=2.0, color="black", ls="--") if "counter" in name else dict(lw=1.1)
        ax.plot(o["prices"], o["profit"], label=name, **style)
        ax.scatter([o["best_price"]], [o["best_profit"]], s=16, zorder=3,
                   c="black" if "counter" in name else None)
    ax.axvline(BASE_OPTIMUM, ls=":", c="firebrick", lw=1)
    ax.text(BASE_OPTIMUM + 0.02, ax.get_ylim()[0] + 0.6,
            f"base env {BASE_OPTIMUM:.2f}", fontsize=7.5, color="firebrick")
    ax.set_xlabel("standing price of one Slow stall")
    ax.set_ylabel("profit per week")
    ax.set_title("Oracle sweep: did the mechanism move the optimum?", fontsize=10)
    ax.legend(fontsize=6.5, ncol=2)

    fig.suptitle(
        "Phase 7e-1 — mechanism calibration: does a state exist to condition on?",
        fontsize=12,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(RESULTS_ROOT / "calibration.png", dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    raise SystemExit(main())
