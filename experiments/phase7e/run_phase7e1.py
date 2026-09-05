"""Run Phase 7e-1 — mechanism calibration. No learner is trained here.

Holds lock-in strength fixed and sweeps the memory horizon. The first version
of this stage swept the investment channel and the saturation scale at a
pinned ceiling; that run is committed, and what it found was that the pinned
ceiling made the stock bind about a third as hard as the counter it was meant
to enrich, which made every gate below it uninterpretable. See
docs/phase_specifications.md, Phase 7e-1.

So L_max is now solved per cell against the counter's own incumbency
advantage, and rho is swept over four memory half-lives with beta moving to
hold the steady-state stock fixed. The one gate that can fail on the
mechanism's account is whether memory still reaches eight weeks back.

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
    PHASE7E_CELLS,
    PHASE7E_COUNTER,
    PHASE7E_CURVATURE,
    PHASE7E_DELTA,
    PHASE7E_RHO,
    PHASE7E_SATURATION,
)
from market_sim.engine import run_season_seeds  # noqa: E402

RESULTS_ROOT = REPO_ROOT / "results" / "phase7e1"
LOG_PATH = REPO_ROOT / "experiment_log.csv"

LAGS = (1, 2, 4, 8, 12, 16)
#: Wide enough that a mechanism-induced shift in the optimum shows as a peak
#: rather than as a boundary. Run only on the cell carried forward: it is the
#: expensive measurement, and gate 2 needs it for one cell.
SWEEP_PRICES = np.round(np.arange(1.80, 3.61, 0.05), 2)
SWEEP_SEEDS = tuple(range(20))
BASE_OPTIMUM = 2.60  # the base environment's, for reference

RESEARCH_QUESTION = (
    "With lock-in strength held equal to the base environment's, does a "
    "persistent loyalty stock reach further back in time than a three-week "
    "counter - the existence condition a multi-week policy needs?"
)


def summarize(cfg, seasons) -> dict[str, float]:
    return {
        "pair_stability": float(
            np.nanmean([s.pair_stability()[30:] for s in seasons])
        ),
        "purchase_rate": float(np.mean([s.purchase_rate().mean() for s in seasons])),
        "profit_per_week": float(
            np.mean([s.profits.sum(axis=1).mean() for s in seasons])
        ),
    }


def main() -> int:
    commit = experiment_log.git_commit(REPO_ROOT)
    RESULTS_ROOT.mkdir(parents=True, exist_ok=True)

    print("\n=== Phase 7e-1 — mechanism calibration ===")
    print(f"  {RESEARCH_QUESTION}\n")
    print(f"  Held fixed: L* = {PHASE7E_SATURATION}, u = S/L* = {PHASE7E_CURVATURE} "
          f"(the empirical contrast maximum), delta = {PHASE7E_DELTA} (inert at "
          f"flat prices; calibrated at 7e-2).")
    print("  Swept: rho, with beta = u * L* * (1 - rho) so the steady-state "
          "stock does not move with it.")
    print("  Calibrated per cell: L_max, solved so incumbency advantage matches "
          "the counter's.\n")

    # ---- the reference cell every gate is scored against --------------------
    counter_seasons = run_season_seeds(PHASE7E_COUNTER)
    counter = acceptance.saturation_share(PHASE7E_COUNTER, counter_seasons)
    counter["contrast"] = acceptance.lockin_contrast(counter_seasons)
    counter["horizon"] = acceptance.memory_horizon(PHASE7E_COUNTER, lags=LAGS)
    counter.update(summarize(PHASE7E_COUNTER, counter_seasons))

    print(f"  {'cell':16s} {'half-life':>9s} {'beta':>6s} {'L_max':>6s} "
          f"{'contrast':>8s} {'lag1':>7s} {'lag8':>7s} {'vs ctr':>7s} "
          f"{'pairstab':>8s} {'purch':>6s}  gate 1b")
    print(f"  {'counter (7a-7d)':16s} {'cap 3':>9s} {'-':>6s} "
          f"{PHASE7E_COUNTER.max_loyalty_bonus():6.2f} {counter['contrast']:8.3f} "
          f"{counter['horizon'][1]:+7.3f} {counter['horizon'][8]:+7.3f} "
          f"{1.0:7.2f} {counter['pair_stability']:8.3f} "
          f"{counter['purchase_rate']:6.3f}  reference")

    rows, horizons, criteria_by_cell = [], {"counter (7a-7d)": counter["horizon"]}, {}
    for seed_cfg in PHASE7E_CELLS:
        cfg, contrast = acceptance.calibrate_max_bonus(seed_cfg, counter["contrast"])
        seasons = run_season_seeds(cfg)
        horizon = acceptance.memory_horizon(cfg, lags=LAGS)
        criteria = acceptance.evaluate_phase7e1(cfg, seasons, counter, horizon, contrast)
        stats = summarize(cfg, seasons)
        ratio = horizon[8] / counter["horizon"][8]
        label = f"rho={cfg.loyalty_retention:g}"
        horizons[label] = horizon
        criteria_by_cell[label] = criteria

        print(f"  {label:16s} "
              f"{np.log(0.5) / np.log(cfg.loyalty_retention):8.1f}w "
              f"{cfg.loyalty_increment:6.3f} {cfg.loyalty_max_bonus:6.2f} "
              f"{contrast:8.3f} {horizon[1]:+7.3f} {horizon[8]:+7.3f} "
              f"{ratio:7.2f} {stats['pair_stability']:8.3f} "
              f"{stats['purchase_rate']:6.3f}  "
              f"{'PASS' if criteria[0].passed else 'fail'}")

        rows.append({
            "cell": cfg.name, "rho": cfg.loyalty_retention,
            "half_life_weeks": float(np.log(0.5) / np.log(cfg.loyalty_retention)),
            "beta": cfg.loyalty_increment, "calibrated_l_max": cfg.loyalty_max_bonus,
            "contrast": contrast, "horizon_lag8": horizon[8],
            "horizon_ratio": ratio,
            **stats,
            "gate1b": criteria[0].passed, "control_ok": criteria[1].passed,
            "cfg": cfg, "criteria": criteria,
        })

    print("\n  Gate 1 detail, per cell:")
    for label, criteria in criteria_by_cell.items():
        print(f"\n  {label}")
        for c in criteria:
            mark = "----" if not c.graded else ("PASS" if c.passed else "FAIL")
            print(f"    [{mark}] {c.name}")
            print(f"           {c.measured}")

    survivors = [r for r in rows if r["gate1b"] and r["control_ok"]]
    print(f"\n  {len(survivors)} of {len(rows)} cells pass gate 1.")

    # ---- the cell carried forward, and its oracle sweep --------------------
    carried = next((r for r in survivors if r["rho"] == PHASE7E_RHO), None)
    if carried is None and survivors:
        carried = max(survivors, key=lambda r: r["horizon_ratio"])
    oracles = {}
    if carried is not None:
        print(f"\n  Carrying rho={carried['rho']:g} into 7e-2 "
              f"(the registered baseline)." if carried["rho"] == PHASE7E_RHO
              else f"\n  Registered rho failed; carrying rho={carried['rho']:g}.")
        oracles["counter (7a-7d)"] = acceptance.oracle_flat_price(
            PHASE7E_COUNTER, SWEEP_PRICES, SWEEP_SEEDS
        )
        oracles[f"rho={carried['rho']:g}"] = acceptance.oracle_flat_price(
            carried["cfg"], SWEEP_PRICES, SWEEP_SEEDS
        )
        for name, o in oracles.items():
            edge = o["best_price"] in (SWEEP_PRICES[0], SWEEP_PRICES[-1])
            print(f"    oracle optimum, {name}: {o['best_price']:.2f} "
                  f"({o['best_profit']:.2f}/wk)"
                  f"{'  [at sweep boundary]' if edge else ''}")

    # ---- artefacts ---------------------------------------------------------
    pd.DataFrame(
        [{k: v for k, v in r.items() if k not in ("cfg", "criteria")} for r in rows]
    ).to_csv(RESULTS_ROOT / "gate1.csv", index=False)
    pd.DataFrame(
        [{"cell": name, "lag": lag, "excess_repeat_rate": v}
         for name, h in horizons.items() for lag, v in h.items()]
    ).to_csv(RESULTS_ROOT / "memory_horizon.csv", index=False)
    if oracles:
        pd.DataFrame(
            [{"cell": name, "price": float(p), "profit": float(v)}
             for name, o in oracles.items()
             for p, v in zip(o["prices"], o["profit"])]
        ).to_csv(RESULTS_ROOT / "oracle_sweep.csv", index=False)
    plot(rows, horizons, oracles, counter)

    if carried is not None:
        carried_oracle = oracles[f"rho={carried['rho']:g}"]
        carried_summary = (
            f"Carried rho={carried['rho']:g} (beta={carried['beta']:.2f}, "
            f"L_max={carried['calibrated_l_max']:.2f}): lag-8 "
            f"{carried['horizon_lag8']:+.3f} = {carried['horizon_ratio']:.2f}x the "
            f"counter's, oracle optimum {carried_oracle['best_price']:.2f}."
        )
    else:
        carried_summary = "No cell passed; 7e stops here."

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
            "loyalty as a per-pair stock with L_max calibrated to the counter's "
            "incumbency advantage; rho swept over half-lives 3.1-13.5 weeks with "
            "beta holding the steady-state stock fixed"
        ),
        "transaction_count": sum(
            len(w.transactions) for s in counter_seasons for w in s.weeks
        ),
        "participation_rate": round(counter["purchase_rate"], 4),
        "result_summary": (
            f"{len(survivors)}/{len(rows)} cells pass gate 1b. Counter: lag-8 "
            f"excess repeat {counter['horizon'][8]:+.3f}, incumbency advantage "
            f"{counter['contrast']:.3f}, pair stability "
            f"{counter['pair_stability']:.3f}. " + carried_summary
        ),
        "decision_implication": "N/A - infrastructure phase, no business decision",
        "next_experiment": (
            "Phase 7e-2 intertemporal headroom gate, delta ladder"
            if survivors else "Phase 7e stops: no mechanism supports a stateful policy"
        ),
    })
    print(f"\n  Wrote {RESULTS_ROOT}\n")
    return 0


def plot(rows, horizons, oracles, counter) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(15.5, 4.4))

    ax = axes[0]
    for name, h in horizons.items():
        lags = sorted(h)
        style = (dict(lw=2.2, color="black", ls="--", marker="o", ms=4)
                 if "counter" in name else dict(lw=1.4, marker="o", ms=3))
        ax.plot(lags, [h[k] for k in lags], label=name, **style)
    ax.axvline(3, ls=":", c="firebrick", lw=1)
    ax.text(3.15, ax.get_ylim()[1] * 0.92, "counter's cap", fontsize=7.5, color="firebrick")
    ax.axhline(0, c="0.7", lw=0.8)
    ax.set_xlabel("lag (weeks)")
    ax.set_ylabel("excess repeat rate over memory-OFF")
    ax.set_title("How far back memory reaches (gate 1b)", fontsize=10)
    ax.legend(fontsize=7.5)

    ax = axes[1]
    x = [r["half_life_weeks"] for r in rows]
    ax.plot(x, [r["horizon_ratio"] for r in rows], marker="o", color="tab:blue",
            label="lag-8 memory, x counter")
    ax.axhline(acceptance.GATE1_MIN_HORIZON_RATIO, ls="--", c="firebrick", lw=1)
    ax.text(x[0], acceptance.GATE1_MIN_HORIZON_RATIO + 0.05,
            f"gate 1b threshold {acceptance.GATE1_MIN_HORIZON_RATIO:g}x",
            fontsize=7.5, color="firebrick")
    ax.axhline(1.0, ls=":", c="0.5", lw=1)
    for r in rows:
        ax.annotate(f"rho={r['rho']:g}\nL_max={r['calibrated_l_max']:.1f}",
                    (r["half_life_weeks"], r["horizon_ratio"]),
                    textcoords="offset points", xytext=(4, -14), fontsize=6.5)
    ax.set_xlabel("stock half-life (weeks)")
    ax.set_ylabel("lag-8 memory, multiple of the counter's")
    ax.set_title("A longer half-life buys less memory, not more", fontsize=10)
    ax.set_ylim(0, max(r["horizon_ratio"] for r in rows) * 1.25)
    ax.legend(fontsize=7.5)

    ax = axes[2]
    if oracles:
        for name, o in oracles.items():
            style = (dict(lw=2.2, color="black", ls="--") if "counter" in name
                     else dict(lw=1.6, color="tab:blue"))
            ax.plot(o["prices"], o["profit"], label=name, **style)
            ax.scatter([o["best_price"]], [o["best_profit"]], s=22, zorder=3,
                       c="black" if "counter" in name else "tab:blue")
            ax.annotate(f"{o['best_price']:.2f}", (o["best_price"], o["best_profit"]),
                        textcoords="offset points", xytext=(4, 4), fontsize=7.5)
        ax.axvline(BASE_OPTIMUM, ls=":", c="firebrick", lw=1)
        ax.legend(fontsize=7.5)
    ax.set_xlabel("standing price of one Slow stall")
    ax.set_ylabel("profit per week")
    ax.set_title("Oracle sweep: gate 2's baseline", fontsize=10)

    fig.suptitle(
        "Phase 7e-1 — with lock-in strength held equal, does memory reach further?",
        fontsize=12,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(RESULTS_ROOT / "calibration.png", dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    raise SystemExit(main())
