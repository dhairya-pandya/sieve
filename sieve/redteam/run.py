"""Run attacks against the reviewer on real NEAR AI Cloud models and record signed transcripts."""
from __future__ import annotations

import base64
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path

import httpx

from sieve import nearai
from sieve.config import REVIEW_MODELS, load_settings
from sieve.redteam.attacks import ATTACKS, adaptive_iterative, llm_adaptive
from sieve.redteam.proposals import BORDERLINE, GOOD, WEAK
from sieve.request import build_request
from sieve.setup import prompt

RESULTS = Path(__file__).resolve().parents[2] / "results" / "redteam"
ROUND_ID = 99  # offline runs use a round id no on-chain round has
ATTACKERS = ("Qwen/Qwen3.8-27B-abliterated", "Qwen/Qwen3.8-27B")
EST_IN, EST_OUT = 900, 600  # tokens per review call, measured on the live test


def complete_text(model: str, text: str) -> str:
    body = json.dumps({"model": model, "messages": [{"role": "user", "content": text}], "temperature": 0.9}).encode()
    response, _ = nearai.complete(body)
    return json.loads(response)["choices"][0]["message"]["content"] or ""


def adaptive_injections(proposals=WEAK, name: str = "adaptive") -> dict[int, str]:
    """One attacker-written injection per proposal, cached so reruns attack with the same text."""
    path = RESULTS / f"{name}.json"
    if path.exists():
        return {int(k): v for k, v in json.loads(path.read_text()).items()}
    out = {}
    for i, (_, body) in enumerate(proposals):
        for attacker in ATTACKERS:
            try:
                out[i] = llm_adaptive(body, attacker, complete_text)
                break
            except httpx.HTTPError:
                continue
    RESULTS.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=1, ensure_ascii=False))
    return out


def iterative_injections(proposals=BORDERLINE, target: str = REVIEW_MODELS[0], rubric: str = "grant_v1",
                         name: str = "iterative") -> dict[int, str]:
    """Attacker adapts over three rounds against one rubric on one model; transfer to the others is measured."""
    path = RESULTS / f"{name}.json"
    if path.exists():
        return {int(k): v for k, v in json.loads(path.read_text()).items()}
    system = prompt(rubric)

    def review(body: str) -> tuple[int, list[str], str]:
        resp, _ = nearai.complete(build_request(target, system, ROUND_ID, 0, "draft", body, 7))
        try:
            r = nearai.parse_review(resp)
            return r.score, r.flags, r.reason
        except ValueError:
            return 0, [], "unparseable"

    out = {}
    for i, (_, body) in enumerate(proposals):
        for attacker in ATTACKERS:
            try:
                out[i] = adaptive_iterative(body, attacker, complete_text, review)
                break
            except httpx.HTTPError:
                continue
    path.write_text(json.dumps(out, indent=1, ensure_ascii=False))
    return out


def prices() -> dict[str, tuple[float, float]]:
    data = httpx.get(f"{load_settings().base_url}/models", timeout=30).json()["data"]
    return {m["id"]: (m["pricing"]["input"], m["pricing"]["output"]) for m in data if "pricing" in m}


def jobs(models, defenses, trials, sets=("weak", "good")) -> list[dict]:
    cases = []
    if "weak" in sets:
        adaptive = adaptive_injections()
        cases += [("none", "weak", i, t, b) for i, (t, b) in enumerate(WEAK)]
        cases += [(name, "weak", i, t, attack(b)) for name, attack in ATTACKS.items() for i, (t, b) in enumerate(WEAK)]
        cases += [("llm_adaptive", "weak", i, WEAK[i][0], body) for i, body in adaptive.items()]
    if "good" in sets:
        cases += [("none", "good", 100 + i, t, b) for i, (t, b) in enumerate(GOOD)]
    if "borderline" in sets:
        adaptive = adaptive_injections(BORDERLINE, "adaptive_borderline")
        iterative = iterative_injections()
        iterative_v2 = iterative_injections(rubric="grant_v2", name="iterative_checklist")
        cases += [("none", "borderline", 200 + i, t, b) for i, (t, b) in enumerate(BORDERLINE)]
        cases += [(name, "borderline", 200 + i, t, attack(b))
                  for name, attack in ATTACKS.items() for i, (t, b) in enumerate(BORDERLINE)]
        cases += [("llm_adaptive", "borderline", 200 + i, BORDERLINE[i][0], b) for i, b in adaptive.items()]
        cases += [("llm_iterative", "borderline", 200 + i, BORDERLINE[i][0], b) for i, b in iterative.items()]
        cases += [("llm_iterative_vs_checklist", "borderline", 200 + i, BORDERLINE[i][0], b) for i, b in iterative_v2.items()]
    return [dict(attack=a, kind=k, proposal=p, title=t, body=b, model=m, defense=d, trial=tr, seed=1000 * tr + p + 1)
            for a, k, p, t, b in cases for m in models for d in defenses for tr in range(trials)]


def one(job: dict, systems: dict[str, str]) -> dict:
    req = build_request(job["model"], systems[job["defense"]], ROUND_ID, job["proposal"], job["title"], job["body"], job["seed"])
    line = {k: job[k] for k in ("attack", "kind", "proposal", "model", "defense", "trial")}
    for attempt in range(3):
        try:
            resp, chat_id = nearai.complete(req)
            sig = nearai.fetch_signature(chat_id)
            break
        except httpx.HTTPError:
            time.sleep(5 * (attempt + 1))
    else:
        return {**line, "error": "request failed"}
    try:
        review = nearai.parse_review(resp)
        score, flags = review.score, review.flags
    except ValueError:
        score, flags = None, []
    return {**line, "request_b64": base64.b64encode(req).decode(), "response_b64": base64.b64encode(resp).decode(),
            "signature": asdict(sig) if sig else None, "score": score, "flags": flags}


def run(models=REVIEW_MODELS, defenses=("naive", "hardened"), trials=2, budget_usd=3.0, workers=8,
        sets=("weak", "good")) -> Path:
    todo = jobs(models, defenses, trials, sets)
    price = prices()
    cost = sum(EST_IN * price[j["model"]][0] / 1e6 + EST_OUT * price[j["model"]][1] / 1e6 for j in todo)
    print(f"{len(todo)} review calls, estimated ${cost:.2f}")
    if cost > budget_usd:
        raise SystemExit(f"estimated cost ${cost:.2f} is over the ${budget_usd:.2f} budget")
    systems = {"naive": prompt("naive_v1"), "hardened": prompt("grant_v1"), "checklist": prompt("grant_v2")}
    out = RESULTS / f"{time.strftime('%Y-%m-%d')}-{'-'.join(sets)}-{'-'.join(defenses)}.jsonl"
    lock, done = threading.Lock(), [0]
    with open(out, "a") as f, ThreadPoolExecutor(workers) as pool:
        for line in pool.map(lambda j: one(j, systems), todo):
            if "error" in line:
                continue
            with lock:
                f.write(json.dumps(line, ensure_ascii=False) + "\n")
                f.flush()
                done[0] += 1
                if done[0] % 50 == 0:
                    print(f"{done[0]}/{len(todo)}", flush=True)
    print(f"wrote {out}")
    return out
