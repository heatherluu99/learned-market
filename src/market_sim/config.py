"""Phase 1 configuration.

Values come straight from docs/phase_specifications.md, Phase 1 —
Transaction Mechanics. Nothing here is tuned; if a number changes, the spec
changes first (ROADMAP.md, "Phase design review gate").
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BuyerParams:
    """Buyer parameters. In Phase 1 all buyers share one instance of this."""

    budget_per_visit: float
    price_sensitivity: float  # alpha


@dataclass(frozen=True)
class SellerParams:
    """Seller parameters. In Phase 1 all sellers share one instance of this."""

    price: float
    inventory: int


@dataclass(frozen=True)
class Phase1Config:
    name: str
    n_buyers: int
    n_sellers: int
    buyer: BuyerParams
    seller: SellerParams
    seeds: tuple[int, ...]

    # Utility coefficients, spelled out rather than inlined in the engine so
    # the formula in the spec and the formula in the code can be diffed by eye:
    #   utility = intercept
    #           + budget_coef * (budget_remaining - price)
    #           - price_sensitivity * (price / price_normalizer)
    #           + preference_coef * preference
    #   P(purchase) = sigmoid(utility - sigmoid_offset)
    intercept: float = 1.0
    budget_coef: float = 0.05
    preference_coef: float = 1.5
    sigmoid_offset: float = 2.0

    @property
    def price_normalizer(self) -> float:
        """Highest posted price in this phase's initial configuration.

        Derived, never hand-written, so it cannot drift out of sync with the
        prices it normalizes. Deliberately not `budget_per_visit`: the utility
        function already has a budget term, and from Phase 2 on budget is
        class-specific, so a budget denominator would give each class a second
        price-scaling tangled with `price_sensitivity` itself. See
        docs/phase_specifications.md, "Utility Price Normalizer - Design Basis".

        Phase 1 is homogeneous, so the highest posted price is the only posted
        price. Phase 2 onward takes the max across seller classes.

        Reading it off the frozen config is also what locks it: from Phase 7 on,
        sellers adjust prices weekly, but those prices live in run state, not
        here, so a learned price can never move this denominator.
        """
        return self.seller.price


#: The Phase 1 experiment exactly as specified.
PHASE1_MAIN = Phase1Config(
    name="phase1_main",
    n_buyers=80,
    n_sellers=4,
    buyer=BuyerParams(budget_per_visit=5.0, price_sensitivity=0.5),
    seller=SellerParams(price=3.0, inventory=120),
    seeds=tuple(range(30)),
)

#: Inventory-pressure side experiment (not part of the spec's main run).
#:
#: Under PHASE1_MAIN the inventory constraint cannot bind: budget 5 and price 3
#: mean each buyer can afford at most one unit, capping market-wide demand at
#: 80 units against 4*120 = 480 units of stock. So the main run cannot answer
#: the phase's own question "does inventory constrain sales?", and its
#: `total_inventory_remaining > 0` acceptance check passes no matter what the
#: inventory bookkeeping does.
#:
#: This variant drops inventory to 15/seller (60 units, below the ~69 units of
#: expected demand) so that stock genuinely runs out. It shares every other
#: parameter and every random draw with the main run, making it a paired
#: comparison on identical seeds.
PHASE1_INVENTORY_PRESSURE = Phase1Config(
    name="phase1_inventory_pressure",
    n_buyers=80,
    n_sellers=4,
    buyer=BuyerParams(budget_per_visit=5.0, price_sensitivity=0.5),
    seller=SellerParams(price=3.0, inventory=15),
    seeds=tuple(range(30)),
)
