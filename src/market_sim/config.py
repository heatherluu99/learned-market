"""Phase 1 configuration.

Values come straight from docs/phase_specifications.md, Phase 1 —
Transaction Mechanics. Nothing here is tuned; if a number changes, the spec
changes first (ROADMAP.md, "Phase design review gate").
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class BuyerParams:
    """Buyer parameters. In Phase 1 all buyers share one instance of this."""

    budget_per_visit: float
    price_sensitivity: float  # alpha


@dataclass(frozen=True)
class SellerParams:
    """Seller parameters. In Phase 1 all sellers share one instance of this.

    Deliberately has no knowledge of `price_reference`: a seller has no
    business knowing what the other stalls charge. Putting the market-wide
    normalizer here is what makes it easy to write the "divide by this
    seller's own price" bug, which collapses the price term to a constant.
    See docs/phase_specifications.md, "Price Normalization Convention".
    """

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
    #           - price_sensitivity * (price / price_reference)
    #           + preference_coef * preference
    #   P(purchase) = sigmoid(utility - sigmoid_offset)
    intercept: float = 1.0
    budget_coef: float = 0.05
    preference_coef: float = 1.5
    sigmoid_offset: float = 2.0

    #: Market-wide price normalizer: max posted price at configuration time.
    #: Stored, not computed on access — see __post_init__ and
    #: docs/phase_specifications.md, "Price Normalization Convention".
    price_reference: float = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "price_reference", self._initial_price_reference())

    def _initial_price_reference(self) -> float:
        """`max(s.price for s in active_sellers)` at week 0.

        Phase 1's seller population is homogeneous, so that max is over a
        single posted price. Phase 2 onward, where sellers come in classes,
        takes the max across those classes; the rule does not change, only the
        number of prices it ranges over.

        Computed here, once, at configuration time — and never again. That is
        the whole point: from Phase 7 sellers learn new prices weekly and from
        Phase 8 they enter and leave, so a normalizer recomputed from the
        *current* active sellers would drift with exactly the mechanisms those
        phases exist to measure. Run-state prices live outside this frozen
        config and have no path back into this value.
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
