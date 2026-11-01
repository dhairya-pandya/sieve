import re
import subprocess
import sys
from pathlib import Path

import pytest

from redswarm.demo.run_demo import run

ROOT = Path(__file__).resolve().parents[1]
MARKER = re.compile(r"^(POSTED|VERIFIED|SWARM|LEAD SALE|BREAK|REPORT|SURVIVED):")


def markers(lines):
    return [line for line in lines if MARKER.match(line)]


@pytest.mark.asyncio
async def test_demo_output_matches_expected():
    lines = await run("fake", emit=lambda _: None)
    expected = (ROOT / "redswarm" / "demo" / "expected_output.txt").read_text().splitlines()
    assert markers(lines) == expected


def test_demo_runs_with_no_env_vars():
    out = subprocess.run([sys.executable, "-m", "redswarm.demo.run_demo", "--chain", "fake"],
                         cwd=ROOT, env={}, capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    assert "SURVIVED:" in out.stdout and "BREAK:" in out.stdout


@pytest.mark.slow
@pytest.mark.asyncio
async def test_demo_output_matches_expected_on_sandbox():
    try:
        lines = await run("sandbox", emit=lambda _: None)
    except Exception as e:
        pytest.skip(f"sandbox unavailable: {e}")
    expected = (ROOT / "redswarm" / "demo" / "expected_output.txt").read_text().splitlines()
    assert markers(lines) == expected
