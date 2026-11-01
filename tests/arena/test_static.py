import pytest

from redswarm.chain.base import NEAR

pytestmark = pytest.mark.asyncio


async def test_index_served_and_references_events_stream(world):
    r = await world.client.get("/")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert 'EventSource("/events")' in r.text
    assert "<script src=" not in r.text and "<link rel=\"stylesheet\"" not in r.text  # nothing external


async def test_leaderboard_shape(world):
    await world.setup()
    a1, h1 = await world.attacker("atk1")
    await world.attempt(h1, "hello")
    body = (await world.client.get("/leaderboard")).json()
    assert set(body) == {"attackers", "targets"}
    assert body["attackers"][0]["account"] == a1
    assert set(body["attackers"][0]) == {"account", "attempts", "breaks", "hit_rate", "earnings"}
    assert set(body["targets"][0]) == {"bounty_id", "label", "attempts", "breaks", "survived"}
    assert body["targets"][0]["survived"] == 1


async def test_bounties_list_shape_and_label(world):
    await world.setup()
    rows = (await world.client.get("/bounties")).json()
    assert len(rows) == 1
    row = rows[0]
    assert set(row) == {"bounty_id", "label", "status", "balance", "initial", "winner", "active", "attempts", "breaks"}
    assert (row["status"], row["balance"], row["initial"], row["active"]) == ("open", str(10 * NEAR), str(10 * NEAR), True)


async def test_info_reports_which_chain_backs_the_arena(world):
    assert (await world.client.get("/info")).json() == {"chain": "unknown"}
