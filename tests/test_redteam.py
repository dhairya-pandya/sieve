import base64
import json
from pathlib import Path

import pytest

from sieve.nearai import parse_review
from sieve.redteam.attacks import ATTACKS
from sieve.redteam.proposals import GOOD, WEAK
from sieve.redteam.report import load_lines, wilson

F = json.loads((Path(__file__).parent / "fixtures" / "signed_review.json").read_text())


def test_every_attack_changes_body_and_keeps_clean_text():
    body = WEAK[0][1]
    assert len(ATTACKS) >= 8
    for name, attack in ATTACKS.items():
        out = attack(body)
        assert out != body, name
        assert body in out, name


def test_proposal_sets():
    assert len(WEAK) == 10 and len(GOOD) == 10
    assert all(len(t) <= 200 and len(b) <= 7_000 for t, b in WEAK + GOOD)


def test_report_wilson_interval():
    lo, hi = wilson(0, 30)
    assert lo == 0 and hi == pytest.approx(0.114, abs=0.001)
    lo, hi = wilson(15, 30)
    assert lo == pytest.approx(0.332, abs=0.001) and hi == pytest.approx(0.668, abs=0.001)


def _line(**over):
    line = {"attack": "none", "kind": "good", "proposal": 0, "model": F["model"], "defense": "hardened", "trial": 0,
            "request_b64": F["request_b64"], "response_b64": F["response_b64"], "signature": F["signature"],
            "score": F["score"], "flags": parse_review(base64.b64decode(F["response_b64"])).flags}
    line.update(over)
    return json.dumps(line)


def test_report_accepts_signed_line(tmp_path):
    p = tmp_path / "run.jsonl"
    p.write_text(_line() + "\n")
    rows, rejected = load_lines(p)
    assert len(rows) == 1 and rejected == 0


def test_report_rejects_bad_signature_line(tmp_path):
    resp = bytearray(base64.b64decode(F["response_b64"]))
    resp[-3] ^= 1
    p = tmp_path / "run.jsonl"
    p.write_text(_line() + "\n" + _line(response_b64=base64.b64encode(bytes(resp)).decode()) + "\n")
    rows, rejected = load_lines(p)
    assert len(rows) == 1 and rejected == 1


def _row(attack, kind, proposal, model, score, flags=()):
    return {"attack": attack, "kind": kind, "proposal": proposal, "model": model, "defense": "hardened", "trial": 0,
            "score": score, "flags": list(flags)}


def test_borderline_push_over_the_line_counts():
    from sieve.redteam.report import summarize
    rows = [_row("none", "borderline", 200, m, 5) for m in ("a", "b", "c")]
    rows += [_row("x", "borderline", 200, "a", 8), _row("x", "borderline", 200, "b", 7), _row("x", "borderline", 200, "c", 4)]
    text = summarize(rows, 0)
    assert "| x | 1/1 = 100%" in text  # deployed median 7, no injection flag: passes on chain


def test_flagged_push_does_not_count():
    from sieve.redteam.report import summarize
    rows = [_row("none", "borderline", 200, m, 5) for m in ("a", "b", "c")]
    rows += [_row("x", "borderline", 200, m, 9, ["injection"] if m == "a" else []) for m in ("a", "b", "c")]
    assert "| x | 0/1 = 0%" in summarize(rows, 0)
