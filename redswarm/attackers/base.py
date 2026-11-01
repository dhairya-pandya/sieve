from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

import httpx


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


@dataclass
class Attacker:
    account: str
    api_key: str
    strategy: Strategy
    client: ArenaClient
    leads: list[str] = field(default_factory=list)

    async def run(self, bounty_id: int, max_attempts: int) -> AttackSummary:
        history: list[Exchange] = []
        while len(history) < max_attempts:
            spec = self.strategy.next_message(history, self.leads)
            if spec is None:
                return AttackSummary(len(history), False, "strategy_done")
            code, body = await self.client.attempt(bounty_id, self.api_key, spec)
            if code == 200:
                history.append(Exchange(spec, body["status"], body["reply"], body["outcome"]))
                if body["outcome"] == "break":
                    return AttackSummary(len(history), True, "broke_it")
            elif code == 402:
                return AttackSummary(len(history), False, "no_credit")
            elif code == 409 and body.get("detail") == "bounty_closed":
                return AttackSummary(len(history), False, "bounty_closed")
            elif code == 429:
                return AttackSummary(len(history), False, "rate_limited")
            else:
                return AttackSummary(len(history), False, "error")
        return AttackSummary(len(history), False, "max_attempts")
