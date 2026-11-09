"""Relayer: reviews open proposal slots with NEAR AI Cloud and posts the signed results.

Anyone can run one. The contract rebuilds the request and checks the model's key itself,
so the relayer is trusted for nothing except showing up. It never posts a review that is
unsigned, gateway-signed, unparseable or too large; it logs actions, never proposal text.
"""
from __future__ import annotations

import asyncio
import base64
import time
from typing import Callable

from sieve import nearai
from sieve.near import ChainError, Near

MAX_RESPONSE = 9_000
PAGE = 50


def log(msg: str) -> None:
    print(f"{time.strftime('%H:%M:%S')} {msg}", flush=True)


def review_slot(request: bytes, model: str,
                complete: Callable[[bytes], tuple[bytes, str]] = nearai.complete,
                fetch: Callable[[str], nearai.Signature | None] = nearai.fetch_signature,
                ) -> tuple[bytes, nearai.Signature, int] | None:
    """Run one review and return (response, signature, score), or None if it must not be posted."""
    response, chat_id = complete(request)
    if len(response) > MAX_RESPONSE:
        return None
    try:
        review = nearai.parse_review(response)
    except ValueError:
        return None
    sig = fetch(chat_id)
    if sig is None or not nearai.verify_signature(model, request, response, sig):
        return None
    return response, sig, review.score


async def proposals(near: Near, contract: str):
    rounds = await near.view(contract, "round_count")
    for rid in range(rounds):
        round_ = await near.view(contract, "get_round", {"round_id": rid})
        start = 0
        while True:
            page = await near.view(contract, "list_proposals", {"round_id": rid, "from": start, "limit": PAGE})
            for pid, p in page:
                yield rid, round_, pid, p
            if len(page) < PAGE:
                break
            start = page[-1][0] + 1


async def relay_once(near: Near, contract: str, signer: str) -> dict:
    stats = {"posted": 0, "skipped": 0, "finalized": 0}
    now_ms = int(time.time() * 1000)
    async for rid, round_, pid, p in proposals(near, contract):
        if p["finalized"] or p["pending"]:
            continue
        if now_ms > p["submitted_ms"] + round_["window_ms"]:
            if sum(s is not None for s in p["slots"]) >= min(2, len(p["slots"])):
                try:
                    out = await near.call(signer, contract, "finalize", {"proposal_id": pid})
                    log(f"finalized proposal {pid}: {out}")
                    stats["finalized"] += 1
                except ChainError as e:
                    log(f"finalize {pid} failed: {e}")
            continue
        for slot, filled in enumerate(p["slots"]):
            if filled is not None:
                continue
            model = round_["models"][slot]
            request = base64.b64decode(await near.view(contract, "review_request", {"proposal_id": pid, "slot": slot}))
            result = await asyncio.to_thread(review_slot, request, model)
            if result is None:
                log(f"proposal {pid} slot {slot} ({model}): no postable signed review")
                stats["skipped"] += 1
                continue
            response, sig, score = result
            try:
                await near.call(signer, contract, "post_review", {
                    "proposal_id": pid, "slot": slot, "response": base64.b64encode(response).decode(),
                    "signature_hex": sig.signature_hex, "public_key_hex": sig.signing_address})
                log(f"proposal {pid} slot {slot} ({model}): score {score}")
                stats["posted"] += 1
            except ChainError as e:
                log(f"proposal {pid} slot {slot}: post failed: {e}")
                stats["skipped"] += 1
    return stats


async def run(operator: str, contract: str, once: bool, interval: float) -> None:
    near = await Near.testnet(operator)
    try:
        while True:
            stats = await relay_once(near, contract, operator)
            if once:
                log(f"done: {stats}")
                return
            await asyncio.sleep(interval)
    finally:
        await near.close()
