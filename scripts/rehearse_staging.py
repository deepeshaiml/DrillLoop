#!/usr/bin/env python3
"""Rehearse hardened staging settings with disposable PostgreSQL and test TLS."""

from __future__ import annotations

import hashlib
import http.cookiejar
import io
import json
import os
import secrets
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

from pypdf import PdfWriter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.auth import hash_password  # noqa: E402


def run(args: list[str], *, input_data: bytes | None = None) -> subprocess.CompletedProcess:
    result = subprocess.run(args, input=input_data, capture_output=True, check=False)
    if result.returncode:
        message = result.stderr.decode("utf-8", errors="replace")[-2500:]
        raise RuntimeError(f"Command failed ({' '.join(args[:5])}): {message}")
    return result


def private_file(path: Path, value: bytes, mode: int = 0o600) -> None:
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, mode)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(value)


def volume_owned(project: str, volume: str) -> bool:
    result = subprocess.run(
        [
            "docker",
            "volume",
            "inspect",
            "--format",
            '{{ index .Labels "com.docker.compose.project" }}',
            volume,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0 and result.stdout.strip() == project


def free_loopback_port(excluded: set[int] | None = None) -> int:
    excluded = excluded or set()
    for _attempt in range(20):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        if port not in excluded:
            return port
    raise RuntimeError("Could not allocate unique loopback ports for the staging rehearsal.")


class LocalSession:
    def __init__(self, origin: str):
        self.origin = origin.rstrip("/")
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=ssl._create_unverified_context()),
            urllib.request.HTTPCookieProcessor(self.jar),
        )
        self.csrf: str | None = None

    def request(
        self,
        path: str,
        *,
        method: str = "GET",
        payload: dict | None = None,
        raw_body: bytes | None = None,
        headers: dict | None = None,
        timeout_seconds: float = 15,
    ) -> tuple[int, dict, bytes, object]:
        request_headers = {"Host": "127.0.0.1"}
        if payload is not None:
            request_headers["Content-Type"] = "application/json"
        if headers:
            request_headers.update(headers)
        if method not in {"GET", "HEAD", "OPTIONS"} and self.csrf:
            request_headers["X-CSRF-Token"] = self.csrf
        data = json.dumps(payload).encode() if payload is not None else raw_body
        request = urllib.request.Request(
            self.origin + path, data=data, headers=request_headers, method=method
        )
        try:
            response = self.opener.open(request, timeout=timeout_seconds)
        except urllib.error.HTTPError as error:
            response = error
        body = response.read()
        try:
            decoded = (
                json.loads(body)
                if body and "json" in response.headers.get("Content-Type", "")
                else {}
            )
        except json.JSONDecodeError:
            decoded = {}
        return response.status, decoded, body, response.headers

    def login(self, username: str, password: str) -> object:
        status, data, _body, headers = self.request(
            "/api/auth/login", method="POST", payload={"username": username, "password": password}
        )
        if status != 200:
            raise RuntimeError(f"HTTPS login failed: HTTP {status}")
        self.csrf = data["csrf_token"]
        return headers


def wait_ready(session: LocalSession, timeout_seconds: int = 60) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            status, data, _body, _headers = session.request("/api/ready")
            if status == 200 and data.get("status") == "ready":
                return True
        except (urllib.error.URLError, TimeoutError):
            pass
        time.sleep(1)
    return False


def verify_ingress_rate_limit(origin: str) -> None:
    def probe(_index: int) -> tuple[int, object, bytes]:
        opener = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=ssl._create_unverified_context())
        )
        request = urllib.request.Request(origin + "/api/live", headers={"Host": "127.0.0.1"})
        try:
            response = opener.open(request, timeout=10)
        except urllib.error.HTTPError as error:
            response = error
        return response.status, response.headers, response.read()

    with ThreadPoolExecutor(max_workers=48) as pool:
        responses = list(pool.map(probe, range(48)))
    limited = [result for result in responses if result[0] == 429]
    if not limited:
        raise RuntimeError("Nginx API rate limit did not return a controlled 429 under a burst.")
    for _status, headers, body in limited:
        try:
            details = json.loads(body).get("detail", {})
        except json.JSONDecodeError as exc:
            raise RuntimeError("Rate-limited ingress response was not structured JSON.") from exc
        if (
            headers.get("Retry-After") != "2"
            or details.get("code") != "EDGE_RATE_LIMITED"
            or "retry" not in details.get("message", "").casefold()
            or headers.get("Strict-Transport-Security") is None
        ):
            raise RuntimeError("Rate-limited ingress response lacked guidance or security headers.")


def multipart_body(files: list[tuple[str, bytes, str]]) -> tuple[bytes, str]:
    boundary = f"drillloop-{secrets.token_hex(12)}"
    chunks = []
    for filename, content, mime_type in files:
        chunks.extend(
            [
                (
                    f'--{boundary}\r\nContent-Disposition: form-data; name="files"; '
                    f'filename="{filename}"\r\nContent-Type: {mime_type}\r\n\r\n'
                ).encode(),
                content,
                b"\r\n",
            ]
        )
    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def synthetic_pdf() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def main() -> None:
    http_port = free_loopback_port()
    https_port = free_loopback_port({http_port})

    project = f"drillloop-staging-{secrets.token_hex(5)}"
    volume = f"{project}_drillloop-postgres"
    scanner_volume = f"{project}_clamav-signatures"
    for candidate_volume in (volume, scanner_volume):
        if (
            subprocess.run(
                ["docker", "volume", "inspect", candidate_volume], capture_output=True, check=False
            ).returncode
            == 0
        ):
            raise SystemExit(
                f"Generated staging volume {candidate_volume} already exists; refusing to reuse it."
            )

    owned_root = Path(tempfile.mkdtemp(prefix="drillloop-staging-"))
    owned_root.chmod(0o700)
    owner_token = secrets.token_hex(32)
    private_file(owned_root / ".drillloop-staging-owner", owner_token.encode())
    tls_dir = owned_root / "tls"
    tls_dir.mkdir(mode=0o700)
    key_path = tls_dir / "privkey.pem"
    cert_path = tls_dir / "fullchain.pem"
    run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-days",
            "1",
            "-keyout",
            str(key_path),
            "-out",
            str(cert_path),
            "-subj",
            "/CN=localhost",
            "-addext",
            "subjectAltName=DNS:localhost,IP:127.0.0.1",
        ]
    )
    # This short-lived self-signed test key is not a deployment credential.
    key_path.chmod(0o644)

    db_password = secrets.token_urlsafe(32)
    admin_password = secrets.token_urlsafe(24)
    viewer_password = secrets.token_urlsafe(24)
    private_file(owned_root / "database_password", db_password.encode())
    private_file(owned_root / "session_secret", secrets.token_hex(48).encode())
    users = [
        {
            "id": "staging-admin",
            "username": "staging-admin",
            "name": "Disposable Staging Administrator",
            "role": "admin",
            "organization_id": "staging-synthetic",
            "password_hash": hash_password(admin_password),
        },
        {
            "id": "staging-viewer",
            "username": "staging-viewer",
            "name": "Disposable Staging Viewer",
            "role": "viewer",
            "organization_id": "staging-synthetic",
            "password_hash": hash_password(viewer_password),
        },
    ]
    private_file(owned_root / "users.json", json.dumps(users).encode())

    tls_config = (ROOT / "deploy/nginx/drillloop.conf").read_text(encoding="utf-8")
    tls_config = tls_config.replace(
        "server_name drillloop.example.invalid;", "server_name localhost 127.0.0.1;"
    )
    private_file(owned_root / "nginx.conf", tls_config.encode())
    override = owned_root / "compose.override.yml"
    override.write_text(
        "services:\n"
        "  ingress:\n"
        "    ports: !override\n"
        f'      - "127.0.0.1:{http_port}:8080"\n'
        f'      - "127.0.0.1:{https_port}:8443"\n'
        "    volumes: !override\n"
        f"      - {owned_root / 'nginx.conf'}:/etc/nginx/conf.d/default.conf:ro\n"
        f"      - {tls_dir}:/etc/nginx/tls:ro\n",
        encoding="utf-8",
    )

    env_values = {
        "DRILLLOOP_DB_PASSWORD_FILE": owned_root / "database_password",
        "DRILLLOOP_SESSION_SECRET_FILE": owned_root / "session_secret",
        "DRILLLOOP_USERS_FILE": owned_root / "users.json",
        "DRILLLOOP_ENVIRONMENT": "staging",
        "DRILLLOOP_BUILD_VERSION": "phase5-disposable-staging",
        "DRILLLOOP_BUILD_REVISION": "synthetic-local-rehearsal",
        "DRILLLOOP_COOKIE_SECURE": "1",
        "DRILLLOOP_TRUSTED_HOSTS": "localhost,127.0.0.1",
        "DRILLLOOP_CORS_ORIGINS": "",
        "DRILLLOOP_UPLOAD_SCAN_MODE": "required",
        "DRILLLOOP_SCANNER_HOST": "clamav",
        "DRILLLOOP_SCANNER_PORT": "3310",
        "DRILLLOOP_SCANNER_MAX_SIGNATURE_AGE_HOURS": "72",
        "DRILLLOOP_FRESHCLAM_CHECKS": "4",
        "DRILLLOOP_SCANNER_TIMEOUT_SECONDS": "5",
        "DRILLLOOP_PARSER_TIMEOUT_SECONDS": "15",
        "DRILLLOOP_PARSER_QUEUE_TIMEOUT_SECONDS": "30",
        "DRILLLOOP_PARSER_MEMORY_MB": "768",
        "DRILLLOOP_BIND_ADDRESS": "127.0.0.1",
        "DRILLLOOP_ENABLE_DEMO_SEED": "0",
        "DRILLLOOP_DEMO_OWNER_ID": "",
        "DEMO_SEED": "0",
        "WHISPER_MODEL_PATH": "",
    }
    private_file(
        owned_root / "compose.env",
        "\n".join(f"{key}={value}" for key, value in env_values.items()).encode(),
    )
    compose = [
        "docker",
        "compose",
        "--profile",
        "scanner",
        "--env-file",
        str(owned_root / "compose.env"),
        "-f",
        str(ROOT / "docker-compose.yml"),
        "-f",
        str(override),
        "--project-name",
        project,
    ]
    report: dict = {
        "schema_version": "drillloop-staging-rehearsal/v1",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "fictional_only": True,
        "environment": "disposable local Compose, secure staging settings, test-only TLS certificate",
        "compose_project": project,
        "checks": {},
    }
    cleanup_error = None
    failure = None
    try:
        run(compose + ["config", "--quiet"])
        report["checks"]["compose_configuration"] = "PASS"
        run(compose + ["build", "app"])
        image = run(["docker", "image", "inspect", "--format", "{{.Id}}", f"{project}-app"])
        report["checks"]["container_build"] = "PASS"
        report["image_id"] = image.stdout.decode().strip() if image.stdout else "built by Compose"
        run(compose + ["up", "--detach", "--wait", "db"])
        report["checks"]["postgres_startup"] = "PASS"
        run(
            compose
            + [
                "--profile",
                "maintenance",
                "run",
                "--build",
                "--rm",
                "migrate",
                "alembic",
                "upgrade",
                "head",
            ]
        )
        run(
            compose
            + [
                "--profile",
                "maintenance",
                "run",
                "--rm",
                "--no-deps",
                "migrate",
                "alembic",
                "check",
            ]
        )
        run(
            compose
            + [
                "--profile",
                "maintenance",
                "run",
                "--rm",
                "--no-deps",
                "migrate",
                "alembic",
                "current",
            ]
        )
        report["checks"]["explicit_migration_and_schema_check"] = "PASS"
        run(compose + ["up", "--detach", "--wait", "--wait-timeout", "600", "clamav"])
        scanner_container = run(compose + ["ps", "-q", "clamav"]).stdout.decode().strip()
        scanner_inspect = json.loads(run(["docker", "inspect", scanner_container]).stdout.decode())[
            0
        ]
        if scanner_inspect.get("HostConfig", {}).get("PortBindings"):
            raise RuntimeError("ClamAV must not publish its TCP port on the host.")
        scanner_mounts = scanner_inspect.get("Mounts", [])
        if not any(
            mount.get("Destination") == "/var/lib/clamav" and mount.get("Type") == "volume"
            for mount in scanner_mounts
        ):
            raise RuntimeError("ClamAV signature database is not on its persistent volume.")
        if scanner_inspect.get("HostConfig", {}).get("Memory") != 5 * 1024**3:
            raise RuntimeError("ClamAV did not start with the configured 5 GiB memory limit.")
        if not any(
            value == "FRESHCLAM_CHECKS=4"
            for value in scanner_inspect.get("Config", {}).get("Env", [])
        ):
            raise RuntimeError("FreshClam update checks are not configured as expected.")
        report["scanner_deployment"] = {
            "host_port_bindings": scanner_inspect.get("HostConfig", {}).get("PortBindings"),
            "signature_volume": next(
                mount.get("Name")
                for mount in scanner_mounts
                if mount.get("Destination") == "/var/lib/clamav"
            ),
            "memory_bytes": scanner_inspect.get("HostConfig", {}).get("Memory"),
            "freshclam_checks_per_day": 4,
            "image": scanner_inspect.get("Config", {}).get("Image"),
        }
        report["scanner_image"] = (
            run(compose + ["exec", "-T", "clamav", "clamdscan", "--version"])
            .stdout.decode("utf-8", errors="replace")
            .strip()
        )
        run(compose + ["up", "--detach", "--wait", "app", "ingress"])
        origin = f"https://127.0.0.1:{https_port}"
        admin = LocalSession(origin)
        status, health, _body, tls_headers = admin.request("/api/ready")
        if status != 200 or health.get("status") != "ready":
            raise RuntimeError(f"TLS ingress readiness failed: HTTP {status}")
        if tls_headers.get("Strict-Transport-Security") is None:
            raise RuntimeError("TLS ingress did not return HSTS.")
        if tls_headers.get("X-Content-Type-Options") != "nosniff":
            raise RuntimeError("TLS ingress did not return nosniff.")
        if health.get("scanner", {}).get("scan_capability") != "clean_and_eicar_verified":
            raise RuntimeError("App readiness did not verify clean/EICAR scan capability.")
        report["scanner_readiness"] = health["scanner"]
        report["checks"]["https_tls_hsts_headers_and_readiness"] = "PASS"

        verify_ingress_rate_limit(origin)
        report["checks"]["controlled_ingress_rate_limit_429_retry_after"] = "PASS"
        time.sleep(3)

        cookie_headers = admin.login("staging-admin", admin_password)
        set_cookie = "\n".join(cookie_headers.get_all("Set-Cookie", []))
        cookie_requirements = ("drillloop_session=", "HttpOnly", "Secure", "SameSite=lax")
        if not all(value in set_cookie for value in cookie_requirements):
            raise RuntimeError("Session cookie did not include HttpOnly, Secure, and SameSite=Lax.")
        status, session, _body, _headers = admin.request("/api/auth/session")
        if status != 200 or session.get("identity", {}).get("role") != "admin":
            raise RuntimeError("File-injected named-user authentication failed.")
        report["checks"]["file_injected_auth_and_secure_cookie"] = "PASS"

        e2e_env = os.environ.copy()
        e2e_env.update(
            {
                "DRILLLOOP_E2E_BASE_URL": origin,
                "DRILLLOOP_E2E_USERNAME": "staging-admin",
                "DRILLLOOP_E2E_PASSWORD": admin_password,
                "DRILLLOOP_E2E_OUTSIDER_USERNAME": "staging-viewer",
                "DRILLLOOP_E2E_OUTSIDER_PASSWORD": viewer_password,
                "DRILLLOOP_E2E_OUTSIDER_NAME": "Disposable Staging Viewer",
                "DRILLLOOP_E2E_REVIEWER_NAME": "Disposable Staging Administrator",
                "DRILLLOOP_E2E_EXPECT_SCAN_STATUS": "clean",
                "DRILLLOOP_E2E_IGNORE_HTTPS_ERRORS": "1",
            }
        )
        e2e = subprocess.run(
            ["node", str(ROOT / "frontend/e2e/live-workflow.mjs")],
            cwd=ROOT,
            env=e2e_env,
            capture_output=True,
            text=True,
            check=False,
        )
        if e2e.returncode:
            app_logs = subprocess.run(
                compose + ["logs", "--tail", "80", "app"],
                capture_output=True,
                text=True,
                check=False,
            )
            ingress_logs = subprocess.run(
                compose + ["logs", "--tail", "80", "ingress"],
                capture_output=True,
                text=True,
                check=False,
            )
            raise RuntimeError(
                f"Scanner-enabled browser workflow failed: {e2e.stderr[-3000:]}\n"
                f"Recent disposable app logs:\n{app_logs.stdout[-6000:]}\n"
                f"Recent disposable ingress logs:\n{ingress_logs.stdout[-3000:]}"
            )
        report["browser_workflow"] = json.loads(e2e.stdout)
        report["checks"]["postgres_clamav_https_browser_workflow"] = "PASS"

        load_env = os.environ.copy()
        load_env.update(
            {
                "DRILLLOOP_LOAD_USERNAME": "staging-admin",
                "DRILLLOOP_LOAD_PASSWORD": admin_password,
            }
        )
        load = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/rehearse_phase5_load.py"),
                "--base-url",
                origin,
                "--compose-project",
                project,
                "--workflows-per-level",
                "20",
                "--max-concurrency",
                "10",
            ],
            cwd=ROOT,
            env=load_env,
            capture_output=True,
            text=True,
            check=False,
        )
        if load.returncode:
            raise RuntimeError(
                "PostgreSQL/ClamAV workflow load rehearsal failed: "
                f"{load.stderr[-3000:]}\n{load.stdout[-3000:]}"
            )
        report["performance"] = json.loads(load.stdout)
        report["checks"]["postgres_clamav_concurrency_1_2_5_10"] = "PASS"

        status, _data, _body, _headers = admin.request("/api/metrics")
        if status != 200:
            raise RuntimeError("Admin metrics endpoint was not available to its authorized user.")
        viewer = LocalSession(origin)
        viewer.login("staging-viewer", viewer_password)
        forbidden_status, _data, _body, _headers = viewer.request("/api/metrics")
        if forbidden_status != 403:
            raise RuntimeError(
                f"Viewer metrics access should be forbidden, got HTTP {forbidden_status}."
            )
        report["checks"]["role_protected_metrics"] = "PASS"

        bad_host_status, _data, _body, _headers = admin.request(
            "/api/ready", headers={"Host": "untrusted.invalid"}
        )
        if bad_host_status != 400:
            raise RuntimeError(
                f"Untrusted Host header should be rejected, got HTTP {bad_host_status}."
            )
        report["checks"]["trusted_host_allowlist"] = "PASS"

        scanner_exercise_id = f"SCANNER-{secrets.token_hex(4)}"
        status, created, _body, _headers = admin.request(
            "/api/exercises",
            method="POST",
            payload={
                "id": scanner_exercise_id,
                "title": "Fictional ClamAV integration rehearsal",
                "scenario": "Synthetic workflow used to verify clean and rejected scan handling.",
                "exercise_date": "2026-11-04",
                "duration_minutes": 30,
                "objectives": [{"id": "S-01", "text": "Restore the fictional service."}],
            },
        )
        if status != 201 or created.get("id") != scanner_exercise_id:
            raise RuntimeError("Could not create the synthetic ClamAV workflow exercise.")

        csv_body, csv_type = multipart_body(
            [
                (
                    "scanner-clean.csv",
                    b"event_id,timestamp,event\nSYN-01,14:00,Fictional power failed.\nSYN-02,14:02,Fictional power restored.\n",
                    "text/csv",
                )
            ]
        )
        csv_status, csv_result, _body, _headers = admin.request(
            f"/api/exercises/{scanner_exercise_id}/evidence",
            method="POST",
            raw_body=csv_body,
            headers={"Content-Type": csv_type},
        )
        if csv_status != 201 or len(csv_result.get("sources", [])) != 1:
            raise RuntimeError(f"Actual ClamAV clean CSV upload failed: HTTP {csv_status}.")
        pdf_body, pdf_type = multipart_body(
            [("scanner-clean.pdf", synthetic_pdf(), "application/pdf")]
        )
        pdf_status, pdf_result, _body, _headers = admin.request(
            f"/api/exercises/{scanner_exercise_id}/evidence",
            method="POST",
            raw_body=pdf_body,
            headers={"Content-Type": pdf_type},
        )
        if pdf_status != 201 or len(pdf_result.get("sources", [])) != 1:
            raise RuntimeError(f"Actual ClamAV clean PDF upload failed: HTTP {pdf_status}.")

        eicar = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
        eicar_body, eicar_type = multipart_body([("eicar.txt", eicar, "text/plain")])
        eicar_status, eicar_result, _body, _headers = admin.request(
            f"/api/exercises/{scanner_exercise_id}/evidence",
            method="POST",
            raw_body=eicar_body,
            headers={"Content-Type": eicar_type},
        )
        if eicar_status != 422 or eicar_result.get("detail", {}).get("code") != "MALWARE_REJECTED":
            raise RuntimeError(f"Actual ClamAV did not reject EICAR safely: HTTP {eicar_status}.")

        invalid_body, invalid_type = multipart_body(
            [
                (
                    "invalid.csv",
                    b"timestamp,event\n99:99,Invalid synthetic timestamp.\n",
                    "text/csv",
                )
            ]
        )
        invalid_status, invalid_result, _body, _headers = admin.request(
            f"/api/exercises/{scanner_exercise_id}/evidence",
            method="POST",
            raw_body=invalid_body,
            headers={"Content-Type": invalid_type},
        )
        if (
            invalid_status != 400
            or invalid_result.get("detail", {}).get("code") != "INVALID_TIMESTAMP"
        ):
            raise RuntimeError(f"Invalid synthetic file was not rejected: HTTP {invalid_status}.")

        status, scanner_detail, _body, _headers = admin.request(
            f"/api/exercises/{scanner_exercise_id}"
        )
        scanner_sources = scanner_detail.get("sources", [])
        if (
            status != 200
            or len(scanner_sources) != 2
            or {item["filename"]: item["scan_status"] for item in scanner_sources}
            != {"scanner-clean.csv": "clean", "scanner-clean.pdf": "clean"}
            or any(item["filename"] == "eicar.txt" for item in scanner_sources)
        ):
            raise RuntimeError("Scanner rejection or invalid extraction reached source records.")
        audit_events = scanner_detail.get("audit_events", [])
        clean_csv_source = next(
            (item for item in scanner_sources if item["filename"] == "scanner-clean.csv"),
            None,
        )
        malware_audit = next(
            (
                event
                for event in audit_events
                if event.get("action") == "upload_rejected"
                and event.get("details", {}).get("error_code") == "MALWARE_REJECTED"
            ),
            None,
        )
        accepted_audit = next(
            (
                event
                for event in audit_events
                if event.get("action") == "evidence_uploaded"
                and clean_csv_source
                and event.get("object_id") == clean_csv_source["id"]
            ),
            None,
        )
        if (
            malware_audit is None
            or not malware_audit["details"].get("scanner_version")
            or not malware_audit["details"].get("signature_timestamp")
            or accepted_audit is None
            or accepted_audit["details"].get("scan_status") != "clean"
            or not accepted_audit["details"].get("scanner_version")
        ):
            raise RuntimeError("Scanner decisions or signature provenance were not auditable.")
        quarantine_entries = (
            run(
                compose
                + [
                    "exec",
                    "-T",
                    "app",
                    "python",
                    "-c",
                    "from pathlib import Path; print(len(list(Path('/run/drillloop-quarantine').iterdir())))",
                ]
            )
            .stdout.decode()
            .strip()
        )
        if quarantine_entries != "0":
            raise RuntimeError(
                "Scanner quarantine was not cleaned after accepted/rejected uploads."
            )
        report["checks"]["actual_clamav_clean_csv_pdf_eicar_invalid_quarantine_audit"] = "PASS"

        exercise_id = f"STAGING-{secrets.token_hex(4)}"
        created_status, created, _body, _headers = admin.request(
            "/api/exercises",
            method="POST",
            payload={
                "id": exercise_id,
                "title": "Disposable staging evidence failure rehearsal",
                "scenario": "Fictional local rehearsal of scanner outage and isolation.",
                "exercise_date": "2026-11-04",
                "duration_minutes": 30,
                "objectives": [{"id": "S-01", "text": "Restore the fictional service."}],
            },
        )
        if created_status != 201 or created.get("id") != exercise_id:
            raise RuntimeError("Could not create the disposable staging exercise.")
        body = b"Fictional evidence only. No external or confidential records."
        timeout_body, timeout_type = multipart_body([("scanner-timeout.txt", body, "text/plain")])
        scanner_container = run(compose + ["ps", "-q", "clamav"]).stdout.decode().strip()
        if not scanner_container:
            raise RuntimeError("Could not identify the disposable ClamAV container.")
        run(["docker", "pause", scanner_container])
        try:
            timeout_status, timeout_result, _body, _headers = admin.request(
                f"/api/exercises/{exercise_id}/evidence",
                method="POST",
                raw_body=timeout_body,
                headers={"Content-Type": timeout_type},
                timeout_seconds=12,
            )
        finally:
            subprocess.run(
                ["docker", "unpause", scanner_container],
                capture_output=True,
                check=False,
            )
        if (
            timeout_status != 503
            or timeout_result.get("detail", {}).get("code") != "SCANNER_TIMEOUT"
        ):
            raise RuntimeError(
                f"Paused ClamAV did not produce the expected safe timeout: HTTP {timeout_status}."
            )
        run(["docker", "restart", scanner_container])
        run(compose + ["up", "--detach", "--wait", "--wait-timeout", "180", "clamav"])
        if not wait_ready(admin, timeout_seconds=180):
            raise RuntimeError("Scanner readiness did not recover after unpausing ClamAV.")

        run(compose + ["stop", "clamav"])
        outage_body, outage_type = multipart_body([("scanner-outage.txt", body, "text/plain")])
        outage_status, outage_result, _body, _headers = admin.request(
            f"/api/exercises/{exercise_id}/evidence",
            method="POST",
            raw_body=outage_body,
            headers={"Content-Type": outage_type},
        )
        if (
            outage_status != 503
            or outage_result.get("detail", {}).get("code") != "SCANNER_UNAVAILABLE"
        ):
            raise RuntimeError(
                f"Required scanner outage did not fail closed: HTTP {outage_status}."
            )
        run(compose + ["up", "--detach", "--wait", "--wait-timeout", "180", "clamav"])
        if not wait_ready(admin, timeout_seconds=180):
            raise RuntimeError("Scanner readiness did not recover after scanner restart.")

        status, detail, _body, _headers = admin.request(f"/api/exercises/{exercise_id}")
        if status != 200 or detail.get("sources") or detail.get("timeline"):
            raise RuntimeError(
                "Unscanned staging upload reached persisted source or analysis state."
            )
        rejected_codes = {
            event.get("details", {}).get("error_code")
            for event in detail.get("audit_events", [])
            if event.get("action") == "upload_rejected"
        }
        if not {"SCANNER_TIMEOUT", "SCANNER_UNAVAILABLE"}.issubset(rejected_codes):
            raise RuntimeError("Scanner timeout/outage decisions were not audited.")
        metrics_status, _data, metrics_body, _headers = admin.request("/api/metrics")
        scan_metric = 'drillloop_uploads_total{status="rejected",scan_status="unavailable"}'
        if metrics_status != 200 or scan_metric.encode() not in metrics_body:
            raise RuntimeError("Rejected scanner outage was not reflected in protected metrics.")
        timeout_metric = 'drillloop_uploads_total{status="rejected",scan_status="timeout"}'
        if timeout_metric.encode() not in metrics_body:
            raise RuntimeError("Scanner timeout was not reflected in protected metrics.")
        report["checks"]["scanner_timeout_and_outage_fail_closed_audit_no_source"] = "PASS"

        viewer_status, _data, _body, _headers = viewer.request(f"/api/exercises/{exercise_id}")
        if viewer_status != 404:
            raise RuntimeError(
                f"Cross-user exercise access should be hidden, got HTTP {viewer_status}."
            )
        report["checks"]["cross_user_exercise_isolation"] = "PASS"

        # This migration target is newly created by this uniquely named rehearsal project.
        def query(database: str, sql: str) -> str:
            return (
                run(
                    compose
                    + [
                        "exec",
                        "-T",
                        "db",
                        "psql",
                        "-X",
                        "-A",
                        "-t",
                        "-U",
                        "drillloop",
                        "-d",
                        database,
                        "-c",
                        sql,
                    ]
                )
                .stdout.decode()
                .strip()
            )

        before_count = int(query("drillloop", "SELECT count(*) FROM exercises"))
        run(compose + ["restart", "app"])
        if (
            not wait_ready(admin)
            or int(query("drillloop", "SELECT count(*) FROM exercises")) != before_count
        ):
            raise RuntimeError("Application restart did not retain database state and readiness.")
        run(compose + ["restart", "db"])
        ready = wait_ready(admin, timeout_seconds=90)
        if not ready or int(query("drillloop", "SELECT count(*) FROM exercises")) != before_count:
            raise RuntimeError("Database restart did not recover readiness and persisted records.")
        report["checks"]["application_and_database_restart_persistence"] = "PASS"

        backup = run(
            compose
            + [
                "exec",
                "-T",
                "db",
                "pg_dump",
                "-U",
                "drillloop",
                "-d",
                "drillloop",
                "--format=custom",
                "--no-owner",
                "--no-acl",
            ]
        ).stdout
        backup_path = owned_root / "staging-rehearsal.dump"
        private_file(backup_path, backup)
        database_container = run(compose + ["ps", "-q", "db"]).stdout.decode().strip()
        run(compose + ["exec", "-T", "db", "createdb", "-U", "drillloop", "staging_restore"])
        run(["docker", "cp", str(backup_path), f"{database_container}:/tmp/staging-rehearsal.dump"])
        run(
            compose
            + [
                "exec",
                "-T",
                "db",
                "pg_restore",
                "--exit-on-error",
                "--no-owner",
                "--no-acl",
                "-U",
                "drillloop",
                "-d",
                "staging_restore",
                "/tmp/staging-rehearsal.dump",
            ]
        )
        restored_count = int(query("staging_restore", "SELECT count(*) FROM exercises"))
        if restored_count != before_count:
            raise RuntimeError("Disposable backup restore did not preserve exercise rows.")
        report["backup_restore"] = {
            "status": "PASS",
            "target": "new disposable database in the same uniquely named project",
            "archive_bytes": len(backup),
            "archive_sha256": hashlib.sha256(backup).hexdigest(),
            "original_exercise_count": before_count,
            "restored_exercise_count": restored_count,
        }
        report["checks"]["backup_restore_to_new_database"] = "PASS"
        report["checks"]["rollback_to_previous_image"] = "NOT RUN"
        report["limitations"] = [
            "The TLS certificate is self-signed and exists only for this local rehearsal.",
            "The scanner deployment is locally operational but is not organization-approved for production.",
            "The 72-hour maximum signature age is a proposed, unapproved owner policy.",
            "No prior compatible image was supplied, so a previous-image rollback was not executed.",
            "This is not an approved or externally hosted staging environment.",
        ]
    except Exception as exc:
        failure = exc
        report["failure"] = {"type": type(exc).__name__, "message": str(exc)}
    finally:
        down = subprocess.run(compose + ["down"], capture_output=True, text=True, check=False)
        if down.returncode:
            cleanup_error = (
                "Unique staging project shutdown failed; disposable resources were preserved."
            )
        else:
            for candidate_volume in (volume, scanner_volume):
                if not volume_owned(project, candidate_volume):
                    continue
                removed = subprocess.run(
                    ["docker", "volume", "rm", candidate_volume],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if removed.returncode:
                    cleanup_error = f"Unique disposable volume {candidate_volume} remains; it was not force-removed."
        marker = owned_root / ".drillloop-staging-owner"
        if marker.is_file() and marker.read_text(encoding="utf-8") == owner_token:
            shutil.rmtree(owned_root)
    if cleanup_error:
        report["cleanup_note"] = cleanup_error
    print(json.dumps(report, indent=2, sort_keys=True))
    if failure is not None:
        raise SystemExit(1) from failure


if __name__ == "__main__":
    main()
