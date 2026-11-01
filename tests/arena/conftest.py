import asyncio

import httpx
import pytest

from redswarm.arena.app import create_app
from redswarm.chain.base import NEAR, secret_hash
from redswarm.chain.fake import FakeChain

pytestmark = pytest.mark.asyncio


class World:
    """A fake chain, an arena app, and a stub target agent whose behaviour tests can switch."""

    def __init__(self):
        self.chain = FakeChain()
        self.mode = "answer"  # answer | down | garbage | hang
        self.token = None
        self.bid = None
        self.inbox: list[dict] = []
        self.target_client = httpx.AsyncClient(transport=httpx.MockTransport(self._target))
        self.app = create_app(self.chain, self.chain.operator, ":memory:",
                              target_client=self.target_client, target_timeout=0.3)
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://arena")

    async def _target(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/redswarm/ownership":
            return httpx.Response(200, json={"token": self.token})
        body = request.read().decode()
        import json

        msg = json.loads(body)
        self.inbox.append(msg)
        if self.mode == "down":
            raise httpx.ConnectError("target is down")
        if self.mode == "hang":
            await asyncio.sleep(5)
        if self.mode == "garbage":
            return httpx.Response(200, content=b"<html>not json</html>")
        if msg["content"].startswith("pay:"):
            await self.chain.pay(self.target, self.bid, msg["content"][4:], NEAR, "stub")
        return httpx.Response(200, json={"reply": "ok"})

    async def setup(self, verified: bool = True):
        c = self.chain
        self.poster = await c.create_account("poster", 50 * NEAR)
        self.target = await c.create_account("target", 5 * NEAR)
        self.vendor = await c.create_account("vendor", NEAR)
        self.bid = await c.post_bounty(self.poster, self.target, [self.vendor], secret_hash("s", "t"), 10 * NEAR)
        r = await self.client.post("/bounties", json={"bounty_id": self.bid, "target_url": "http://target.local"})
        assert r.status_code == 200, r.text
        self.token, self.poster_key = r.json()["ownership_token"], r.json()["poster_key"]
        if verified:
            assert (await self.client.post(f"/bounties/{self.bid}/verify")).status_code == 200

    async def attacker(self, name: str, credit: int = NEAR) -> tuple[str, dict]:
        acct = await self.chain.create_account(name, 20 * NEAR)
        await self.chain.register_attacker(acct)
        if credit:
            await self.chain.deposit_credit(acct, credit)
        r = await self.client.post("/attackers", json={"account": acct})
        assert r.status_code == 200, r.text
        return acct, {"X-API-Key": r.json()["api_key"]}

    async def attempt(self, headers, content="hello", channel="chat", kind="chat"):
        return await self.client.post(f"/bounties/{self.bid}/attempts", headers=headers,
                                      json={"channel": channel, "kind": kind, "content": content})


@pytest.fixture
async def world():
    w = World()
    yield w
    await w.client.aclose()
    await w.target_client.aclose()
