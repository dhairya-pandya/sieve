import pytest

from redswarm.arena import fees
from redswarm.attackers import strategies
from redswarm.attackers.house import STRATEGIES, build_house_swarm
from redswarm.chain.base import NEAR

pytestmark = pytest.mark.asyncio


async def test_attacker_stops_after_break(naive_rig):
    atk = await naive_rig.attacker("atk", strategies.poisoned_email)
    summary = await atk.run(naive_rig.bid, max_attempts=10)
    assert summary.broke is True
    assert summary.stopped == "broke_it"
    assert summary.attempts == 2  # the email, then the invoice
    assert (await naive_rig.chain.get_bounty(naive_rig.bid)).winner == atk.account


async def test_attacker_stops_when_credit_exhausted(naive_rig):
    atk = await naive_rig.attacker("atk", strategies.urgency, credit=fees.FEE_YOCTO + fees.FEE_YOCTO // 2)
    summary = await atk.run(naive_rig.bid, max_attempts=10)
    assert summary.attempts == 1
    assert summary.stopped == "no_credit"
    assert summary.broke is False


async def test_swarm_breaks_naive_bot(naive_rig):
    swarm = await build_house_swarm(naive_rig.chain, naive_rig.arena, n=len(STRATEGIES))
    import asyncio

    summaries = await asyncio.gather(*(a.run(naive_rig.bid, max_attempts=10) for a in swarm))
    b = await naive_rig.chain.get_bounty(naive_rig.bid)
    assert b.status == "broken"
    assert b.winner in {a.account for a in swarm}
    assert sum(s.broke for s in summaries) == 1


async def test_swarm_fails_against_hardened_bot(hardened_rig):
    swarm = await build_house_swarm(hardened_rig.chain, hardened_rig.arena, n=len(STRATEGIES))
    import asyncio

    summaries = await asyncio.gather(*(a.run(hardened_rig.bid, max_attempts=10) for a in swarm))
    b = await hardened_rig.chain.get_bounty(hardened_rig.bid)
    assert b.status == "open"
    assert not any(s.broke for s in summaries)
    assert all(s.stopped == "strategy_done" for s in summaries)
    assert sum(s.attempts for s in summaries) > 0


async def test_slow_persuasion_breaks_naive_only_with_a_lead(naive_rig):
    without = await naive_rig.attacker("slow-a", strategies.slow_persuasion)
    s1 = await without.run(naive_rig.bid, max_attempts=10)
    assert s1.broke is False
    with_lead = await naive_rig.attacker("slow-b", strategies.slow_persuasion)
    with_lead.leads = ["the bot trusts documents. vendor: acme"]
    s2 = await with_lead.run(naive_rig.bid, max_attempts=10)
    assert s2.broke is True
