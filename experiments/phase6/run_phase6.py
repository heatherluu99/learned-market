"""Run Phase 6 — Repeated Interaction.

A 22-week season with persistent buyer memory, run against a no-loyalty
control on identical seeds. Both graded comparisons are made against that
control or against the season's own early weeks, never against the raw
stability level: most of that level is seller popularity and fixed preference
rather than memory.

    python experiments/phase6/run_phase6.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import warnings

import matplotlib

matplotlib.use("Agg")
# Week 0 has no predecessor, so its stability column is all-NaN by design;
# nanstd over it warns about zero degrees of freedom and returns NaN, which
# is the wanted behaviour.
warnings.filterwarnings("ignore", message="Degrees of freedom <= 0")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from market_sim import acceptance, experiment_log, outputs  # noqa: E402
from market_sim.config import PHASE6_MAIN, PHASE6_NO_LOYALTY  # noqa: E402
from market_sim.engine import run_season_seeds  # noqa: E402

RESULTS_ROOT = REPO_ROOT / "results" / "phase6"
LOG_PATH = REPO_ROOT / "experiment_log.csv"

RESEARCH_QUESTION = (
    "Does buyer memory (loyalty to a previously-purchased seller) change future "
    "behaviour and produce stable buyer-seller relationships over time?"
)


def plot_season(seasons, control, out_path: Path) -> None:
    loyal = np.array([s.pair_stability() for s in seasons])
    plain = np.array([s.pair_stability() for s in control])
    weeks = np.arange(loyal.shape[1])

    fig, axes = plt.subplots(1, 2, figsize=(13, 5))

    ax = axes[0]
    for arr, label, colour in (
        (loyal, "with loyalty", "tab:blue"),
        (plain, "no-loyalty control", "tab:grey"),
    ):
        mean = np.nanmean(arr, axis=0)
        sem = np.nanstd(arr, axis=0, ddof=1) / np.sqrt(arr.shape[0])
        ax.plot(weeks, mean, marker="o", markersize=3, label=label, color=colour)
        ax.fill_between(weeks, mean - sem, mean + sem, alpha=0.15, color=colour)
    plateau = acceptance.plateau_week(seasons)
    if plateau:
        ax.axvline(plateau, linestyle=":", color="firebrick", linewidth=1)
        ax.annotate(
            f"plateau: week {plateau}",
            xy=(plateau, ax.get_ylim()[0]),
            xytext=(plateau + 0.4, ax.get_ylim()[0] + 0.01),
            fontsize=8,
            color="firebrick",
        )
    ax.set_xlabel("week")
    ax.set_ylabel("buyer_seller_pair_stability")
    ax.set_title("Pair stability over one season (shaded = ±1 SEM)")
    ax.legend(fontsize=9)

    ax = axes[1]
    attendance = np.array([s.attendance_rate() for s in seasons]).mean(axis=0)
    purchase = np.array([s.purchase_rate() for s in seasons]).mean(axis=0)
    streak = np.array(
        [
            [
                s.streaks[w][s.chosen_seller[w] >= 0].mean()
                if (s.chosen_seller[w] >= 0).any()
                else np.nan
                for w in range(s.n_weeks)
            ]
            for s in seasons
        ]
    ).mean(axis=0)
    ax.plot(weeks, attendance, marker="o", markersize=3, label="attendance_rate")
    ax.plot(weeks, purchase, marker="o", markersize=3, label="purchase_rate")
    ax.axhspan(0.6, 1.0, color="tab:green", alpha=0.06)
    ax2 = ax.twinx()
    ax2.plot(weeks, streak, color="tab:orange", linestyle="--", label="mean streak")
    ax2.set_ylabel("mean loyalty streak (weeks)", color="tab:orange")
    ax.set_xlabel("week")
    ax.set_ylabel("rate")
    ax.set_title("Attendance vs purchase, and streak growth")
    ax.legend(fontsize=8, loc="lower left")
    ax2.legend(fontsize=8, loc="lower right")

    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def main() -> int:
    commit = experiment_log.git_commit(REPO_ROOT)

    seasons = run_season_seeds(PHASE6_MAIN)
    control = run_season_seeds(PHASE6_NO_LOYALTY)

    for cfg, data in ((PHASE6_MAIN, seasons), (PHASE6_NO_LOYALTY, control)):
        out = RESULTS_ROOT / cfg.name
        out.mkdir(parents=True, exist_ok=True)
        outputs.weekly_summary_frame(cfg, data).to_csv(
            out / "weekly_summary.csv", index=False
        )
        flat = [w for s in data for w in s.weeks]
        outputs.write_all(cfg, flat, out)

    criteria = acceptance.evaluate_phase6(PHASE6_MAIN, seasons, control)
    plateau = acceptance.plateau_week(seasons)

    loyal = np.array([s.pair_stability() for s in seasons])
    plain = np.array([s.pair_stability() for s in control])
    print(f"\n=== {PHASE6_MAIN.name} — {PHASE6_MAIN.weeks} weeks, "
          f"{len(PHASE6_MAIN.seeds)} seeds ===")
    print(f"  loyalty bonus 0.5 x min(streak, {PHASE6_MAIN.loyalty_streak_cap}), "
          f"max {PHASE6_MAIN.max_loyalty_bonus():g} = preference_coef "
          f"{PHASE6_MAIN.preference_coef:g}")
    print(f"\n  {'week':>5s} {'attend':>8s} {'purchase':>9s} {'stability':>10s} "
          f"{'control':>9s} {'diff':>8s} {'streak':>8s}")
    att = np.array([s.attendance_rate() for s in seasons]).mean(axis=0)
    pur = np.array([s.purchase_rate() for s in seasons]).mean(axis=0)
    stk = np.array(
        [
            [
                s.streaks[w][s.chosen_seller[w] >= 0].mean()
                if (s.chosen_seller[w] >= 0).any()
                else np.nan
                for w in range(s.n_weeks)
            ]
            for s in seasons
        ]
    ).mean(axis=0)
    for w in (1, 3, 5, 8, 11, 14, 17, 21):
        a, b = np.nanmean(loyal[:, w]), np.nanmean(plain[:, w])
        print(
            f"  {w:5d} {att[w]:8.3f} {pur[w]:9.3f} {a:10.3f} {b:9.3f} "
            f"{a - b:+8.3f} {stk[w]:8.2f}"
        )

    print("\n  acceptance criteria:")
    for c in criteria:
        print(f"    [{'PASS' if c.passed else 'FAIL'}] {c.name}")
        print(f"           measured: {c.measured}  (required: {c.threshold})")
        if c.note:
            print(f"           note: {c.note}")
    print(f"\n  plateau week (running mean within 1 SEM of final): {plateau}")

    print("\n=== reported, not graded: shock recovery ===")
    print("  One seller closed for a single week at week 12, repeated across every")
    print("  seller and every seed. Measured over the cohort paired with that seller")
    print("  the week before, against the same seed's unshocked counterfactual.")
    print(f"\n  {'seller':>7s} {'arm':>4s} {'cohort':>7s} {'return 3wk':>11s} "
          f"{'permanent':>10s} {'recovery wk':>12s}")
    shock = {}
    for cfg, label in ((PHASE6_MAIN, "ON"), (PHASE6_NO_LOYALTY, "OFF")):
        rows = []
        for sid in range(cfg.n_sellers):
            m = acceptance.shock_metrics(cfg, sid, 12)
            rows.append(m)
            print(f"  {sid:7d} {label:>4s} {m['cohort_size']:7.1f} "
                  f"{m['return_rate_3wk']:11.3f} {m['permanent_switch_rate']:10.3f} "
                  f"{m['recovery_weeks']:12.2f}")
        shock[label] = rows
    print()
    for key, name in (("return_rate_3wk", "return rate (3 wk)"),
                      ("permanent_switch_rate", "permanent switching"),
                      ("recovery_weeks", "recovery weeks")):
        a = float(np.nanmean([m[key] for m in shock["ON"]]))
        b = float(np.nanmean([m[key] for m in shock["OFF"]]))
        print(f"  {name:22s} ON {a:6.3f}   OFF {b:6.3f}   diff {a - b:+.3f}")
    print("  Memory does not confer shock resilience here. Permanent switching is")
    print("  slightly *higher* with memory on: a buyer pushed off its usual stall")
    print("  starts a fresh streak with the substitute, and the same mechanism that")
    print("  built the original relationship then holds it in the new one.")

    plot_season(seasons, control, RESULTS_ROOT / "season.png")

    stab_loyal = float(np.nanmean([np.nanmean(s.pair_stability()[1:]) for s in seasons]))
    stab_plain = float(np.nanmean([np.nanmean(s.pair_stability()[1:]) for s in control]))
    # Week 1 alone, matching the criterion in acceptance.evaluate_phase6 - see
    # the post-hoc window correction recorded in the spec.
    early = np.array([s.pair_stability()[1] for s in seasons])
    late = np.array([np.nanmean(s.pair_stability()[17:22]) for s in seasons])
    rise, rlo, rhi = acceptance.mean_difference_ci(late, early)

    for cfg, data, note in (
        (PHASE6_MAIN, seasons, "22-week season, loyalty streak bonus active"),
        (PHASE6_NO_LOYALTY, control, "control arm: identical market, loyalty disabled"),
    ):
        experiment_log.append_row(
            LOG_PATH,
            {
                "experiment_id": cfg.name,
                "git_commit": commit,
                "config_file": f"src/market_sim/config.py::{cfg.name.upper()}",
                "phase": 6,
                "seed": "0-29",
                "n_buyers": cfg.n_buyers,
                "n_sellers": cfg.n_sellers,
                "model_used": "rule_based",
                "decision_type": "N/A",
                "human_benchmark_id": "N/A",
                "human_benchmark_status": "not_applicable",
                "synthetic_cost_usd": "N/A",
                "synthetic_latency_seconds": "N/A",
                "research_question": RESEARCH_QUESTION,
                "changed_mechanism": note,
                "transaction_count": sum(
                    len(w.transactions) for s in data for w in s.weeks
                ),
                "participation_rate": round(
                    float(np.mean([s.purchase_rate().mean() for s in data])), 4
                ),
                "result_summary": (
                    f"Mean pair stability {stab_loyal:.3f} with loyalty against "
                    f"{stab_plain:.3f} in the control. Stability rises across the "
                    f"season {rise:+.4f} CI [{rlo:+.4f}, {rhi:+.4f}], plateauing at "
                    f"week {plateau}. {sum(c.passed for c in criteria)}/"
                    f"{len(criteria)} criteria passed. Note the control's level is "
                    f"not zero: unequal seller popularity and season-long fixed "
                    f"preference produce stability without any memory."
                ),
                "decision_implication": "N/A - infrastructure phase, no business decision",
                "next_experiment": "Phase 6 web visualization, then Phase 7 seller learning",
            },
        )

    print(f"\nWrote {LOG_PATH.relative_to(REPO_ROOT)}")
    return 0 if all(c.passed for c in criteria) else 1


if __name__ == "__main__":
    raise SystemExit(main())
