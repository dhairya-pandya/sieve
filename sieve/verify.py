"""Re-check every review on chain without an API key.

For each review event the contract emitted, rebuild the request from the on-chain proposal and
round (with sieve/request.py, independently of the contract), check that it matches what the
contract asked for, check the model's ed25519 signature over request and response hashes, check
that the key is registered for that model, and re-read the score from the signed answer.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import os
import json

import httpx
from nacl.exceptions import BadSignatureError
from nacl.signing import VerifyKey

from sieve.nearai import parse_review, signed_text
from sieve.request import build_request

NEARBLOCKS = "https://api-testnet.nearblocks.io/v3"
ARCHIVAL_RPC = "https://archival-rpc.testnet.near.org"
RPC = os.environ.get("SIEVE_RPC", "https://rpc.testnet.fastnear.com")


def check_review(event: dict, request: bytes, signers: dict[str, str]) -> str:
    """'OK' or the first reason the review does not verify. `signers` maps key hex to model."""
    if not event.get("response"):
        return "answer missing from the transaction"
    if signers.get(event["public_key"]) != event["model"]:
        return "key not registered for model"
    response = base64.b64decode(event["response"])
    text = signed_text(event["model"], request, response)
    try:
        VerifyKey(bytes.fromhex(event["public_key"])).verify(text.encode(), bytes.fromhex(event["signature"]))
    except (BadSignatureError, ValueError):
        return "signature does not match"
    try:
        score = parse_review(response).score
    except ValueError:
        return "signed answer is not a review"
    if score != event["score"]:
        return "event score differs from signed answer"
    return "OK"


def local_request(event: dict, proposal: dict, round_: dict) -> bytes:
    """Rebuild, independently of the contract, the request a review event answered, for whichever stage it was."""
    stage = event.get("stage", 0)
    if stage == proposal.get("stage", 0):
        seed, record, evidence = proposal["seed"], proposal["record"], proposal.get("evidence")
    else:
        past = proposal["past"][stage]
        seed, record, evidence = past["seed"], past["record"], past["evidence"]
    system = round_["system"] if stage == 0 else round_["milestone_system"]
    rec = (record["days"], record["submitted"], record["passed"], record["delivered"])
    return build_request(event["model"], system, proposal["round_id"], event["proposal_id"], proposal["title"],
                         proposal["body"], seed, record=rec, stage=stage, evidence=evidence)


def _rpc(url: str, method: str, params) -> dict:
    r = httpx.post(url, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params}, timeout=60)
    body = r.json()
    if "error" in body:
        raise RuntimeError(json.dumps(body["error"])[:300])
    return body["result"]


def view(contract: str, method: str, args: dict | None = None):
    res = _rpc(RPC, "query", {"request_type": "call_function", "finality": "final", "account_id": contract,
                              "method_name": method,
                              "args_base64": base64.b64encode(json.dumps(args or {}).encode()).decode()})
    return json.loads(bytes(res["result"]))


def review_transactions(contract: str) -> list[tuple[str, str]]:
    """(tx hash, signer) of every successful post_review call, oldest first, from NearBlocks."""
    out, cursor = [], None
    while True:
        params = {"limit": 100, "method": "post_review"}
        if cursor:
            params["cursor"] = cursor
        d = httpx.get(f"{NEARBLOCKS}/accounts/{contract}/txns", params=params, timeout=60).json()
        for t in d.get("data") or []:
            if t.get("outcomes", {}).get("status") and any(a.get("method") == "post_review" for a in t.get("actions", [])):
                out.append((t["transaction_hash"], t["signer_account_id"]))
        cursor = (d.get("meta") or {}).get("next_page") or (d.get("meta") or {}).get("cursor")
        if not cursor or not d.get("data"):
            return list(reversed(out))


def events_from_tx(tx: dict) -> list[dict]:
    """Review events of one transaction, each with the answer bytes (base64) under "response".

    Newer contracts log only the answer's hash; the answer is taken from the post_review call's own
    arguments and kept only if it matches the logged hash (else "response" is None). Older ones logged it.
    """
    args = []
    for action in tx["transaction"]["actions"]:
        call = action.get("FunctionCall") if isinstance(action, dict) else None
        if call and call.get("method_name") == "post_review":
            args.append(json.loads(base64.b64decode(call["args"])))
    events = []
    for r in tx["receipts_outcome"]:
        for line in r["outcome"]["logs"]:
            if not line.startswith("EVENT_JSON:"):
                continue
            e = json.loads(line[len("EVENT_JSON:"):])
            if e.get("standard") != "sieve" or e.get("event") != "review":
                continue
            for d in e["data"]:
                if "response_hash" in d and "response" not in d:
                    match = next((a["response"] for a in args if a.get("proposal_id") == d["proposal_id"]
                                  and a.get("slot") == d["slot"]
                                  and hashlib.sha256(base64.b64decode(a["response"])).hexdigest() == d["response_hash"]), None)
                    d = dict(d, response=match)
                events.append(d)
    return events


def review_events(tx_hash: str, signer: str) -> list[dict]:
    return events_from_tx(_rpc(ARCHIVAL_RPC, "tx", {"tx_hash": tx_hash, "sender_account_id": signer, "wait_until": "FINAL"}))


def verify(contract: str, round_id: int | None = None) -> int:
    rows, failures = [], 0
    signers: dict[str, str] = {}
    rounds: dict[int, dict] = {}
    for tx_hash, signer in review_transactions(contract):
        for e in review_events(tx_hash, signer):
            p = view(contract, "get_proposal", {"proposal_id": e["proposal_id"]})
            if round_id is not None and p["round_id"] != round_id:
                continue
            if p["round_id"] not in rounds:
                rounds[p["round_id"]] = view(contract, "get_round", {"round_id": p["round_id"]})
            r = rounds[p["round_id"]]
            if e["public_key"] not in signers:
                s = view(contract, "get_signer", {"public_key_hex": e["public_key"]})
                signers[e["public_key"]] = s["model"] if s else ""
            local = local_request(e, p, r)
            onchain = base64.b64decode(view(contract, "stage_request",
                                            {"proposal_id": e["proposal_id"], "stage": e.get("stage", 0), "slot": e["slot"]}))
            status = "request differs from contract" if local != onchain else check_review(e, local, signers)
            failures += status != "OK"
            rows.append((e["proposal_id"], e["slot"], e["model"], e["score"], status, tx_hash))
    print(f"{'proposal':>8} {'slot':>4}  {'model':<38} {'score':>5}  status")
    for pid, slot, model, score, status, tx in rows:
        print(f"{pid:>8} {slot:>4}  {model:<38} {score:>5}  {status}   tx {tx}")
    print(f"\n{len(rows)} reviews checked, {failures} failed")
    return 1 if failures or not rows else 0
