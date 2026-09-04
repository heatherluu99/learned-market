"""Flatten RunResults into the four CSV tables Phase 1 owes."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .engine import (
    NO_PURCHASE_BUDGET,
    NO_PURCHASE_INVENTORY,
    NO_PURCHASE_UTILITY,
    RunResult,
)


def transactions_frame(results: list[RunResult]) -> pd.DataFrame:
    rows = [vars(t) for r in results for t in r.transactions]
    frame = pd.DataFrame(rows)
    if frame.empty:  # keep the schema stable even for a market that never trades
        frame = pd.DataFrame(
            columns=[
                "seed",
                "buyer_id",
                "seller_id",
                "visit_order",
                "price",
                "budget_before",
                "budget_after",
                "seller_inventory_after",
            ]
        )
    return frame.reset_index(drop=True).rename_axis("transaction_id").reset_index()


def buyer_summary_frame(results: list[RunResult]) -> pd.DataFrame:
    return pd.concat(
        [
            pd.DataFrame(
                {
                    "seed": r.seed,
                    "buyer_id": range(len(r.buyer_n_purchases)),
                    "n_purchases": r.buyer_n_purchases,
                    "total_spent": r.buyer_total_spent,
                    "budget_remaining": r.buyer_budget_remaining,
                }
            )
            for r in results
        ],
        ignore_index=True,
    )


def seller_summary_frame(results: list[RunResult]) -> pd.DataFrame:
    return pd.concat(
        [
            pd.DataFrame(
                {
                    "seed": r.seed,
                    "seller_id": range(len(r.seller_n_sold)),
                    "n_sold": r.seller_n_sold,
                    "revenue": r.seller_revenue,
                    "inventory_remaining": r.seller_inventory_remaining,
                }
            )
            for r in results
        ],
        ignore_index=True,
    )


def run_summary_frame(results: list[RunResult]) -> pd.DataFrame:
    """The spec's five columns, plus three block-reason diagnostics.

    The diagnostics are an addition to the spec. They exist because
    `total_inventory_remaining` alone cannot distinguish "inventory was tracked
    and never ran out" from "inventory was ignored"; `n_blocked_by_inventory`
    can. `participation_rate` and `avg_purchases_per_buyer` are both kept
    because the spec names both, but note they are identical by construction in
    Phase 1: budget 5 and price 3 cap every buyer at one purchase.
    """
    return pd.DataFrame(
        [
            {
                "seed": r.seed,
                "participation_rate": r.participation_rate,
                "avg_purchases_per_buyer": r.avg_purchases_per_buyer,
                "total_revenue": r.total_revenue,
                "total_inventory_remaining": r.total_inventory_remaining,
                "n_blocked_by_utility": r.blocked_counts[NO_PURCHASE_UTILITY],
                "n_blocked_by_budget": r.blocked_counts[NO_PURCHASE_BUDGET],
                "n_blocked_by_inventory": r.blocked_counts[NO_PURCHASE_INVENTORY],
            }
            for r in results
        ]
    )


def write_all(results: list[RunResult], out_dir: Path) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    frames = {
        "transactions": transactions_frame(results),
        "buyer_summary": buyer_summary_frame(results),
        "seller_summary": seller_summary_frame(results),
        "run_summary": run_summary_frame(results),
    }
    paths = {}
    for name, frame in frames.items():
        path = out_dir / f"{name}.csv"
        frame.to_csv(path, index=False)
        paths[name] = path
    return paths
