from __future__ import annotations

import os
from collections.abc import Generator
from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, sessionmaker

from app.database_config import database_connect_args
from app.models import Base

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./drillloop.db")
TEST_DB_MARKER = ".drillloop-test-owner"


class UnsafeTestDatabaseError(ValueError):
    """Raised when a test database URL could target storage outside its owned temp root."""


def validate_test_database_url(
    database_url: str,
    *,
    test_root: str | Path | None = None,
    owner_token: str | None = None,
    require_new: bool = True,
) -> Path:
    """Validate that a test database is a new SQLite file owned by this test run."""
    try:
        url = make_url(database_url)
    except Exception as exc:
        raise UnsafeTestDatabaseError("Invalid test database URL") from exc

    if url.get_backend_name() != "sqlite":
        raise UnsafeTestDatabaseError("Tests may use only an isolated SQLite database")
    if not url.database or url.database == ":memory:":
        raise UnsafeTestDatabaseError("Tests require a uniquely named SQLite file")

    raw_path = Path(url.database)
    if not raw_path.is_absolute():
        raise UnsafeTestDatabaseError("Test database path must be absolute")
    if raw_path.is_symlink():
        raise UnsafeTestDatabaseError("Test database path may not be a symlink")

    root_value = test_root if test_root is not None else os.getenv("DRILLLOOP_TEST_DB_ROOT")
    expected_token = (
        owner_token if owner_token is not None else os.getenv("DRILLLOOP_TEST_DB_TOKEN")
    )
    if not root_value or not expected_token:
        raise UnsafeTestDatabaseError("Owned test database root and token are required")

    root_path = Path(root_value)
    if root_path.is_symlink():
        raise UnsafeTestDatabaseError("Test database root may not be a symlink")
    try:
        root = root_path.resolve(strict=True)
    except OSError as exc:
        raise UnsafeTestDatabaseError("Test database root does not exist") from exc

    marker = root / TEST_DB_MARKER
    if marker.is_symlink() or not marker.is_file():
        raise UnsafeTestDatabaseError("Test database ownership marker is missing or unsafe")
    try:
        actual_token = marker.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise UnsafeTestDatabaseError("Test database ownership marker cannot be read") from exc
    if not actual_token or actual_token != expected_token:
        raise UnsafeTestDatabaseError("Test database ownership token does not match")

    try:
        parent = raw_path.parent.resolve(strict=True)
    except OSError as exc:
        raise UnsafeTestDatabaseError("Test database parent directory does not exist") from exc
    if parent != root:
        raise UnsafeTestDatabaseError("Test database must be directly inside the owned temp root")
    if raw_path.name in {"drillloop.db", ".pytest-drillloop.db"}:
        raise UnsafeTestDatabaseError("Application database names are forbidden in tests")
    if not raw_path.name.startswith("test-") or raw_path.suffix != ".sqlite3":
        raise UnsafeTestDatabaseError("Test database must use a test-*.sqlite3 filename")
    if require_new and raw_path.exists():
        raise UnsafeTestDatabaseError(
            "Test database target already exists; refusing to overwrite it"
        )
    if raw_path.exists() and not raw_path.is_file():
        raise UnsafeTestDatabaseError("Test database target must be a regular file")

    return raw_path


def create_database_engine(database_url: str, *, require_new_test_db: bool = True) -> Engine:
    if os.getenv("DRILLLOOP_TEST_MODE") == "1":
        validate_test_database_url(database_url, require_new=require_new_test_db)
    return create_engine(
        database_url,
        connect_args=database_connect_args(database_url),
        pool_pre_ping=True,
    )


engine = create_database_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db(target_engine: Engine | None = None) -> None:
    """Fail closed unless Alembic and ORM schemas match; never create or alter tables here."""
    selected_engine = target_engine or engine
    config = _alembic_config()
    with selected_engine.connect() as connection:
        context = MigrationContext.configure(connection)
        inspector = inspect(connection)
        if "alembic_version" not in inspector.get_table_names():
            raise RuntimeError(
                "Database schema is not versioned. Back up and inspect it, then follow the "
                "database adoption runbook; fresh databases require `alembic upgrade head`."
            )
        current = set(context.get_current_heads())
        script = ScriptDirectory.from_config(config)
        expected = set(script.get_heads())
        if current != expected:
            raise RuntimeError(
                f"Database migration revision mismatch (current={sorted(current)}, "
                f"expected={sorted(expected)}); run `alembic upgrade head` after review."
            )
        differences = compare_metadata(context, Base.metadata)
        if differences:
            summary = "; ".join(str(item) for item in differences[:8])
            raise RuntimeError(
                "Database schema differs from the SQLAlchemy models; no automatic repair was "
                f"attempted. Differences: {summary}"
            )


def _alembic_config() -> Config:
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    return config


def migrate_database(target_engine: Engine | None = None) -> None:
    """Explicit migration entry point, mainly for isolated tests and operator tooling."""
    selected_engine = target_engine or engine
    config = _alembic_config()
    with selected_engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")


def get_db() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
