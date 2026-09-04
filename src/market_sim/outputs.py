"""Flatten RunResults into the four CSV tables each phase owes."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .config import MarketConfig
from .engine import (
    NO_PURCHASE_BUDGET,
    NO_PURCHASE_INVENTORY,
    NO_PURCHASE_UNNOTICED,
    NO_PURCHASE_UTILITY,
    RunResult,
)

TRANSACTION_COLUMNS = [
    "seed",
    "buyer_id",
    "buyer_class",
    "seller_id",
    "seller_class",
    "visit_order",
    "price",
    "budget_before",
    "budget_after",
    "seller_inventory_after",
]


def transactions_frame(results: list[RunResult]) -> pd.DataFrame:
    rows = [vars(t) for r in results for t in r.transactions]
    frame = pd.DataFrame(rows)
    if frame.empty:  # keep the schema stable even for a market that never trades
        frame = pd.DataFrame(columns=TRANSACTION_COLUMNS)
    return frame.reset_index(drop=True).rename_axis("transaction_id").reset_index()


def buyer_summary_frame(results: list[RunResult]) -> pd.DataFrame:
    return pd.concat(
        [
            pd.DataFrame(
                {
                    "seed": r.seed,
                    "buyer_id": range(len(r.buyer_n_purchases)),
                    "buyer_class": r.buyer_classes,
                    "n_purchases": r.buyer_n_purchases,
                    "total_spent": r.buyer_total_spent,
                    "budget_remaining": r.buyer_budget_remaining,
                }
            )
            for r in results
        ],
        ignore_index=True,
    )


def seller_summary_frame(
    results: list[RunResult], cfg: MarketConfig | None = None
) -> pd.DataFrame:
    """Per seller, per seed.

    `cfg` adds the Phase 3 environment columns (`position_score`,
    `visibility_prob`, realized `visibility_rate`). Without it the frame is the
    Phase 1/2 shape, which is what the seed-only callers want.
    """
    position = visibility = None
    if cfg is not None and cfg.has_environment:
        position = [
            c.position_score for c in cfg.seller_classes for _ in range(c.count)
        ]
        visibility = cfg.visibility_prob_of()

    frames = []
    for r in results:
        data = {
            "seed": r.seed,
            "seller_id": range(len(r.seller_n_sold)),
            "seller_class": r.seller_classes,
            "n_sold": r.seller_n_sold,
            "revenue": r.seller_revenue,
            "inventory_remaining": r.seller_inventory_remaining,
        }
        if position is not None:
            data["position_score"] = position
            data["visibility_prob"] = visibility
            data["visibility_rate"] = r.visibility_rate_by_seller(len(r.buyer_classes))
        frames.append(pd.DataFrame(data))
    return pd.concat(frames, ignore_index=True)


def run_summary_frame(cfg: MarketConfig, results: list[RunResult]) -> pd.DataFrame:
    """The spec's core columns, plus per-class shares and block diagnostics.

    The block-reason counts are an addition to the spec. They exist because
    `total_inventory_remaining` alone cannot distinguish "inventory was tracked
    and never ran out" from "inventory was ignored", and because Phase 2 needs
    to show that Poor was *priced out* of the premium tier rather than choosing
    to avoid it — `n_blocked_by_budget` and the per-pair counts are what
    separate a constraint from a preference.

    `participation_rate` and `avg_purchases_per_buyer` are both kept because
    the spec names both. Note they are identical in Phase 1 by construction
    (budget 5 and price 3 cap every buyer at one purchase); in Phase 2 they
    diverge, since Middle and Rich can afford more than one unit.
    """
    buyer_names = [c.name for c in cfg.buyer_classes]
    # Deduplicated: from Phase 3 a tier spans several entries (same price,
    # different position), which would otherwise emit duplicate columns.
    seller_names = cfg.seller_tier_names()

    rows = []
    for r in results:
        row = {
            "seed": r.seed,
            "participation_rate": r.participation_rate,
            "avg_purchases_per_buyer": r.avg_purchases_per_buyer,
            "total_revenue": r.total_revenue,
            "total_inventory_remaining": r.total_inventory_remaining,
            "n_blocked_by_utility": r.blocked_counts[NO_PURCHASE_UTILITY],
            "n_blocked_by_budget": r.blocked_counts[NO_PURCHASE_BUDGET],
            "n_blocked_by_inventory": r.blocked_counts[NO_PURCHASE_INVENTORY],
            "n_not_noticed": r.blocked_counts.get(NO_PURCHASE_UNNOTICED, 0),
        }
        # Phase 3 onward: realized visibility per seller, the observed
        # counterpart of the configured position_score.
        if cfg.has_environment:
            for seller_id, rate in enumerate(
                r.visibility_rate_by_seller(cfg.n_buyers)
            ):
                row[f"visibility_rate_seller_{seller_id}"] = float(rate)
        for bc in buyer_names:
            row[f"{bc}_participation_rate"] = r.participation_rate_of(bc)
            for sc in seller_names:
                row[f"{bc}_to_{sc}_share"] = r.tier_share(bc, sc)
            for sc in seller_names:
                row[f"{bc}_blocked_by_budget_at_{sc}"] = r.blocked_by_budget_pairs.get(
                    (bc, sc), 0
                )
        rows.append(row)
    return pd.DataFrame(rows)


def seller_class_summary(results: list[RunResult]) -> pd.DataFrame:
    """Per seller class, averaged over seeds. Used by the phase slides."""
    frame = seller_summary_frame(results)
    per_seed = frame.groupby(["seed", "seller_class"], as_index=False).agg(
        n_sold=("n_sold", "sum"),
        revenue=("revenue", "sum"),
        inventory_remaining=("inventory_remaining", "sum"),
        min_inventory_remaining=("inventory_remaining", "min"),
    )
    return per_seed.groupby("seller_class", as_index=False).mean(numeric_only=True)


def write_all(
    cfg: MarketConfig, results: list[RunResult], out_dir: Path
) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    frames = {
        "transactions": transactions_frame(results),
        "buyer_summary": buyer_summary_frame(results),
        "seller_summary": seller_summary_frame(results, cfg),
        "run_summary": run_summary_frame(cfg, results),
    }
    paths = {}
    for name, frame in frames.items():
        path = out_dir / f"{name}.csv"
        frame.to_csv(path, index=False)
        paths[name] = path
    return paths
