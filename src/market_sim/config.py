"""Market configuration.

Values come straight from docs/phase_specifications.md. Nothing here is tuned;
if a number changes, the spec changes first (ROADMAP.md, "Phase design review
gate").

Phase 1 is expressed in the same structure as Phase 2 — one buyer class of 80
and one seller class of 4 — rather than kept in a separate homogeneous type.
One engine then runs both, and Phase 1's numbers are protected by a regression
test rather than by a second code path.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class BuyerClass:
    """One buyer class. Phase 1 has a single one; Phase 2 has three."""

    name: str
    count: int
    budget_per_visit: float
    price_sensitivity: float  # alpha
    #: Descriptive only — income does not enter the purchase rule in any phase
    #: through Phase 8. Recorded so the population is documented, not used.
    income: float | None = None


@dataclass(frozen=True)
class SellerClass:
    """One seller class.

    Deliberately has no knowledge of `price_reference`: a seller has no
    business knowing what the other stalls charge. Putting the market-wide
    normalizer here is what makes it easy to write the "divide by this seller's
    own price" bug, which collapses the price term to a constant. See
    docs/phase_specifications.md, "Price Normalization Convention".
    """

    name: str
    count: int
    price: float
    inventory: int
    #: Phase 3 onward. None means "no environment" — every stall is always
    #: noticed, which is what Phases 1 and 2 assume. A float in [0, 1] gives
    #: `visibility_prob = 0.5 + 0.5 * position_score` (1 = by the entrance).
    #: Sellers of the same class can differ here, so Phase 3 lists one
    #: SellerClass per position rather than per price tier.
    position_score: float | None = None

    @property
    def visibility_prob(self) -> float:
        """Probability a given buyer notices this stall in a given run."""
        if self.position_score is None:
            return 1.0
        return 0.5 + 0.5 * self.position_score


@dataclass(frozen=True)
class MarketConfig:
    name: str
    phase: int
    buyer_classes: tuple[BuyerClass, ...]
    seller_classes: tuple[SellerClass, ...]
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
        if not self.seller_classes:
            raise ValueError("a market needs at least one seller class")
        object.__setattr__(self, "price_reference", self._initial_price_reference())

    def _initial_price_reference(self) -> float:
        """`max(s.price for s in active_sellers)` at week 0.

        Computed here, once, at configuration time — and never again. That is
        the whole point: from Phase 7 sellers learn new prices weekly and from
        Phase 8 they enter and leave, so a normalizer recomputed from the
        *current* active sellers would drift with exactly the mechanisms those
        phases exist to measure. Run-state prices live outside this frozen
        config and have no path back into this value.
        """
        return max(s.price for s in self.seller_classes)

    @property
    def n_buyers(self) -> int:
        return sum(c.count for c in self.buyer_classes)

    @property
    def n_sellers(self) -> int:
        return sum(c.count for c in self.seller_classes)

    def buyer_class_of(self) -> list[str]:
        """Class label per buyer id. Assignment is fixed, never randomized."""
        return [c.name for c in self.buyer_classes for _ in range(c.count)]

    def seller_class_of(self) -> list[str]:
        return [c.name for c in self.seller_classes for _ in range(c.count)]

    def seller_tier_names(self) -> list[str]:
        """Distinct seller tier names, in configuration order.

        From Phase 3 a tier can span several SellerClass entries — same price,
        different position — so the entry list is no longer one per tier and
        must be deduplicated before it is used to name output columns.
        """
        seen: list[str] = []
        for c in self.seller_classes:
            if c.name not in seen:
                seen.append(c.name)
        return seen

    def visibility_prob_of(self) -> list[float]:
        """Visibility probability per seller id. All 1.0 before Phase 3."""
        return [c.visibility_prob for c in self.seller_classes for _ in range(c.count)]

    @property
    def has_environment(self) -> bool:
        return any(c.position_score is not None for c in self.seller_classes)

    def with_common_price_sensitivity(self, alpha: float, name: str) -> "MarketConfig":
        """Same market with every class sharing one alpha.

        Used for Phase 2's required attribution diagnostic: budget
        heterogeneity and price-sensitivity heterogeneity are both
        "person-level heterogeneity", and this separates their contributions.
        """
        return MarketConfig(
            name=name,
            phase=self.phase,
            buyer_classes=tuple(
                BuyerClass(
                    name=c.name,
                    count=c.count,
                    budget_per_visit=c.budget_per_visit,
                    price_sensitivity=alpha,
                    income=c.income,
                )
                for c in self.buyer_classes
            ),
            seller_classes=self.seller_classes,
            seeds=self.seeds,
            intercept=self.intercept,
            budget_coef=self.budget_coef,
            preference_coef=self.preference_coef,
            sigmoid_offset=self.sigmoid_offset,
        )


# --------------------------------------------------------------------------
# Phase 1 — Transaction Mechanics (homogeneous)
# --------------------------------------------------------------------------

PHASE1_MAIN = MarketConfig(
    name="phase1_main",
    phase=1,
    buyer_classes=(
        BuyerClass("Homogeneous", count=80, budget_per_visit=5.0, price_sensitivity=0.5),
    ),
    seller_classes=(SellerClass("Homogeneous", count=4, price=3.0, inventory=120),),
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
#: This variant drops inventory to 15/seller (60 units, below the ~66 units of
#: expected demand) so that stock genuinely runs out. It shares every other
#: parameter and every random draw with the main run, making it a paired
#: comparison on identical seeds.
PHASE1_INVENTORY_PRESSURE = MarketConfig(
    name="phase1_inventory_pressure",
    phase=1,
    buyer_classes=(
        BuyerClass("Homogeneous", count=80, budget_per_visit=5.0, price_sensitivity=0.5),
    ),
    seller_classes=(SellerClass("Homogeneous", count=4, price=3.0, inventory=15),),
    seeds=tuple(range(30)),
)


# --------------------------------------------------------------------------
# Phase 2 — Linear Consumer Heterogeneity
# --------------------------------------------------------------------------

#: Buyers 7:2:1 Poor:Middle:Rich, sellers 3 Slow : 2 Shigh, both 20:1 overall.
#:
#: Middle's budget is 7, not the originally specified 5: at 5 it could not
#: afford the Shigh price of 6 at all, making this phase's second research
#: question (how the middle class splits between tiers) unanswerable by
#: arithmetic. Poor's budget of 3 still cannot reach Shigh — that exclusion is
#: kept deliberately, but it is an affordability wall, not a price-sensitivity
#: result. See docs/phase_specifications.md, Phase 2.
PHASE2_MAIN = MarketConfig(
    name="phase2_main",
    phase=2,
    buyer_classes=(
        BuyerClass("Poor", count=70, budget_per_visit=3.0, price_sensitivity=0.85, income=25),
        BuyerClass("Middle", count=20, budget_per_visit=7.0, price_sensitivity=0.5, income=55),
        BuyerClass("Rich", count=10, budget_per_visit=10.0, price_sensitivity=0.2, income=100),
    ),
    seller_classes=(
        SellerClass("Slow", count=3, price=2.0, inventory=130),
        SellerClass("Shigh", count=2, price=6.0, inventory=70),
    ),
    seeds=tuple(range(30)),
)

#: Attribution diagnostic: same market, one alpha for every class. Isolates how
#: much of the stratification comes from price sensitivity rather than from
#: budget heterogeneity. Required reporting, not a pass/fail bar.
PHASE2_COMMON_ALPHA = PHASE2_MAIN.with_common_price_sensitivity(
    0.5, name="phase2_common_alpha"
)


# --------------------------------------------------------------------------
# Phase 3 — Person + Environment
# --------------------------------------------------------------------------

#: Phase 2's market plus one environment variable: stall position, which drives
#: how likely a buyer is to notice a stall at all. Nothing else changes —
#: buyers, prices, inventories and the utility function are Phase 2's.
#:
#: A tier now spans two entries, because same-price stalls sit in different
#: places. Seller ids come out as 0,1 = Slow near / 2 = Slow far /
#: 3 = Shigh near / 4 = Shigh far.
#:
#: Note the tier-level asymmetry this assignment creates: mean visibility is
#: 0.850 for Slow against 0.775 for Shigh, because 2 of 3 Slow stalls are near
#: but only 1 of 2 Shigh stalls is. Any tier-share movement is partly an
#: artifact of that choice. See docs/phase_specifications.md, Phase 3.
PHASE3_MAIN = MarketConfig(
    name="phase3_main",
    phase=3,
    buyer_classes=PHASE2_MAIN.buyer_classes,
    seller_classes=(
        SellerClass("Slow", count=2, price=2.0, inventory=130, position_score=0.9),
        SellerClass("Slow", count=1, price=2.0, inventory=130, position_score=0.3),
        SellerClass("Shigh", count=1, price=6.0, inventory=70, position_score=0.8),
        SellerClass("Shigh", count=1, price=6.0, inventory=70, position_score=0.3),
    ),
    seeds=PHASE2_MAIN.seeds,
)
