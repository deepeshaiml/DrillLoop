#!/usr/bin/env python3
"""Non-destructive database backup, archive verification, and restore to a new target."""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import sqlite3
import stat
import subprocess
from pathlib import Path

from sqlalchemy.engine import make_url


def _database_url(value: str | None = None):
    value = value or os.getenv("DATABASE_URL", "")
    if not value:
        raise SystemExit("Set DATABASE_URL to the intended database target.")
    try:
        return make_url(value)
    except Exception as exc:
        raise SystemExit("DATABASE_URL is invalid.") from exc


def _identity(url) -> str:
    if url.get_backend_name() == "sqlite":
        if not url.database:
            raise SystemExit("SQLite backup requires an on-disk database file.")
        return Path(url.database).name
    if url.get_backend_name() == "postgresql" and url.database:
        return url.database
    raise SystemExit("Only PostgreSQL and on-disk SQLite databases are supported.")


def _confirm(actual: str, supplied: str) -> None:
    if actual != supplied:
        raise SystemExit(f"Target confirmation mismatch: expected exact target name {actual!r}.")


def _secure_new_output(path_value: str) -> Path:
    path = Path(path_value).expanduser()
    path = path.absolute()
    parent = path.parent
    if parent.is_symlink() or not parent.is_dir():
        raise SystemExit("Backup directory must already exist and may not be a symlink.")
    mode = stat.S_IMODE(parent.stat().st_mode)
    if os.name == "posix" and mode & 0o077:
        raise SystemExit("Backup directory must be private (mode 0700 or stricter).")
    if path.exists() or path.is_symlink():
        raise SystemExit("Backup target already exists; refusing to overwrite it.")
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    descriptor = os.open(path, flags, 0o600)
    os.close(descriptor)
    return path


def _sqlite_check(path: Path) -> bool:
    uri = f"file:{path.resolve()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        result = connection.execute("PRAGMA integrity_check").fetchone()[0]
        if result != "ok":
            raise SystemExit(
                "SQLite integrity check failed; preserve the backup for investigation."
            )
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        return "alembic_version" in tables


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _pg_env(url) -> dict[str, str]:
    env = os.environ.copy()
    password = url.password
    if not password and os.getenv("DATABASE_PASSWORD_FILE"):
        secret = Path(os.environ["DATABASE_PASSWORD_FILE"])
        if secret.is_symlink() or not secret.is_file():
            raise SystemExit("DATABASE_PASSWORD_FILE must point to a regular secret file.")
        password = secret.read_text(encoding="utf-8").rstrip("\r\n")
    if password:
        env["PGPASSWORD"] = password
    return env


def _pg_uri(url) -> str:
    return url.set(drivername="postgresql", password=None).render_as_string(hide_password=True)


def backup(target: str, confirm_target: str, output: str) -> Path:
    url = _database_url(target)
    _confirm(_identity(url), confirm_target)
    path = _secure_new_output(output)
    if url.get_backend_name() == "sqlite":
        source = Path(url.database)
        if source.is_symlink() or not source.is_file():
            raise SystemExit("SQLite source must be an existing regular database file.")
        _sqlite_check(source)  # Legacy, unversioned databases can still be protected by backup.
        with sqlite3.connect(f"file:{source.resolve()}?mode=ro", uri=True) as source_db:
            with sqlite3.connect(path) as backup_db:
                source_db.backup(backup_db)
        path.chmod(0o600)
        _sqlite_check(path)
    else:
        executable = shutil.which("pg_dump")
        if not executable:
            raise SystemExit("pg_dump is required for PostgreSQL backups.")
        result = subprocess.run(
            [
                executable,
                "--format=custom",
                "--no-owner",
                "--no-acl",
                "--file",
                str(path),
                "--dbname",
                _pg_uri(url),
            ],
            env=_pg_env(url),
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode:
            raise SystemExit(
                f"pg_dump failed with exit code {result.returncode}; backup file was retained."
            )
        verify(path)
    return path


def verify(path_value: str | Path) -> None:
    path = Path(path_value)
    if path.is_symlink() or not path.is_file():
        raise SystemExit("Backup must be an existing regular file.")
    if path.suffix.casefold() in {".sqlite", ".sqlite3", ".db"}:
        _sqlite_check(path)
        return
    executable = shutil.which("pg_restore")
    if not executable:
        raise SystemExit("pg_restore is required to verify PostgreSQL custom archives.")
    result = subprocess.run(
        [executable, "--list", str(path)], capture_output=True, text=True, check=False
    )
    if result.returncode or not result.stdout.strip():
        raise SystemExit("PostgreSQL archive integrity check failed.")


def restore(backup_path: str, target: str, confirm_target: str) -> str:
    archive = Path(backup_path)
    verify(archive)
    url = _database_url(target)
    actual = _identity(url)
    _confirm(actual, confirm_target)
    if url.get_backend_name() == "sqlite":
        target_path = Path(url.database)
        if not target_path.is_absolute() or target_path.is_symlink():
            raise SystemExit("SQLite restore target must be a new absolute path.")
        if target_path.exists():
            raise SystemExit("SQLite restore target already exists; refusing to overwrite it.")
        _secure_new_output(str(target_path))
        try:
            shutil.copyfile(archive, target_path)
            target_path.chmod(0o600)
            _sqlite_check(target_path)
        except Exception:
            raise SystemExit(
                f"Restore verification failed; preserve the new target for review: {target_path}"
            )
        return str(target_path)

    if archive.suffix.casefold() in {".sqlite", ".sqlite3", ".db"}:
        raise SystemExit(
            "SQLite backups can only restore to SQLite; use a PostgreSQL dump for PostgreSQL."
        )
    admin_value = os.getenv("DRILLLOOP_PG_ADMIN_URL", "")
    if not admin_value:
        raise SystemExit(
            "Set DRILLLOOP_PG_ADMIN_URL to a maintenance database for a new-target restore."
        )
    admin_url = make_url(admin_value)
    if admin_url.get_backend_name() != "postgresql":
        raise SystemExit("DRILLLOOP_PG_ADMIN_URL must be a PostgreSQL connection URL.")
    if not actual.replace("_", "").isalnum():
        raise SystemExit(
            "PostgreSQL restore target names may contain only letters, digits, and underscores."
        )
    try:
        import psycopg

        kwargs = {}
        if admin_url.password:
            kwargs["password"] = admin_url.password
        elif os.getenv("DATABASE_PASSWORD_FILE"):
            kwargs["password"] = (
                Path(os.environ["DATABASE_PASSWORD_FILE"]).read_text().rstrip("\r\n")
            )
        with psycopg.connect(_pg_uri(admin_url), **kwargs) as connection:
            exists = connection.execute(
                "SELECT 1 FROM pg_database WHERE datname = %s", (actual,)
            ).fetchone()
            if exists:
                raise SystemExit("PostgreSQL restore target already exists; refusing to modify it.")
    except SystemExit:
        raise
    except Exception as exc:
        raise SystemExit("Could not safely check the new PostgreSQL restore target.") from exc
    env = _pg_env(admin_url)
    create_db = shutil.which("createdb")
    pg_restore = shutil.which("pg_restore")
    if not create_db or not pg_restore:
        raise SystemExit("createdb and pg_restore are required for PostgreSQL restore.")
    owner = admin_url.username
    command_args = [create_db, "--maintenance-db", _pg_uri(admin_url)]
    if owner:
        command_args.extend(["--owner", owner])
    command_args.append(actual)
    created = subprocess.run(command_args, env=env, capture_output=True, text=True, check=False)
    if created.returncode:
        raise SystemExit(
            "Could not create the new PostgreSQL restore database; no existing database was changed."
        )
    target_url = url.set(drivername="postgresql", password=None)
    loaded = subprocess.run(
        [
            pg_restore,
            "--exit-on-error",
            "--no-owner",
            "--no-acl",
            "--dbname",
            _pg_uri(target_url),
            str(archive),
        ],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if loaded.returncode:
        raise SystemExit(
            f"Restore failed into new database {actual!r}; preserve it as an incomplete restore for review."
        )
    return actual


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    backup_parser = subparsers.add_parser("backup")
    backup_parser.add_argument("--confirm-target", required=True)
    backup_parser.add_argument("--output", required=True)
    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("--backup", required=True)
    restore_parser = subparsers.add_parser("restore")
    restore_parser.add_argument("--backup", required=True)
    restore_parser.add_argument("--target-url", required=True)
    restore_parser.add_argument("--confirm-target", required=True)
    args = parser.parse_args()

    if args.command == "backup":
        result = backup(os.getenv("DATABASE_URL", ""), args.confirm_target, args.output)
        print(f"Backup created and integrity-checked: {result} sha256={_sha256(result)}")
    elif args.command == "verify":
        verify(args.backup)
        print("Backup integrity check passed.")
    else:
        result = restore(args.backup, args.target_url, args.confirm_target)
        print(f"Restore completed into new database target: {result}")


if __name__ == "__main__":
    main()
