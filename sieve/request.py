"""The canonical review request. The contract builds the same bytes (contract/src/request.rs);
any change here must change there too, or every on-chain review check fails."""
from __future__ import annotations

import json


def json_str(s: str) -> str:
    """JSON string literal escaped the way serde_json::to_string(&str) does it."""
    return json.dumps(s, ensure_ascii=False)


def user_message(round_id: int, proposal_id: int, title: str, body: str) -> str:
    return f"Round {round_id}, proposal {proposal_id}.\n<proposal>\nTITLE: {title}\n\n{body}\n</proposal>"


def build_request(model: str, system: str, round_id: int, proposal_id: int, title: str, body: str, seed: int) -> bytes:
    user = user_message(round_id, proposal_id, title, body)
    return (
        '{"model":' + json_str(model)
        + ',"messages":[{"role":"system","content":' + json_str(system)
        + '},{"role":"user","content":' + json_str(user)
        + '}],"temperature":0,"seed":' + str(seed)
        + ',"response_format":{"type":"json_object"}}'
    ).encode()
