"""Phase 9a design-review evidence. Measures only - fits nothing.

Two things the 9a gate has to be set against, and neither should live in a
conversation: what the hand-coded buyer's policy distribution actually looks
like, and whether a candidate WTP parameterization leaves buying "neither
always nor never worthwhile" against the standing prices and budgets.

No learner is trained here and no threshold is set. See
docs/phase_specifications.md, Phase 9a.

    python experiments/phase9a/measure_teacher.py
"""

from __future__ import annotations

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

from market_sim import experiment_log  # noqa: E402
from market_sim.config import PHASE7A_FIXED as BASE  # noqa: E402
from market_sim.engine import purchase_probability  # noqa: E402

RESULTS_ROOT = REPO_ROOT / "results" / "phase9a_gate"
LOG_PATH = REPO_ROOT / "experiment_log.csv"

SEEDS = tuple(range(6))
#: The loyalty extremes. Phase 6's bonus is `0.5 * min(streak, 3)`, so these
#: bracket every state the teacher can be in on that axis.
STREAKS = (0, 3)

#: Candidate WTP parameterizations for the design review. A depends on the
#: buyer only, which is what the spec currently writes; B adds a class-specific
#: quality premium for the premium tier, which is a new primitive.
CANDIDATES = {
    "A: buyer class only": {
        "base": {"Poor": 1.0, "Middle": 1.5, "Rich": 1.5},
        "spread": {"Poor": 2.0, "Middle": 3.0, "Rich": 5.0},
        "premium": {"Poor": 0.0, "Middle": 0.0, "Rich": 0.0},
    },
    "B: plus a quality premium": {
        "base": {"Poor": 1.0, "Middle": 1.5, "Rich": 1.5},
        "spread": {"Poor": 2.0, "Middle": 3.0, "Rich": 5.0},
        "premium": {"Poor": 0.0, "Middle": 2.0, "Rich": 3.5},
    },
}
PRICES = {"Slow": 2.0, "Shigh": 6.0}
BUDGETS = {"Poor": 3.0, "Middle": 7.0, "Rich": 10.0}

RESEARCH_QUESTION = (
    "What does the hand-coded buyer's policy distribution look like, and does a "
    "candidate WTP parameterization leave buying neither always nor never "
    "worthwhile?"
)


def teacher_probabilities() -> pd.DataFrame:
    """Every affordable encounter's p_T(s), tagged by the gate's strata.

    Unaffordable pairs are excluded: the engine never evaluates a purchase
    probability for them, so they are not decisions the teacher makes and
    including them would dilute every stratum with a structural zero.
    """
    buyer_class = BASE.buyer_class_of()
    seller_class = BASE.seller_class_of()
    alpha = np.array(
        [c.price_sensitivity for c in BASE.buyer_classes for _ in range(c.count)]
    )
    price0 = np.array([c.price for c in BASE.seller_classes for _ in range(c.count)])

    rows = []
    for seed in SEEDS:
        budgets = BASE.buyer_budgets(seed)
        preference = np.random.default_rng(seed).random((BASE.n_buyers, BASE.n_sellers))
        for b in range(BASE.n_buyers):
            for s in range(BASE.n_sellers):
                if price0[s] > budgets[b]:
                    continue
                for streak in STREAKS:
                    bonus = BASE.loyalty_bonus_per_streak * min(
                        streak, BASE.loyalty_streak_cap
                    )
                    rows.append({
                        "seed": seed,
                        "buyer_class": buyer_class[b],
                        "seller_tier": seller_class[s],
                        "price": float(price0[s]),
                        "streak": streak,
                        "p": purchase_probability(
                            BASE, budgets[b], price0[s], preference[b, s],
                            alpha[b], BASE.price_reference, loyalty_bonus=bonus,
                        ),
                    })
    return pd.DataFrame(rows)


def summarize(frame: pd.DataFrame, by) -> pd.DataFrame:
    def stats(g):
        p = g["p"].to_numpy()
        entropy = -(p * np.log2(np.clip(p, 1e-12, 1))
                    + (1 - p) * np.log2(np.clip(1 - p, 1e-12, 1)))
        return pd.Series({
            "n": len(p), "mean_p": p.mean(),
            "p5": np.percentile(p, 5), "p95": np.percentile(p, 95),
            "entropy_bits": entropy.mean(),
            # The best any deterministic policy can score against a sampled
            # action. A classifier at this number is perfect, not mediocre.
            "argmax_ceiling": np.maximum(p, 1 - p).mean(),
            # What two policies that both recover p exactly, but draw their own
            # actions, would agree on. Not what this phase measures - under the
            # shared purchase_draw a perfect student agrees 100%.
            "independent_agreement": (p**2 + (1 - p)**2).mean(),
        })
    return frame.groupby(by, dropna=False).apply(stats, include_groups=False).reset_index()


def wtp_sanity(name: str, params: dict, draws: int = 200_000) -> pd.DataFrame:
    """Is buying ever, and not always, worthwhile - per class and tier?"""
    pref = np.random.default_rng(0).random(draws)
    rows = []
    for cls in ("Poor", "Middle", "Rich"):
        surplus = {}
        for tier, price in PRICES.items():
            wtp = (params["base"][cls] + params["spread"][cls] * pref
                   + params["premium"][cls] * (tier == "Shigh"))
            surplus[tier] = wtp - price
            affordable = price <= BUDGETS[cls]
            rows.append({
                "candidate": name, "buyer_class": cls, "seller_tier": tier,
                "wtp_min": wtp.min(), "wtp_max": wtp.max(),
                "p_worth_buying": float(np.mean(wtp > price)),
                "affordable": affordable,
                # Degenerate either way round: a cell that is never worth
                # buying carries no decision, and one that is always worth
                # buying carries no trade-off.
                "degenerate": affordable and (
                    np.mean(wtp > price) < 0.01 or np.mean(wtp > price) > 0.99
                ),
            })
        if PRICES["Shigh"] <= BUDGETS[cls]:
            # Independent draws, as the engine gives each (buyer, seller) pair
            # its own preference.
            a, b = surplus["Slow"], surplus["Shigh"][::-1]
            rows[-1]["prefers_premium"] = float(np.mean((b > a) & (b > 0)))
    return pd.DataFrame(rows)


def main() -> int:
    commit = experiment_log.git_commit(REPO_ROOT)
    RESULTS_ROOT.mkdir(parents=True, exist_ok=True)
    teacher = teacher_probabilities()

    print("\n=== Phase 9a design-review evidence — measurements only ===")
    print(f"  {RESEARCH_QUESTION}\n")
    print(f"  {len(teacher)} affordable encounters, {len(SEEDS)} seeds, "
          f"both loyalty extremes.\n")

    strata = {
        "loyalty (streak)": ["streak"],
        "buyer class": ["buyer_class"],
        "seller tier": ["seller_tier"],
        "class x tier": ["buyer_class", "seller_tier"],
    }
    tables = []
    for label, by in strata.items():
        table = summarize(teacher, by)
        table.insert(0, "stratum", label)
        tables.append(table)
        print(f"  {label}")
        for _, r in table.iterrows():
            key = " / ".join(str(r[c]) for c in by)
            print(f"    {key:16s} n={int(r['n']):5d}  mean p {r['mean_p']:.3f}  "
                  f"[{r['p5']:.3f}, {r['p95']:.3f}]  H {r['entropy_bits']:.3f}  "
                  f"argmax ceiling {r['argmax_ceiling']:.3f}")
    p = teacher["p"].to_numpy()
    print(f"\n  pooled: mean p {p.mean():.3f}, share in [0.2, 0.8] "
          f"{np.mean((p > 0.2) & (p < 0.8)):.1%}, argmax ceiling "
          f"{np.maximum(p, 1 - p).mean():.3f}")
    print("  NOTE: the argmax ceiling is what a *deterministic* policy scores "
          "against a\n  sampled action. Under the shared purchase_draw a student "
          "that recovers p\n  exactly agrees 100%. The two must not be compared.")

    sanity = pd.concat([wtp_sanity(n, p_) for n, p_ in CANDIDATES.items()])
    print("\n  WTP candidates — is buying ever, and not always, worthwhile?")
    for name in CANDIDATES:
        sub = sanity[sanity["candidate"] == name]
        bad = sub[sub["degenerate"]]
        print(f"\n    {name}")
        for _, r in sub.iterrows():
            note = ""
            if not r["affordable"]:
                note = "unaffordable"
            elif r["degenerate"]:
                note = "DEGENERATE"
            elif not np.isnan(r.get("prefers_premium", np.nan)):
                note = f"prefers premium {r['prefers_premium']:.1%}"
            print(f"      {r['buyer_class']:7s} {r['seller_tier']:6s} "
                  f"WTP {r['wtp_min']:5.2f}-{r['wtp_max']:<5.2f} "
                  f"P(worth buying) {r['p_worth_buying']:6.1%}  {note}")
        print(f"      -> {len(bad)} degenerate cell(s)")

    pd.concat(tables).to_csv(RESULTS_ROOT / "teacher_policy.csv", index=False)
    sanity.to_csv(RESULTS_ROOT / "wtp_candidates.csv", index=False)
    plot(teacher, sanity)

    experiment_log.append_row(LOG_PATH, {
        "experiment_id": "phase9a_gate_evidence", "git_commit": commit,
        "config_file": "experiments/phase9a/measure_teacher.py",
        "phase": 9, "seed": f"{SEEDS[0]}-{SEEDS[-1]}",
        "n_buyers": BASE.n_buyers, "n_sellers": BASE.n_sellers,
        "model_used": "rule_based", "decision_type": "N/A",
        "human_benchmark_id": "N/A", "human_benchmark_status": "not_applicable",
        "synthetic_cost_usd": "N/A", "synthetic_latency_seconds": "N/A",
        "research_question": RESEARCH_QUESTION,
        "changed_mechanism": "none - design-review measurement, nothing is fitted",
        "transaction_count": "N/A", "participation_rate": "N/A",
        "result_summary": (
            f"Teacher is near-maximally stochastic: pooled mean p {p.mean():.3f}, "
            f"{np.mean((p > 0.2) & (p < 0.8)):.0%} of decisions in [0.2, 0.8], "
            f"argmax ceiling {np.maximum(p, 1 - p).mean():.3f}. Loyalty dominates "
            f"the conditional structure (streak 0: "
            f"{teacher[teacher.streak == 0]['p'].mean():.3f}, streak 3: "
            f"{teacher[teacher.streak == 3]['p'].mean():.3f}) while class and tier "
            f"move the mean by under 0.08. WTP candidate A leaves "
            f"{int(sanity[(sanity.candidate.str.startswith('A')) & sanity.degenerate].shape[0])} "
            f"degenerate cells, candidate B "
            f"{int(sanity[(sanity.candidate.str.startswith('B')) & sanity.degenerate].shape[0])}."
        ),
        "decision_implication": "Sets Phase 9a's gate strata and WTP parameterization",
        "next_experiment": "Phase 9a gate definition, once A or B is chosen",
    })
    print(f"\n  Wrote {RESULTS_ROOT}\n")
    return 0


def plot(teacher: pd.DataFrame, sanity: pd.DataFrame) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(15.5, 4.4))

    ax = axes[0]
    for streak, colour in ((0, "tab:blue"), (3, "tab:red")):
        sub = teacher[teacher["streak"] == streak]["p"]
        ax.hist(sub, bins=40, range=(0, 1), alpha=0.55, color=colour, density=True,
                label=f"streak {streak} (mean {sub.mean():.3f})")
    ax.axvline(0.5, ls="--", c="0.4", lw=1)
    ax.text(0.505, ax.get_ylim()[1] * 0.94, "argmax boundary", fontsize=7.5, color="0.35")
    ax.set_xlabel("teacher's purchase probability p(s)")
    ax.set_ylabel("density")
    ax.set_title("The teacher is undecided almost everywhere", fontsize=10)
    ax.legend(fontsize=8)

    ax = axes[1]
    order = ["streak 0", "streak 3", "Poor", "Middle", "Rich", "Slow", "Shigh"]
    values = [
        teacher[teacher.streak == 0]["p"].mean(), teacher[teacher.streak == 3]["p"].mean(),
        *[teacher[teacher.buyer_class == c]["p"].mean() for c in ("Poor", "Middle", "Rich")],
        *[teacher[teacher.seller_tier == t]["p"].mean() for t in ("Slow", "Shigh")],
    ]
    colours = ["tab:blue", "tab:red"] + ["0.55"] * 5
    ax.barh(range(len(order)), values, color=colours, height=0.62)
    ax.axvline(teacher["p"].mean(), ls="--", c="firebrick", lw=1.2)
    ax.text(teacher["p"].mean() + 0.008, len(order) - 0.4,
            f"pooled {teacher['p'].mean():.3f}", fontsize=7.5, color="firebrick")
    ax.set_yticks(range(len(order)))
    ax.set_yticklabels(order, fontsize=9)
    ax.invert_yaxis()
    ax.set_xlabel("mean purchase probability")
    ax.set_title("Loyalty moves it; class and tier barely do", fontsize=10)

    ax = axes[2]
    width = 0.36
    labels = []
    for i, (name, marker) in enumerate(zip(CANDIDATES, ("A", "B"))):
        sub = sanity[(sanity["candidate"] == name) & sanity["affordable"]]
        x = np.arange(len(sub)) + (i - 0.5) * width
        ax.bar(x, sub["p_worth_buying"], width, label=name,
               color=["tab:orange", "tab:blue"][i],
               edgecolor=["firebrick" if d else "white" for d in sub["degenerate"]],
               linewidth=1.6)
        labels = [f"{r.buyer_class}\n{r.seller_tier}" for r in sub.itertuples()]
    ax.axhline(1.0, ls=":", c="firebrick", lw=1)
    ax.axhline(0.0, ls=":", c="firebrick", lw=1)
    ax.set_xticks(np.arange(len(labels)))
    ax.set_xticklabels(labels, fontsize=7.5)
    ax.set_ylim(0, 1.12)
    ax.set_ylabel("P(WTP > price)")
    ax.set_title("WTP candidates: red edge = degenerate cell", fontsize=10)
    ax.legend(fontsize=7.5, loc="lower left")

    fig.suptitle("Phase 9a design-review evidence — the teacher, and the WTP decision",
                 fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(RESULTS_ROOT / "gate_evidence.png", dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    raise SystemExit(main())
