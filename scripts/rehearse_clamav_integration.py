#!/usr/bin/env python3
"""Run the actual ClamAV API integration test against an owned loopback-only container."""

from __future__ import annotations

import json
import os
import secrets
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLAMAV_IMAGE = (
    "clamav/clamav-debian:1.5.4@sha256:"
    "c21aa18cc0a358678255a3dfb343a4555b58f71b97d7b869df8fdf7ea0a5b4b1"
)
OWNER_LABEL = "drillloop.phase5.scanner-test-owner"


def run(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, check=False)
    if check and result.returncode:
        raise RuntimeError(f"Command failed ({' '.join(args[:5])}): {result.stderr[-2000:]}")
    return result


def free_loopback_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def container_owner(container: str) -> str | None:
    result = run(
        [
            "docker",
            "inspect",
            "--format",
            f'{{{{ index .Config.Labels "{OWNER_LABEL}" }}}}',
            container,
        ],
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def volume_owner(volume: str) -> str | None:
    result = run(
        [
            "docker",
            "volume",
            "inspect",
            "--format",
            f'{{{{ index .Labels "{OWNER_LABEL}" }}}}',
            volume,
        ],
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def main() -> None:
    token = secrets.token_hex(8)
    container = f"drillloop-phase5-clamav-test-{token}"
    volume = f"drillloop-phase5-clamav-signatures-{token}"
    port = free_loopback_port()
    if run(["docker", "inspect", container], check=False).returncode == 0:
        raise SystemExit(f"Generated container {container} already exists; refusing to reuse it.")
    if run(["docker", "volume", "inspect", volume], check=False).returncode == 0:
        raise SystemExit(f"Generated volume {volume} already exists; refusing to reuse it.")

    created_volume = False
    created_container = False
    test_result = None
    cleanup_errors = []
    try:
        run(["docker", "volume", "create", "--label", f"{OWNER_LABEL}={token}", volume])
        created_volume = True
        run(
            [
                "docker",
                "run",
                "--detach",
                "--name",
                container,
                "--label",
                f"{OWNER_LABEL}={token}",
                "--memory",
                "5g",
                "--cpus",
                "2",
                "--publish",
                f"127.0.0.1:{port}:3310",
                "--mount",
                f"type=volume,src={volume},dst=/var/lib/clamav",
                "--env",
                "CLAMAV_NO_MILTERD=true",
                "--env",
                "FRESHCLAM_CHECKS=4",
                "--health-cmd=clamdcheck.sh",
                "--health-interval=10s",
                "--health-timeout=5s",
                "--health-retries=18",
                "--health-start-period=6m",
                CLAMAV_IMAGE,
            ]
        )
        created_container = True
        inspect = json.loads(run(["docker", "inspect", container]).stdout)[0]
        binding = inspect.get("HostConfig", {}).get("PortBindings", {}).get("3310/tcp", [])
        mounts = inspect.get("Mounts", [])
        if (
            len(binding) != 1
            or binding[0].get("HostIp") != "127.0.0.1"
            or not any(
                item.get("Name") == volume and item.get("Destination") == "/var/lib/clamav"
                for item in mounts
            )
        ):
            raise RuntimeError("Test scanner is not loopback-only with its owned signature volume.")

        deadline = time.monotonic() + 600
        while time.monotonic() < deadline:
            state = json.loads(run(["docker", "inspect", container]).stdout)[0]["State"]
            health = state.get("Health", {}).get("Status")
            if health == "healthy":
                break
            if state.get("Status") != "running" or health == "unhealthy":
                logs = run(["docker", "logs", "--tail", "60", container], check=False)
                raise RuntimeError(
                    f"Actual ClamAV service failed startup (state={state.get('Status')}, health={health}).\n{logs.stdout[-4000:]}"
                )
            time.sleep(2)
        else:
            raise RuntimeError("Timed out waiting for the actual ClamAV service health check.")

        environment = os.environ.copy()
        environment.pop("DATABASE_URL", None)
        environment["DRILLLOOP_TEST_CLAMAV_HOST"] = "127.0.0.1"
        environment["DRILLLOOP_TEST_CLAMAV_PORT"] = str(port)
        test_result = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "backend/tests/test_clamav_integration.py"],
            cwd=ROOT,
            env=environment,
            check=False,
        )
    finally:
        if created_container:
            if container_owner(container) == token:
                removed = run(["docker", "rm", "--force", container], check=False)
                if removed.returncode:
                    cleanup_errors.append(f"Owned test container remains: {container}.")
            else:
                cleanup_errors.append(
                    f"Container ownership check failed; preserved container {container}."
                )
        if created_volume:
            if volume_owner(volume) == token:
                removed = run(["docker", "volume", "rm", volume], check=False)
                if removed.returncode:
                    cleanup_errors.append(f"Owned test signature volume remains: {volume}.")
            else:
                cleanup_errors.append(f"Volume ownership check failed; preserved volume {volume}.")

    result = {
        "scanner_image": CLAMAV_IMAGE,
        "loopback_only_host_binding": f"127.0.0.1:{port}",
        "actual_clamav_integration_test_exit_code": (
            test_result.returncode if test_result is not None else None
        ),
        "cleanup_errors": cleanup_errors,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    if cleanup_errors:
        raise SystemExit(
            "Test resources were preserved because cleanup ownership could not be verified."
        )
    if test_result is None or test_result.returncode:
        raise SystemExit(test_result.returncode if test_result else 1)


if __name__ == "__main__":
    main()
