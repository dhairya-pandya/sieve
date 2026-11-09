import hashlib
import json

import pytest
from nacl.signing import SigningKey

from sieve.nearai import Signature, parse_review, verify_signature


def _response(content: str) -> bytes:
    return json.dumps({"id": "chatcmpl-1", "choices": [{"message": {"role": "assistant", "content": content}}]}).encode()


def _signed(model: str, req: bytes, resp: bytes, key: SigningKey, kind: str = "provider_tee") -> Signature:
    text = f"{model}:{hashlib.sha256(req).hexdigest()}:{hashlib.sha256(resp).hexdigest()}"
    sig = key.sign(text.encode()).signature.hex()
    return Signature(text=text, signature_hex=sig, signing_address=key.verify_key.encode().hex(), signature_kind=kind)


def test_parse_review_plain_json():
    r = parse_review(_response('{"score": 7, "flags": ["duplicate"], "reason": "ok"}'))
    assert (r.score, r.flags, r.reason) == (7, ["duplicate"], "ok")


def test_parse_review_strips_one_fence():
    r = parse_review(_response('```json\n{"score": 2, "flags": [], "reason": "weak"}\n```'))
    assert r.score == 2


@pytest.mark.parametrize("content", [
    '{"score": 11, "flags": []}',
    '{"score": "9", "flags": []}',
    '{"flags": []}',
    '{"score": 5, "flags": "none"}',
    'Score: 9',
    '{"score": true, "flags": []}',
])
def test_parse_review_rejects_bad_output(content):
    with pytest.raises(ValueError):
        parse_review(_response(content))


def test_verify_signature_accepts_and_rejects_tamper():
    key = SigningKey.generate()
    req, resp = b'{"model":"m"}', _response('{"score":1,"flags":[]}')
    sig = _signed("m", req, resp, key)
    assert verify_signature("m", req, resp, sig)
    assert not verify_signature("m", req, resp + b" ", sig)
    assert not verify_signature("other", req, resp, sig)


def test_verify_signature_requires_provider_tee():
    key = SigningKey.generate()
    req, resp = b"{}", b"{}"
    assert not verify_signature("m", req, resp, _signed("m", req, resp, key, kind="gateway"))
