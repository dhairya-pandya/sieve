"""Check NEAR AI Cloud model attestations before trusting a model's signing key.

For each model we ask for a fresh report with our own nonce and check that:
- the report is for that model and echoes our nonce,
- the Intel TDX quote's report data binds the signing key to our nonce,
- the NVIDIA GPU evidence echoes our nonce,
- the TDX quote is signed by Intel (via dcap-qvl, which fetches Intel collateral).
A check that cannot run is reported as UNVERIFIED, never as OK.
"""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import secrets
import time

import httpx

from sieve.config import load_settings

TD_REPORT_DATA = slice(568, 632)  # TDX quote v4: 48-byte header + report body, report_data is its last 64 bytes


class AttestationError(RuntimeError):
    pass


def fetch_report(model: str, nonce: str) -> dict:
    s = load_settings()
    r = httpx.get(f"{s.base_url}/attestation/report", timeout=60,
                  params={"model": model, "provider": "near", "signing_algo": "ed25519", "nonce": nonce},
                  headers={"Authorization": f"Bearer {s.near_ai_api_key}"})
    r.raise_for_status()
    return r.json()


def _quote_status(quote: bytes) -> str:
    try:
        import dcap_qvl
    except ImportError:
        return "UNVERIFIED"
    for _ in range(4):
        try:
            # Own thread so this also works when called from inside a running event loop.
            with ThreadPoolExecutor(1) as pool:
                result = pool.submit(asyncio.run, dcap_qvl.get_collateral_and_verify(quote)).result()
            status = json.loads(result.to_json()).get("status", "")
            break
        except (ValueError, RuntimeError):
            time.sleep(2)
    else:
        return "UNVERIFIED"
    if status != "UpToDate":
        raise AttestationError(f"TDX quote status is {status!r}")
    return "OK"


def check_model_report(report: dict, model: str, nonce: str, verify_quote: bool = True) -> tuple[str, list[tuple[str, str]]]:
    """Return the model's ed25519 signing key (hex) and the list of (check, status)."""
    candidates = [a for a in report.get("model_attestations", []) if a.get("model_name") == model]
    if len(candidates) != 1:
        raise AttestationError(f"no attestation for model {model}")
    a = candidates[0]
    key = a["signing_public_key"].lower()
    checks: list[tuple[str, str]] = []
    if a.get("signing_algo") != "ed25519":
        raise AttestationError("signing key is not ed25519")
    if a.get("request_nonce") != nonce:
        raise AttestationError("report does not echo our nonce")
    checks.append(("nonce", "OK"))
    quote = bytes.fromhex(a["intel_quote"])
    if quote[TD_REPORT_DATA].hex() != key + nonce:
        raise AttestationError("TDX quote report data does not bind this key to our nonce")
    checks.append(("quote_binds_key_and_nonce", "OK"))
    gpu = a.get("nvidia_payload")
    gpu = json.loads(gpu) if isinstance(gpu, str) else gpu
    if not gpu or gpu.get("nonce") != nonce:
        raise AttestationError("GPU evidence does not echo our nonce")
    checks.append(("gpu_nonce", "OK"))
    checks.append(("tdx_quote_signature", _quote_status(quote) if verify_quote else "UNVERIFIED"))
    return key, checks


def model_signers(models: list[str] | tuple[str, ...], require_all: bool = True) -> dict[str, str]:
    """Fresh attestation for each model; prints every check and returns {model: signing key hex}.
    With `require_all`, a check that could not run (UNVERIFIED) is a failure, not a pass."""
    keys = {}
    for model in models:
        nonce = secrets.token_hex(32)
        key, checks = check_model_report(fetch_report(model, nonce), model, nonce)
        print(f"{model}: key {key[:16]}...  " + "  ".join(f"{n}={s}" for n, s in checks))
        if require_all and any(status != "OK" for _, status in checks):
            raise AttestationError(f"{model}: attestation not fully verified; rerun when the Intel collateral service is reachable")
        keys[model] = key
    return keys
