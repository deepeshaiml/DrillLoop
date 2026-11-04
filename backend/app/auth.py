from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass
from getpass import getpass
from pathlib import Path

from fastapi import Depends, HTTPException, Request

SESSION_COOKIE = "drillloop_session"
SESSION_MAX_AGE = 8 * 60 * 60
ALLOWED_ROLES = {"admin", "evaluator", "reviewer", "viewer"}
PASSWORD_SCRYPT_N = 1 << 15


class AuthConfigurationError(ValueError):
    """Raised when named-user or session configuration is missing or invalid."""


@dataclass(frozen=True)
class Identity:
    user_id: str
    username: str
    name: str
    role: str
    organization_id: str
    csrf_token: str

    def public_dict(self) -> dict[str, str]:
        return {
            "id": self.user_id,
            "username": self.username,
            "name": self.name,
            "role": self.role,
            "organization_id": self.organization_id,
        }


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def hash_password(password: str) -> str:
    if len(password) < 12:
        raise ValueError("Password must contain at least 12 characters")
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=PASSWORD_SCRYPT_N,
        r=8,
        p=1,
        maxmem=64 * 1024 * 1024,
        dklen=32,
    )
    return f"scrypt${PASSWORD_SCRYPT_N}$8$1${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, n_text, r_text, p_text, salt_text, expected_text = encoded.split("$", 5)
        if algorithm != "scrypt":
            return False
        n, r, p = int(n_text), int(r_text), int(p_text)
        if n != PASSWORD_SCRYPT_N or r != 8 or p != 1:
            return False
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=_unb64(salt_text),
            n=n,
            r=r,
            p=p,
            maxmem=64 * 1024 * 1024,
            dklen=32,
        )
        return hmac.compare_digest(actual, _unb64(expected_text))
    except (ValueError, TypeError, OverflowError):
        return False


def configured_users() -> dict[str, dict[str, str]]:
    users_file = os.getenv("DRILLLOOP_USERS_FILE", "")
    if users_file:
        path = Path(users_file)
        if path.is_symlink() or not path.is_file():
            raise AuthConfigurationError(
                "DRILLLOOP_USERS_FILE must point to a regular configuration file"
            )
        try:
            raw = path.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise AuthConfigurationError("DRILLLOOP_USERS_FILE cannot be read") from exc
    else:
        raw = os.getenv("DRILLLOOP_USERS_JSON", "").strip()
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AuthConfigurationError("DRILLLOOP_USERS_JSON must be valid JSON") from exc
    if not isinstance(payload, list):
        raise AuthConfigurationError("DRILLLOOP_USERS_JSON must be a JSON array")
    result: dict[str, dict[str, str]] = {}
    usernames: set[str] = set()
    for user in payload:
        required = ("id", "username", "name", "role", "organization_id", "password_hash")
        if not isinstance(user, dict) or any(
            not isinstance(user.get(key), str) for key in required
        ):
            raise AuthConfigurationError(
                "Each configured user needs id, username, name, role, organization_id, and password_hash"
            )
        if user["role"] not in ALLOWED_ROLES:
            raise AuthConfigurationError(f"Unsupported role for user {user['username']!r}")
        username = user["username"].casefold()
        if username in usernames:
            raise AuthConfigurationError("Configured usernames must be unique")
        if (
            not user["id"].strip()
            or not user["organization_id"].strip()
            or not user["name"].strip()
        ):
            raise AuthConfigurationError(
                "Configured user IDs, names, and organization IDs cannot be empty"
            )
        if not user["password_hash"].startswith("scrypt$"):
            raise AuthConfigurationError(
                f"User {user['username']!r} has an unsupported password hash"
            )
        usernames.add(username)
        result[user["id"]] = {**user, "username": username}
    return result


def session_secret() -> bytes | None:
    secret_file = os.getenv("DRILLLOOP_SESSION_SECRET_FILE", "")
    if secret_file:
        path = Path(secret_file)
        if path.is_symlink() or not path.is_file():
            return None
        try:
            value = path.read_text(encoding="utf-8").strip()
        except OSError:
            return None
    else:
        value = os.getenv("DRILLLOOP_SESSION_SECRET", "")
    if len(value.encode("utf-8")) < 32:
        return None
    return value.encode("utf-8")


def _user_by_username(username: str) -> dict[str, str] | None:
    folded = username.casefold()
    return next((user for user in configured_users().values() if user["username"] == folded), None)


def authenticate(username: str, password: str) -> dict[str, str] | None:
    user = _user_by_username(username)
    if user is None:
        # Do a bounded scrypt operation for unknown names to reduce username timing differences.
        verify_password(password, _DUMMY_PASSWORD_HASH)
        return None
    return user if verify_password(password, user["password_hash"]) else None


_DUMMY_PASSWORD_HASH = hash_password("dummy-password-not-for-login")


def create_session(user: dict[str, str]) -> tuple[str, Identity]:
    secret = session_secret()
    if secret is None:
        raise AuthConfigurationError(
            "Set DRILLLOOP_SESSION_SECRET to at least 32 characters before enabling sign-in"
        )
    csrf_token = secrets.token_urlsafe(32)
    claims = {
        "sub": user["id"],
        "exp": int(time.time()) + SESSION_MAX_AGE,
        "csrf": csrf_token,
    }
    body = _b64(json.dumps(claims, separators=(",", ":")).encode("utf-8"))
    signature = _b64(hmac.new(secret, body.encode("ascii"), hashlib.sha256).digest())
    token = f"{body}.{signature}"
    identity = Identity(
        user_id=user["id"],
        username=user["username"],
        name=user["name"],
        role=user["role"],
        organization_id=user["organization_id"],
        csrf_token=csrf_token,
    )
    return token, identity


def resolve_session(token: str | None) -> Identity | None:
    secret = session_secret()
    if not token or secret is None:
        return None
    try:
        body, signature = token.split(".", 1)
        expected = _b64(hmac.new(secret, body.encode("ascii"), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            return None
        claims = json.loads(_unb64(body))
        if not isinstance(claims, dict) or int(claims.get("exp", 0)) <= int(time.time()):
            return None
        user = configured_users().get(claims.get("sub"))
        csrf_token = claims.get("csrf")
        if not user or not isinstance(csrf_token, str) or len(csrf_token) < 32:
            return None
        return Identity(
            user_id=user["id"],
            username=user["username"],
            name=user["name"],
            role=user["role"],
            organization_id=user["organization_id"],
            csrf_token=csrf_token,
        )
    except (ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def current_identity(request: Request) -> Identity:
    try:
        users = configured_users()
        secret = session_secret()
    except AuthConfigurationError as exc:
        raise HTTPException(
            status_code=503, detail={"code": "AUTH_CONFIGURATION_INVALID", "message": str(exc)}
        ) from exc
    if not users or secret is None:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "AUTH_NOT_CONFIGURED",
                "message": "Named-user authentication is not configured.",
            },
        )
    identity = resolve_session(request.cookies.get(SESSION_COOKIE))
    if identity is None:
        raise HTTPException(
            status_code=401,
            detail={"code": "AUTHENTICATION_REQUIRED", "message": "Sign in is required."},
        )
    return identity


def require_roles(*roles: str):
    def dependency(identity: Identity = Depends(current_identity)) -> Identity:
        if identity.role not in roles:
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "ROLE_FORBIDDEN",
                    "message": "Your account role cannot perform this action.",
                },
            )
        return identity

    return dependency


def cookie_secure() -> bool:
    return os.getenv("DRILLLOOP_COOKIE_SECURE", "1").casefold() not in {"0", "false", "no"}


def _hash_password_cli() -> None:
    parser = argparse.ArgumentParser(
        description="Create a DrillLoop scrypt password hash for server configuration."
    )
    parser.add_argument("command", choices=["hash-password"])
    parser.parse_args()
    print(hash_password(getpass("Password (12+ characters): ")))


if __name__ == "__main__":
    _hash_password_cli()
