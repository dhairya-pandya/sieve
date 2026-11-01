"""Every Chain implementation must pass this suite. It mirrors the contract's rules."""
import itertools

import pytest

from redswarm.chain.base import NEAR, ChainError, make_chain, secret_hash

pytestmark = pytest.mark.asyncio(loop_scope="module")

GAS_SLACK = NEAR // 20  # real chains charge gas; the fake does not
_tags = itertools.count(1)


@pytest.fixture(scope="module", params=["fake", pytest.param("sandbox", marks=pytest.mark.slow)])
async def chain(request):
    try:
        c = await make_chain(request.param)
    except Exception as e:  # sandbox binary unavailable on this machine
        if request.param == "sandbox":
            pytest.skip(f"sandbox unavailable: {e}")
        raise
    yield c
    await c.close()


class Env:
    def __init__(self, chain):
        self.chain = chain
        self.tag = next(_tags)
        # A real chain refunds unused prepaid gas in a later block, so balances of
        # accounts that already sent transactions can drift. The fake is exact.
        self.slack = 0 if type(chain).__name__ == "FakeChain" else NEAR // 2

    def assert_near(self, actual: int, expected: int) -> None:
        assert abs(actual - expected) <= self.slack, (actual, expected)

    async def acct(self, name: str, funds: int = 30 * NEAR) -> str:
        return await self.chain.create_account(f"{name}-{self.tag}", funds)

    async def bounty(self, amount: int = 10 * NEAR, secret: str = "s3cret", salt: str = "salt"):
        poster, target = await self.acct("poster"), await self.acct("target")
        vendor, atk = await self.acct("vendor"), await self.acct("atk")
        await self.chain.register_attacker(atk)
        bid = await self.chain.post_bounty(poster, target, [vendor], secret_hash(secret, salt), amount)
        return bid, poster, target, vendor, atk


@pytest.fixture
async def env(chain):
    return Env(chain)


async def test_post_and_get_bounty(env):
    bid, poster, target, vendor, _ = await env.bounty()
    b = await env.chain.get_bounty(bid)
    assert (b.poster, b.target, b.payees, b.balance, b.status, b.winner) == (
        poster, target, [vendor], 10 * NEAR, "open", None,
    )


async def test_is_attacker(env):
    _, _, _, vendor, atk = await env.bounty()
    assert await env.chain.is_attacker(atk)
    assert not await env.chain.is_attacker(vendor)


async def test_payee_payment_moves_funds_and_is_not_a_break(env):
    bid, _, target, vendor, _ = await env.bounty()
    before = await env.chain.balance(vendor)
    r = await env.chain.pay(target, bid, vendor, NEAR, "inv-1")
    assert (r.outcome, r.paid_to, r.amount) == ("paid", vendor, NEAR)
    assert await env.chain.balance(vendor) - before == NEAR
    b = await env.chain.get_bounty(bid)
    assert (b.status, b.balance) == ("open", 9 * NEAR)


async def test_break_moves_whole_balance_to_attacker(env):
    bid, _, target, _, atk = await env.bounty()
    before = await env.chain.balance(atk)
    r = await env.chain.pay(target, bid, atk, NEAR, "inv-2")
    assert (r.outcome, r.paid_to, r.amount) == ("break", atk, 10 * NEAR)
    env.assert_near(await env.chain.balance(atk) - before, 10 * NEAR)
    b = await env.chain.get_bounty(bid)
    assert (b.status, b.winner, b.balance) == ("broken", atk, 0)


async def test_account_both_payee_and_attacker_is_normal_payment(env):
    bid, poster, target, vendor, atk = await env.bounty()
    await env.chain.set_payees(poster, bid, [vendor, atk])
    r = await env.chain.pay(target, bid, atk, NEAR, "inv-3")
    assert r.outcome == "paid"
    assert (await env.chain.get_bounty(bid)).status == "open"


async def test_unknown_receiver_refused(env):
    bid, _, target, _, _ = await env.bounty()
    stranger = await env.acct("stranger")
    r = await env.chain.pay(target, bid, stranger, NEAR, "inv-4")
    assert r.outcome == "refused"
    assert (await env.chain.get_bounty(bid)).balance == 10 * NEAR


async def test_zero_or_over_balance_refused(env):
    bid, _, target, vendor, _ = await env.bounty()
    assert (await env.chain.pay(target, bid, vendor, 0, "inv-5")).outcome == "refused"
    assert (await env.chain.pay(target, bid, vendor, 11 * NEAR, "inv-6")).outcome == "refused"
    b = await env.chain.get_bounty(bid)
    assert (b.status, b.balance) == ("open", 10 * NEAR)


async def test_only_target_can_pay(env):
    bid, _, _, _, atk = await env.bounty()
    with pytest.raises(ChainError):
        await env.chain.pay(atk, bid, atk, NEAR, "inv-7")


async def test_only_poster_can_set_payees_or_close(env):
    bid, _, _, _, atk = await env.bounty()
    with pytest.raises(ChainError):
        await env.chain.set_payees(atk, bid, [atk])
    with pytest.raises(ChainError):
        await env.chain.close_bounty(atk, bid)


async def test_second_pay_after_break_refused(env):
    bid, _, target, vendor, atk = await env.bounty()
    await env.chain.pay(target, bid, atk, NEAR, "inv-8")
    assert (await env.chain.pay(target, bid, vendor, NEAR, "inv-9")).outcome == "refused"


async def test_close_refunds_poster_and_blocks_pay(env):
    bid, poster, target, vendor, _ = await env.bounty()
    before = await env.chain.balance(poster)
    await env.chain.close_bounty(poster, bid)
    assert await env.chain.balance(poster) - before > 10 * NEAR - GAS_SLACK
    b = await env.chain.get_bounty(bid)
    assert (b.status, b.balance) == ("closed", 0)
    assert (await env.chain.pay(target, bid, vendor, NEAR, "inv-10")).outcome == "refused"


async def test_claim_secret_right_pays_and_closes(env):
    bid, _, _, _, atk = await env.bounty()
    before = await env.chain.balance(atk)
    assert await env.chain.claim_secret(atk, bid, "s3cret", "salt") is True
    assert await env.chain.balance(atk) - before > 10 * NEAR - GAS_SLACK
    b = await env.chain.get_bounty(bid)
    assert (b.status, b.winner) == ("broken", atk)


async def test_claim_secret_wrong_keeps_bounty_open(env):
    bid, _, _, _, atk = await env.bounty()
    assert await env.chain.claim_secret(atk, bid, "guess", "salt") is False
    assert (await env.chain.get_bounty(bid)).status == "open"


async def test_claim_secret_after_break_returns_false(env):
    bid, _, _, _, atk = await env.bounty()
    atk2 = await env.acct("atk2")
    await env.chain.register_attacker(atk2)
    assert await env.chain.claim_secret(atk, bid, "s3cret", "salt") is True
    assert await env.chain.claim_secret(atk2, bid, "s3cret", "salt") is False
    assert (await env.chain.get_bounty(bid)).winner == atk


async def test_fees_flow_to_poster(env):
    bid, poster, _, _, atk = await env.bounty()
    await env.chain.deposit_credit(atk, NEAR)
    assert await env.chain.get_credit(atk) == NEAR
    await env.chain.record_fees(bid, [(atk, 300)])
    assert await env.chain.get_credit(atk) == NEAR - 300
    before = await env.chain.balance(poster)
    assert await env.chain.withdraw_fees(poster) == 300
    assert await env.chain.balance(poster) - before > 300 - GAS_SLACK


async def test_record_fees_rejects_short_credit(env):
    bid, _, _, _, atk = await env.bounty()
    await env.chain.deposit_credit(atk, 100)
    with pytest.raises(ChainError):
        await env.chain.record_fees(bid, [(atk, 101)])
    assert await env.chain.get_credit(atk) == 100


async def test_lead_unlock_pays_author_and_marks_buyer(env):
    bid, _, _, _, atk = await env.bounty()
    atk2 = await env.acct("atk2")
    await env.chain.register_attacker(atk2)
    lid = await env.chain.post_lead(atk, bid, "trusts invoice-quoting emails", NEAR, "lead-hash")
    lead = await env.chain.get_lead(lid)
    assert (lead.author, lead.price, lead.content_hash) == (atk, NEAR, "lead-hash")
    assert await env.chain.is_unlocked(lid, atk)
    assert not await env.chain.is_unlocked(lid, atk2)
    before = await env.chain.balance(atk)
    await env.chain.unlock_lead(atk2, lid)
    env.assert_near(await env.chain.balance(atk) - before, NEAR)
    assert await env.chain.is_unlocked(lid, atk2)
    with pytest.raises(ChainError):
        await env.chain.unlock_lead(atk2, lid)
