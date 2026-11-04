from __future__ import annotations

from pathlib import Path

import pytest
from app.db import TEST_DB_MARKER, UnsafeTestDatabaseError, validate_test_database_url
from sqlalchemy.engine import URL


def _owned_root(tmp_path: Path) -> tuple[Path, str]:
    root = tmp_path / "owned-test-root"
    root.mkdir()
    token = "test-owner-token"
    (root / TEST_DB_MARKER).write_text(token, encoding="utf-8")
    return root, token


def _sqlite_url(path: Path) -> str:
    return URL.create("sqlite", database=str(path)).render_as_string(hide_password=False)


def test_accepts_only_new_named_database_in_owned_root(tmp_path):
    root, token = _owned_root(tmp_path)
    target = root / "test-independent-case.sqlite3"

    assert (
        validate_test_database_url(_sqlite_url(target), test_root=root, owner_token=token) == target
    )
    assert not target.exists()


@pytest.mark.parametrize(
    "database_url",
    [
        "postgresql://user:password@localhost/drillloop",
        "sqlite:///:memory:",
        "sqlite:///./drillloop.db",
        "sqlite:///./.pytest-drillloop.db",
    ],
)
def test_rejects_external_or_application_database_targets(tmp_path, database_url):
    root, token = _owned_root(tmp_path)

    with pytest.raises(UnsafeTestDatabaseError):
        validate_test_database_url(database_url, test_root=root, owner_token=token)


def test_rejects_existing_target_even_inside_owned_root(tmp_path):
    root, token = _owned_root(tmp_path)
    target = root / "test-already-present.sqlite3"
    target.write_bytes(b"do not overwrite")

    with pytest.raises(UnsafeTestDatabaseError, match="already exists"):
        validate_test_database_url(_sqlite_url(target), test_root=root, owner_token=token)

    assert target.read_bytes() == b"do not overwrite"


@pytest.mark.parametrize("name", ["drillloop.db", ".pytest-drillloop.db"])
def test_rejects_application_database_names_inside_owned_root(tmp_path, name):
    root, token = _owned_root(tmp_path)

    with pytest.raises(UnsafeTestDatabaseError):
        validate_test_database_url(_sqlite_url(root / name), test_root=root, owner_token=token)


def test_rejects_path_outside_owned_root_and_invalid_owner_token(tmp_path):
    root, token = _owned_root(tmp_path)
    outside = tmp_path / "test-outside.sqlite3"

    with pytest.raises(UnsafeTestDatabaseError, match="directly inside"):
        validate_test_database_url(_sqlite_url(outside), test_root=root, owner_token=token)

    with pytest.raises(UnsafeTestDatabaseError, match="token does not match"):
        validate_test_database_url(
            _sqlite_url(root / "test-wrong-owner.sqlite3"),
            test_root=root,
            owner_token="another-run",
        )
