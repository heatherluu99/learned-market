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

import dataclasses
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
    #: Phase 2 onward (added at the Phase 7 gate): lognormal sigma for
    #: within-class budget spread, with `budget_per_visit` as the class MEAN.
    #: None means every member holds the class value exactly, which is how
    #: Phases 1-6 were originally built and what produced the price cliff at
    #: Poor's budget. See docs/phase_specifications.md, "Population
    #: Specification - Within-Class Dispersion".
    budget_dispersion: float | None = None
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
    #: Phase 7e: pin this stall's unit cost instead of deriving it from `price`.
    #: Needed because the oracle sweep varies a stall's standing price, and a
    #: cost derived from that price makes the margin a constant fraction - the
    #: sweep would then measure a moving cost structure rather than demand.
    #: None keeps the derived cost, which is every phase through 7d.
    unit_cost: float | None = None

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

    #: Phase 6 path-dependence probe: force this buyer to skip `perturb_week`.
    #: The draw is made and then overridden, so the random stream is identical
    #: to the unperturbed run and any divergence is the memory state's doing.
    perturb_buyer: int | None = None
    perturb_week: int = 0
    #: Phase 6 shock probe: close this seller for exactly one week. Exogenous
    #: and one-off - endogenous entry and exit is Phase 8 and is not front-run
    #: here. See docs/phase_specifications.md, Phase 6.
    shock_seller: int | None = None
    shock_week: int | None = None

    #: Phase 8: seller entry and exit. None disables the mechanism entirely,
    #: which is every phase through 7e. "capital" exits a seller when its
    #: balance runs out; "streak" is the originally registered rule, exit
    #: after `exit_loss_weeks` consecutive losing weeks. Both are run - see
    #: docs/phase_specifications.md, Phase 8.
    exit_rule: str | None = None
    #: Starting capital, three weeks of fixed cost, so a seller earning nothing
    #: survives as long as the registered streak rule would have allowed.
    seller_endowment: float = 30.0
    exit_loss_weeks: int = 3
    #: Free entry: an entrant appears after this many consecutive weeks of
    #: mean active-seller profit above zero. Above zero is the textbook
    #: condition - entrants expect to cover their costs - and needs no
    #: threshold parameter, so it scales across the fixed-cost sweep.
    entry_profit_weeks: int = 2
    #: Fixed slots. Weekly draws are taken at this width whatever the
    #: occupancy, so two arms with different entry histories still consume the
    #: same random stream and stay paired on a seed. A capacity, not a target:
    #: at 20 the cheapest cells reached it and their equilibrium would have
    #: been the cap rather than the market, and at 40 the busiest cell peaks at
    #: 27. Checked at 60, where the answer does not move.
    max_sellers: int = 40

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

    #: Phase 7e: which loyalty mechanism is active. "streak" is the bounded
    #: counter of Phases 6-7d. "stock" is the mechanism-enabled environment's
    #: per-pair stock, which decays instead of resetting and accrues more from
    #: a cheaper purchase - the property that makes a discount buy something
    #: outlasting the week. See docs/phase_specifications.md, Phase 7e.
    loyalty_model: str = "streak"
    #: Weekly retention (rho). 0.80 gives a stock half-life of 3.1 weeks and
    #: costs a defector 20% of the stock rather than all of it.
    loyalty_retention: float = 0.80
    #: Accrual per purchase (beta) before the price adjustment.
    loyalty_increment: float = 0.25
    #: Sensitivity of accrual to the price paid (delta), denominated in one
    #: full arm move: a purchase at the cheapest arm accrues (1 + delta) times
    #: the base increment, the dearest (1 - delta) times, clamped at zero.
    #: delta = 0 is the control - a purchase is a purchase, and the mechanism
    #: has no investment channel at all.
    loyalty_deal_sensitivity: float = 0.0
    #: Saturation scale (L*) of the tanh, the stock level at which the bonus
    #: reaches 0.762 * L_max. Where the typical loyal buyer sits relative to
    #: this knee decides whether further investment still pays.
    loyalty_saturation: float = 1.25
    #: Ceiling on the stock bonus (L_max). Pinned at Phase 6's maximum streak
    #: bonus (0.5 * 3) so the two mechanisms share a ceiling and only the path
    #: to it differs - a 7e result cannot come from stronger habit.
    loyalty_max_bonus: float = 1.5
    #: Phase 9c: redraw `preference[b, s]` every week instead of once per
    #: season. Season-long taste is a *stabilizer* - it pulls a wandering buyer
    #: back toward the same stalls - and this ablates it. False everywhere
    #: before Phase 9c, and when False no extra draw is taken at all, so no
    #: earlier phase's random stream moves.
    weekly_preference: bool = False
    #: Phase 9b: temperature on the purchase logit. 1.0 is every phase before
    #: it. Below 1 sharpens the same preference ordering toward a step
    #: function; above 1 flattens it toward a coin flip. It changes how
    #: *decisively* a buyer acts, never what it prefers.
    teacher_temperature: float = 1.0
    #: Phase 9a: a learned buyer policy, `(observables) -> probability`. When
    #: set, buyers act on it instead of the hand-written rule - but the rule's
    #: own probability is still computed and recorded, so the teacher can be
    #: shadow-evaluated on states only the student would ever reach.
    buyer_policy: object | None = None
    #: Phase 9a: record every buyer-seller encounter - what the buyer could
    #: observe, the probability the hand-written rule computed, and the action
    #: it took. Off by default; only the buyer-distillation phase reads it.
    record_encounters: bool = False
    #: Keep the per-week (buyer, seller) bonus matrix on the SeasonResult.
    #: Off by default: only Phase 7e's calibration reads it, and it is the one
    #: run-state array whose size scales with buyers x sellers x weeks.
    record_loyalty_bonus: bool = False

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
        if self.loyalty_model not in ("streak", "stock"):
            raise ValueError(f"unknown loyalty_model {self.loyalty_model!r}")
        if self.exit_rule not in (None, "capital", "streak"):
            raise ValueError(f"unknown exit_rule {self.exit_rule!r}")
        if self.has_entry_exit and self.max_sellers < self.n_sellers:
            raise ValueError("max_sellers is below the starting seller count")
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
            c.unit_cost if c.unit_cost is not None else c.price * self.unit_cost_fraction
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
        return self.has_loyalty_stock or self.loyalty_bonus_per_streak > 0

    @property
    def has_loyalty_stock(self) -> bool:
        return self.loyalty_model == "stock"

    @property
    def has_entry_exit(self) -> bool:
        return self.exit_rule is not None

    @property
    def n_slots(self) -> int:
        """Draw width. Equal to the seller count unless entry/exit is on."""
        return self.max_sellers if self.has_entry_exit else self.n_sellers

    @property
    def arm_half_range(self) -> float:
        """The widest single price move available, used to denominate delta.

        Reading it off the arms rather than hard-coding 0.2 keeps delta
        meaning the same thing if the arm set is ever changed - which Phase
        7b's ceiling finding makes a live possibility.
        """
        return max(abs(m - 1.0) for m in self.price_arms)

    @property
    def has_budget_dispersion(self) -> bool:
        return any(c.budget_dispersion for c in self.buyer_classes)

    def buyer_budgets(self, seed: int) -> "np.ndarray":
        """Per-buyer budget for one run.

        Drawn from its own generator, so adding this mechanism moves no
        existing random stream and only *enabling* dispersion changes a result.
        Lognormal with the class value as the mean, so mu = ln(mean) -
        sigma^2/2 rather than ln(mean).
        """
        import numpy as np

        if not self.has_budget_dispersion:
            return np.array(
                [c.budget_per_visit for c in self.buyer_classes for _ in range(c.count)],
                dtype=float,
            )
        rng = np.random.default_rng(20_000 + seed)
        out = []
        for c in self.buyer_classes:
            if not c.budget_dispersion:
                out.extend([c.budget_per_visit] * c.count)
                continue
            sigma = c.budget_dispersion
            mu = np.log(c.budget_per_visit) - sigma**2 / 2
            out.extend(rng.lognormal(mu, sigma, size=c.count))
        return np.array(out, dtype=float)

    def attendance_prob_of(self) -> list[float]:
        """Attendance probability per buyer id. All 1.0 before Phase 6."""
        return [
            c.attendance_probability if c.attendance_probability is not None else 1.0
            for c in self.buyer_classes
            for _ in range(c.count)
        ]

    def max_loyalty_bonus(self) -> float:
        if self.has_loyalty_stock:
            return self.loyalty_max_bonus
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
            # dataclasses.replace, never a hand-listed field set: a new
            # BuyerClass field would otherwise be dropped here in silence.
            buyer_classes=tuple(
                dataclasses.replace(c, price_sensitivity=alpha)
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
        # budget_dispersion flows from here to Phases 3-7: those configs reuse
        # these classes, so the population is specified in exactly one place.
        BuyerClass("Poor", 70, 3.0, 0.85, income=25, budget_dispersion=0.12),
        BuyerClass("Middle", 20, 7.0, 0.5, income=55, budget_dispersion=0.12),
        BuyerClass("Rich", 10, 10.0, 0.2, income=100, budget_dispersion=0.12),
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
    dataclasses.replace(c, attendance_probability=p)
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


# --------------------------------------------------------------------------
# Phase 7d — Reinforcement Learning (multi-week credit assignment)
# --------------------------------------------------------------------------

#: Same market and same arms as 7b, so the comparison isolates the reward
#: horizon. price_rule="policy" hands arm selection to a callable; the training
#: code lives in market_sim.rl and the policy sees only the seller's own state,
#: since Phase 7c established there is no external state worth conditioning on.
PHASE7D = _phase7("phase7d_rl", rule="policy")

#: Seeds used to fit the policy. Disjoint from the 0-29 evaluation block every
#: other phase uses: a policy scored on the seeds it was fitted to measures
#: memorization. See docs/phase_specifications.md, Phase 7d.
PHASE7D_TRAIN_SEEDS = tuple(range(1000, 1120))


# --------------------------------------------------------------------------
# Phase 7e — Mechanism Sufficiency (a separate, mechanism-enabled environment)
# --------------------------------------------------------------------------

#: The registered baseline. rho was chosen at the design gate and the first
#: calibration run confirmed it - with lock-in strength held equal it gives
#: the longest realized memory of the four horizons tested.
PHASE7E_RHO = 0.80

#: Where the population sits on the tanh, as a multiple of L*: u = S/L* with
#: S = beta/(1 - rho) the steady-state stock of an every-week buyer. Fixed at
#: the empirical contrast maximum, so beta follows from rho rather than being
#: free. See docs/phase_specifications.md, Phase 7e-1.
PHASE7E_CURVATURE = 2.0
PHASE7E_SATURATION = 1.00

#: Starting point for the L_max calibration, not a fixed value: L_max is
#: solved per cell so the mechanism's incumbency advantage matches the
#: counter's. Pinning it at Phase 6's ceiling of 1.5 made the stock bind about
#: a third as hard as the counter, which is what the first run found.
PHASE7E_LMAX_SEED = 3.3

#: Registered accrual sensitivity to the price paid. Carried forward
#: unmeasured: at the flat prices 7e-1 runs on, delta is inert by construction
#: and is calibrated at 7e-2, where schedules supply the price variation.
PHASE7E_DELTA = 0.25

#: The swept dimension - memory horizon, as half-lives of 3.1, 4.3, 6.6 and
#: 13.5 weeks. beta moves with it to hold the steady-state stock fixed, so
#: horizon is swept independently of level.
PHASE7E_RETENTIONS = (0.80, 0.85, 0.90, 0.95)


def phase7e_beta(rho: float) -> float:
    """The accrual that puts an every-week buyer at u = S/L* on the tanh."""
    return PHASE7E_CURVATURE * PHASE7E_SATURATION * (1.0 - rho)


PHASE7E_BETA = phase7e_beta(PHASE7E_RHO)

#: The week a stall is closed for the gate-1 persistence probe. Phase 6 used
#: week 12 of 22; at 66 weeks the equivalent point is well past the stock's
#: 3.1-week half-life, so the shock lands on a converged state rather than on
#: one still filling up.
PHASE7E_SHOCK_WEEK = 40


def phase7e_cell(
    rho: float = PHASE7E_RHO,
    delta: float = PHASE7E_DELTA,
    saturation: float = PHASE7E_SATURATION,
    max_bonus: float = PHASE7E_LMAX_SEED,
) -> MarketConfig:
    """One calibration cell: Phase 7a's flat-price market, stock loyalty.

    Everything outside the loyalty mechanism is 7a's baseline arm, so the
    contrast against the base environment is the mechanism and nothing else.
    `max_bonus` is a starting point - the cell is only usable once
    `acceptance.calibrate_max_bonus` has solved it against the counter.
    """
    return dataclasses.replace(
        PHASE7A_FIXED,
        name=f"phase7e_r{int(rho * 100):03d}",
        loyalty_model="stock",
        # Zeroed rather than left at 0.5: the streak bonus is unreachable once
        # the stock model is on, and a config should not carry a number that
        # does nothing.
        loyalty_bonus_per_streak=0.0,
        loyalty_retention=rho,
        loyalty_increment=phase7e_beta(rho),
        loyalty_deal_sensitivity=delta,
        loyalty_saturation=saturation,
        loyalty_max_bonus=max_bonus,
        record_loyalty_bonus=True,
    )


#: The reference cell: Phases 6-7d's bounded counter, unchanged, with the bonus
#: matrix recorded so both mechanisms are read through identical code.
PHASE7E_COUNTER = dataclasses.replace(
    PHASE7A_FIXED, name="phase7e_counter", record_loyalty_bonus=True
)

PHASE7E_CELLS = tuple(phase7e_cell(rho=r) for r in PHASE7E_RETENTIONS)


# --------------------------------------------------------------------------
# Phase 8 — Endogenous Market Structure
# --------------------------------------------------------------------------

#: Five seasons. Whether the seller mix settles or oscillates is only visible
#: across several season boundaries - see docs/phase_specifications.md,
#: "Weeks and Seasons".
PHASE8_WEEKS = 110

#: The swept axis. Gross margin before fixed cost is 28.0 / 28.0 / 16.9 / 15.5
#: / 10.0 per starting seller, so 10.0 sits exactly on the weakest one's
#: break-even and the registered value would have decided the phase by itself.
PHASE8_FIXED_COSTS = (6.0, 8.0, 10.0, 12.0)

#: Both exit rules, run as a contrast rather than one chosen: sensitivity to
#: the rule's own form is then a reported quantity.
PHASE8_EXIT_RULES = ("capital", "streak")


def phase8_cell(exit_rule: str, fixed_cost: float) -> MarketConfig:
    """Phase 7a's fixed-price market with entry and exit switched on.

    Buyer and pricing mechanics are unchanged from Phase 7, which is what
    makes entry/exit the single changed dimension.
    """
    return dataclasses.replace(
        PHASE7A_FIXED,
        name=f"phase8_{exit_rule}_f{int(fixed_cost):02d}",
        phase=8,
        weeks=PHASE8_WEEKS,
        fixed_weekly_cost=fixed_cost,
        exit_rule=exit_rule,
    )


PHASE8_CELLS = tuple(
    phase8_cell(rule, cost)
    for rule in PHASE8_EXIT_RULES
    for cost in PHASE8_FIXED_COSTS
)


# --------------------------------------------------------------------------
# Phase 9c — which environment characteristics suppress divergence?
# --------------------------------------------------------------------------

#: The two entropy levels the ablation is run at: Phase 9a's, and the sharpest
#: regime Phase 9b measured, where amplification reached 1.67x.
PHASE9C_HIGH_ENTROPY = 1.0
PHASE9C_LOW_ENTROPY = 0.1

#: Opening the budget wall means giving Poor a budget that reaches the premium
#: tier's price of 6.0 rather than stopping at 3.0. Set well clear of it so the
#: wall is genuinely open rather than marginally so.
PHASE9C_OPEN_BUDGET = 8.0


def phase9c_cell(
    temperature: float, budget_wall: bool, fixed_preference: bool
) -> "MarketConfig":
    """One cell of the stabilizer ablation. Phase 6's market otherwise.

    The two stabilizers are removed one at a time and then together, because
    removing both at once cannot say which of them was doing the work.
    """
    buyers = tuple(
        c if budget_wall or c.name != "Poor"
        else dataclasses.replace(c, budget_per_visit=PHASE9C_OPEN_BUDGET)
        for c in PHASE6_MAIN.buyer_classes
    )
    wall = "wall" if budget_wall else "open"
    taste = "fixed" if fixed_preference else "weekly"
    return dataclasses.replace(
        PHASE6_MAIN,
        name=f"phase9c_t{int(temperature * 100):03d}_{wall}_{taste}",
        phase=9,
        buyer_classes=buyers,
        teacher_temperature=temperature,
        weekly_preference=not fixed_preference,
    )


#: The registered five rows: a high-entropy reference, then the low-entropy
#: regime with each stabilizer removed alone and both together.
PHASE9C_CELLS = (
    phase9c_cell(PHASE9C_HIGH_ENTROPY, budget_wall=True, fixed_preference=True),
    phase9c_cell(PHASE9C_LOW_ENTROPY, budget_wall=True, fixed_preference=True),
    phase9c_cell(PHASE9C_LOW_ENTROPY, budget_wall=False, fixed_preference=True),
    phase9c_cell(PHASE9C_LOW_ENTROPY, budget_wall=True, fixed_preference=False),
    phase9c_cell(PHASE9C_LOW_ENTROPY, budget_wall=False, fixed_preference=False),
)
