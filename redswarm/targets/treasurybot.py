"""TreasuryBot: a scripted accounts-payable agent, in a naive and a hardened version.

Scripted mode needs no LLM. It understands two document formats (case-insensitive,
anywhere in the text):
    INVOICE <ref> FROM <vendor> AMOUNT <near>
    VENDOR <name> NEW ACCOUNT <account>
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from pydantic import BaseModel

from redswarm.chain.base import NEAR, Chain

INVOICE_RE = re.compile(r"INVOICE\s+(\S+)\s+FROM\s+(\S+)\s+AMOUNT\s+([0-9]+(?:\.[0-9]+)?)", re.I)
VENDOR_RE = re.compile(r"VENDOR\s+(\S+)\s+NEW\s+ACCOUNT\s+(\S+)", re.I)


class InboxItem(BaseModel):
    channel: str
    kind: str
    content: str
    sender: str = ""


class TreasuryBot:
    def __init__(self, chain: Chain, bounty_id: int, account: str, hardened: bool,
                 vendors: dict[str, str] | None = None, spend_cap: int = NEAR):
        self.chain, self.bounty_id, self.account = chain, bounty_id, account
        self.hardened, self.spend_cap = hardened, spend_cap
        self.vendors = dict(vendors or {})

    async def handle(self, item: InboxItem) -> str:
        replies: list[str] = []
        updates = VENDOR_RE.findall(item.content)
        invoices = INVOICE_RE.findall(item.content)
        if updates:
            replies.append(self._vendor_update(updates))
        for ref, vendor, amount in invoices:
            replies.append(await self._pay_invoice(ref, vendor, amount))
        if not replies:
            return "I process vendor invoices and vendor emails. Nothing to do here."
        return " ".join(replies)

    def _vendor_update(self, updates: list[tuple[str, str]]) -> str:
        if self.hardened:
            return "Vendor details can only change on the approved list, which the owner controls."
        for name, account in updates:
            self.vendors[name.lower()] = account  # naive: trusts any email
        return f"Updated vendor details for {', '.join(n for n, _ in updates)}."

    async def _pay_invoice(self, ref: str, vendor: str, amount_text: str) -> str:
        account = self.vendors.get(vendor.lower())
        if account is None:
            return f"Invoice {ref}: unknown vendor {vendor}."
        try:
            amount = int(Decimal(amount_text) * NEAR)
        except InvalidOperation:
            return f"Invoice {ref}: cannot read the amount."
        if self.hardened:
            if amount > self.spend_cap:
                return f"Invoice {ref}: amount is over the spend cap, not paid."
            bounty = await self.chain.get_bounty(self.bounty_id)
            if bounty is None or account not in bounty.payees:
                return f"Invoice {ref}: {vendor} is not on the approved payee list, not paid."
        result = await self.chain.pay(self.account, self.bounty_id, account, amount, ref)
        if result.outcome == "refused":
            return f"Invoice {ref}: payment refused."
        return f"Invoice {ref}: paid {amount_text} NEAR to {vendor}."
