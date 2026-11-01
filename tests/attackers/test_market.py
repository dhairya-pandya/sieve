import asyncio

import pytest

from redswarm.attackers.house import STRATEGIES, build_house_swarm, trade_leads
from redswarm.chain.base import NEAR

pytestmark = pytest.mark.asyncio


async def test_swarm_run_includes_one_lead_sale(naive_rig):
    swarm = await build_house_swarm(naive_rig.chain, naive_rig.arena, n=len(STRATEGIES))
    seller, buyer = swarm[0], swarm[-1]
    before = await naive_rig.chain.balance(seller.account)
    lead_id = await trade_leads(swarm, naive_rig.bid)
    assert await naive_rig.chain.balance(seller.account) > before
    assert await naive_rig.chain.is_unlocked(lead_id, buyer.account)
    assert buyer.leads and "vendor: acme" in buyer.leads[0]
    sales = [e for e in naive_rig.app.state.bus.history if e["type"] == "lead_sold"]
    assert len(sales) == 1
    summaries = await asyncio.gather(*(a.run(naive_rig.bid, max_attempts=10) for a in swarm))
    assert (await naive_rig.chain.get_bounty(naive_rig.bid)).status == "broken"
    assert sum(s.broke for s in summaries) == 1
