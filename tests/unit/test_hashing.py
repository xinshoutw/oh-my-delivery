import pytest
from app.core.hashing import (
    canonical_json,
    compute_event_hash,
    hash_asset_token,
    hash_national_id,
    hash_pin,
    hash_short_code,
)

SECRET = "x" * 32


def test_hash_asset_token_is_deterministic_and_keyed():
    token = "R1A.B7K3M9Q2X8P4ZD6A"
    h1 = hash_asset_token(token, SECRET)
    h2 = hash_asset_token(token, SECRET)
    h_other = hash_asset_token(token, "y" * 32)
    assert h1 == h2
    assert h1 != h_other
    assert len(h1) == 64


def test_hash_short_code_changes_with_input():
    assert hash_short_code("ABC12345") != hash_short_code("ABC12346")


def test_hash_national_id_is_normalized():
    a = hash_national_id(" a123456789 ", SECRET)
    b = hash_national_id("A123456789", SECRET)
    assert a == b


def test_hash_pin_is_deterministic():
    assert hash_pin("123456") == hash_pin("123456")
    assert hash_pin("123456") != hash_pin("123457")


def test_canonical_json_is_stable_across_key_order():
    a = canonical_json({"b": 1, "a": 2})
    b = canonical_json({"a": 2, "b": 1})
    assert a == b


def test_compute_event_hash_chains_previous():
    event = {"event_id": "e1", "type": "AssetCreated"}
    h1 = compute_event_hash(event, previous_event_hash=None)
    h2 = compute_event_hash(event, previous_event_hash=h1)
    h3 = compute_event_hash(event, previous_event_hash=h1)
    assert h1 != h2
    assert h2 == h3


def test_compute_event_hash_detects_payload_tamper():
    event_a = {"event_id": "e1", "type": "AssetCreated"}
    event_b = {"event_id": "e1", "type": "AssetTampered"}
    assert compute_event_hash(event_a, None) != compute_event_hash(event_b, None)


@pytest.mark.parametrize(
    "payload",
    [
        {"x": 1},
        {"x": [1, 2, 3], "nested": {"y": "z"}},
        {"unicode": "餐盒"},
    ],
)
def test_compute_event_hash_handles_varied_payloads(payload):
    h = compute_event_hash(payload, previous_event_hash=None)
    assert isinstance(h, str)
    assert len(h) == 64
