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
#: Phase 6 onward: the buyer did not shop that week at all. Distinct from
#: shopping and buying nothing - no decision was made either way.
NO_PURCHASE_ABSENT = "did_not_shop"


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
    #: Phase 4 onward: which seller was discounted this run, if any.
    promoted_seller: int | None = None
    #: Posted price actually charged per seller this run, after any discount.
    effective_prices: np.ndarray | None = None
    #: Phase 7 onward: revenue - unit_cost*sold - fixed_weekly_cost, per seller.
    #: None before a cost model exists, which is every phase through 6.
    seller_profit: np.ndarray | None = None

    def n_sold_by(self, buyer_class: str, seller_id: int) -> int:
        """Units this class bought from one specific seller."""
        return sum(
            1
            for t in self.transactions
            if t.buyer_class == buyer_class and t.seller_id == seller_id
        )

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
    loyalty_bonus: float = 0.0,
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
        - price_sensitivity * (price / price_reference)
        + cfg.preference_coef * preference
    )
    if cfg.use_linear_budget_term:
        utility += cfg.budget_coef * (budget_remaining - price)
    # Phase 5: reluctance to spend down to near-nothing, a reference-point
    # effect the smooth linear term cannot express (Kahneman & Tversky 1979).
    if cfg.budget_cliff_gap is not None:
        if (budget_remaining - price) < cfg.budget_cliff_gap:
            utility -= cfg.budget_cliff_penalty
    # Phase 6: habit. Passed in rather than read from cfg because it depends on
    # the buyer's streak, which is run state, not configuration.
    utility += loyalty_bonus
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
    # Promotion draws come last, after visibility, for the same reason
    # visibility came after the purchase draw: every earlier phase keeps the
    # exact stream it had. They are drawn unconditionally - even by configs
    # with no promotion mechanism - so that all Phase 4 arms (lottery, forced,
    # and none) stay paired with each other seed by seed.
    promotion_roll = rng.random()
    promotion_pick = int(rng.integers(0, n_sellers))

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
    if cfg.forced_promotion_seller is not None:
        promoted_seller: int | None = cfg.forced_promotion_seller
    elif promotion_roll < cfg.promotion_probability:
        promoted_seller = promotion_pick
    else:
        promoted_seller = None
    if promoted_seller is not None:
        seller_price[promoted_seller] = cfg.discounted_price(
            seller_price[promoted_seller]
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
        promoted_seller=promoted_seller,
        effective_prices=seller_price.copy(),
    )


def run_seeds(cfg: MarketConfig) -> list[RunResult]:
    return [run_single(cfg, seed) for seed in cfg.seeds]


@dataclass
class SeasonResult:
    """One 22-week season. State persists across weeks; outputs do not.

    Phases 1-5 repeat a static market for statistics; this repeats it as a
    timeline. The distinction is the whole point of Phase 6 - see
    docs/phase_specifications.md, "Why Phases 1-5 have no week axis at all".
    """

    config_name: str
    seed: int
    weeks: list[RunResult]
    #: (week, buyer) chosen seller that week, -1 if the buyer bought nothing.
    chosen_seller: np.ndarray
    #: (week, buyer) whether the buyer showed up at all.
    attended: np.ndarray
    #: (week, buyer) consecutive weeks the chosen seller has been the choice.
    streaks: np.ndarray
    #: (week, seller) the price posted before that week's promotion, if any.
    #: Constant across weeks unless the phase has adaptive pricing.
    posted_prices: np.ndarray | None = None
    #: (week, seller) profit. None before a cost model exists.
    profits: np.ndarray | None = None

    @property
    def n_weeks(self) -> int:
        return len(self.weeks)

    def attendance_rate(self) -> np.ndarray:
        """Per week: share of buyers who showed up."""
        return self.attended.mean(axis=1)

    def purchase_rate(self) -> np.ndarray:
        """Per week: share of buyers who bought something.

        Kept separate from attendance because they are different quantities:
        a buyer can show up and buy nothing. Phases 1-5's `participation_rate`
        is this one, so this is what the 0.6-1.0 band applies to.
        """
        return (self.chosen_seller >= 0).mean(axis=1)

    def pair_stability(self) -> np.ndarray:
        """Per week: share of buyers whose chosen seller matches last week's.

        Denominator is buyers who bought in *both* weeks - a buyer who skipped
        a week has no choice to compare, and counting them as a mismatch would
        confound attendance with loyalty. Week 0 is NaN: nothing precedes it.
        """
        out = np.full(self.n_weeks, np.nan)
        for w in range(1, self.n_weeks):
            both = (self.chosen_seller[w] >= 0) & (self.chosen_seller[w - 1] >= 0)
            if both.any():
                out[w] = float(
                    (self.chosen_seller[w][both] == self.chosen_seller[w - 1][both]).mean()
                )
        return out

    def tier_share(self, buyer_class: str, seller_class: str) -> float:
        """Season-wide share of a class's purchases that went to a tier."""
        own = [t for r in self.weeks for t in r.transactions if t.buyer_class == buyer_class]
        if not own:
            return float("nan")
        return sum(1 for t in own if t.seller_class == seller_class) / len(own)


def _choice_of_week(bought: list[int]) -> int:
    """The seller a buyer is taken to have chosen this week.

    Most units purchased, ties broken by first encountered. Deliberately not
    "most recent": that depends on the buyer's random stall order that week,
    which would inject noise into what is meant to be a memory state. See
    docs/phase_specifications.md, Phase 6.
    """
    if not bought:
        return -1
    counts: dict[int, int] = {}
    for s in bought:
        counts[s] = counts.get(s, 0) + 1
    best = max(counts.values())
    for s in bought:  # first encountered among the maxima
        if counts[s] == best:
            return s
    return -1


def run_season(cfg: MarketConfig, seed: int) -> SeasonResult:
    """Run one season of `cfg.weeks` weeks with persistent buyer memory.

    Budget and inventory reset every week; `last_seller_purchased` and the
    loyalty streak do not - that persistence is the phase's changed dimension.
    Preference is drawn once for the whole season, since the "run" the earlier
    phases fixed it over is now a season rather than a single session.
    """
    if cfg.weeks is None:
        raise ValueError(f"{cfg.name} has no week axis; use run_single")

    n_buyers, n_sellers = cfg.n_buyers, cfg.n_sellers
    rng = np.random.default_rng(seed)
    preference = rng.random((n_buyers, n_sellers))

    buyer_class = cfg.buyer_class_of()
    seller_class = cfg.seller_class_of()
    budget0 = np.array(
        [c.budget_per_visit for c in cfg.buyer_classes for _ in range(c.count)], dtype=float
    )
    alpha = np.array(
        [c.price_sensitivity for c in cfg.buyer_classes for _ in range(c.count)], dtype=float
    )
    price0 = np.array(
        [c.price for c in cfg.seller_classes for _ in range(c.count)], dtype=float
    )
    inventory0 = np.array(
        [c.inventory for c in cfg.seller_classes for _ in range(c.count)], dtype=int
    )
    visibility_prob = np.array(cfg.visibility_prob_of(), dtype=float)
    attendance_prob = np.array(cfg.attendance_prob_of(), dtype=float)
    price_reference = cfg.price_reference

    unit_cost = np.array(cfg.unit_cost_of(), dtype=float)
    last_seller = np.full(n_buyers, -1, dtype=int)
    streak = np.zeros(n_buyers, dtype=int)
    # Phase 7: the posted price persists across weeks - that persistence is
    # what makes pricing adaptive. Budget and inventory still reset weekly.
    posted_price = price0.copy()
    climb_direction = np.ones(n_sellers, dtype=float)
    previous_profit: np.ndarray | None = None
    profit_window: list[np.ndarray] = []
    weeks: list[RunResult] = []
    chosen_hist, attended_hist, streak_hist = [], [], []
    price_hist, profit_hist = [], []

    for _week in range(cfg.weeks):
        attends = rng.random(n_buyers) < attendance_prob
        visit_orders = np.array([rng.permutation(n_sellers) for _ in range(n_buyers)])
        purchase_draw = rng.random((n_buyers, n_sellers))
        visibility_draw = rng.random((n_buyers, n_sellers))
        promotion_roll = rng.random()
        promotion_pick = int(rng.integers(0, n_sellers))

        price = posted_price.copy()
        if cfg.forced_promotion_seller is not None:
            promoted: int | None = cfg.forced_promotion_seller
        elif promotion_roll < cfg.promotion_probability:
            promoted = promotion_pick
        else:
            promoted = None
        if promoted is not None:
            price[promoted] = cfg.discounted_price(price[promoted])

        budget = budget0.copy()
        inventory = inventory0.copy()
        buyer_n_purchases = np.zeros(n_buyers, dtype=int)
        buyer_total_spent = np.zeros(n_buyers, dtype=float)
        seller_n_sold = np.zeros(n_sellers, dtype=int)
        seller_revenue = np.zeros(n_sellers, dtype=float)
        noticed = np.zeros(n_sellers, dtype=int)
        blocked = {
            NO_PURCHASE_UTILITY: 0,
            NO_PURCHASE_BUDGET: 0,
            NO_PURCHASE_INVENTORY: 0,
            NO_PURCHASE_UNNOTICED: 0,
            NO_PURCHASE_ABSENT: 0,
        }
        blocked_pairs: dict[tuple[str, str], int] = {}
        transactions: list[Transaction] = []
        bought_this_week: list[list[int]] = [[] for _ in range(n_buyers)]

        for buyer_id in range(n_buyers):
            if not attends[buyer_id]:
                blocked[NO_PURCHASE_ABSENT] += n_sellers
                continue
            for visit_order, seller_id in enumerate(visit_orders[buyer_id]):
                seller_id = int(seller_id)
                if visibility_draw[buyer_id, seller_id] >= visibility_prob[seller_id]:
                    blocked[NO_PURCHASE_UNNOTICED] += 1
                    continue
                noticed[seller_id] += 1

                p = price[seller_id]
                bonus = 0.0
                if cfg.has_loyalty and seller_id == last_seller[buyer_id]:
                    bonus = cfg.loyalty_bonus_per_streak * min(
                        streak[buyer_id], cfg.loyalty_streak_cap
                    )
                p_purchase = purchase_probability(
                    cfg,
                    budget[buyer_id],
                    p,
                    preference[buyer_id, seller_id],
                    alpha[buyer_id],
                    price_reference,
                    loyalty_bonus=bonus,
                )
                wants = p_purchase > purchase_draw[buyer_id, seller_id]
                can_afford = p <= budget[buyer_id]
                in_stock = inventory[seller_id] > 0

                if not (wants and can_afford and in_stock):
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
                budget[buyer_id] -= p
                inventory[seller_id] -= 1
                buyer_n_purchases[buyer_id] += 1
                buyer_total_spent[buyer_id] += p
                seller_n_sold[seller_id] += 1
                seller_revenue[seller_id] += p
                bought_this_week[buyer_id].append(seller_id)
                transactions.append(
                    Transaction(
                        seed=seed,
                        buyer_id=buyer_id,
                        buyer_class=buyer_class[buyer_id],
                        seller_id=seller_id,
                        seller_class=seller_class[seller_id],
                        visit_order=visit_order,
                        price=float(p),
                        budget_before=budget_before,
                        budget_after=float(budget[buyer_id]),
                        seller_inventory_after=int(inventory[seller_id]),
                    )
                )

        chosen = np.array([_choice_of_week(b) for b in bought_this_week])
        for b in range(n_buyers):
            if chosen[b] < 0:
                continue  # bought nothing: memory and streak both carry over
            streak[b] = streak[b] + 1 if chosen[b] == last_seller[b] else 1
            last_seller[b] = chosen[b]

        weeks.append(
            RunResult(
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
                promoted_seller=promoted,
                effective_prices=price.copy(),
            )
        )
        profit = seller_revenue - unit_cost * seller_n_sold - cfg.fixed_weekly_cost
        weeks[-1].seller_profit = profit.copy()

        chosen_hist.append(chosen)
        attended_hist.append(attends.copy())
        streak_hist.append(streak.copy())
        price_hist.append(posted_price.copy())
        profit_hist.append(profit.copy())

        if cfg.price_rule == "hill_climb":
            # Keep moving the way we moved last week while profit improves;
            # reverse when it stops. No thresholds, and the floor at unit cost
            # is the one thing a purely demand-driven rule cannot supply -
            # below cost a further cut is irrational rather than merely bad.
            #
            # A seller only acts on a profit change bigger than its own recent
            # noise. Volume differs by an order of magnitude across stalls - the
            # busiest sells 27 units a week, the quietest 3 - and on the quiet
            # ones a single week's profit says nothing: its standard deviation
            # is several times its mean. Without this gate the rule random-walks
            # there and drifts a price to 3.5x its start on noise alone, which
            # reads as discovery and is not.
            profit_window.append(profit)
            if len(profit_window) > cfg.price_signal_window:
                profit_window.pop(0)
            if previous_profit is not None:
                change = profit - previous_profit
                noise = (
                    np.std(np.array(profit_window), axis=0, ddof=1)
                    if len(profit_window) > 1
                    else np.zeros(n_sellers)
                )
                informative = np.abs(change) > noise
                climb_direction = np.where(
                    informative & (change < 0), -climb_direction, climb_direction
                )
                step = np.where(informative, cfg.price_step, 0.0)
            else:
                step = np.full(n_sellers, cfg.price_step)
            previous_profit = profit
            posted_price = np.maximum(
                posted_price * (1.0 + climb_direction * step), unit_cost * 1.01
            )
        elif cfg.price_rule is not None:
            raise ValueError(f"unknown price_rule {cfg.price_rule!r}")

    return SeasonResult(
        config_name=cfg.name,
        seed=seed,
        weeks=weeks,
        chosen_seller=np.array(chosen_hist),
        attended=np.array(attended_hist),
        streaks=np.array(streak_hist),
        posted_prices=np.array(price_hist),
        profits=np.array(profit_hist) if cfg.has_costs else None,
    )


def run_season_seeds(cfg: MarketConfig) -> list[SeasonResult]:
    return [run_season(cfg, seed) for seed in cfg.seeds]
