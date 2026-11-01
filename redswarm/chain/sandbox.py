"""Chain backed by the real escrow contract, on a local NEAR sandbox node or on testnet."""
from __future__ import annotations

import asyncio
import base64
import json
from pathlib import Path

import base58
from nacl import signing
from py_near.account import Account

from redswarm.chain import sandbox_bootstrap as sb
from redswarm.chain.base import NEAR, Bounty, ChainError, Lead, PayResult

WASM_PATH = Path(__file__).resolve().parents[2] / "contract" / "redswarm_escrow.wasm"


def _new_keypair() -> tuple[str, str]:
    sk = signing.SigningKey.generate()
    seed, pub = sk.encode(), sk.verify_key.encode()
    return "ed25519:" + base58.b58encode(seed + pub).decode(), "ed25519:" + base58.b58encode(pub).decode()


def _bounty(d: dict | None) -> Bounty | None:
    if d is None:
        return None
    return Bounty(d["id"], d["poster"], d["target"], d["payees"], d["secret_hash"],
                  int(d["balance"]), d["status"], d["winner"])


class SandboxChain:
    """All accounts are sub-accounts of `root_account`; keys live in memory only.

    `tag` is appended to every account name so repeated runs on a shared network (testnet)
    never collide. It is empty on the sandbox, which starts fresh each time.
    """

    def __init__(self, node: sb.SandboxNode | None, root: Account, rpc_url: str, root_account: str, tag: str = ""):
        self._node, self._root, self._rpc_url = node, root, rpc_url
        self._suffix, self._tag = root_account, tag
        self.escrow = f"escrow{tag}.{root_account}"
        self.operator = f"operator{tag}.{root_account}"
        self._accounts: dict[str, Account] = {}

    @classmethod
    async def start(cls) -> "SandboxChain":
        node = await asyncio.to_thread(sb.start_node)
        try:
            root = Account(node.root_account, node.root_key, rpc_addr=node.rpc_url)
            await root.startup()
            chain = cls(node, root, node.rpc_url, node.root_account)
            await chain._deploy(100 * NEAR, 10 * NEAR)
            return chain
        except BaseException:
            await asyncio.to_thread(node.stop)
            raise

    @classmethod
    async def connect(cls, rpc_url: str, root_account: str, root_key: str, tag: str | None = None) -> "SandboxChain":
        """Use an existing network (testnet). `root_account` pays for everything, so fund it first.
        NOT exercised by the automated tests: it needs a funded testnet account."""
        import secrets

        root = Account(root_account, root_key, rpc_addr=rpc_url)
        await root.startup()
        chain = cls(None, root, rpc_url, root_account, tag if tag is not None else "-" + secrets.token_hex(2))
        await chain._deploy(20 * NEAR, 2 * NEAR)
        return chain

    async def _deploy(self, escrow_funds: int, operator_funds: int) -> None:
        escrow = await self._new_account(self.escrow, escrow_funds)
        await self._new_account(self.operator, operator_funds)
        await escrow.deploy_contract(WASM_PATH.read_bytes())
        await self._check(await escrow.function_call(self.escrow, "new", {"operator": self.operator}))

    async def _new_account(self, account_id: str, funds: int) -> Account:
        priv, pub = _new_keypair()
        await self._root.create_account(account_id, pub, funds)
        acc = Account(account_id, priv, rpc_addr=self._rpc_url)
        await acc.startup()
        self._accounts[account_id] = acc
        return acc

    @staticmethod
    async def _check(result):
        status = result.status
        if "Failure" in status:
            raise ChainError(json.dumps(status["Failure"])[:300])
        value = status.get("SuccessValue") or ""
        return json.loads(base64.b64decode(value)) if value else None

    async def _call(self, caller: str, method: str, args: dict, deposit: int = 0):
        acc = self._accounts[caller]
        return await self._check(await acc.function_call(self.escrow, method, args, amount=deposit))

    async def _view(self, method: str, args: dict):
        return (await self._root.view_function(self.escrow, method, args)).result

    # -- accounts ---------------------------------------------------------
    async def create_account(self, name: str, funds: int) -> str:
        account_id = f"{name}{self._tag}.{self._suffix}"
        await self._new_account(account_id, funds)
        return account_id

    async def balance(self, account: str) -> int:
        return await self._root.get_balance(account)

    async def close(self) -> None:
        for acc in [self._root, *self._accounts.values()]:
            try:
                await acc.shutdown()
            except Exception:
                pass
        if self._node is not None:
            await asyncio.to_thread(self._node.stop)

    # -- bounties ---------------------------------------------------------
    async def post_bounty(self, poster, target, payees, secret_hash, amount):
        return await self._call(poster, "post_bounty",
                                {"target": target, "payees": payees, "secret_hash": secret_hash}, amount)

    async def set_payees(self, poster, bounty_id, payees):
        await self._call(poster, "set_payees", {"bounty_id": bounty_id, "payees": payees})

    async def close_bounty(self, poster, bounty_id):
        await self._call(poster, "close_bounty", {"bounty_id": bounty_id})

    async def get_bounty(self, bounty_id):
        return _bounty(await self._view("get_bounty", {"bounty_id": bounty_id}))

    # -- attackers --------------------------------------------------------
    async def register_attacker(self, account):
        await self._call(account, "register_attacker", {})

    async def is_attacker(self, account):
        return await self._view("is_attacker", {"account": account})

    # -- breaks -----------------------------------------------------------
    async def pay(self, target, bounty_id, receiver, amount, invoice_ref):
        r = await self._call(target, "pay", {"bounty_id": bounty_id, "receiver": receiver,
                                             "amount": str(amount), "invoice_ref": invoice_ref})
        return PayResult(r["outcome"], r["paid_to"], int(r["amount"]))

    async def claim_secret(self, attacker, bounty_id, secret, salt):
        return await self._call(attacker, "claim_secret",
                                {"bounty_id": bounty_id, "secret": secret, "salt": salt})

    # -- credit and fees --------------------------------------------------
    async def deposit_credit(self, account, amount):
        await self._call(account, "deposit_credit", {}, amount)

    async def get_credit(self, account):
        return int(await self._view("get_credit", {"account": account}))

    async def record_fees(self, bounty_id, charges):
        await self._call(self.operator, "record_fees",
                         {"bounty_id": bounty_id, "charges": [[a, str(f)] for a, f in charges]})

    async def withdraw_fees(self, poster):
        return int(await self._call(poster, "withdraw_fees", {}))

    # -- leads ------------------------------------------------------------
    async def post_lead(self, author, bounty_id, title, price, content_hash):
        return await self._call(author, "post_lead", {"bounty_id": bounty_id, "title": title,
                                                      "price": str(price), "content_hash": content_hash})

    async def get_lead(self, lead_id):
        d = await self._view("get_lead", {"lead_id": lead_id})
        if d is None:
            return None
        return Lead(d["id"], d["bounty_id"], d["author"], d["title"], int(d["price"]), d["content_hash"])

    async def unlock_lead(self, buyer, lead_id):
        lead = await self.get_lead(lead_id)
        if lead is None:
            raise ChainError("no such lead")
        await self._call(buyer, "unlock_lead", {"lead_id": lead_id}, lead.price)

    async def is_unlocked(self, lead_id, account):
        return await self._view("is_unlocked", {"lead_id": lead_id, "account": account})
