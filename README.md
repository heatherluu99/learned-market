# Millbrook Market

**A synthetic consumer market built to find out when a simulated buyer or seller
can be trusted — and, more often, when it cannot.**

Agent-based simulations of consumer behaviour are easy to build and hard to
believe. Add a mechanism, watch a number move, declare an insight. The number
moves because you added the mechanism. This project is an attempt to do the
opposite: every phase states a question **before** it is run, states what result
would count as a failure, and reports the answer even when the answer is *no*.

Nine of the twenty-five logged experiments returned a null. Those are the ones
worth reading.

---

## Headline results

| Phase | Question | Answer |
|---|---|---|
| 2 | Does buyer heterogeneity produce stratification? | **Yes**, gap +0.088 CI [+0.053, +0.124] — but **73% of it is budget, not price sensitivity** |
| 3 | Does the environment re-sort buyers across tiers? | **No.** Position moves sales *within* a tier; class→tier shares don't move |
| 5 | Does a nonlinear budget cliff change conclusions? | **No** — 1.6 pp, equivalent. The model rolls back to linear |
| 6 | Does memory change behaviour? | **Yes**, pair stability 0.425 vs 0.316. But the control is 0.316, not 0 |
| 7b | Does a bandit beat a hand-written rule? | **Yes**, +10.3% profit — **and moves no class share at all** |
| 7c | Does market state predict the best price? | **No.** Skipped on the evidence rather than run |
| 7d | Does a multi-week horizon add anything? | **No**, −1.3% CI [−2.8%, +0.1%], equivalent |
| 7e-2 | Can *any* schedule beat the best standing price? | **Yes**, +2.6% — and the δ=0 control **loses money** |
| 7e-3a | Does conditioning on loyalty state pay? | **No**, −2.3%. An oracle says there is nothing to condition on |
| 7e-3b | Can a learner find a trade-off known to exist? | **Partly** — right shape, right depth, half the duration, **31% of the gain** |
| 8 | Does macro structure emerge from micro interaction? | **Yes** — premium tier eliminated, no rule ever reads a class label |
| 9a | Does one-step imitation fidelity survive closed-loop deployment? | **The loop is real and does not compound** — +0.0057 CI excludes zero, at 1.07× |
| 9b | Does teacher entropy govern whether it compounds? | **Yes for amplification** — Spearman −1.00, 1.02×→1.67×. **Not yet for behaviour** |
| 9c | Which environment characteristic suppresses divergence? | **Neither — persistence *carries* it.** Removing season-long taste kills amplification outright |

Full detail: [`docs/phase_specifications.md`](docs/phase_specifications.md).
Every run: [`experiment_log.csv`](experiment_log.csv), or the self-contained
[Experiment Explorer](viz/experiment_explorer.html).

---

## The problem

Synthetic consumers are being sold as a replacement for survey panels. The
pitch is cheap, fast, scalable. The unanswered question is **when the synthetic
answer is wrong in a way that flips a decision**, and nobody can answer it by
looking at a simulation that was only ever compared to itself.

Three failure modes this project is built to catch:

1. **Encoded results.** A model that produces stratification because
   stratification was written into its rules. Distinguishing that from
   stratification that *emerges* requires the rules to be auditable, and the
   audit to be a test rather than a claim.
2. **Mechanisms that pay for themselves in the metric that motivated them.**
   Add loyalty, measure loyalty, find loyalty. The control arm is the whole
   discipline.
3. **Complexity that is added because it is available.** LLM agents, deep RL,
   contextual bandits — each is worth having only if a simpler thing has been
   shown to fail first.

## The solution: a ladder with gates

Sixteen phases, each changing **exactly one** dimension — behavioural,
environmental, or population — against the phase before it. Nothing advances
until the current phase's pre-registered criteria are met.

Four rules do most of the work:

**Pre-registration.** The question, the mechanism, and the acceptance criteria
are committed to `docs/phase_specifications.md` *before* the implementation, as
their own commit. When a criterion later turns out to be broken, the correction
is committed with its reason rather than edited silently — the repository
contains a gate whose threshold was arithmetically unreachable, and the commit
that says so.

**Equivalence testing, three verdicts.** A confidence interval wholly inside a
materiality margin is `equivalent`; wholly outside is `material`; straddling it
is `inconclusive` — a failure to measure, not a finding. Margins are ±5
percentage points for shares and ±5% relative for profit. **What is graded is
that a verdict is reached, not which verdict it is.** An `inconclusive` result
is answered with more seeds, never a softer threshold.

**Common random numbers.** All randomness is drawn up front, in a fixed order,
at fixed width. New draws are appended *last*, so every earlier phase stays
bit-identical — Phase 1's participation rate has been 0.8216666666666667 to
twelve decimals across sixty commits and eight mechanism additions. Phase 8
allocates 40 fixed seller *slots* and draws at slot width regardless of
occupancy, so two arms whose entry histories diverge still consume the same
stream and remain paired.

**Held-out evaluation.** Anything fitted is evaluated on seeds it never saw.
Anything *selected* — a schedule chosen from 36, a hyperparameter chosen from
4 — is selected on a discovery block and tested on a disjoint one, because a
maximum over ~150 comparisons is significant by construction.

---

## World state and observability

The engine holds a complete world state; **no agent sees it.** What each agent
observes is a deliberate, tested restriction.

### The world

| | persists across weeks | resets weekly |
|---|---|---|
| buyer | `last_seller`, loyalty streak / stock, fixed preference | budget |
| seller | posted price, capital, firm identity, active/inactive | inventory |
| market | the seller set (Phase 8), week index | promotion lottery |

`preference[b, s] ~ U(0,1)` is drawn once per season: taste is a property of a
buyer, not a per-week coin flip. Budgets are drawn per seed with within-class
lognormal dispersion, `μ = ln(mean) − σ²/2`, `σ = 0.12` — before this, every
"heterogeneous" buyer inside a class was identical and the population was three
points rather than a distribution.

### Buyer observability

A buyer evaluating a stall sees **only**: the posted price, its own remaining
budget, its own preference for that stall, and its own loyalty toward it. It
does not see other buyers, other stalls' sales, seller costs, or the future.
Whether it sees a stall at all is gated by

```
visibility_prob = 0.5 + 0.5 · position_score
```

An unnoticed stall is recorded as `not_noticed`, never as a declined purchase —
a buyer who never saw a stall has expressed no preference about it.

### Seller persona and its observability

A seller's policy sees a strictly self-referential state:

```python
{ "loyal_fraction",    # share of buyers currently attached to *this* seller
  "loyalty_stock",     # mean loyalty bonus its own buyers hold toward it
  "last_arm",          # its own previous price
  "last_profit",       # its own previous profit
  "season_fraction" }  # how far into the season
```

**No rival's price, no rival's sales, no market aggregate.** This is pinned by
a test that fails if any other key appears. Phase 7c established there is no
external market state worth conditioning on; giving a policy one anyway would
add parameters without adding information.

### The audit that makes "emergent" mean something

Phase 8's entry and exit rules never read a class label. That is not asserted —
it is tested by **swapping the tier names while holding every numeric parameter
fixed and requiring a bit-identical run**: same entries, same exits, same
profits, to the last slot. What that establishes is exactly *label-invariance*.
It does **not** establish that the outcome is independent of the
parameterization, and the spec keeps the two separate:

| | is this result that? |
|---|---|
| label-encoded outcome (a rule reads a class and acts on it) | **no** |
| parameter-induced endogenous selection | **yes** |

---

## Actions, learning, and transitions

### The action space

A seller's action is a **price arm** — a multiplier on its own list price,
`{0.8, 0.9, 1.0, 1.1, 1.2}`. Schedules, bandits and the Q-network all act
through **one interface**, the engine's policy hook `(seller_id, state) → arm`,
so a hand-written schedule and a trained network enter the market through the
same door and neither can see anything the other cannot.

A buyer's action is binary per stall visited: buy or don't.

### Utility and purchase

```
U(b, s) = intercept
        − α_c · (price / price_reference)          price, normalized market-wide
        + 1.5 · preference[b, s]                    taste
        + 0.05 · (budget_remaining − price)         liquidity
        − 1[budget_remaining − price < gap] · pen   Phase 5 cliff
        + loyalty_bonus                             Phase 6 / 7e

P(buy) = σ( U − offset )
```

`price_reference` is **the highest posted price in the phase's configuration**,
computed once and frozen — not the buyer's budget (which double-counts the
liquidity term) and emphatically not the stall's own price (which collapses the
ratio to 1.0 and deletes the price term entirely). It stays frozen through
Phase 7's learned pricing and Phase 8's entry and exit, because a normalizer
that drifts with the mechanism under test makes the utility scale a function of
the result.

### Loyalty: a counter, then a stock

Phases 6–7d use a bounded streak counter. Phase 7e replaces it with a per-pair
**stock** — the change that the whole of Phase 7e exists to test:

```
purchased:  L[b,s] ← ρ·L[b,s] + β·max(0, 1 + δ·(1 − p_paid/p_list)/A)
otherwise:  L[b,s] ← ρ·L[b,s]
bonus:      L_max · tanh( L[b,s] / L* )
```

`δ` is the **investment channel**: it makes a discount buy something that
outlives the week. With `δ = 0` a purchase is a purchase whatever it cost, and
the only reason to cut price is this week's demand — which is precisely the
myopic problem a bandit already solves.

### Seller learning, in four rungs

| rung | rule |
|---|---|
| 7a heuristic | keep moving the price the way it moved while profit improves; reverse when it stops. Acts only on a change larger than its own recent noise |
| 7b bandit | UCB1, `argmax( v̄_a + c·√(2 ln t / n_a) )`, and ε-greedy. Every arm swept once first |
| 7e-3a contextual | LinUCB, one ridge model per arm over `[1, loyalty_stock, season_fraction]` |
| 7d / 7e-3b RL | Q-network on a 10-week discounted return, `target = r + γ·max_a' Q(s', a')`, `γ = 0.9` |

Profit, the reward, had to be **defined** before any of this — Phases 1–6 have
no cost model and "exit if profit is below threshold" was unimplementable:

```
profit = revenue − unit_cost · units_sold − fixed_weekly_cost
```

### Transitions and entry/exit

Phase 8 makes the seller set itself endogenous:

```
exit  (capital): capital ← capital + profit;  exit when capital ≤ 0
exit  (streak) : exit after 3 consecutive losing weeks
entry          : after 2 consecutive weeks of mean profit > 0, one entrant
                 copies a randomly chosen incumbent's price, position and
                 inventory — reading profit, never a class label
```

Both exit rules are run, because a modelling choice with a fourfold effect on
turnover turned out to have only a modest effect on structure — and that is
only visible because both were run.

---

## Phase-by-phase

### ✅ Phases 1–6 — mechanics, heterogeneity, environment, context, nonlinearity, memory

**Phase 1** pins the engine: participation 0.822, inventory never binds, budget
binds 3,961 times. A deliberate inventory-pressure arm drops participation to
0.733 on identical seeds, proving inventory *can* bind when scarce.

**Phase 2** finds stratification — Rich−Middle gap to the premium tier **+0.088,
CI [+0.053, +0.124]**. The diagnostic arm is the finding: equalizing price
sensitivity shrinks it to +0.065, so **≈73% of stratification is budget alone**.
"Heterogeneity produces stratification" holds; the narrower "price sensitivity
produces stratification" mostly does not. Poor's premium share is 0.000 by an
**affordability wall** — budget 3 against price 6 — not by preference.

**Phase 3** adds visibility. Position moves sales strongly *within* a tier and
class→tier sorting does not move (Middle +0.0000, CI [−0.0201, +0.0202]). The
largest effect is a participation drop of −0.065.

**Phase 4** adds promotions. The effect is an **interaction, not a level
shift**: lift concentrates in the lowest-budget class that can afford the
discounted price. Poor's lift at a discounted premium stall is ~0 by
arithmetic — 6 × 0.7 = 4.2 still exceeds a budget of 3.

**Phase 5** adds a budget cliff, in both readings of an ambiguous spec. Largest
share shift **1.6 pp / 2.1 pp, both equivalent → the model rolls back to
linear.** This phase's materiality test is reused at 7b–7e.

**Phase 6** makes weeks real. Pair stability **0.425 with memory against 0.316
without** — and the control's level is the result: unequal popularity and
season-long fixed preference produce stability with no memory at all. Path
dependence is a pre-registered **null**.

### ✅ Phase 7 — seller learning, and two nulls that trace to one line

7a's heuristic lifts profit 48.4 → 60.9. 7b's bandit reaches 66.0 (+10.3% over
7a) **while moving no class-to-tier share at all** — more profit, identical
market structure.

**7c was skipped on evidence.** The profit-maximizing arm is 2.60 under every
observable weekly condition tested, and the profit curve shifts in level
without changing shape. A contextual bandit conditions the *estimate* of reward
and cannot change a decision that context does not move. The diagnostic is
committed; the skip is a result.

**7d returned its pre-registered null**: −1.3%, CI [−2.8%, +0.1%], equivalent.
And the pre-registered *signature* was itself defective — the myopic bandit
scored **higher** on week–price correlation (0.420 vs 0.304) than the RL agent,
because any learner climbing toward a better arm produces a rising price path.
Kept, with its defect recorded, rather than quietly replaced.

Both nulls trace to `loyalty_streak_cap = 3`: a bounded counter is not a stock,
so there is neither cross-sectional state to condition on nor an intertemporal
asset to invest in.

### ✅ Phase 7e — a second environment, built to make complexity necessary

Three existence gates, each licensing one level of policy complexity.

**Gate 1 — is there a state?** With lock-in strength *calibrated to equal* the
counter's (so a better result cannot come from stronger habit), the stock's
memory reaches **2.83× as far at a lag of 8 weeks**, and the counter's advantage
collapses at exactly its 3-week cap. Getting there cost two corrections, both
in the record: a gate whose threshold (5 pp below a 4.0% baseline) was
arithmetically unreachable, and a pinned ceiling that made the new mechanism
bind **a third as hard** as the one it was meant to enrich.

**Gate 2 — is there a trade-off?** Yes: *invest 16 weeks at 0.90×, then return
to the standing price* earns **+2.6%, CI [+2.0%, +3.2%]** on held-out seeds.
The δ ladder on the identical price path is the causal argument —
**−1.24% / +0.09% / +1.25% / +3.05%** — so with the investment channel off, the
same schedule *loses money*. What pays is **acquisition, not extraction**: every
schedule that ever charges above the standing price loses, the worst by 56%.

**Gate 3 — does complexity pay?**

- **Context: no.** −2.3%, CI [−3.0%, −1.5%], equivalent. An oracle diagnostic
  says why rather than leaving it ambiguous: across 460 seller-weeks split at
  the median loyalty state, the best arm is **1.00× on both sides**. A seller
  with a deeply loyal base and one without want the same price.
- **Horizon: partly.** The Q-network prices at **2.379** over weeks 0–7 against
  the hand-found schedule's **2.385** — it located the investment at almost
  exactly the right depth — then returns to the standing price at week 8 where
  the schedule holds to 16. It spends 75% of the discount and collects **31% of
  the gain**. This is 7d's missing sacrifice-then-recover trajectory, appearing
  for the first time, and still not enough to pass.

**Phase 7e's answer: policy complexity became *valuable* without becoming
*learnable*.** The market structure that makes a sophisticated policy worth
having is not the structure that makes it findable.

### ✅ Phase 8 — endogenous market structure

Both halves of the originally registered mechanism were **inoperative**, found
by diagnostics run before any implementation code: exit would have fired on
week-0 arithmetic in 100% of seeds, and the unmet-demand entry trigger was
identically zero across 1,980 seller-weeks (no stall ever sold out).

Rebuilt, the market grows from 5 sellers to a fixed-cost-determined level —
**24.9 / 18.8 / 15.1 / 12.4** sellers at fixed costs of 6 / 8 / 10 / 12 — and
the premium tier is eliminated in all eight cells, from a 40% starting share to
essentially zero.

What settles is a **stochastic stationary structure, not an equilibrium.** In
the final season entry and exit both run at 0.10–0.47 firms a week, and under
the three-week rule only **48–62% of firms survive a season while the count does
not move**. `N ≈ 15` does not mean the same fifteen stalls.

**"Emergent" is meant narrowly.** The mechanism did not encode the outcome, but
*why* the premium tier loses was fixed at Phase 2 — 70% of buyers hold a budget
of 3.0 against a price of 6.0, and both tiers pay the same rent. The market
discovered what the population already made true.

### ✅ Phase 9a — learned buyer policy

The next rung, and the concept trap is pinned before any code. Training
trajectories come from **this project's own hand-coded buyer**, so a fitted
policy is *policy distillation of a simulator* — not learning of human
behaviour, which begins at Phase 10.

**The teacher is stochastic**, which decides whether any of its metrics mean
anything. Measured over 4,268 affordable decisions: mean `p = 0.578`, **83% of
decisions between 0.2 and 0.8**, mean binary entropy **0.938 of 1.0 bits**.
Consequently:

- the accuracy ceiling of *any* deterministic policy is **0.619** — a "62%
  accurate" classifier is perfect;
- a policy that recovers `p` exactly and samples scores **0.541**, *below* the
  argmax policy, while being the only one that reproduces the teacher;
- the argmax policy buys on 23.8% of decisions against the teacher's 40.9% — a
  **17.1 pp** aggregate error in the "more accurate" model.

So the metrics are distributional. And the project's shared `purchase_draw`
turns out to make the right metric the natural one: teacher and student differ
exactly when the shared uniform falls between their probabilities, so

```
1 − CRN-coupled agreement = E_s[ TV( π_T(·|s), π_θ(·|s) ) ] = E_s|p_T − p_θ|
```

— an expected conditional policy distance, not an accuracy.

The phase runs as **offline conditional fidelity → held-out calibration →
[gate] → closed-loop trajectory fidelity → state-distribution drift**, and its
hypothesis is:

> **High one-step conditional-policy fidelity does not guarantee closed-loop
> trajectory fidelity, because policy errors can endogenously shift the state
> distribution on which future decisions are made.**

Measurable here because the teacher is a *function* and stays evaluable on
states the student reached and the teacher never would have:

```
D_offline = E_{s∼d_T}     |p_T(s) − p_θ(s)|     can I imitate where the teacher goes?
D_shadow  = E_{s∼d_θ}     |p_T(s) − p_θ(s)|     do I still imitate where I go?
D(d_T, d_θ)                                     how far did I move the world?
```

**Result.** The gate passes — policy distance 0.0834 against a measured floor
of 0.0832, worst stratum calibration 0.0157. Deployed, `D_shadow` exceeds
`D_offline` by **+0.0057, CI [+0.0055, +0.0060]**: the same student really is
worse at imitating the teacher on the states *it* brings about. And the
amplification is 1.07×, the largest state drift a Wasserstein-1 of 0.0100, and
all six class-to-tier shares equivalent. **Under this stochastic teacher and
these stabilizing dynamics, imitation error produces measurable endogenous
distribution shift but not economically meaningful trajectory divergence.**

### ✅ Phase 9b — teacher entropy sweep

9a's conclusion names its conditions, so the next phase varies them. Sweeping
the teacher's logit temperature with the **market's purchase level held fixed**
— the offset re-solved at every temperature, or a sharper regime would be a
different market rather than a sharper one:

| `H(π_T)` bits | 0.98 | 0.93 | 0.76 | 0.46 | 0.19 |
|---|---|---|---|---|---|
| error / noise `R` | 9% | 18% | 31% | 47% | **85%** |
| amplification | 1.02× | 1.06× | 1.18× | 1.40× | **1.67×** |
| behavioural (pp) | 0.33 | 0.40 | 1.67 | 0.76 | 2.49 |

**Amplification and state drift are monotone in entropy at Spearman −1.00**,
with the excess growing 160-fold and every interval excluding zero. Every
regime's student clears Gate 9a against its own floor, so no point on the curve
is just an undertrained model.

**The fourth link is not reached**: behavioural divergence peaks at 2.49 pp
against a ±5 pp margin and all six shares stay equivalent everywhere. Teacher
stochasticity governs amplification and does not, alone, carry it into material
behaviour. What sits between them is the environment — **9c** ablates the budget
wall and the season-long preference draw to find out which of them absorbs it.

### ✅ Phase 9c — stabilizer ablation

9b left the environment as the missing link, so 9c removes its two candidate
stabilizers one at a time at the sharpest entropy, with the purchase level held
fixed. **The result reverses 9a's own framing.**

| | amplification | state drift | behavioural |
|---|---|---|---|
| low entropy, both stabilizers on | **1.67×** | 0.0883 | 2.49 pp |
| budget wall removed | 1.59× | 0.0250 | 1.75 pp |
| **season-long taste removed** | **1.00×** | 0.0053 | 0.38 pp |

9a called fixed preference a stabilizer that "pulls a wandering buyer back" and
predicted removing it would let divergence grow. Removing it **eliminates the
amplification entirely.** Compounding needs a **carrier**: an early error has to
move the buyer into a state that *persists* long enough to be inhabited. Redraw
taste weekly and there is no such state, so this week's deviation never reaches
next week.

Persistence stabilizes the trajectory *and* carries the error — one mechanism,
seen twice. And `R` alone does not govern amplification: the weekly-taste cells
have the **largest** systematic error in the study (116% against 85%) and
amplify by exactly 1.00×. So `amplification ~ R × state persistence`.

**Nothing across 9a–9c reached materiality.** The worst behavioural divergence
anywhere is 2.49 pp against a ±5 pp margin, and every class-to-tier share in
every cell returns `equivalent`. The mechanism has been isolated, its governing
quantity identified and its carrier found — and it has still never moved this
market by enough to change a decision.

### ⬜ Phases 9d–16

LLM agents (9d), human comparison (10), bias quantification (11), cross-model
robustness (12–13), decision reliability (14), reference-scale demonstration
(15), data flywheel (16). No human data enters before Phase 10, and nothing in
Phases 1–9 claims anything about human behaviour.

---

## Reproducing

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest -q                        # 299 tests
.venv/bin/python experiments/phase8/run_phase8.py    # any phase
.venv/bin/python tools/build_experiment_explorer.py  # rebuild the explorer
```

| path | |
|---|---|
| `docs/phase_specifications.md` | the pre-registered spec — every gate, correction and result |
| `src/market_sim/` | engine, config, acceptance criteria, bandits, RL |
| `experiments/phase*/` | one runnable script per phase |
| `results/`, `experiment_log.csv` | generated outputs, each bound to a commit hash |
| `viz/experiment_explorer.html` | every run, its figure, and the commits behind it |
| `project_tracking.pptx` | one tracking slide per completed phase |

Every logged run records the commit it ran at, and the log refuses a clean hash
if any source path is dirty.
