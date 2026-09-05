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
    #: Phase 6 onward: probability this class shows up in a given week. None
    #: means "always shows up", which is what Phases 1-5 assume. A buyer who
    #: does not show up makes no purchase decision at all - distinct from one
    #: who shopped and bought nothing.
    attendance_probability: float | None = None


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

    #: Phase 7 onward: seller cost model. Phases 1-6 have none, which is why
    #: "profit" was undefined before now and Phase 8's exit rule was
    #: unimplementable. One margin parameter rather than two independent costs,
    #: so unit cost is derived from the price it is charged against.
    unit_cost_fraction: float | None = None
    fixed_weekly_cost: float = 0.0
    #: Phase 7a: weekly price adaptation. None leaves prices fixed, which is
    #: every phase through 6. "hill_climb" keeps moving the price the way it
    #: moved last week while profit improves and reverses when it does not -
    #: no thresholds, and a natural equilibrium. See
    #: docs/phase_specifications.md, Phase 7a.
    price_rule: str | None = None
    price_step: float = 0.05
    #: Weeks of profit history used to judge whether a change is signal. A
    #: seller whose profit moved by less than its own recent noise has learned
    #: nothing and holds its price. Without this the rule random-walks wherever
    #: volume is thin - see docs/phase_specifications.md, Phase 7a.
    price_signal_window: int = 8
    #: Phase 7b: the bandit's arms, as multipliers on the seller's initial
    #: price. Deliberately left at the specified +/-20%: the Slow optimum is
    #: 1.5x, outside this range, and widening the arms to reach it would encode
    #: the answer into the hypothesis space. The ceiling is the finding.
    price_arms: tuple[float, ...] = (0.8, 0.9, 1.0, 1.1, 1.2)
    #: Exploration rate for price_rule="bandit_eps". Unused by UCB1, which has
    #: no hyperparameter - one reason both are run.
    bandit_epsilon: float = 0.1

    #: Phase 6 onward: weeks in one season. None means a single static
    #: session, which is what Phases 1-5 are.
    weeks: int | None = None
    #: Phase 6: loyalty bonus per consecutive week of the same choice,
    #: `bonus * min(streak, cap)`. 0.0 disables it, which is the control arm.
    loyalty_bonus_per_streak: float = 0.0
    #: Capped so the maximum bonus equals preference_coef: habit can match the
    #: strongest taste difference but never override it. See
    #: docs/phase_specifications.md, Phase 6.
    loyalty_streak_cap: int = 3

    #: Phase 5: budget-cliff nonlinearity. None disables it entirely (Phases
    #: 1-4). A float is the gap below which the penalty applies:
    #: `if (budget_remaining - price) < gap: utility -= penalty`.
    budget_cliff_gap: float | None = None
    budget_cliff_penalty: float = 1.0
    #: Phase 5 "replace" arm. False drops `budget_coef * (budget_remaining -
    #: price)` from the utility, leaving the cliff as the only channel by which
    #: remaining budget reaches utility. The spec is self-contradictory about
    #: whether Phase 5 replaces or augments the linear term, so both readings
    #: are built and compared rather than one being guessed at.
    use_linear_budget_term: bool = True

    #: Phase 4 onward: probability that some seller is discounted in a run.
    #: 0.0 means no promotion mechanism at all (Phases 1-3).
    promotion_probability: float = 0.0
    #: Fractional discount applied to the promoted seller's price for that run.
    promotion_discount: float = 0.3
    #: Diagnostic override: promote this seller id in every run regardless of
    #: the lottery. None leaves the lottery in charge. Used to build the paired
    #: arms the Phase 4 criteria are graded on - see
    #: docs/phase_specifications.md, Phase 4.
    forced_promotion_seller: int | None = None

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

    @property
    def has_costs(self) -> bool:
        return self.unit_cost_fraction is not None

    def unit_cost_of(self) -> list[float]:
        """Per-seller unit cost. Zero when no cost model is configured."""
        if self.unit_cost_fraction is None:
            return [0.0] * self.n_sellers
        return [
            c.price * self.unit_cost_fraction
            for c in self.seller_classes
            for _ in range(c.count)
        ]

    @property
    def has_adaptive_pricing(self) -> bool:
        return self.price_rule is not None

    @property
    def has_weeks(self) -> bool:
        return self.weeks is not None

    @property
    def has_loyalty(self) -> bool:
        return self.loyalty_bonus_per_streak > 0

    def attendance_prob_of(self) -> list[float]:
        """Attendance probability per buyer id. All 1.0 before Phase 6."""
        return [
            c.attendance_probability if c.attendance_probability is not None else 1.0
            for c in self.buyer_classes
            for _ in range(c.count)
        ]

    def max_loyalty_bonus(self) -> float:
        return self.loyalty_bonus_per_streak * self.loyalty_streak_cap

    @property
    def has_budget_cliff(self) -> bool:
        return self.budget_cliff_gap is not None

    @property
    def has_promotions(self) -> bool:
        return self.promotion_probability > 0 or self.forced_promotion_seller is not None

    def discounted_price(self, price: float) -> float:
        return price * (1.0 - self.promotion_discount)

    def expected_responder(self, seller_class_name: str) -> str | None:
        """Class predicted to respond most to a discount at this tier.

        Defined from the parameters alone: the lowest-budget class that can
        afford the discounted price. A discount matters most to buyers for
        whom it is the difference between reachable and not, and not at all to
        buyers who could already afford the stall or still cannot. Deriving it
        this way keeps Phase 4's interaction criterion a prediction rather than
        a restatement of an observed result.
        """
        price = next(
            c.price for c in self.seller_classes if c.name == seller_class_name
        )
        discounted = self.discounted_price(price)
        affordable = [
            c for c in self.buyer_classes if c.budget_per_visit >= discounted
        ]
        if not affordable:
            return None
        return min(affordable, key=lambda c: c.budget_per_visit).name

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


# --------------------------------------------------------------------------
# Phase 4 — Person + Environment + Context
# --------------------------------------------------------------------------


def _phase4(name: str, probability: float, forced: int | None = None) -> MarketConfig:
    """Phase 3's market plus a temporary promotion, varying only how the
    promotion is decided."""
    return MarketConfig(
        name=name,
        phase=4,
        buyer_classes=PHASE3_MAIN.buyer_classes,
        seller_classes=PHASE3_MAIN.seller_classes,
        seeds=PHASE3_MAIN.seeds,
        promotion_probability=probability,
        promotion_discount=0.3,
        forced_promotion_seller=forced,
    )


#: The market as specified: a 30% discount lands on one random seller in about
#: one run in five. Reported for its aggregate behaviour, but not what the
#: criteria are graded on — at 0.2 over 30 seeds it yields roughly one promoted
#: run per seller, which cannot support a per-seller comparison. See
#: docs/phase_specifications.md, Phase 4.
PHASE4_MAIN = _phase4("phase4_main", probability=0.2)

#: Baseline arm: identical market, promotion mechanism switched off.
PHASE4_NO_PROMOTION = _phase4("phase4_no_promotion", probability=0.0)

#: One arm per seller, that seller discounted in every seed. Paired with
#: PHASE4_NO_PROMOTION seed by seed — identical preferences, visit orders,
#: purchase draws and visibility draws — giving 30 paired observations per
#: seller instead of about one.
PHASE4_FORCED = tuple(
    _phase4(f"phase4_forced_seller{i}", probability=0.0, forced=i)
    for i in range(PHASE3_MAIN.n_sellers)
)


# --------------------------------------------------------------------------
# Phase 5 — Nonlinear Behavioural Effects
# --------------------------------------------------------------------------


def _phase5(name: str, cliff: float | None, linear_term: bool) -> MarketConfig:
    """Phase 4's market, varying only how remaining budget enters utility."""
    return MarketConfig(
        name=name,
        phase=5,
        buyer_classes=PHASE4_MAIN.buyer_classes,
        seller_classes=PHASE4_MAIN.seller_classes,
        seeds=PHASE4_MAIN.seeds,
        promotion_probability=PHASE4_MAIN.promotion_probability,
        promotion_discount=PHASE4_MAIN.promotion_discount,
        budget_cliff_gap=cliff,
        budget_cliff_penalty=1.0,
        use_linear_budget_term=linear_term,
    )


#: Baseline arm: Phase 4 exactly, no cliff. Named separately from PHASE4_MAIN
#: so Phase 5's own outputs are self-contained.
PHASE5_LINEAR = _phase5("phase5_linear", cliff=None, linear_term=True)

#: The additive reading: the smooth linear term stays and the cliff is added
#: on top. Supported by the mechanism's own rationale - "not captured by the
#: smooth linear term" presupposes that term still exists.
PHASE5_ADDITIVE = _phase5("phase5_additive", cliff=0.5, linear_term=True)

#: The replacement reading: the linear budget term is removed and the cliff is
#: the only route by which remaining budget affects utility. Taken from the
#: spec's "Single changed dimension" line. Note this changes two things at
#: once by the project's own accounting, which is part of what the three-way
#: comparison is meant to expose.
PHASE5_CLIFF_ONLY = _phase5("phase5_cliff_only", cliff=0.5, linear_term=False)


# --------------------------------------------------------------------------
# Phase 6 — Repeated Interaction (history becomes real here)
# --------------------------------------------------------------------------

#: Phase 4's market with a time axis. Phase 5 rejected the budget cliff, so the
#: single-week mechanics inherited here are the linear ones - see
#: docs/phase_specifications.md, Phase 5's recorded result.
_PHASE6_BUYERS = tuple(
    BuyerClass(
        name=c.name,
        count=c.count,
        budget_per_visit=c.budget_per_visit,
        price_sensitivity=c.price_sensitivity,
        income=c.income,
        attendance_probability=p,
    )
    for c, p in zip(PHASE4_MAIN.buyer_classes, (0.85, 0.84, 0.82))
)


def _phase6(name: str, loyalty: float) -> MarketConfig:
    return MarketConfig(
        name=name,
        phase=6,
        buyer_classes=_PHASE6_BUYERS,
        seller_classes=PHASE4_MAIN.seller_classes,
        seeds=PHASE4_MAIN.seeds,
        weeks=22,
        loyalty_bonus_per_streak=loyalty,
        loyalty_streak_cap=3,
        promotion_probability=PHASE4_MAIN.promotion_probability,
        promotion_discount=PHASE4_MAIN.promotion_discount,
    )


#: 22 weeks, memory accumulating up to a bonus of 0.5 * 3 = 1.5 - equal to
#: preference_coef, so habit can match the strongest taste difference without
#: overriding it.
PHASE6_MAIN = _phase6("phase6_main", loyalty=0.5)

#: Control arm: identical market, loyalty disabled. Required because most of
#: the raw pair-stability level is seller popularity and fixed preference
#: rather than memory - see docs/phase_specifications.md, Phase 6.
PHASE6_NO_LOYALTY = _phase6("phase6_no_loyalty", loyalty=0.0)


# --------------------------------------------------------------------------
# Phase 7a — Heuristic Seller Pricing
# --------------------------------------------------------------------------

#: Three seasons, because a single one is not enough for a hill climber to
#: settle. Buyer-side mechanics are Phase 6's, unchanged.
PHASE7_WEEKS = 66


def _phase7(name: str, rule: str | None) -> MarketConfig:
    return MarketConfig(
        name=name,
        phase=7,
        buyer_classes=PHASE6_MAIN.buyer_classes,
        seller_classes=PHASE6_MAIN.seller_classes,
        seeds=PHASE6_MAIN.seeds,
        weeks=PHASE7_WEEKS,
        loyalty_bonus_per_streak=PHASE6_MAIN.loyalty_bonus_per_streak,
        loyalty_streak_cap=PHASE6_MAIN.loyalty_streak_cap,
        promotion_probability=PHASE6_MAIN.promotion_probability,
        promotion_discount=PHASE6_MAIN.promotion_discount,
        unit_cost_fraction=0.5,
        fixed_weekly_cost=10.0,
        price_rule=rule,
    )


#: Baseline arm: Phase 6's market run to 66 weeks with prices held fixed. The
#: cost model is active here too, so both arms are scored on the same profit.
PHASE7A_FIXED = _phase7("phase7a_fixed", rule=None)

#: Profit hill-climbing. Reads only profit, needs no hand-picked thresholds,
#: and stops short of the 3.00 optimum on purpose - that headroom is what
#: 7b-7d have to win. See docs/phase_specifications.md, Phase 7a.
PHASE7A_HILL = _phase7("phase7a_hill", rule="hill_climb")


# --------------------------------------------------------------------------
# Phase 7b — Multi-Armed Bandit (context-blind)
# --------------------------------------------------------------------------

#: Both algorithms are run because the choice between them flips the
#: graduation verdict: on identical arms and seeds, epsilon-greedy loses to 7a
#: and UCB1 beats it. See docs/phase_specifications.md, Phase 7b.
PHASE7B_EPS = _phase7("phase7b_eps", rule="bandit_eps")
PHASE7B_UCB = _phase7("phase7b_ucb", rule="bandit_ucb")
