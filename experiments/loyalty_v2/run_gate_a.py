"""Loyalty v2, Gate A — which loyalty regimes does the human evidence rule out?

For each cell of the pre-registered `rho x gamma` grid, the simulator's state
dependence is measured by the same causal ablation Phase 10 used for its
`+0.109`: identical seeds re-run with the loyalty bonus disabled and fixed
preference retained, so memory is removed and heterogeneity is held constant.
Neither arm draws randomness, so treatment and control are paired down to the
draw and the difference between them is the memory's doing.

Each cell is then marked by whether it lands inside Phase 10's human interval.
The output is a region, not a winner: the question is which regimes the human
evidence excludes, and picking a best cell is explicitly not the goal.

This is calibration against an interval, not estimation. No likelihood is
maximized and no posterior over (rho, gamma) is formed.
"""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from market_sim import config, experiment_log  # noqa: E402
from market_sim.acceptance import memory_off  # noqa: E402
from market_sim.engine import run_season  # noqa: E402

RESULTS_ROOT = REPO_ROOT / "results" / "loyalty_v2"
LOG_PATH = REPO_ROOT / "experiment_log.csv"

#: Phase 10's bracket. The lower end is a statistical control whose household
#: intercepts absorb some genuine state dependence, so it is a lower bound; the
#: upper end removes brand-share concentration and nothing else, so it is an
#: upper bound. Neither is a point estimate and the interval is not a CI.
HUMAN_LOW, HUMAN_HIGH = 0.02, 0.36

#: Weeks before this are dropped so the mechanism is measured at its steady
#: state rather than while it fills. rho = 0.95 has a 13.5-week half-life, so
#: the burn-in has to clear that rather than Phase 6's shorter one.
BURN_IN = 30
SEEDS = tuple(range(30))

RESEARCH_QUESTION = (
    "Which regions of the (rho, gamma) loyalty parameter space produce "
    "simulated state dependence consistent with the interval bracketing human "
    "state dependence in the Cracker panel?"
)


def state_dependence(cfg, seeds=SEEDS) -> tuple[float, float]:
    """Excess one-step repeat rate over the same market with memory off.

    Returns the mean across seeds and its standard error. Measured at lag 1,
    the same lag Phase 10's simulator figure was measured at.
    """
    off_cfg = memory_off(cfg)
    per_seed = []
    for seed in seeds:
        pair = []
        for c in (cfg, off_cfg):
            chosen = run_season(dataclasses.replace(c, seeds=(seed,)), seed).chosen_seller
            a, b = chosen[BURN_IN + 1 :], chosen[BURN_IN:-1]
            both = (a >= 0) & (b >= 0)
            pair.append(float((a[both] == b[both]).mean()) if both.any() else np.nan)
        per_seed.append(pair[0] - pair[1])
    per_seed = np.array(per_seed)
    return float(np.nanmean(per_seed)), float(
        np.nanstd(per_seed, ddof=1) / np.sqrt(len(per_seed))
    )


#: Lags for the horizon diagnostic. Not a gate - a check on what the gate's
#: own estimand actually measures.
LAGS = (1, 2, 4, 8, 16)


def state_dependence_by_lag(cfg, lags=LAGS, seeds=SEEDS[:12]) -> dict[int, float]:
    """The same excess, at several horizons.

    Gate A is a one-step quantity because the human bracket it is compared
    against is one-step. But `rho` sets both the accrual weight `(1 - rho)`
    and the decay, so a single lag cannot separate them, and this table is
    what shows it: the ordering across `rho` at lag 1 is the reverse of the
    ordering at lag 16.
    """
    off_cfg = memory_off(cfg)
    out: dict[int, list[float]] = {lag: [] for lag in lags}
    for seed in seeds:
        runs = [run_season(dataclasses.replace(c, seeds=(seed,)), seed).chosen_seller
                for c in (cfg, off_cfg)]
        for lag in lags:
            pair = []
            for chosen in runs:
                a, b = chosen[BURN_IN + lag :], chosen[BURN_IN:-lag]
                both = (a >= 0) & (b >= 0)
                pair.append(float((a[both] == b[both]).mean()) if both.any() else np.nan)
            out[lag].append(pair[0] - pair[1])
    return {lag: float(np.nanmean(v)) for lag, v in out.items()}


def main() -> int:
    commit = experiment_log.git_commit(REPO_ROOT)
    RESULTS_ROOT.mkdir(parents=True, exist_ok=True)
    print("\n=== Loyalty v2, Gate A — empirical admissibility ===")
    print(f"  {RESEARCH_QUESTION}\n")
    print(f"  human interval [{HUMAN_LOW:+.2f}, {HUMAN_HIGH:+.2f}], "
          f"{len(SEEDS)} seeds, burn-in {BURN_IN} weeks\n")

    rows = []
    print(f"  {'cell':24s} {'rho':>5s} {'gamma':>6s} {'SD_sim':>9s} {'se':>7s}  verdict")
    for cfg in config.LOYALTY_V2_CELLS:
        sd, se = state_dependence(cfg)
        admissible = HUMAN_LOW <= sd <= HUMAN_HIGH
        rows.append({"cell": cfg.name, "rho": cfg.loyalty_retention,
                     "gamma": cfg.loyalty_gamma, "state_dependence": sd,
                     "std_error": se, "admissible": bool(admissible)})
        print(f"  {cfg.name:24s} {cfg.loyalty_retention:5.2f} "
              f"{cfg.loyalty_gamma:6.2f} {sd:+9.4f} {se:7.4f}  "
              f"{'admissible' if admissible else 'excluded'}")

    # M1, the streak ablation, on the same environment - reported alongside
    # rather than inside the grid, because it is a different theory of what
    # loyalty is and not another point in this one's parameter space.
    m1_sd, m1_se = state_dependence(config.LOYALTY_V2_STREAK)
    m1_ok = HUMAN_LOW <= m1_sd <= HUMAN_HIGH
    print(f"\n  {'M1 streak (kappa=0.5, C=3)':24s} {'-':>5s} {'-':>6s} "
          f"{m1_sd:+9.4f} {m1_se:7.4f}  {'admissible' if m1_ok else 'excluded'}")

    # The horizon diagnostic. Gamma is held at its middle value so the table
    # varies only in rho, which is the parameter whose reading is at issue.
    print(f"\n  Excess repeat by lag, gamma = 1.50 fixed:")
    print(f"  {'rho':>6s} " + "".join(f"{('lag ' + str(l)):>10s}" for l in LAGS))
    lag_rows = []
    for rho in config.LOYALTY_V2_RHOS:
        by_lag = state_dependence_by_lag(config.loyalty_v2_cell(rho, 1.50))
        lag_rows.append({"cell": f"rho={rho:.2f}", "rho": rho, "gamma": 1.50,
                         **{f"lag_{l}": by_lag[l] for l in LAGS}})
        print(f"  {rho:6.2f} " + "".join(f"{by_lag[l]:+10.4f}" for l in LAGS))
    m1_by_lag = state_dependence_by_lag(config.LOYALTY_V2_STREAK)
    lag_rows.append({"cell": "M1 streak", "rho": np.nan, "gamma": np.nan,
                     **{f"lag_{l}": m1_by_lag[l] for l in LAGS}})
    print(f"  {'M1':>6s} " + "".join(f"{m1_by_lag[l]:+10.4f}" for l in LAGS))
    pd.DataFrame(lag_rows).to_csv(RESULTS_ROOT / "gate_a_by_lag.csv", index=False)

    frame = pd.DataFrame(rows)
    frame.to_csv(RESULTS_ROOT / "gate_a.csv", index=False)
    pd.DataFrame([{"cell": "M1 streak", "rho": np.nan, "gamma": np.nan,
                   "state_dependence": m1_sd, "std_error": m1_se,
                   "admissible": bool(m1_ok)}]).to_csv(
        RESULTS_ROOT / "gate_a_m1.csv", index=False)
    plot(frame, m1_sd, lag_rows)

    n_ok = int(frame["admissible"].sum())
    admissible = frame[frame["admissible"]]
    print(f"\n  {n_ok}/9 cells admissible.")
    if n_ok:
        print("  Theta_H = " + ", ".join(
            f"(rho={r.rho:.2f}, gamma={r.gamma:.2f})" for r in admissible.itertuples()))

    experiment_log.append_row(LOG_PATH, {
        "experiment_id": "loyaltyv2_gate_a_admissibility",
        "git_commit": commit,
        "config_file": "experiments/loyalty_v2/run_gate_a.py",
        "phase": 10.5, "seed": f"{len(SEEDS)} seeds, burn-in {BURN_IN}",
        "n_buyers": sum(b.count for b in config.PHASE7A_FIXED.buyer_classes),
        "n_sellers": sum(s.count for s in config.PHASE7A_FIXED.seller_classes),
        "model_used": "relationship loyalty (Guadagni-Little), M2",
        "decision_type": "purchase",
        "human_benchmark_id": "Ecdat::Cracker via Phase 10 bracket",
        "research_question": RESEARCH_QUESTION,
        "changed_mechanism": (
            "loyalty as L <- rho*L + (1-rho)*I with bonus gamma*L, replacing "
            "Phase 7e's saturating stock with per-cell L_max calibration and "
            "its active delta = 0.25 promotion term"
        ),
        # No model is queried in this gate; the columns exist for the phases
        # that do, and zero is the honest entry rather than a blank.
        "synthetic_cost_usd": 0.0,
        "synthetic_latency_seconds": 0.0,
        "transaction_count": len(SEEDS) * len(config.LOYALTY_V2_CELLS),
        "human_benchmark_status": "compared_to_published_panel",
        "participation_rate": "N/A - state dependence is conditional on choice",
        "result_summary": (
            f"{n_ok}/9 cells inside the human interval "
            f"[{HUMAN_LOW:+.2f}, {HUMAN_HIGH:+.2f}]; "
            + "; ".join(f"rho={r.rho:.2f} gamma={r.gamma:.2f}: "
                        f"{r.state_dependence:+.4f}"
                        f"{'' if r.admissible else ' (excluded)'}"
                        for r in frame.itertuples())
            + f". M1 streak: {m1_sd:+.4f}"
              f"{'' if m1_ok else ' (excluded)'}"
        ),
        "decision_implication": (
            "Gate B runs the longitudinal tests only inside the admissible "
            "region; cells outside it are not carried forward"
        ),
        "next_experiment": "Loyalty v2 Gate B - dynamic validity",
    })
    print(f"\n  Wrote {RESULTS_ROOT}\n")
    return 0


def plot(frame, m1_sd: float, lag_rows: list) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(12.5, 4.6))

    ax = axes[0]
    grid = frame.pivot(index="rho", columns="gamma", values="state_dependence")
    im = ax.imshow(grid.values, cmap="viridis", origin="lower", aspect="auto")
    ax.set_xticks(range(len(grid.columns)))
    ax.set_xticklabels([f"{g:.2f}" for g in grid.columns])
    ax.set_yticks(range(len(grid.index)))
    ax.set_yticklabels([f"{r:.2f}" for r in grid.index])
    ax.set_xlabel("gamma — loyalty strength")
    ax.set_ylabel("rho — memory persistence")
    for i, r in enumerate(grid.index):
        for j, g in enumerate(grid.columns):
            row = frame[(frame["rho"] == r) & (frame["gamma"] == g)].iloc[0]
            ax.text(j, i, f"{row['state_dependence']:+.3f}\n"
                          f"{'admissible' if row['admissible'] else 'excluded'}",
                    ha="center", va="center", fontsize=8,
                    color="white" if row["state_dependence"] < grid.values.mean() else "black")
    ax.set_title("Simulated state dependence per cell", fontsize=10)
    fig.colorbar(im, ax=ax, label="excess repeat rate over memory-off")

    ax = axes[1]
    for row in lag_rows:
        label = row["cell"]
        style = dict(ls="--", c="0.4") if label == "M1 streak" else {}
        ax.plot(LAGS, [row[f"lag_{l}"] for l in LAGS], marker="o", label=label,
                **style)
    ax.axhline(0, c="0.3", lw=0.8)
    ax.set_xscale("log", base=2)
    ax.set_xticks(LAGS)
    ax.set_xticklabels([str(l) for l in LAGS])
    ax.set_xlabel("lag (weeks)")
    ax.set_ylabel("excess repeat over memory-off")
    ax.set_title("rho sets accrual and decay together: the ordering inverts",
                 fontsize=10)
    ax.legend(fontsize=7)

    fig.suptitle("Loyalty v2 Gate A — which loyalty regimes the human evidence "
                 "rules out", fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(RESULTS_ROOT / "gate_a.png", dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    raise SystemExit(main())
