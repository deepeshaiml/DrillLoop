"""Build a throwaway, owner-marked runtime for local synthetic evaluations."""

from __future__ import annotations

import atexit
import json
import os
import secrets
import sys
import tempfile
import uuid
from pathlib import Path


def configure() -> Path:
    root = Path(tempfile.mkdtemp(prefix="drillloop-eval-"))
    root.chmod(0o700)
    token = secrets.token_hex(32)
    marker = root / ".drillloop-test-owner"
    marker.write_text(token, encoding="utf-8")
    marker.chmod(0o600)

    backend = Path(__file__).resolve().parents[1] / "backend"
    sys.path.insert(0, str(backend))
    os.environ["DRILLLOOP_TEST_MODE"] = "1"
    os.environ["DRILLLOOP_ENVIRONMENT"] = "test"
    os.environ["DRILLLOOP_TEST_DB_ROOT"] = str(root)
    os.environ["DRILLLOOP_TEST_DB_TOKEN"] = token
    os.environ["DATABASE_URL"] = f"sqlite:///{root / f'test-eval-{uuid.uuid4().hex}.sqlite3'}"
    os.environ["DRILLLOOP_UPLOAD_SCAN_MODE"] = "disabled"
    os.environ["DRILLLOOP_COOKIE_SECURE"] = "0"
    os.environ["DRILLLOOP_ENABLE_DEMO_SEED"] = "1"
    os.environ["DEMO_SEED"] = "0"
    os.environ["DRILLLOOP_SESSION_SECRET"] = secrets.token_hex(48)
    os.environ["DRILLLOOP_DEMO_OWNER_ID"] = "evaluation-admin"
    for name in (
        "DATABASE_PASSWORD_FILE",
        "DRILLLOOP_USERS_FILE",
        "DRILLLOOP_SESSION_SECRET_FILE",
        "DRILLLOOP_TRUSTED_HOSTS",
        "DRILLLOOP_CORS_ORIGINS",
    ):
        os.environ.pop(name, None)

    from app.auth import hash_password  # noqa: PLC0415

    os.environ["DRILLLOOP_USERS_JSON"] = json.dumps(
        [
            {
                "id": "evaluation-admin",
                "username": "evaluation-admin",
                "name": "Synthetic Evaluation Operator",
                "role": "admin",
                "organization_id": "synthetic-evaluation",
                "password_hash": hash_password("synthetic-evaluation-only-password"),
            }
        ]
    )

    def cleanup() -> None:
        if marker.is_file() and marker.read_text(encoding="utf-8").strip() == token:
            import shutil

            shutil.rmtree(root)

    atexit.register(cleanup)
    return root
