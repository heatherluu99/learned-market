# Phase Specifications — Phase 1 through Phase 16

This document is a pre-registration-style specification: each phase's
research question, mechanism, and acceptance criteria are fixed in advance,
before implementation, to prevent post-hoc rationalization of results.

**Phases 1–8 are fully parameterized now** because they are deterministic
simulations with no external data dependency. **Phases 9–16 specify research
questions, logging schema, and decision gates**, but not fixed empirical
numbers — those depend on real Agent/human data that does not exist yet.
Treating placeholder numbers in Phases 9–16 as if they were calibrated would
violate the project's own validity-before-commercialization principle.

Only the **current phase** (see ROADMAP.md) should be implemented at any
given time. Writing this document in full now is planning, not
implementation — Claude Code should not build ahead of the phase marked
current in ROADMAP.md.

---

## Logging Schema (applies from Phase 1 onward)

Every experiment run writes a row to `experiment_log.csv` with at minimum:

```
experiment_id, git_commit, config_file, phase, seed,
n_buyers, n_sellers, model_used, decision_type,
human_benchmark_id, human_benchmark_status,
synthetic_cost_usd, synthetic_latency_seconds,
research_question, changed_mechanism,
transaction_count, participation_rate,
result_summary, decision_implication, next_experiment
```

- `model_used`: "rule_based" for Phases 1–8; actual model name from Phase 9 on.
- `decision_type`: one of {pricing, segmentation, campaign, market_entry, N/A}. Set even in Phase 1–8 as "N/A" so later filtering/joins work cleanly.
- `human_benchmark_id` / `human_benchmark_status`: "N/A" / "not_applicable" until Phase 10; from Phase 10 on, points to a row in a separate `human_benchmarks.csv`.
- `synthetic_cost_usd` / `synthetic_latency_seconds`: "N/A" for Phases 1–8 (no API calls, pure rule-based). From Phase 9 on: total API cost and wall-clock time for the run's Agent calls. These are compared against a separate `human_baseline.csv` (introduced in Phase 9, see below) to compute a cost/speed advantage ratio. This ratio is not cosmetic — Phase 15's commercial gate requires a favorable ratio before any client recommendation proceeds (see ROADMAP.md, Commercial Viability Constraint).

This schema is fixed now specifically so Phase 1–8 runs and Phase 9+ runs can be joined into one longitudinal table without migration later (see ROADMAP.md, Moat Strategy).

---

## Phase Completion Deliverable — Tracking Slide (applies from Phase 1 onward)

After a phase's acceptance criteria pass — **before** `git tag phaseN-validated` — append one slide to a single running deck, `project_tracking.pptx`. This is one continuously growing deck (one new slide per phase), not a separate file per phase, so the whole project's progression can be flipped through in one place.

**Each slide must contain, in this layout** (see `phase1_template_slide.pptx` for the visual reference — built as a design template; its numbers are placeholders, not real Phase 1 results):

- **Header:** Phase number + name, git tag, seed count, and a status badge.
- **Agents:** buyer count/classes, seller count/classes, and their key parameters.
- **Environment & Context:** which environment/context features are active this phase (or "None — static baseline").
- **Method:** the decision mechanism in one or two lines (rule-based formula / bandit variant / model name+version for Agent phases).
- **Literature Basis:** the paper(s) this phase's mechanism is grounded in (author, year, short title — see each phase's "Literature basis" line below). Where a phase has no strong direct citation (e.g., Phase 12, 15, 16), say so plainly rather than forcing one — this keeps the slide's academic grounding honest rather than decorative.
- **Key Results:** a small metric table pulled directly from that phase's `run_summary.csv`, each row showing pass/fail against the phase's documented acceptance criteria.
- **Research Question + Finding:** the phase's research question and a one-line, non-overclaiming statement of what was actually found (not a business conclusion — that language is reserved for Phase 14+ once Asset D exists).

**Implementation note:** because the rest of this project is Python, implement the generator as `tools/generate_phase_slide.py` using `python-pptx` (not the `pptxgenjs` script used to produce the visual reference above) — it should open `project_tracking.pptx` if it exists (or create it on Phase 1), call `add_slide()` with a blank layout, and draw the same sections as shapes/text boxes, reading phase config and `run_summary.csv` as input. Since each call only ever appends a new slide (never duplicates or edits an existing one), `python-pptx`'s lack of slide-duplication support is not a limiting factor here. When setting text, assign to `run.text` on a paragraph's run rather than `text_frame.text`, so formatting (bold labels, colored status text) survives.

---

## Narrative Setting

The simulation is framed as **Millbrook Market** — a fictional, composite indoor public market in a mid-size American town, open every week, year-round. It is not modeled on any single real location. This is a deliberate choice: the project's quantitative calibration source (Rhode Island DEM's public farmers-market reports) describes small/mid-size town markets, not a major-city landmark market (e.g., Pike Place, Ferry Building, Reading Terminal). Naming a specific real landmark market would invite the expectation that the simulation's numbers match that real place; a fictional composite town avoids that mismatch while keeping the same real data as the quantitative anchor.

Two concrete consequences of "indoor, year-round" (as opposed to the outdoor seasonal farmers markets RI DEM reports on):
- The market has no true off-season. The 22-week "season" used throughout this document is **not** a real calendar season anymore — see the redefinition immediately below.
- Millbrook's customers are explicitly mixed-income ("whatever kind of people are around"), not skewed toward any one tier — this motivates the three-way buyer split introduced in Phase 2 below.

## Weeks and Seasons — Design Basis (applies from Phase 6 onward)

**1 week = 1 real market day.** **1 season = 22 weeks.** The 22-week figure originally came from Rhode Island DEM's public farmers-market reports (2019–2023), which show real *outdoor, seasonal* markets running early May to mid/late October — about 22 weekly market days. Because Millbrook Market is framed as indoor and open year-round, a "season" here is **not a calendar season** — there is no winter closure to justify one. The 22-week figure is kept anyway, but its meaning changes: it is now **an internal review cycle length** (the cadence at which Phase 8's entry/exit logic reconsiders the seller mix), chosen because it's the same horizon already validated in Phase 6 for loyalty stabilization — not because Millbrook actually closes for the winter. This is a narrower, more honest justification than the original one, and is stated explicitly here so the number isn't mistaken for a recovered calendar fact about an indoor market that doesn't have an off-season.

The buyer:seller ratio's justification is unaffected by this — RI DEM's customer:vendor ratio is a property of market *scale*, not of indoor/outdoor or seasonal/year-round status, so it still applies (see the note below).

### Why Phases 1–5 have no week axis at all

Phases 1–5 don't get a row with an actual week count because they have no time axis yet — not a short one, a nonexistent one. Each of those phases is a single-session static market: one run means every buyer visits every seller once, makes a purchase decision, and the run is over. There is no "next week" inside a Phase 1–5 run for a buyer to carry memory into.

This is a direct, deliberate consequence of the project's own one-dimension-at-a-time discipline. Phases 2 through 5 are each adding exactly one new dimension to a single-period decision — heterogeneity (2), environment (3), context (4), nonlinearity (5). If a time axis were introduced alongside any of those, and a result changed, there would be no way to tell whether the new behavioral dimension or the new time dimension caused it. So "history" — the thing that actually requires weeks to exist — is deliberately withheld until every single-period building block has been validated in isolation. That's the whole reason Phase 6 is named "Repeated Interaction" and explicitly called out as the phase where "history becomes real": everything before it is, on purpose, a single freeze-frame of the market, repeated for statistics, not a movie of it.

That distinction — repeated for statistics vs. repeated as a timeline — is the key one. What varies across the multiple runs used to validate Phases 1–5 is the random **seed** (30 seeds, per each phase's Validation section), not the week. Running the same static market 30 times with 30 different seeds answers "is this result reliable, or did I get lucky with one random draw" — a statistics question, resolved by watching a running mean converge across seeds. Running a market for 30 *weeks* would instead ask "does memory change future behavior" — a mechanism question that only becomes askable once Phase 6 gives buyers something to remember week to week. Phases 1–5 are built to answer the first kind of question only; the second kind doesn't exist for them by construction.

Different phases need different numbers of seasons from Phase 6 onward, because they're testing different things. Phases 1–5 are listed in the table below too, so their absence of a week count reads as the deliberate choice explained above rather than a gap:

| Phase | Seasons | Weeks | Why |
|---|---|---|---|
| 1–5 | N/A | N/A — single-session, static market | See "Why Phases 1–5 have no week axis at all" above. |
| 6 | 1 | 22 | One real season is enough to observe within-season loyalty stabilization, and matches the horizon a single RI DEM report actually covers. |
| 7a–7d | 3 | 66 | Bandit/RL-style learning typically needs more repetitions than one season provides before 7b–7d's improvement over 7a becomes distinguishable from noise. |
| 8 | 3–5 | 66–110 | Entry/exit needs multiple season boundaries to show whether the vendor mix stabilizes or oscillates — and this is the one place real multi-year data exists to check against: RI DEM's actual vendor counts across 2019–2023 (24, 31, 25, 24, 26) are a real cross-season stability benchmark, not a fabricated one. |
| 9–14 | inherits Phase 8 | inherits Phase 8 | These phases run scenarios *within* the environment Phase 8 already established; they don't reopen the "how many weeks" question. |
| 15 | 3–5 | 66–110 | The terminal, full-scale run — see Phase 15 below. |

**Phase 1/2 population ratio (applied):** Phase 1 and Phase 2's buyer:seller counts (80:4 and 100:5, both 20:1) reflect the RI DEM-informed correction discussed earlier, replacing the original engineering-convenience placeholders (10:4, 15:5). This keeps the ratio consistent from the first phase through Phase 15's full-scale run, rather than only becoming real at the end.

---

## Price Normalization Convention (applies from Phase 1 onward)

Every phase's purchase rule divides price by a normalizer before scaling it by `price_sensitivity`:

```
utility = ... - price_sensitivity * (price / price_reference) + ...
```

**The rule: `price_reference` = the highest posted price in that phase's initial configuration.** It is one constant shared by every buyer in the phase, computed once when the phase's configuration is fixed, and never recomputed afterwards.

**Why not `budget_per_visit`.** The formula already contains a term dedicated to the budget: `0.05 * (budget_remaining - price)`. Dividing by budget as well would route affordability into utility through two channels at once — once linearly, once folded into the `price_sensitivity` scaling. That is double-counting on its own, and it gets worse from Phase 2 on, where budget is class-specific (Poor 3, Middle 5, Rich 10): a per-class denominator would silently give each class its own additional price-sensitivity scaling, tangled with the `price_sensitivity` parameter that is supposed to be the only knob controlling exactly that. Class stratification could then no longer be attributed cleanly to `price_sensitivity` rather than to the denominator — a direct violation of the project's own change-one-dimension-at-a-time discipline.

The highest posted price is a single market-wide constant that does not vary by class, so the scaling stays entirely out of the buyer-side differences and `price_sensitivity` remains the sole knob for how strongly a class reacts to price.

**Why not the price of the seller currently being evaluated.** This is the other tempting reading, and it is the worst of the three, because it does not merely distort the price term — it deletes it. If the denominator were each seller's own price, then `price / price_reference` is 1.0 for *every* seller by construction: Phase 2's Slow seller gives 2/2 = 1.0 and its Shigh seller gives 6/6 = 1.0. The whole term collapses to the constant `- price_sensitivity`, identical at every stall, and price stops entering the comparison between stalls at all. A model built to ask whether lower-budget buyers sort toward lower-priced sellers would then contain no mechanism by which price could affect that sorting.

**Why it is locked at configuration time, and not updated by dynamic pricing or by entry/exit.** From Phase 7 onward sellers adjust prices weekly, and from Phase 8 onward sellers enter and leave. The normalizer follows **neither**. If it drifted along with the prices Phase 7's algorithms are actively learning to set, the overall scale of utility would become entangled with the pricing-learning mechanism under test. The same argument applies unchanged to Phase 8: entry and exit *are* the mechanism being measured there, so the scale of utility must not move with them. Concretely — **if a Phase 8 entrant posts a higher price than every incumbent, `price_reference` does not rise to meet it.** It stays at the max computed from that phase's week-0 configuration, and the newcomer simply evaluates at a ratio above 1.0. The normalizer is pinned once and held for the whole run, including across the 66–110 weeks of Phases 7–8 and 15.

**Where it lives (architecture).** The value belongs to the market, not to any seller:

- It is a field on the market/phase configuration object — `MarketConfig.price_reference` — computed **once at initialization** as `max(s.price for s in active_sellers)` and stored, not recomputed on access.
- It must **not** be a property on the `Seller` object. A seller has no business knowing what the other stalls charge; that is not its responsibility, and putting the value there is what makes the "each seller's own price" mistake above easy to write by accident.
- The utility function takes `price_reference` as an explicit argument (or reads it once from the config). Every seller in the market is evaluated against the same value, and the value does not vary with which seller is currently being scored.

**Values per phase, as derived by this rule:**

| Phase | Posted prices in initial config | `price_reference` |
|---|---|---|
| 1 | 3 (single homogeneous seller class) | **3** |
| 2 | Slow 2, Shigh 6 | **6** |
| 3–8, 15 | inherited from the phase's own seller configuration | max of those prices, fixed at week 0 |

**Correction history:** Phase 1 originally specified `price/5`. Under this rule the correct value is 3 — the only posted price in the configuration. The original 5 coincided with `budget_per_visit`, not with any posted price, and was corrected before Phase 1's validated run. Phase 2's `price/6` was already correct (6 is the Shigh price, the highest in that configuration) but had not been justified; it is derived from the rule above, not a coincidence.

---

## Methodology Summary — Variables, Comparisons, and What Accumulates

This section exists because two different things are easy to conflate across 16 phases: the **environment** (the simulated market itself — its mechanisms, agents, and history) and the **methodology** (the statistical/experimental method used to answer that phase's specific research question). They behave differently, and neither behaves as simply as "everything from before gets carried forward."

### Environment: cumulative, but gated — not unconditional

Most of the environment does carry forward: Phase 3's environment sits on top of Phase 2's heterogeneity, Phase 6's history sits on top of Phase 5's conclusion, and Phase 15 explicitly runs "the full accumulated stack." This is deliberate — the logging schema was designed from Phase 1 onward specifically so Phase 1–8 data and Phase 9+ data merge into one longitudinal table.

Two exceptions matter:

- **Threshold-gated accumulation (Phase 5; Phase 7b–7d).** New complexity only carries forward if it changes results by more than a pre-agreed margin (5 percentage points on the tracked class-share metrics). If it doesn't clear that bar, the project explicitly **rolls back** to the simpler prior version for every subsequent phase — it does not carry forward "the simple version plus an inert extra term." If Phase 5's nonlinear threshold doesn't clear 5pp, Phase 6 onward uses Phase 4's linear model, not linear-plus-unused-nonlinearity. If none of 7b–7d clear 7a, Phase 8 onward uses 7a's plain heuristic, not a half-adopted bandit or RL layer.
- **Coexistence, not replacement (Phase 9).** Phase 9 does not upgrade the environment from rule-based to Agent-based; it adds Agents for a 30-buyer subset while the other 70 buyers stay rule-based, deliberately, so the two mechanisms run side by side as a built-in control group. From Phase 9 onward, "the environment" contains both decision mechanisms at once, not one replacing the other.

### Methodology: not cumulative — a toolbox, used selectively, with two deliberate reuses

There is no phase where all thirteen prior methodologies are simultaneously in use. Each phase reaches for whatever method actually answers its own research question, and mostly stops using it once that question is answered — Phase 12's variance decomposition and Phase 13's perturbation-sensitivity analysis, for example, don't reappear anywhere after their own phase.

Exactly two methodological patterns are deliberately **reused**, not reinvented:
1. The **two-version-comparison-with-a-percentage-point-threshold** approach invented in Phase 5 is reused verbatim at Phase 7b, 7c, and 7d.
2. The **compare-against-real-RI-DEM-data-for-plausibility** approach invented in Phase 8 is reused verbatim at Phase 15, just at real scale instead of test scale.

Everything else in the table below is used once, for the phase it's listed under.

### Full per-phase table

**Phases 1–5 — single-period market, one linear model extended one dimension at a time**

| Phase | Methodology | Independent variable(s) | Dependent variable(s) | How difference is judged |
|---|---|---|---|---|
| 1 | Rule-based engine, no comparison group — plausibility check only | None (homogeneous agents; seed is the only source of variation) | `participation_rate`, `total_revenue`, `inventory_remaining` | Running-mean convergence across 30 seeds + hard invariant checks (budget never exceeded) |
| 2 | Linear random utility model (McFadden 1974 binary-logit special case) | Buyer class (Poor/Middle/Rich, 7:2:1) | Class-to-stall share (`Poor_to_Slow_share`, etc.) | Phase 1 (homogeneous) vs. Phase 2 (heterogeneous); require `Poor_to_Slow_share` ≥ 2× `Poor_to_Shigh_share` and the symmetric check for Rich; Middle recorded as an open observation |
| 3 | Same linear model, one environment variable added | Stall position → visibility probability (Huff gravity model) | Per-stall sales volume, class shares | Near- vs. far-stall sales gap at equal price; shift in shares vs. Phase 2 baseline |
| 4 | Same linear model, one context variable added | Promotion active (0/1) × buyer class (interaction) | Promoted stall's weekly sales | Percentage-point sales difference, promotion on vs. off; split by class for the interaction |
| 5 | **Linear vs. nonlinear model comparison** | Budget-exhaustion threshold penalty (0/1) | Class shares (same as Phases 2–4) | **Percentage-point gap between linear and nonlinear versions, same seeds — this is the template threshold test reused at Phase 7b–7d** |

**Phases 6–8 — a time axis exists now; comparison shifts from two-version tests to trajectories or real-data checks**

| Phase | Methodology | Independent variable(s) | Dependent variable(s) | How difference is judged |
|---|---|---|---|---|
| 6 | Add history; linear utility plus a fixed loyalty bonus | Week number (time); last week's stall (memory state) | `buyer_seller_pair_stability` trajectory | Not a two-group comparison — a single trajectory over 22 weeks, watched for whether and when it plateaus |
| 7a | Heuristic (non-learning) seller pricing | Pricing rule (fixed vs. moving-average) | Profit, participation, class shares (3 seasons / 66 weeks) | vs. Phase 6 fixed-price baseline, same seeds |
| 7b | Multi-armed bandit (first policy-learning stage) | Pricing algorithm (7a heuristic vs. 7b bandit) | Same as 7a | Same 5pp threshold test as Phase 5; graduates to 7c only if cleared |
| 7c | Contextual bandit + representation learning | **Learned market-state embedding vs. hand-designed features** (the actual research question this phase asks) | Same as 7a | Three-way: 7b (no context) vs. 7c-learned vs. 7c-hand-designed |
| 7d | Reinforcement learning (multi-week cumulative reward) | Reward horizon (single-week vs. cumulative) | Same as 7a, plus presence/absence of a short-term-loss-for-long-term-loyalty trajectory signature | Same threshold test + qualitative check for a sacrifice-then-recover pricing pattern |
| 7e | **Mechanism-sufficiency test in a separate environment** — three existence gates run in order, each licensing one level of policy complexity | Loyalty mechanism (bounded streak counter vs. persistent price-sensitive stock), swept over `delta` x `L*` | Gate 1: bonus dispersion and post-shock persistence. Gate 2: schedule headroom over the cell's own oracle optimum. Gate 3: same as 7b-7d | Gates 1-2 against pre-registered thresholds at flat prices; gate 3 on the standard +/-5% test, on the cell with the largest gate-2 headroom - **selection on outcome, valid for existence and not for effect size** |
| 8 | Emergent-structure test; entry/exit rules contain no class information | No manipulated variable — observed natural evolution across seasons | Active-seller count per class, stratification | **Not an internal model comparison — compared against real RI DEM 2019–2023 vendor counts (24, 31, 25, 24, 26) for plausibility of volatility** |

**Phases 9–14 — comparison shifts from within-model tests to comparison against real human data, with formal statistics**

| Phase | Methodology | Independent variable(s) | Dependent variable(s) | How difference is judged |
|---|---|---|---|---|
| 9a | Learned buyer policy; behavior cloning as a pipeline check, surplus-maximizing policy as the baseline | Buyer decision mechanism (hand-written rule vs. trained policy) | Realized consumer surplus, class shares | Paired against the Phase 8 rule on identical seeds; clone arm expected **equivalent**, policy arm required to raise surplus with CI excluding zero |
| 9b | Substitution experiment; Agent decisions replace **trained-policy** decisions for a subset (within-run control group) | Decision mechanism (rule / trained policy / Agent), holding everything else fixed | Choice distribution, `synthetic_cost_usd`, latency | Agent subgroup vs. rule-based subgroup within the same run; cost/speed ratio against `human_baseline.csv` |
| 10 | Distributional comparison against real (published) human data | Data source (N=100 Agent responses vs. an existing published human benchmark) | Per-scenario choice distribution | **Jensen-Shannon divergence** + directional agreement (same top choice or not) |
| 11 | Structured bias mapping + correction-function fitting | Category × demographic × context × model (four-way grid) | Phase 10's gap metric, aggregated per cell | Fit a correction function on a training subset; check error reduction on a **held-out** subset never used to fit it |
| 12 | Variance decomposition (ANOVA-style) | Model family (GPT/Claude/etc.), seed, prompt, environment | Output distribution from repeating Phase 10 scenarios | Share of total outcome variance attributable to each factor |
| 13 | Prompt-perturbation sensitivity analysis (Sclar et al. 2024 method) | Wording/ordering variants of the same underlying scenario | Choice distribution per variant | Context Sensitivity Score (dispersion across variants) |
| 14 | Proportion estimation with a formal confidence interval | Decision type (pricing/segmentation/campaign/market-entry) × model × context | Binary: major decision error occurred or not | **P(major decision error)**, with required sample size (n≈385 for ±5pp at 95% CI) computed from the standard binomial proportion formula, not chosen by feel |

**Phases 15–16 — terminus**

| Phase | Methodology | Independent variable(s) | Dependent variable(s) | How difference is judged |
|---|---|---|---|---|
| 15 | Full-stack integration run at real scale | Population scale (small test scale vs. ~700:25 real scale) | Seller-survival trajectory, participation, stability, cost ratio | Compared against real RI DEM figures for plausibility — **explicitly a plausibility check, not a formal hypothesis test** |
| 16 | (Not executed) Recalibration loop | Calibration cycle (time) | Tightening of reliability estimates | Held-out accuracy before vs. after each recalibration cycle — documented as future work, out of this project's executed scope |

---

## Phase 1 — Transaction Mechanics

**Research question:** Do buyers purchase, do sellers sell, does price affect demand, does inventory constrain sales, and are transactions recorded correctly — with no heterogeneity, no environment, no context to confound the answer?

**Explicitly out of scope:** heterogeneity, environment variation, context, history, learning, Agents.

**Agents:**
- Buyers: 80, all identical.
- Sellers: 4, all identical.

*(Population ratio note: 80:4 = 20:1, matching the real farmers-market customer:vendor ratio found in Rhode Island DEM's public market reports (~15:1 to 30:1); see the Weeks and Seasons section above for the same data source used to set the time axis. This replaces an earlier, purely-convenience placeholder ratio.)*

**Buyer parameters (fixed, identical across all 80):**
| Parameter | Value |
|---|---|
| budget_per_visit | 5 |
| price_sensitivity (α) | 0.5 |
| preference | drawn once per buyer per seller, Uniform(0,1), fixed for the run |

**Seller parameters (fixed, identical across all 4):**
| Parameter | Value |
|---|---|
| price | 3 |
| inventory (per run) | 120 |

**Purchase decision:** each buyer visits all 4 sellers in random order, once per run.

```
utility = 1.0 + 0.05*(budget_remaining - price) - price_sensitivity*(price/3) + 1.5*preference
P(purchase) = sigmoid(utility - 2.0)
```

The denominator is `price_reference` = `max(3)` = **3** — the highest (here, only) posted price in this phase's configuration, per "Price Normalization Convention" above. It is not `budget_per_visit`, which is 5.

Purchase occurs if: `P(purchase) > random(0,1)` AND `price <= budget_remaining` AND `seller.inventory > 0`.
On purchase: `budget_remaining -= price`; `seller.inventory -= 1`; log transaction.

**Output tables:** `transactions.csv`, `buyer_summary.csv`, `seller_summary.csv`, `run_summary.csv` (columns: seed, participation_rate, avg_purchases_per_buyer, total_revenue, total_inventory_remaining).

**Validation:** run 30 seeds; plot running mean of each `run_summary.csv` column; confirm convergence (curve flattens) by roughly seed 15.

**Acceptance criteria:**
- `participation_rate` between 0.6 and 1.0 (not 0 = broken; not saturated at 1.0 with no budget/inventory binding = parameters too loose to test constraints)
- `total_inventory_remaining` > 0 for at least some sellers (confirms inventory is tracked, not ignored)
- No buyer ever spends more than `budget_per_visit` (hard invariant check, not a tunable target)

**Known limitation of the main run — the inventory constraint cannot bind.** With `budget_per_visit` = 5 and `price` = 3, a buyer who purchases once is left with 2 and can never afford a second unit. Market-wide demand is therefore capped at 80 units (one per buyer) against 4 × 120 = 480 units of stock. Three consequences, recorded here rather than discovered later:

1. The research question's "does inventory constrain sales?" clause is **not answerable** by the main run. It is not that inventory happens not to bind on these seeds — it cannot bind at these parameters.
2. The `total_inventory_remaining > 0` criterion passes regardless of whether the inventory bookkeeping works, so it is not evidence that "inventory is tracked, not ignored" as originally annotated.
3. `participation_rate` and `avg_purchases_per_buyer` are identical by construction, since no buyer can exceed one purchase.

**Inventory-pressure side experiment (addresses limitations 1 and 2).** In addition to the main run, run an otherwise identical configuration with `inventory` = 15 per seller (60 units total, below the ~69 units of expected demand), over the same 30 seeds. All random draws — preferences, visit orders, purchase draws — are made before any purchase decision, so a given seed presents both configurations with identical random inputs and the two runs form a paired comparison differing only in stock level.

This side experiment is not part of the main run's acceptance criteria and its numbers are not the phase's headline result. Its sole purpose is to supply the evidence the main run structurally cannot: that stock depletion is enforced, that sales are blocked once inventory reaches zero, and that participation falls relative to the main run on the same seeds. The main run's parameters are left exactly as specified rather than retuned, so the phase's headline numbers remain the ones this document pre-registered.

**Additional `run_summary.csv` diagnostic columns:** `n_blocked_by_utility`, `n_blocked_by_budget`, `n_blocked_by_inventory` — the count of buyer-seller evaluations that ended without a purchase, attributed to the binding constraint (hard constraints attributed first). `n_blocked_by_inventory` is what makes the inventory mechanism observable at all; without it, a market that ignored inventory and a market where inventory never ran out produce identical tables.

**Literature basis:** McFadden (1974), "Conditional Logit Analysis of Qualitative Choice Behavior" — random-utility-model basis for the utility+sigmoid purchase rule (binary logit is the special case used here). Gode & Sunder (1993), "Allocative Efficiency of Markets with Zero-Intelligence Traders" (*Journal of Political Economy*) — methodological justification for testing market mechanics with minimal agent intelligence before adding sophistication.

**Exit condition:** `git tag phase1-validated`.

---

## Population Specification — Within-Class Dispersion (applies from Phase 2 onward)

**Discovered at Phase 7 and applied retrospectively to Phases 2–7.** Every buyer parameter through Phase 6 was a class constant: all 70 Poor buyers had `budget_per_visit` of exactly 3.0 and `price_sensitivity` of exactly 0.85. The only individual-level variation anywhere in the population was `preference`, drawn `U(0,1)` per buyer per seller.

So the market contained **three distinct buyer types replicated a hundred times**, not a heterogeneous population — and a phase named "Linear Consumer Heterogeneity" was modelling class-level heterogeneity only.

### What it did to the learning landscape

An oracle price sweep at the Phase 7 configuration — fixed seller policy, no learning, 66 weeks, 24 seeds, one tier swept on a 0.10 grid with the other held fixed — makes the consequence exact:

| Slow price | 2.60 | 2.80 | **3.00** | **3.10** | 3.50 |
|---|---|---|---|---|---|
| profit/week | 80.0 | 92.5 | **104.3** | **22.4** | 30.3 |

Profit rises monotonically to a maximum at exactly 3.00 and falls **79% in a single 0.10 step**. 3.00 is Poor's budget. Because every Poor buyer's budget is *identical*, all seventy affordability constraints bind at the same price, and seventy individual walls sum into one cliff.

**This is a property of the population, not of the choice rule.** The purchase rule is already probabilistic — a random-utility logit, `P = sigmoid(utility - 2.0)` — with a hard affordability gate on top. The gate is not a behavioural assumption and is not removed: a buyer holding 3 units of money cannot pay 3.01. Holding the gate fixed and giving budgets within-class dispersion:

| within-class budget | argmax | peak profit | drop in the step after the peak |
|---|---|---|---|
| none (as originally built) | 3.00 | 104.6 | **78.8%** |
| lognormal σ = 0.10 | 2.50 | 75.1 | 1.2% |
| **lognormal σ = 0.12** | 2.60 | 74.4 | **2.5%** |
| lognormal σ = 0.15 | 2.50 | 69.3 | 1.7% |

The cliff disappears. So does about a third of the peak — 104.6 against 74.4 — because that surplus was the artefact of extracting exactly 3.00 from all seventy Poor buyers at once.

### The specification

`budget_per_visit` is drawn per buyer from a **lognormal distribution whose mean is the class value**, so 3 / 7 / 10 remain the class means and only the within-class shape is new. Real budget and income distributions are right-skewed, which is why lognormal rather than uniform; a uniform distribution would also introduce hard edges of its own, just smaller ones.

**σ = 0.12, derived rather than chosen.** The binding constraint is that the classes must remain identifiable as distinct populations, or Phase 2's between-class stratification finding dissolves into its own noise. The closest adjacent pair is Middle and Rich, `ln(10/7) = 0.357` apart in log space. Setting σ so that adjacent class means sit **three within-class standard deviations apart** gives `0.357 / 3 = 0.119`, rounded to 0.12. At that value Poor's budgets span roughly 2.44–3.63 with a mean of 3.00, and the probability that a Poor buyer can reach the Shigh price of 6 is 0.002% — under one buyer in ten thousand, so the affordability wall documented from Phase 2 onward survives.

`price_sensitivity` is left as a class constant for now. Dispersing it too would change two things at once, and the phases most sensitive to it — Phase 2's attribution diagnostic in particular — should be re-read under dispersed budgets before a second dimension is added.

### Cost, stated plainly

This re-opens Phases 2 through 7. Their published numbers were produced in a market whose population differs from this one, so all five validated tags are re-run and re-evaluated rather than left standing. That is the correct trade: the alternative is a longitudinal table in which Phases 2–7 and Phases 8+ describe different populations, which is exactly what the logging schema has been protecting against since Phase 1.

The findings this is expected to move, and which must be re-read rather than assumed to carry over: Phase 2's stratification gap and its budget-versus-α attribution, Phase 5's equivalence verdicts, Phase 7a's price trajectory, and Phase 7b's arm-ceiling result — the ceiling itself is measured against an optimum that has now moved from 3.00 to about 2.60.

---

## Phase 2 — Linear Consumer Heterogeneity

**Research question:** Does person-level heterogeneity alone (holding environment and context fixed) produce different purchasing patterns, and specifically, does it produce basic economic stratification (lower-budget buyers sorting toward lower-priced sellers)? With three buyer classes instead of two, this phase also asks a second, previously nonexistent question: **how does the middle class split its patronage between tiers**, given it is not cleanly assigned to either?

**Single changed dimension vs Phase 1:** buyer and seller classes are introduced. Everything else (single market pass, no environment, no context, no history) stays as in Phase 1.

**Agents:**
- Buyers: 100 total — **Poor 70, Middle 20, Rich 10** (a 7:2:1 ratio), fixed assignment (not randomized).
- Sellers: 5 total — 3 Low-price (Slow), 2 Premium (Shigh), fixed assignment. Sellers stay two-tier even though buyers are now three-tier — the tier count on each side of the market doesn't need to match; the interesting question is precisely how the un-matched middle class resolves that mismatch.

*(Population ratio note: 100:5 = 20:1, same RI DEM-informed ratio as Phase 1. The 7:2:1 Poor:Middle:Rich split replaces the earlier 50:50 L/H split — a 50:50 split of "low" and "high" budget never resembled a real income distribution; 7:2:1 at least has the right skewed shape, even though it is still a chosen ratio, not one fitted to a specific real income distribution.)*

**Buyer parameters:**
| Parameter | Poor | Middle | Rich |
|---|---|---|---|
| income | 25 | 55 | 100 |
| budget_per_visit | 3 | **7** | 10 |
| price_sensitivity (α) | 0.85 | 0.5 | 0.2 |
| preference | drawn once per buyer per seller, Uniform(0,1), fixed for the run |

**Why Middle's budget is 7 and not 5 (corrected at the Phase 2 design review gate).** At the originally specified 5, Middle could not afford the Shigh price of 6 *at all*, so `Middle_to_Shigh_share` was 0.000 in every run — not approximately, but by arithmetic. That made this phase's explicitly stated second research question ("how does the middle class split its patronage between tiers") unanswerable by construction: the answer was 100/0 before a single seed was drawn. At 7, Middle can afford exactly one Shigh unit (leaving 1), and the measured split becomes a real observation (~0.24 to Shigh, SD 0.09 across 30 seeds).

**Poor's exclusion from Shigh is retained, and is a hard constraint, not a behavioural result.** With budget 3 against a price of 6, `Poor_to_Shigh_share` is identically 0.000. This is kept because pricing low-income buyers out of a premium tier is a real market phenomenon worth having in the model — but it must never be reported as evidence that `price_sensitivity` produces stratification. It is an affordability wall, and it would produce the same 0.000 with α set to 0, or with Poor made the *least* price-sensitive class. Any Phase 2 output describing Poor's tier split must say which of the two mechanisms it is attributing the result to.

**Seller parameters:**
| Parameter | Slow (×3) | Shigh (×2) |
|---|---|---|
| price | 2 | 6 |
| inventory (per run) | 130 | 70 |

**Purchase decision:** identical functional form to Phase 1, applied per buyer class:

```
utility = 1.0 + 0.05*(budget_remaining - price) - price_sensitivity*(price/6) + 1.5*preference
P(purchase) = sigmoid(utility - 2.0)
```

The denominator is `price_reference` = `max(2, 6)` = **6** — computed from this phase's posted prices by the rule in "Price Normalization Convention" above, not chosen because it happens to equal the Shigh price. It is deliberately *not* each class's own `budget_per_visit` (3 / 5 / 10): a per-class denominator would add a second, class-varying price-scaling on top of `price_sensitivity`, and this phase's entire purpose is to attribute stratification to `price_sensitivity` alone. It is equally not each seller's own price, which would make both stalls evaluate at 2/2 = 6/6 = 1.0 and remove price from the comparison entirely.

Budget is shared across all 5 sellers within one run (spending at one seller reduces what's left for the next); resets each run. All three classes evaluate all 5 sellers: class affects the parameters feeding into utility, never the choice set itself.

**But the choice set and the affordable set are not the same thing.** An earlier version of this paragraph claimed "nothing restricts Poor or Rich buyers from considering the 'wrong' tier". That is true of the choice set and false of the outcome. The purchase rule requires `price <= budget_remaining`, so a Poor buyer (budget 3) evaluates the Shigh stalls and is then blocked by affordability every single time. Leaving no formal restriction in the choice set does not mean every tier is reachable by every class — and in this configuration it is not.

**Output tables:** same four as Phase 1, plus `run_summary.csv` adds: `Poor_to_Slow_share`, `Poor_to_Shigh_share`, `Middle_to_Slow_share`, `Middle_to_Shigh_share`, `Rich_to_Slow_share`, `Rich_to_Shigh_share`.

**Validation:** 30 seeds, running-mean convergence check as in Phase 1.

**Acceptance criteria:**
- `participation_rate` in 0.6–1.0
- **Stratification, graded across classes rather than within one:** the across-seed mean of `Rich_to_Shigh_share` − `Middle_to_Shigh_share` is positive, with its 95% confidence interval excluding zero (30 seeds)
- `Shigh` sellers do not fully sell out (`inventory_remaining` > 0), confirming high-price demand isn't artificially unconstrained
- **Reported without a pass/fail bar:** `Middle_to_Slow_share` vs. `Middle_to_Shigh_share` (no "correct" direction is encoded for Middle), and `Poor_to_Shigh_share` (identically 0.000 — see the affordability-wall note above, and do not grade it)

**Why the stratification criterion is cross-class (corrected at the Phase 2 design review gate).** The original bars were `Poor_to_Slow_share ≥ 2 × Poor_to_Shigh_share` and `Rich_to_Shigh_share ≥ 2 × Rich_to_Slow_share`. Both were unusable, in opposite directions:

- The Poor bar is **vacuous**. `Poor_to_Shigh_share` is 0.000 by the affordability wall, so the bar reads `1.000 ≥ 0` and passes no matter what the model does — the same defect as Phase 1's original inventory criterion.
- The Rich bar is **unreachable**. Since a class's two tier-shares sum to 1, demanding `Rich_to_Shigh ≥ 2 × Rich_to_Slow` is demanding a Shigh share ≥ 0.667. The measured value is 0.315, and no parameter choice reaches 0.667, because the utility function contains no term by which an expensive stall becomes *more* attractive: price enters only through `−α·(price/price_reference)` and through spending down `budget_remaining`, and both are negative. Rich buyers are less deterred by price (α = 0.2), never drawn to it. Requiring a class to buy predominantly from the expensive tier is also a stronger claim than stratification needs.

Stratification is a statement *between* classes: richer buyers patronize the premium tier more than poorer buyers do. The replacement criterion states exactly that. It compares Rich against Middle rather than against Poor, because the Poor contrast is the vacuous one.

**Why the bar is "CI excludes zero" and not a percentage-point threshold.** The project's standing 5-percentage-point convention (Phase 5, Phases 7b–7d) is a *materiality* bar — "did added complexity change the result enough to keep it". This criterion asks a different question, existence and direction, so it takes a different bar. It is also what the data will support and no more: at 30 seeds the mean Rich−Middle gap is 0.076 with an across-seed SD of 0.101 — larger than the mean, and negative in 5 of 30 individual seeds. The 95% CI of the mean is roughly [0.04, 0.11], which excludes zero but straddles 0.05, so a 5pp bar could not be cleanly adjudicated and must not be adopted merely because the observed 0.076 happens to clear it. The criterion is therefore graded on the across-seed mean, never per seed.

**Comparison required:** report homogeneous (Phase 1 style) vs. heterogeneous (this phase) participation and class-share metrics side by side, to isolate what heterogeneity alone contributes.

**Attribution diagnostic required (added at the design review gate).** "Person-level heterogeneity" is two things at once in this phase — heterogeneous `budget_per_visit` *and* heterogeneous `price_sensitivity` — and they do not contribute equally. Re-run the same 30 seeds with all three classes' α set to a single common value (0.5), holding budgets at 3 / 7 / 10, and report the Rich−Middle gap under both settings. Gate-stage measurement puts the gap at 0.076 with the specified α's and about 0.050 with α equalized, meaning roughly one third of the stratification comes from price sensitivity and two thirds from budget heterogeneity alone.

This is a reported diagnostic, not a pass/fail bar. It exists because "heterogeneity produces stratification" is true here while the narrower reading "price sensitivity produces stratification" is mostly not, and the phase's own research question is worded loosely enough that the result could be written up either way. Any Phase 2 finding must state which of the two it is claiming.

**Literature basis:** Same random-utility framework as Phase 1 (McFadden, 1974), extended to heterogeneous per-class parameters — a standard discrete-choice modeling practice rather than a distinct citation; see also Train, *Discrete Choice Methods with Simulation*, for heterogeneous-parameter extensions of RUM.

**Exit condition:** `git tag phase2-validated`.

---

## Phase 3 — Person + Environment

**Research question:** Does a single environmental feature (stall visibility, driven by position) materially change purchase distribution beyond what person-level heterogeneity (Phase 2) already explains?

**Single changed dimension vs Phase 2:** add one environment variable — seller position — nothing else changes.

**New parameter:** each seller gets a fixed `position_score` in [0,1] (1 = near entrance, 0.3 = far).
```
visibility_prob = 0.5 + 0.5 * position_score
```
Each buyer "notices" (can consider purchasing from) a given seller in a given run with probability `visibility_prob`, independently sampled per buyer-seller-run. If not noticed, that seller is skipped for that buyer this run — no purchase decision is evaluated.

Assign: 2 Slow sellers near entrance (position 0.9), 1 Slow seller far (position 0.3); 1 Shigh near entrance (0.8), 1 Shigh far (0.3).

**Position assignment builds in a tier-level visibility difference — note it before reading any share result.** Two of three Slow stalls are near, but only one of two Shigh stalls is, so mean visibility by tier is Slow 0.850 against Shigh 0.775. Any shift in class-to-tier shares under this phase is therefore partly an artifact of *this particular* position assignment, not a general property of "adding an environment variable". The assignment is kept as specified, but a different one would produce a different tier-level effect, and that must not be mistaken for a different finding about environments.

**Implementation requirement — draw visibility last.** The per-buyer-per-seller visibility draw must come *after* the preference, visit-order, and purchase draws in the random stream. Two things depend on it: Phase 1 and Phase 2 results stay bit-for-bit reproducible at their validated tags, and Phase 3 becomes a properly paired comparison against Phase 2 — same seeds, same preferences, same visit orders, same purchase draws, differing only in whether a stall was noticed.

**Output:** same as Phase 2, plus `run_summary.csv` adds `visibility_rate_by_seller`.

**Acceptance criteria:**
- `participation_rate` in 0.6–1.0
- **Position effect:** within each price tier, the across-seed mean of (mean `n_sold` at near stalls − `n_sold` at the far stall) is positive with its 95% CI excluding zero. This replaces the original "measurably lower", which set no bar at all; the CI form matches the one adopted for Phase 2's stratification criterion.

**Reported, not graded:**
- **Class-to-tier share shift vs. the Phase 2 baseline**, paired by seed: `Poor_to_Slow_share`, `Middle_to_Slow_share`, `Rich_to_Slow_share`, each with the 95% CI of its shift. **A shift indistinguishable from zero is an acceptable and informative outcome of this phase, pre-registered as such.** It would mean the environment redistributes sales *between sellers* without disturbing the class-to-tier sorting Phase 2 established — a real finding, not a failure, and this phase must not be re-parameterized to manufacture a shift. `Poor_to_Slow_share` in particular cannot move at all: it is pinned at 1.000 by the same affordability wall documented in Phase 2, so its shift is 0.000 by construction and is reported only for completeness.
- **Participation shift vs. the Phase 2 baseline**, paired by seed, with its 95% CI. Visibility is the only mechanism that can reduce participation here — a buyer who never notices a stall cannot buy from it — so this is the phase's most direct aggregate consequence and must be stated explicitly rather than left to pass silently inside the 0.6–1.0 band.

**Literature basis:** Huff (1963, 1964), gravity-based retail trade-area model — basis for `visibility_prob` declining with seller position, directly paralleling Huff's $P_{ij} \propto A_j^\alpha / D_{ij}^\beta$.

**Exit condition:** `git tag phase3-validated`.

---

## Phase 4 — Person + Environment + Context

**Research question:** Does a transient, situational factor (a temporary promotion) shift buyer distribution beyond Person + Environment (Phase 3), and does its effect resemble a level-shift or an interaction with buyer class?

**Single changed dimension vs Phase 3:** add one context variable — a temporary price promotion — nothing else changes.

**New mechanism:** each run, with probability 0.2, one randomly chosen seller receives a 30% temporary price discount for that run only (`price_effective = price * 0.7`). This does not persist across runs (no memory yet — that's Phase 6).

**The stochastic mechanism cannot measure its own effect — a paired diagnostic does that.** At probability 0.2 over 30 seeds only about 6 runs carry a promotion, spread across 5 sellers; a gate-stage draw produced `[4, 0, 0, 1, 1]`, leaving two sellers never promoted at all. A criterion phrased as "the promoted seller's `n_sold` vs. its own baseline" therefore rests on roughly one observation per seller, which is not a sample.

The 0.2 mechanism is kept exactly as specified, because it is the market environment Phase 5 onward inherits and because an occasional situational factor is what Belk's framework describes. Measurement is separated from it:

- **`phase4_main`** — the market as specified, promotion probability 0.2. Reported for its aggregate behaviour; not the basis of the graded criteria.
- **`phase4_no_promotion`** — probability 0, otherwise identical. The baseline arm.
- **`phase4_forced_<seller_id>`** — one run set per seller, that seller promoted in every seed, otherwise identical.

Every arm draws the promotion roll and the promotion pick in the same position in the random stream (after the visibility draw, itself after the purchase draw), so all arms share identical preferences, visit orders, purchase draws and visibility draws on a given seed. The forced arms and the no-promotion arm are therefore paired seed by seed, and the graded criteria below are evaluated on those pairs — 30 paired observations per seller instead of about one. This mirrors Phase 1's inventory-pressure side experiment: the main run stays exactly as pre-registered, and a paired variant supplies the evidence the main run structurally cannot.

**A 30% discount never opens Shigh to Poor.** 6 × 0.7 = 4.2, still above Poor's budget of 3. Poor's response to a promoted Shigh stall is therefore 0.000 by arithmetic, as in Phases 2 and 3, and must not be reported as evidence that low-budget buyers are insensitive to promotions.

**Output:** `run_summary.csv` adds `promotion_active (bool)`, `promotion_seller_id`, `promotion_discount`, and share metrics conditional on promotion status.

**Acceptance criteria** (evaluated on the paired forced-promotion arms against `phase4_no_promotion`, same seeds):
- `participation_rate` in 0.6–1.0
- **Promotion lift:** for every seller, the across-seed mean of (`n_sold` promoted − `n_sold` not promoted) is positive with its 95% CI excluding zero. This replaces "increases measurably", which set no bar; the CI form matches Phases 2 and 3.
- **Class interaction:** for each promoted tier, the *expected responder* class shows a larger lift than every other class, paired by seed, with each difference's 95% CI excluding zero.

  The expected responder is defined **from the parameters, in advance of any result**: it is the lowest-budget class that can afford the discounted price. For a promoted Slow stall (2 → 1.4) that is Poor; for a promoted Shigh stall (6 → 4.2) that is Middle, because Poor's budget of 3 cannot reach 4.2. Naming the class structurally rather than by observed outcome is what keeps this a prediction rather than a description of a result already seen.

  This was originally worded "report whether the promotion effect size differs across Poor, Middle, and Rich buyers" — a reporting line, not a bar. It is promoted to a graded criterion because it is one of the phase's two stated research questions, and because a level-shift and an interaction are exactly what this criterion distinguishes: a level shift would lift all classes alike, an interaction concentrates the lift in the class for which the discount is marginal.

**Literature basis:** Belk (1975), "Situational Variables and Consumer Behavior" (*Journal of Consumer Research*) — basis for modeling a transient promotion as a situational/context variable distinct from stable person or environment features.

**Exit condition:** `git tag phase4-validated`.

---

## Phase 5 — Nonlinear Behavioral Effects

**Research question:** Does adding one nonlinear mechanism (a budget-cliff threshold effect) materially change conclusions vs. the linear model used in Phases 2–4?

**Single changed dimension:** how remaining budget enters utility; everything else (heterogeneity, environment, context) stays as configured in Phase 4.

**New mechanism:** if `budget_remaining - price < 0.5` (i.e., the purchase would leave the buyer with almost nothing), apply a utility penalty:
```
if (budget_remaining - price) < 0.5:
    utility -= 1.0
```
This represents reluctance to spend down to near-zero, not captured by the smooth linear term.

**Both readings of "replace vs. add" are run, because this document contradicted itself.** The "Single changed dimension" line originally said *replace* the linear budget term; the mechanism paragraph calls the penalty *additional* and justifies it as capturing what "the smooth linear term" misses, which presupposes that term survives. Those are different models and, at the gate, they gave materially different answers, so neither is guessed at:

| Arm | Budget enters utility via | Note |
|---|---|---|
| `phase5_linear` | `0.05 * (budget_remaining - price)` only | Phase 4's model, the baseline |
| `phase5_additive` | linear term **and** the cliff | The mechanism paragraph's reading |
| `phase5_cliff_only` | the cliff only | The "replace" reading. By this project's own accounting it changes two things at once — it removes the sole smooth channel *and* adds a threshold — so it is reported but is not the phase's primary arm. |

All three run on identical seeds, and the cliff changes no random draws, so the arms are exactly paired.

**The cliff cannot fire on any buyer's first purchase at these parameters.** Every class clears the 0.5 gap on its first affordable stall — Poor 3−2 = 1.0, Middle 7−6 = 1.0, Rich 10−6 = 4.0 — so the penalty only reaches buyers deep in a multi-purchase sequence. Gate-stage measurement put that at 17 of 2677 purchases (0.6%). The mechanism is genuinely testable but nearly inert here, and that is the reason for the size of the result, not evidence that threshold effects are unimportant in general.

**Acceptance criteria:**
- `participation_rate` in 0.6–1.0
- **The comparison is decisive on every tracked class-share metric** — see the decision rule below. What is graded is that the test *reaches a verdict*, not which verdict it reaches: this phase exists to decide whether the nonlinearity earns its place, and an inconclusive test decides nothing.

### Decision rule: the 5-point materiality test (template, reused at Phases 7b–7d)

For each tracked class-share metric, compute the paired across-seed shift against the baseline arm and its 95% CI, in percentage points, and classify it:

| Verdict | Condition | Meaning |
|---|---|---|
| **equivalent** | the whole CI lies inside ±5 pp | A material effect is *ruled out*. The added complexity is not justified; roll back. |
| **material** | the whole CI lies beyond +5 pp or below −5 pp | The added complexity changes conclusions; keep it. |
| **inconclusive** | the CI straddles a boundary | Neither claim is available at this sample size. |

**The bar is the confidence interval, not the point estimate.** Comparing only point estimates to 5 pp cannot distinguish "no material effect" from "not enough data to tell", and it would have gone wrong here: at 30 seeds the `phase5_cliff_only` arm had a point estimate of 4.68 pp — under the bar — with a CI of [+3.00, +6.36] that straddled it. Read as a point estimate the arm would have been declared immaterial; read as an interval it was undecided, and at 1000 seeds the estimate settled at 2.73 pp [+2.50, +2.96]. The point estimate moved by nearly two points, which is exactly the error an interval-based rule prevents.

**When an arm comes out inconclusive at 30 seeds, re-run that arm and its baseline at 1000 seeds and decide on that.** The 30-seed result is still reported alongside. This is not a change to the phase's headline sample; it is what to do when the headline sample cannot answer the question the phase exists to ask.

**Literature basis:** Kahneman & Tversky (1979), "Prospect Theory: An Analysis of Decision under Risk" (*Econometrica*) — basis for the reference-point-driven utility penalty near budget exhaustion (loss aversion near a reference point, here the point of near-zero remaining budget).

**Exit condition:** `git tag phase5-validated`. If the test returns **equivalent** on every tracked share, document that finding and default back to the linear model for subsequent phases unless a specific later phase needs the nonlinearity reinstated.

**Result (recorded here because the rollback it triggers governs Phases 6–15).** Both arms came out equivalent, so the project uses the **linear model from Phase 6 onward** — not linear-plus-an-inert-threshold, per ROADMAP.md's threshold-gated accumulation rule.

| Arm | Largest class-share shift vs linear | Verdict |
|---|---|---|
| `phase5_additive` (30 seeds) | 0.172 pp, CI [−1.29, +0.94] | equivalent |
| `phase5_cliff_only` (1000 seeds, after being inconclusive at 30) | 2.734 pp, CI [+2.50, +2.96] | equivalent |

Under the additive reading, `Poor_*` and `Middle_*` shares are unchanged to the last decimal place: Poor's sequences never reach the cliff and neither do Middle's, so only Rich moves at all, and not detectably.

---

## Phase 6 — Repeated Interaction (multi-week; history becomes real here)

**Research question (strengthened at a second design review gate):** **Does persistent memory create trajectory-level behaviour that cannot be explained by static preferences alone?**

The original — "does memory produce stable buyer-seller relationships" — invites the obvious objection: a loyalty bonus was written into the utility function, and repeat purchasing went up. Demonstrating a mechanism you installed is not a finding. Three things separate a real memory test from that demonstration, and the phase is graded on all three rather than on the level of stability alone.

1. **Ablation.** Memory ON against an otherwise identical memory-OFF arm on matched seeds. *Already built and graded* — this is `phase6_no_loyalty`, and the decomposition below shows how little of the raw stability level is memory at all.
2. **Path dependence.** Whether two buyers with the same traits can end up in permanently different relationships because of early history. This is the claim that cannot be restated as "you added a bonus", because it is about the dynamics rather than the mechanism.
3. **Shock recovery** (secondary). Whether a relationship that already exists survives a temporary disruption — persistence and hysteresis rather than steady-state stability.

**Single changed dimension:** add a time axis (multiple weeks in one simulation) and a memory term; single-week mechanics inherited from Phase 5 (or Phase 4, per that phase's outcome) are otherwise unchanged.

**New mechanism:**
- Run 1 season = 22 weeks per simulation (not independent reruns — state persists across weeks within one simulation). See "Weeks and Seasons — Design Basis" above for why 22.
- Each buyer tracks `last_seller_purchased` and `loyalty_streak`, the number of consecutive shopped weeks that seller has been their choice.
- Add a loyalty bonus to utility when evaluating `last_seller_purchased`:
  ```
  utility += 0.5 * min(loyalty_streak, 3)
  ```
- Seller inventory resets at the start of each week; budget resets each week.
- Not every buyer participates every week — give each buyer a per-class participation probability (Poor 0.85, Middle 0.84, Rich 0.82) and skip the purchase decision entirely (log as "did not shop") on weeks they don't participate.

**Memory accumulates; a fixed bonus does not (corrected at the design review gate).** This originally read `+0.5` if the seller was `last_seller_purchased`, with no streak. That version cannot produce the trajectory this phase's own acceptance criterion asks for: a constant bonus on a one-week-deep memory is a Markov chain at equilibrium after a single step, so stability is the same in week 1 as in week 21. Gate-stage measurement confirmed it — 0.381 at week 1 against 0.384 at week 21, with a late-minus-early difference of −0.001, CI [−0.019, +0.017]. The streak version rises: +0.037, CI [+0.012, +0.062].

The rest of the spec had already assumed streaks existed — the Phase 6 visualization below specifies a "loyalty streak ≥ N weeks" slider and an agent panel showing "a clicked buyer's ... loyalty streak", neither of which is definable under a one-week memory. The mechanism is corrected to match, rather than the visualization being cut back to match the mechanism.

**Why the streak is capped at 3.** The cap is derived, not tuned to make the test pass. `preference_coef * preference` spans [0, 1.5], so a maximum loyalty bonus of `0.5 * 3 = 1.5` lets habit at most *match* the strongest possible taste difference and never override it — loyalty is a tie-breaker of comparable weight to taste, not a lock-in. Sensitivity at the gate: cap 2 (max +1.0) produces no detectable rise, CI [−0.001, +0.047]; cap 4 and above, and uncapped, let the bonus exceed the preference range and saturate stability near 0.51.

**`last_seller_purchased` when a buyer used several sellers in one week:** take the seller they bought the *most* units from, ties broken by first encountered. This is undefined in about 15% of buyer-weeks and the choice matters — at the gate, "most" gave week-21 stability of 0.401 against 0.360 for "most recent". "Most recent" was rejected because it depends on the buyer's random stall order that week, which injects noise into what is supposed to be a memory state.

**Output:** new table `weekly_summary.csv`: `week_number`, `attendance_rate`, `purchase_rate`, class shares, `buyer_seller_pair_stability` (fraction of buyers, among those who shopped *and bought* in both this week and the prior week, whose chosen seller matches).

**Participation is two different quantities and both are recorded.** `attendance_rate` is the share of buyers who showed up — the direct expression of the per-class participation probability, about 0.834. `purchase_rate` is the share who actually bought something, about 0.680. The Phase 1–5 acceptance band of 0.6–1.0 applies to `purchase_rate`, because that is the quantity `participation_rate` measured in those phases; keeping the names distinct is what stops the longitudinal table from silently comparing two different things.

**A no-loyalty control arm is required, because most of this metric is not memory.** Decomposition of week-21 stability at the gate:

| Source | Cumulative stability |
|---|---|
| Uniform random over 5 sellers | 0.200 |
| + unequal seller popularity (`Σpᵢ²`) | 0.283 |
| + season-long fixed preference | 0.323 |
| + loyalty bonus | 0.384 |

Loyalty contributes 0.061 of 0.384; the remaining 0.323 is popularity concentration and fixed taste, neither of which is memory. Reporting the raw level as evidence that "memory produces stable relationships" would be wrong by a factor of five. `phase6_no_loyalty` runs the identical market with the bonus disabled, paired seed by seed.

### Path dependence: pre-registered as a null

Measured at the gate with a butterfly test — one buyer is forced to skip week 0 and **every random draw is left untouched**, so under memory OFF the perturbation has nowhere to persist and later weeks must be bit-identical. Under memory ON the streak state differs, and the question is whether that difference survives.

| | weeks 1–5 differ | weeks 17–21 differ | ever diverged |
|---|---|---|---|
| memory OFF | 0.000 | 0.000 | 0% |
| memory ON | 0.018 | **0.000** | 8% |

**It does not survive.** Divergence is rare to begin with and has decayed to nothing by the end of the season. So *early history → persistent future divergence* is **false in this model**, and "same persona ≠ same trajectory" is not a claim Phase 6 can make.

**The cause is a design decision made earlier in this phase, not an accident.** `loyalty_streak_cap = 3` was derived so the maximum bonus equals `preference_coef` — habit can match the strongest taste difference and never override it. That is exactly what prevents lock-in: the bonus stops growing after three weeks and resets to zero on a single switch, making this a short-memory Markov process in which perturbations decay geometrically. **Keeping habit subordinate to taste and producing path dependence are two sides of the same choice, and this phase keeps the first.**

The cap is therefore *not* relaxed to make the effect appear — that would be changing the mechanism after seeing a null. The null is recorded as the finding: a three-week-capped memory raises steady-state persistence without producing trajectory-level path dependence. It also sets up a clean contrast for Phase 7d, which asks whether a seller's multi-week horizon can do what a buyer's bounded memory cannot.

**Note on the matched-persona variant.** Comparing buyers with near-identical preference vectors was also tried and is *not* adopted: preferences are drawn `U(0,1)` per buyer per seller, so near-identical vectors are rare — 6 usable pairs across 20 seeds, far too few to conclude anything. The butterfly test is the version with power, because it compares a buyer against a counterfactual of itself.

### Shock recovery (secondary, reported not graded)

A different question from path dependence: not whether early history shapes long-run trajectories, but whether a relationship that already exists resists an external disturbance. One seller is closed for a single week at week 12 and reopens at week 13; nothing else changes.

Three quantities, for buyers paired with that seller before the shock, memory ON against OFF:

- **return rate** — share who are back with it within the following weeks
- **recovery time** — weeks until pair stability returns to its pre-shock level
- **permanent switching rate** — share who never return

**The shock is repeated across every seller and across all seeds**, not run once on one stall: a single outage would confound the memory effect with that particular seller's popularity. It is an exogenous, one-week probe and deliberately not an endogenous entry/exit mechanism — that is Phase 8, and this must not front-run it.

Either outcome is informative. Memory-ON buyers flowing back while the OFF arm redistributes would show that memory creates relationships surviving temporary disruption. Neither arm returning would show that this memory mechanism raises steady-state stability without conferring shock resilience — a boundary worth having, and consistent with the path-dependence null above.

**Acceptance criteria:**
- `purchase_rate` in 0.6–1.0
- **Memory raises stability above the no-loyalty control:** the paired across-seed mean of (`buyer_seller_pair_stability` with loyalty − without) is positive with its 95% CI excluding zero
- **Stability rises from its starting level:** the mean of weeks 17–21 exceeds **week 1**, paired across seeds, with its 95% CI excluding zero

  **This window is a post-hoc correction, and is labelled as one rather than presented as pre-registered.** The criterion originally compared weeks 17–21 against the mean of weeks **1–5**, and that comparison failed: +0.0155, CI [−0.0042, +0.0351]. The window was then narrowed after seeing it fail, which is exactly the move this project's pre-registration discipline exists to prevent, so it is recorded here as what it is.

  The justification for the narrower window is derivable from the mechanism and *should have been derived before the run*: with the streak capped at 3, the bonus reaches its maximum after three consecutive weeks, so the mechanism saturates by roughly week 4. Averaging weeks 1–5 as "early" therefore averages over the very rise being measured. The observed trajectory confirms it — 0.386 at week 1, 0.411 by week 2, and essentially flat noise around 0.42 thereafter.

  **This criterion is weak evidence and must not be reported on its own.** It is sensitive to exactly where the early window is drawn:

  | Early window | Rise vs weeks 17–21 | 95% CI | |
  |---|---|---|---|
  | Week 1 only | +0.0372 | [+0.0083, +0.0661] | passes |
  | Weeks 1–2 | +0.0247 | [−0.0003, +0.0497] | fails |
  | Weeks 1–5 (pre-registered) | +0.0155 | [−0.0042, +0.0351] | fails |

  The phase's substantive finding is the control comparison above (+0.109, CI [+0.105, +0.112]), which is an order of magnitude better separated and does not depend on any window choice. Any write-up must lead with that and treat the within-season rise as the marginal result it is.
- Report the week at which stability plateaus, defined as the first week after which the running mean stays within 1 SEM of its final value — the same convergence band used across seeds in Phases 1–5, applied along the week axis
- **Path dependence:** the memory-ON and memory-OFF arms' late-season perturbation persistence are compared under the ±5pp equivalence test and the comparison is **decisive**. As at Phase 5, what is graded is that a verdict is reached, not which verdict — and the pre-registered expectation here is **equivalent**, i.e. no path dependence
- Shock recovery is reported, not graded

### Web Visualization (introduced here — dual-purpose: debugging tool + portfolio piece)

This is the first phase where "week" is a real mechanism, so it is the natural point to introduce the market's web visualization. Because this project also serves as a CS/generative-agent portfolio piece, this visualization is built with real presentation quality from the start rather than deferred to Phase 15 — but the scope stays tightly bounded so it doesn't become its own multi-week side project.

**Rendering approach:** the visualization consumes the *pre-computed* output of a completed 22-week (1-season) simulation run (`weekly_summary.csv` + `transactions.csv`), not a live/real-time simulation. This keeps it buildable as a single self-contained artifact.

**Design direction (supersedes the earlier pixel-sprite plan):** after prototyping, the page follows a research-tool aesthetic closer to an interactive scientific demo (in the spirit of tools like Distill.pub explainers or agent-based-model dashboards) rather than a game-style pixel market. A working reference prototype exists (`from_choice_to_behavior.html`, which superseded an earlier two-class version, `market_bonds_prototype.html`) and should be used as the template rather than re-derived from scratch:
- **Header:** title, population/season badges, live readouts (participation rate, active stall count, avg. buyers per active stall, pair stability).
- **Filters, above the graph, not overlaid on it:** show/hide by buyer class (now three: Poor, Middle, Rich) and by stall class; a "loyalty streak ≥ N weeks" slider that dims buyers below the threshold. Any legend or "how to use" text must live outside the graph canvas (in a strip above or a caption below) — never as a floating overlay on top of the graph itself, since fixed-width overlays break on narrow viewports and visually collide with the dots underneath them.
- **Graph:** buyers as small circles (three distinct colors, one per class — do not reuse a stall-tier color for a buyer class, to keep the two class systems visually unambiguous), stalls as squares (color by class, distinguishing shape as well as color). No connecting lines between buyers and stalls — clustering position alone conveys "who's shopping where." Buyers continuously roam the whole canvas via an animation loop independent of the week slider: periodically (every few seconds) each buyer picks a new destination — mostly its real current-week assigned stall, sometimes another stall (for Poor/Rich, another stall of the same class, i.e. "browsing"; for Middle, any active stall, since Middle isn't restricted to one tier), occasionally open space — and glides there smoothly. This roaming is a visual/atmosphere layer only; it never feeds back into the logged metrics, which are always computed from the discrete weekly assignment data. Buyers who did not participate that week fade out entirely and fade back in when they resume shopping — a direct visualization of `participation_rate`, not decoration. Stalls fade/scale in and out on their real entry/exit weeks (Phase 8 onward).
- **Right panel:** a metrics-over-time chart (pair stability, active stall count, avg. load per stall — all computed from the same weekly data driving the graph, not a separate fabricated series) with a clickable legend to toggle series; the phase's research question as a highlighted callout; and a short numbered "how the simulation works" explanation. **Agent detail is a pointer-following tooltip, not a side panel** (changed during Phase 6 implementation): at this dot size the reader's eye is already on the buyer, and sending the reading position to the far edge of the page breaks that. Hovering a buyer or stall shows its class, current stall, loyalty streak and class parameters at the cursor; clicking pins it so it survives the pointer leaving, and clicking again releases it. Being transient and pointer-anchored, it does not fall under the no-overlay rule above, which exists to stop *fixed-width* furniture from colliding with the dots and breaking on narrow viewports;
- **Footer:** play/pause and a week scrubber.

**Framing note for the portfolio angle:** because this same page is extended incrementally in Phase 8 (entry/exit panels) and Phase 9 (Agent Inspector) rather than rebuilt from scratch, the finished demo tells a coherent story on its own — "watch the simulation grow from simple rules to an Agent-driven system" — which is a more distinctive portfolio narrative than a single flashy end-state demo with no visible reasoning behind it.

**Literature basis:** Massy, Montgomery & Morrison (1970), *Stochastic Models of Buying Behavior* (MIT Press) — classic framework for loyalty/switching dynamics in repeated purchasing; basis for the buyer-seller pair-stability metric.

**Exit condition:** `git tag phase6-validated`.

---

## Phase 7 — Seller Learning

**Research question (replaced at the Phase 7 design review gate):** **Does stateful policy learning produce market structures that cannot emerge from myopic bandit optimization?**

The original question — "does adaptive pricing change profit, participation and class-segregation relative to fixed pricing" — is answerable but weak: it compares performance, and the answer was never in doubt. The replacement asks about *structure*, which is what this project's Phase 8 is about anyway, and it is decidable in either direction.

**Where the profit optimum actually is — measured, not inferred.** An oracle sweep at the real Phase 7 configuration (fixed seller policy, no learning, 66 weeks, 40 seeds, one tier swept on a 0.05 grid with the other held fixed):

| Slow price | 2.40 | 2.60 | **2.65** | 2.70 | 3.00 | 3.50 |
|---|---|---|---|---|---|---|
| profit/week | 66.6 | 72.2 | **72.4** | 71.3 | 60.1 | 34.5 |

A smooth unimodal curve with an interior maximum at **2.65 ± 0.6**, arising from the ordinary trade-off between margin and volume.

**This is not where it was.** Before within-class budget dispersion the same sweep put the maximum at exactly 3.00 — Poor's budget — with a 79% collapse in the following 0.05 step. That optimum was an artefact: every Poor buyer held an identical budget, so seventy affordability constraints bound at one price and summed into a cliff. See "Population Specification — Within-Class Dispersion" above. The optimum is now an economic quantity rather than a boundary written into the environment, and this section previously argued from the artefact.

### Profit, defined (needed here and by Phase 8's exit rule)

```
profit = revenue - unit_cost * units_sold - fixed_weekly_cost
unit_cost        = 0.5 * the seller's initial posted price   (Slow 1.0, Shigh 3.0)
fixed_weekly_cost = 10.0 for every seller
```

Phases 1–6 have no cost model at all, so "profit" in the original text was undefined and Phase 8's "exit if profit < a fixed cost threshold" was unimplementable. One margin parameter is used rather than two independent costs so the cost is derived from the price rather than picked separately, and the unit cost gives price-cutting a real floor: below cost a further cut is irrational, which no purely demand-driven rule provides. These figures are set here and **must be revisited at Phase 8's gate**, which is where they actually bite.

This phase is split into four sub-stages, run in order. **Each sub-stage requires a graduation gate before moving to the next** — added complexity must materially change the outcome metrics (profit, participation, class shares) by more than a pre-agreed threshold (e.g., >5 percentage points), or the project stops at the simpler sub-stage and documents that finding. This directly applies the project's own "does complexity earn its place" principle to the learning-sophistication dimension, not just the behavioral-modeling dimension.

**Price normalizer stays frozen through every sub-stage.** This is the first phase where posted prices move week to week, so it is the first phase where the utility formula's `price_reference` could drift. It must not: it is pinned to the highest posted price in the phase's week-0 configuration and held there for all 66 weeks, regardless of how far the learned prices travel from it. A normalizer that tracked the prices being learned would put the scale of utility itself under the control of the mechanism this phase is trying to measure. See "Price Normalization Convention" above.

### Phase 7a — Moving-Average Heuristic (baseline)

**Single changed dimension:** sellers adjust price weekly based on a moving-average heuristic; buyer-side mechanics unchanged from Phase 6.

**Mechanism — profit hill-climbing (replaced at the gate; the original rule is recorded below because its failure is instructive):**
```
each week: price *= (1 + direction * 0.05)
           if profit(this week) < profit(last week): direction = -direction
           price is floored at unit_cost (below cost a further cut is irrational)
```
The seller keeps moving its price the way it moved last week for as long as that keeps helping, and reverses when it stops. It needs **no hand-picked thresholds at all** — it reads only the profit defined above — and it has a natural equilibrium, oscillating around a local optimum instead of running away.

**Why the originally specified rule was rejected.** It read "raise 5% if inventory ran out, cut 5% if more than half the stock is left". Measured over 66 weeks:

| branch | condition | fired |
|---|---|---|
| raise ×1.05 | inventory == 0 | **0 of 330 seller-weeks** |
| cut ×0.95 | inventory > 50% of start | **309 of 330** |

Stock never runs out — a Slow stall sells about 30 of 130 — so the raise branch is dead code and the cut branch fires almost every week. The rule is a one-way ratchet with no restoring force, and prices collapse geometrically: 0.95⁶⁶ = 0.034, taking Slow from 2.00 to **0.071** and Shigh to 0.60.

Two consequences made this unusable rather than merely uninteresting:

1. **It fabricates a finding.** At week 14 the collapsing Shigh price falls below Poor's budget of 3, and Poor makes **1,987 purchases at the premium tier** over the run. The affordability wall documented from Phase 2 through Phase 4 appears to break, and this phase's own criterion asks precisely whether adaptive pricing moves `Poor_to_Shigh_share`. It would have reported a large increase caused entirely by runaway deflation.
2. **7a is the baseline all three later sub-stages are graded against**, so a degenerate 7a poisons the 7b, 7c and 7d graduation gates simultaneously, and every one of them would inherit the fabricated premium-tier access as "baseline behaviour".

A sell-through dead band was tried first and rejected too: centred on the observed baseline sell-through it is a no-op, moving prices by under 1% across 66 weeks, and its thresholds could only be set by eye after seeing the data.

**Correction made during implementation: the seller only acts on a change bigger than its own noise.** The rule as written above reverses whenever last week's profit was worse than the week before. That works where volume is thick and random-walks where it is thin, and this market is both at once:

| stall | units/week | weekly profit | sd / mean | final price ÷ initial |
|---|---|---|---|---|
| Slow #0 | 27.0 | 29.8 | 0.39 | 1.45 max |
| Slow #2 | 16.5 | 12.1 | 0.64 | 1.45 max |
| Shigh #3 | 5.1 | 5.1 | 1.41 | 1.18 max |
| **Shigh #4** | **3.0** | **−0.89** | **6.53** | **3.56 max (price 21.36)** |

At three units a week a single week's profit has a standard deviation six times its mean, so the far premium stall cannot tell an improvement from a coin flip. It drifted to three and a half times its starting price on noise alone — which reads as the heuristic discovering something, and is not.

The fix restores what this sub-stage was called in the first place. A *moving-average* heuristic compares against a smoothed signal, and dropping the moving average was an error in the replacement rule, not a deliberate simplification. Concretely: the seller keeps the last 8 weeks of its own profit, and acts only when `|profit − last week's profit|` exceeds the standard deviation of that window. Below it, nothing was learned, so the price holds. The window enters as one parameter and the bar it sets is the seller's own measured noise, not a number chosen by hand.

This is deliberately not a fix that lets the quiet stall price "correctly": at three units a week there is no window short enough to track change and long enough to see through the noise. The honest behaviour is for it to stand still, and it does. That it is also structurally unprofitable — three units a week at a margin of 3 against a fixed cost of 10 — is a Phase 8 matter, where a seller in that position exits.

**Measured behaviour of the replacement**, 30 seeds, 66 weeks, against the fixed-price baseline: final posted prices span roughly 0.75× to 1.51× their initial value, the lowest premium price stays above Poor's mean budget, and `Poor_to_Shigh_share` is 0.0002 — a far-tail effect of dispersed budgets, not a deflationary wall-break. Without the noise gate the profit gain reads +25.1 rather than +14.8; the difference is noise-driven overpricing on the thin stalls, not learning, which is why the gated figure is the one reported. That the heuristic stops short of the optimum is deliberate headroom: it leaves something for 7b–7d to win.

**Acceptance criteria:**
- Compare profit, participation rate, and class shares over 3 seasons (66 weeks) against the Phase 6 fixed-price baseline, same seeds
- Report whether adaptive pricing increases or decreases `Poor_to_Shigh_share` and `Rich_to_Slow_share` (does learning pull the middle class toward one tier or the other?)

**Literature basis:** den Boer (2015), "Dynamic Pricing and Learning: Historical Origins, Current Research, and New Directions" — survey grounding for heuristic (non-optimizing) adaptive pricing as the baseline stage before formal learning algorithms.

**Exit condition:** `git tag phase7a-validated`.

### Phase 7b — Multi-Armed Bandit (policy learning, no context)

**Research question:** Does treating price choice as a bandit problem (exploring a small set of price points, exploiting the best-performing one) outperform the fixed heuristic in 7a, without yet using any market context?

**Mechanism:** each seller picks a weekly price from the fixed set {price × 0.8, 0.9, 1.0, 1.1, 1.2} on weekly profit as reward. No buyer-class or environment information is used — deliberately context-blind, to isolate what pure trial-and-error contributes before context is added.

**Both algorithms are run, and the thing that actually moves the verdict is neither of them.** The original text offered "e.g., epsilon-greedy or UCB" as though interchangeable, and a first measurement appeared to show that the choice flipped the graduation decision. It does not. Isolating it against 7a's 64.3 profit per week:

| initialization | ε-greedy (ε = 0.1) | UCB1 |
|---|---|---|
| no initial sweep | 55.4 (**−8.9** vs 7a) | 69.7 (+5.4) |
| each arm pulled once first | 68.2 (**+3.9** vs 7a) | 69.7 (+5.4) |

**The sensitivity is to initialization, not to the algorithm.** UCB1 is identical in both rows because pulling every untried arm once is part of its definition; ε-greedy swings by 12.8 profit per week on that one choice alone, because without a sweep it commits early to whichever arm its first pull happened to favour and thereafter only revisits others 10% of the time. Once both are initialized the same way they agree, and neither flips the decision.

The original spec named the algorithm as a free choice and did not mention initialization at all — so the parameter it left open was harmless and the one that mattered was invisible. Both algorithms are run and graded anyway, with an initial sweep in each, and their agreement is reported: two learning rules reaching the same verdict is stronger evidence than one.

**The arm set is deliberately *not* widened in the graded run, and a separate ladder measures what that costs.** Widening the arms because the optimum is known to lie outside them would encode the answer into the hypothesis space. Instead the ceiling is varied as its own experiment, with seeds, environment, initialization, reward, horizon and algorithm all held fixed:

| arm ceiling | UCB1 | ε-greedy | price UCB1 settles on |
|---|---|---|---|
| 1.2× = 2.40 (specified) | 66.0 | 64.7 | 2.35 |
| 1.3× = 2.60 | 73.0 | 70.8 | 2.53 |
| **1.4× = 2.80** | **74.0** | 72.1 | 2.58 |
| 1.5× = 3.00 | 73.4 | 72.1 | 2.60 |
| 1.6× = 3.20 | 73.0 | 71.0 | 2.60 |
| 1.8× = 3.60 | 71.9 | 70.1 | 2.62 |

Profit rises with the ceiling until the action set contains the oracle optimum of 2.65, then **stops rising and slowly declines** — additional arms past the optimum buy nothing and cost exploration. Both algorithms trace the same shape.

Two things follow. **Performance improvement comes primarily from expanding the feasible action space until it contains the economic optimum, not from the learning rule** — the specified 2.40 ceiling costs about 8% of achievable profit, and no choice between ε-greedy and UCB1 recovers it. And once the optimum *is* reachable, the bandit finds it: UCB1 settles at 2.58–2.62 against an oracle optimum of 2.65.

This is why a contextual bandit is not the next step. Context conditions the *estimate* of reward, `E[R | X, A]`; it cannot enlarge `A`. Running 7c against a misspecified action space would confound whatever context contributes with the ceiling it still could not cross.

### Graduation threshold, stated in the right units

The original text asked for changes "by more than a pre-agreed threshold (e.g., >5 percentage points)" across "profit, participation, class shares". Profit is not measured in percentage points, so the Phase 5 materiality test does not apply to it unchanged. Both forms are the same three-verdict equivalence test (**equivalent** / **material** / **inconclusive**), graded on the confidence interval and never on the point estimate:

| quantity | margin |
|---|---|
| class shares, participation | ±5 percentage points, as at Phase 5 |
| profit | ±5% of the comparison arm's own mean |

Graduation to 7c requires a **material** verdict on at least one quantity. An **equivalent** verdict on all of them stops the ladder at 7a and records that finding, exactly as Phase 5's rollback did.

**Acceptance criteria:** the comparison against 7a is decisive — no quantity returns **inconclusive** — over the same 3 seasons and seeds. As at Phase 5, what is graded is that the test reaches a verdict, not which verdict it reaches.

**Literature basis:** Robbins (1952), "Some Aspects of the Sequential Design of Experiments" (*Bulletin of the AMS*) — origin of the multi-armed bandit problem.

**Exit condition:** `git tag phase7b-validated`.

### Phase 7c — Contextual Bandit with a Learned Representation (SKIPPED)

**Status: skipped, on pre-registered evidence rather than after a failed run.** Both halves of this sub-stage — learned representation against hand-designed features, and either against context-blind 7b — presuppose that market state predicts *which action is best*. This market turns out to predict only *how much that action earns*, and a contextual bandit can exploit only the former: it conditions `E[R | X, A]`, and if the ranking over `A` does not move with `X` there is no decision for it to change.

Two diagnostics, both reproducible from `experiments/phase7/run_phase7c_diagnostic.py` and the oracle sweep above.

**Regime level.** The profit-maximizing Slow price under large changes in market state:

| condition | baseline | competitor at 4.20 | competitor at 8.40 | no promotions | frequent promotions | fewer Middle+Rich | fewer Poor |
|---|---|---|---|---|---|---|---|
| argmax | 2.65 | 2.65 | 2.65 | 2.60 | 2.65 | 2.55 | 2.65 |
| peak profit | 72.2 | 68.5 | 80.5 | 73.5 | 69.1 | 56.0 | 47.7 |

Doubling the competitor's price moves the optimum by nothing at all. Peak profit ranges over 47.7 to 80.5 — a 70% spread — while the argmax moves at most 0.10, which is **less than one arm's spacing** (0.20 at the specified arm set). A contextual bandit could not express a different decision even given perfect context.

**Weekly level.** Counterfactual evaluation of five arms bracketing the optimum, 1,584 seller-weeks, with weekly context draws identical across arms:

| condition | n | 2.20 | 2.40 | **2.60** | 2.80 | 3.00 | best |
|---|---|---|---|---|---|---|---|
| all weeks | 1584 | 22.9 | 26.8 | **28.7** | 27.6 | 24.1 | 2.60 |
| a promotion elsewhere | 249 | 23.8 | 27.7 | **29.5** | 28.5 | 24.7 | 2.60 |
| no promotion elsewhere | 1335 | 22.8 | 26.7 | **28.5** | 27.4 | 24.0 | 2.60 |
| attendance above median | 651 | 24.6 | 28.7 | **30.6** | 29.5 | 25.7 | 2.60 |
| attendance at or below median | 933 | 21.8 | 25.6 | **27.3** | 26.3 | 22.9 | 2.60 |

The same arm wins under every split, and the curve shifts in level without changing shape. The per-week *realized* argmax does vary — 2.40 in 15% of weeks, 2.60 in 47%, 2.80 in 28% — but it tracks no observable state. That is noise, and a contextual bandit cannot exploit variation that context does not predict.

**Why this is a skip and not an untested assumption.** The arms in the weekly test bracket the optimum on both sides deliberately: a set pinned at its ceiling could not reveal context-dependence even if it existed, so it would not falsify anything. And this is the ladder's own design working as intended — the graduation gates exist so a rung that cannot earn its place is not built, exactly as Phase 5's rollback was a result rather than a failure.

**What would reopen it.** A market where the demand curve's *shape*, not just its height, varies with observable state — heterogeneous price sensitivity within a class, or seller-specific buyer segments — would restore the premise. The population respecification above disperses budgets but leaves `price_sensitivity` a class constant, and that is the most likely place for such variation to enter.

**Original research question, retained for the record:** Does giving the bandit a *learned* compressed representation of market state (rather than hand-designed features) improve pricing decisions further — and is representation learning actually necessary here, or would hand-designed context features do just as well?

**Mechanism:**
- Define a "market state" each week: recent buyer arrival mix, recent visibility/promotion status, recent inventory trajectory.
- **Representation learning step:** rather than hand-picking which of these features matter, learn a low-dimensional embedding of the market-state history (e.g., a simple autoencoder or PCA over the accumulated weekly state vectors) and feed that embedding to the bandit as context, instead of raw hand-engineered features.
- The bandit becomes a contextual bandit (e.g., LinUCB) conditioned on this learned embedding.

**Required comparison (this is the actual research deliverable, not just "does it run"):** run the same contextual bandit with (i) the learned embedding vs (ii) a hand-designed feature vector of the same dimensionality. If the learned representation does not outperform the hand-designed one, that is a valid and useful finding — document it rather than assuming representation learning must help.

**Acceptance criteria:** report profit/participation/class-share deltas for both context variants against the 7b baseline.

**Literature basis:** Li, Chu, Langford & Schapire (2010), "A Contextual-Bandit Approach to Personalized News Article Recommendation" (LinUCB, *WWW*) — contextual bandit algorithm. Bengio, Courville & Vincent (2013), "Representation Learning: A Review and New Perspectives" (*IEEE TPAMI*) — basis for learning a compressed market-state embedding rather than relying on hand-designed features.

**Exit condition:** `git tag phase7c-skipped`. No implementation is built.

### Phase 7d — Reinforcement Learning (multi-week credit assignment)

**Research question:** Does optimizing for cumulative multi-week reward (rather than 7a–7c's single-week-ahead reward) change pricing behavior or outcomes — e.g., does an RL seller learn to sacrifice short-term profit for longer-term buyer loyalty?

**Mechanism:** a Q-network over the same arm set 7b uses, trained on a discounted multi-week return rather than the current week's profit. PyTorch, a small MLP, with training and evaluation seeds disjoint.

**The comparison is against 7b, not 7c, which is skipped.** The state cannot be "the Phase 7c representation" for the same reason: 7c established there is no external market state worth representing, since the profit-maximizing arm is identical under every observable condition tested. What is left is the seller's *own accumulated position* — how many buyers currently hold a loyalty streak with it, its own last price, and how far into the season it is. If a multi-week horizon is worth anything here, that is where it has to come from.

**Pre-registered expectation: a null, and the reason traces to a Phase 6 decision.** Hand-designed invest-then-harvest schedules measured at the gate against flat pricing at the myopic optimum of 2.60, 30 seeds, 66 weeks:

| plan | total profit | vs flat | loyal buyers @wk8 | @wk20 |
|---|---|---|---|---|
| flat at 2.60 | 1998.7 | — | 18.9 | 19.8 |
| discount 8wk to 2.20, then 2.60 | 1951.7 | **−47.0** | 20.9 | **19.8** |
| discount 8wk to 2.20, then harvest at 3.00 | 1694.5 | −304.2 | 18.6 | 13.7 |
| discount 16wk to 2.20, then 2.60 | 1903.7 | −94.9 | 21.7 | 20.0 |
| discount 8wk to 1.80, then harvest at 3.00 | 1618.4 | −380.3 | 20.0 | 13.8 |

Every investment loses, and the loyalty column shows why: eight weeks of discounting does build a larger loyal base — 20.9 buyers against 18.9 at week 8 — and by week 20 it has decayed to 19.8, exactly the flat-pricing level. The discount is never recovered.

**The cause is `loyalty_streak_cap = 3`.** Loyalty is not a stock that can be accumulated: the bonus tops out after three consecutive weeks and resets to zero on a single switch, so a buyer acquired expensively is worth no more than one acquired at the steady-state price, and a defection wipes the investment. There is nothing to invest *in*.

That is Phase 6's path-dependence null seen from the seller's side, and it makes a cross-phase trade-off explicit: **the cap keeps habit from overriding taste, which is why it was chosen, and it simultaneously removes every mechanism that would make sophisticated seller learning pay** — laterally at 7c and intertemporally here.

**7d is run rather than skipped like 7c.** The diagnostic above tests only the schedules that were thought of, and a search might find one that was not; and unlike 7c, this sub-stage carries Phase 7's own headline question, which would be weaker answered by diagnostic than by measurement.

**Acceptance criteria:**
- The profit comparison against 7b is **decisive** under the ±5% relative margin, evaluated on **seeds never used for training**. As at Phase 5, what is graded is that a verdict is reached, not which verdict it is.
- **Qualitative signature, reported not graded:** does the learned policy price below the myopic optimum early and above it later? Operationalized as the correlation between week index and chosen price, and the mean price in the first against the last third of the season. Absence is the expected outcome and is a result; presence *without* a profit gain would be more interesting still.

  **The signature as specified does not distinguish intertemporal strategy from ordinary convergence, and the measured run shows why.** Any learner that starts uninformed and climbs toward a better arm produces a rising price path and therefore a positive week-price correlation. In the run, the *myopic* bandit scored **higher** on it than the RL agent — 0.420 against 0.304 — with both first thirds at ~2.25. A criterion that a per-week optimizer passes more strongly than a multi-week one is measuring the learning curve, not the horizon. It is kept because it was pre-registered and because reporting it alongside its own defect is more useful than silently replacing it; anything drawn from it must be read against a same-arms myopic baseline rather than against zero.

**Training and evaluation seeds are disjoint.** A policy scored on the seeds it was fitted to measures memorization rather than learning. Seeds 0–29 stay the evaluation set every other phase uses; training draws from a separate block.

**Literature basis:** den Boer & Zwart (2015), "Dynamic Pricing and Learning with Finite Inventories" (*Operations Research*) — directly addresses learning-to-price under a finite-inventory constraint, matching this project's seller setup.

**Result.** Trained on seeds 1000–1119, evaluated on 0–29: **65.2 profit per week against the bandit's 66.0, −1.3% with a 95% CI of [−2.8%, +0.1%] — equivalent, and decisive.** Optimizing a ten-week discounted return finds nothing that per-week optimization does not, and the sacrifice-then-recover trajectory is absent. This is the pre-registered outcome, now measured rather than inferred, and it closes Phase 7's headline question for the base environment: in a market whose loyalty is a bounded three-week counter, stateful optimization produces no value a myopic learner cannot reach.

**Exit condition:** `git tag phase7d-validated`. If none of 7b–7d clear their graduation threshold over 7a, the project should explicitly adopt 7a as the standing baseline for Phase 8 onward and record that as a finding, not treat it as a failure.

---

## Phase 7e — Mechanism Sufficiency (a second, mechanism-enabled environment)

**Research question:** As a market acquires state-dependent and intertemporal
mechanisms, at what point does each level of policy complexity become
*necessary*?

Phase 7 answered its headline question in the negative twice, and both nulls
trace to a single line of configuration. `loyalty_streak_cap = 3` makes
loyalty a bounded counter: it tops out after three consecutive weeks, resets
to 1 on one switch, and is worth the same whatever price was paid to acquire
it. A counter like that leaves no cross-section worth conditioning on (7c) and
no stock worth investing in (7d). Phase 7 therefore measured something
narrower than it set out to measure — not "does stateful learning pay?" but
"does stateful learning pay in a market that has no state?"

7e makes the obstacle the question. It builds a **separate** environment in
which loyalty is a stock rather than a counter, and puts the same learners to
the same test.

**This is not a correction to Phase 7.** Nothing in 7a–7d is revised,
retracted, or re-run, and the base environment stays the default everywhere
else in the project. Phase 6 chose the cap deliberately — habit must not
override taste — and that choice was right for what Phase 6 was testing. The
value of 7e is the *pair*: complexity pays here and not there, with the
difference stated as a structural commitment rather than as a parameter that
was nudged until the result improved.

### The mechanism: persistent, price-sensitive, bounded loyalty

One stock per buyer–seller pair, updated once a week for every pair, before
the next week begins:

```
purchased:      L[b,s] <- rho*L[b,s] + beta * max(0, 1 + delta*(1 - p_paid/p_list[s]) / A)
not purchased:  L[b,s] <- rho*L[b,s]
utility bonus:  bonus[b,s] = L_max * tanh(L[b,s] / L_star)
```

`A = max |arm - 1|` is the arm half-range (0.2 for the standard arm set), so
`delta` is denominated in "one full price move" and means the same thing if
the arm set ever changes. The accrual multiplier is clamped at zero: a premium
price can slow accumulation to a stop but never subtract stock directly —
erosion is `rho`'s job, and letting both channels drain it at once would make
the harvest side of any schedule punitively expensive for reasons the
mechanism does not actually claim.

Four departures from the counter, three structural and one that is the whole
point:

| | streak counter (Phases 6–7d) | loyalty stock (7e) |
|---|---|---|
| accumulation | integer, +1 per consecutive week | continuous, geometric toward `q*beta/(1-rho)` |
| defection | resets to 1 — the entire investment | −20% for one week; the rest survives |
| saturation | hard cap at 3 | smooth `tanh` knee at `L*` |
| **price paid** | **irrelevant** | **`delta` makes a cheap purchase build more stock** |

The fourth row is what creates an intertemporal trade-off at all. With
`delta = 0` a purchase is a purchase, and the only reason to cut price is this
week's demand — precisely the myopic problem 7b already solves. `delta` is the
investment channel: it is what a discount *buys* that outlives the week.

**Parameters, and where each came from.** `rho = 0.80` and `beta = 0.25` are
the values chosen at the design gate. `L_max = 1.5` is not free: it is exactly
Phase 6's maximum bonus (`0.5 * 3`), so the ceiling on habit is unchanged and
only the path to it differs. That is deliberate and load-bearing — if 7e's
learners do better, it cannot be because habit was simply made stronger.
`delta` and `L*` are what 7e-1 calibrates.

Implied dynamics at `rho = 0.80`, `beta = 0.25`: a stock half-life of
**3.1 weeks**, and a buyer who buys from the same stall a fraction `q` of
weeks converges to `L = 1.25q`.

| | `L* = 1.00` | `L* = 1.25` |
|---|---|---|
| bonus at `q = 1.0` (every week) | 1.27 | 1.14 |
| bonus at `q = 0.6` | 0.96 | 0.81 |
| marginal bonus per unit stock at `q = 0.6` | 0.86 | 1.03 |

The two `L*` points are not a fine grid around a guess; they place the typical
loyal buyer on opposite sides of the `tanh` knee. At `L* = 1.00` the operating
point is past the knee, where further investment returns little and the
mechanism behaves *like* the old cap. At `L* = 1.25` it sits at the knee,
where marginal investment still pays. If loyalty investment is going to matter
anywhere in this family, it matters at the second point — and if it does not
matter even there, that is a much stronger statement than one point failing.

**No new random draws.** The stock update is deterministic given the week's
purchases. Phases 1–7d stay bit-identical, and the stock model is off by
default (`loyalty_model = "streak"`), so no existing config changes.

### Three gates, and what each one licenses

Each gate is the *existence condition* for a specific kind of policy. This is
the structure Phase 7 lacked: 7c and 7d were run against mechanisms that could
not have rewarded them, and only the results said so.

| Gate | Question | Licenses | Sub-stage |
|---|---|---|---|
| 1 | Is there a persistent, dispersed state? | **context** — a contextual policy (7c's revival) | 7e-1 |
| 2 | Is there an intertemporal trade-off? | **horizon** — a multi-week policy (7d's revival) | 7e-2 |
| 3 | Does the extra complexity measurably pay? | the answer itself | 7e-3 |

**Gate 1 — a state exists.** Graded on flat pricing, 30 seeds, 66 weeks, so it
measures the mechanism and not a learner. Two pre-registered checks:

- **Dispersion — is the state at its ceiling for most of the population?**
  Share of *attached* buyers (those who bought from their modal seller in the
  final week) whose loyalty bonus sits within 5% of `L_max`. Threshold:
  **≤ 0.50**. A state variable that is maxed out for most of the people it
  describes carries no information, whoever reads it — that is exactly the
  condition that killed 7c, and under the counter it is the normal state of
  affairs, since three consecutive weeks reach the cap and nothing above it
  exists. The interquartile range is reported alongside as a descriptive.
- **Persistence — what does one interruption actually cost?** Phase 6's
  one-week closure probe, scored on the metric Phase 6 already publishes:
  **permanent switching rate** among the cohort attached to the closed seller.
  Threshold: **at least 5 pp below the counter's**, the project's standard
  materiality unit.

**Both checks were rewritten before anything was run, and the reasons are
worth keeping.** The first was an interquartile range against an absolute
threshold of 0.20. That number had no derivation, and a derivation makes it
worse rather than better: one arm step is worth 0.024 utility at the mean
price sensitivity, so a bonus spread of 0.20 is eight arm steps and any
threshold in "actionable" units would be passed trivially. The bonus scale
(up to 1.5) simply dwarfs the price term (0.11 across the entire arm range for
a Poor buyer at a Slow stall) — which is itself worth stating, because it
means a fully loyal buyer in this market buys almost regardless of price, and
the seller's arm choice is mostly a decision about everyone else. A share is
interpretable without that conversion, and saturation is the property actually
at issue.

The second check asserted that the counter retains 0.33 of the bonus after an
interruption because the streak resets to 1. **That is wrong.** A cohort buyer
locked out of their stall for a week buys somewhere else, which moves
`last_seller` to the other stall and makes the bonus toward the original
**zero**, not a third; the only ones who retain anything are those who bought
nothing at all that week. So the counter is more brittle than the spec claimed,
not less. Measuring the bonus would also have been close to definitional on the
stock side — with no purchase available, the stock decays by exactly `rho`, so
retention is 0.80 adjusted by `tanh` curvature and the "gate" would be checking
arithmetic. Permanent switching is behavioral, is not definitional on either
side, and is directly comparable to a number Phase 6 has already published.

**Gate 2 — an intertemporal trade-off exists.** 7d's diagnostic, re-run per
surviving cell: hand-designed invest-then-harvest schedules against flat
pricing *at that cell's own oracle optimum*, paired by seed. Passes if the
best schedule's advantage has a 95% CI excluding zero **and** a point estimate
**≥ +2%**. In the base environment every schedule lost, the largest by −380.3.

**Gate 3 — complexity is necessary.** Two independent comparisons under the
standard ±5% relative materiality test, on seeds disjoint from training:
contextual bandit vs. context-blind bandit (needs gate 1), and the Q-network
vs. the better bandit (needs gate 2).

### Pre-registered handling of two things that will otherwise be argued after the fact

**Cell selection is deliberate selection on the outcome, and is valid only for
the claim being made.** 7e-2 runs on every cell that passes gate 1; 7e-3 runs
on the single cell with the *largest* gate-2 headroom. That is choosing the
most favorable market in the family. It is the correct design for an
**existence** claim — if complexity does not pay in the most favorable market
constructible here, the null is strong — and it is invalid for any statement
about effect size, which must not be read off 7e-3's chosen cell as though it
were a typical market.

**Gate 2 failing does skip 7e-3 here, and the reason it did not at 7d is not
convenience.** At 7d the schedule diagnostic was the only evidence, and it
tests only the schedules that were thought of, so running the learner added
information. At 7e the same diagnostic is run across a whole parameter ladder
including its own control (`delta = 0`); a uniform failure across the ladder
is a statement about the mechanism family, not about one analyst's
imagination. If gates 1 and 2 both fail across every cell, the finding is that
this family of loyalty mechanisms does not generate the structure, and no
learner is trained.

**Stopping rule, binding.** If gate 3 fails on the most favorable cell, record
the result: *even with persistent, price-sensitive, bounded loyalty, no
intertemporal trade-off large enough to reward a multi-week policy formed.*
Do not tune `rho`, `beta`, `delta`, `L*`, or `L_max` further, and do not widen
the arms, until a learner wins. A stopping rule that only binds when it is
convenient is not one.

### Phase 7e-1 — Mechanism calibration (no learner is trained)

A 4 × 2 grid at flat prices, plus the counter as a reference cell:
`delta` ∈ {0, 0.25, 0.5, 1.0} × `L*` ∈ {1.00, 1.25}, with `rho = 0.80`,
`beta = 0.25`, `L_max = 1.5` held fixed. `delta = 0` is the control that
separates the effect of the stock *form* from the effect of price-sensitive
accrual.

Outputs, per cell:
1. The two gate-1 statistics against their thresholds.
2. Stock trajectory: mean and IQR of the bonus by week, against the counter's.
3. **An oracle flat-price sweep**, which both supplies gate 2's baseline and
   answers on its own whether the mechanism moved the static optimum away from
   the base environment's 2.65.
4. Pair stability and switching rate, comparable to Phase 6's, so the
   mechanism can be read against a number that already exists.

**Acceptance criterion for 7e-1:** that gate 1 returns a decisive verdict for
every cell — that the mechanism's presence or absence is established, not that
any particular cell passes. As at Phase 5, what is graded is that a verdict is
reached.

### What the registered 7e-1 grid returned, and the four corrections it forced

The grid as registered — `delta` ∈ {0, 0.25, 0.5, 1.0} × `L*` ∈ {1.00, 1.25},
`rho = 0.80`, `beta = 0.25`, `L_max = 1.5` — was run at 30 seeds and 66 weeks.
Its headline number: **gate 1a passed in every cell and gate 1b failed in every
cell**, and neither outcome meant what the gate said it meant.

**1. Gate 1b's threshold was arithmetically unreachable.** It required
permanent switching at least 5 pp below the counter's. The counter's is
**4.0%**, so the largest advantage the metric can express is 4.0 pp and the
gate cannot be passed by any mechanism whatsoever. This is the same error as
Phase 6's first recovery metric, which compared a cohort against its own
pre-shock share of 1.0 and so set a bar nothing could clear. The lesson that
did not transfer the first time: **an absolute threshold on a quantity whose
range has not been measured is not a pre-registration, it is a guess wearing
one.** Thresholds on bounded rates are stated relatively from here on.

The metric was also close to inert. Permanent switching after a one-week
closure is 3.4–4.5% in *every* environment tested, because what brings a buyer
back is fixed preference — drawn once per season with a coefficient of 1.5 —
and not memory. It was measuring the population, not the mechanism.

**2. `delta` cannot be calibrated at flat prices, and 7e-1 runs at flat
prices.** Its entire function is to make a price *deviation* accrue loyalty
differently. At flat prices the only deviation is the promotion lottery, which
reaches a given stall in about 4% of weeks. The measured consequence, across
`delta` = 0 → 1: the oracle optimum does not move at all (2.65 in every cell)
and profit rises 1%. The `delta` ladder is therefore moved to **7e-2**, where
schedules supply the price variation it acts on. Running it here was a design
error, not a null.

**3. Pinning `L_max = 1.5` did not deliver the control it promised, and cost
the phase its premise.** The intent was that both mechanisms share a ceiling
so a 7e result could not come from stronger habit. But a nominal ceiling is
not strength. What binds a buyer is the *gap* between their incumbent's bonus
and the best alternative's, and a `tanh` stock spreads a smaller bonus across
several pairs where a counter puts its whole bonus on one and zero on the
rest:

| | lock-in contrast | pair stability | attached bonus (mean) |
|---|---|---|---|
| counter (7a–7d) | **0.811** | **0.430** | 0.542 |
| stock, `L*` = 1.00 | 0.292 | 0.368 | 0.655 |
| stock, `L*` = 1.25 | 0.244 | 0.360 | 0.527 |

The registered environment is a **weaker** lock-in than the one it was built to
enrich — about a third of the incumbency advantage, and lower pair stability
despite a comparable or higher mean bonus. A learner cannot exploit state that
binds less than the state it replaced, so every gate below this one would have
been measuring a poorer market and reporting it as a null about policy
complexity. Spread loyalty is weak loyalty; the counter's brutality was the
source of its strength.

**4. Gate 1a is definitional for a `tanh` mechanism and is demoted to a
descriptive.** A stock's achievable maximum is `L_max * tanh(S(1+delta)/L*)`,
strictly below `L_max`, so "not pinned at the ceiling" is arithmetic rather
than evidence — 0.0% in every cell. The counter's 20.5% is the informative
half of the comparison and is reported as such. A check that cannot fail is
not a gate, and calling it one inflates the apparent strength of gate 1.

### The corrected 7e-1 design: hold strength fixed, sweep the horizon

The diagnosis names strength, not shape, as what the registered grid got
wrong. So strength becomes a **control variable** rather than a free
parameter, and the sweep moves to the dimension the phase is actually about.

- **Control: lock-in contrast is equalized to the counter's**, by calibrating
  `L_max` per cell to a fixed point (contrast scales nearly linearly in
  `L_max`, so this converges in one or two iterations). The two environments
  are then equally strong and differ only in the *shape* of loyalty —
  persistent and graded against resettable and stepped. That is the controlled
  comparison the phase wanted, and the nominal ceiling was a bad proxy for it.
- **Curvature is fixed at the contrast-maximizing operating point.** With
  `S = beta/(1 - rho)` the steady-state stock of an every-week buyer,
  `u = S/L*` decides where on the `tanh` the population sits. Measured at
  `L_max` = 1.5: contrast peaks at `u` ≈ 2 (0.372) and falls off on both sides
  (0.247 at `u` = 1, 0.154 at `u` = 6). Fixed at **`u` = 2**, with `L*` = 1.00.
- **Swept: `rho`, the memory horizon** — {0.80, 0.85, 0.90, 0.95}, half-lives
  3.1 / 4.3 / 6.6 / 13.5 weeks — with `beta = u * L* * (1 - rho)` so the
  steady-state stock is unchanged and horizon is swept independently of level.
  One dimension at a time, which is the project's rule applied inside a
  calibration.

**Gate 1b, replaced: memory horizon.** Excess rate of returning to the same
seller `k` weeks later, over the **memory-OFF twin** on identical seeds —
Phase 6's ablation, and necessary because fixed preference produces choice
repetition at every lag on its own. Probed at **lag 8**, more than twice the
counter's three-week cap, so a mechanism whose horizon is genuinely longer
separates from one that merely smoothed the same horizon. Threshold:
**at least 1.5× the counter's excess at that lag** — relative, per correction 1.

**What the corrected design returned.** Contrast equalized at 0.81–0.84
against the counter's 0.825:

| `rho` | half-life | `beta` | calibrated `L_max` | contrast | lag-1 excess | lag-8 excess | vs counter | pair stability |
|---|---|---|---|---|---|---|---|---|
| counter | (cap 3) | — | 1.50 | 0.825 | +0.117 | +0.019 | 1.00× | 0.436 |
| **0.80** | 3.1 | 0.400 | 3.30 | 0.833 | +0.085 | **+0.054** | **2.87×** | 0.405 |
| 0.85 | 4.3 | 0.300 | 3.72 | 0.810 | +0.072 | +0.050 | 2.69× | 0.390 |
| 0.90 | 6.6 | 0.200 | 4.58 | 0.816 | +0.056 | +0.045 | 2.39× | 0.374 |
| 0.95 | 13.5 | 0.100 | 5.70 | 0.811 | +0.042 | +0.037 | 1.98× | 0.358 |

Every cell passes gate 1b, and **the registered `rho = 0.80` passes it most
strongly**. Raising the horizon parameter *lowers* the realized horizon,
because holding the steady state fixed requires `beta` to fall with `1 - rho`,
and a buyer who accrues more slowly builds less differentiation inside a
66-week season than one who accrues quickly and forgets. The chosen value was
right; what was wrong was the strength, not the horizon — which is the
opposite of what the failing gate appeared to say.

**Registered cell for 7e-2 and 7e-3:** `rho = 0.80`, `beta = 0.40`,
`L* = 1.00`, `L_max` calibrated to the counter's contrast, `delta = 0.25`
carried forward unmeasured and calibrated at 7e-2.

**One difference is not controlled and is stated rather than hidden.**
Equalizing incumbency advantage does not equalize total loyalty mass: the
calibrated environment sells more, with a purchase rate of 0.81 against the
counter's 0.69, because many buyers hold a small bonus toward several stalls
instead of a large one toward one. Gate 3 compares policies *within* an
environment, so this does not confound it. It does mean **profit levels are
not comparable across the two environments**, and no cross-environment profit
comparison is drawn anywhere in Phase 7e.

**Exit condition:** `git tag phase7e1-calibrated`, and gate 1's verdict
recorded per cell.

### Phase 7e-2 — Intertemporal headroom (still no learner)

**Question:** in the calibrated environment, can *any* hand-designed pricing
schedule beat the best standing price? If not, there is nothing for a
multi-week policy to find, and 7e-3's horizon arm is not run.

**Environment:** the cell carried from 7e-1 — `rho` = 0.80, `beta` = 0.40,
`L*` = 1.00, `L_max` = 3.30 — with the target stall's standing price set to
its own oracle optimum of **2.65**. That is the anchor, so the schedule's
arms are deviations *from a price buyers have adapted to*, and the loyalty
stock's reference point does not move with the schedule. `L_max` is held at
7e-1's calibrated value and is not re-solved here: re-calibrating per schedule
would make the environment a function of the policy being tested.

**The `delta` ladder runs here**, {0, 0.25, 0.5, 1.0}, because this is the
first stage with price variation for it to act on. `delta` = 0 remains the
control: the stock form with no investment channel. At flat prices all four
cells are identical by construction, which is why 7e-1 could not calibrate it
and why the flat baseline is shared across the ladder.

**Two schedule families, and the second is the one that matters.**

- **One-shot invest-then-harvest**, 7d's family, kept for comparability:
  `W` ∈ {8, 16} weeks at a discount, then a standing price for the rest.
- **Cyclic invest/harvest**: repeat `k` weeks low, `m` weeks high. This is
  included because at a 3.1-week half-life a one-shot investment provably
  cannot survive a 58-week harvest — the stock is gone within ten weeks of
  the harvest beginning. If a decaying stock rewards any schedule at all, it
  rewards a cycle, and testing only the one-shot family would produce a null
  that says more about the schedule set than about the mechanism.

**Selection and testing use disjoint seed blocks.** Roughly 170 schedule ×
`delta` combinations are compared; taking the maximum over them and testing it
at 95% would manufacture a pass out of noise. Schedules are therefore selected
on a **discovery block, seeds 2000–2059**, and the selected schedule alone is
tested on the standard **evaluation block, seeds 0–29**. This is 7d's
train/evaluate discipline applied to a search over hand-designed policies
rather than over network weights, and it is the difference between "some
schedule looked good" and "this schedule is good".

**Gate 2 passes** if, on the evaluation block, the selected schedule's profit
advantage over flat pricing has a 95% CI excluding zero **and** a point
estimate **≥ +2%**.

**What each outcome licenses.** Gate 2 passing licenses 7e-3's horizon arm
(the Q-network). Gate 2 failing does not stop 7e-3 — gate 1 already licensed
the **context** arm, so the contextual bandit runs either way, and a failure
here means the multi-week comparison is not run rather than that the phase
ends. Recorded now so the branch is not chosen after the number is known.

**Result: gate 2 passes, marginally, and the control is what makes it
readable.** Selected on the discovery block, tested on seeds 0–29: *invest 16
weeks at 0.90× the standing price, then return to it* earns **44.32 per week
against flat pricing's 43.18, +2.6% with a 95% CI of [+2.0%, +3.2%]**.

The `delta` ladder run on that identical price path is the causal argument, and
it is monotone:

| `delta` | 0 (control) | 0.25 (registered) | 0.5 | 1.0 |
|---|---|---|---|---|
| gain over flat, discovery block | **−1.24%** | +0.09% | +1.25% | **+3.05%** |

With the investment channel switched off, the same schedule **loses money**. The
gain is the loyalty stock, not the shape of the price path — which is the
comparison 7d could not make, because in the base environment there was no
channel to switch off.

**What actually pays is acquisition, and not extraction.** Every schedule that
ever charges *above* the standing price loses, the best of them by 5.5% and the
worst by 56%. So does every cycle. The winner discounts and then stops
discounting; it never harvests. This sharpens 7d's null rather than reversing
it: the sacrifice-then-recover signature is absent here too, and now the reason
is visible — a genuine intertemporal trade-off exists, and its profitable half
is the sacrifice.

**Two boundary conditions, recorded because they limit the claim.** The
headroom appears only at `delta` = 1, the strongest investment channel on the
ladder, so the true optimum may lie outside the range tested; per the phase's
stopping rule the ladder is **not** extended to find it. And the registered
`delta` = 0.25 yields +0.09% — it would have failed this gate. Carrying the
best cell into 7e-3 is the pre-registered selection-on-outcome rule, valid for
an existence claim and not for effect size.

**Exit condition:** `git tag phase7e2-headroom`, with the verdict and the
selected schedule recorded.

### Phase 7e-3a — Does context pay? (the arm gate 1 licensed)

**Question:** now that a persistent, dispersed loyalty state exists, does a
policy that conditions on it beat one that ignores it?

This is Phase 7c's question, asked in the environment 7c was skipped for
lacking. 7c was skipped because the profit-maximizing price turned out to be
invariant to every observable market condition tested — there was nothing for
a contextual policy to condition on, and running one would have measured the
cost of learning a useless feature. That answer was specific to the base
environment and does not carry over on its own.

**Environment:** the cell carried from 7e-2 — `rho` = 0.80, `beta` = 0.40,
`L*` = 1.00, `L_max` = 3.30, **`delta` = 1.0**, standing price 2.65, arms at
±20% of it. Carrying the highest-headroom cell is the pre-registered
selection-on-outcome rule: valid for an existence claim, invalid for effect
size.

**The context is the mechanism's own state.** The seller observes the mean
loyalty bonus buyers hold toward it, normalized by `L_max`, alongside the
features 7d already exposed. Conditioning a "contextual" policy on the streak
counter instead would test a feature this environment does not run on.

**Two measurements, because a learned null on its own is ambiguous.**

- **The oracle context diagnostic.** Does the profit-maximizing arm actually
  depend on the loyalty state? Measured by one-week deviations: from an
  all-flat reference season, at each week `w` play arm `a` for that week alone,
  then return to flat, and score the **cumulative profit over weeks `w`..`w+8`**
  — about two and a half stock half-lives, so an arm's effect on the stock is
  inside the window rather than discarded. The best arm per `(seed, week)` is
  then split by the loyalty state at `w`. This is 7c's diagnostic rebuilt for a
  mechanism whose state is endogenous to the price path: 7c could compare
  parallel full seasons because its state did not depend on the prices, and
  here it does.
- **The learned comparison.** LinUCB against context-blind UCB1, identical arms,
  identical seeds, identical online-within-season learning budget — the only
  difference is whether the context is visible. Both learn from scratch each
  season, which is 7b's protocol, so 3a is a clean paired comparison.

Reporting both is what makes a null readable. A LinUCB loss with an oracle that
*does* vary means context is real but costs more to learn than it returns in 66
weeks; a LinUCB loss with an oracle that does **not** vary means 7c's finding
survives the mechanism change. Those are different results and the learned
number alone cannot distinguish them.

**Reference ladder.** All arms are scored against the same two known points:
flat pricing at the oracle standing price (the myopic ceiling, 43.18/wk) and
7e-2's best hand-designed schedule (44.32/wk). A learner that cannot beat a
schedule written by hand has not found much.

**Gate 3a passes** if LinUCB beats UCB1 by a **material** margin under the
standard ±5% relative test on the evaluation seeds. As everywhere since Phase
5, what is *graded* is that the comparison reaches a verdict; which verdict it
reaches is the finding.

**Literature basis:** Li, Chu, Langford & Schapire (2010), "A Contextual-Bandit
Approach to Personalized News Article Recommendation" (WWW) — LinUCB, the
standard linear contextual bandit, used here in its original form rather than
with a learned representation, since the state is three interpretable features
rather than raw observations.

**Exit condition:** `git tag phase7e3a-context`, with both measurements
recorded.

---

## Phase 8 — Endogenous Market Structure

**Research question:** Can repeated micro-level interactions (Phase 7 dynamics) produce macro-level structure — market concentration, niche formation, or persistent inequality — without that structure being explicitly programmed?

**Single changed dimension:** allow seller entry/exit; buyer/seller decision mechanics unchanged from Phase 7.

**Run length:** 3–5 seasons (66–110 weeks) — a single season isn't enough to see whether the seller mix stabilizes or oscillates across season boundaries; see "Weeks and Seasons — Design Basis" above.

**New mechanism:**
- A seller exits if profit < a fixed cost threshold for 3 consecutive weeks.
- A new seller enters (class assigned proportionally to observed excess demand) if aggregate unmet demand exceeds a threshold for 2 consecutive weeks.

**`price_reference` is not recomputed on entry or exit.** The active seller set changes every time this mechanism fires, so this is the phase where a normalizer defined as "max over active sellers" would silently start moving. It must not. `price_reference` stays at the value computed from this phase's week-0 configuration for all 66–110 weeks — including when an entrant posts a price above every incumbent, in which case that seller simply evaluates at a ratio above 1.0 rather than resetting the scale. The reason is the same one that freezes it against Phase 7's learned prices: entry and exit are the mechanism under test here, and the scale of utility cannot be allowed to drift with the thing being measured. See "Price Normalization Convention" above.

**Acceptance criteria:**
- Track number of active sellers per class over weeks; report whether the market converges to a stable seller count/mix or oscillates
- **Real-data plausibility check:** compare the simulated season-to-season active-seller-count trajectory against RI DEM's actual 2019–2023 vendor counts (24, 31, 25, 24, 26) — not as a strict pass/fail, but to flag if the simulated trajectory is wildly more volatile or more static than a real multi-year market ever was
- Explicitly label any resulting stratification as **emergent** only if class information was not used anywhere in the seller entry/exit or pricing rule — otherwise label it **encoded** (per the project's own encoded-vs-emergent discipline)

### Web Visualization Extension — Entry/Exit Panels

Extends the Phase 6 page (same underlying artifact, not a rebuild). Adds:
- **Top-right panel:** "New this week" — list of entering sellers with class and entry week.
- **Bottom-right panel:** "Exited this week" — list of exiting sellers with class and reason (e.g., "profit below cost threshold for 3 consecutive weeks").
- On the main graph, an entering stall fades/scales in and an exiting stall fades/scales out when the week slider crosses the week they change — this makes the entry/exit dynamic visible, not just listed as text.

**Literature basis:** Schelling (1971), "Dynamic Models of Segregation" (*Journal of Mathematical Sociology*) — origin of the encoded-vs-emergent stratification question this phase tests. Gode & Sunder (1993) again relevant: market-level structure can emerge from simple, non-strategic agents.

**Exit condition:** `git tag phase8-validated`. This is the last purely rule-based phase — no moat-relevant data is generated through Phase 8.

---

## Phase 9a — Learned Buyer Policy (no LLM)

**Why this phase exists.** Phases 1–8 give sellers a four-rung learning ladder (7a heuristic → 7b bandit → 7c contextual bandit → 7d RL) but give buyers a single step from a hand-written formula straight to an LLM. That asymmetry weakens the question Phase 9b is supposed to answer.

The problem is sharper than "we skipped a rung". **No buyer parameter in Phases 1–8 was ever fitted to anything.** `intercept` 1.0, `budget_coef` 0.05, `preference_coef` 1.5, α 0.85/0.5/0.2, the loyalty bonus 0.5 and its cap of 3 — every one is hand-chosen, several of them chosen during this project's own design review gates. So the Phase 9 control group is not "an interpretable model" but *an unfitted model*, and an LLM beating it would establish only that an LLM outperforms a set of numbers someone picked. That is not a finding.

**Research question:** How does a buyer policy trained to actually maximize buyer welfare differ from the hand-written rule, and how far from optimal was the hand-written rule?

### The reward problem, and why a new primitive is needed

Sellers can be given reinforcement learning without difficulty because their objective — profit — is external and uncontroversial. Buyers have no such objective. The obvious answer, "maximize utility", is circular: utility *is* the hand-written formula, so a policy trained on it optimizes the very model this phase exists to move past.

Phase 9a therefore introduces one new simulation primitive: **`willingness_to_pay[buyer, seller]`**, the value a buyer actually places on a unit from that seller. Reward for a purchase is realized consumer surplus, `WTP − price_paid`; not purchasing earns zero. Budget and inventory constraints are unchanged.

**WTP must be the ground truth that `preference` was approximating — not an independent draw.** This is the constraint that makes the comparison valid at all. `preference[b, s] ~ U(0,1)` already exists and plays the role of taste in the hand-written utility. If WTP were drawn separately, the learned policy and the hand-written rule would be facing *different worlds*, and "9a vs Phase 8" would compare two markets rather than two decision rules. WTP is therefore a deterministic, monotone function of the same `preference[b, s]` draw and the buyer's class:

```
willingness_to_pay[b, s] = wtp_base[class] + wtp_spread[class] * preference[b, s]
```

The hand-written rule continues to see only `preference` — its proxy for value. The learned policy is evaluated on surplus — the value itself. Both act in one market, on identical seeds and identical draws, exactly as every paired comparison in Phases 1–6 has done.

`wtp_base` and `wtp_spread` are set at this phase's own design review gate, not here, and must be checked against the existing prices (2 and 6) and budgets (3, 7, 10) so that buying is neither always nor never worthwhile.

**A consequence worth stating: this makes the hand-written rule falsifiable.** With a surplus measure defined, "how much surplus does the hand-written rule leave on the table relative to a policy that optimizes it?" becomes an answerable question, and its answer is a result in its own right — the first time in this project that the rule-based model can be scored against anything other than itself.

### Architecture: a loop, not a pipeline

A generative agent is not a single learning algorithm, and writing this phase as
"representation learning → policy learning → LLM" would misdescribe what
Phases 9a and 9b together build. The structure is a closed loop:

```
behavioural trajectories (Phases 1-8 runs; real human data from Phase 10)
  -> representation learning        z_t = f(x, h_t)      latent buyer state
  -> policy / behaviour model       pi(a_t | z_t, e_t)   state -> action
  -> generative model               concrete decisions   (Phase 9b only)
  -> environment + memory update    h_{t+1}
  -> back to the top
```

Phase 9a builds the first two stages and the memory update; Phase 9b replaces
the policy stage with an LLM and closes the loop with generated behaviour.

**The latent state is learned, not hand-specified.** `x` is the buyer's stable
attributes and `h_t` its interaction history — and `h_t` already exists: Phase 6
gives every buyer a `last_seller_purchased` and a `loyalty_streak`, and the
transaction log carries the rest. Nothing new has to be invented to have a
history to compress; what is new is that `z_t` is *learned from trajectories*
rather than being the four hand-set coefficients Phases 1-8 used.

This matters for the same reason the reward could not be utility: a policy
conditioned on hand-designed features is still carrying the hand-written model's
assumptions about what matters. Whether a learned `z_t` beats hand-designed
features is an open question here exactly as it is for sellers at Phase 7c, and
it is tested the same way rather than assumed.

### Three arms, and only one of them is a baseline

- **`phase9a_clone` — behavior cloning of the Phase 8 rule.** A pipeline self-check, *not* a baseline. Behavior cloning succeeds exactly when it reproduces what it imitated, so the expected and desired outcome is **equivalent** under the Phase 5 materiality test. That result validates that the network and training pipeline can represent this decision task; it does not produce a stronger comparison group, because a neural copy of an unfitted model is still that unfitted model. Reported under that label so it cannot be mistaken for one.
- **`phase9a_policy_handfeat` — a surplus-maximizing policy on hand-designed features.** Class parameters, budget remaining, price, loyalty streak: the quantities the Phase 1-8 rule already used, given to a network that optimizes rather than imitates.
- **`phase9a_policy_learned` — the same policy on a learned `z_t`.** The load-bearing arm and the control group Phase 9b is graded against, *if* it beats the hand-designed variant; if it does not, the hand-designed one takes that role and the finding is recorded, as at Phase 7c.

**Acceptance criteria:**
- `phase9a_clone` returns **equivalent** against the Phase 8 rule on the tracked class shares, under the Phase 5 materiality test — the pipeline reproduces known behaviour
- Both policy arms achieve higher mean realized surplus per buyer than the Phase 8 rule, paired by seed, with 95% CIs excluding zero
- **Learned vs hand-designed representation is reported as a three-way comparison** (rule / hand-designed features / learned `z_t`) and is not assumed to favour the learned one — the same discipline Phase 7c applies to sellers
- Report the surplus gap as a percentage of the rule's own surplus — the "how far from optimal was the hand-written rule" number

**Technical note.** PyTorch becomes a real dependency here rather than an aspirational one, and is also what Phases 7c and 7d need. **PettingZoo is deliberately not adopted.** Multi-agent in the agent-based-modelling sense is not multi-agent in the multi-agent-RL sense: PettingZoo exists for several *learning* agents interacting simultaneously, and no phase in this roadmap has buyers and sellers learning at the same time — Phase 7 trains sellers only, Phase 9a trains buyers only. Adopting it would be ceremony. Mesa, SimPy and NetworkX are left unspecified on purpose; at a few hundred agents, plain Python and NumPy are sufficient, and pinning a framework in the spec would constrain implementation for no measured benefit.

**Literature basis:** Pomerleau (1991), "Efficient Training of Artificial Neural Networks for Autonomous Navigation" (*Neural Computation*) — the behavior-cloning approach used for the pipeline-check arm. For the optimizing arm, the framing is standard consumer-surplus maximization under a budget constraint rather than a specific paper.

**Exit condition:** `git tag phase9a-validated`.

---

## Phase 9b — Synthetic Agent Users

**Research question:** What does replacing the buyer decision function with an LLM-driven Agent change, holding the rest of the simulation fixed? This is a scaffolding phase, not yet a human comparison.

**The control group is Phase 9a's trained policy, not the hand-written rule.** Comparing an LLM against an unfitted formula can only show that an LLM outperforms a set of hand-picked coefficients, which nobody doubts and which answers nothing. Compared against a policy trained to maximize realized surplus, the question becomes decidable in either direction: if the LLM still wins, that is a result worth reporting; if it does not, the case for LLM agents in this setting is weaker than assumed, and that is equally worth reporting. This is the question the project's own design philosophy asks - what does a foundation model contribute over an interpretable one - and the earlier control group could not answer it.

The rule-based subgroup is still run, as a third arm, so the three decision mechanisms can be ranked against each other in one market.

**Single changed dimension:** decision function for a subset of buyers only — **N = 30 buyers (30% of the 100-buyer population)** run as Agents. The remaining 70 are split between the Phase 9a trained policy and the hand-written rule, so all three mechanisms appear in the same run against the same seeds, prices and draws.

**Why N = 30, not a pilot-and-see number:** Brand, Israeli & Ngwe (2023) describe submitting each prompt/scenario "dozens of times" in their methodology (their abstract separately says "hundreds" — the two are not fully consistent, and both are reported here rather than picking whichever sounds better). 30 sits inside the "dozens" range their methodology actually uses, and this phase carries no human-comparison cost yet, so there is no budget reason to go smaller.

**Mechanism:** each Agent receives a structured persona (class, budget, preference, current week's context/promotion state) and returns a purchase decision per seller. Exact prompt format is an implementation detail to finalize during this phase, not before.

**Logging additions (mandatory, ties to moat schema):** `model_used` = actual model name/version; `prompt_version`; random seed for any Agent sampling temperature used; `synthetic_cost_usd` and `synthetic_latency_seconds` per run (see Logging Schema section above).

**New reference table — `human_baseline.csv`:** introduced here to give the cost/speed KPI something to compare against. Columns: `research_method` (e.g., "in-person survey panel", "online panel"), `cost_per_respondent_usd`, `typical_turnaround_days`, `source` (citation for the figure, e.g., an industry report — do not invent a number without a source). This table is populated with a small number of well-sourced industry reference points, not primary research at this stage.

**Acceptance criteria:**
- Compare Agent-subset vs rule-based-subset choice distributions within the same run
- Confirm the Agent's decisions are logged with enough metadata (prompt version, model version) to be reproducible — this metadata requirement is what makes Phase 10+ comparisons possible later
- Compute and report the cost/speed ratio: `synthetic_cost_usd / (n_agent_decisions × human_baseline.cost_per_respondent_usd)` and the equivalent latency ratio, using the `human_baseline.csv` reference

### Web Visualization Extension — Agent Inspector (generative-AI showcase)

Extends the Phase 6/8 page. This is the centerpiece feature for the portfolio angle, because it is the first point where the visualization can show *reasoning*, not just outcomes.

- Clicking any Agent-driven buyer sprite opens an **Agent Inspector** panel showing: the buyer's persona summary (class, budget, preference), the decisions made that week per seller visited, and — if the Agent was prompted to explain itself — the natural-language reasoning text returned by the model for that decision.
- The panel also displays a small comparison badge using the cost/speed ratio computed above (e.g., "$0.002 vs ~$5/respondent · 0.8s vs ~3 days typical turnaround"), sourced from `human_baseline.csv` — this is the single visual that most directly makes the commercial "cheaper and faster" argument tangible rather than abstract.
- This inspector view also has direct research value beyond the demo: the reasoning text is a cheap qualitative check on whether the Agent's stated logic matches what its class/preference profile should produce — a useful sanity signal ahead of the formal Phase 10 human comparison.

**Literature basis:** Park et al. (2023), "Generative Agents: Interactive Simulacra of Human Behavior" (Stanford, *UIST*) — foundational LLM-agent architecture; see also Park et al. (2024), "Generative Agent Simulations of 1,000 People" (arXiv:2411.10109), a closer analogue to this project's population-scale ambitions. Horton (2023), "Large Language Models as Simulated Economic Agents" (NBER WP 31122) — the "Homo Silicus" framing for using LLMs as economic agents.

**Exit condition:** `git tag phase9b-validated`.

---

## Phase 10 — Human vs Agent (Asset A begins)

**Research question:** For a fixed decision scenario, where does Agent/synthetic choice distribution match or diverge from real human choice distribution?

**Budget constraint, addressed directly:** this project currently has no budget for new primary human data collection (surveys, panels). Phase 10 therefore runs **only on scenarios where a usable human benchmark already exists in the public record** — reusing published data rather than collecting new data. This is not a compromise invented for this project; it mirrors what Brand, Israeli & Ngwe (2023) themselves did — their human benchmark was an already-published conjoint study, not new data they collected.

**Candidate public data sources — verified, not assumed.** Each of the following was actually checked (fetched and inspected), not just found in a search result, because several plausible-looking candidates turned out to be unusable on inspection:

*Usable:*
- **"Preference and WTP for Livestock Market Facilities" (2018, agricultural economics)** — the closest domain match found: real discrete-choice data on preferences for market-facility attributes. Hosted on Mendeley Data (`data.mendeley.com/datasets/4754fk2tw7/1`).
- **"Consumer WTP for Sustainability Attributes in Beer" (2020)** — real consumer choice/WTP data, useful for the price-sensitivity dimension. Mendeley Data (`data.mendeley.com/datasets/4z748jnnjs/2`).
- **"Are farmers willing to pay for climate-related wheat traits?" (Ethiopia, 2020)** — real agricultural-market WTP data, though production-side rather than consumer-side. Mendeley Data (`data.mendeley.com/datasets/r288pwfzhj/1`).
- Curated source for finding more candidates as needed: the `alvarogutyerrez/TheDiscreteChoiceDataBank` GitHub repository, a maintained list of real, publicly downloadable discrete-choice datasets across fields.

*Checked and rejected:*
- Santurkar et al.'s (2023) **OpinionQA dataset** — confirmed real and downloadable (`github.com/tatsu-lab/opinions_qa`), but on inspection it is political/social-attitude survey data (abortion, climate policy, automation), not consumer/retail choice data. Domain mismatch — **do not use for this project's scenarios**, despite being a legitimate, well-known dataset in general.
- The `prices` and `hotel` datasets bundled in `ajgara/choice-models` (companion code to Berbeglia, Garassino & Vulcano 2018) — their own documentation states these are **synthetic instances generated for that paper's model testing**, not real human responses. Do not cite these as human data.
- The Kamishima Sushi dataset (also bundled in the same repo) — this one *is* real (5,000 real respondents ranking 10 sushi types), but the packaged form is ~436MB of resampled JSON instances built for that paper's own training/testing pipeline, not a clean usable choice-distribution file, and sushi ranking is a weak domain match for market/pricing scenarios. Rejected on practicality and fit, not on authenticity.

**No exact scenario match exists, and that's expected, not a failure.** Nothing public replicates "buyers choosing between low-price and premium farmers-market stalls." Phase 10's scope is adjusted accordingly:

**Revised acceptance criteria:** Phase 10 validates **directional, general-pattern agreement** (e.g., does the Agent's choice probability decrease with price the same way real WTP data shows it should, for *some* real consumer-choice dataset covering that general mechanism) rather than exact-scenario distributional replication. This limitation — cross-domain directional validation, not same-domain distributional validation — must be stated explicitly in any output of this phase, not left implicit.

**Fetch note (division of labor):** GitHub-hosted candidates can be fetched directly by an automated agent (Claude Code or otherwise) with standard git/network access. Mendeley Data, Figshare, and Dryad — where the three "usable" datasets above actually live — are not reachable from every sandboxed environment; downloading those three currently requires a human click-through (no login required) or an agent environment with broader network access than a locked-down sandbox.

**Agent side — N = 100 responses per scenario.** This lands between Brand, Israeli & Ngwe's two reported figures ("dozens" in their methods text, "hundreds" in their abstract) — a concrete, defensible middle point grounded in that paper's own practice, not a number chosen by us in the abstract.

**New logging table:** `human_benchmarks.csv`: `human_benchmark_id`, `source_type` (**public_dataset** / published_estimate / survey / choice_experiment / transaction_data — `public_dataset` and `published_estimate` are the only types available until Phase 15), `sample_size`, `scenario_id`, `collection_date`, `known_limitations` (e.g., stated- vs revealed-preference gap, cross-domain rather than same-domain match).

**Metrics to compute per scenario:** choice distribution distance (e.g., Jensen-Shannon divergence), directional agreement (did human and synthetic favor the same option, regardless of magnitude), and — critically — **assign a `decision_type` tag** (pricing/segmentation/campaign/market_entry) to every scenario, since this tag is what Phase 14's reliability metric will later aggregate over.

**Acceptance criteria:** at least one complete (scenario, human_benchmark, synthetic_run, gap_metric, decision_type) record logged, sourced entirely from public/published data — this is the first row of Asset A.

**Literature basis:** Brand, Israeli & Ngwe (2023), "Using GPT for Market Research" (HBS Working Paper 23-062 / *EC'24*) — the closest direct precedent for this project's commercial use case (LLM-simulated willingness-to-pay compared against a published human conjoint study, not new data); note their caution that the model captures aggregate patterns better than individual-level preference heterogeneity, directly relevant to what this phase should watch for. Argyle et al. (2023), "Out of One, Many" (*Political Analysis*) and Aher, Arriaga & Kalai (2023, *ICML*) — support for LLM-simulated human samples. Bisbee et al. (2023/2024), "Synthetic Replacements for Human Survey Data? The Perils of Large Language Models" (*Political Analysis*) — counterpoint urging caution, kept alongside the supporting evidence rather than cited selectively.

**Exit condition:** `git tag phase10-validated`.

---

## Phase 11 — Bias Quantification (Asset A formalizes; Asset B built)

**Research question:** Is the human-AI gap systematic and predictable, and can it be corrected?

**Deliverable 1 — Bias Map:** a structured table across (category, demographic/class, context, model, gap magnitude, gap direction), built by repeating Phase 10 across multiple scenarios.

**Deliverable 2 — Correction layer prototype (Asset B):** a function (starting as simple as a per-category additive/multiplicative adjustment) that maps raw synthetic output to a corrected prediction, fit on a training subset of the Bias Map and evaluated on a held-out subset (calibration/validation split — never claim correction works based on the same data it was fit on).

**Acceptance criteria:**
- Held-out correction error is measurably smaller than uncorrected error
- Document which categories/contexts show large, stable bias (correctable) vs. noisy, unstable bias (not yet correctable) — both are informative

**Literature basis:** Santurkar et al. (2023), "Whose Opinions Do Language Models Reflect?" (*ICML*) — demographic-group bias-mapping methodology this phase's Bias Map is directly modeled on.

**Exit condition:** `git tag phase11-validated`.

---

## Phase 12 — Cross-Model Comparison (Asset C begins)

**Research question:** Does the same scenario produce different behavioral conclusions across foundation model families (e.g., GPT family vs. Claude family)?

**Mechanism:** repeat the Phase 10 scenario set across at least two model families, holding persona/environment/context/task/scenario fixed. Log `model_family`, `model_version` per run.

**Acceptance criteria:** decompose observed outcome variance into model effect vs. seed/random effect vs. prompt effect vs. environment effect (simple ANOVA-style breakdown is sufficient at this stage — do not reach for hierarchical models until this breakdown shows it's needed).

**Literature basis:** No single canonical cross-model behavioral-benchmarking paper exists yet — this is a thin, fast-moving area. Say so on the slide rather than forcing a citation; treat this phase's own accumulated results as the primary source, and revisit as the field matures.

**Exit condition:** `git tag phase12-validated`.

---

## Phase 13 — Context Robustness

**Research question:** How much does simulated behavior change under small variations in prompt wording, persona description, or information ordering — and is that sensitivity comparable to human context-sensitivity, or artificially unstable?

**Mechanism:** for a fixed underlying scenario, vary prompt wording/persona phrasing/ordering while holding the substantive scenario constant; compute a Context Sensitivity Score (e.g., variance in choice distribution across prompt variants).

**Acceptance criteria:** report the Context Sensitivity Score per scenario/model; where human framing-effect data exists (from Phase 10 sourcing), compare; where it does not, explicitly flag this as an open gap rather than assuming synthetic sensitivity is "fine."

**Literature basis:** Sclar, Choi, Tsvetkov & Suhr (2024), "Quantifying Language Models' Sensitivity to Spurious Features in Prompt Design" (*ICLR*) — found performance swings of up to 76 accuracy points from meaning-preserving prompt-format changes; direct basis for the Context Sensitivity Score.

**Exit condition:** `git tag phase13-validated`.

---

## Phase 14 — Decision Reliability (Asset D crystallizes)

**Research question:** At what point does simulation error become large enough to flip a business-relevant decision, and can this be estimated as a probability?

**Deliverable:** for each `decision_type` (using the tag introduced in Phase 10), compute `P(major decision error | model, context, decision_type)` — defined as the frequency with which the simulation's ranking/recommendation direction disagreed with the human-benchmark-implied decision, using accumulated data from Phases 10–13.

**Output:** a reliability table (decision_type × model × context → reliability estimate) — this is the first artifact that is directly client-facing.

**Literature basis:** Howard (1966), "Information Value Theory" (*IEEE Trans. Systems Science and Cybernetics*) — decision-analysis foundation for treating reliability/uncertainty-reduction as a quantity with a defined value, which is what P(major decision error) operationalizes here.

**Exit condition:** `git tag phase14-validated`. This is the last phase before any real client engagement.

---

## Phase 15 — Reference-Scale Demonstration (portfolio terminus; no real client required)

**Reframing note:** this phase no longer requires a paying client. For a portfolio/academic context (e.g., an MSCS application), the terminal validation is against the best available *public* reference data rather than a live commercial engagement — Phase 16's data flywheel is the piece that genuinely requires an ongoing client relationship, and is treated as future work, not executed here (see Phase 16 below).

**Research question:** When every mechanism from Phases 1–14 runs together at a realistic population scale, do the resulting aggregate patterns land in a plausible range compared to real farmers-market data — not "is this a validated commercial product," but "does the whole stack still make sense once you stop simplifying it for tractability?"

**Scale:** ~700 buyers : ~25 sellers (20:1 ratio, matching the RI DEM real-market average directly, rather than the smaller 80:4 / 100:5 used for mechanism-testing in earlier phases), with buyers split Poor 490 / Middle 140 / Rich 70 (same 7:2:1 ratio as Phase 2), run for 3–5 seasons (66–110 weeks).

**What runs:** the full accumulated stack — heterogeneous buyers (Phase 2), environment and context (Phases 3–4), whichever nonlinear/linear conclusion Phase 5 reached, loyalty and participation (Phase 6), the seller-learning sub-stage that actually cleared its graduation bar in Phase 7 (7a if none of 7b–7d did), endogenous entry/exit (Phase 8), Agent-driven decisions for a subset of buyers with cost/speed tracking (Phase 9), and — where public benchmark data exists — the bias-corrected predictions from Phase 11.

**Acceptance criteria:**
- The simulated multi-season active-seller trajectory, participation rate, and buyer-seller pair stability should fall within a plausible range of the real RI DEM figures used throughout this document (season length ~22 weeks, vendor counts ~24–34, customer:vendor ratio ~15:1–30:1) — this is a plausibility check, not a formal statistical validation, and should be reported as such
- The cost/speed ratio from Phase 9 (`synthetic_cost_usd` vs. `human_baseline.csv`) should still hold at this larger scale

**Web page:** the same assembled artifact from Phase 6/8/9 (see `market_bonds_prototype.html`), now fed this run's real output data instead of illustrative seeded-random sample data. This is the "final state" deliverable — see below.

**Literature basis:** No direct academic citation for the demonstration step itself — it is an applied capstone grounded in the accumulated findings of Phases 1–14, at a scale directly informed by Brand, Israeli & Ngwe's (2023) demonstrated commercial use case and the RI DEM real-market data used throughout this document.

**Exit condition:** `git tag phase15-validated`.

---

## Final State — What the Last Stage Actually Looks Like

By Phase 15, the project has one running artifact, not sixteen disconnected ones: a single web page (built incrementally, never rebuilt from scratch) that has accumulated a layer per phase —

- **From Phase 6:** the market view itself — buyers (colored circles) and stalls (colored squares) at real reference scale, buyers roaming continuously between stalls via the animation loop, fading out on weeks they don't participate; the metrics-over-time chart; the agent-detail panel; the research-question callout; the "how it works" steps; filters and a loyalty-streak slider; a week scrubber.
- **From Phase 8:** the entry/exit panels layered onto the same page, now showing real (not scripted) entry/exit events from the Phase 8 mechanism running at full scale.
- **From Phase 9:** the Agent Inspector — clicking a buyer shows real Agent-generated reasoning text (not the two canned example sentences used in the prototype) for the subset of buyers running as Agents, alongside the real cost/speed comparison badge against the human baseline.
- **The numbers behind all of it** are, for the first time, running at the ~700:25 real-market scale across 3–5 real-length seasons, rather than the small mechanism-testing populations used from Phase 1 through Phase 14.

Concretely: `market_bonds_prototype.html` (the working prototype already built during Phase 6 design) *is* structurally the final page — Phase 15 does not design a new page, it re-runs the same page against real Phase 1–14 output at real scale. This is the practical payoff of insisting, back in Phase 6, that the visualization be extended incrementally rather than rebuilt at each phase: by Phase 15 there is nothing left to build, only real data left to plug in.

---

## Phase 16 — Data Flywheel (future work — not executed in this project's scope)

**Status note:** unlike Phases 1–15, this phase is not executed. It genuinely requires an ongoing real client relationship generating real outcomes to recalibrate against, which a portfolio/academic project doesn't have. Documenting the intended design (below) without running it is the honest way to handle this — the architecture (schema, logging) built from Phase 1 onward already supports it, so nothing here would need to be redesigned if a real engagement did materialize later.

**Research question:** Do real client outcomes measurably improve future simulation accuracy when fed back into the correction layer (B) and reliability estimates (D)?

**Mechanism:** define a recalibration cadence (e.g., quarterly): new `client_engagements.csv` rows and any new `human_benchmarks.csv` rows are used to refit the Phase 11 correction layer and update the Phase 14 reliability table.

**Acceptance criteria:** reliability estimates from Phase 14 measurably tighten (narrower uncertainty, or improved held-out accuracy) after each recalibration cycle, and this improvement is documented per cycle — this running record is, at this point, the primary product.

**Literature basis:** No direct academic citation — the recalibration loop is an applied extension of the calibration/validation discipline established in Phases 10–14, not a distinct piece of literature.
