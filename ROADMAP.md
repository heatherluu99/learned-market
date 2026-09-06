# Market Simulation Project — Roadmap

## Vision

Build a commercially viable Agent-based synthetic consumer / market simulation
system for marketing research and consulting. The system progresses from a
pure rule-based transaction engine through LLM-driven Agents, human-vs-AI
behavioral gap quantification, cross-model robustness testing, to a
decision-reliability product backed by a self-reinforcing client feedback
loop.

Core philosophy: simple first, complex later. Linear first, nonlinear later.
Static first, dynamic later. Rule-based first, learning later. Interpretable
first, black-box later. Mechanism first, realism later. Validity first,
commercialization after validity. Change only ONE complexity dimension
(behavioral / environmental / population scale) per phase.

## Numbering note

This project uses a single unified **Phase 1–16** numbering. This is
equivalent to the "Level 1–16" experimental roadmap in the original design
philosophy, and supersedes the shorter Phase 0–8 ladder used in early
planning notes. Any older reference to "Phase 1" containing buyer
heterogeneity (L/H classes) refers to what is now **Phase 2** below — Phase 1
itself is intentionally homogeneous (see phase_specifications.md).

## Moat strategy (confirmed north star)

The foundation model itself (GPT, Claude, etc.) is not a defensible asset —
any competitor can call the same API tomorrow. The two assets we are
deliberately accumulating, which a same-day competitor cannot replicate, are:

| Priority | Asset | What it is | Why it compounds |
|---|---|---|---|
| **Primary** | **A — Human–AI Behavioral Gap Database** | Structured record of (scenario, demographic, context, model) → (human choice distribution, synthetic choice distribution, gap metric) | Requires real human data collection (surveys, panels, client transaction data). Slow and expensive to build; each engagement adds to a growing, non-public dataset. |
| **Primary** | **D — Decision-Reliability Track Record** | Per decision-type (pricing / segmentation / campaign / market-entry), a running estimate of P(major decision error), built from A plus real client outcomes | Functions like a credit/reliability rating. A new entrant has no history to point to — trust cannot be faked or copied. |
| Supporting | B — Calibration / correction methodology | Systematic function mapping raw synthetic output → corrected prediction, derived from A | Internal tooling that improves A/D; not the external sales pitch on its own (too easy to claim, hard to verify from outside, and not what clients actually buy). |
| Supporting | C — Cross-model reliability benchmark | Continuously updated map of which model families are accurate for which behavioral tasks | Feeds into D (e.g., cross-model disagreement as an early-warning signal for likely error) rather than being sold as a standalone product. |

**Practical consequence for phase design:** Phases 1–8 (pure simulation, no
Agent/LLM calls, no real humans) do not generate A or D directly — they are necessary
infrastructure, fully replicable by any competitor in a few weeks, and should
not be over-invested in for their own sake. Asset generation for A begins at
**Phase 10**, formalizes at **Phase 11**, and D crystallizes at **Phase 14**,
compounding through the client feedback loop from **Phase 15–16** onward.

Because of this, **logging schemas from Phase 1 onward must already include
placeholder fields** (`model_used`, `decision_type`, `human_benchmark_id`,
`synthetic_cost_usd`, `synthetic_latency_seconds`, etc., filled as `N/A`
until relevant) so that Phase 1–8 data merges cleanly with Phase 9+ data
later, rather than requiring a schema migration.

## Commercial viability constraint (cost & speed)

Alongside reliability (Asset D), the simulation must be demonstrably
**cheaper and faster than a real human research panel** — this is not a
side benefit but a required gate. From **Phase 9d** onward, every run logs
`synthetic_cost_usd` and `synthetic_latency_seconds`, compared against a
sourced `human_baseline.csv` reference table (industry figures for panel
cost/turnaround, introduced in Phase 9d). **Phase 15**'s reference-scale run
should still hold this ratio favorable, even without a real client
involved — see `docs/phase_specifications.md`, Phase 9d and Phase 15.

## Dual purpose: commercial roadmap + CS/generative-agent portfolio piece

This project also serves as a portfolio/demonstration piece in the
generative-agent / synthetic-user space. This does not change phase
sequencing or scientific discipline — it changes how much polish the **web
visualization** gets, and when. Specifically:

- The web visualization is introduced at **Phase 6** (not deferred to
  Phase 15) with real presentational quality (a research-tool-style page —
  see `docs/phase_specifications.md`'s Phase 6 section and the working
  prototype `market_bonds_prototype.html`), because it is expected to
  double as demo/portfolio material from early on.
- The same visualization artifact is **extended incrementally** at Phase 8
  (entry/exit panels) and Phase 9d (the "Agent Inspector" — see
  `docs/phase_specifications.md`), rather than rebuilt from scratch, so the
  finished demo tells a visible story of increasing sophistication —
  itself a differentiator versus a demo that jumps straight to a flashy
  end-state with no visible reasoning behind it.
- This does **not** license front-loading Agent/learning mechanics earlier
  than their assigned phases just to make the demo more impressive sooner —
  the discipline in the Vision section still applies; only the rendering
  quality of already-existing mechanics is prioritized earlier.

## Current phase

**Phase 9b complete; next is Phase 9c.** Every phase through 9b is tagged.

Phase 9a distilled the hand-written buyer into a policy that sees eight
observable columns and not the latent taste draw, and deployed it. The gate
passes: policy distance 0.0834 against a measured floor of 0.0832, worst
stratum calibration 0.0157, and 0.0264 of the 0.0474 available nats.

The closed-loop result is a directional confirmation and a quantitative
rejection. `D_shadow` exceeds `D_offline` by +0.0057, CI [+0.0055, +0.0060] —
the same student really is worse at imitating the teacher on the states *it*
brings about, so the mechanism exists and every link is measured. But the
amplification is 7%, the largest state drift is a Wasserstein-1 of 0.0100, and
all six class-to-tier shares return equivalent. **The loop is real and it does
not compound.**

The reason is quantitative: the teacher's per-decision noise has an sd of
0.475 against the student's systematic deviation of 0.083, so the bias is 17%
of the coin-flip the market already runs on. Compounding imitation error needs
a near-deterministic teacher — the regime a temperature-0 LLM agent occupies —
which makes this the axis Phase 9b sweeps.

**Phase 9b swept it, and the response curve is exact.** Holding the market's
purchase level fixed while teacher entropy falls from 0.98 to 0.19 bits, the
error-to-noise ratio rises 9% → 85% and error amplification rises 1.02× →
1.67× — Spearman **−1.00** against entropy, with the excess growing 160-fold
and every interval excluding zero. State drift is equally monotone.

**And the fourth link is not reached.** Behavioural divergence peaks at 2.49 pp
against a ±5 pp margin, and all six class-to-tier shares return `equivalent` in
every regime including the sharpest. Teacher stochasticity governs
amplification; it does not, alone, carry it through to material behaviour.
What remains between them is the environment, which **9c** ablates.

Phase 8's entry/exit dynamics selectively eliminated the premium tier — from
a 40% starting share to essentially zero in all eight cells — under this
population, these budgets and this cost structure. The disadvantage was not
created here: Phase 2 gave 70% of buyers a budget of 3.0 against a premium
price of 6.0, and both tiers pay the same rent. What Phase 8 supplies is the
selection mechanism that turns a standing fitness difference into a
composition.

The result is **emergent with respect to the decision rules, but conditional
on exogenously specified buyer affordability and seller economics**. Swapping
the tier names gives a bit-identical run, which proves the outcome is
label-invariant — no rule reads a class. It does not prove the composition is
independent of the parameterization, and that distinction is kept explicit.

Free entry endogenizes market size and the fixed cost strongly determines its
stationary level: 24.9 sellers at a cost of 6 down to 12.4 at 12. What settles
is a **stochastic stationary structure**, not an equilibrium — in the final
season entry and exit both run at 0.10–0.47 firms a week, and under the
three-week rule only 48–62% of firms survive a season while the count does not
move. The exit rule mainly changes turnover and convergence speed and changes
the long-run count only modestly, by about 15%. Phases 1–6 and 7a, 7b, 7d are
tagged validated; 7c is tagged `phase7c-skipped`; 7e-1 through 7e-3b are
tagged `phase7e1-calibrated`, `phase7e2-headroom`, `phase7e3a-context` and
`phase7e3b-horizon`.

Phase 7 answered its headline question in the negative, twice over. A
context-blind bandit beats the heuristic on profit (+10.3%) while leaving
every class-to-tier share where the heuristic had it, and a Q-network on a
ten-week discounted return finds nothing further (−1.3%, CI [−2.8%, +0.1%],
equivalent). Both nulls trace to one mechanism: `loyalty_streak_cap = 3`
makes loyalty a bounded counter rather than a stock, so there is neither
cross-sectional state worth conditioning on nor an intertemporal asset
worth investing in.

**Phase 7e** turns that into the question rather than the obstacle — see
`docs/phase_specifications.md`. It builds a separate mechanism-enabled
environment in which loyalty is a stock rather than a counter, and asks
under what market structure each level of policy complexity becomes
necessary. It runs as three existence gates — is there a state (licenses
context), is there an intertemporal trade-off (licenses horizon), does the
complexity measurably pay — with a binding stopping rule: if the third
gate fails on the most favorable market in the family, that is recorded as
the finding and the mechanism parameters are not tuned further. The base
environment's results stand unchanged alongside it; the point is the
contrast, not a replacement.

**Gate 1 passed at 7e-1.** With lock-in strength calibrated to match the
counter's, the stock's memory reaches 2.8× as far at a lag of eight weeks,
and the counter's advantage collapses at exactly its three-week cap. So a
state now exists for a contextual or multi-week policy to condition on,
which is the thing the base environment never had. Getting there cost two
corrections that are recorded in the spec rather than quietly fixed: the
first gate's threshold was arithmetically unreachable, and pinning the
stock's ceiling at Phase 6's made it bind a third as hard as the counter —
the *weaker* mechanism, dressed as the richer one.

**Gate 2 passed at 7e-2, marginally.** A schedule that discounts for sixteen
weeks and then returns to the standing price beats the best standing price by
+2.6%, CI [+2.0%, +3.2%] on held-out seeds. The same path with the investment
channel switched off loses 1.2%, so the gain is the loyalty stock rather than
the price path — the control 7d had no way to run. But what pays is
acquisition, not extraction: every schedule that ever charges above the
standing price loses, and so does every cycle. Both arms of gate 3 are
licensed, and 7e-3 runs the contextual bandit and the Q-network.

**Gate 3a returned a null, and 7c's finding survived the mechanism change.**
Conditioning on the loyalty state is worth −2.3%, CI [−3.0%, −1.5%] at 300
seeds — equivalent, and slightly costly rather than merely useless. An oracle
diagnostic run alongside it says why: over 460 seller-weeks split at the
median loyalty state, the profit-maximizing arm is the same on both sides. A
seller with a loyal base and one without want the same price, even here. And
it connects back to 7e-2 — no *one-week* deviation pays at any state, but a
*sixteen-week* one pays 2.6%, so the exploitable structure is a sustained
commitment rather than a weekly state-contingent choice, and a contextual
bandit is the wrong instrument for it by construction.

**Gate 3b: the right shape, the right depth, half the duration.** The
Q-network prices at 2.379 over weeks 0–7 against the hand-found schedule's
2.385 — then returns to the standing price at week 8 where the schedule holds
to week 16. It spends 75% of the discount and collects 31% of the gain,
because a stock compounds while it is being fed. This is the
sacrifice-then-recover trajectory 7d looked for and did not find, appearing
for the first time, in the environment built to contain it. It is still
+2.2% with a CI of [−0.4%, +4.8%] — equivalent, not material — so gate 3b
does not pass, and the sign of the advantage is not established. The
registered escalation fires only on an interval straddling the materiality
boundary, which this one does not, so it is not run and the limitation is
reported rather than repaired.

**Phase 7e's answer.** Policy complexity became *valuable* without becoming
*learnable*. Gate 2 measured an intertemporal trade-off worth 2.6% where the
base environment had none; context stayed worthless even against an oracle,
and the multi-week learner recovered under a third of a trade-off known to
exist. **The market structure that makes a sophisticated policy worth having
is not the structure that makes it findable.** Phase 7's original null was
understating the problem, not overstating it.

Full specification: see `docs/phase_specifications.md`.

## Full phase list (summary)

| # | Name | One-line research question | Moat relevance |
|---|---|---|---|
| 1 | Transaction Mechanics | Do buyers buy, do sellers sell, does inventory bind? | Infrastructure only |
| 2 | Linear Consumer Heterogeneity | Does person-level heterogeneity alone change purchase patterns? | Infrastructure only |
| 3 | Person + Environment | Does environment materially alter behavior beyond person features? | Infrastructure only |
| 4 | Person + Environment + Context | Does situational context add explanatory power beyond environment? | Infrastructure only |
| 5 | Nonlinear Behavior | Do nonlinear/interaction effects change conclusions vs. linear baseline? | Infrastructure only |
| 6 | Repeated Interaction | Does history/memory change future behavior? ("weeks" become real here) | Infrastructure only — **web viz introduced** |
| 7 (a, b, d) | Seller Learning | Does stateful policy learning produce market structures that myopic bandit optimization cannot? **No, in the base environment.** 7b beats the heuristic on profit but moves no class share; 7d's multi-week horizon adds nothing (equivalent). **7c skipped**: the profit-maximizing price is invariant to observable market state. | Infrastructure only |
| 7e | Mechanism Sufficiency | Under what market structure does each level of policy complexity become *necessary*? A separate environment with persistent, price-sensitive, bounded loyalty, run as three gates: state exists → intertemporal trade-off exists → complexity pays. **Gates 1 and 2 passed** — memory reaches 2.8× further than the counter's at lag 8 with lock-in strength held equal, and a discount-then-stop schedule beats the best standing price by +2.6% while the delta = 0 control loses. **Gate 3a null** — conditioning on the state is worth −2.3% (equivalent), and an oracle says the best arm is the same at every state. **Gate 3b not passed** — the Q-network reproduces the schedule's first eight weeks and stops, collecting 31% of a gain known to exist. Complexity became valuable without becoming learnable. | Infrastructure only — gives context conditioning and stateful learning an existence condition |
| 8 | Endogenous Market Structure | Does repeated local interaction produce macro-level structure? | Infrastructure only — **web viz: entry/exit panels** |
| 9a | Learned Buyer Policy | Can a learned policy recover the rule-based buyer's conditional behaviour, and does one-step fidelity survive closed-loop deployment? **The loop is real and does not compound** — D_shadow exceeds D_offline decisively (+0.0057, CI excludes zero) at 7%, with every trajectory quantity equivalent. | Infrastructure only — closes the buyer-side learning ladder |
| 9b | Teacher Entropy Sweep | Does the ratio of systematic policy error to intrinsic teacher stochasticity govern whether one-step error compounds? **Yes for amplification** (Spearman −1.00, 1.02×→1.67×), **not yet for behaviour** (peak 2.49 pp against ±5). | Infrastructure only |
| 9c | Stabilizer Ablation | Which environment characteristics — the budget wall, season-long fixed preference — suppress trajectory divergence? | Infrastructure only |
| 9d | Synthetic Agent Users | What does an LLM Agent add over a *trained* buyer policy? | First scaffolding for A — **web viz: Agent Inspector; cost/speed KPI begins** |
| 10 | Human vs Agent | Where does synthetic behavior match/diverge from real humans? | **A begins** |
| 11 | Bias Quantification | Can the gap be measured, mapped, and corrected? | **A formalizes; B built** |
| 12 | Cross-Model Comparison | Do different foundation models yield different conclusions? | **C begins** |
| 13 | Context Robustness | How sensitive are conclusions to prompt/persona construction? | Feeds A/D |
| 14 | Decision Reliability | When does error become large enough to flip a business decision? | **D crystallizes** |
| 15 | Reference-Scale Demonstration | Do all mechanisms together, at real market scale, produce plausible aggregate patterns? | **D compounds against real reference data (no client needed)** |
| 16 | Data Flywheel | Do real outcomes continuously improve future simulation? | **A + D compound; primary moat operational** |

## Hard constraints (apply until this file is explicitly edited)

- No Agent/LLM calls in agent decision logic before Phase 9d (Phase 9a is classical ML only)
- No adaptive/learning pricing before Phase 7
- No cross-run memory/history before Phase 6
- No web frontend before Phase 6 (when "weeks" first become a real mechanism). From Phase 6 on, the web visualization is built with portfolio-grade presentation quality (see "Dual purpose" section above), extended incrementally at Phase 8 and Phase 9 — not rebuilt from scratch each time
- Change only ONE complexity dimension per phase
- Every experiment run must be logged with git commit hash in `experiment_log.csv`
- Logging schema must include moat-relevant placeholder fields from Phase 1 onward (see `docs/phase_specifications.md` → Logging Schema section)

## Phase design review gate

Before writing any implementation code for a phase, Claude Code presents the
phase's config summary — agent counts, buyer/seller classes and parameters,
active environment/context features, and the decision-making method — to the
user in chat, in plain language, and waits for explicit confirmation.
Implementation starts only after that confirmation. This applies even when
the phase's spec is already written in `docs/phase_specifications.md`: the
written spec is the proposal, chat confirmation is the approval. If the
user requests changes, update `docs/phase_specifications.md` first, then
re-confirm before implementing.

## Phase completion checklist

A phase is not complete until all of the following are done, in order:
1. Acceptance criteria (in `docs/phase_specifications.md`) are met.
2. One slide is appended to `project_tracking.pptx` (see "Phase Completion
   Deliverable" in `docs/phase_specifications.md`).
3. `experiment_log.csv` has a row for the run(s), including the git commit hash.
4. `git tag phaseN-validated`.

## Git workflow

- Tag phase completion: `phase1-validated`, `phase2-validated`, etc. (only after the completion checklist above)
- Branch per phase: `phase2-heterogeneous`, `phase3-environment`, etc.
- Never advance to the next phase's branch until the current phase's acceptance criteria (in `docs/phase_specifications.md`) are met and tagged

### Three commits per phase, in this order

"Commit per meaningful change" was too vague to follow: Phases 3–5 each landed
as a single commit of 20–40 files, and Phase 4's was 42,000 lines. A spec
correction, an engine change and seven sets of generated CSVs in one diff means
the record of *how* a mechanism was built is unreadable even though it is
technically preserved. Each phase is therefore committed in three parts:

| # | Commit | Contains | Why separate |
|---|---|---|---|
| 1 | **Gate** | `docs/phase_specifications.md` (and `ROADMAP.md`) only | The design decisions made at the review gate, as a diff of tens of lines that can actually be read. Lands *before* implementation, which is also the order the gate itself requires. |
| 2 | **Implementation** | `src/`, `tests/`, `experiments/`, `tools/` | The code, reviewable on its own. Not buried under generated output. |
| 3 | **Results** | `results/`, `experiment_log.csv`, `project_tracking.pptx` | Entirely generated. Isolating it keeps the code diff in commit 2 legible, and keeps `git log --stat` honest about which changes were authored and which were produced by a run. |

Results stay committed rather than ignored: `experiment_log.csv` binds every
run to a commit hash, so the outputs are part of the evidence chain, not
incidental build artifacts.

Extra commits beyond these three are fine and expected when something is
corrected mid-phase — Phase 1 took four because the price normalizer and the
convergence band were both fixed after the first run. The three are a floor on
granularity, not a cap.
