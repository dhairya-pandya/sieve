import json
from pathlib import Path

import pytest

from sieve.attest import AttestationError, check_model_report

REPORT = json.loads((Path(__file__).parent / "fixtures" / "attestation_qwen.json").read_text())
NONCE = REPORT["model_attestations"][0]["request_nonce"]
KEY = REPORT["model_attestations"][0]["signing_public_key"]


def test_accepts_matching_report_without_quote_service():
    key, checks = check_model_report(REPORT, "Qwen/Qwen3.8-27B", NONCE, verify_quote=False)
    assert key == KEY
    names = dict(checks)
    assert names["nonce"] == "OK" and names["quote_binds_key_and_nonce"] == "OK" and names["gpu_nonce"] == "OK"
    assert names["tdx_quote_signature"] == "UNVERIFIED"


def test_rejects_nonce_mismatch():
    with pytest.raises(AttestationError, match="nonce"):
        check_model_report(REPORT, "Qwen/Qwen3.8-27B", "00" * 32, verify_quote=False)


def test_rejects_wrong_model():
    with pytest.raises(AttestationError, match="no attestation for model"):
        check_model_report(REPORT, "z-ai/glm-5.3-flash", NONCE, verify_quote=False)


def test_rejects_key_not_bound_in_quote():
    bad = json.loads(json.dumps(REPORT))
    bad["model_attestations"][0]["signing_public_key"] = "ab" * 32
    bad["model_attestations"][0]["signing_address"] = "ab" * 32
    with pytest.raises(AttestationError, match="quote"):
        check_model_report(bad, "Qwen/Qwen3.8-27B", NONCE, verify_quote=False)
