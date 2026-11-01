"""In-memory chain mirroring the escrow contract's rules exactly. Gas is not modelled."""
from __future__ import annotations

from dataclasses import replace

from redswarm.chain.base import Bounty, ChainError, Lead, PayResult, secret_hash


class FakeChain:
    def __init__(self) -> None:
        self.operator = "operator.test.near"
        self._balances: dict[str, int] = {self.operator: 0}
        self._bounties: dict[int, Bounty] = {}
        self._attackers: set[str] = set()
        self._credits: dict[str, int] = {}
        self._fees: dict[str, int] = {}
        self._leads: dict[int, Lead] = {}
        self._unlocked: set[tuple[int, str]] = set()
        self._next_bounty = 1
        self._next_lead = 1

    # -- accounts ---------------------------------------------------------
    async def create_account(self, name: str, funds: int) -> str:
        account = f"{name}.test.near"
        if account in self._balances:
            raise ChainError(f"account exists: {account}")
        self._balances[account] = funds
        return account

    async def balance(self, account: str) -> int:
        return self._balances[account]

    async def close(self) -> None:
        return None

    def _debit(self, account: str, amount: int) -> None:
        if self._balances.get(account, 0) < amount:
            raise ChainError(f"{account} cannot afford {amount}")
        self._balances[account] -= amount

    def _credit(self, account: str, amount: int) -> None:
        self._balances[account] = self._balances.get(account, 0) + amount

    def _bounty(self, bounty_id: int) -> Bounty:
        b = self._bounties.get(bounty_id)
        if b is None:
            raise ChainError("no such bounty")
        return b

    # -- bounties ---------------------------------------------------------
    async def post_bounty(self, poster, target, payees, secret_hash, amount):
        if amount <= 0:
            raise ChainError("attach a deposit to fund the bounty")
        self._debit(poster, amount)
        bid, self._next_bounty = self._next_bounty, self._next_bounty + 1
        self._bounties[bid] = Bounty(bid, poster, target, list(payees), secret_hash, amount, "open", None)
        return bid

    async def set_payees(self, poster, bounty_id, payees):
        b = self._bounty(bounty_id)
        if poster != b.poster:
            raise ChainError("only the poster can change payees")
        if b.status != "open":
            raise ChainError("bounty is not open")
        self._bounties[bounty_id] = replace(b, payees=list(payees))

    async def close_bounty(self, poster, bounty_id):
        b = self._bounty(bounty_id)
        if poster != b.poster:
            raise ChainError("only the poster can close")
        if b.status != "open":
            raise ChainError("bounty is not open")
        self._credit(poster, b.balance)
        self._bounties[bounty_id] = replace(b, balance=0, status="closed")

    async def get_bounty(self, bounty_id):
        return self._bounties.get(bounty_id)

    # -- attackers --------------------------------------------------------
    async def register_attacker(self, account):
        self._attackers.add(account)

    async def is_attacker(self, account):
        return account in self._attackers

    # -- breaks -----------------------------------------------------------
    async def pay(self, target, bounty_id, receiver, amount, invoice_ref):
        b = self._bounty(bounty_id)
        if target != b.target:
            raise ChainError("only the target can pay")
        refused = PayResult("refused", None, 0)
        if b.status != "open" or amount <= 0 or amount > b.balance:
            return refused
        if receiver in b.payees:
            self._credit(receiver, amount)
            self._bounties[bounty_id] = replace(b, balance=b.balance - amount)
            return PayResult("paid", receiver, amount)
        if receiver in self._attackers:
            self._credit(receiver, b.balance)
            self._bounties[bounty_id] = replace(b, balance=0, status="broken", winner=receiver)
            return PayResult("break", receiver, b.balance)
        return refused

    async def claim_secret(self, attacker, bounty_id, secret, salt):
        if attacker not in self._attackers:
            raise ChainError("register as an attacker first")
        b = self._bounty(bounty_id)
        if b.status != "open" or secret_hash(secret, salt) != b.secret_hash:
            return False
        self._credit(attacker, b.balance)
        self._bounties[bounty_id] = replace(b, balance=0, status="broken", winner=attacker)
        return True

    # -- credit and fees --------------------------------------------------
    async def deposit_credit(self, account, amount):
        if amount <= 0:
            raise ChainError("attach a deposit")
        self._debit(account, amount)
        self._credits[account] = self._credits.get(account, 0) + amount

    async def get_credit(self, account):
        return self._credits.get(account, 0)

    async def record_fees(self, bounty_id, charges):
        poster = self._bounty(bounty_id).poster
        credits = dict(self._credits)
        total = 0
        for account, fee in charges:
            if credits.get(account, 0) < fee:
                raise ChainError("insufficient credit")
            credits[account] -= fee
            total += fee
        self._credits = credits
        self._fees[poster] = self._fees.get(poster, 0) + total

    async def withdraw_fees(self, poster):
        owed, self._fees[poster] = self._fees.get(poster, 0), 0
        self._credit(poster, owed)
        return owed

    # -- leads ------------------------------------------------------------
    async def post_lead(self, author, bounty_id, title, price, content_hash):
        if author not in self._attackers:
            raise ChainError("register as an attacker first")
        self._bounty(bounty_id)
        lid, self._next_lead = self._next_lead, self._next_lead + 1
        self._leads[lid] = Lead(lid, bounty_id, author, title, price, content_hash)
        return lid

    async def get_lead(self, lead_id):
        return self._leads.get(lead_id)

    async def unlock_lead(self, buyer, lead_id):
        lead = self._leads.get(lead_id)
        if lead is None:
            raise ChainError("no such lead")
        if await self.is_unlocked(lead_id, buyer):
            raise ChainError("already unlocked")
        self._debit(buyer, lead.price)
        self._credit(lead.author, lead.price)
        self._unlocked.add((lead_id, buyer))

    async def is_unlocked(self, lead_id, account):
        lead = self._leads.get(lead_id)
        return lead is not None and (lead.author == account or (lead_id, account) in self._unlocked)
