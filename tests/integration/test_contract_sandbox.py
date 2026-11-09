import asyncio
import base64
import json

import pytest
from nacl.signing import SigningKey

from sieve.near import NEAR, ChainError
from sieve.nearai import signed_text

pytestmark = pytest.mark.slow

MODELS = ["model-a", "model-b", "model-c"]
KEYS = [SigningKey(bytes([i + 1]) * 32) for i in range(3)]
WINDOW_MS = 20_000


async def _setup_round(chain, d, dao: str) -> int:
    for k, m in zip(KEYS, MODELS):
        await chain.call(d["root"], d["sieve"], "register_signer",
                         {"public_key_hex": k.verify_key.encode().hex(), "model": m, "expires_ms": 2**62})
    return await chain.call(d["root"], d["sieve"], "create_round", {
        "kind": "Grant", "dao": dao, "system": "rubric", "models": MODELS, "threshold": 7,
        "tranche": str(NEAR), "dao_bond": str(NEAR // 10), "window_ms": WINDOW_MS}, deposit=NEAR)


async def _review_all(chain, d, pid: int, score: int) -> None:
    for slot, (k, m) in enumerate(zip(KEYS, MODELS)):
        req = base64.b64decode(await chain.view(d["sieve"], "review_request", {"proposal_id": pid, "slot": slot}))
        resp = json.dumps({"id": "x", "choices": [{"message": {"content": json.dumps({"score": score, "flags": []})}}]}).encode()
        sig = k.sign(signed_text(m, req, resp).encode()).signature.hex()
        await chain.call(d["root"], d["sieve"], "post_review", {
            "proposal_id": pid, "slot": slot, "response": base64.b64encode(resp).decode(),
            "signature_hex": sig, "public_key_hex": k.verify_key.encode().hex()})


async def test_grant_round_files_dao_proposal(chain, deployed):
    d = deployed
    rid = await _setup_round(chain, d, d["dao"])
    before = await chain.view(d["dao"], "get_last_proposal_id")
    pid = await chain.call(d["applicant"], d["sieve"], "submit",
                           {"round_id": rid, "title": "DAO vote indexer", "body": "Six weeks, 4,000 USDC."}, deposit=NEAR // 10)
    await _review_all(chain, d, pid, 8)
    await asyncio.sleep(WINDOW_MS / 1000 + 2)
    outcome = await chain.call(d["root"], d["sieve"], "finalize", {"proposal_id": pid})
    assert outcome["passed"] and outcome["median"] == 8
    assert await chain.view(d["dao"], "get_last_proposal_id") == before + 1
    prop = await chain.view(d["dao"], "get_proposal", {"id": before})
    assert prop["kind"]["Transfer"]["receiver_id"] == d["applicant"]
    assert prop["kind"]["Transfer"]["amount"] == str(NEAR)
    p = await chain.view(d["sieve"], "get_proposal", {"proposal_id": pid})
    assert p["finalized"] and p["outcome"]["dao_proposal_id"] == before


async def test_failed_dao_call_is_retryable(chain, deployed):
    d = deployed
    other = await chain.create_dao("closed", [d["root"]], f"nobody.{d['root']}")  # Sieve has no role here
    rid = await _setup_round(chain, d, other)
    pid = await chain.call(d["applicant"], d["sieve"], "submit",
                           {"round_id": rid, "title": "t", "body": "b"}, deposit=NEAR // 10)
    await _review_all(chain, d, pid, 9)
    await asyncio.sleep(WINDOW_MS / 1000 + 2)
    try:
        await chain.call(d["root"], d["sieve"], "finalize", {"proposal_id": pid})
    except ChainError:
        pass
    p = await chain.view(d["sieve"], "get_proposal", {"proposal_id": pid})
    assert not p["finalized"] and not p["pending"]
    assert (await chain.view(d["sieve"], "get_round", {"round_id": rid}))["bonds"] == str(NEAR)
