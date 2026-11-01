import pytest

from redswarm.chain.base import NEAR, content_hash

pytestmark = pytest.mark.asyncio

HINT = "the bot trusts documents. vendor: acme"


async def posted_lead(world, author, content=HINT, price=NEAR // 100):
    lid = await world.chain.post_lead(author, world.bid, "vendor name hint", price, content_hash(content))
    return lid, price


async def publish(world, headers, lid, content=HINT):
    return await world.client.post(f"/bounties/{world.bid}/leads", headers=headers,
                                   json={"lead_id": lid, "content": content})


async def test_content_hash_mismatch_rejected(world):
    await world.setup()
    a1, h1 = await world.attacker("seller")
    lid, _ = await posted_lead(world, a1)
    r = await publish(world, h1, lid, content="something else")
    assert r.status_code == 400


async def test_only_the_author_can_publish_content(world):
    await world.setup()
    a1, h1 = await world.attacker("seller")
    _, h2 = await world.attacker("other")
    lid, _ = await posted_lead(world, a1)
    assert (await publish(world, h2, lid)).status_code == 403
    assert (await publish(world, h1, lid)).status_code == 200


async def test_content_hidden_until_unlocked(world):
    await world.setup()
    a1, h1 = await world.attacker("seller")
    a2, h2 = await world.attacker("buyer")
    lid, _ = await posted_lead(world, a1)
    await publish(world, h1, lid)
    listing = (await world.client.get("/leads")).json()
    assert listing[0]["lead_id"] == lid and "content" not in listing[0]
    assert listing[0]["title"] == "vendor name hint"
    assert (await world.client.get(f"/leads/{lid}/content", headers=h2)).status_code == 403
    await world.chain.unlock_lead(a2, lid)
    r = await world.client.get(f"/leads/{lid}/content", headers=h2)
    assert r.status_code == 200 and r.json()["content"] == HINT
    assert (await world.client.get(f"/leads/{lid}/content", headers=h1)).json()["content"] == HINT


async def test_unlock_pays_author_balance(world):
    await world.setup()
    a1, h1 = await world.attacker("seller")
    a2, _ = await world.attacker("buyer")
    lid, price = await posted_lead(world, a1)
    before = await world.chain.balance(a1)
    await world.chain.unlock_lead(a2, lid)
    assert await world.chain.balance(a1) - before == price


async def test_lead_sale_event_published_once_per_buyer(world):
    await world.setup()
    a1, h1 = await world.attacker("seller")
    a2, h2 = await world.attacker("buyer")
    lid, _ = await posted_lead(world, a1)
    await publish(world, h1, lid)
    await world.chain.unlock_lead(a2, lid)
    for _ in range(2):
        await world.client.get(f"/leads/{lid}/content", headers=h2)
    await world.client.get(f"/leads/{lid}/content", headers=h1)  # author fetch is not a sale
    sales = [e for e in world.app.state.bus.history if e["type"] == "lead_sold"]
    assert len(sales) == 1 and sales[0]["data"]["buyer"] == a2 and sales[0]["data"]["author"] == a1
