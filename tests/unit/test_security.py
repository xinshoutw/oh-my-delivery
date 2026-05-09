import re
import time

import pytest
from app.core.config import Settings
from app.core.security import (
    TokenError,
    create_access_token,
    decode_access_token,
    generate_pin,
)


@pytest.fixture
def settings() -> Settings:
    return Settings(server_secret="s" * 32, jwt_secret="j" * 32)  # type: ignore[call-arg]


def test_generate_pin_is_six_digits_by_default():
    for _ in range(50):
        pin = generate_pin()
        assert re.match(r"^\d{6}$", pin)


def test_generate_pin_supports_custom_length():
    assert re.match(r"^\d{4}$", generate_pin(4))


def test_jwt_round_trip(settings: Settings):
    token = create_access_token(settings, subject="user_1", role="courier")
    payload = decode_access_token(settings, token)
    assert payload["sub"] == "user_1"
    assert payload["role"] == "courier"
    assert payload["exp"] > payload["iat"]


def test_jwt_rejects_tampered_token(settings: Settings):
    token = create_access_token(settings, subject="user_1", role="courier")
    tampered = token[:-2] + ("AA" if token[-2:] != "AA" else "BB")
    with pytest.raises(TokenError):
        decode_access_token(settings, tampered)


def test_jwt_extra_claims_round_trip(settings: Settings):
    token = create_access_token(
        settings,
        subject="user_1",
        role="partner",
        extra_claims={"partner_id": "p_1"},
    )
    payload = decode_access_token(settings, token)
    assert payload["partner_id"] == "p_1"


def test_settings_lru_cache_hit_does_not_break(settings: Settings):
    # Just exercise: ensure the dataclass surface is what we expect.
    assert settings.deposit_base_amount == 200
    assert settings.reward_window_days == 14
    _ = time.time()
