import httpx
import pytest

from redswarm.arena.app import create_app
from redswarm.attackers.base import ArenaClient, Attacker
from redswarm.chain.base import NEAR, secret_hash
from redswarm.chain.fake import FakeChain
from redswarm.targets.api import create_target_app
from redswarm.targets.treasurybot import TreasuryBot


class Rig:
    """Fake chain + arena + one TreasuryBot target, all in process."""

    async def build(self, hardened: bool):
        self.chain = c = FakeChain()
        self.poster = await c.create_account("poster", 50 * NEAR)
        self.bot_account = await c.create_account("bot", 5 * NEAR)
        self.vendor = await c.create_account("acme", NEAR)
        self.bid = await c.post_bounty(self.poster, self.bot_account, [self.vendor],
                                       secret_hash("s", "t"), 10 * NEAR)
        self.bot = TreasuryBot(c, self.bid, self.bot_account, hardened=hardened,
                               vendors={"acme": self.vendor}, spend_cap=NEAR)
        token = {}
        target_app = create_target_app(self.bot, lambda: token["t"])
        self.target_http = httpx.AsyncClient(transport=httpx.ASGITransport(app=target_app),
                                             base_url="http://target.local")
        self.app = create_app(c, c.operator, target_client=self.target_http)
        self.http = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://arena")
        self.arena = ArenaClient(self.http)
        r = await self.http.post("/bounties", json={"bounty_id": self.bid, "target_url": "http://target.local"})
        assert r.status_code == 200
        token["t"] = r.json()["ownership_token"]
        assert (await self.http.post(f"/bounties/{self.bid}/verify")).status_code == 200
        return self

    async def attacker(self, name, strategy_factory, credit=NEAR):
        acct = await self.chain.create_account(name, 20 * NEAR)
        await self.chain.register_attacker(acct)
        if credit:
            await self.chain.deposit_credit(acct, credit)
        key = await self.arena.register_attacker(acct)
        return Attacker(acct, key, strategy_factory(acct), self.arena)

    async def close(self):
        await self.http.aclose()
        await self.target_http.aclose()


@pytest.fixture
async def naive_rig():
    rig = await Rig().build(hardened=False)
    yield rig
    await rig.close()


@pytest.fixture
async def hardened_rig():
    rig = await Rig().build(hardened=True)
    yield rig
    await rig.close()
