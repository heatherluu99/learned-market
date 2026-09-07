"""Phase 10's second evaluation — the free-running closed loop.

    After the first occasion the history is updated with the model's *own*
    choices - a_1 -> S_2 -> a_2 -> ... - while each occasion still presents
    the choice set the household actually faced.

The two arms are **not re-synchronised**, because re-synchronising removes the
feedback loop that is the object of study. Prices, display and feature remain
the household's real ones throughout: only the choice history is endogenous.

The Phase 10 gate registered an expectation for this, from Phase 9c: that
amplification needs persistent state to carry it, so a real panel with genuine
household persistence is where it could appear. **Loyalty v2's Gate B3 has
since found the opposite sign** - stronger memory stabilized trajectories
rather than amplifying them - so this run is a direct test between the gate's
registered expectation and a later measurement that contradicts it. Both are on
record and neither was adjusted after the other.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from market_sim import experiment_log, human  # noqa: E402

_here = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("p10", _here / "run_phase10.py")
p10 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(p10)
_sspec = importlib.util.spec_from_file_location("sarm", _here / "run_s_arm.py")

RESULTS_ROOT = REPO_ROOT / "results" / "phase10"
LOG_PATH = REPO_ROOT / "experiment_log.csv"
BRANDS = p10.BRANDS

#: The S arm's selected cell, carried over rather than re-selected. Choosing
#: it again against the closed-loop metric would be selecting on the thing
#: being measured.
RHO, GAMMA = 0.80, 0.5
RUNS = 40

RESEARCH_QUESTION = (
    "When the simulator's own choices drive its memory forward instead of the "
    "household's real ones, does a small one-step mismatch compound into "
    "household-level trajectory divergence?"
)


def softmax(u):
    u = u - u.max(axis=-1, keepdims=True)
    e = np.exp(u)
    return e / e.sum(axis=-1, keepdims=True)


def run(records, base_utility, households, rho, gamma, runs, seed=0):
    """Free-running distributions, averaged over independent rollouts.

    Returns the mean predicted distribution per occasion and the model's own
    realized choices, so both the distribution and the trajectory it generates
    can be compared against the panel.
    """
    rng = np.random.default_rng(seed)
    n = len(BRANDS)
    eye = np.eye(n)
    total = np.zeros((len(records), n))
    own_choice = np.zeros((runs, len(records)), dtype=int)
    for r in range(runs):
        state = np.zeros(n)
        previous = None
        for i in range(len(records)):
            if households[i] != previous:
                state = np.zeros(n)
                previous = households[i]
            p = softmax(base_utility[i] + gamma * state)
            total[i] += p
            pick = int(rng.choice(n, p=p))
            own_choice[r, i] = pick
            # The model's own choice drives the state, not the household's.
            state = rho * state + (1 - rho) * eye[pick]
    return total / runs, own_choice


def one_step(records, base_utility, households, rho, gamma):
    """The same model with the household's real history driving the state."""
    n = len(BRANDS)
    eye = np.eye(n)
    out = np.zeros((len(records), n))
    state = np.zeros(n)
    previous = None
    for i, rec in enumerate(records):
        if households[i] != previous:
            state = np.zeros(n)
            previous = households[i]
        out[i] = softmax(base_utility[i] + gamma * state)
        state = rho * state + (1 - rho) * eye[rec["chosen_index"]]
    return out


def repeat_rate(choices, households) -> float:
    same = np.r_[False, households[1:] == households[:-1]]
    rep = np.r_[False, choices[1:] == choices[:-1]] & same
    return float(rep.sum() / same.sum())


def main() -> int:
    commit = experiment_log.git_commit(REPO_ROOT)
    RESULTS_ROOT.mkdir(parents=True, exist_ok=True)
    print("\n=== Phase 10 — free-running closed loop ===")
    print(f"  {RESEARCH_QUESTION}\n")
    print(f"  rho={RHO}, gamma={GAMMA} carried over from the S arm, not "
          f"re-selected here.\n  {RUNS} independent rollouts, never "
          f"re-synchronised to the panel.\n")

    panel = human.load()
    records = p10.occasions(panel)
    n = len(BRANDS)
    households = np.array([r["household"] for r in records])
    observed = np.zeros((len(records), n))
    observed[np.arange(len(records)), [r["chosen_index"] for r in records]] = 1

    price = np.array([[a["price"] for a in r["alternatives"]] for r in records])
    display = np.array([[a["display"] for a in r["alternatives"]] for r in records])
    feature = np.array([[a["feature"] for a in r["alternatives"]] for r in records])
    relative_price = price / price.max()

    l2, _ = human.select_l2(panel)
    fit = human.fit_memoryless_choice(panel, household_effects=True, l2=l2)
    held = fit["held_out"][: len(records)]
    brand_index = np.arange(n)[None, :]
    base = (fit["alpha"][brand_index]
            + fit["u"][households[:, None], brand_index]
            + relative_price * fit["beta"][0]
            + display * fit["beta"][1]
            + feature * fit["beta"][2])

    step = one_step(records, base, households, RHO, GAMMA)
    free, own = run(records, base, households, RHO, GAMMA, RUNS)

    keep = np.flatnonzero(held)
    held_records = [records[i] for i in keep]
    held_observed = observed[keep]
    human_contrasts = p10.contrasts(held_records, held_observed)

    rows = []
    for name, predicted in (("one-step (real history)", step),
                            ("free-running (own history)", free)):
        sub = predicted[keep]
        js = p10.scenario_js(held_records, sub)
        ll = float(-np.log(np.clip((sub * held_observed).sum(1), 1e-12, 1)).mean())
        c = p10.contrasts(held_records, sub)
        signs = {k: bool(np.sign(c[k]) == np.sign(human_contrasts[k])) for k in c}
        rows.append({"arm": name, "weighted_js": js["weighted_js"], "log_loss": ll,
                     **{f"contrast_{k}": v for k, v in c.items()},
                     "signs_matched": int(sum(signs.values()))})
        print(f"  {name:28s} JS {js['weighted_js']:.4f}   log-loss {ll:.4f}   "
              + " ".join(f"{k}{'+' if signs[k] else 'X'}" for k in c))

    amplification = rows[1]["weighted_js"] / rows[0]["weighted_js"]
    print(f"\n  closed-loop amplification (JS free / JS one-step): "
          f"{amplification:.2f}x")

    # Does divergence grow with depth into the household's sequence? That is
    # what "compounds" means, and a ratio at the aggregate cannot show it.
    index = np.zeros(len(records), dtype=int)
    seen: dict[int, int] = {}
    for i, h in enumerate(households):
        index[i] = seen.get(h, 0)
        seen[h] = index[i] + 1
    buckets = [(0, 3), (3, 8), (8, 16), (16, 999)]
    print(f"\n  {'occasions into the household':32s} {'n':>6s} {'one-step':>9s} "
          f"{'free':>9s} {'ratio':>7s}")
    depth_rows = []
    for lo, hi in buckets:
        mask = held & (index >= lo) & (index < hi)
        if mask.sum() < 60:
            continue
        sel = [records[i] for i in np.flatnonzero(mask)]
        a = p10.scenario_js(sel, step[mask], min_n=15)["weighted_js"]
        b = p10.scenario_js(sel, free[mask], min_n=15)["weighted_js"]
        depth_rows.append({"from": lo, "to": hi, "n": int(mask.sum()),
                           "js_one_step": a, "js_free": b, "ratio": b / a})
        label = f"{lo}-{hi}" if hi < 999 else f"{lo}+"
        print(f"  {label:32s} {mask.sum():6d} "
              f"{a:9.4f} {b:9.4f} {b / a:7.2f}")

    human_repeat = repeat_rate(np.array([r["chosen_index"] for r in records]),
                               households)
    own_repeat = float(np.mean([repeat_rate(own[r], households) for r in range(RUNS)]))
    print(f"\n  repeat rate  human {human_repeat:.4f}   "
          f"free-running {own_repeat:.4f}   ({own_repeat - human_repeat:+.4f})")

    frame = pd.DataFrame(rows)
    frame.to_csv(RESULTS_ROOT / "s_freerunning.csv", index=False)
    pd.DataFrame(depth_rows).to_csv(RESULTS_ROOT / "s_freerunning_depth.csv",
                                    index=False)
    plot(frame, pd.DataFrame(depth_rows), human_repeat, own_repeat)

    experiment_log.append_row(LOG_PATH, {
        "experiment_id": "phase10_s_arm_free_running",
        "git_commit": commit,
        "config_file": "experiments/phase10/run_s_freerunning.py",
        "phase": 10, "seed": f"{RUNS} rollouts, rho={RHO}, gamma={GAMMA}",
        "n_buyers": panel["household"].nunique(), "n_sellers": n,
        "model_used": "relationship loyalty (M2) on Cracker, self-driven history",
        "decision_type": "brand_choice",
        "human_benchmark_id": "Ecdat::Cracker",
        "synthetic_cost_usd": 0.0, "synthetic_latency_seconds": 0.0,
        "research_question": RESEARCH_QUESTION,
        "changed_mechanism": (
            "the loyalty state is advanced by the model's own sampled choices "
            "rather than the household's real ones, never re-synchronised, "
            "with the real choice sets retained throughout"
        ),
        "transaction_count": int(held.sum()),
        "human_benchmark_status": "compared_to_published_panel",
        "participation_rate": "N/A - conditioned on participation",
        "result_summary": (
            f"one-step JS {rows[0]['weighted_js']:.4f}, free-running "
            f"{rows[1]['weighted_js']:.4f}, amplification {amplification:.2f}x; "
            f"repeat rate human {human_repeat:.4f} vs free-running "
            f"{own_repeat:.4f}; by depth "
            + "; ".join(f"{r['from']}-{r['to']}: {r['ratio']:.2f}x"
                        for r in depth_rows)
        ),
        "decision_implication": (
            "Whether one-step conditional fidelity implies trajectory fidelity "
            "against a real household sequence"
        ),
        "next_experiment": "N/A - completes the Phase 10 gate's two evaluations",
    })
    print(f"\n  Wrote {RESULTS_ROOT}\n")
    return 0


def plot(frame, depth, human_repeat, own_repeat) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(12.5, 4.6))
    ax = axes[0]
    ax.bar(range(len(frame)), frame["weighted_js"],
           color=["tab:blue", "tab:red"], width=0.55)
    ax.set_xticks(range(len(frame)))
    ax.set_xticklabels(frame["arm"], fontsize=8)
    for i, v in enumerate(frame["weighted_js"]):
        ax.text(i, v, f"{v:.4f}", ha="center", va="bottom", fontsize=9)
    ax.set_ylabel("weighted Jensen-Shannon divergence (bits)")
    ax.set_title("Does self-driven history cost fidelity?", fontsize=10)

    ax = axes[1]
    if len(depth):
        x = range(len(depth))
        ax.plot(x, depth["js_one_step"], marker="o", label="one-step")
        ax.plot(x, depth["js_free"], marker="s", label="free-running")
        ax.set_xticks(list(x))
        ax.set_xticklabels([f"{r['from']}-{r['to'] if r['to'] < 999 else '+'}"
                            for _, r in depth.iterrows()], fontsize=8)
    ax.set_xlabel("occasions into the household's own sequence")
    ax.set_ylabel("weighted JS")
    ax.set_title("Compounding would show as a widening gap", fontsize=10)
    ax.legend(fontsize=8)

    fig.suptitle(f"Phase 10 free-running closed loop — repeat rate "
                 f"{own_repeat:.3f} against the panel's {human_repeat:.3f}",
                 fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    fig.savefig(RESULTS_ROOT / "s_freerunning.png", dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    raise SystemExit(main())
