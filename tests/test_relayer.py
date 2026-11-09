import hashlib
import json

from nacl.signing import SigningKey

from sieve.nearai import Signature, signed_text
from sieve.relayer import review_slot

REQ = b'{"model":"m"}'
RESP = json.dumps({"id": "c1", "choices": [{"message": {"content": '{"score": 4, "flags": []}'}}]}).encode()
KEY = SigningKey(b"\x05" * 32)


def _sig(kind="provider_tee", resp=RESP):
    text = signed_text("m", REQ, resp)
    return Signature(text, KEY.sign(text.encode()).signature.hex(), KEY.verify_key.encode().hex(), kind)


def test_skips_when_signature_missing():
    assert review_slot(REQ, "m", complete=lambda r: (RESP, "c1"), fetch=lambda cid: None) is None


def test_skips_gateway_signature():
    assert review_slot(REQ, "m", complete=lambda r: (RESP, "c1"), fetch=lambda cid: _sig("gateway")) is None


def test_skips_unparseable_review():
    bad = json.dumps({"id": "c1", "choices": [{"message": {"content": "I give it a 9"}}]}).encode()
    assert review_slot(REQ, "m", complete=lambda r: (bad, "c1"), fetch=lambda cid: _sig(resp=bad)) is None


def test_skips_oversize_response():
    big = json.dumps({"id": "c1", "choices": [{"message": {"content": '{"score":1}', "reasoning_content": "x" * 9000}}]}).encode()
    assert review_slot(REQ, "m", complete=lambda r: (big, "c1"), fetch=lambda cid: _sig(resp=big)) is None


def test_returns_verified_review():
    out = review_slot(REQ, "m", complete=lambda r: (RESP, "c1"), fetch=lambda cid: _sig())
    assert out is not None
    resp, sig, score = out
    assert resp == RESP and score == 4 and sig.signing_address == KEY.verify_key.encode().hex()
    assert hashlib.sha256(resp).hexdigest() in sig.text
