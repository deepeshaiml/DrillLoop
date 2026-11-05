#!/usr/bin/env python3
"""Wait for CI's ClamAV daemon to load signatures inside the freshness policy."""

from __future__ import annotations

import argparse
import json
import re
import socket
import subprocess
import sys
import time
from datetime import UTC, datetime

VERSION_PATTERN = re.compile(r"^ClamAV (?P<engine>[^/]+)/(?P<database>\d+)/(?P<timestamp>.+)$")
DIAGNOSTIC_PATTERN = re.compile(
    r"freshclam|daily\.cvd|main\.cvd|bytecode\.cvd|download|update|error|warning|rate limit",
    re.IGNORECASE,
)
URL_PATTERN = re.compile(r"https?://\S+", re.IGNORECASE)
IP_PATTERN = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")


def _clamd_command(host: str, port: int, command: str, timeout: float) -> str:
    with socket.create_connection((host, port), timeout=timeout) as connection:
        connection.settimeout(timeout)
        connection.sendall(f"z{command}\0".encode("ascii"))
        response = bytearray()
        while len(response) < 4096:
            block = connection.recv(min(1024, 4096 - len(response)))
            if not block:
                break
            response.extend(block)
            if b"\0" in block or b"\n" in block:
                break
        if len(response) >= 4096 and b"\0" not in response and b"\n" not in response:
            raise OSError("ClamD response exceeded the readiness protocol limit.")
        return bytes(response).rstrip(b"\0\r\n").decode("utf-8", errors="replace")


def _parse_version(version: str) -> tuple[str, str, datetime] | None:
    match = VERSION_PATTERN.fullmatch(version)
    if match is None:
        return None
    try:
        signature_at = datetime.strptime(match.group("timestamp"), "%a %b %d %H:%M:%S %Y").replace(
            tzinfo=UTC
        )
    except ValueError:
        return None
    return match.group("engine"), match.group("database"), signature_at


def _diagnostics(container_id: str, last_check: dict[str, object] | None) -> None:
    print("ClamAV readiness failed; uploads remain blocked by the scanner policy.", file=sys.stderr)
    if last_check is not None:
        print(
            "Last clamd check: " + json.dumps(last_check, sort_keys=True),
            file=sys.stderr,
        )

    try:
        result = subprocess.run(
            ["docker", "logs", "--since", "15m", container_id],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        print("FreshClam container logs were unavailable for diagnostics.", file=sys.stderr)
        return
    lines = (result.stdout + "\n" + result.stderr).splitlines()
    selected = [line for line in lines if DIAGNOSTIC_PATTERN.search(line)]
    if not selected:
        print("No FreshClam update errors or warnings were captured.", file=sys.stderr)
        return
    print("Filtered FreshClam diagnostics:", file=sys.stderr)
    for line in selected[-40:]:
        safe_line = URL_PATTERN.sub("<redacted-url>", line)
        safe_line = IP_PATTERN.sub("<redacted-ip>", safe_line)
        print(safe_line[:400], file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--container-id", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=3310)
    parser.add_argument("--max-age-hours", type=float, default=72)
    parser.add_argument("--timeout-seconds", type=float, default=600)
    parser.add_argument("--interval-seconds", type=float, default=5)
    parser.add_argument("--socket-timeout-seconds", type=float, default=3)
    parser.add_argument("--expected-engine-version", default="1.5.4")
    args = parser.parse_args()

    if (
        not 1 <= args.port <= 65535
        or not 1 <= args.max_age_hours <= 24 * 14
        or args.timeout_seconds <= 0
        or args.interval_seconds <= 0
        or not 0 < args.socket_timeout_seconds <= 30
    ):
        parser.error("port, freshness, and timeout settings are outside supported bounds")

    deadline = time.monotonic() + args.timeout_seconds
    last_check: dict[str, object] | None = None
    while time.monotonic() < deadline:
        checked_at = datetime.now(UTC)
        try:
            ping = _clamd_command(args.host, args.port, "PING", args.socket_timeout_seconds)
            version = _clamd_command(args.host, args.port, "VERSION", args.socket_timeout_seconds)
            parsed = _parse_version(version)
            if ping != "PONG":
                last_check = {"ping": ping[:80], "scanner_version": version[:160]}
            elif parsed is None:
                last_check = {
                    "ping": ping,
                    "scanner_version": version[:160],
                    "error": "signature timestamp could not be parsed",
                }
            else:
                engine_version, database_version, signature_at = parsed
                age_seconds = (checked_at - signature_at).total_seconds()
                age_hours = age_seconds / 3600
                last_check = {
                    "ping": ping,
                    "engine_version": engine_version,
                    "database_version": database_version,
                    "signature_timestamp": signature_at.isoformat(),
                    "signature_age_hours": round(age_hours, 2),
                    "max_signature_age_hours": args.max_age_hours,
                }
                if (
                    engine_version == args.expected_engine_version
                    and -300 <= age_seconds <= args.max_age_hours * 3600
                ):
                    print(
                        json.dumps(
                            {"status": "ready", **last_check},
                            sort_keys=True,
                        )
                    )
                    return 0
        except (OSError, TimeoutError) as exc:
            last_check = {"error": type(exc).__name__, "message": str(exc)[:160]}

        time.sleep(min(args.interval_seconds, max(0, deadline - time.monotonic())))

    _diagnostics(args.container_id, last_check)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
