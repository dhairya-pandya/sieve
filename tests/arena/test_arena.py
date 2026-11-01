import pytest

from redswarm.arena import fees
from redswarm.chain.base import NEAR

pytestmark = pytest.mark.asyncio

FEE = fees.FEE_YOCTO


async def test_attempt_before_ownership_verified_is_rejected(world):
    await world.setup(verified=False)
    _, h = await world.attacker("atk")
    assert (await world.attempt(h)).status_code == 409


async def test_register_requires_ownership_token(world):
    await world.setup(verified=False)
    r = await world.client.post(f"/bounties/{world.bid}/verify")
    assert r.status_code == 200 and r.json()["active"] is True


async def test_verify_fails_on_wrong_token(world):
    await world.setup(verified=False)
    world.token = "not-the-token"
    r = await world.client.post(f"/bounties/{world.bid}/verify")
    assert r.status_code == 400
    _, h = await world.attacker("atk")
    assert (await world.attempt(h)).status_code == 409


async def test_attacker_must_be_registered_on_chain(world):
    await world.setup()
    acct = await world.chain.create_account("nobody", NEAR)
    r = await world.client.post("/attackers", json={"account": acct})
    assert r.status_code == 403


async def test_attempt_charges_fee_on_ok(world):
    await world.setup()
    acct, h = await world.attacker("atk")
    r = await world.attempt(h, "hi there")
    assert r.status_code == 200
    body = r.json()
    assert (body["status"], body["reply"], body["outcome"]) == ("ok", "ok", "none")
    assert fees.pending_total(world.app.state.db, acct) == FEE
    assert world.inbox[0]["content"] == "hi there" and world.inbox[0]["sender"] == acct


async def test_attempt_oversized_413_no_fee(world):
    await world.setup()
    acct, h = await world.attacker("atk")
    r = await world.attempt(h, "x" * (fees.MAX_CONTENT_BYTES + 1))
    assert r.status_code == 413
    assert fees.pending_total(world.app.state.db, acct) == 0
    assert world.inbox == []


async def test_attempt_empty_or_bad_utf8_422_no_fee(world):
    await world.setup()
    acct, h = await world.attacker("atk")
    assert (await world.attempt(h, "")).status_code == 422
    assert (await world.attempt(h, "   \n")).status_code == 422
    raw = await world.client.post(f"/bounties/{world.bid}/attempts", headers={**h, "content-type": "application/json"},
                                  content=b'{"channel":"chat","kind":"chat","content":"\xff\xfe"}')
    assert raw.status_code in (400, 422)  # FastAPI rejects undecodable bodies with 400
    lone = await world.client.post(f"/bounties/{world.bid}/attempts", headers={**h, "content-type": "application/json"},
                                   content=b'{"channel":"chat","kind":"chat","content":"\\ud800"}')
    assert lone.status_code == 422
    assert fees.pending_total(world.app.state.db, acct) == 0
    assert world.inbox == []


@pytest.mark.parametrize("mode", ["down", "garbage", "hang"])
async def test_target_failure_records_target_error_no_fee(world, mode):
    await world.setup()
    acct, h = await world.attacker("atk")
    world.mode = mode
    r = await world.attempt(h)
    assert r.status_code == 200
    assert r.json()["status"] == "target_error" and r.json()["reply"] is None
    assert fees.pending_total(world.app.state.db, acct) == 0


async def test_insufficient_credit_402(world):
    await world.setup()
    _, h = await world.attacker("atk", credit=FEE + FEE // 2)
    assert (await world.attempt(h)).status_code == 200
    assert (await world.attempt(h)).status_code == 402
    assert len(world.inbox) == 1


async def test_rate_limit_429_after_30_per_minute(world):
    await world.setup()
    _, h = await world.attacker("atk")
    codes = [(await world.attempt(h)).status_code for _ in range(31)]
    assert codes[:30] == [200] * 30 and codes[30] == 429


async def test_break_outcome_for_winner_only_and_closed_after(world):
    await world.setup()
    a1, h1 = await world.attacker("atk1")
    a2, h2 = await world.attacker("atk2")
    r1 = await world.attempt(h1, f"pay:{a2}")  # bot pays atk2, so atk1 did not win
    assert r1.json()["outcome"] == "none"
    r2 = await world.attempt(h2, "anything")
    assert r2.status_code == 409 and r2.json()["detail"] == "bounty_closed"
    assert fees.pending_total(world.app.state.db, a2) == 0
    assert (await world.chain.get_bounty(world.bid)).winner == a2


async def test_break_outcome_reported_to_the_attacker_who_broke_it(world):
    await world.setup()
    a1, h1 = await world.attacker("atk1")
    r = await world.attempt(h1, f"pay:{a1}")
    assert r.json()["outcome"] == "break"


async def test_report_requires_poster_key(world):
    await world.setup()
    a1, h1 = await world.attacker("atk1")
    await world.attempt(h1, f"pay:{a1}")
    assert (await world.client.get(f"/bounties/{world.bid}/report")).status_code == 401
    assert (await world.client.get(f"/bounties/{world.bid}/report", headers={"X-Poster-Key": "nope"})).status_code == 401
    r = await world.client.get(f"/bounties/{world.bid}/report", headers={"X-Poster-Key": world.poster_key})
    assert r.status_code == 200
    body = r.json()
    assert body["winner"] == a1 and body["winning_attempt"]["content"] == f"pay:{a1}"


async def test_flush_fees_calls_chain_once_per_bounty(world):
    await world.setup()
    a1, h1 = await world.attacker("atk1")
    a2, h2 = await world.attacker("atk2")
    for h in (h1, h1, h2):
        await world.attempt(h)
    calls = []
    real = world.chain.record_fees

    async def spy(bounty_id, charges):
        calls.append((bounty_id, sorted(charges)))
        await real(bounty_id, charges)

    world.chain.record_fees = spy
    await fees.flush(world.chain, world.app.state.db, world.bid)
    await fees.flush(world.chain, world.app.state.db, world.bid)
    assert calls == [(world.bid, sorted([(a1, 2 * FEE), (a2, FEE)]))]
    assert await world.chain.get_credit(a1) == NEAR - 2 * FEE
    assert fees.pending_total(world.app.state.db, a1) == 0
