"""Thin async NEAR client over py-near for the local sandbox and testnet."""
from __future__ import annotations

import asyncio
import base64
import json
import os
from pathlib import Path

import base58
import httpx
from nacl import signing
from py_near.account import Account

from sieve.chain import sandbox_bootstrap as sb

NEAR = 10**24
TGAS = 10**12
TESTNET_RPC = "https://rpc.testnet.near.org"
SPUTNIK_FACTORY = "sputnikv2.testnet"
# Any DAO deployed by the testnet factory runs the factory's default Sputnik v2 code.
SPUTNIK_CODE_SOURCE = "civic-vft8z.sputnikv2.testnet"
CACHE = Path(os.environ.get("SIEVE_CACHE", Path.home() / ".cache" / "sieve"))
WASM_PATH = Path(__file__).resolve().parents[1] / "contract" / "sieve.wasm"


class ChainError(RuntimeError):
    pass


def new_keypair() -> tuple[str, str]:
    sk = signing.SigningKey.generate()
    seed, pub = sk.encode(), sk.verify_key.encode()
    return "ed25519:" + base58.b58encode(seed + pub).decode(), "ed25519:" + base58.b58encode(pub).decode()


def _outcome(result):
    status = result.status
    if "Failure" in status:
        raise ChainError(json.dumps(status["Failure"])[:500])
    for receipt in getattr(result, "receipt_outcome", []) or []:
        st = getattr(receipt, "status", {}) or {}
        if isinstance(st, dict) and "Failure" in st:
            raise ChainError(json.dumps(st["Failure"])[:500])
    value = status.get("SuccessValue") or ""
    return json.loads(base64.b64decode(value)) if value else None


def dao_policy(council: list[str], sieve_contract: str, proposal_bond: int) -> dict:
    """Council can do everything; the Sieve contract may only add Transfer proposals."""
    vote = {"weight_kind": "RoleWeight", "quorum": "0", "threshold": [1, 2]}
    return {
        "roles": [
            {"name": "council", "kind": {"Group": council}, "permissions": ["*:*"], "vote_policy": {}},
            {"name": "sieve", "kind": {"Group": [sieve_contract]}, "permissions": ["transfer:AddProposal"], "vote_policy": {}},
        ],
        "default_vote_policy": vote,
        "proposal_bond": str(proposal_bond),
        "proposal_period": str(7 * 24 * 3600 * 10**9),
        "bounty_bond": str(proposal_bond),
        "bounty_forgiveness_period": str(24 * 3600 * 10**9),
    }


class Near:
    """Accounts this client created or loaded, keyed by account id. Keys stay in memory."""

    def __init__(self, rpc_url: str, root: Account, node: sb.SandboxNode | None = None):
        self.rpc_url, self.root, self._node = rpc_url, root, node
        self.accounts: dict[str, Account] = {root.account_id: root}

    @classmethod
    async def sandbox(cls) -> "Near":
        node = await asyncio.to_thread(sb.start_node)
        root = Account(node.root_account, node.root_key, rpc_addr=node.rpc_url)
        await root.startup()
        return cls(node.rpc_url, root, node)

    @classmethod
    async def testnet(cls, account_id: str, key_path: Path | None = None) -> "Near":
        key_path = key_path or Path.home() / ".near-credentials" / "testnet" / f"{account_id}.json"
        key = json.loads(key_path.read_text())["private_key"]
        root = Account(account_id, key, rpc_addr=TESTNET_RPC)
        await root.startup()
        return cls(TESTNET_RPC, root)

    async def close(self) -> None:
        for acc in self.accounts.values():
            try:
                await acc.shutdown()
            except Exception:
                pass
        if self._node is not None:
            await asyncio.to_thread(self._node.stop)

    async def create_account(self, account_id: str, funds: int) -> str:
        priv, pub = new_keypair()
        await self.root.create_account(account_id, pub, funds)
        acc = Account(account_id, priv, rpc_addr=self.rpc_url)
        await acc.startup()
        self.accounts[account_id] = acc
        return account_id

    async def deploy(self, account_id: str, wasm: bytes, init: dict | None = None, init_method: str = "new") -> None:
        acc = self.accounts[account_id]
        await acc.deploy_contract(wasm)
        if init is not None:
            await self.call(account_id, account_id, init_method, init)

    async def call(self, signer: str, contract: str, method: str, args: dict, deposit: int = 0, gas: int = 300 * TGAS):
        result = await self.accounts[signer].function_call(contract, method, args, gas=gas, amount=deposit)
        return _outcome(result)

    async def view(self, contract: str, method: str, args: dict | None = None):
        return (await self.root.view_function(contract, method, args or {})).result

    async def balance(self, account_id: str) -> int:
        return await self.root.get_balance(account_id)

    async def sputnik_code(self) -> bytes:
        path = CACHE / "sputnikdao2.wasm"
        if not path.exists():
            async with httpx.AsyncClient(timeout=60) as c:
                r = await c.post(TESTNET_RPC, json={"jsonrpc": "2.0", "id": 1, "method": "query", "params": {
                    "request_type": "view_code", "finality": "final", "account_id": SPUTNIK_CODE_SOURCE}})
                code = base64.b64decode(r.json()["result"]["code_base64"])
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(code)
        return path.read_bytes()

    async def create_dao(self, name: str, council: list[str], sieve_contract: str,
                         proposal_bond: int = NEAR // 10, funds: int = 10 * NEAR) -> str:
        """A Sputnik v2 DAO whose policy lets `sieve_contract` add Transfer proposals."""
        init = {"config": {"name": name, "purpose": "Grants reviewed by Sieve", "metadata": ""},
                "policy": dao_policy(council, sieve_contract, proposal_bond)}
        if self._node is not None:
            dao = await self.create_account(f"{name}.{self.root.account_id}", funds)
            await self.deploy(dao, await self.sputnik_code(), init)
            return dao
        args = base64.b64encode(json.dumps(init).encode()).decode()
        await self.call(self.root.account_id, SPUTNIK_FACTORY, "create", {"name": name, "args": args},
                        deposit=funds, gas=150 * TGAS)
        return f"{name}.{SPUTNIK_FACTORY}"
