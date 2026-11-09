"""Read-only HTTP API over the Sieve contract, plus the static web page.

Every review returned carries the exact request and response bytes and the model signature,
so the page can re-check it in the browser; `verified` is the server's own check, for reference.
"""
from __future__ import annotations

import base64
import os
import threading
import time
from pathlib import Path
from typing import Callable, Protocol

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from sieve import verify as v

WEB = Path(__file__).resolve().parents[1] / "web"
REPORT = Path(__file__).resolve().parents[1] / "results" / "redteam" / "REPORT.md"


class Chain(Protocol):
    contract: str

    def view(self, method: str, args: dict | None = None): ...
    def events(self) -> list[dict]: ...


class LiveChain:
    """Testnet reads through public RPC; review events from NearBlocks and archival RPC, refreshed every 30 s."""

    def __init__(self, contract: str, ttl: float = 30.0):
        self.contract, self._ttl = contract, ttl
        self._events: list[dict] = []
        self._seen: set[str] = set()
        self._at = 0.0
        self._lock = threading.Lock()

    def view(self, method: str, args: dict | None = None):
        return v.view(self.contract, method, args)

    def events(self) -> list[dict]:
        with self._lock:
            if time.time() - self._at > self._ttl:
                for tx, signer in v.review_transactions(self.contract):
                    if tx not in self._seen:
                        self._events += [dict(e, tx=tx) for e in v.review_events(tx, signer)]
                        self._seen.add(tx)
                self._at = time.time()
            return list(self._events)


def live_signals(round_id: int, proposals: list[tuple[int, dict]]) -> dict[int, dict]:
    from sieve import signals
    authors = sorted({p["author"] for _, p in proposals})
    syb = signals.sybil(authors)
    dup: dict[int, list] = {}
    if os.environ.get("NEAR_AI_API_KEY") and len(proposals) > 1:
        dup = signals.duplicates([{"id": pid, "text": p["title"] + "\n" + p["body"]} for pid, p in proposals])
    return {pid: {"duplicates": dup.get(pid, []), "account": syb.get(p["author"], {})} for pid, p in proposals}


def create_app(chain: Chain, signals: Callable[[int, list], dict] = live_signals) -> FastAPI:
    app = FastAPI(title="Sieve API")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"])
    signal_cache: dict[int, tuple[float, dict]] = {}

    def round_signals(round_id: int, proposals: list) -> dict:
        at, data = signal_cache.get(round_id, (0.0, {}))
        if time.time() - at > 300 or any(pid not in data for pid, _ in proposals):
            try:
                data = signals(round_id, proposals)
            except Exception:
                data = {}
            signal_cache[round_id] = (time.time(), data)
        return data

    def all_proposals(round_id: int) -> list:
        out, start = [], 0
        while True:
            page = chain.view("list_proposals", {"round_id": round_id, "from": start, "limit": 50})
            out += [tuple(x) for x in page]
            if len(page) < 50:
                return out
            start = page[-1][0] + 1

    @app.get("/api/rounds")
    def rounds():
        n = chain.view("round_count")
        return {"contract": chain.contract,
                "rounds": [dict(chain.view("get_round", {"round_id": i}), id=i) for i in range(n)]}

    @app.get("/api/rounds/{round_id}")
    def round_detail(round_id: int):
        r = chain.view("get_round", {"round_id": round_id})
        if r is None:
            raise HTTPException(404, "no such round")
        props = all_proposals(round_id)
        sig = round_signals(round_id, props)
        return {"id": round_id, "round": r,
                "proposals": [dict(p, id=pid, signals=sig.get(pid, {})) for pid, p in props]}

    @app.get("/api/proposals/{proposal_id}")
    def proposal(proposal_id: int):
        p = chain.view("get_proposal", {"proposal_id": proposal_id})
        if p is None:
            raise HTTPException(404, "no such proposal")
        r = chain.view("get_round", {"round_id": p["round_id"]})
        reviews, signers = [], {}
        for e in chain.events():
            if e["proposal_id"] != proposal_id:
                continue
            request = chain.view("review_request", {"proposal_id": proposal_id, "slot": e["slot"]})
            if e["public_key"] not in signers:
                s = chain.view("get_signer", {"public_key_hex": e["public_key"]})
                signers[e["public_key"]] = s["model"] if s else ""
            verified = v.check_review(e, base64.b64decode(request), signers)
            reviews.append(dict(e, request=request, verified=verified))
        return {"id": proposal_id, "proposal": p, "round": r, "reviews": reviews}

    @app.get("/api/redteam")
    def redteam():
        return {"markdown": REPORT.read_text() if REPORT.exists() else ""}

    if WEB.exists():
        @app.get("/")
        def index():
            return FileResponse(WEB / "index.html")
        app.mount("/", StaticFiles(directory=WEB, html=True), name="web")
    return app


def main() -> FastAPI:
    import json
    deployed = Path(__file__).resolve().parents[1] / "deployments" / "testnet.json"
    return create_app(LiveChain(os.environ.get("SIEVE_CONTRACT") or json.loads(deployed.read_text())["contract"]))
