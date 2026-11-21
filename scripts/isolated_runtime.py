"""Build a throwaway, owner-marked runtime for local synthetic evaluations."""

from __future__ import annotations

import atexit
import json
import os
import secrets
import socket
import sys
import tempfile
import threading
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


def configure(backend: Path | None = None, *, retain_under: Path | None = None) -> Path:
    root = Path(tempfile.mkdtemp(prefix="drillloop-eval-", dir=retain_under))
    root.chmod(0o700)
    token = secrets.token_hex(32)
    marker = root / ".drillloop-test-owner"
    marker.write_text(token, encoding="utf-8")
    marker.chmod(0o600)

    backend = backend or Path(__file__).resolve().parents[1] / "backend"
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
        "DRILLLOOP_TEST_DB_ALLOW_EXISTING",
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

    if retain_under is None:
        atexit.register(cleanup)
    return root


@contextmanager
def serve(app, *, port: int = 0) -> Iterator[int]:
    import uvicorn

    with socket.socket() as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", port))
        port = listener.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(app, log_level="warning", access_log=False))
        thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
        thread.start()
        try:
            deadline = time.monotonic() + 10
            while not server.started and thread.is_alive() and time.monotonic() < deadline:
                time.sleep(0.05)
            if not server.started:
                raise RuntimeError("The isolated DrillLoop server did not start.")
            yield port
        finally:
            server.should_exit = True
            thread.join(timeout=10)
            if thread.is_alive():
                raise RuntimeError("The isolated DrillLoop server did not stop.")
