"""Transaction engine.

One run = one static market session: every buyer visits every seller once, in
a random order, and decides whether to buy. There is no week axis through
Phase 5 (see docs/phase_specifications.md, "Why Phases 1-5 have no week axis at
all"), so repetition across seeds is for statistics, not for time.

The same engine runs Phase 1 and Phase 2. Phase 1 is simply the case where
every buyer class and seller class has one member, so its numbers must not move
when heterogeneity is added — there is a regression test pinning them.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .config import MarketConfig

# Reasons a buyer-seller evaluation did not end in a purchase. Tracked because
# Phase 1's research question asks specifically whether inventory constrains
# sales, and Phase 2's asks whether affordability excludes classes from a tier;
# a bare purchase count answers neither.
NO_PURCHASE_UTILITY = "utility_draw"
NO_PURCHASE_BUDGET = "budget_exhausted"
NO_PURCHASE_INVENTORY = "inventory_empty"
#: Phase 3 onward: the stall was never noticed, so no decision was made at all.
#: Kept distinct from "did not want to buy" - a buyer who never saw a stall has
#: not expressed a preference about it.
NO_PURCHASE_UNNOTICED = "not_noticed"


@dataclass
class Transaction:
    seed: int
    buyer_id: int
    buyer_class: str
    seller_id: int
    seller_class: str
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
    buyer_classes: list[str]
    seller_classes: list[str]
    transactions: list[Transaction]
    buyer_n_purchases: np.ndarray
    buyer_total_spent: np.ndarray
    buyer_budget_remaining: np.ndarray
    seller_n_sold: np.ndarray
    seller_revenue: np.ndarray
    seller_inventory_remaining: np.ndarray
    blocked_counts: dict[str, int] = field(default_factory=dict)
    #: (buyer_class, seller_class) -> evaluations blocked by affordability.
    #: Phase 2 needs this to show that a class was priced out of a tier rather
    #: than choosing to avoid it.
    blocked_by_budget_pairs: dict[tuple[str, str], int] = field(default_factory=dict)
    #: Phase 3 onward: how many buyers noticed each seller this run. The
    #: realized counterpart of the configured visibility_prob.
    seller_noticed: np.ndarray | None = None

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

    def tier_share(self, buyer_class: str, seller_class: str) -> float:
        """Share of `buyer_class`'s purchases that went to `seller_class`.

        NaN when that class bought nothing at all this run — an undefined
        share, which must not be silently read as zero.
        """
        own = [t for t in self.transactions if t.buyer_class == buyer_class]
        if not own:
            return float("nan")
        return sum(1 for t in own if t.seller_class == seller_class) / len(own)

    def visibility_rate_by_seller(self, n_buyers: int) -> np.ndarray:
        """Realized share of buyers who noticed each seller."""
        if self.seller_noticed is None:
            return np.ones(len(self.seller_n_sold))
        return self.seller_noticed / n_buyers

    def participation_rate_of(self, buyer_class: str) -> float:
        mask = np.array([c == buyer_class for c in self.buyer_classes])
        if not mask.any():
            return float("nan")
        return float(np.mean(self.buyer_n_purchases[mask] > 0))


def sigmoid(x: float | np.ndarray) -> float | np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


def purchase_probability(
    cfg: MarketConfig,
    budget_remaining: float,
    price: float,
    preference: float,
    price_sensitivity: float,
    price_reference: float,
) -> float:
    """P(purchase) for one buyer facing one seller.

    utility = 1.0 + 0.05*(budget_remaining - price)
              - alpha*(price/price_reference) + 1.5*preference
    P       = sigmoid(utility - 2.0)

    `price_reference` is passed in rather than read from the seller being
    scored, and the caller is expected to pass the same market-wide value for
    every seller in the run. It is the max posted price at configuration time
    (3 in Phase 1, max(2, 6) = 6 in Phase 2) — not budget_per_visit, and
    emphatically not `price` itself, which would make the ratio 1.0 at every
    stall and delete the price term. See docs/phase_specifications.md,
    "Price Normalization Convention".
    """
    utility = (
        cfg.intercept
        + cfg.budget_coef * (budget_remaining - price)
        - price_sensitivity * (price / price_reference)
        + cfg.preference_coef * preference
    )
    return float(sigmoid(utility - cfg.sigmoid_offset))


def run_single(cfg: MarketConfig, seed: int) -> RunResult:
    """Run one static market session.

    All random inputs are drawn up front, before any decision is made, so the
    random stream does not depend on outcomes. That is what makes paired
    comparisons genuinely paired — Phase 1's inventory-pressure variant and
    Phase 2's common-alpha diagnostic both differ from their baseline in one
    parameter and in nothing else, including the random draws.

    The draw order (preferences, then visit orders, then purchase draws) is
    load-bearing: changing it would silently move every historical result.
    """
    n_buyers, n_sellers = cfg.n_buyers, cfg.n_sellers
    rng = np.random.default_rng(seed)

    # preference[b, s]: buyer b's fixed taste for seller s, drawn once per run.
    preference = rng.random((n_buyers, n_sellers))
    # visit_orders[b]: the order buyer b walks the stalls.
    visit_orders = np.array([rng.permutation(n_sellers) for _ in range(n_buyers)])
    # purchase_draw[b, s]: the uniform compared against P(purchase).
    purchase_draw = rng.random((n_buyers, n_sellers))
    # visibility_draw[b, s]: Phase 3 onward, whether buyer b notices seller s.
    # Drawn LAST, deliberately: everything above keeps the exact stream it had
    # before the environment existed, so Phase 1 and Phase 2 stay reproducible
    # at their validated tags, and Phase 3 is a properly paired comparison
    # against Phase 2 rather than a differently-randomized market.
    visibility_draw = rng.random((n_buyers, n_sellers))
    visibility_prob = np.array(cfg.visibility_prob_of(), dtype=float)

    buyer_class = cfg.buyer_class_of()
    seller_class = cfg.seller_class_of()
    budget = np.array(
        [c.budget_per_visit for c in cfg.buyer_classes for _ in range(c.count)],
        dtype=float,
    )
    alpha = np.array(
        [c.price_sensitivity for c in cfg.buyer_classes for _ in range(c.count)],
        dtype=float,
    )
    seller_price = np.array(
        [c.price for c in cfg.seller_classes for _ in range(c.count)], dtype=float
    )
    inventory = np.array(
        [c.inventory for c in cfg.seller_classes for _ in range(c.count)], dtype=int
    )

    buyer_n_purchases = np.zeros(n_buyers, dtype=int)
    buyer_total_spent = np.zeros(n_buyers, dtype=float)
    seller_n_sold = np.zeros(n_sellers, dtype=int)
    seller_revenue = np.zeros(n_sellers, dtype=float)

    blocked = {
        NO_PURCHASE_UTILITY: 0,
        NO_PURCHASE_BUDGET: 0,
        NO_PURCHASE_INVENTORY: 0,
        NO_PURCHASE_UNNOTICED: 0,
    }
    noticed = np.zeros(n_sellers, dtype=int)
    blocked_pairs: dict[tuple[str, str], int] = {}
    transactions: list[Transaction] = []
    # Read once, outside both loops: one market-wide value for every seller.
    price_reference = cfg.price_reference

    for buyer_id in range(n_buyers):
        for visit_order, seller_id in enumerate(visit_orders[buyer_id]):
            seller_id = int(seller_id)
            # Phase 3 environment: an unnoticed stall is skipped entirely — no
            # purchase decision is evaluated, so it is not a "chose not to buy".
            if visibility_draw[buyer_id, seller_id] >= visibility_prob[seller_id]:
                blocked[NO_PURCHASE_UNNOTICED] += 1
                continue
            noticed[seller_id] += 1

            price = seller_price[seller_id]
            p_purchase = purchase_probability(
                cfg,
                budget[buyer_id],
                price,
                preference[buyer_id, seller_id],
                alpha[buyer_id],
                price_reference,
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
                    key = (buyer_class[buyer_id], seller_class[seller_id])
                    blocked_pairs[key] = blocked_pairs.get(key, 0) + 1
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
                    buyer_class=buyer_class[buyer_id],
                    seller_id=seller_id,
                    seller_class=seller_class[seller_id],
                    visit_order=visit_order,
                    price=float(price),
                    budget_before=budget_before,
                    budget_after=float(budget[buyer_id]),
                    seller_inventory_after=int(inventory[seller_id]),
                )
            )

    return RunResult(
        config_name=cfg.name,
        seed=seed,
        buyer_classes=buyer_class,
        seller_classes=seller_class,
        transactions=transactions,
        buyer_n_purchases=buyer_n_purchases,
        buyer_total_spent=buyer_total_spent,
        buyer_budget_remaining=budget,
        seller_n_sold=seller_n_sold,
        seller_revenue=seller_revenue,
        seller_inventory_remaining=inventory,
        blocked_counts=blocked,
        blocked_by_budget_pairs=blocked_pairs,
        seller_noticed=noticed,
    )


def run_seeds(cfg: MarketConfig) -> list[RunResult]:
    return [run_single(cfg, seed) for seed in cfg.seeds]
