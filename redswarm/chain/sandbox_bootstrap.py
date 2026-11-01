"""Download and run a local NEAR sandbox node.

Findings recorded while building this (2026-11-02):
- Binary URL: https://s3-us-west-1.amazonaws.com/build.nearprotocol.com/nearcore/{Platform}-{arch}/{version}/near-sandbox.tar.gz
  Platform-arch pairs published by the NEAR tooling: Darwin-arm64, Linux-x86_64, Linux-aarch64.
  Darwin x86_64 is not supported; callers fall back to FakeChain there.
- Default version used by near-sandbox-rs: 2.14.0.
- CLI: `near-sandbox --home DIR init`, then `near-sandbox --home DIR run`; RPC on 127.0.0.1:3030
  by default; root account `test.near` with its key in DIR/validator_key.json.
- py-near add_public_key allowance is in yoctoNEAR (default 25 * 10**21), not gas.
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import socket
import subprocess
import tarfile
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

SANDBOX_VERSION = "2.14.0"
BASE_URL = "https://s3-us-west-1.amazonaws.com/build.nearprotocol.com/nearcore"
CACHE_DIR = Path(os.environ.get("REDSWARM_CACHE", Path.home() / ".cache" / "redswarm"))


class SandboxUnavailable(RuntimeError):
    pass


def platform_tag() -> str:
    system, machine = platform.system(), platform.machine().lower()
    if system == "Linux" and machine in ("x86_64", "amd64"):
        return "Linux-x86_64"
    if system == "Linux" and machine in ("aarch64", "arm64"):
        return "Linux-aarch64"
    if system == "Darwin" and machine == "arm64":
        return "Darwin-arm64"
    raise SandboxUnavailable(f"no sandbox binary for {system} {machine}")


def _find_binary(folder: Path) -> Path | None:
    if not folder.exists():
        return None
    return next((p for p in folder.rglob("near-sandbox") if p.is_file()), None)


def ensure_binary(version: str = SANDBOX_VERSION) -> Path:
    """Return the path to near-sandbox, downloading it into the cache on first use."""
    override = os.environ.get("NEAR_SANDBOX_BIN_PATH")
    if override:
        return Path(override)
    dest = CACHE_DIR / f"near-sandbox-{version}"
    existing = _find_binary(dest)
    if existing:
        return existing
    url = f"{BASE_URL}/{platform_tag()}/{version}/near-sandbox.tar.gz"
    dest.mkdir(parents=True, exist_ok=True)
    archive = dest / "near-sandbox.tar.gz"
    try:
        with httpx.stream("GET", url, follow_redirects=True, timeout=120) as r:
            r.raise_for_status()
            with open(archive, "wb") as f:
                for chunk in r.iter_bytes():
                    f.write(chunk)
    except httpx.HTTPError as e:
        shutil.rmtree(dest, ignore_errors=True)
        raise SandboxUnavailable(f"could not download {url}: {e}") from e
    with tarfile.open(archive) as tar:
        tar.extractall(dest, filter="data")
    archive.unlink()
    found = _find_binary(dest)
    if not found:
        raise SandboxUnavailable("archive did not contain a near-sandbox binary")
    found.chmod(0o755)
    return found


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@dataclass
class SandboxNode:
    home: Path
    rpc_url: str
    process: subprocess.Popen
    root_account: str
    root_key: str

    def stop(self) -> None:
        self.process.terminate()
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.kill()
        shutil.rmtree(self.home, ignore_errors=True)


def start_node(version: str = SANDBOX_VERSION) -> SandboxNode:
    binary = ensure_binary(version)
    home = Path(tempfile.mkdtemp(prefix="redswarm-sandbox-"))
    subprocess.run([binary, "--home", home, "init"], check=True, capture_output=True)
    rpc_port, net_port = _free_port(), _free_port()
    cfg_path = home / "config.json"
    cfg = json.loads(cfg_path.read_text())
    cfg["rpc"]["addr"] = f"127.0.0.1:{rpc_port}"
    cfg["network"]["addr"] = f"127.0.0.1:{net_port}"
    cfg_path.write_text(json.dumps(cfg))
    log = open(home / "node.log", "wb")
    process = subprocess.Popen([binary, "--home", home, "run"], stdout=log, stderr=log)
    rpc_url = f"http://127.0.0.1:{rpc_port}"
    deadline = time.time() + 60
    while time.time() < deadline:
        if process.poll() is not None:
            raise SandboxUnavailable(f"sandbox exited early, see {home / 'node.log'}")
        try:
            r = httpx.get(f"{rpc_url}/status", timeout=2)
            if r.status_code == 200 and r.json().get("sync_info", {}).get("latest_block_height", 0) > 0:
                break
        except httpx.HTTPError:
            pass
        time.sleep(0.5)
    else:
        process.kill()
        raise SandboxUnavailable("sandbox RPC did not come up in 60s")
    key = json.loads((home / "validator_key.json").read_text())
    return SandboxNode(home, rpc_url, process, key["account_id"], key["secret_key"])
