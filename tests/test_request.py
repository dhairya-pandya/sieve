import json

from sieve.request import build_request

TITLE = 'Fix "fees" \\ path'
BODY = "Line one\n\tTabbed \x01 control 🚀 अनुदान"
RECORD0 = ("Applicant record (written by the Sieve contract, not by the applicant): first seen 0 days before this "
           "submission; 0 proposals submitted before this one; 0 passed review; 0 milestones delivered.")


def test_build_request_escaping():
    raw = build_request("Qwen/Qwen3.8-27B", "Rubric here", 3, 7, TITLE, BODY, 42)
    data = json.loads(raw)
    assert data["model"] == "Qwen/Qwen3.8-27B"
    assert data["messages"][0] == {"role": "system", "content": "Rubric here"}
    assert data["messages"][1]["content"] == (
        f"Round 3, proposal 7, stage 0.\n{RECORD0}\n<proposal>\nTITLE: {TITLE}\n\n{BODY}\n</proposal>"
    )
    assert data["temperature"] == 0 and data["seed"] == 42
    assert data["response_format"] == {"type": "json_object"}
    assert b"\\u0001" in raw
    assert "🚀".encode() in raw and "अनुदान".encode() in raw


def test_build_request_layout_is_fixed():
    raw = build_request("m", "s", 0, 1, "t", "b", 5)
    assert raw == (
        b'{"model":"m","messages":[{"role":"system","content":"s"},'
        b'{"role":"user","content":"Round 0, proposal 1, stage 0.\\n' + RECORD0.encode() + b'\\n<proposal>\\nTITLE: t\\n\\nb\\n</proposal>"}],'
        b'"temperature":0,"seed":5,"response_format":{"type":"json_object"}}'
    )


def test_request_carries_contract_record_and_stage():
    raw = build_request("m", "s", 2, 9, "t", "b", 5, record=(12, 3, 1, 1), stage=0)
    user = json.loads(raw)["messages"][1]["content"]
    assert user.startswith("Round 2, proposal 9, stage 0.\nApplicant record (written by the Sieve contract, not by the applicant): "
                           "first seen 12 days before this submission; 3 proposals submitted before this one; "
                           "1 passed review; 1 milestones delivered.\n<proposal>\nTITLE: t\n\nb\n</proposal>")
    assert "<evidence" not in user


def test_request_milestone_stage_appends_evidence():
    raw = build_request("m", "s", 2, 9, "t", "b", 5, record=(0, 0, 0, 0), stage=2, evidence="Release v1: commit abc")
    user = json.loads(raw)["messages"][1]["content"]
    assert user.endswith('</proposal>\n<evidence milestone="2">\nRelease v1: commit abc\n</evidence>')


def test_shared_vectors_match():
    """tests/fixtures/request_vectors.json is checked by this test, by cargo test and by web/app.js (node)."""
    from pathlib import Path
    vectors = json.loads((Path(__file__).parent / "fixtures" / "request_vectors.json").read_text())
    assert len(vectors) >= 4
    for v in vectors:
        got = build_request(v["model"], v["system"], v["round_id"], v["proposal_id"], v["title"], v["body"], v["seed"],
                            record=tuple(v["record"]), stage=v["stage"], evidence=v["evidence"])
        assert got.decode() == v["request"], v["name"]
