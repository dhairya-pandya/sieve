"""Settings come from environment variables only. Nothing here is ever written to disk or logs."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Mapping

DEFAULT_BASE_URL = "https://cloud-api.near.ai/v1"
REVIEW_MODELS = ("Qwen/Qwen3.8-27B", "z-ai/glm-5.3-flash", "deepseek-ai/DeepSeek-V4.1-Flash-1017")
EMBEDDING_MODEL = "Qwen/Qwen3-Embedding-0.6B"


@dataclass(frozen=True)
class Settings:
    near_ai_api_key: str | None = field(default=None, repr=False)
    base_url: str = DEFAULT_BASE_URL


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    env = os.environ if env is None else env
    return Settings(
        near_ai_api_key=env.get("NEAR_AI_API_KEY") or None,
        base_url=env.get("NEAR_AI_BASE_URL", DEFAULT_BASE_URL),
    )
