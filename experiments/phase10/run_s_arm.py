"""Phase 10's S arm — the simulator's own buyer, on the human choice sets.

Registered in the Phase 10 gate and never built. Every comparison this project
has made between its simulator and the Cracker panel so far has computed a
statistic in the farmers' market and a statistic in the panel and set them side
by side - which is what the gate itself said not to do:

    Letting the simulator generate its own price environment and comparing
    aggregates would compare two markets rather than two policies.

This puts the simulator's decision rule on `C_it`, the identical alternatives
at the identical prices and promotions the household actually faced.

**Two variants, because they answer different questions and reporting either
alone invites the wrong reading.**

`S-blind` uses the simulator's own coefficients and draws household preference
the way the simulator draws it - from a distribution, not from this
household's history. It asks whether the *mechanism* produces human-shaped
behaviour. It is expected to lose to B1, which knows what each household likes,
and losing that way is not evidence against the mechanism.

`S-informed` starts from exactly B1's fitted utility and adds the loyalty term.
It is therefore B1 plus memory and nothing else, which makes the difference
between them the cleanest measurement of what the memory contributes. This is
the comparison the Phase 10 gate was after.
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from market_sim import config, experiment_log, human  # noqa: E402

import importlib.util  # noqa: E402
_spec = importlib.util.spec_from_file_location(
    "p10", Path(__file__).resolve().parent / "run_phase10.py")
p10 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(p10)

RESULTS_ROOT = REPO_ROOT / "results" / "phase10"
LOG_PATH = REPO_ROOT / "experiment_log.csv"
BRANDS = p10.BRANDS

#: Selected on held-out log-loss, never on the repeat rate being measured -
#: the discipline B1's own L2 penalty is selected under. Reported with the
#: whole grid so a single number cannot be mistaken for the only one tried.
RHO_GRID = (0.50, 0.80, 0.95)
#: Extended past 4.0 after S-blind's first selection landed on it.
#: A minimum at a boundary is not a minimum - the same correction
#: this project already had to make to the L2 grid.
GAMMA_GRID = (0.0, 0.25, 0.5, 1.0, 2.0, 4.0, 8.0, 16.0, 32.0)

RESEARCH_QUESTION = (
    "Given the identical choice sets the households actually faced, does this "
    "project's simulated buyer reproduce human brand choice, and does its "
    "memory add anything to a conditional model that already knows the "
    "household?"
)


def loyalty_stocks(records, rho: float) -> np.ndarray:
    """`L[occasion, brand]` under `L <- rho*L + (1-rho)*I`, per household.

    The state in force *before* each occasion, so a household's own choice on
    that trip never enters the state it is scored under.
    """
    n = len(BRANDS)
    out = np.zeros((len(records), n))
    state = np.zeros(n)
    previous_household = None
    for i, r in enumerate(records):
        if r["household"] != previous_household:
            state = np.zeros(n)
            previous_household = r["household"]
        out[i] = state
        state = rho * state + (1 - rho) * np.eye(n)[r["chosen_index"]]
    return out


def softmax(u: np.ndarray) -> np.ndarray:
    u = u - u.max(axis=1, keepdims=True)
    e = np.exp(u)
    return e / e.sum(axis=1, keepdims=True)


def main() -> int:
    commit = experiment_log.git_commit(REPO_ROOT)
    RESULTS_ROOT.mkdir(parents=True, exist_ok=True)
    print("\n=== Phase 10 S arm — the simulator on the human choice sets ===")
    print(f"  {RESEARCH_QUESTION}\n")

    panel = human.load()
    records = p10.occasions(panel)
    n = len(BRANDS)
    observed = np.zeros((len(records), n))
    observed[np.arange(len(records)), [r["chosen_index"] for r in records]] = 1
    human_contrasts = p10.contrasts(records, observed)

    price = np.array([[a["price"] for a in r["alternatives"]] for r in records])
    display = np.array([[a["display"] for a in r["alternatives"]] for r in records])
    feature = np.array([[a["feature"] for a in r["alternatives"]] for r in records])
    households = np.array([r["household"] for r in records])
    relative_price = price / price.max()

    # ---- baselines, recomputed here so every arm is scored identically -----
    shares = observed.mean(0)
    b0 = np.tile(shares, (len(records), 1))
    l2, _ = human.select_l2(panel)
    fit = human.fit_memoryless_choice(panel, household_effects=True, l2=l2)
    held = fit["held_out"]
    b1 = np.tile(shares, (len(records), 1))
    b1[held[: len(records)]] = fit["probabilities"][: held[: len(records)].sum()]

    # B1's own utility, rebuilt so the loyalty term can be added to it.
    brand_index = np.arange(n)[None, :]
    b1_utility = (fit["alpha"][brand_index]
                  + fit["u"][households[:, None], brand_index]
                  + relative_price * fit["beta"][0]
                  + display * fit["beta"][1]
                  + feature * fit["beta"][2])

    # ---- S-blind: the simulator's own coefficients and its own preference --
    # Preference is drawn, not fitted - that is the point of this variant.
    rng = np.random.default_rng(0)
    unique_households = {h: i for i, h in enumerate(np.unique(households))}
    drawn = rng.normal(0.0, 1.0, size=(len(unique_households), n))
    cfg = config.loyalty_v2_cell(0.80, 1.50)
    alpha = float(np.mean([c.price_sensitivity for c in cfg.buyer_classes]))
    blind_base = (-alpha * relative_price
                  + cfg.preference_coef
                  * drawn[[unique_households[h] for h in households]][:, brand_index[0]])

    # **Every arm is scored on held-out occasions only.** B1's fitted utility
    # is in-sample on the training half, and so is S-informed's, which is
    # built from it. Scoring on everything would let both read answers they
    # were fitted to - and would do it asymmetrically, since Phase 10 hands B1
    # marginal shares on the training half while S-informed would be using its
    # fit there. That comparison flatters S-informed enormously and says
    # nothing.
    keep = np.flatnonzero(held[: len(records)])
    held_records = [records[i] for i in keep]
    held_observed = observed[keep]
    held_human_contrasts = p10.contrasts(held_records, held_observed)
    print(f"  Scored on {len(keep):,} held-out occasions of {len(records):,}.\n")

    print(f"  {'arm':34s} {'weighted JS':>12s} {'log-loss':>10s}  directions")
    rows = []

    def score(name, predicted, extra=None):
        predicted = predicted[keep]
        js = p10.scenario_js(held_records, predicted)
        ll = float(-np.log(np.clip((predicted * held_observed).sum(1),
                                   1e-12, 1)).mean())
        c = p10.contrasts(held_records, predicted)
        signs = {k: bool(np.sign(c[k]) == np.sign(held_human_contrasts[k]))
                 for k in c}
        rows.append({"arm": name, "weighted_js": js["weighted_js"], "log_loss": ll,
                     **{f"contrast_{k}": v for k, v in c.items()},
                     **{f"sign_ok_{k}": v for k, v in signs.items()},
                     "signs_matched": int(sum(signs.values())), **(extra or {})})
        print(f"  {name:34s} {js['weighted_js']:12.4f} {ll:10.4f}  "
              + " ".join(f"{k}{'+' if signs[k] else 'X'}" for k in c))
        return rows[-1]

    score("B0 marginal shares", b0)
    # B1 scored from its own fitted utility on the held-out half, which is
    # what it predicts there - identical to Phase 10's b1_full on this subset.
    b1_row = score("B1 conditional model", softmax(b1_utility))

    # ---- the grid, both variants ------------------------------------------
    # Held-out log-loss selects (rho, gamma). It is never the repeat rate the
    # comparison is about, and the whole grid is written out so the selected
    # cell cannot be mistaken for the only one run.
    grid = []
    for rho in RHO_GRID:
        stocks = loyalty_stocks(records, rho)
        for gamma in GAMMA_GRID:
            for variant, base in (("S-blind", blind_base),
                                  ("S-informed", b1_utility)):
                predicted = softmax(base + gamma * stocks)
                ll = float(-np.log(np.clip(
                    (predicted * observed)[held[: len(records)]].sum(1),
                    1e-12, 1)).mean())
                grid.append({"variant": variant, "rho": rho, "gamma": gamma,
                             "held_out_log_loss": ll})
    grid = pd.DataFrame(grid)
    grid.to_csv(RESULTS_ROOT / "s_arm_grid.csv", index=False)

    print()
    for variant, base in (("S-blind", blind_base), ("S-informed", b1_utility)):
        sub = grid[grid["variant"] == variant]
        best = sub.loc[sub["held_out_log_loss"].idxmin()]
        rho, gamma = float(best["rho"]), float(best["gamma"])
        predicted = softmax(base + gamma * loyalty_stocks(records, rho))
        score(f"{variant} (rho={rho:.2f}, gamma={gamma:g})", predicted,
              {"variant": variant, "rho": rho, "gamma": gamma})
        no_memory = sub[sub["gamma"] == 0.0]["held_out_log_loss"].min()
        edge = " AT GRID BOUNDARY" if gamma == max(GAMMA_GRID) else ""
        print(f"    selected on held-out log-loss; gamma=0 gives {no_memory:.4f}, "
              f"selected {best['held_out_log_loss']:.4f} "
              f"({no_memory - best['held_out_log_loss']:+.4f}){edge}")

    frame = pd.DataFrame(rows)
    frame.to_csv(RESULTS_ROOT / "s_arm.csv", index=False)
    pd.DataFrame([{"metric": k, "human": v} for k, v in human_contrasts.items()]
                 ).to_csv(RESULTS_ROOT / "s_arm_human_contrasts.csv", index=False)
    plot(frame, grid, human_contrasts)

    informed = frame[frame["arm"].str.startswith("S-informed")].iloc[0]

    # A paired bootstrap over households on the held-out set, both fits held
    # fixed. The quantity is small enough that reporting it without an
    # interval would be reporting noise, and the two arms are scored on the
    # same occasions, so the comparison must be paired.
    rho_s, gamma_s = float(informed["rho"]), float(informed["gamma"])
    s_pred = softmax(b1_utility + gamma_s * loyalty_stocks(records, rho_s))[keep]
    b1_pred = softmax(b1_utility)[keep]
    per_occasion = (
        -np.log(np.clip((s_pred * held_observed).sum(1), 1e-12, 1))
        + np.log(np.clip((b1_pred * held_observed).sum(1), 1e-12, 1)))
    held_households = households[keep]
    unique = np.unique(held_households)
    rng2 = np.random.default_rng(0)
    draws = []
    for _ in range(2000):
        picked = rng2.choice(unique, size=len(unique), replace=True)
        draws.append(np.concatenate(
            [per_occasion[held_households == h] for h in picked]).mean())
    lo_d, hi_d = np.percentile(draws, [2.5, 97.5])
    delta_ll = float(per_occasion.mean())
    print(f"\n  S-informed minus B1, held-out log-loss: {delta_ll:+.4f} "
          f"95% CI [{lo_d:+.4f}, {hi_d:+.4f}]")
    print(f"  -> memory's contribution is "
          f"{'distinguishable from zero' if hi_d < 0 or lo_d > 0 else 'NOT distinguishable from zero'}")
    frame.loc[frame["arm"].str.startswith("S-informed"), "vs_b1_log_loss"] = delta_ll
    frame.loc[frame["arm"].str.startswith("S-informed"), "vs_b1_ci_lo"] = lo_d
    frame.loc[frame["arm"].str.startswith("S-informed"), "vs_b1_ci_hi"] = hi_d
    frame.to_csv(RESULTS_ROOT / "s_arm.csv", index=False)

    experiment_log.append_row(LOG_PATH, {
        "experiment_id": "phase10_s_arm_simulator_on_human_choice_sets",
        "git_commit": commit,
        "config_file": "experiments/phase10/run_s_arm.py",
        "phase": 10, "seed": f"{len(records)} occasions, held-out scored",
        "n_buyers": panel["household"].nunique(), "n_sellers": n,
        "model_used": "relationship loyalty (M2) on the Cracker choice sets",
        "decision_type": "brand_choice",
        "human_benchmark_id": "Ecdat::Cracker",
        "synthetic_cost_usd": 0.0, "synthetic_latency_seconds": 0.0,
        "research_question": RESEARCH_QUESTION,
        "changed_mechanism": (
            "the simulator's own decision rule evaluated on the identical "
            "alternatives the households faced, rather than on aggregates "
            "computed in its own market - the S arm the Phase 10 gate "
            "registered and which had never been built"
        ),
        "transaction_count": len(records),
        "human_benchmark_status": "compared_to_published_panel",
        "participation_rate": "N/A - conditioned on participation",
        "result_summary": "; ".join(
            f"{r.arm}: JS {r.weighted_js:.4f}, log-loss {r.log_loss:.4f}, "
            f"{r.signs_matched}/4 directions" for r in frame.itertuples()),
        "decision_implication": (
            "Whether the simulator's memory adds predictive content over a "
            "conditional model that already carries household preference"
        ),
        "next_experiment": "Phase 10 free-running closed loop",
    })
    print(f"\n  Wrote {RESULTS_ROOT}\n")
    return 0


def plot(frame, grid, human_contrasts) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.6))
    ax = axes[0]
    colors = ["0.6", "tab:orange", "tab:red", "tab:blue"]
    ax.barh(range(len(frame)), frame["weighted_js"], color=colors[: len(frame)],
            height=0.6)
    ax.set_yticks(range(len(frame)))
    ax.set_yticklabels(frame["arm"], fontsize=8)
    ax.invert_yaxis()
    for i, v in enumerate(frame["weighted_js"]):
        ax.text(v, i, f"  {v:.4f}", va="center", fontsize=8)
    ax.set_xlabel("weighted Jensen-Shannon divergence (bits), lower is closer")
    ax.set_title("Distance to the human panel, same choice sets", fontsize=10)

    ax = axes[1]
    for (variant, rho), sub in grid.groupby(["variant", "rho"]):
        ax.plot(sub["gamma"], sub["held_out_log_loss"], marker="o",
                ls="-" if variant == "S-informed" else "--",
                label=f"{variant}, rho={rho:g}")
    ax.set_xlabel(r"$\gamma$ — loyalty strength")
    ax.set_ylabel("held-out log-loss")
    ax.set_title("Does adding memory buy anything?", fontsize=10)
    ax.legend(fontsize=6.5)

    fig.suptitle("Phase 10 S arm — the simulator on the households' own choice sets",
                 fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(RESULTS_ROOT / "s_arm.png", dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    raise SystemExit(main())
