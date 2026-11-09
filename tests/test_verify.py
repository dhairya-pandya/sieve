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


def test_local_request_uses_the_events_stage():
    import json as _json
    from sieve.verify import local_request
    rec0 = {"days": 0, "submitted": 0, "passed": 0, "delivered": 0}
    rec1 = {"days": 2, "submitted": 1, "passed": 1, "delivered": 0}
    proposal = {"round_id": 1, "title": "t", "body": "b", "seed": 9, "record": rec1, "stage": 1, "evidence": "proof",
                "past": [{"seed": 5, "record": rec0, "evidence": None}]}
    round_ = {"system": "grant rubric", "milestone_system": "delivery rubric"}
    old = _json.loads(local_request({"model": "m", "stage": 0, "proposal_id": 4}, proposal, round_))
    new = _json.loads(local_request({"model": "m", "stage": 1, "proposal_id": 4}, proposal, round_))
    assert old["seed"] == 5 and old["messages"][0]["content"] == "grant rubric" and "<evidence" not in old["messages"][1]["content"]
    assert new["seed"] == 9 and new["messages"][0]["content"] == "delivery rubric" and "proof" in new["messages"][1]["content"]


def _tx(event: dict, args: dict) -> dict:
    return {"transaction": {"actions": [{"FunctionCall": {"method_name": "post_review",
                                                          "args": base64.b64encode(json.dumps(args).encode()).decode()}}]},
            "receipts_outcome": [{"outcome": {"logs": ["EVENT_JSON:" + json.dumps(
                {"standard": "sieve", "version": "1.0.0", "event": "review", "data": [event]})]}}]}


def test_events_take_the_answer_from_transaction_arguments():
    import hashlib
    from sieve.verify import events_from_tx
    resp = base64.b64decode(F["response_b64"])
    event = {"proposal_id": 0, "slot": 0, "model": F["model"], "score": F["score"],
             "response_hash": hashlib.sha256(resp).hexdigest()}
    [e] = events_from_tx(_tx(event, {"proposal_id": 0, "slot": 0, "response": F["response_b64"]}))
    assert base64.b64decode(e["response"]) == resp


def test_events_reject_arguments_that_do_not_match_the_logged_hash():
    from sieve.verify import events_from_tx
    event = {"proposal_id": 0, "slot": 0, "model": "m", "score": 1, "response_hash": "00" * 32}
    [e] = events_from_tx(_tx(event, {"proposal_id": 0, "slot": 0, "response": F["response_b64"]}))
    assert e["response"] is None
