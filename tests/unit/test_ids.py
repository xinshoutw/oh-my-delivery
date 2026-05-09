import re
import uuid

from app.core.ids import (
    CROCKFORD_ALPHABET,
    new_asset_token,
    new_short_code,
    new_uuid7,
    random_crockford,
)

CROCKFORD_RE = re.compile(rf"^[{CROCKFORD_ALPHABET}]+$")


def test_new_uuid7_returns_uuid_version_7():
    value = new_uuid7()
    assert isinstance(value, uuid.UUID)
    assert value.version == 7


def test_uuid7_is_time_ordered():
    samples = [new_uuid7() for _ in range(50)]
    assert samples == sorted(samples)


def test_random_crockford_uses_only_allowed_alphabet():
    code = random_crockford(64)
    assert len(code) == 64
    assert CROCKFORD_RE.match(code) is not None
    forbidden = set("ILOU")
    assert forbidden.isdisjoint(set(code))


def test_new_asset_token_has_prefix_and_correct_random_length():
    token = new_asset_token(prefix="R1A.", random_length=16)
    assert token.startswith("R1A.")
    body = token.removeprefix("R1A.")
    assert len(body) == 16
    assert CROCKFORD_RE.match(body) is not None


def test_short_code_uniqueness_in_sample():
    codes = {new_short_code(8) for _ in range(2000)}
    assert len(codes) > 1990
