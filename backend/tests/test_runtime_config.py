from __future__ import annotations

import json

import pytest
from app import runtime_config
from app.auth import hash_password


def test_production_configuration_rejects_local_sqlite(monkeypatch):
    monkeypatch.setenv("DRILLLOOP_ENVIRONMENT", "production")
    monkeypatch.setattr(runtime_config, "DATABASE_URL", "sqlite:////tmp/drillloop-not-used.sqlite3")

    with pytest.raises(RuntimeError, match="requires PostgreSQL"):
        runtime_config.validate_runtime_config()


def test_staging_configuration_rejects_local_sqlite(monkeypatch):
    monkeypatch.setenv("DRILLLOOP_ENVIRONMENT", "staging")
    monkeypatch.setattr(runtime_config, "DATABASE_URL", "sqlite:////tmp/drillloop-not-used.sqlite3")

    with pytest.raises(RuntimeError, match="Staging requires PostgreSQL"):
        runtime_config.validate_runtime_config()


def test_scanner_timeout_configuration_is_bounded(monkeypatch):
    monkeypatch.setenv("DRILLLOOP_ENVIRONMENT", "local")
    monkeypatch.setenv("DRILLLOOP_SCANNER_TIMEOUT_SECONDS", "31")

    with pytest.raises(RuntimeError, match="Scanner timeout must be between 1 and 30 seconds"):
        runtime_config.validate_runtime_config()


def test_production_configuration_requires_secure_secret_files(monkeypatch, tmp_path):
    db_secret = tmp_path / "database-password"
    session_secret = tmp_path / "session-secret"
    users_file = tmp_path / "users.json"
    db_secret.write_text("synthetic-test-db-password", encoding="utf-8")
    session_secret.write_text(
        "synthetic-test-session-secret-with-at-least-32-bytes", encoding="utf-8"
    )
    users_file.write_text(
        json.dumps(
            [
                {
                    "id": "runtime-admin",
                    "username": "runtime-admin",
                    "name": "Synthetic Runtime Admin",
                    "role": "admin",
                    "organization_id": "synthetic",
                    "password_hash": hash_password("runtime-only-test-password"),
                }
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        runtime_config,
        "DATABASE_URL",
        "postgresql+psycopg://drillloop@localhost:5432/drillloop",
    )
    monkeypatch.setenv("DRILLLOOP_ENVIRONMENT", "production")
    monkeypatch.setenv("DATABASE_PASSWORD_FILE", str(db_secret))
    monkeypatch.setenv("DRILLLOOP_SESSION_SECRET_FILE", str(session_secret))
    monkeypatch.setenv("DRILLLOOP_USERS_FILE", str(users_file))
    monkeypatch.setenv("DRILLLOOP_COOKIE_SECURE", "1")
    monkeypatch.setenv("DRILLLOOP_UPLOAD_SCAN_MODE", "required")
    monkeypatch.setenv("DRILLLOOP_SCANNER_HOST", "clamav.internal")
    monkeypatch.setenv("DRILLLOOP_TRUSTED_HOSTS", "drillloop.example.invalid")
    monkeypatch.setenv("DEMO_SEED", "0")
    monkeypatch.setenv("DRILLLOOP_ENABLE_DEMO_SEED", "0")

    runtime_config.validate_runtime_config()


def test_production_configuration_rejects_explicit_demo_seed_flag(monkeypatch, tmp_path):
    session_secret = tmp_path / "session-secret"
    users_file = tmp_path / "users.json"
    session_secret.write_text("test-secret-value-longer-than-thirty-two-bytes", encoding="utf-8")
    users_file.write_text(
        json.dumps(
            [
                {
                    "id": "admin",
                    "username": "admin",
                    "name": "Admin",
                    "role": "admin",
                    "organization_id": "test",
                    "password_hash": hash_password("runtime-only-test-password"),
                }
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("DRILLLOOP_ENVIRONMENT", "production")
    monkeypatch.setattr(
        runtime_config,
        "DATABASE_URL",
        "postgresql+psycopg://drillloop@localhost:5432/drillloop",
    )
    monkeypatch.setenv("DATABASE_PASSWORD_FILE", "/configured/database-secret")
    monkeypatch.setenv("DRILLLOOP_SESSION_SECRET_FILE", str(session_secret))
    monkeypatch.setenv("DRILLLOOP_USERS_FILE", str(users_file))
    monkeypatch.setenv("DRILLLOOP_COOKIE_SECURE", "1")
    monkeypatch.setenv("DRILLLOOP_UPLOAD_SCAN_MODE", "required")
    monkeypatch.setenv("DRILLLOOP_SCANNER_HOST", "clamav.internal")
    monkeypatch.setenv("DRILLLOOP_TRUSTED_HOSTS", "drillloop.example.invalid")
    monkeypatch.setenv("DEMO_SEED", "0")
    monkeypatch.setenv("DRILLLOOP_ENABLE_DEMO_SEED", "1")

    with pytest.raises(RuntimeError, match="Synthetic demo seeding must be disabled"):
        runtime_config.validate_runtime_config()


def test_production_configuration_requires_scanning_and_trusted_hosts(monkeypatch, tmp_path):
    session_secret = tmp_path / "session-secret"
    users_file = tmp_path / "users.json"
    session_secret.write_text("test-secret-value-longer-than-thirty-two-bytes", encoding="utf-8")
    users_file.write_text(
        json.dumps(
            [
                {
                    "id": "admin",
                    "username": "admin",
                    "name": "Admin",
                    "role": "admin",
                    "organization_id": "test",
                    "password_hash": hash_password("runtime-only-test-password"),
                }
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("DRILLLOOP_ENVIRONMENT", "production")
    monkeypatch.setattr(
        runtime_config,
        "DATABASE_URL",
        "postgresql+psycopg://drillloop@localhost:5432/drillloop",
    )
    monkeypatch.setenv("DATABASE_PASSWORD_FILE", "/configured/database-secret")
    monkeypatch.setenv("DRILLLOOP_SESSION_SECRET_FILE", str(session_secret))
    monkeypatch.setenv("DRILLLOOP_USERS_FILE", str(users_file))
    monkeypatch.setenv("DRILLLOOP_COOKIE_SECURE", "1")
    monkeypatch.setenv("DRILLLOOP_UPLOAD_SCAN_MODE", "optional")
    monkeypatch.setenv("DRILLLOOP_SCANNER_HOST", "clamav.internal")
    monkeypatch.setenv("DRILLLOOP_TRUSTED_HOSTS", "drillloop.example.invalid")
    monkeypatch.setenv("DEMO_SEED", "0")
    monkeypatch.setenv("DRILLLOOP_ENABLE_DEMO_SEED", "0")

    with pytest.raises(RuntimeError, match="UPLOAD_SCAN_MODE=required"):
        runtime_config.validate_runtime_config()
