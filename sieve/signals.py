"""Advisory signals for voters: near-duplicate proposals and applicant accounts created by the same account.
The contract never uses these; they are shown next to each proposal."""
from __future__ import annotations

import math
import time
from collections import defaultdict
from typing import Callable

import httpx

from sieve.config import EMBEDDING_MODEL, load_settings

NEARBLOCKS = "https://api-testnet.nearblocks.io"


def embed(texts: list[str]) -> list[list[float]]:
    s = load_settings()
    r = httpx.post(f"{s.base_url}/embeddings", json={"model": EMBEDDING_MODEL, "input": texts},
                   headers={"Authorization": f"Bearer {s.near_ai_api_key}"}, timeout=60)
    r.raise_for_status()
    return [d["embedding"] for d in sorted(r.json()["data"], key=lambda d: d["index"])]


def _cos(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    return dot / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)) or 1.0)


def duplicates(proposals: list[dict], embed: Callable[[list[str]], list[list[float]]] = embed,
               threshold: float = 0.9) -> dict[int, list[tuple[int, float]]]:
    """For each proposal id, the other proposals at or above `threshold` cosine similarity, most similar first."""
    vectors = embed([p["text"] for p in proposals]) if proposals else []
    out: dict[int, list[tuple[int, float]]] = {p["id"]: [] for p in proposals}
    for i, p in enumerate(proposals):
        for j, q in enumerate(proposals):
            if i != j and (sim := _cos(vectors[i], vectors[j])) >= threshold:
                out[p["id"]].append((q["id"], round(sim, 3)))
        out[p["id"]].sort(key=lambda x: -x[1])
    return out


def _nearblocks(path: str) -> dict:
    return httpx.get(f"{NEARBLOCKS}{path}", timeout=30).json()


def sybil(accounts: list[str], fetch: Callable[[str], dict] = _nearblocks, now_ns: int | None = None) -> dict[str, dict]:
    """Account age and creator for each applicant, and which other applicants share that creator.
    Top-level `testnet`/`near` creators (faucets and wallets) are not treated as shared."""
    now_ns = now_ns or time.time_ns()
    info: dict[str, dict] = {}
    for acc in accounts:
        created = (fetch(f"/v3/accounts/{acc}").get("data") or {}).get("created") or {}
        creator = None
        if created.get("transaction_hash"):
            creator = (fetch(f"/v3/txns/{created['transaction_hash']}").get("data") or {}).get("signer_account_id")
        age = (now_ns - int(created["block_timestamp"])) // (86_400 * 10**9) if created.get("block_timestamp") else None
        info[acc] = {"age_days": age, "created_by": creator}
    by_creator = defaultdict(list)
    for acc, i in info.items():
        if i["created_by"] and "." in i["created_by"]:
            by_creator[i["created_by"]].append(acc)
    for acc, i in info.items():
        i["shares_creator_with"] = [a for a in by_creator.get(i["created_by"], []) if a != acc]
    return info
