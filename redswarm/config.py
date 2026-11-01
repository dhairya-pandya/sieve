"""Settings come from environment variables only. Nothing here is ever written to disk or logs."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Mapping

DEFAULT_BASE_URL = "https://cloud-api.near.ai/v1"


@dataclass(frozen=True)
class Settings:
    near_ai_api_key: str | None = field(default=None, repr=False)
    base_url: str = DEFAULT_BASE_URL
    target_model: str = "openai/gpt-5.4-mini"
    attacker_model: str = "z-ai/glm-5.3-flash"
    chain: str = "auto"  # auto | fake | sandbox | testnet
    rpc_url: str | None = None
    root_account: str | None = None
    root_key: str | None = field(default=None, repr=False)


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    env = os.environ if env is None else env
    return Settings(
        near_ai_api_key=env.get("NEAR_AI_API_KEY") or None,
        base_url=env.get("NEAR_AI_BASE_URL", DEFAULT_BASE_URL),
        target_model=env.get("REDSWARM_TARGET_MODEL", Settings.target_model),
        attacker_model=env.get("REDSWARM_ATTACKER_MODEL", Settings.attacker_model),
        chain=env.get("REDSWARM_CHAIN", "auto"),
        rpc_url=env.get("REDSWARM_RPC_URL") or None,
        root_account=env.get("REDSWARM_ROOT_ACCOUNT") or None,
        root_key=env.get("REDSWARM_ROOT_KEY") or None,
    )


def make_llm_client(settings: Settings):
    """An OpenAI-compatible async client pointed at NEAR AI Cloud."""
    if not settings.near_ai_api_key:
        raise RuntimeError("NEAR_AI_API_KEY is not set")
    from openai import AsyncOpenAI

    return AsyncOpenAI(api_key=settings.near_ai_api_key, base_url=settings.base_url)
