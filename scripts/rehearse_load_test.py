#!/usr/bin/env python3
"""Start a disposable local API and run the bounded readiness load test."""

from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.isolated_runtime import configure  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requests", type=int, default=500)
    parser.add_argument("--concurrency", type=int, default=20)
    parser.add_argument("--port", type=int, default=8129)
    args = parser.parse_args()
    if not 1 <= args.requests <= 1000 or not 1 <= args.concurrency <= 20:
        raise SystemExit("Limits are 1–1000 requests and 1–20 concurrent workers.")
    if not 1024 <= args.port <= 65535:
        raise SystemExit("Port must be between 1024 and 65535.")
    with socket.socket() as probe:
        if probe.connect_ex(("127.0.0.1", args.port)) == 0:
            raise SystemExit(f"Loopback port {args.port} is already in use.")

    owned_root = configure()
    import os

    from app import db as database

    os.environ["DRILLLOOP_BUILD_VERSION"] = "phase3-load-rehearsal"
    os.environ["DRILLLOOP_BUILD_REVISION"] = "synthetic-disposable"
    database.migrate_database()
    log_path = owned_root / "api.log"
    log_stream = log_path.open("w", encoding="utf-8")
    api_environment = os.environ.copy()
    api_environment.pop("DRILLLOOP_TEST_MODE", None)
    api = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--app-dir",
            "backend",
            "--host",
            "127.0.0.1",
            "--port",
            str(args.port),
            "--no-access-log",
        ],
        cwd=ROOT,
        env=api_environment,
        stdout=log_stream,
        stderr=subprocess.STDOUT,
    )
    url = f"http://127.0.0.1:{args.port}/api/ready"
    try:
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            if api.poll() is not None:
                raise RuntimeError(
                    "Disposable API exited before readiness: "
                    + log_path.read_text(encoding="utf-8")[-3000:]
                )
            try:
                with urllib.request.urlopen(url, timeout=2) as response:
                    if response.status == 200:
                        break
            except (urllib.error.URLError, TimeoutError):
                time.sleep(0.25)
        else:
            raise RuntimeError("Disposable API did not become ready within 45 seconds.")

        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/load_test.py"),
                "--base-url",
                f"http://127.0.0.1:{args.port}",
                "--requests",
                str(args.requests),
                "--concurrency",
                str(args.concurrency),
                "--pid",
                str(api.pid),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode:
            raise RuntimeError(f"Load test failed: {result.stderr[-2000:]} {result.stdout[-2000:]}")
        report = json.loads(result.stdout)
    finally:
        api.terminate()
        try:
            api.wait(timeout=15)
        except subprocess.TimeoutExpired:
            api.kill()
            api.wait(timeout=5)
        log_stream.close()

    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
