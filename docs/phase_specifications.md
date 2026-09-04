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
| 8 | Emergent-structure test; entry/exit rules contain no class information | No manipulated variable — observed natural evolution across seasons | Active-seller count per class, stratification | **Not an internal model comparison — compared against real RI DEM 2019–2023 vendor counts (24, 31, 25, 24, 26) for plausibility of volatility** |

**Phases 9–14 — comparison shifts from within-model tests to comparison against real human data, with formal statistics**

| Phase | Methodology | Independent variable(s) | Dependent variable(s) | How difference is judged |
|---|---|---|---|---|
| 9 | Substitution experiment; Agent decisions replace rule-based decisions for a subset (within-run control group) | Decision mechanism (rule-based vs. Agent), holding everything else fixed | Choice distribution, `synthetic_cost_usd`, latency | Agent subgroup vs. rule-based subgroup within the same run; cost/speed ratio against `human_baseline.csv` |
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
| budget_per_visit | 3 | 5 | 10 |
| price_sensitivity (α) | 0.85 | 0.5 | 0.2 |
| preference | drawn once per buyer per seller, Uniform(0,1), fixed for the run |

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

Budget is shared across all 5 sellers within one run (spending at one seller reduces what's left for the next); resets each run. All three classes evaluate all 5 sellers — nothing restricts Poor or Rich buyers from considering the "wrong" tier, the same as before; class only affects the parameters feeding into utility, never the choice set itself.

**Output tables:** same four as Phase 1, plus `run_summary.csv` adds: `Poor_to_Slow_share`, `Poor_to_Shigh_share`, `Middle_to_Slow_share`, `Middle_to_Shigh_share`, `Rich_to_Slow_share`, `Rich_to_Shigh_share`.

**Validation:** 30 seeds, running-mean convergence check as in Phase 1.

**Acceptance criteria:**
- `participation_rate` in 0.6–1.0
- `Poor_to_Slow_share` at least 2x `Poor_to_Shigh_share`, and `Rich_to_Shigh_share` at least 2x `Rich_to_Slow_share` (confirms the encoded direction is working at both ends — a mechanism check, not a "finding")
- `Shigh` sellers do not fully sell out (`inventory_remaining` > 0), confirming high-price demand isn't artificially unconstrained
- **New check, specific to the three-class design:** report `Middle_to_Slow_share` vs. `Middle_to_Shigh_share` without a directional pass/fail bar — unlike Poor and Rich, there is no "correct" direction encoded for Middle, so this is recorded as an open observation, not graded against a threshold

**Comparison required:** report homogeneous (Phase 1 style) vs. heterogeneous (this phase) participation and class-share metrics side by side, to isolate what heterogeneity alone contributes.

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

Assign, e.g.: 2 Slow sellers near entrance (position 0.9), 1 Slow seller far (position 0.3); 1 Shigh near entrance (0.8), 1 Shigh far (0.3).

**Output:** same as Phase 2, plus `run_summary.csv` adds `visibility_rate_by_seller`.

**Acceptance criteria:**
- Far sellers show measurably lower `n_sold` than near sellers of the same price class (isolates the environment effect from the price effect)
- Compare `Poor_to_Slow_share`, `Middle_to_Slow_share`, and `Rich_to_Slow_share` against the Phase 2 baseline — quantify how much the environment variable shifts these shares (this is the actual deliverable: "person alone" vs "person + environment" explanatory contribution)

**Literature basis:** Huff (1963, 1964), gravity-based retail trade-area model — basis for `visibility_prob` declining with seller position, directly paralleling Huff's $P_{ij} \propto A_j^\alpha / D_{ij}^\beta$.

**Exit condition:** `git tag phase3-validated`.

---

## Phase 4 — Person + Environment + Context

**Research question:** Does a transient, situational factor (a temporary promotion) shift buyer distribution beyond Person + Environment (Phase 3), and does its effect resemble a level-shift or an interaction with buyer class?

**Single changed dimension vs Phase 3:** add one context variable — a temporary price promotion — nothing else changes.

**New mechanism:** each run, with probability 0.2, one randomly chosen seller receives a 30% temporary price discount for that run only (`price_effective = price * 0.7`). This does not persist across runs (no memory yet — that's Phase 6).

**Output:** `run_summary.csv` adds `promotion_active (bool)`, `promotion_seller_id`, and share metrics conditional on promotion status.

**Acceptance criteria:**
- Among runs where a promotion is active, the promoted seller's `n_sold` increases measurably vs. its own Phase-3 baseline
- Report whether the promotion effect size differs across Poor, Middle, and Rich buyers (first place an interaction naturally shows up, before Phase 5 formally introduces interaction terms)

**Literature basis:** Belk (1975), "Situational Variables and Consumer Behavior" (*Journal of Consumer Research*) — basis for modeling a transient promotion as a situational/context variable distinct from stable person or environment features.

**Exit condition:** `git tag phase4-validated`.

---

## Phase 5 — Nonlinear Behavioral Effects

**Research question:** Does adding one nonlinear mechanism (a budget-cliff threshold effect) materially change conclusions vs. the linear model used in Phases 2–4?

**Single changed dimension:** replace the linear budget term with a threshold term; everything else (heterogeneity, environment, context) stays as configured in Phase 4.

**New mechanism:** if `budget_remaining - price < 0.5` (i.e., the purchase would leave the buyer with almost nothing), apply an additional utility penalty:
```
if (budget_remaining - price) < 0.5:
    utility -= 1.0
```
This represents reluctance to spend down to near-zero, not captured by the smooth linear term.

**Acceptance criteria:**
- Compute class-share metrics (`Poor_to_Slow_share`, etc., across all three classes) under linear-only (Phase 4 rerun) vs. linear+threshold (this phase), same seeds
- Report a distributional distance (e.g., total variation or simple percentage-point difference) between the two — the deliverable is answering "was the added complexity worth it," not just "the nonlinear model also runs"

**Literature basis:** Kahneman & Tversky (1979), "Prospect Theory: An Analysis of Decision under Risk" (*Econometrica*) — basis for the reference-point-driven utility penalty near budget exhaustion (loss aversion near a reference point, here the point of near-zero remaining budget).

**Exit condition:** `git tag phase5-validated`. If the nonlinear term changes conclusions by less than a pre-agreed small threshold (e.g., <5 percentage points on all tracked shares), document that finding and default back to the linear model for subsequent phases unless a specific later phase needs the nonlinearity reinstated.

---

## Phase 6 — Repeated Interaction (multi-week; history becomes real here)

**Research question:** Does buyer memory (loyalty to a previously-purchased seller) change future behavior and produce stable buyer-seller relationships over time?

**Single changed dimension:** add a time axis (multiple weeks in one simulation) and a memory term; single-week mechanics inherited from Phase 5 (or Phase 4, per that phase's outcome) are otherwise unchanged.

**New mechanism:**
- Run 1 season = 22 weeks per simulation (not independent reruns — state persists across weeks within one simulation). See "Weeks and Seasons — Design Basis" above for why 22.
- Each buyer tracks `last_seller_purchased`.
- Add a loyalty bonus to utility: `+0.5` if evaluating the seller from `last_seller_purchased`.
- Seller inventory resets at the start of each week; budget resets each week.
- Not every buyer participates every week — give each buyer a per-class participation probability (e.g., Poor ≈ 0.85, Middle ≈ 0.84, Rich ≈ 0.82) and skip the purchase decision entirely (log as "did not shop") on weeks they don't participate. This is a real, previously-undocumented part of the mechanism, not a visualization-only flourish — `participation_rate` in `run_summary.csv`/`weekly_summary.csv` should reflect it directly.

**Output:** new table `weekly_summary.csv`: week_number, participation_rate, class shares, `buyer_seller_pair_stability` (fraction of buyers, among those who participated in both this week and the prior week, whose seller choice matches).

**Acceptance criteria:**
- `buyer_seller_pair_stability` should increase over the 22 weeks and plateau (convergence check, same running-mean logic as before, but along the week axis within a run rather than across seeds)
- Report the week at which stability plateaus

### Web Visualization (introduced here — dual-purpose: debugging tool + portfolio piece)

This is the first phase where "week" is a real mechanism, so it is the natural point to introduce the market's web visualization. Because this project also serves as a CS/generative-agent portfolio piece, this visualization is built with real presentation quality from the start rather than deferred to Phase 15 — but the scope stays tightly bounded so it doesn't become its own multi-week side project.

**Rendering approach:** the visualization consumes the *pre-computed* output of a completed 22-week (1-season) simulation run (`weekly_summary.csv` + `transactions.csv`), not a live/real-time simulation. This keeps it buildable as a single self-contained artifact.

**Design direction (supersedes the earlier pixel-sprite plan):** after prototyping, the page follows a research-tool aesthetic closer to an interactive scientific demo (in the spirit of tools like Distill.pub explainers or agent-based-model dashboards) rather than a game-style pixel market. A working reference prototype exists (`from_choice_to_behavior.html`, which superseded an earlier two-class version, `market_bonds_prototype.html`) and should be used as the template rather than re-derived from scratch:
- **Header:** title, population/season badges, live readouts (participation rate, active stall count, avg. buyers per active stall, pair stability).
- **Filters, above the graph, not overlaid on it:** show/hide by buyer class (now three: Poor, Middle, Rich) and by stall class; a "loyalty streak ≥ N weeks" slider that dims buyers below the threshold. Any legend or "how to use" text must live outside the graph canvas (in a strip above or a caption below) — never as a floating overlay on top of the graph itself, since fixed-width overlays break on narrow viewports and visually collide with the dots underneath them.
- **Graph:** buyers as small circles (three distinct colors, one per class — do not reuse a stall-tier color for a buyer class, to keep the two class systems visually unambiguous), stalls as squares (color by class, distinguishing shape as well as color). No connecting lines between buyers and stalls — clustering position alone conveys "who's shopping where." Buyers continuously roam the whole canvas via an animation loop independent of the week slider: periodically (every few seconds) each buyer picks a new destination — mostly its real current-week assigned stall, sometimes another stall (for Poor/Rich, another stall of the same class, i.e. "browsing"; for Middle, any active stall, since Middle isn't restricted to one tier), occasionally open space — and glides there smoothly. This roaming is a visual/atmosphere layer only; it never feeds back into the logged metrics, which are always computed from the discrete weekly assignment data. Buyers who did not participate that week fade out entirely and fade back in when they resume shopping — a direct visualization of `participation_rate`, not decoration. Stalls fade/scale in and out on their real entry/exit weeks (Phase 8 onward).
- **Right panel:** a metrics-over-time chart (pair stability, active stall count, avg. load per stall — all computed from the same weekly data driving the graph, not a separate fabricated series) with a clickable legend to toggle series; an "agent detail" panel that shows a clicked buyer's class, current stall, and loyalty streak; the phase's research question as a highlighted callout; a short numbered "how the simulation works" explanation.
- **Footer:** play/pause and a week scrubber.

**Framing note for the portfolio angle:** because this same page is extended incrementally in Phase 8 (entry/exit panels) and Phase 9 (Agent Inspector) rather than rebuilt from scratch, the finished demo tells a coherent story on its own — "watch the simulation grow from simple rules to an Agent-driven system" — which is a more distinctive portfolio narrative than a single flashy end-state demo with no visible reasoning behind it.

**Literature basis:** Massy, Montgomery & Morrison (1970), *Stochastic Models of Buying Behavior* (MIT Press) — classic framework for loyalty/switching dynamics in repeated purchasing; basis for the buyer-seller pair-stability metric.

**Exit condition:** `git tag phase6-validated`.

---

## Phase 7 — Seller Learning

**Research question:** Does adaptive pricing change profit, participation, and class-segregation patterns relative to the fixed-price baseline (Phase 6), and how much additional learning sophistication (bandit → contextual bandit with a learned representation → reinforcement learning) is actually justified by the results?

This phase is split into four sub-stages, run in order. **Each sub-stage requires a graduation gate before moving to the next** — added complexity must materially change the outcome metrics (profit, participation, class shares) by more than a pre-agreed threshold (e.g., >5 percentage points), or the project stops at the simpler sub-stage and documents that finding. This directly applies the project's own "does complexity earn its place" principle to the learning-sophistication dimension, not just the behavioral-modeling dimension.

**Price normalizer stays frozen through every sub-stage.** This is the first phase where posted prices move week to week, so it is the first phase where the utility formula's `price_reference` could drift. It must not: it is pinned to the highest posted price in the phase's week-0 configuration and held there for all 66 weeks, regardless of how far the learned prices travel from it. A normalizer that tracked the prices being learned would put the scale of utility itself under the control of the mechanism this phase is trying to measure. See "Price Normalization Convention" above.

### Phase 7a — Moving-Average Heuristic (baseline)

**Single changed dimension:** sellers adjust price weekly based on a moving-average heuristic; buyer-side mechanics unchanged from Phase 6.

**Mechanism:**
```
if inventory_remaining == 0 at end of week:
    price *= 1.05
elif inventory_remaining > 0.5 * starting_inventory:
    price *= 0.95
```

**Acceptance criteria:**
- Compare profit, participation rate, and class shares over 3 seasons (66 weeks) against the Phase 6 fixed-price baseline, same seeds
- Report whether adaptive pricing increases or decreases `Poor_to_Shigh_share` and `Rich_to_Slow_share` (does learning pull the middle class toward one tier or the other?)

**Literature basis:** den Boer (2015), "Dynamic Pricing and Learning: Historical Origins, Current Research, and New Directions" — survey grounding for heuristic (non-optimizing) adaptive pricing as the baseline stage before formal learning algorithms.

**Exit condition:** `git tag phase7a-validated`.

### Phase 7b — Multi-Armed Bandit (policy learning, no context)

**Research question:** Does treating price choice as a bandit problem (exploring a small set of price points, exploiting the best-performing one) outperform the fixed heuristic in 7a, without yet using any market context?

**Mechanism:** each seller picks weekly price from a fixed discrete set (e.g., {price × 0.8, price × 0.9, price × 1.0, price × 1.1, price × 1.2}) using a standard bandit algorithm (e.g., epsilon-greedy or UCB) on weekly profit as reward. No buyer-class or environment information is used — this is deliberately context-blind, to isolate what pure trial-and-error optimization contributes before context is added.

**Acceptance criteria:** compare profit/participation/class-shares against 7a over the same 3 seasons (66 weeks), same seeds. Graduate to 7c only if the improvement clears the pre-agreed threshold.

**Literature basis:** Robbins (1952), "Some Aspects of the Sequential Design of Experiments" (*Bulletin of the AMS*) — origin of the multi-armed bandit problem.

**Exit condition:** `git tag phase7b-validated`.

### Phase 7c — Contextual Bandit with a Learned Representation

**Research question:** Does giving the bandit a *learned* compressed representation of market state (rather than hand-designed features) improve pricing decisions further — and is representation learning actually necessary here, or would hand-designed context features do just as well?

**Mechanism:**
- Define a "market state" each week: recent buyer arrival mix, recent visibility/promotion status, recent inventory trajectory.
- **Representation learning step:** rather than hand-picking which of these features matter, learn a low-dimensional embedding of the market-state history (e.g., a simple autoencoder or PCA over the accumulated weekly state vectors) and feed that embedding to the bandit as context, instead of raw hand-engineered features.
- The bandit becomes a contextual bandit (e.g., LinUCB) conditioned on this learned embedding.

**Required comparison (this is the actual research deliverable, not just "does it run"):** run the same contextual bandit with (i) the learned embedding vs (ii) a hand-designed feature vector of the same dimensionality. If the learned representation does not outperform the hand-designed one, that is a valid and useful finding — document it rather than assuming representation learning must help.

**Acceptance criteria:** report profit/participation/class-share deltas for both context variants against the 7b baseline.

**Literature basis:** Li, Chu, Langford & Schapire (2010), "A Contextual-Bandit Approach to Personalized News Article Recommendation" (LinUCB, *WWW*) — contextual bandit algorithm. Bengio, Courville & Vincent (2013), "Representation Learning: A Review and New Perspectives" (*IEEE TPAMI*) — basis for learning a compressed market-state embedding rather than relying on hand-designed features.

**Exit condition:** `git tag phase7c-validated`.

### Phase 7d — Reinforcement Learning (multi-week credit assignment)

**Research question:** Does optimizing for cumulative multi-week reward (rather than 7a–7c's single-week-ahead reward) change pricing behavior or outcomes — e.g., does an RL seller learn to sacrifice short-term profit for longer-term buyer loyalty?

**Mechanism:** replace the bandit's single-step reward with a standard RL setup (e.g., simple Q-learning or policy gradient) where the state includes the Phase 7c representation and the reward is accumulated over a multi-week horizon rather than the current week alone.

**Acceptance criteria:** compare against 7c on the same metrics, plus a new one: does the RL seller exhibit any short-term-profit-sacrificing behavior visible in the weekly trajectory (e.g., temporarily under-pricing to build loyalty before raising prices)? This is the qualitative signature that would justify RL's added complexity over 7c.

**Literature basis:** den Boer & Zwart (2015), "Dynamic Pricing and Learning with Finite Inventories" (*Operations Research*) — directly addresses learning-to-price under a finite-inventory constraint, matching this project's seller setup.

**Exit condition:** `git tag phase7d-validated`. If none of 7b–7d clear their graduation threshold over 7a, the project should explicitly adopt 7a as the standing baseline for Phase 8 onward and record that as a finding, not treat it as a failure.

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

## Phase 9 — Synthetic Agent Users

**Research question:** What does replacing the rule-based decision function with an LLM-driven Agent change, holding the rest of the Phase 8 simulation fixed? This is a scaffolding phase, not yet a human comparison.

**Single changed dimension:** decision function for a subset of buyers only — **N = 30 buyers (30% of the 100-buyer population)** run as Agents, the remaining 70 stay rule-based as the control group within the same run.

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

**Exit condition:** `git tag phase9-validated`.

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
