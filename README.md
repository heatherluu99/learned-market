# Millbrook Market

**A synthetic consumer market built to find out when a simulated buyer can be
trusted — and, more often, when it cannot.**

Every phase writes down its question and its failure condition *before* it runs,
and reports the answer either way. **Most of the headline results are negative.**
Those are the ones worth reading.

---

## The difference this project is about

| most synthetic-consumer work | here |
|---|---|
| `Persona + Prompt → Response` | `Persona + State + Environment + Memory + Policy → Trajectory` |
| one answer, no history | 22–110 weeks, choices that change later choices |
| judged by whether it sounds right | judged against a pre-registered threshold |

A response can be graded by reading it. A **trajectory** can only be graded
against something — a control, a baseline, a real panel. That is the whole
design.

---

## What it found

### An LLM buyer is further from real humans than knowing only the brand shares

![Phase 10](results/phase10/groq/human_vs_agent.png)

3,289 real purchase occasions, Ecdat::Cracker scanner panel. Same choice sets
for every arm.

| arm | distance to humans | log-loss |
|---|---|---|
| marginal brand shares | 0.1256 | 1.0696 |
| conditional choice model | **0.0404** | **0.7739** |
| **LLM Agent** | **0.2448** | **1.8966** |

**Every arm got all four mechanism directions right — including the floor.** So
sign agreement separates none of them. A test the marginal-share baseline passes
is not a test.

### The LLM's error is one number

![Phase 9d](results/phase9d/offline_fidelity.png)

Fitting the Agent against the rule that generates the world, over 447 states:

```
agent = −0.219 + 0.954 × rule
```

Slope ≈ 1. Its **comparative statics are right and its intercept is broken.**
Adding that one number back recovers **71.6%** of the collapse in a closed loop.

What *survives* the correction is a class bias: **+0.121** for high-income
buyers, **−0.063** for low-budget ones. Recalibration does not fix that, and
that is the part a client would be harmed by.

### Aggregate fidelity is cheap; individual fidelity is not

A model that knows **nothing about any individual household** matches the
aggregate choice distribution almost as well as one that knows every household
— 0.0035 against 0.0015 — while being **twice as wrong** per household.

A synthetic-consumer product graded on distributional match and sign agreement
can look excellent and carry no individual-level validity.

### Six more, briefly

| | question | answer |
|---|---|---|
| **2** | Does buyer heterogeneity cause stratification? | **Yes** — but 73% of it is budget, not price sensitivity |
| **6** | Does memory create stable relationships? | **Yes**, 0.425 vs 0.316 — but the *control* is 0.316, not 0 |
| **7c** | Does market state predict the best price? | **No.** Skipped on the evidence rather than run |
| **7e** | Can a learner find a gain known to exist? | Right shape, **31% of the gain**. Complexity became valuable without becoming learnable |
| **9** | Does imitation error compound? | **Real but bounded** — saturates at ~1.7×, never material |
| **10** | Does the simulator's memory beat a model that knows the household? | **No** — −0.005 nats, CI spans zero |

Full detail: [`docs/phase_specifications.md`](docs/phase_specifications.md) ·
every run: [`experiment_log.csv`](experiment_log.csv)

---

## Three corrections worth more than the results

**A claim withdrawn.** Phase 10 first reported human loyalty as "3.4× stronger
than the simulator's". That compared an *upper bound* against a *causal
quantity*. Withdrawn, and the honest version recorded: a memoryless model with
household preferences predicts **97%** of the observed repeat rate.

**A measurement artifact caught.** Human memory looked flat across eight weeks —
which no decaying mechanism can produce. The cause was the train/test split:
odd lags averaged +0.016 and even lags +0.032, eight for eight. Parity-free, it
decays normally.

**A win that was in-sample.** The simulator arm first beat its baseline by 0.35
nats. It was reading answers it had been fitted to on half the data. Scored
properly: **0.005 nats, CI spanning zero.**

---

## See it

```bash
open viz/millbrook.html
```

Four tabs, one file, no server:

| tab | |
|---|---|
| **Market** | a season replayed — buyers, stalls, who went where |
| **Entry & Exit** | firms entering and leaving; week 11 shows the premium tier competed out |
| **Agent Inspector** | 1,591 LLM decisions with the model's own reasoning, beside what the rule said |
| **Experiments** | all 41 runs, their figures, and the commits behind them |

---

## How it works, in short

**Buyers** carry a budget, a price sensitivity, a fixed taste, and a memory of
where they shopped. **Sellers** post a price and learn — by hill-climbing, by
bandit, or by a Q-network on multi-week return. Purchase is a logit:

```
U = intercept − α·(price/reference) + 1.5·preference + budget terms + γ·loyalty
P(buy) = sigmoid((U − 2) / τ)
```

**Loyalty** is Guadagni & Little (1983): `L ← ρL + (1−ρ)·1{bought}`, bonus `γL`.
Three variants are kept side by side — none, a capped streak counter, and this
decaying stock — because **two of five conclusions turn on which one is used.**

**Nothing reads a class label.** Entry copies a profitable rival; exit follows
capital. That is what lets "the premium tier was competed out" mean something.

---

## Reproducing

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest -q                          # 342 tests
.venv/bin/python experiments/phase8/run_phase8.py      # any phase
.venv/bin/python tools/build_combined_viz.py           # rebuild the page
```

| path | |
|---|---|
| `docs/phase_specifications.md` | the pre-registered spec — every gate, correction and result |
| `src/market_sim/` | engine, config, acceptance criteria, bandits, RL, LLM clients |
| `experiments/` | one runnable script per phase and per gate |
| `results/`, `experiment_log.csv` | outputs, each bound to a commit hash |
| `viz/millbrook.html` | the four tabs above |

Every logged run records the commit it ran at, and says `-dirty` out loud when
the tree was not clean. Eight rows were written that way before anything warned;
all eight were re-run clean and reproduced exactly.
