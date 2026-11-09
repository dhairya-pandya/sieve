import os

import pytest

from sieve.config import REVIEW_MODELS
from sieve.near import NEAR
from sieve.relayer import relay_once
from sieve.setup import deployment, prompt

pytestmark = [pytest.mark.slow, pytest.mark.live,
              pytest.mark.skipif(not os.environ.get("NEAR_AI_API_KEY"), reason="needs NEAR_AI_API_KEY")]


async def test_relay_once_sandbox(chain, deployed):
    d = deployed
    for model, key in deployment()["signers"].items():
        await chain.call(d["root"], d["sieve"], "register_signer", {"public_key_hex": key, "model": model, "expires_ms": 2**62})
    rid = await chain.call(d["root"], d["sieve"], "create_round", {
        "kind": "Grant", "dao": d["dao"], "system": prompt("grant_v1"), "models": list(REVIEW_MODELS),
        "threshold": 7, "tranche": str(NEAR), "dao_bond": str(NEAR // 10), "window_ms": 600_000}, deposit=NEAR)
    pid = await chain.call(d["applicant"], d["sieve"], "submit", {
        "round_id": rid, "title": "Open indexer for Sputnik DAO votes",
        "body": "Six weeks, 4,000 USDC, weekly milestones, public dashboard."}, deposit=NEAR // 10)
    stats = await relay_once(chain, d["sieve"], d["root"])
    assert stats["posted"] == 3, stats
    p = await chain.view(d["sieve"], "get_proposal", {"proposal_id": pid})
    assert all(s is not None for s in p["slots"])
