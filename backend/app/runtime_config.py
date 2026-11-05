from __future__ import annotations

import os
import stat
from pathlib import Path

from sqlalchemy.engine import make_url

from app.auth import AuthConfigurationError, configured_users, cookie_secure, session_secret
from app.db import DATABASE_URL


def comma_separated(name: str, default: tuple[str, ...] = ()) -> list[str]:
    value = os.getenv(name)
    if value is None:
        return list(default)
    return [item.strip() for item in value.split(",") if item.strip()]


def validate_runtime_config() -> None:
    environment = os.getenv("DRILLLOOP_ENVIRONMENT", "local").casefold()
    if environment not in {"local", "test", "staging", "production"}:
        raise RuntimeError("DRILLLOOP_ENVIRONMENT must be local, test, staging, or production.")
    try:
        timeout = float(os.getenv("DRILLLOOP_PARSER_TIMEOUT_SECONDS", "15"))
        queue_timeout = float(os.getenv("DRILLLOOP_PARSER_QUEUE_TIMEOUT_SECONDS", "30"))
        scanner_timeout = float(os.getenv("DRILLLOOP_SCANNER_TIMEOUT_SECONDS", "5"))
        scanner_max_signature_age = float(
            os.getenv("DRILLLOOP_SCANNER_MAX_SIGNATURE_AGE_HOURS", "72")
        )
        scanner_port = int(os.getenv("DRILLLOOP_SCANNER_PORT", "3310"))
        memory_mb = int(os.getenv("DRILLLOOP_PARSER_MEMORY_MB", "768"))
    except ValueError as exc:
        raise RuntimeError(
            "Parser/scanner timeout, signature age, port, and memory settings must be numeric."
        ) from exc
    if not 1 <= timeout <= 60 or not 256 <= memory_mb <= 768:
        raise RuntimeError("Parser timeout must be 1–60 seconds and memory limit 256–768 MB.")
    if not 1 <= queue_timeout <= 120:
        raise RuntimeError("Parser queue timeout must be between 1 and 120 seconds.")
    if not 1 <= scanner_timeout <= 30:
        raise RuntimeError("Scanner timeout must be between 1 and 30 seconds.")
    if not 1 <= scanner_port <= 65535:
        raise RuntimeError("Scanner port must be between 1 and 65535.")
    if not 1 <= scanner_max_signature_age <= 24 * 14:
        raise RuntimeError("Scanner signature age must be between 1 and 336 hours.")
    quarantine_root = os.getenv("DRILLLOOP_QUARANTINE_DIR")
    if quarantine_root:
        quarantine = Path(quarantine_root)
        if quarantine.is_symlink() or not quarantine.is_dir():
            raise RuntimeError("DRILLLOOP_QUARANTINE_DIR must name an existing private directory.")
        metadata = quarantine.stat()
        if metadata.st_uid != os.geteuid() or stat.S_IMODE(metadata.st_mode) & 0o077:
            raise RuntimeError(
                "DRILLLOOP_QUARANTINE_DIR must be owned by the application user and mode 0700 or stricter."
            )

    if environment not in {"staging", "production"}:
        return
    if make_url(DATABASE_URL).get_backend_name() != "postgresql":
        raise RuntimeError(
            f"{environment.title()} requires PostgreSQL; SQLite is not supported in this environment."
        )
    if not os.getenv("DATABASE_PASSWORD_FILE"):
        raise RuntimeError(f"{environment.title()} requires file-injected database credentials.")
    if session_secret() is None or not os.getenv("DRILLLOOP_SESSION_SECRET_FILE"):
        raise RuntimeError(
            f"{environment.title()} requires a file-injected session secret of at least 32 bytes."
        )
    try:
        if not configured_users() or not os.getenv("DRILLLOOP_USERS_FILE"):
            raise RuntimeError(f"{environment.title()} requires configured named accounts.")
    except AuthConfigurationError as exc:
        raise RuntimeError(f"{environment.title()} named-user configuration is invalid.") from exc
    if not cookie_secure():
        raise RuntimeError(f"{environment.title()} requires Secure session cookies behind HTTPS.")
    if os.getenv("DRILLLOOP_UPLOAD_SCAN_MODE", "disabled").casefold() != "required":
        raise RuntimeError(f"{environment.title()} requires DRILLLOOP_UPLOAD_SCAN_MODE=required.")
    scanner_host = os.getenv("DRILLLOOP_SCANNER_HOST", "").strip()
    if not scanner_host or any(character.isspace() for character in scanner_host):
        raise RuntimeError(
            f"{environment.title()} requires a configured private ClamAV scanner host."
        )
    if not comma_separated("DRILLLOOP_TRUSTED_HOSTS"):
        raise RuntimeError(f"{environment.title()} requires an explicit trusted-host allowlist.")
    seed_enabled = any(
        os.getenv(name, "0").casefold() in {"1", "true", "yes"}
        for name in ("DEMO_SEED", "DRILLLOOP_ENABLE_DEMO_SEED")
    )
    if seed_enabled:
        raise RuntimeError(f"Synthetic demo seeding must be disabled in {environment}.")
