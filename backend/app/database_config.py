from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy.engine import make_url


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
