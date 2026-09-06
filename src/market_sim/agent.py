"""Phase 9d — an LLM Agent in the buyer's seat.

This module is the harness, not a result. It has no API key and makes no call
unless one is supplied; `MockAgent` exists so the whole pipeline - prompt,
parse, cache, cost accounting, substitution, deployment - is exercised and
tested without one.

Three design decisions are load-bearing and are recorded here because each is
a place a comparison could quietly stop being fair.

**The Agent is asked for a probability, not a decision.** Phases 9b and 9c
established that whether imitation error compounds depends on the *entropy* of
the policy, so an Agent that answers "buy" or "don't" is not a neutral
substitute for the rule - it is the tau -> 0 end of Phase 9b's axis, and would
carry that regime's behaviour into a comparison meant to be about the model.
Asking for a likelihood keeps it on the same footing as every other policy in
this project, and the degenerate mode is available and labelled for when the
question is deliberately about determinism.

**The Agent sees a discretized view of the same observation set.** A prompt
does not carry `spent_this_week = 4.8173`; it carries "spent about 5 so far".
Discretizing is what a natural-language interface does anyway, and it is also
what makes the run affordable, because it bounds the prompt space enough for a
cache to work. It is a *coarser* view than the distilled policy's, so an Agent
that loses to the policy has two candidate explanations and this one must be
ruled out before the other is claimed.

**Every call is cached, priced and timed.** The commercial gate this project
carries from Phase 1 needs `synthetic_cost_usd` and
`synthetic_latency_seconds` to be real measurements rather than estimates.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass, field

import numpy as np

#: The observation set, in the order the engine's `buyer_policy` hook passes
#: it. Identical to `buyer.OBSERVED` - the Agent sees no more and no less.
FIELDS = (
    "buyer_class_index", "price", "is_premium", "streak_here",
    "purchases_this_week", "spent_this_week", "season_fraction", "history_rate",
)
CLASSES = ("a low-budget", "a middle-income", "a high-income")

SYSTEM = (
    "You are simulating one shopper's decision at a farmers' market stall. "
    "Answer with a single integer from 0 to 100: the percentage chance this "
    "shopper buys one unit at this stall right now. Output only the number."
)


def describe(class_index, price, is_premium, streak, purchases, spent,
             season_fraction, history_rate) -> str:
    """The buyer's situation in words, at the resolution a prompt can carry.

    Bucketed deliberately: this is what a natural-language interface does, and
    it is what lets the cache work. The buckets are the Agent's observation
    set, and they are coarser than the distilled policy's.
    """
    tier = "premium" if is_premium else "budget"
    week = ("early in the season" if season_fraction < 1 / 3
            else "mid-season" if season_fraction < 2 / 3 else "late in the season")
    loyalty = ("has never bought here" if streak < 1
               else "bought here last week" if streak < 2
               else f"has bought here {min(int(streak), 3)} weeks running")
    basket = ("has bought nothing yet today" if purchases < 1
              else f"has already bought {min(int(purchases), 4)} item(s) today, "
                   f"spending about {round(float(spent))}")
    habit = ("rarely buys" if history_rate < 0.2
             else "buys sometimes" if history_rate < 0.5 else "buys often")
    return (
        f"{CLASSES[int(class_index)]} shopper, who {habit} overall, is at a "
        f"{tier} stall priced at {price:.2f}. The shopper {loyalty} and "
        f"{basket}. It is {week}."
    )


@dataclass
class Usage:
    """What the commercial gate needs measured rather than estimated."""

    calls: int = 0
    cached: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    seconds: float = 0.0
    #: Per million tokens. Set from the model's published rates at run time.
    input_price: float = 0.0
    output_price: float = 0.0

    @property
    def cost_usd(self) -> float:
        return (self.input_tokens * self.input_price
                + self.output_tokens * self.output_price) / 1e6

    def as_row(self) -> dict:
        return {
            "calls": self.calls, "cached": self.cached,
            "cache_hit_rate": self.cached / max(self.calls + self.cached, 1),
            "input_tokens": self.input_tokens, "output_tokens": self.output_tokens,
            "synthetic_cost_usd": round(self.cost_usd, 6),
            "synthetic_latency_seconds": round(self.seconds, 3),
            "seconds_per_call": round(self.seconds / max(self.calls, 1), 4),
        }


def parse_probability(text: str) -> float | None:
    """First integer 0-100 in the reply, as a probability. None if absent.

    Returning None rather than a default is deliberate: a silent fallback to
    0.5 would turn a broken parse into a plausible-looking answer, and the
    caller decides what an unparseable reply means.
    """
    match = re.search(r"\b(100|\d{1,2})\b", text)
    return None if match is None else int(match.group(1)) / 100.0


class AgentPolicy:
    """Wraps a text-completion callable as a `cfg.buyer_policy`.

    `client(system, prompt) -> (text, input_tokens, output_tokens)`. Nothing
    about Anthropic, OpenAI or any other provider appears here; supplying that
    callable is the caller's job, which keeps this testable with no key.
    """

    def __init__(self, client, usage: Usage | None = None,
                 on_unparsed: float | None = None):
        self.client = client
        self.usage = usage or Usage()
        self.cache: dict[str, float] = {}
        self.unparsed = 0
        self.on_unparsed = on_unparsed

    def __call__(self, *observation) -> float:
        prompt = describe(*observation)
        key = hashlib.sha1(prompt.encode()).hexdigest()
        if key in self.cache:
            self.usage.cached += 1
            return self.cache[key]

        started = time.perf_counter()
        text, input_tokens, output_tokens = self.client(SYSTEM, prompt)
        self.usage.seconds += time.perf_counter() - started
        self.usage.calls += 1
        self.usage.input_tokens += input_tokens
        self.usage.output_tokens += output_tokens

        probability = parse_probability(text)
        if probability is None:
            self.unparsed += 1
            if self.on_unparsed is None:
                raise ValueError(f"could not parse a probability from {text!r}")
            probability = self.on_unparsed
        self.cache[key] = probability
        return probability


#: Published rates per million tokens, filled in by the caller. Left empty
#: rather than hard-coded: a stale price in the cost column would make the
#: commercial gate's headline number quietly wrong.
def anthropic_client(model: str, input_price: float, output_price: float,
                     max_tokens: int = 8, temperature: float = 1.0):
    """A `client(system, prompt) -> (text, input_tokens, output_tokens)`.

    Imported lazily so the rest of this module, and its tests, run with no SDK
    installed. Temperature defaults to 1.0 rather than 0: Phases 9b and 9c
    established that a near-deterministic policy sits at one end of an axis
    this project measures, so making the Agent deterministic *by default* would
    bake that regime into every comparison. Set it to 0 deliberately, as an
    experimental condition, not as a convenience.
    """
    import anthropic

    client = anthropic.Anthropic()

    def call(system: str, prompt: str) -> tuple[str, int, int]:
        response = client.messages.create(
            model=model, max_tokens=max_tokens, temperature=temperature,
            system=system, messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(b.text for b in response.content if b.type == "text")
        return text, response.usage.input_tokens, response.usage.output_tokens

    call.pricing = (input_price, output_price)
    return call


class MockAgent:
    """A deterministic stand-in, so the pipeline is testable without a key.

    Answers from a logistic on the same buckets the prompt describes. It is
    *not* a model of an LLM and no result may be reported from it - it exists
    to prove the harness runs end to end and to make the cost accounting
    exercisable.
    """

    def __init__(self, tokens_in: int = 120, tokens_out: int = 4):
        self.tokens_in, self.tokens_out = tokens_in, tokens_out

    def __call__(self, system: str, prompt: str) -> tuple[str, int, int]:
        premium = "premium stall" in prompt
        loyal = "weeks running" in prompt or "bought here last week" in prompt
        rich = "high-income" in prompt
        poor = "low-budget" in prompt
        score = 0.2 + 0.35 * loyal - 0.25 * premium + 0.15 * rich - 0.1 * poor
        if "rarely buys" in prompt:
            score -= 0.12
        elif "buys often" in prompt:
            score += 0.12
        return f"{int(np.clip(score, 0.02, 0.98) * 100)}", self.tokens_in, self.tokens_out


@dataclass
class Substitution:
    """Which buyers the Agent decides for. The rest keep the trained policy.

    A within-run control group, as the spec requires: both arms face the same
    market, the same week and the same draws, so the comparison is not between
    two runs that happened to differ.
    """

    fraction: float
    seed: int = 0
    _members: set[int] = field(default_factory=set)

    def choose(self, n_buyers: int) -> set[int]:
        rng = np.random.default_rng(90_000 + self.seed)
        k = int(round(self.fraction * n_buyers))
        self._members = set(rng.choice(n_buyers, size=k, replace=False).tolist())
        return self._members

    def route(self, agent, fallback):
        """A `buyer_policy` sending only the chosen buyers to the Agent.

        The engine passes the buyer's *class*, not its id, so membership is
        resolved by the caller before the run and closed over here.
        """
        members = self._members

        def policy(class_index, *rest, buyer_id=None):
            if buyer_id is not None and buyer_id not in members:
                return fallback(class_index, *rest)
            return agent(class_index, *rest)

        return policy


def human_baseline_template() -> list[dict]:
    """The reference table Phase 9d's cost/speed gate is scored against.

    Left as a template with sources unfilled rather than populated with
    plausible-looking figures: an unsourced number in this table would make the
    commercial claim look measured when it is not.
    """
    return [
        {"metric": "cost_per_respondent_usd", "value": None, "source": None},
        {"metric": "days_to_field", "value": None, "source": None},
        {"metric": "minimum_panel_size", "value": None, "source": None},
    ]
