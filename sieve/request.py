"""The canonical review request. The contract builds the same bytes (contract/src/request.rs);
any change here must change there too, or every on-chain review check fails."""
from __future__ import annotations

import json


def json_str(s: str) -> str:
    """JSON string literal escaped the way serde_json::to_string(&str) does it."""
    return json.dumps(s, ensure_ascii=False)


Record = tuple[int, int, int, int]  # days since first seen, proposals submitted before, passed, milestones delivered


def user_message(round_id: int, proposal_id: int, title: str, body: str,
                 record: Record = (0, 0, 0, 0), stage: int = 0, evidence: str | None = None) -> str:
    days, submitted, passed, delivered = record
    text = (f"Round {round_id}, proposal {proposal_id}, stage {stage}.\n"
            "Applicant record (written by the Sieve contract, not by the applicant): "
            f"first seen {days} days before this submission; {submitted} proposals submitted before this one; "
            f"{passed} passed review; {delivered} milestones delivered.\n"
            f"<proposal>\nTITLE: {title}\n\n{body}\n</proposal>")
    if stage > 0:
        text += f'\n<evidence milestone="{stage}">\n{evidence or ""}\n</evidence>'
    return text


def build_request(model: str, system: str, round_id: int, proposal_id: int, title: str, body: str, seed: int,
                  record: Record = (0, 0, 0, 0), stage: int = 0, evidence: str | None = None) -> bytes:
    user = user_message(round_id, proposal_id, title, body, record, stage, evidence)
    return (
        '{"model":' + json_str(model)
        + ',"messages":[{"role":"system","content":' + json_str(system)
        + '},{"role":"user","content":' + json_str(user)
        + '}],"temperature":0,"seed":' + str(seed)
        + ',"response_format":{"type":"json_object"}}'
    ).encode()
