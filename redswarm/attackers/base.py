from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

import asyncio
import inspect

import httpx

from redswarm.chain.base import Chain, content_hash


@dataclass(frozen=True)
class AttemptSpec:
    channel: str  # "chat" | "document"
    kind: str  # "chat" | "invoice" | "email"
    content: str


@dataclass
class Exchange:
    spec: AttemptSpec
    status: str
    reply: str | None
    outcome: str


@dataclass
class AttackSummary:
    attempts: int
    broke: bool
    stopped: str  # strategy_done | broke_it | no_credit | bounty_closed | rate_limited | max_attempts | error


class Strategy(Protocol):
    def next_message(self, history: list[Exchange], leads: list[str]) -> AttemptSpec | None:
        """Return the next attempt, or None when the strategy has nothing more to try.
        Strategies keep no state of their own: everything comes from `history` and `leads`."""


class ArenaClient:
    """Thin wrapper over the arena HTTP API. Works against a real server or in process via ASGI."""

    def __init__(self, http: httpx.AsyncClient):
        self.http = http

    async def register_attacker(self, account: str) -> str:
        r = await self.http.post("/attackers", json={"account": account})
        r.raise_for_status()
        return r.json()["api_key"]

    async def attempt(self, bounty_id: int, api_key: str, spec: AttemptSpec) -> tuple[int, dict]:
        r = await self.http.post(
            f"/bounties/{bounty_id}/attempts", headers={"X-API-Key": api_key},
            json={"channel": spec.channel, "kind": spec.kind, "content": spec.content})
        try:
            body = r.json()
        except ValueError:
            body = {}
        return r.status_code, body


    async def publish_lead(self, bounty_id: int, api_key: str, lead_id: int, content: str) -> None:
        r = await self.http.post(f"/bounties/{bounty_id}/leads", headers={"X-API-Key": api_key},
                                 json={"lead_id": lead_id, "content": content})
        r.raise_for_status()

    async def lead_content(self, api_key: str, lead_id: int) -> str:
        r = await self.http.get(f"/leads/{lead_id}/content", headers={"X-API-Key": api_key})
        r.raise_for_status()
        return r.json()["content"]

    async def list_leads(self) -> list[dict]:
        return (await self.http.get("/leads")).json()


@dataclass
class Attacker:
    account: str
    api_key: str
    strategy: Strategy
    client: ArenaClient
    leads: list[str] = field(default_factory=list)
    chain: Chain | None = None
    pause: float = 0.0  # seconds between attempts, so a live page is watchable

    async def post_lead(self, bounty_id: int, title: str, price: int, content: str) -> int:
        """Sell a lead: commit its hash on chain, then hand the content to the arena."""
        lead_id = await self.chain.post_lead(self.account, bounty_id, title, price, content_hash(content))
        await self.client.publish_lead(bounty_id, self.api_key, lead_id, content)
        return lead_id

    async def buy_lead(self, lead_id: int) -> str:
        """Pay for a lead on chain, fetch it from the arena, and check it against the posted hash."""
        await self.chain.unlock_lead(self.account, lead_id)
        content = await self.client.lead_content(self.api_key, lead_id)
        lead = await self.chain.get_lead(lead_id)
        if content_hash(content) != lead.content_hash:
            raise ValueError("arena served content that does not match the on-chain hash")
        self.leads.append(content)
        return content

    async def run(self, bounty_id: int, max_attempts: int) -> AttackSummary:
        history: list[Exchange] = []
        while len(history) < max_attempts:
            spec = self.strategy.next_message(history, self.leads)
            if inspect.isawaitable(spec):  # LLM-driven strategies are async
                spec = await spec
            if spec is None:
                return AttackSummary(len(history), False, "strategy_done")
            code, body = await self.client.attempt(bounty_id, self.api_key, spec)
            if code == 200:
                history.append(Exchange(spec, body["status"], body["reply"], body["outcome"]))
                if body["outcome"] == "break":
                    return AttackSummary(len(history), True, "broke_it")
                if self.pause:
                    await asyncio.sleep(self.pause)
            elif code == 402:
                return AttackSummary(len(history), False, "no_credit")
            elif code == 409 and body.get("detail") == "bounty_closed":
                return AttackSummary(len(history), False, "bounty_closed")
            elif code == 429:
                return AttackSummary(len(history), False, "rate_limited")
            else:
                return AttackSummary(len(history), False, "error")
        return AttackSummary(len(history), False, "max_attempts")
