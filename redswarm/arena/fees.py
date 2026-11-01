from __future__ import annotations

from redswarm.arena.db import Db
from redswarm.chain.base import Chain

FEE_YOCTO = 10**21  # 0.001 NEAR per attempt
MAX_CONTENT_BYTES = 20_000
RATE_LIMIT_PER_MINUTE = 30
TARGET_TIMEOUT = 10.0


def pending_total(db: Db, attacker: str) -> int:
    rows = db.all("SELECT amount FROM pending_fees WHERE attacker=? AND flushed=0", (attacker,))
    return sum(int(r["amount"]) for r in rows)


def record(db: Db, bounty_id: int, attacker: str, amount: int = FEE_YOCTO) -> None:
    db.execute("INSERT INTO pending_fees(bounty_id, attacker, amount) VALUES (?,?,?)",
               (bounty_id, attacker, str(amount)))


async def flush(chain: Chain, db: Db, bounty_id: int) -> None:
    """Settle all unflushed fees for one bounty with a single chain call."""
    rows = db.all("SELECT id, attacker, amount FROM pending_fees WHERE bounty_id=? AND flushed=0", (bounty_id,))
    if not rows:
        return
    totals: dict[str, int] = {}
    for r in rows:
        totals[r["attacker"]] = totals.get(r["attacker"], 0) + int(r["amount"])
    await chain.record_fees(bounty_id, list(totals.items()))
    for r in rows:
        db.execute("UPDATE pending_fees SET flushed=1 WHERE id=?", (r["id"],))
