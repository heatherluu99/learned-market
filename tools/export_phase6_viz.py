"""Export one Phase 6 season as compact JSON for the web visualization.

The page consumes the pre-computed output of a completed 22-week run rather
than simulating anything itself, per docs/phase_specifications.md, Phase 6:
"this keeps it buildable as a single self-contained artifact".

One seed is exported, not all thirty. The page shows a market evolving as a
timeline; averaging thirty seeds would destroy exactly the per-buyer trajectory
it exists to make visible. The seed is recorded in the payload so the picture
can be traced back to a reproducible run.

    python tools/export_phase6_viz.py --seed 0 --out viz/phase6_data.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from market_sim import acceptance, experiment_log  # noqa: E402
from market_sim.config import PHASE6_MAIN, PHASE6_NO_LOYALTY  # noqa: E402
from market_sim.engine import run_season, run_season_seeds  # noqa: E402


def build_payload(seed: int) -> dict:
    season = run_season(PHASE6_MAIN, seed)
    cfg = PHASE6_MAIN

    stalls = []
    seller_classes = cfg.seller_class_of()
    prices = [c.price for c in cfg.seller_classes for _ in range(c.count)]
    positions = [c.position_score for c in cfg.seller_classes for _ in range(c.count)]
    visibility = cfg.visibility_prob_of()
    for i, name in enumerate(seller_classes):
        stalls.append(
            {
                "id": i,
                "cls": name,
                "price": prices[i],
                "position": positions[i],
                "visibility": round(visibility[i], 3),
            }
        )

    stability = season.pair_stability()
    attendance = season.attendance_rate()
    purchase = season.purchase_rate()

    weeks = []
    for w, week in enumerate(season.weeks):
        chosen = season.chosen_seller[w]
        active = [i for i in range(cfg.n_sellers) if week.seller_n_sold[i] > 0]
        buyers_placed = int((chosen >= 0).sum())
        weeks.append(
            {
                "w": w,
                "attended": season.attended[w].astype(int).tolist(),
                "chosen": chosen.tolist(),
                "streak": season.streaks[w].tolist(),
                "attendance_rate": round(float(attendance[w]), 4),
                "purchase_rate": round(float(purchase[w]), 4),
                "stability": None if np.isnan(stability[w]) else round(float(stability[w]), 4),
                "active_stalls": len(active),
                "avg_load": round(buyers_placed / len(active), 2) if active else 0.0,
                "revenue": round(week.total_revenue, 1),
                "promo": week.promoted_seller if week.promoted_seller is not None else -1,
                "sold": week.seller_n_sold.tolist(),
            }
        )

    # Season-level numbers the header badges quote. Computed here rather than in
    # the page so the page cannot drift from what the phase actually reported.
    seasons = run_season_seeds(PHASE6_MAIN)
    control = run_season_seeds(PHASE6_NO_LOYALTY)
    loyal = np.array([np.nanmean(s.pair_stability()[1:]) for s in seasons])
    plain = np.array([np.nanmean(s.pair_stability()[1:]) for s in control])
    gap, glo, ghi = acceptance.mean_difference_ci(loyal, plain)

    return {
        "meta": {
            "phase": 6,
            "seed": seed,
            "weeks": cfg.weeks,
            "n_buyers": cfg.n_buyers,
            "n_sellers": cfg.n_sellers,
            "git_commit": experiment_log.git_commit(REPO_ROOT),
            "loyalty_bonus": cfg.loyalty_bonus_per_streak,
            "loyalty_cap": cfg.loyalty_streak_cap,
            "max_bonus": cfg.max_loyalty_bonus(),
            "plateau_week": acceptance.plateau_week(seasons),
            "season_stability": round(float(loyal.mean()), 4),
            "control_stability": round(float(plain.mean()), 4),
            "stability_gap": round(float(gap), 4),
            "stability_gap_ci": [round(float(glo), 4), round(float(ghi), 4)],
            "n_seeds": len(cfg.seeds),
        },
        "buyer_classes": [
            {
                "name": c.name,
                "count": c.count,
                "budget": c.budget_per_visit,
                "alpha": c.price_sensitivity,
                "attendance": c.attendance_probability,
            }
            for c in cfg.buyer_classes
        ],
        "buyers": season.chosen_seller.shape[1] and cfg.buyer_class_of(),
        "stalls": stalls,
        "weeks": weeks,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "viz" / "phase6_data.json")
    args = parser.parse_args()

    payload = build_payload(args.seed)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, separators=(",", ":")))
    size = args.out.stat().st_size
    print(
        f"Wrote {args.out.relative_to(REPO_ROOT)} "
        f"({size / 1024:.1f} KB, seed {args.seed}, {payload['meta']['weeks']} weeks)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
