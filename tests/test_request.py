import json

from sieve.request import build_request

TITLE = 'Fix "fees" \\ path'
BODY = "Line one\n\tTabbed \x01 control 🚀 अनुदान"


def test_build_request_escaping():
    raw = build_request("Qwen/Qwen3.8-27B", "Rubric here", 3, 7, TITLE, BODY, 42)
    data = json.loads(raw)
    assert data["model"] == "Qwen/Qwen3.8-27B"
    assert data["messages"][0] == {"role": "system", "content": "Rubric here"}
    assert data["messages"][1]["content"] == (
        f"Round 3, proposal 7.\n<proposal>\nTITLE: {TITLE}\n\n{BODY}\n</proposal>"
    )
    assert data["temperature"] == 0 and data["seed"] == 42
    assert data["response_format"] == {"type": "json_object"}
    assert b"\\u0001" in raw
    assert "🚀".encode() in raw and "अनुदान".encode() in raw


def test_build_request_layout_is_fixed():
    raw = build_request("m", "s", 0, 1, "t", "b", 5)
    assert raw == (
        b'{"model":"m","messages":[{"role":"system","content":"s"},'
        b'{"role":"user","content":"Round 0, proposal 1.\\n<proposal>\\nTITLE: t\\n\\nb\\n</proposal>"}],'
        b'"temperature":0,"seed":5,"response_format":{"type":"json_object"}}'
    )
