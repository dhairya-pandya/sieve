import base64
import json
from pathlib import Path

from sieve.verify import check_review

F = json.loads((Path(__file__).parent / "fixtures" / "signed_review.json").read_text())
REQUEST = base64.b64decode(F["request_b64"])
KEY = F["signature"]["signing_address"]
EVENT = {"proposal_id": 0, "slot": 0, "model": F["model"], "score": F["score"], "public_key": KEY,
         "signature": F["signature"]["signature_hex"], "response": F["response_b64"]}


def test_verify_accepts_fixture():
    assert check_review(EVENT, REQUEST, {KEY: F["model"]}) == "OK"


def test_verify_detects_tamper():
    resp = bytearray(base64.b64decode(F["response_b64"]))
    resp[-3] ^= 1
    tampered = dict(EVENT, response=base64.b64encode(bytes(resp)).decode())
    assert check_review(tampered, REQUEST, {KEY: F["model"]}) == "signature does not match"


def test_verify_detects_other_request():
    assert check_review(EVENT, REQUEST + b" ", {KEY: F["model"]}) == "signature does not match"


def test_verify_detects_unregistered_key():
    assert check_review(EVENT, REQUEST, {}) == "key not registered for model"


def test_verify_detects_score_mismatch():
    assert check_review(dict(EVENT, score=10), REQUEST, {KEY: F["model"]}) == "event score differs from signed answer"
