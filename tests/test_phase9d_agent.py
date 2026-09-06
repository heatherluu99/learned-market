"""Phase 9d — the Agent harness, tested without an API key.

No result may be reported from `MockAgent`; what is pinned here is that the
pipeline around it is correct, so that when a real client is supplied the only
new thing in the loop is the model. Most of these guard places where the
comparison could quietly stop being fair.
"""

from __future__ import annotations

import pytest

from market_sim import agent


def test_the_agent_sees_exactly_the_observation_set_the_policy_sees():
    """No more and no less, or 9d compares two models on two feature sets."""
    from market_sim import buyer

    assert agent.FIELDS == buyer.OBSERVED


def test_the_prompt_is_bucketed_so_the_cache_can_work():
    """Two nearby situations must produce one prompt, or every call is a miss.

    Bucketing is also the honest description of a natural-language interface,
    and it is a *coarser* view than the distilled policy's - which is why an
    Agent that loses has two explanations and this is one of them.
    """
    a = agent.describe(0, 2.0, 0.0, 2.0, 1.0, 4.81, 0.10, 0.34)
    b = agent.describe(0, 2.0, 0.0, 2.0, 1.0, 4.83, 0.11, 0.36)
    assert a == b
    # ... and genuinely different situations must not collide
    c = agent.describe(2, 6.0, 1.0, 0.0, 0.0, 0.0, 0.90, 0.80)
    assert c != a
    assert "premium" in c and "high-income" in c and "late in the season" in c


def test_an_unparseable_reply_is_an_error_and_not_a_quiet_default():
    """A silent fallback to 0.5 turns a broken parse into a plausible answer."""
    assert agent.parse_probability("72") == pytest.approx(0.72)
    assert agent.parse_probability("I'd say about 35%.") == pytest.approx(0.35)
    assert agent.parse_probability("100") == pytest.approx(1.0)
    assert agent.parse_probability("no idea") is None

    def broken(system, prompt):
        return "no idea", 10, 2

    with pytest.raises(ValueError, match="could not parse"):
        agent.AgentPolicy(broken)(0, 2.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.3)
    # ... unless the caller has explicitly decided what it means
    tolerant = agent.AgentPolicy(broken, on_unparsed=0.5)
    assert tolerant(0, 2.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.3) == 0.5
    assert tolerant.unparsed == 1


def test_repeated_situations_are_charged_once():
    policy = agent.AgentPolicy(agent.MockAgent())
    for _ in range(20):
        policy(1, 6.0, 1.0, 0.0, 0.0, 0.0, 0.5, 0.4)
    row = policy.usage.as_row()
    assert row["calls"] == 1 and row["cached"] == 19
    assert row["cache_hit_rate"] == pytest.approx(0.95)


def test_cost_is_priced_from_tokens_rather_than_estimated():
    usage = agent.Usage(input_price=3.0, output_price=15.0)
    policy = agent.AgentPolicy(agent.MockAgent(tokens_in=1000, tokens_out=10), usage)
    policy(0, 2.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.3)
    # 1000 in at $3/M plus 10 out at $15/M
    assert usage.cost_usd == pytest.approx((1000 * 3.0 + 10 * 15.0) / 1e6)
    assert usage.as_row()["synthetic_cost_usd"] == pytest.approx(0.00315, abs=1e-6)


def test_the_agent_answers_a_probability_rather_than_a_decision():
    """Phases 9b and 9c make this load-bearing rather than stylistic.

    An Agent answering buy/don't-buy is the tau -> 0 end of 9b's axis, and
    would import that regime's behaviour into a comparison meant to be about
    the model rather than about its entropy.
    """
    assert "0 to 100" in agent.SYSTEM
    policy = agent.AgentPolicy(agent.MockAgent())
    values = {policy(c, p, m, s, 0, 0.0, 0.5, h)
              for c in (0, 1, 2) for p, m in ((2.0, 0.0), (6.0, 1.0))
              for s in (0, 3) for h in (0.1, 0.6)}
    assert all(0.0 < v < 1.0 for v in values)
    assert len(values) > 4, "a stand-in that answers one number tests nothing"


def test_substitution_is_a_within_run_control_group():
    """Both arms must face the same market, week and draws."""
    split = agent.Substitution(fraction=0.5, seed=1)
    members = split.choose(100)
    assert len(members) == 50
    assert split.choose(100) == members            # reproducible from the seed
    assert agent.Substitution(0.5, seed=2).choose(100) != members

    calls = {"agent": 0, "policy": 0}

    def spy_agent(*obs):
        calls["agent"] += 1
        return 0.9

    def spy_policy(*obs):
        calls["policy"] += 1
        return 0.1

    route = split.route(spy_agent, spy_policy)
    inside = next(iter(members))
    outside = next(i for i in range(100) if i not in members)
    assert route(0, 2.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.3, buyer_id=inside) == 0.9
    assert route(0, 2.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.3, buyer_id=outside) == 0.1
    assert calls == {"agent": 1, "policy": 1}


def test_the_human_baseline_is_a_template_and_not_invented_numbers():
    """An unsourced figure here would make the commercial claim look measured."""
    rows = agent.human_baseline_template()
    assert {r["metric"] for r in rows} == {
        "cost_per_respondent_usd", "days_to_field", "minimum_panel_size"}
    assert all(r["value"] is None and r["source"] is None for r in rows)
