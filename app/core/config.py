from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    env: Literal["dev", "test", "prod"] = "dev"
    debug: bool = True

    database_url: str = Field(
        default="postgresql+asyncpg://omd:omd@localhost:5432/omd",
        description="async SQLAlchemy URL",
    )

    server_secret: str = Field(
        ...,
        min_length=32,
        description="HMAC key for asset tokens, national_id hashing, etc.",
    )
    jwt_secret: str = Field(..., min_length=32)
    jwt_algorithm: str = "HS256"
    jwt_access_ttl_minutes: int = 60 * 12

    deposit_base_amount: int = 200
    deposit_step_amount: int = 100
    deposit_max_level: int = 3  # 0..3 → 200/300/400/500
    deposit_due_days: int = 31
    reward_window_days: int = 14
    reward_points_per_return: int = 5
    deposit_reset_no_overdue_days: int = 90

    pin_max_attempts: int = 5
    pin_cooldown_minutes: int = 10
    pin_ttl_minutes: int = 60 * 24

    pickup_session_ttl_seconds: int = 300
    return_session_ttl_seconds: int = 60

    short_code_length: int = 8
    asset_token_random_chars: int = 16
    asset_token_prefix: str = "R1A."


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
