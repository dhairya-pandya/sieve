"""The page rebuilds review requests in the browser; its builder must match the shared vectors byte for byte."""
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = r"""
const fs = require("fs");
const src = fs.readFileSync(process.argv[1], "utf8");
eval(src.match(/function buildRequest[\s\S]*?\n}\n/)[0]);
const vs = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
let bad = 0;
for (const v of vs) {
  const got = buildRequest(v.model, v.system, v.round_id, v.proposal_id, v.title, v.body, v.seed,
    { days: v.record[0], submitted: v.record[1], passed: v.record[2], delivered: v.record[3] }, v.stage, v.evidence);
  if (got !== v.request) { bad++; console.log("mismatch: " + v.name); }
}
console.log(bad ? "FAIL" : "OK");
"""


@pytest.mark.skipif(not shutil.which("node"), reason="needs node")
def test_browser_builder_matches_vectors():
    out = subprocess.run(["node", "-e", SCRIPT, str(ROOT / "web" / "app.js"), str(ROOT / "tests" / "fixtures" / "request_vectors.json")],
                         capture_output=True, text=True)
    assert out.stdout.strip().endswith("OK"), out.stdout + out.stderr
