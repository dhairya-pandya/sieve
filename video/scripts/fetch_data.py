"""Pull the real on-chain facts the video shows into src/data.json. Run with the local Sieve API up:
    .venv/bin/python video/scripts/fetch_data.py http://127.0.0.1:8791
"""
import base64
import json
import sys
import urllib.request
from pathlib import Path

base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8791"
get = lambda p: json.load(urllib.request.urlopen(base + p))


def reason(review):
    content = json.loads(base64.b64decode(review["response"]))["choices"][0]["message"]["content"].strip().strip("`")
    return json.loads(content[content.find("{"):content.rfind("}") + 1]).get("reason", "")


def reviews(pid):
    d = get(f"/api/proposals/{pid}")
    return d, [{"model": r["model"], "score": r["score"], "flags": r["flags"], "stage": r.get("stage", 0), "reason": reason(r),
                "signature": r["signature"], "public_key": r["public_key"], "tx": r["tx"]} for r in d["reviews"]]


attack, attack_reviews = reviews(5)
honest, honest_reviews = reviews(8)
rounds = get("/api/rounds")
out = {
    "contract": rounds["contract"],
    "attack": {"id": 5, "title": attack["proposal"]["title"], "body": attack["proposal"]["body"], "reviews": attack_reviews},
    "honest": {"id": 8, "title": honest["proposal"]["title"], "author": honest["proposal"]["author"],
               "dao_proposal_ids": honest["proposal"]["dao_proposal_ids"], "reviews": honest_reviews,
               "evidence": honest["proposal"]["evidence"]},
    "dao": rounds["rounds"][0]["dao"],
}
Path(__file__).resolve().parents[1].joinpath("src", "data.json").write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
print({k: (len(v["reviews"]) if isinstance(v, dict) and "reviews" in v else v) for k, v in out.items()})
