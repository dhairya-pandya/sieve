"""NEAR AI Cloud client: completions with exact bytes kept, TEE response signatures, review parsing."""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass

import httpx
from nacl.exceptions import BadSignatureError
from nacl.signing import VerifyKey

from sieve.config import load_settings


@dataclass(frozen=True)
class Signature:
    text: str
    signature_hex: str
    signing_address: str
    signature_kind: str


@dataclass(frozen=True)
class Review:
    score: int
    flags: list[str]
    reason: str


def _client() -> httpx.Client:
    settings = load_settings()
    if not settings.near_ai_api_key:
        raise RuntimeError("NEAR_AI_API_KEY is not set")
    return httpx.Client(
        base_url=settings.base_url,
        headers={"Authorization": f"Bearer {settings.near_ai_api_key}", "Accept-Encoding": "identity"},
        timeout=120,
    )


def complete(request: bytes) -> tuple[bytes, str]:
    """Send the exact request bytes; return the exact response bytes and the chat id."""
    with _client() as c:
        r = c.post("/chat/completions", content=request,
                   headers={"Content-Type": "application/json", "x-no-aliasing": "true"})
        r.raise_for_status()
        body = r.content
    return body, json.loads(body)["id"]


def fetch_signature(chat_id: str, retries: int = 6, delay: float = 2.0) -> Signature | None:
    """The ed25519 signature for a completion, or None if it never became available."""
    with _client() as c:
        for attempt in range(retries):
            r = c.get(f"/signature/{chat_id}", params={"signing_algo": "ed25519"}, headers={"Accept": "application/json"})
            if r.status_code == 200:
                d = r.json()
                if "signature" in d and "error_code" not in d:
                    return Signature(d["text"], d["signature"].removeprefix("0x"),
                                     d["signing_address"].removeprefix("0x"), d.get("signature_kind", ""))
            elif r.status_code != 404:
                r.raise_for_status()
            if attempt < retries - 1:
                time.sleep(delay)
    return None


def signed_text(model: str, request: bytes, response: bytes) -> str:
    return f"{model}:{hashlib.sha256(request).hexdigest()}:{hashlib.sha256(response).hexdigest()}"


def verify_signature(model: str, request: bytes, response: bytes, sig: Signature) -> bool:
    if sig.signature_kind != "provider_tee" or sig.text != signed_text(model, request, response):
        return False
    try:
        VerifyKey(bytes.fromhex(sig.signing_address)).verify(sig.text.encode(), bytes.fromhex(sig.signature_hex))
        return True
    except (BadSignatureError, ValueError):
        return False


def _strip_fence(content: str) -> str:
    s = content.strip()
    if s.startswith("```") and s.endswith("```") and len(s) >= 6:
        s = s[3:-3]
        newline = s.find("\n")
        if newline != -1 and s[:newline].strip().isalpha():
            s = s[newline + 1:]
    return s.strip()


def parse_review(response: bytes) -> Review:
    try:
        content = json.loads(response)["choices"][0]["message"]["content"]
        data = json.loads(_strip_fence(content))
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as e:
        raise ValueError(f"not a review: {e}") from e
    score, flags = data.get("score") if isinstance(data, dict) else None, data.get("flags", []) if isinstance(data, dict) else None
    if type(score) is not int or not 0 <= score <= 10:
        raise ValueError("score must be an integer from 0 to 10")
    if not isinstance(flags, list) or not all(isinstance(f, str) for f in flags):
        raise ValueError("flags must be a list of strings")
    reason = data.get("reason", "")
    return Review(score, flags, reason if isinstance(reason, str) else "")
