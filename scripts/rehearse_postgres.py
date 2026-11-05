#!/usr/bin/env python3
"""Run the full fictional browser, PostgreSQL migration, restart, and recovery rehearsal."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POSTGRES_IMAGE = (
    "postgres:18.6-alpine@sha256:10a5c69a83035ab5239f5620d708520e8b28f5aa1f2b20143e6024532edadfb5"
)
sys.path.insert(0, str(ROOT / "backend"))
from app.auth import hash_password  # noqa: E402


def _run(args: list[str], *, input_data: bytes | None = None) -> subprocess.CompletedProcess:
    result = subprocess.run(args, input=input_data, capture_output=True, check=False)
    if result.returncode:
        detail = result.stderr.decode("utf-8", errors="replace")[-3000:]
        raise RuntimeError(
            f"Command failed ({' '.join(args[:5])}; exit {result.returncode}): {detail}"
        )
    return result


def _health(url: str, timeout_seconds: float = 90) -> dict:
    deadline = time.monotonic() + timeout_seconds
    last_error = "not reached"
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3) as response:
                payload = json.loads(response.read())
                if response.status == 200 and payload.get("status") == "ready":
                    return payload
                last_error = f"unexpected status payload {payload!r}"
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = type(exc).__name__
        time.sleep(1)
    raise RuntimeError(f"Application readiness did not recover: {last_error}")


def _private_file(path: Path, content: bytes) -> None:
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(content)


def _psql(compose: list[str], database: str, query: str) -> str:
    result = _run(
        compose
        + [
            "exec",
            "-T",
            "db",
            "psql",
            "-X",
            "-A",
            "-t",
            "-F",
            "\t",
            "-U",
            "drillloop",
            "-d",
            database,
            "-c",
            query,
        ]
    )
    return result.stdout.decode("utf-8").strip()


def _counts(compose: list[str], database: str) -> dict[str, int]:
    tables = (
        "exercises",
        "exercise_grants",
        "sources",
        "observations",
        "findings",
        "corrective_actions",
        "audit_events",
    )
    query = " UNION ALL ".join(f"SELECT '{table}', count(*) FROM {table}" for table in tables)
    return {
        name: int(count)
        for name, count in (
            line.split("\t") for line in _psql(compose, database, query).splitlines()
        )
    }


def _source_fingerprints(compose: list[str], database: str) -> dict[str, str]:
    query = "SELECT id, sha256, replace(encode(source_bytes, 'base64'), chr(10), '') FROM sources ORDER BY id"
    result: dict[str, str] = {}
    for line in _psql(compose, database, query).splitlines():
        source_id, stored_digest, encoded = line.split("\t")
        actual_digest = hashlib.sha256(base64.b64decode(encoded)).hexdigest()
        if stored_digest != actual_digest:
            raise RuntimeError(f"Stored source bytes failed SHA-256 validation: {source_id}")
        result[source_id] = actual_digest
    return result


def _record_snapshots(compose: list[str], database: str) -> dict[str, list[dict]]:
    columns = {
        "exercises": "id,title,scenario,exercise_date,duration_minutes,objectives_json,criteria_json,evaluator_roles_json,participants_json,milestones_json,created_at",
        "exercise_grants": "id,exercise_id,user_id,organization_id,access_role,created_at",
        "sources": "id,exercise_id,filename,kind,mime_type,sha256,content_text,provenance_json,scan_status,created_at",
        "observations": "id,exercise_id,source_id,text,event_time_raw,event_time_normalized,time_confidence,source_locator,observation_type,extraction_method,recognition_confidence,created_at",
        "findings": "id,exercise_id,code,title,category,objective_id,observation,interpretation,evidence_ids_json,confidence,status,review_note,reviewer,created_at,updated_at",
        "corrective_actions": "id,exercise_id,finding_id,title,evidence_ids_json,owner,priority,due_date,acceptance_criteria,status,reviewer_decision,reviewer,closure_evidence,created_at,updated_at",
        "audit_events": "id,exercise_id,actor,action,object_id,details_json,created_at",
    }
    snapshots = {}
    for table, selected_columns in columns.items():
        query = (
            "SELECT COALESCE(json_agg(row_to_json(snapshot_row) ORDER BY snapshot_row.id), '[]'::json)::text "
            f"FROM (SELECT {selected_columns} FROM {table} ORDER BY id) AS snapshot_row"
        )
        snapshots[table] = json.loads(_psql(compose, database, query))
    return snapshots


def _volume_belongs_to(project: str, volume: str) -> bool:
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


def main() -> None:
    if not Path(ROOT / "frontend/node_modules/playwright").exists():
        raise SystemExit("Install frontend dependencies first: npm --prefix frontend ci")
    with socket.socket() as probe:
        if probe.connect_ex(("127.0.0.1", 8000)) == 0:
            raise SystemExit(
                "Loopback port 8000 is already in use; stop the local service before rehearsal."
            )

    project = f"drillloop-phase3-{secrets.token_hex(5)}"
    volume = f"{project}_drillloop-postgres"
    existing_volume = subprocess.run(
        ["docker", "volume", "inspect", volume], capture_output=True, check=False
    )
    if existing_volume.returncode == 0:
        raise SystemExit(
            "The generated Compose project volume already exists; refusing to reuse it."
        )

    root = Path(tempfile.mkdtemp(prefix="drillloop-phase3-postgres-"))
    root.chmod(0o700)
    owner_token = secrets.token_hex(32)
    marker = root / ".drillloop-owner"
    _private_file(marker, owner_token.encode())

    password = "phase3-disposable-db-password"
    admin_password = "phase3-disposable-admin-password"
    viewer_password = "phase3-disposable-viewer-password"
    _private_file(root / "database_password", password.encode())
    _private_file(root / ".pgpass", f"*:*:*:drillloop:{password}".encode())
    _private_file(root / "session_secret", secrets.token_hex(48).encode())
    users = [
        {
            "id": "demo-admin",
            "username": "demo-admin",
            "name": "Demo Administrator",
            "role": "admin",
            "organization_id": "phase3-synthetic",
            "password_hash": hash_password(admin_password),
        },
        {
            "id": "phase3-viewer",
            "username": "phase3-viewer",
            "name": "CI Viewer",
            "role": "viewer",
            "organization_id": "phase3-synthetic",
            "password_hash": hash_password(viewer_password),
        },
    ]
    _private_file(root / "users.json", json.dumps(users).encode())
    env_file = root / "compose.env"
    values = {
        "DRILLLOOP_DB_PASSWORD_FILE": root / "database_password",
        "DRILLLOOP_SESSION_SECRET_FILE": root / "session_secret",
        "DRILLLOOP_USERS_FILE": root / "users.json",
        "DRILLLOOP_ENVIRONMENT": "local",
        "DRILLLOOP_BUILD_VERSION": "phase3-rehearsal",
        "DRILLLOOP_BUILD_REVISION": "disposable",
        "DRILLLOOP_COOKIE_SECURE": "0",
        "DRILLLOOP_TRUSTED_HOSTS": "localhost,127.0.0.1",
        "DRILLLOOP_CORS_ORIGINS": "http://localhost:5173,http://127.0.0.1:5173",
        "DRILLLOOP_UPLOAD_SCAN_MODE": "disabled",
        "DRILLLOOP_PARSER_TIMEOUT_SECONDS": "15",
        "DRILLLOOP_PARSER_MEMORY_MB": "768",
        "DRILLLOOP_BIND_ADDRESS": "127.0.0.1",
        "DRILLLOOP_ENABLE_DEMO_SEED": "1",
        "DRILLLOOP_DEMO_OWNER_ID": "demo-admin",
        "DEMO_SEED": "0",
        "WHISPER_MODEL_PATH": "",
    }
    _private_file(
        env_file,
        "\n".join(f"{key}={value}" for key, value in values.items()).encode(),
    )
    compose = [
        "docker",
        "compose",
        "--env-file",
        str(env_file),
        "--project-name",
        project,
    ]
    database_name = "drillloop"
    restore_name = f"recovery_{secrets.token_hex(5)}"
    cleanup_error = None
    report = {
        "schema_version": "drillloop-postgres-rehearsal/v1",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "fictional_only": True,
        "compose_project": project,
        "stages": [],
    }
    try:
        _run(compose + ["config", "--quiet"])
        _run(compose + ["up", "--build", "--detach", "--wait", "db"])
        report["stages"].append("fresh PostgreSQL 18 database ready")
        _run(
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
                "8bb36fe0ea4c",
            ]
        )
        _run(
            compose
            + [
                "exec",
                "-T",
                "db",
                "psql",
                "-v",
                "ON_ERROR_STOP=1",
                "-U",
                "drillloop",
                "-d",
                database_name,
                "-c",
                "INSERT INTO exercises (id,title,scenario,exercise_date,duration_minutes,objectives_json,criteria_json,evaluator_roles_json,participants_json,milestones_json,created_at) VALUES ('PG-MIGRATION-SYNTHETIC','Synthetic populated upgrade','Fictional disposable data','2026-11-03',30,'[]','[]','[]','[]','[]',NOW()); INSERT INTO sources (id,exercise_id,filename,kind,mime_type,sha256,content_text,source_bytes,provenance_json,created_at) VALUES ('pg-migration-source','PG-MIGRATION-SYNTHETIC','synthetic.txt','text','text/plain','a12871fee210fb8619291eaea194581cbd2531e4b23759d225f6806923f63222','fictional source wording',decode('0102','hex'),'{}',NOW());",
            ]
        )
        _run(compose + ["--profile", "maintenance", "run", "--build", "--rm", "migrate"])
        migrated_source_status = _psql(
            compose,
            database_name,
            "SELECT scan_status FROM sources WHERE id='pg-migration-source'",
        )
        if migrated_source_status != "not_scanned":
            raise RuntimeError("Populated PostgreSQL upgrade did not preserve source scan state.")
        report["stages"].append(
            "PostgreSQL upgrade from initial revision preserved a source and applied scan-state default"
        )
        _run(compose + ["up", "--build", "--detach", "--wait", "app", "ingress"])
        readiness = _health("http://127.0.0.1:8000/api/ready")
        report["application"] = readiness
        report["stages"].append("container readiness and PostgreSQL connectivity passed")

        e2e_env = os.environ.copy()
        e2e_env.update(
            {
                "DRILLLOOP_E2E_BASE_URL": "http://127.0.0.1:8000",
                "DRILLLOOP_E2E_USERNAME": "demo-admin",
                "DRILLLOOP_E2E_PASSWORD": admin_password,
                "DRILLLOOP_E2E_OUTSIDER_USERNAME": "phase3-viewer",
                "DRILLLOOP_E2E_OUTSIDER_PASSWORD": viewer_password,
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
            raise RuntimeError(f"Browser workflow failed: {e2e.stderr[-3000:]}")
        report["browser_workflow"] = json.loads(e2e.stdout)
        report["stages"].append(
            "Playwright seeded/unfamiliar evidence, review, action closure, PDF, resume, access grant/revoke, and cross-user denial passed"
        )

        _run(
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
        report["stages"].append("Alembic model/schema consistency check passed on PostgreSQL")

        backup_path = root / "drillloop-postgres.dump"
        dump = _run(
            compose
            + [
                "exec",
                "-T",
                "db",
                "pg_dump",
                "-U",
                "drillloop",
                "-d",
                database_name,
                "--format=custom",
                "--no-owner",
                "--no-acl",
            ]
        )
        _private_file(backup_path, dump.stdout)
        _run(
            [
                "docker",
                "run",
                "--rm",
                "--network",
                "none",
                "--mount",
                f"type=bind,src={root},dst=/backup,readonly",
                POSTGRES_IMAGE,
                "pg_restore",
                "--list",
                f"/backup/{backup_path.name}",
            ]
        )
        report["backup"] = {
            "format": "PostgreSQL custom archive",
            "bytes": len(dump.stdout),
            "sha256": hashlib.sha256(dump.stdout).hexdigest(),
            "pg_restore_list": "passed",
            "mode": oct(stat.S_IMODE(backup_path.stat().st_mode)),
        }

        original_counts = _counts(compose, database_name)
        original_sources = _source_fingerprints(compose, database_name)
        original_records = _record_snapshots(compose, database_name)
        grants_query = "SELECT exercise_id || '|' || user_id || '|' || organization_id || '|' || access_role FROM exercise_grants ORDER BY exercise_id,user_id"
        original_grants = _psql(compose, database_name, grants_query)
        account_ids = {user["id"] for user in users}
        granted_users = {
            value
            for value in _psql(
                compose, database_name, "SELECT DISTINCT user_id FROM exercise_grants"
            ).splitlines()
            if value
        }
        if not granted_users.issubset(account_ids):
            raise RuntimeError(
                "Active exercise grants reference users absent from the configured directory."
            )
        _run(compose + ["exec", "-T", "db", "createdb", "-U", "drillloop", restore_name])
        database_container = _run(compose + ["ps", "-q", "db"]).stdout.decode().strip()
        _run(
            [
                "docker",
                "run",
                "--rm",
                "--network",
                f"container:{database_container}",
                "--mount",
                f"type=bind,src={root},dst=/backup,readonly",
                "--env",
                "PGPASSFILE=/backup/.pgpass",
                POSTGRES_IMAGE,
                "pg_restore",
                "--exit-on-error",
                "--no-owner",
                "--no-acl",
                "--dbname",
                f"postgresql://drillloop@127.0.0.1:5432/{restore_name}",
                f"/backup/{backup_path.name}",
            ]
        )
        restored_counts = _counts(compose, restore_name)
        restored_sources = _source_fingerprints(compose, restore_name)
        restored_records = _record_snapshots(compose, restore_name)
        restored_grants = _psql(compose, restore_name, grants_query)
        if (
            original_counts != restored_counts
            or original_sources != restored_sources
            or original_grants != restored_grants
            or original_records != restored_records
        ):
            raise RuntimeError(
                "PostgreSQL restored rows, metadata, review decisions, access grants, or source-byte hashes did not match."
            )
        if original_counts["findings"] < 1 or original_counts["corrective_actions"] < 1:
            raise RuntimeError("Browser rehearsal did not create findings and corrective actions.")
        if not any(
            row["status"] == "approved" and row["reviewer"] for row in restored_records["findings"]
        ):
            raise RuntimeError("Restored findings did not retain human reviewer attribution.")
        if not any(
            row["status"] == "closed" and row["reviewer"] and row["closure_evidence"]
            for row in restored_records["corrective_actions"]
        ):
            raise RuntimeError(
                "Restored corrective actions did not retain reviewer/closure records."
            )
        if not any(
            row["action"] == "exercise_access_granted" for row in restored_records["audit_events"]
        ) or not any(
            row["action"] == "exercise_access_revoked" for row in restored_records["audit_events"]
        ):
            raise RuntimeError("Restored audit history did not retain access grant/revoke events.")
        revision = _psql(compose, restore_name, "SELECT version_num FROM alembic_version")
        report["restore"] = {
            "target": "new disposable database",
            "table_counts": restored_counts,
            "source_rows_with_verified_sha256": len(restored_sources),
            "all_record_snapshots_match": True,
            "reviewer_decisions_and_action_closure_verified": True,
            "access_grant_audit_history_verified": True,
            "active_grants_reference_configured_users": True,
            "access_grant_rows_match": True,
            "alembic_revision": revision,
            "counts_and_source_bytes_match": True,
            "tables_checked": list(restored_counts),
        }
        _run(
            compose
            + [
                "--profile",
                "maintenance",
                "run",
                "--rm",
                "--no-deps",
                "-e",
                f"DATABASE_URL=postgresql+psycopg://drillloop@db:5432/{restore_name}",
                "migrate",
                "alembic",
                "check",
            ]
        )
        report["stages"].append(
            "PostgreSQL archive restored into new DB; row snapshots, source hashes, reviewer decisions, access records, and schema check matched"
        )

        _run(compose + ["restart", "app"])
        _health("http://127.0.0.1:8000/api/ready")
        _run(compose + ["restart", "db"])
        _run(compose + ["up", "--detach", "--wait", "db"])
        report["post_restart_readiness"] = _health("http://127.0.0.1:8000/api/ready")
        post_restart_counts = _counts(compose, database_name)
        post_restart_sources = _source_fingerprints(compose, database_name)
        post_restart_records = _record_snapshots(compose, database_name)
        if (
            post_restart_counts != original_counts
            or post_restart_sources != original_sources
            or post_restart_records != original_records
        ):
            raise RuntimeError("Post-restart data counts or source-byte hashes changed.")
        report["post_restart_table_counts"] = post_restart_counts
        report["stages"].append(
            "Application and PostgreSQL restarts recovered with persisted records"
        )
    finally:
        down = subprocess.run(compose + ["down"], capture_output=True, text=True, check=False)
        if down.returncode:
            cleanup_error = (
                "Compose stop/remove did not complete cleanly; isolated resources were preserved."
            )
        elif _volume_belongs_to(project, volume):
            removed = subprocess.run(
                ["docker", "volume", "rm", volume], capture_output=True, text=True, check=False
            )
            if removed.returncode:
                cleanup_error = "Isolated database volume could not be removed; it remains under its unique project name."
        if marker.is_file() and marker.read_text(encoding="utf-8") == owner_token:
            shutil.rmtree(root)
    if cleanup_error:
        report["cleanup_note"] = cleanup_error
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
