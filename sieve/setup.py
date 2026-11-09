"""Deploy Sieve to testnet: contract, attested model signers, a demo Sputnik DAO and two rounds."""
from __future__ import annotations

import json
import time
from importlib import resources
from pathlib import Path

import httpx

from sieve.attest import model_signers
from sieve.config import REVIEW_MODELS
from sieve.near import NEAR, TESTNET_RPC, WASM_PATH, Near

DEPLOYMENTS = Path(__file__).resolve().parents[1] / "deployments"
SIGNER_LIFETIME_MS = 30 * 24 * 3600 * 1000
DAO_BOND = NEAR // 10


def prompt(name: str) -> str:
    return resources.files("sieve.prompts").joinpath(f"{name}.txt").read_text()


def account_exists(account_id: str) -> bool:
    r = httpx.post(TESTNET_RPC, json={"jsonrpc": "2.0", "id": 1, "method": "query", "params": {
        "request_type": "view_account", "finality": "final", "account_id": account_id}}, timeout=30)
    return "result" in r.json()


def deployment(network: str = "testnet") -> dict:
    return json.loads((DEPLOYMENTS / f"{network}.json").read_text())


async def setup(operator: str, name: str = "sieve", dao_name: str = "sieve-demo") -> dict:
    near = await Near.testnet(operator)
    try:
        contract = f"{name}.{operator}"
        if account_exists(contract):
            raise SystemExit(f"{contract} already exists; pass --name to deploy a fresh contract")
        await near.create_account(contract, 7 * NEAR)
        await near.deploy(contract, WASM_PATH.read_bytes(), {"owner": operator})
        print(f"contract {contract}")

        expires = int(time.time() * 1000) + SIGNER_LIFETIME_MS
        signers = model_signers(REVIEW_MODELS)
        for model, key in signers.items():
            await near.call(operator, contract, "register_signer", {"public_key_hex": key, "model": model, "expires_ms": expires})

        dao = f"{dao_name}.sputnikv2.testnet"
        if not account_exists(dao):
            dao = await near.create_dao(dao_name, [operator], contract, proposal_bond=DAO_BOND, funds=7 * NEAR)
        print(f"dao {dao}")

        models = list(REVIEW_MODELS)
        grant = await near.call(operator, contract, "create_round", {
            "kind": "Grant", "dao": dao, "system": prompt("grant_v1"), "models": models, "threshold": 7,
            "tranche": str(NEAR), "dao_bond": str(DAO_BOND), "window_ms": 600_000}, deposit=NEAR)
        honeypot = await near.call(operator, contract, "create_round", {
            "kind": "Honeypot", "dao": dao, "system": prompt("honeypot_v1"), "models": models, "threshold": 7,
            "tranche": "0", "dao_bond": "0", "window_ms": 600_000}, deposit=2 * NEAR)
        out = {"network": "testnet", "contract": contract, "operator": operator, "dao": dao,
               "rounds": {"grant": grant, "honeypot": honeypot}, "signers": signers}
        DEPLOYMENTS.mkdir(exist_ok=True)
        (DEPLOYMENTS / "testnet.json").write_text(json.dumps(out, indent=2) + "\n")
        print(json.dumps(out["rounds"]))
        return out
    finally:
        await near.close()
