# Buyer reference-policy audit

*Written before any code change, at commit `52301b3`, with the full suite
green (358 passed). Nothing in this document has been implemented.*

The question put to this audit: the buyer "ground truth" is a hand-written
rule, and the project has been treating it in places as though it stood in for
human behaviour. This is an inspection of what that rule actually is, what in
it is grounded and what is invented, which results depend on which, and what a
literature-grounded replacement would have to look like.

---

## 1. The exact current buyer decision process

It is **not a discrete-choice model.** It is a sequential search-and-accept
scan, and every property below follows from that.

```
each week:
  attends ~ Bernoulli(attendance_prob[class])              # Phase 6+
  if not attends:  no decision is made at all
  visit_order <- uniform random permutation of all slots   # redrawn each week
  for stall in visit_order:
      skip if slot empty / stall closed                    # not counted a decline
      skip if visibility_draw >= visibility_prob[stall]     # Phase 3+, "not noticed"
      U = intercept                                         # 1.0
          - alpha[class] * (price / price_reference)        # market-wide reference
          + preference_coef * preference[buyer, stall]      # 1.5 * U(0,1), per season
          + budget_coef * (budget_remaining - price)        # 0.05, optional arm
          - budget_cliff_penalty  if (budget_remaining - price) < gap   # Phase 5
          + loyalty_bonus                                   # Phase 6+
      p = sigmoid((U - sigmoid_offset) / tau)               # offset 2.0, tau 1.0
      wants = p > purchase_draw[buyer, stall]               # independent draw per pair
      if wants and price <= budget_remaining and inventory > 0:
          buy ONE unit;  budget -= price;  inventory -= 1
      # the walk continues: the buyer may buy again this week
  choice_of_week <- stall with most units, ties to first encountered
  loyalty <- rho*loyalty + (1-rho) * 1{bought there this week}    # per pair
```

`src/market_sim/engine.py:148` (`purchase_probability`),
`engine.py:690-806` (the walk), `engine.py:810-836` (loyalty update),
`engine.py:435` (`_choice_of_week`).

### Six properties, each a modelling commitment

**1. There is no outside option and no normalisation.** `P(buy at j)` is an
independent Bernoulli per stall. The probabilities across stalls sum to
nothing in particular. "Bought nothing" is the product of independent
rejections, not a modelled alternative with a utility.

**2. There is no substitution in the probability.** `p_j` reads only stall
*j*'s price, this buyer's preference for *j*, loyalty to *j*, and the budget
remaining. **Adding a stall cannot lower any other stall's probability.**
Competition enters only through three back doors: budget depletion, inventory,
and walk order.

**3. Weeks are multi-unit.** Measured (v2 cell, seed 0, 66 weeks), stalls
bought from in one week: `{1: 3647, 2: 583, 3: 206, 4: 2}` — **17.8% of
purchase-weeks involve more than one stall.**

**4. Walk order is a first-order effect, not a tiebreaker.** The budget buys
**1.24–1.67 units** on average across configurations. The first affordable
stall the buyer accepts therefore usually exhausts the budget — and *which*
stall that is, is decided by a uniform random permutation rather than by
relative attractiveness.

**5. The budget constraint is the dominant mechanism.** Share of declined
encounters, measured:

| config | budget | utility draw | not noticed | did not shop | inventory |
|---|---|---|---|---|---|
| Phase 1 | **55.9%** | 44.1% | — | — | 0.0% |
| Phase 2 | **61.2%** | 38.8% | — | — | 0.0% |
| Phase 6 | **40.2%** | 22.0% | 17.9% | 19.9% | 0.0% |
| Phase 7a | **40.7%** | 22.3% | 18.2% | 18.9% | 0.0% |

The hard affordability test blocks more encounters than the utility draw in
every configuration. **Inventory never binds once.**

**6. Preference dominates price.** Utility swing by term:

| config | price | preference | budget term |
|---|---|---|---|
| Phase 1 | **0.000** | 1.500 | 0.000 |
| Phase 2 / 7a | 0.783 | **1.500** | 0.550 |

In **Phase 1 the price coefficient does nothing at all** — every seller posts
3.0, so `-alpha*(p/ref)` is the constant −0.500 at every stall. The only thing
varying across stalls in Phase 1 is the preference draw.

---

## 2. Ad hoc versus literature-grounded

| component | status | note |
|---|---|---|
| logistic form `sigmoid(U − offset)` | **form grounded, application not** | binary logit is standard; applying it independently per alternative on a multi-alternative occasion, with no outside option and no normalisation, is not the standard discrete-choice treatment |
| `intercept = 1.0`, `budget_coef = 0.05`, `preference_coef = 1.5`, `sigmoid_offset = 2.0` | **ad hoc** | `config.py:90-98` states them with no provenance, no source and no calibration. They are chosen numbers |
| `− alpha * (price / price_reference)` | **convention, documented** | the market-wide reference is a deliberate guard against a real bug (dividing by the stall's own price collapses the term). But dividing by a constant is just a rescaled linear price term — it is **not** a reference-price behavioural model in the sense of Winer (1986), which uses a *remembered or expected* price |
| `preference[buyer, stall] ~ U(0,1)` | **structurally grounded, distributionally ad hoc** | this is a **random brand intercept** — the project already has a random-coefficients structure. But mixed logit uses normal/lognormal; Uniform(0,1) is a choice with no source |
| `budget_coef * (budget − price)` | **ad hoc, and near-inert** | swing 0.55 against preference's 1.5; the *hard* affordability test is what actually does the work (property 5) |
| budget cliff (Phase 5) | **grounded** | cited to Kahneman & Tversky (1979); a reference-point effect a linear term cannot express |
| attendance probability (Phase 6) | **grounded** | purchase incidence, standard since Bucklin & Gupta (1992) |
| visibility (Phase 3) | **grounded in kind** | a consideration-set stage (Roberts & Lattin 1991); implemented as an independent Bernoulli per pair, which is the simplest version |
| loyalty M1 — `gamma * min(streak, cap)` | **ad hoc** | a capped streak counter. The cap is set so the maximum bonus equals `preference_coef` — a calibration decision recorded in the code, not a literature quantity |
| loyalty M2 — `L <- rho*L + (1-rho)*I` | **form faithful, indicator not** | see below |

### The loyalty deviation, measured

The v2 stock reproduces Guadagni & Little (1983) in form. **The indicator is
not theirs.** G&L's is `I(Y_{i,t−1} = j)`: the brand chosen on the previous
*purchase occasion*, exactly one per occasion — so `sum_j L_ij` is conserved at
1 and the stock is a normalised state. Here the indicator is "bought from *j*
this week", and a buyer can buy at several stalls, so mass is not conserved.

Replaying the accrual over 66 weeks at `rho = 0.5`:

| | per-buyer `sum_j L_ij` |
|---|---|
| Guadagni & Little | **1.000 exactly** |
| this implementation | min **0.093**, median **0.853**, max **2.290** |

This is not cosmetic. The utility bonus is `gamma * L`, so a buyer holding
mass 2.29 receives a larger *total* loyalty bonus than one holding 0.09 —
something G&L's normalisation makes impossible. Any claim that the simulator's
loyalty "is Guadagni–Little" needs this caveat attached.

---

## 3. Which Phase 1–11 results depend on these choices

### Immune — human data only, would not move

- **Phase 10** headline: B0 0.1256 / B1 0.0404 / Agent 0.2448, all four
  mechanism contrasts, the withdrawn 3.4× claim, the split-parity correction.
- **Phase 11** entire bias map, all four corrections, the permutation test.
- **loyalty_v2 Gate A1 / A2a / A2b** — the human admissibility bracket and the
  human lag profile.

These touch no simulator rule. A migration cannot change them.

### Partially exposed — simulator loyalty against human data

- **Phase 10 S arm** (simulator on the households' own choice sets, −0.005
  nats; free-running arm).
- **loyalty_v2 Gate B, B3, C** — including *"two of five conclusions turn on
  the representation"*, which is already a statement about this exact
  sensitivity.

### Fully exposed — the rule generates the world

Phase 1 mechanics · Phase 3 visibility · Phase 4 promotions · Phase 5
additive-vs-replace · Phase 6 memory (0.425 vs 0.316) · Phases 7a–7e including
*"31% of a gain known to exist"* · Phase 9a–9c distillation and drift ·
Phase 9d slope 0.954, intercept −0.219, 71.6% recovery, class bias
+0.121 / −0.063.

**Two are at materially higher risk than the rest:**

- **Phase 2, "73% of stratification is budget, not price sensitivity."** This
  decomposes exactly the two channels whose relative strength the architecture
  fixes by construction — a hard budget test that blocks 61% of encounters
  against a price term with swing 0.78. Under a normalised choice model with
  budget constraining the *choice set*, this number is not merely uncertain,
  it is measuring something different.

  **The project already diagnosed half of this and wrote it down.**
  `docs/phase_specifications.md:332` records that Poor's exclusion from the
  premium tier is *"an affordability wall … it would produce the same 0.000
  with alpha set to 0"*. That is the same mechanism this audit is describing,
  caught once, in one cell, and correctly caveated there. What the audit adds
  is that it is not confined to that cell — it is the architecture.
- **Phase 8, "the premium tier was competed out."** Entry and exit respond to
  profit, which responds to demand — and under the current model **sellers do
  not substitute at all**. Whatever competed the premium tier out, it was not
  buyers switching on relative utility. This result most needs re-running.

### A fourth exposure the phase table does not show

The Agent is asked **two different questions** in the two tracks:

| track | system prompt | task |
|---|---|---|
| controlled (Phase 9, 9d) | `agent.SYSTEM` | *"percentage chance this shopper buys one unit at this stall right now"* — **per-stall Bernoulli** |
| empirical (Phase 10, 11) | `agent.CHOICE_SYSTEM` | *"percentage chance it picks each brand … four integers summing to 100"* — **multinomial choice** |

Each matches its own ground truth faithfully. But it means the two tracks do
not merely have different oracles — **they pose different decision problems to
the model.** That is the deepest reason the tracks cannot currently be bridged,
and the strongest single argument for the migration.

---

## 4. Proposed formulation

**The unit becomes the purchase occasion, not the weekly stall-scan.** A week
contains one or more occasions; at each, the buyer makes one choice from a
constrained set including an explicit outside option.

**Choice set.** At occasion *t*, buyer *i* faces

```
C_it = { j : active_j and inventory_j > 0 and price_j <= budget_it and noticed_ijt }  u  {0}
```

Budget and inventory **constrain the set**; they are not utility penalties.
Visibility keeps its Phase 3 role as a consideration filter. Alternative `0` is
the outside option — buy nothing at this occasion.

**Systematic utility.**

```
V_ijt = beta_brand_ij                      # random intercept, replaces preference[b,s]
      + beta_price   * (price_jt / price_reference)
      + beta_promo   * promo_jt
      + beta_loyalty * L_ijt
      + beta_tier    * 1{premium_j}
V_i0t = beta_outside                        # normalised: the outside option's scale anchor
```

**Choice probability.**

```
P(j | s_it) = exp(V_ijt / tau) / sum_{k in C_it} exp(V_ikt / tau)
```

`tau` keeps Phase 9b's temperature role and stays 1.0 by default.

**Loyalty, corrected to the literature.**

```
L_ij,t+1 = rho * L_ijt + (1 - rho) * 1{choice_it = j}
```

The indicator is now over a **choice occasion with exactly one winner**, so
`sum_j L_ij` is conserved — which is what makes it Guadagni & Little rather
than an accumulator that resembles it. `L_ij0 = 1/|C|`.

**What this preserves:** heterogeneous buyers (β_brand is per buyer-seller,
β_price per class), multi-unit weeks (several occasions), the Phase 5 cliff
(retained as an optional utility term on the outside option, where a
reference-point effect belongs), temperature, and the CRN draw-order
discipline.

**What it deliberately removes:** the independent per-stall Bernoulli, the
walk-order-as-allocator, and the unnormalised loyalty accumulator.

### Benchmark tiers

| tier | policy | status |
|---|---|---|
| **A `legacy`** | the rule above, byte-identical | default; all Phase 1–11 results reproduce under it |
| **B `canonical_memoryless`** | MNL + outside option, no state | new |
| **C `canonical_stateful`** | B + Guadagni–Little loyalty | new |
| **D `empirical`** | B/C structure, parameters estimated from panel data | **unavailable — raises `NotImplementedError`.** Nothing is to be reported from it until estimation is actually run |

Structure is literature-grounded; **parameter values are controlled
experimental settings and must be documented as such, never as empirically
validated.**

---

## 5. Files that would change

| file | change | risk |
|---|---|---|
| `src/market_sim/policy.py` | **new** — the four tiers behind one interface | none, additive |
| `src/market_sim/engine.py` | occasion loop alongside the stall-scan, selected by `cfg.buyer_policy_tier`; legacy path untouched | **highest.** The walk is 120 lines entangled with CRN draw order, blocked-reason accounting and encounter recording |
| `src/market_sim/config.py` | `buyer_policy_tier`, the β block, `beta_outside`, `occasions_per_week`; defaults set to `legacy` | low if defaults hold |
| `src/market_sim/agent.py` | a choice-format prompt for the controlled track, so both tracks pose the same question | medium — **changes Phase 9d's task**, so 9d must be re-run, not translated |
| `src/market_sim/acceptance.py` | criteria that assume a per-encounter probability | medium |
| `src/market_sim/human.py` | expose panel data in the same choice-set shape the new policy consumes | low |
| `experiments/phase12_policy_complexity/` | **new** — the ladder in §6 | none |
| `tests/test_policy_tiers.py` | **new** | none |
| `tests/` (5 files touching the rule) | legacy-reproduction assertions | low |
| `docs/phase_specifications.md`, `README.md` | terminology; the two-track framing | none |

---

## 6. Backward-compatibility risks

1. **CRN draw order is load-bearing and fragile.** `engine.py:205` documents
   the order (preferences → visit orders → purchase draws) because paired
   comparisons across arms depend on it. An occasion loop draws a *different
   number* of randoms per week. **Mitigation: the new tier must consume its own
   RNG stream, seeded separately, so legacy draws are bit-identical.** This is
   the single largest risk of silently invalidating historical results.

2. **`price_reference` is computed at config time** (`config.py:267`) and
   assumes a market-wide constant. Under MNL, price enters a normalised
   comparison and the reference changes meaning. Legacy must keep its own.

3. **Blocked-reason accounting has no analogue.** `budget_exhausted` vs
   `utility_draw` is a distinction the scan makes and a choice model does not —
   under MNL, an unaffordable stall is simply absent from the set. Several
   acceptance criteria read these counters. They need per-tier definitions,
   not a translation.

4. **Phase 9d's task changes.** A Bernoulli prompt and a choice prompt are not
   comparable. Its numbers must be **re-run under the new tier and reported
   beside the old ones**, never rescaled.

5. **Encounter records feed Phase 9a's distillation.** `ENCOUNTER_FIELDS` is a
   per-encounter schema. A choice model produces per-occasion rows with a
   variable-size set. The distilled student would need retraining, so Phase 9's
   drift results are re-run, not carried.

6. **`experiment_log.csv` must not be rewritten.** New tiers log new rows with
   a `policy_tier` column; historical rows keep their commit binding.

7. **The empirical tier is the tempting one.** Leaving `D` raising
   `NotImplementedError` is a deliberate guard: a plausible-looking set of βs
   sitting in config is exactly how "controlled parameters" quietly becomes
   "estimated from human data" in a later README edit.

---

## 7. Is MNL the right model here?

**Short answer: MNL is the right tier B, mixed logit is the right tier C, and
nested logit should be avoided for now. But there is a data asymmetry that
matters more than the choice between them.**

**MNL is exactly right for the empirical track.** Guadagni & Little (1983) —
already cited by this project for the loyalty term — *is* an MNL on scanner
panel data with a loyalty covariate. The panels have 4 alternatives and exactly
one chosen on every occasion (verified: 3,289 of 3,289 for Cracker). This is
the data structure MNL was written for.

**MNL's IIA is not innocuous for the simulator.** IIA says removing a premium
stall redistributes its share proportionally over all survivors, budget stalls
included. Phase 8's headline — *"the premium tier was competed out"* — is a
statement about precisely that substitution pattern. Adopting plain MNL would
impose an answer to the question Phase 8 asks.

**The project already has random coefficients, so mixed logit is not an
escalation — it is a more faithful translation.** `preference[buyer, seller] ~
U(0,1)` is a random brand intercept and `alpha` varies by class. Keeping that
draw as `beta_brand_ij` gives a random-coefficients logit essentially for free,
and it **relaxes IIA**, which turns "do premium stalls compete with each other
more than with budget stalls?" from an assumption into something measurable.

**Nested logit is the wrong starting point** even though the premium/budget
tiers look like an obvious nest: choosing the nest *imposes* the substitution
structure, and that structure is the object of study.

### The asymmetry that constrains the whole design

**The human panels are conditional on purchase and contain no outside option.**
Verified above: every occasion has 4 alternatives and exactly 1 chosen. The
simulator, by contrast, needs an outside option — not buying is a frequent and
meaningful outcome.

So an MNL-with-outside-option simulator and an MNL-without-one panel model are
**not the same model**, and a bridge that ignores this compares a 5-alternative
distribution against a 4-alternative one. Two defensible resolutions:

1. **Two-stage incidence-then-choice** (Bucklin & Gupta 1992): model
   *whether* a purchase happens and *which brand* separately. The simulator
   gets both stages; the panel identifies only the second. Comparisons are made
   stage-matched.
2. **Restrict the bridge to conditional-on-purchase.** Compare
   `P(j | bought something)` on both sides and state plainly that purchase
   incidence is out of scope for the bridge.

**Recommendation: (1), with (2) as the fallback if incidence proves
unidentifiable.** (1) is the literature-standard decomposition and it makes the
outside option a modelled object rather than a mismatch to be argued around.

---

## What this audit does not settle

Whether the migration is worth its cost. The honest accounting: Phases 10, 11
and Gate A survive untouched; Gates B/B3/C and Phase 10's S arm need re-running
against a corrected loyalty stock; and roughly nine phases of controlled
results would have to be re-run to be quotable under the new tier. That is the
bill. It buys one thing the project cannot currently get at any price — **two
tracks that pose the same decision problem, and therefore a defensible bridge
between them.**
