from __future__ import annotations

import json
import os
import tempfile
import uuid
from pathlib import Path

# Do not silently replace a caller-provided database configuration. A stale local or
# production URL must stop test collection before any application database is opened.
if os.getenv("DATABASE_URL"):
    raise RuntimeError(
        "DATABASE_URL is set in the test environment. Unset it; tests create their own isolated database."
    )

for _test_only_variable in (
    "DATABASE_PASSWORD_FILE",
    "DRILLLOOP_USERS_FILE",
    "DRILLLOOP_SESSION_SECRET_FILE",
    "DRILLLOOP_TRUSTED_HOSTS",
    "DRILLLOOP_CORS_ORIGINS",
):
    os.environ.pop(_test_only_variable, None)

_TEST_TEMPORARY_DIRECTORY = tempfile.TemporaryDirectory(prefix="drillloop-pytest-")
_TEST_DB_ROOT = Path(_TEST_TEMPORARY_DIRECTORY.name)
_TEST_DB_ROOT.chmod(0o700)
_TEST_DB_TOKEN = uuid.uuid4().hex
(_TEST_DB_ROOT / ".drillloop-test-owner").write_text(_TEST_DB_TOKEN, encoding="utf-8")
(_TEST_DB_ROOT / ".drillloop-test-owner").chmod(0o600)

os.environ["DRILLLOOP_TEST_MODE"] = "1"
os.environ["DRILLLOOP_ENVIRONMENT"] = "test"
os.environ["DRILLLOOP_UPLOAD_SCAN_MODE"] = "disabled"
os.environ["DRILLLOOP_TEST_DB_ROOT"] = str(_TEST_DB_ROOT)
os.environ["DRILLLOOP_TEST_DB_TOKEN"] = _TEST_DB_TOKEN
os.environ["DATABASE_URL"] = (
    f"sqlite:///{_TEST_DB_ROOT / f'test-bootstrap-{uuid.uuid4().hex}.sqlite3'}"
)
os.environ["DEMO_SEED"] = "0"
os.environ["DRILLLOOP_ENABLE_DEMO_SEED"] = "1"
os.environ["DRILLLOOP_SESSION_SECRET"] = uuid.uuid4().hex + uuid.uuid4().hex
os.environ["DRILLLOOP_COOKIE_SECURE"] = "0"

import pytest  # noqa: E402
from app.auth import hash_password  # noqa: E402

_TEST_PASSWORD = "test-only-password-for-suite"
os.environ["DRILLLOOP_USERS_JSON"] = json.dumps(
    [
        {
            "id": "test-admin",
            "username": "test-admin",
            "name": "Fixture Administrator",
            "role": "admin",
            "organization_id": "test-organization",
            "password_hash": hash_password(_TEST_PASSWORD),
        },
        {
            "id": "test-reviewer",
            "username": "test-reviewer",
            "name": "Fixture Reviewer",
            "role": "reviewer",
            "organization_id": "test-organization",
            "password_hash": hash_password(_TEST_PASSWORD),
        },
        {
            "id": "test-evaluator",
            "username": "test-evaluator",
            "name": "Fixture Evaluator",
            "role": "evaluator",
            "organization_id": "test-organization",
            "password_hash": hash_password(_TEST_PASSWORD),
        },
        {
            "id": "test-viewer",
            "username": "test-viewer",
            "name": "Fixture Viewer",
            "role": "viewer",
            "organization_id": "test-organization",
            "password_hash": hash_password(_TEST_PASSWORD),
        },
        {
            "id": "other-organization-admin",
            "username": "other-admin",
            "name": "Other Organization Admin",
            "role": "admin",
            "organization_id": "other-organization",
            "password_hash": hash_password(_TEST_PASSWORD),
        },
    ]
)

from app import db as database  # noqa: E402
from app.main import app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

_BOOTSTRAP_ENGINE = database.engine


@pytest.fixture
def client():
    database_url = f"sqlite:///{_TEST_DB_ROOT / f'test-{uuid.uuid4().hex}.sqlite3'}"
    test_engine = database.create_database_engine(database_url)
    database.engine = test_engine
    database.SessionLocal.configure(bind=test_engine)
    try:
        database.migrate_database(test_engine)
        database.init_db()
        with TestClient(app) as test_client:
            login = test_client.post(
                "/api/auth/login",
                json={"username": "test-admin", "password": _TEST_PASSWORD},
            )
            if login.status_code != 200:
                raise AssertionError(f"Isolated test identity could not sign in: {login.text}")
            test_client.headers.update({"X-CSRF-Token": login.json()["csrf_token"]})
            yield test_client
    finally:
        test_engine.dispose()
        database.engine = _BOOTSTRAP_ENGINE
        database.SessionLocal.configure(bind=_BOOTSTRAP_ENGINE)
