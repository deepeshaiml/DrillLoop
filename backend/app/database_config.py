from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import event
from sqlalchemy.engine import Engine, make_url


def database_connect_args(database_url: str) -> dict:
    """Resolve database driver options without creating a global SQLAlchemy engine."""
    url = make_url(database_url)
    if url.get_backend_name() == "sqlite":
        return {"check_same_thread": False}
    secret_path = os.getenv("DATABASE_PASSWORD_FILE", "")
    if url.get_backend_name() == "postgresql" and secret_path:
        path = Path(secret_path)
        if path.is_symlink() or not path.is_file():
            raise RuntimeError("DATABASE_PASSWORD_FILE must point to a regular secret file.")
        password = path.read_text(encoding="utf-8").rstrip("\r\n")
        if not password:
            raise RuntimeError("Database password secret file is empty.")
        return {"password": password}
    return {}


def enforce_sqlite_foreign_keys(engine: Engine) -> Engine:
    if engine.dialect.name == "sqlite":

        @event.listens_for(engine, "connect")
        def enable_foreign_keys(connection, _record):
            connection.execute("PRAGMA foreign_keys=ON")

    return engine
