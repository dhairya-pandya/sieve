from __future__ import annotations

import asyncio
import json
import secrets
import time
from collections import defaultdict, deque
from typing import Literal

import httpx
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from redswarm.arena import fees
from redswarm.arena.db import Db
from redswarm.arena.events import EventBus
from redswarm.chain.base import Chain


class NewBounty(BaseModel):
    bounty_id: int
    target_url: str


class NewAttacker(BaseModel):
    account: str


class Attempt(BaseModel):
    channel: Literal["chat", "document"]
    kind: Literal["chat", "invoice", "email"]
    content: str


def create_app(
    chain: Chain,
    operator_account: str,
    db_path: str = ":memory:",
    target_client: httpx.AsyncClient | None = None,
    target_timeout: float = fees.TARGET_TIMEOUT,
) -> FastAPI:
    app = FastAPI(title="RedSwarm arena")
    db = Db(db_path)
    bus = EventBus()
    client = target_client or httpx.AsyncClient()
    locks: dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)
    recent: dict[str, deque] = defaultdict(deque)
    app.state.db, app.state.bus, app.state.operator = db, bus, operator_account

    def attacker_for(api_key: str | None) -> str:
        row = db.one("SELECT account FROM attackers WHERE api_key=?", (api_key or "",))
        if row is None:
            raise HTTPException(401, "unknown api key")
        return row["account"]

    def rate_limit(account: str) -> None:
        now, window = time.monotonic(), recent[account]
        while window and now - window[0] > 60:
            window.popleft()
        if len(window) >= fees.RATE_LIMIT_PER_MINUTE:
            raise HTTPException(429, "rate limit: 30 attempts per minute")
        window.append(now)

    @app.post("/bounties")
    async def register_bounty(body: NewBounty):
        b = await chain.get_bounty(body.bounty_id)
        if b is None or b.status != "open":
            raise HTTPException(404, "no open bounty with that id on chain")
        if db.one("SELECT id FROM bounties WHERE id=?", (body.bounty_id,)):
            raise HTTPException(409, "bounty already registered")
        token, poster_key = secrets.token_urlsafe(16), secrets.token_urlsafe(24)
        db.execute("INSERT INTO bounties(id, target_url, token, poster_key) VALUES (?,?,?,?)",
                   (body.bounty_id, body.target_url.rstrip("/"), token, poster_key))
        return {"ownership_token": token, "poster_key": poster_key}

    @app.post("/bounties/{bounty_id}/verify")
    async def verify_bounty(bounty_id: int):
        row = db.one("SELECT target_url, token FROM bounties WHERE id=?", (bounty_id,))
        if row is None:
            raise HTTPException(404, "unknown bounty")
        try:
            r = await asyncio.wait_for(client.get(f"{row['target_url']}/redswarm/ownership"), target_timeout)
            echoed = r.json().get("token")
        except Exception:
            raise HTTPException(400, "target did not answer the ownership check")
        if echoed != row["token"]:
            raise HTTPException(400, "ownership token mismatch")
        db.execute("UPDATE bounties SET active=1 WHERE id=?", (bounty_id,))
        bus.publish("bounty_active", {"bounty_id": bounty_id})
        return {"active": True}

    @app.post("/attackers")
    async def register_attacker(body: NewAttacker):
        if not await chain.is_attacker(body.account):
            raise HTTPException(403, "register the account as an attacker on chain first")
        if db.one("SELECT account FROM attackers WHERE account=?", (body.account,)):
            raise HTTPException(409, "attacker already has an api key")
        key = secrets.token_urlsafe(24)
        db.execute("INSERT INTO attackers(account, api_key) VALUES (?,?)", (body.account, key))
        return {"api_key": key}

    @app.post("/bounties/{bounty_id}/attempts")
    async def attempt(bounty_id: int, body: Attempt, x_api_key: str | None = Header(default=None)):
        account = attacker_for(x_api_key)
        rate_limit(account)
        try:
            size = len(body.content.encode("utf-8"))
        except UnicodeEncodeError:
            raise HTTPException(422, "content is not valid UTF-8 text")
        if not body.content.strip():
            raise HTTPException(422, "content is empty")
        if size > fees.MAX_CONTENT_BYTES:
            raise HTTPException(413, f"content over {fees.MAX_CONTENT_BYTES} bytes")
        row = db.one("SELECT target_url, active FROM bounties WHERE id=?", (bounty_id,))
        if row is None:
            raise HTTPException(404, "unknown bounty")
        if not row["active"]:
            raise HTTPException(409, "target ownership not verified")

        async with locks[bounty_id]:  # one attempt at a time per bounty: no racing past a break
            before = await chain.get_bounty(bounty_id)
            if before is None or before.status != "open":
                raise HTTPException(409, "bounty_closed")
            credit = await chain.get_credit(account) - fees.pending_total(db, account)
            if credit < fees.FEE_YOCTO:
                raise HTTPException(402, "not enough credit for the attempt fee")

            reply, status = None, "ok"
            try:
                r = await asyncio.wait_for(
                    client.post(f"{row['target_url']}/redswarm/inbox",
                                json={"channel": body.channel, "kind": body.kind,
                                      "content": body.content, "sender": account}),
                    target_timeout)
                data = r.json()
                if r.status_code != 200 or not isinstance(data.get("reply"), str):
                    raise ValueError("bad target reply")
                reply = data["reply"]
            except Exception:
                status = "target_error"

            outcome, payout = "none", 0
            if status == "ok":
                fees.record(db, bounty_id, account)
                after = await chain.get_bounty(bounty_id)
                if after.status == "broken" and after.winner == account:
                    outcome, payout = "break", before.balance
            attempt_id = db.execute(
                "INSERT INTO attempts(bounty_id, attacker, channel, kind, content, reply, status, outcome, payout, created)"
                " VALUES (?,?,?,?,?,?,?,?,?,?)",
                (bounty_id, account, body.channel, body.kind, body.content, reply, status, outcome,
                 str(payout), time.time()))
            bus.publish("attempt", {"attempt_id": attempt_id, "bounty_id": bounty_id, "attacker": account,
                                    "status": status, "outcome": outcome})
            if status == "ok" and (await chain.get_bounty(bounty_id)).status != "open":
                await fees.flush(chain, db, bounty_id)
                if outcome == "break":
                    bus.publish("break", {"bounty_id": bounty_id, "winner": account, "amount": str(payout)})
        return {"attempt_id": attempt_id, "status": status, "reply": reply, "outcome": outcome}

    @app.get("/leaderboard")
    async def leaderboard():
        attackers = [
            {"account": r["attacker"], "attempts": r["n"], "breaks": r["breaks"],
             "hit_rate": (r["breaks"] / r["n"]) if r["n"] else 0.0, "earnings": "0"}
            for r in db.all("SELECT attacker, COUNT(*) n, SUM(outcome='break') breaks"
                            " FROM attempts WHERE status='ok' GROUP BY attacker")
        ]
        for a in attackers:
            rows = db.all("SELECT payout FROM attempts WHERE attacker=? AND outcome='break'", (a["account"],))
            a["earnings"] = str(sum(int(x["payout"]) for x in rows))
        targets = [
            {"bounty_id": r["bounty_id"], "attempts": r["n"], "breaks": r["breaks"],
             "survived": r["n"] if not r["breaks"] else 0}
            for r in db.all("SELECT bounty_id, COUNT(*) n, SUM(outcome='break') breaks FROM attempts"
                            " WHERE status='ok' GROUP BY bounty_id")
        ]
        return {"attackers": sorted(attackers, key=lambda a: -a["breaks"]), "targets": targets}

    @app.get("/bounties/{bounty_id}/report")
    async def report(bounty_id: int, x_poster_key: str | None = Header(default=None)):
        row = db.one("SELECT poster_key FROM bounties WHERE id=?", (bounty_id,))
        if row is None or not x_poster_key or not secrets.compare_digest(row["poster_key"], x_poster_key):
            raise HTTPException(401, "poster key required")
        b = await chain.get_bounty(bounty_id)
        win = db.one("SELECT * FROM attempts WHERE bounty_id=? AND outcome='break'", (bounty_id,))
        history = []
        if win is not None:
            history = [dict(r) for r in db.all(
                "SELECT id, channel, kind, content, reply, status, outcome FROM attempts"
                " WHERE bounty_id=? AND attacker=? AND id<=? ORDER BY id", (bounty_id, win["attacker"], win["id"]))]
        return {"bounty_id": bounty_id, "status": b.status, "winner": b.winner,
                "winning_attempt": dict(win) if win is not None else None, "winner_history": history}

    @app.get("/events/recent")
    async def recent_events():
        return list(bus.history)

    @app.get("/events")
    async def events():
        async def stream():
            for e in list(bus.history):
                yield f"data: {json.dumps(e)}\n\n"
            async for e in bus.subscribe():
                yield f"data: {json.dumps(e)}\n\n"

        return StreamingResponse(stream(), media_type="text/event-stream")

    return app
