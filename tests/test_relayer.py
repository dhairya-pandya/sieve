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


import base64 as _b64
import time as _time

from sieve.relayer import relay_once


class FakeNear:
    """One round with three models; proposals given as {pid: slots}. Records post_review calls."""

    def __init__(self, slots_by_pid, threshold=7):
        now = int(_time.time() * 1000)
        self.round = {"models": ["m0", "m1", "m2"], "window_ms": 3_600_000, "threshold": threshold}
        self.props = {pid: {"round_id": 0, "slots": slots, "submitted_ms": now, "finalized": False, "pending": False}
                      for pid, slots in slots_by_pid.items()}
        self.posts = []

    async def view(self, contract, method, args=None):
        if method == "round_count":
            return 1
        if method == "get_round":
            return self.round
        if method == "list_proposals":
            return [[pid, p] for pid, p in self.props.items() if pid >= args["from"]]
        if method == "review_request":
            return _b64.b64encode(b"req").decode()
        raise KeyError(method)

    async def call(self, signer, contract, method, args, **kw):
        self.posts.append((method, args.get("proposal_id"), args.get("slot")))


def _fixed(score):
    sig = Signature("t", "00", "11", "provider_tee")
    return lambda request, model: (b"{}", sig, score)


async def test_overrules_cherry_picked_passing_score():
    near = FakeNear({0: [{"score": 9, "flags": [], "response_hash": ""}, None, None]})
    await relay_once(near, "c", "relayer", review=_fixed(3))
    assert ("post_review", 0, 0) in near.posts  # lower score posted over the cherry-picked 9


async def test_leaves_low_scores_alone():
    near = FakeNear({0: [{"score": 2, "flags": [], "response_hash": ""}] * 3})
    await relay_once(near, "c", "relayer", review=_fixed(1))
    assert near.posts == []  # already failing, nothing to overrule


async def test_does_not_post_higher_score_over_filled_slot():
    near = FakeNear({0: [{"score": 8, "flags": [], "response_hash": ""}, None, None]})
    await relay_once(near, "c", "relayer", review=_fixed(9))
    assert ("post_review", 0, 0) not in near.posts


async def test_one_failing_slot_does_not_stop_the_run():
    near = FakeNear({0: [None, None, None], 1: [None, None, None]})
    calls = []

    def flaky(request, model):
        calls.append(model)
        if len(calls) == 1:
            raise RuntimeError("HTTP 400 from model")
        return b"{}", Signature("t", "00", "11", "provider_tee"), 5

    stats = await relay_once(near, "c", "relayer", review=flaky)
    assert stats["errors"] == 1 and stats["posted"] == 5
