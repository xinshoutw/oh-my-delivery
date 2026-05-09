"""JWT, PIN generation, and password hashing."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from jose import JWTError, jwt

from app.core.config import Settings
from app.core.hashing import hash_pin


class TokenError(Exception):
    pass


def utcnow() -> datetime:
    return datetime.now(UTC)


def create_access_token(
    settings: Settings,
    subject: str,
    role: str,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    now = utcnow()
    payload: dict[str, Any] = {
        "sub": subject,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.jwt_access_ttl_minutes)).timestamp()),
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(settings: Settings, token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError as err:
        raise TokenError(str(err)) from err


def generate_pin(digits: int = 6) -> str:
    upper = 10**digits
    return f"{secrets.randbelow(upper):0{digits}d}"


def hash_pin_for_storage(pin: str) -> str:
    return hash_pin(pin)
