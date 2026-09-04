"""Phase 1 transaction engine.

One run = one static market session: every buyer visits every seller once, in
a random order, and decides whether to buy. There is no week axis in Phase 1
(see docs/phase_specifications.md, "Why Phases 1-5 have no week axis at all"),
so repetition across seeds is for statistics, not for time.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .config import Phase1Config

# Reasons a buyer-seller evaluation did not end in a purchase. Tracked because
# the phase's research question asks specifically whether inventory constrains
# sales, and a bare purchase count cannot answer that.
NO_PURCHASE_UTILITY = "utility_draw"
NO_PURCHASE_BUDGET = "budget_exhausted"
NO_PURCHASE_INVENTORY = "inventory_empty"


@dataclass
class Transaction:
    seed: int
    buyer_id: int
    seller_id: int
    visit_order: int
    price: float
    budget_before: float
    budget_after: float
    seller_inventory_after: int


@dataclass
class RunResult:
    """Everything one seed produced, before it is flattened into CSVs."""

    config_name: str
    seed: int
    transactions: list[Transaction]
    buyer_n_purchases: np.ndarray
    buyer_total_spent: np.ndarray
    buyer_budget_remaining: np.ndarray
    seller_n_sold: np.ndarray
    seller_revenue: np.ndarray
    seller_inventory_remaining: np.ndarray
    blocked_counts: dict[str, int] = field(default_factory=dict)

    @property
    def participation_rate(self) -> float:
        """Share of buyers who made at least one purchase."""
        return float(np.mean(self.buyer_n_purchases > 0))

    @property
    def avg_purchases_per_buyer(self) -> float:
        return float(np.mean(self.buyer_n_purchases))

    @property
    def total_revenue(self) -> float:
        return float(np.sum(self.seller_revenue))

    @property
    def total_inventory_remaining(self) -> int:
        return int(np.sum(self.seller_inventory_remaining))


def sigmoid(x: float | np.ndarray) -> float | np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


def purchase_probability(
    cfg: Phase1Config, budget_remaining: float, price: float, preference: float
) -> float:
    """P(purchase) for one buyer facing one seller.

    utility = 1.0 + 0.05*(budget_remaining - price)
              - alpha*(price/price_normalizer) + 1.5*preference
    P       = sigmoid(utility - 2.0)

    price_normalizer is the highest posted price in the phase's configuration
    (3 in Phase 1), not budget_per_visit.
    """
    utility = (
        cfg.intercept
        + cfg.budget_coef * (budget_remaining - price)
        - cfg.buyer.price_sensitivity * (price / cfg.price_normalizer)
        + cfg.preference_coef * preference
    )
    return float(sigmoid(utility - cfg.sigmoid_offset))


def run_single(cfg: Phase1Config, seed: int) -> RunResult:
    """Run one static market session.

    All random inputs are drawn up front, before any decision is made, so the
    random stream does not depend on outcomes. That is what makes the
    inventory-pressure variant a genuinely paired comparison against the main
    run: on a given seed, both see identical preferences, identical visit
    orders, and identical purchase draws, and differ only in stock level.
    """
    rng = np.random.default_rng(seed)

    # preference[b, s]: buyer b's fixed taste for seller s, drawn once per run.
    preference = rng.random((cfg.n_buyers, cfg.n_sellers))
    # visit_orders[b]: the order buyer b walks the stalls.
    visit_orders = np.array(
        [rng.permutation(cfg.n_sellers) for _ in range(cfg.n_buyers)]
    )
    # purchase_draw[b, s]: the uniform compared against P(purchase).
    purchase_draw = rng.random((cfg.n_buyers, cfg.n_sellers))

    budget = np.full(cfg.n_buyers, cfg.buyer.budget_per_visit, dtype=float)
    inventory = np.full(cfg.n_sellers, cfg.seller.inventory, dtype=int)
    buyer_n_purchases = np.zeros(cfg.n_buyers, dtype=int)
    buyer_total_spent = np.zeros(cfg.n_buyers, dtype=float)
    seller_n_sold = np.zeros(cfg.n_sellers, dtype=int)
    seller_revenue = np.zeros(cfg.n_sellers, dtype=float)

    blocked = {
        NO_PURCHASE_UTILITY: 0,
        NO_PURCHASE_BUDGET: 0,
        NO_PURCHASE_INVENTORY: 0,
    }
    transactions: list[Transaction] = []
    price = cfg.seller.price

    for buyer_id in range(cfg.n_buyers):
        for visit_order, seller_id in enumerate(visit_orders[buyer_id]):
            seller_id = int(seller_id)
            p_purchase = purchase_probability(
                cfg, budget[buyer_id], price, preference[buyer_id, seller_id]
            )
            wants_to_buy = p_purchase > purchase_draw[buyer_id, seller_id]
            can_afford = price <= budget[buyer_id]
            in_stock = inventory[seller_id] > 0

            if not (wants_to_buy and can_afford and in_stock):
                # Attribute the block to the binding constraint, hard
                # constraints first: "could not" is more informative than
                # "did not want to" when both are true.
                if not can_afford:
                    blocked[NO_PURCHASE_BUDGET] += 1
                elif not in_stock:
                    blocked[NO_PURCHASE_INVENTORY] += 1
                else:
                    blocked[NO_PURCHASE_UTILITY] += 1
                continue

            budget_before = float(budget[buyer_id])
            budget[buyer_id] -= price
            inventory[seller_id] -= 1
            buyer_n_purchases[buyer_id] += 1
            buyer_total_spent[buyer_id] += price
            seller_n_sold[seller_id] += 1
            seller_revenue[seller_id] += price
            transactions.append(
                Transaction(
                    seed=seed,
                    buyer_id=buyer_id,
                    seller_id=seller_id,
                    visit_order=visit_order,
                    price=price,
                    budget_before=budget_before,
                    budget_after=float(budget[buyer_id]),
                    seller_inventory_after=int(inventory[seller_id]),
                )
            )

    return RunResult(
        config_name=cfg.name,
        seed=seed,
        transactions=transactions,
        buyer_n_purchases=buyer_n_purchases,
        buyer_total_spent=buyer_total_spent,
        buyer_budget_remaining=budget,
        seller_n_sold=seller_n_sold,
        seller_revenue=seller_revenue,
        seller_inventory_remaining=inventory,
        blocked_counts=blocked,
    )


def run_seeds(cfg: Phase1Config) -> list[RunResult]:
    return [run_single(cfg, seed) for seed in cfg.seeds]
