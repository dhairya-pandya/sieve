"""HTTP shell every target implements: the arena talks to this and nothing else."""
from __future__ import annotations

from typing import Callable

from fastapi import FastAPI

from redswarm.targets.treasurybot import InboxItem


def create_target_app(bot, ownership_token: str | Callable[[], str]) -> FastAPI:
    """`bot` is anything with `async handle(InboxItem) -> str`.

    `ownership_token` may be a callable, because the arena issues the token only after registration.
    """
    app = FastAPI(title="RedSwarm target")

    @app.get("/redswarm/ownership")
    async def ownership():
        return {"token": ownership_token() if callable(ownership_token) else ownership_token}

    @app.post("/redswarm/inbox")
    async def inbox(item: InboxItem):
        return {"reply": await bot.handle(item)}

    return app
