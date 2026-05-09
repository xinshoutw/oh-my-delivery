"""Hashing utilities: HMAC token hash, short_code hash, hash chain over canonical events."""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any


def hmac_sha256_hex(value: str, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), value.encode("utf-8"), hashlib.sha256).hexdigest()


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def hash_asset_token(token: str, secret: str) -> str:
    return hmac_sha256_hex(token, secret)


def hash_short_code(short_code: str) -> str:
    return sha256_hex(short_code)


def hash_national_id(national_id: str, secret: str) -> str:
    normalized = national_id.strip().upper()
    return hmac_sha256_hex(normalized, secret)


def hash_pin(pin: str) -> str:
    return sha256_hex(pin)


def canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def compute_event_hash(canonical_event: dict[str, Any], previous_event_hash: str | None) -> str:
    body = canonical_json(canonical_event)
    chain = f"{body}|{previous_event_hash or ''}"
    return sha256_hex(chain)
