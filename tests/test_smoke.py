import subprocess
import sys


def test_cli_help():
    out = subprocess.run([sys.executable, "-m", "sieve.cli", "--help"], capture_output=True, text=True)
    assert out.returncode == 0
    assert "verify" in out.stdout
