"""Identifier generators: UUIDv7, Crockford Base32 asset tokens, short codes."""

from __future__ import annotations

import secrets
import uuid

import uuid_utils

CROCKFORD_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_CROCKFORD_LEN = len(CROCKFORD_ALPHABET)


def new_uuid7() -> uuid.UUID:
    return uuid.UUID(str(uuid_utils.uuid7()))


def random_crockford(length: int) -> str:
    return "".join(CROCKFORD_ALPHABET[secrets.randbelow(_CROCKFORD_LEN)] for _ in range(length))


def new_asset_token(prefix: str, random_length: int) -> str:
    return f"{prefix}{random_crockford(random_length)}"


def new_short_code(length: int) -> str:
    return random_crockford(length)
