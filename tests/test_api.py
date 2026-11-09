import json
from pathlib import Path

from fastapi.testclient import TestClient

from sieve.api import create_app

F = json.loads((Path(__file__).parent / "fixtures" / "signed_review.json").read_text())
EVENT = {"proposal_id": 0, "slot": 0, "model": F["model"], "score": F["score"], "flags": [],
         "public_key": F["signature"]["signing_address"], "signature": F["signature"]["signature_hex"],
         "response": F["response_b64"], "tx": "TX1"}


class StubChain:
    contract = "sieve.test"

    def view(self, method, args=None):
        if method == "round_count":
            return 1
        if method == "get_round":
            return {"kind": "Grant", "dao": "dao.test", "system": F["system"], "models": [F["model"]], "threshold": 7,
                    "tranche": "1", "dao_bond": "0", "window_ms": 600000, "bounty": "0", "bonds": "0", "open": True,
                    "creator": "op.test"}
        if method == "get_proposal":
            return {"round_id": 0, "author": "alice.test", "title": F["title"], "body": F["body"], "seed": F["seed"],
                    "submitted_ms": 1, "slots": [None], "finalized": False, "pending": False, "outcome": None}
        if method == "list_proposals":
            return [[0, self.view("get_proposal")]]
        if method == "review_request":
            return F["request_b64"]
        if method == "get_signer":
            return {"model": F["model"], "expires_ms": 2**62}
        raise KeyError(method)

    def events(self):
        return [EVENT]


def app(chain=None):
    return TestClient(create_app(chain or StubChain(), signals=lambda round_id, proposals: {}))


def test_api_proposal_includes_review_bytes():
    r = app().get("/api/proposals/0")
    assert r.status_code == 200
    d = r.json()
    assert d["proposal"]["title"] == F["title"]
    review = d["reviews"][0]
    assert review["response"] == F["response_b64"] and review["request"] == F["request_b64"]
    assert review["verified"] == "OK"


def test_api_rounds_list():
    d = app().get("/api/rounds").json()
    assert d["rounds"][0]["id"] == 0 and d["contract"] == "sieve.test"


def test_api_unknown_proposal_is_404():
    class Missing(StubChain):
        def view(self, method, args=None):
            return None if method == "get_proposal" else super().view(method, args)
    assert app(Missing()).get("/api/proposals/5").status_code == 404
