"""Settings from environment variables. Secrets are never hard-coded (CLAUDE.md)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


@dataclass(frozen=True)
class Settings:
    database_url: str = field(default_factory=lambda: _env("DATABASE_URL", "postgresql://postgres@localhost:54322/rahbar"))
    anthropic_api_key: str = field(default_factory=lambda: _env("ANTHROPIC_API_KEY"))
    model_fast: str = field(default_factory=lambda: _env("MODEL_FAST", "claude-haiku-5-5"))
    model_standard: str = field(default_factory=lambda: _env("MODEL_STANDARD", "claude-sonnet-5-5"))
    model_deep: str = field(default_factory=lambda: _env("MODEL_DEEP", "claude-opus-5-5"))
    llm_mode: str = field(default_factory=lambda: _env("LLM_MODE", "auto"))  # auto|anthropic|offline
    firecrawl_api_key: str = field(default_factory=lambda: _env("FIRECRAWL_API_KEY"))
    apify_token: str = field(default_factory=lambda: _env("APIFY_TOKEN"))
    crawl_provider: str = field(default_factory=lambda: _env("CRAWL_PROVIDER", "auto"))  # auto|live|fixture
    flight_provider: str = field(default_factory=lambda: _env("FLIGHT_PROVIDER", "sandbox"))
    hotel_provider: str = field(default_factory=lambda: _env("HOTEL_PROVIDER", "sandbox"))
    payment_provider: str = field(default_factory=lambda: _env("PAYMENT_PROVIDER", "manual"))
    docs_encryption_key: str = field(default_factory=lambda: _env("DOCS_ENCRYPTION_KEY"))
    fresh_days_fees: int = 7
    fresh_days_general: int = 30
    quote_valid_hours: int = 72
    user_agent: str = "RahbarBot/0.1 (+https://rahbar.example/bot; official-source verification)"

    @property
    def use_anthropic(self) -> bool:
        if self.llm_mode == "offline":
            return False
        if self.llm_mode == "anthropic":
            return True
        return bool(self.anthropic_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
