"""H_promo — does a promotion-acquired purchase build weaker attachment?

The contrast is the same formula on both sides: the repeat rate after a
purchase made on promotion, minus the repeat rate after one made at list
price. A comparison between two differently-defined quantities is not a
comparison.

On the human side the same contrast is also computed after conditioning on B1
- household-specific brand preference, price, display and feature, no
previous-choice term - because the raw number is confounded in the same
direction as the hypothesis: a promoted purchase is disproportionately a
deal-induced switch, so the brand bought was one the household likes less and
would repeat less often with no loyalty mechanism at all.

The registered prediction is about that adjusted number, which had not been
computed when the gate was written. The raw one had been, and the gate says so.
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

from market_sim import config, experiment_log, human  # noqa: E402
from market_sim.engine import run_season  # noqa: E402

RESULTS_ROOT = REPO_ROOT / "results" / "loyalty_v2"
LOG_PATH = REPO_ROOT / "experiment_log.csv"

BURN_IN = 30
SEEDS = tuple(range(30))
N_BOOT = 300

#: Registered in the gate, before the adjusted contrast was computed.
PREDICTED_LO, PREDICTED_HI = -0.03, 0.0

RESEARCH_QUESTION = (
    "Does a purchase made on promotion create weaker, equal, or stronger "
    "future attachment than one made at list price?"
)


def human_contrast(long, *, l2=0.03, split="contiguous", adjusted=True):
    """Repeat after a promoted purchase minus repeat after a list-price one.

    `adjusted` subtracts B1's expected repeat from each side before
    differencing, so what is left is the part promotion explains that
    household preference and current conditions do not.
    """
    n = len(human.BRANDS)
    wide = long.sort_values(["occasion", "brand"])
    chosen = wide["chosen"].to_numpy().reshape(-1, n)
    disp = wide["display"].to_numpy().reshape(-1, n)
    feat = wide["feature"].to_numpy().reshape(-1, n)
    households = wide["household"].to_numpy().reshape(-1, n)[:, 0]
    ci = chosen.argmax(1)
    rows = np.arange(len(ci))
    promoted = (disp[rows, ci] > 0) | (feat[rows, ci] > 0)

    same = np.r_[False, households[1:] == households[:-1]]
    repeat = np.r_[False, ci[1:] == ci[:-1]] & same
    prev_promo = np.r_[False, promoted[:-1]]
    prev_brand = np.r_[-1, ci[:-1]]

    if not adjusted:
        a, b = same & prev_promo, same & ~prev_promo
        return (float(repeat[a].mean() - repeat[b].mean()),
                int(a.sum()), int(b.sum()))

    fit = human.fit_memoryless_choice(long, household_effects=True, l2=l2,
                                      split=split)
    held = fit["held_out"]
    expected = np.zeros(len(ci))
    expected[held] = fit["probabilities"][rows[held] - rows[held][0] * 0
                                          if False else np.arange(held.sum()),
                                          prev_brand[held].clip(0)]
    keep = same & held & (prev_brand >= 0)
    residual = repeat.astype(float) - expected
    a, b = keep & prev_promo, keep & ~prev_promo
    return (float(residual[a].mean() - residual[b].mean()),
            int(a.sum()), int(b.sum()))


def _raw_contrast(cfg, seed) -> float | None:
    """Repeat after a promoted purchase minus after a list-price one, one seed."""
    season = run_season(dataclasses.replace(cfg, seeds=(seed,)), seed)
    chosen = season.chosen_seller[BURN_IN:]
    promoted_seller = np.array(
        [w.promoted_seller if w.promoted_seller is not None else -1
         for w in season.weeks][BURN_IN:])
    prev, nxt = chosen[:-1], chosen[1:]
    on_promo = prev == promoted_seller[:-1, None]
    valid = (prev >= 0) & (nxt >= 0)
    rep = prev == nxt
    a, b = valid & on_promo, valid & ~on_promo
    if not (a.sum() and b.sum()):
        return None
    return float(rep[a].mean() - rep[b].mean())


def simulator_contrast(cfg, seeds=SEEDS) -> dict[str, float]:
    """The contrast raw, and with the same confound removed the human side removes.

    A promoted purchase is disproportionately a deal-induced switch to a
    seller the buyer likes less, so it repeats less often **whether or not any
    loyalty mechanism exists**. The human side removes that with B1; the
    simulator's equivalent is its own memory-off twin, run on the same seeds
    down to the draw. Subtracting it leaves the part promotion explains
    through loyalty and nothing else.

    Comparing the simulator's raw number against the human's adjusted one
    would compare two different estimands, which is the error this function
    exists to avoid.
    """
    from market_sim.acceptance import memory_off

    off_cfg = memory_off(cfg)
    raw, adjusted = [], []
    for seed in seeds:
        on_c, off_c = _raw_contrast(cfg, seed), _raw_contrast(off_cfg, seed)
        if on_c is None or off_c is None:
            continue
        raw.append(on_c)
        adjusted.append(on_c - off_c)
    return {
        "contrast_raw": float(np.mean(raw)),
        "contrast_raw_se": float(np.std(raw, ddof=1) / np.sqrt(len(raw))),
        "contrast": float(np.mean(adjusted)),
        "std_error": float(np.std(adjusted, ddof=1) / np.sqrt(len(adjusted))),
    }


def main() -> int:
    commit = experiment_log.git_commit(REPO_ROOT)
    RESULTS_ROOT.mkdir(parents=True, exist_ok=True)
    print("\n=== H_promo — promotion-dependent reinforcement ===")
    print(f"  {RESEARCH_QUESTION}\n")
    print(f"  Registered before running: the B1-adjusted human contrast is "
          f"negative and\n  lands in ({PREDICTED_LO:+.2f}, {PREDICTED_HI:+.2f}).\n")

    panel = human.load()
    raw, n_promo, n_list = human_contrast(panel, adjusted=False)
    adj, na, nb = human_contrast(panel, adjusted=True)
    print(f"  Human, raw        : {raw:+.4f}   (n {n_promo} promoted / {n_list} list)")
    print(f"  Human, B1-adjusted: {adj:+.4f}   (n {na} / {nb})")

    rng = np.random.default_rng(0)
    draws = []
    for _ in range(N_BOOT):
        rep = human._resample_households(panel, rng)
        draws.append(human_contrast(rep, adjusted=True)[0])
    lo, hi = np.percentile(draws, [2.5, 97.5])
    print(f"  95% CI            : [{lo:+.4f}, {hi:+.4f}]  ({N_BOOT} household bootstraps)")

    inside = PREDICTED_LO < adj < PREDICTED_HI
    excludes_zero = hi < 0 or lo > 0
    print(f"\n  Registered interval ({PREDICTED_LO:+.2f}, {PREDICTED_HI:+.2f}): "
          f"{'point falls inside' if inside else 'POINT FALLS OUTSIDE'}")
    print(f"  Distinguishable from zero: {'yes' if excludes_zero else 'NO'}")

    print(f"\n  Simulator. 'raw' is the human raw estimand; 'adjusted' removes")
    print(f"  the same selection effect B1 removes, using each cell's memory-off twin.")
    print(f"  {'cell':16s} {'delta':>7s} {'raw':>9s} {'adjusted':>10s} "
          f"{'se':>8s} {'ceiling':>8s}")
    rows = []
    for cell in config.HPROMO_CELLS:
        got = simulator_contrast(cell)
        rows.append({"cell": cell.name, "delta": cell.loyalty_deal_sensitivity,
                     **got, "ceiling": cell.max_loyalty_bonus()})
        print(f"  {cell.name:16s} {cell.loyalty_deal_sensitivity:+7.2f} "
              f"{got['contrast_raw']:+9.4f} {got['contrast']:+10.4f} "
              f"{got['std_error']:8.4f} {cell.max_loyalty_bonus():8.3f}")

    frame = pd.DataFrame(rows)
    frame.to_csv(RESULTS_ROOT / "hpromo_cells.csv", index=False)
    pd.DataFrame([{"estimand": "raw", "contrast": raw, "n_promoted": n_promo,
                   "n_list": n_list},
                  {"estimand": "b1_adjusted", "contrast": adj, "ci_lo": lo,
                   "ci_hi": hi, "n_promoted": na, "n_list": nb,
                   "predicted_lo": PREDICTED_LO, "predicted_hi": PREDICTED_HI,
                   "inside_registered_interval": bool(inside),
                   "distinguishable_from_zero": bool(excludes_zero)}]
                 ).to_csv(RESULTS_ROOT / "hpromo_human.csv", index=False)

    # Adjusted against adjusted, raw against raw. The first is the comparison
    # that identifies delta; the second only says whether the simulator
    # reproduces the same selection effect the human panel shows.
    closest = frame.loc[(frame["contrast"] - adj).abs().idxmin()]
    closest_raw = frame.loc[(frame["contrast_raw"] - raw).abs().idxmin()]
    print(f"\n  adjusted vs adjusted: human {adj:+.4f} -> closest cell "
          f"delta = {closest['delta']:+.2f} ({closest['contrast']:+.4f})")
    print(f"  raw vs raw:           human {raw:+.4f} -> closest cell "
          f"delta = {closest_raw['delta']:+.2f} ({closest_raw['contrast_raw']:+.4f})")
    within = frame[(frame["contrast"] >= lo) & (frame["contrast"] <= hi)]
    print(f"  cells inside the human adjusted CI: "
          f"{', '.join(f'{d:+.2f}' for d in within['delta']) or 'none'}")
    plot(frame, adj, lo, hi, raw)

    experiment_log.append_row(LOG_PATH, {
        "experiment_id": "hpromo_promotion_reinforcement",
        "git_commit": commit,
        "config_file": "experiments/loyalty_v2/run_hpromo.py",
        "phase": 10.5, "seed": f"{len(SEEDS)} seeds, {N_BOOT} bootstraps",
        "n_buyers": panel["household"].nunique(),
        "n_sellers": len(human.BRANDS),
        "model_used": "relationship loyalty with deal sensitivity",
        "decision_type": "purchase",
        "human_benchmark_id": "Ecdat::Cracker",
        "synthetic_cost_usd": 0.0,
        "synthetic_latency_seconds": 0.0,
        "research_question": RESEARCH_QUESTION,
        "changed_mechanism": (
            "loyalty accrual multiplied by (1 + delta) on a purchase made at "
            "the promotional price, tested against the same contrast measured "
            "on the human panel"
        ),
        "transaction_count": n_promo + n_list,
        "human_benchmark_status": "compared_to_published_panel",
        "participation_rate": "N/A - conditional on purchase",
        "result_summary": (
            f"Human raw {raw:+.4f}; B1-adjusted {adj:+.4f} [{lo:+.4f}, {hi:+.4f}], "
            f"{'inside' if inside else 'OUTSIDE'} the registered "
            f"({PREDICTED_LO:+.2f}, {PREDICTED_HI:+.2f}), "
            f"{'distinguishable' if excludes_zero else 'NOT distinguishable'} "
            f"from zero. Simulator: "
            + "; ".join(f"delta={r.delta:+.2f}: adjusted {r.contrast:+.4f} "
                        f"(raw {r.contrast_raw:+.4f})" for r in frame.itertuples())
            + f". Closest on the adjusted estimand: delta "
              f"{closest['delta']:+.2f}."
        ),
        "decision_implication": (
            "Whether Loyalty v2's baseline needs a promotion term at all"
        ),
        "next_experiment": "N/A",
    })
    print(f"\n  Wrote {RESULTS_ROOT}\n")
    return 0


def plot(frame, adj, lo, hi, raw) -> None:
    fig, ax = plt.subplots(figsize=(8.5, 4.8))
    ax.axhspan(lo, hi, color="tab:green", alpha=0.15,
               label=f"human B1-adjusted 95% CI [{lo:+.3f}, {hi:+.3f}]")
    ax.axhline(adj, c="tab:green", lw=2.2, label=f"human adjusted {adj:+.4f}")
    ax.axhline(raw, c="tab:green", lw=1.2, ls=":", label=f"human raw {raw:+.4f}")
    ax.axhspan(PREDICTED_LO, PREDICTED_HI, color="tab:purple", alpha=0.10,
               label=f"registered ({PREDICTED_LO:+.2f}, {PREDICTED_HI:+.2f})")
    ax.errorbar(frame["delta"], frame["contrast"], yerr=frame["std_error"],
                marker="o", capsize=4, c="tab:blue", label="simulator, adjusted")
    ax.plot(frame["delta"], frame["contrast_raw"], marker="s", ls="--",
            c="tab:blue", alpha=0.45, label="simulator, raw")
    ax.axhline(0, c="0.3", lw=0.8)
    ax.set_xlabel(r"$\delta$ — extra loyalty accrued on a promoted purchase")
    ax.set_ylabel("repeat after promoted minus repeat after list price")
    ax.set_title("H_promo — promotion-dependent reinforcement", fontsize=11)
    ax.legend(fontsize=7.5)
    fig.tight_layout()
    fig.savefig(RESULTS_ROOT / "hpromo.png", dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    raise SystemExit(main())
