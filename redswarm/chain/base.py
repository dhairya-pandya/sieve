"""Chain interface shared by the in-memory fake and the real NEAR sandbox/testnet."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Protocol

NEAR = 10**24


class ChainError(Exception):
    """A call was rejected by the contract (or its fake)."""


@dataclass(frozen=True)
class PayResult:
    outcome: str  # "paid" | "break" | "refused"
    paid_to: str | None
    amount: int


@dataclass(frozen=True)
class Bounty:
    id: int
    poster: str
    target: str
    payees: list[str]
    secret_hash: str
    balance: int
    status: str  # "open" | "broken" | "closed"
    winner: str | None


@dataclass(frozen=True)
class Lead:
    id: int
    bounty_id: int
    author: str
    title: str
    price: int
    content_hash: str


def secret_hash(secret: str, salt: str) -> str:
    return hashlib.sha256((secret + salt).encode()).hexdigest()


def content_hash(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()


class Chain(Protocol):
    operator: str

    async def create_account(self, name: str, funds: int) -> str: ...
    async def balance(self, account: str) -> int: ...
    async def close(self) -> None: ...

    async def post_bounty(self, poster: str, target: str, payees: list[str], secret_hash: str, amount: int) -> int: ...
    async def set_payees(self, poster: str, bounty_id: int, payees: list[str]) -> None: ...
    async def close_bounty(self, poster: str, bounty_id: int) -> None: ...
    async def get_bounty(self, bounty_id: int) -> Bounty | None: ...

    async def register_attacker(self, account: str) -> None: ...
    async def is_attacker(self, account: str) -> bool: ...

    async def pay(self, target: str, bounty_id: int, receiver: str, amount: int, invoice_ref: str) -> PayResult: ...
    async def claim_secret(self, attacker: str, bounty_id: int, secret: str, salt: str) -> bool: ...

    async def deposit_credit(self, account: str, amount: int) -> None: ...
    async def get_credit(self, account: str) -> int: ...
    async def record_fees(self, bounty_id: int, charges: list[tuple[str, int]]) -> None: ...
    async def withdraw_fees(self, poster: str) -> int: ...

    async def post_lead(self, author: str, bounty_id: int, title: str, price: int, content_hash: str) -> int: ...
    async def get_lead(self, lead_id: int) -> Lead | None: ...
    async def unlock_lead(self, buyer: str, lead_id: int) -> None: ...
    async def is_unlocked(self, lead_id: int, account: str) -> bool: ...


async def make_chain(kind: str) -> Chain:
    """kind is "fake" or "sandbox"."""
    if kind == "fake":
        from redswarm.chain.fake import FakeChain

        return FakeChain()
    if kind == "sandbox":
        from redswarm.chain.sandbox import SandboxChain

        return await SandboxChain.start()
    raise ValueError(f"unknown chain kind: {kind}")
