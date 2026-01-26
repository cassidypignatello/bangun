"""
Application configuration using Pydantic Settings v2
Environment variables loaded from .env file
"""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with validation and environment variable loading"""

    # Core
    env: Literal["development", "staging", "production"] = "development"
    debug: bool = False

    # Database
    supabase_url: str
    supabase_service_key: str

    # AI
    openai_api_key: str

    # Scraping
    apify_token: str

    # Payment
    midtrans_server_key: str
    midtrans_client_key: str

    # Security
    field_encryption_key: str

    # Affiliate Marketing
    tokopedia_affiliate_id: str | None = None  # Set in production for affiliate tracking

    # Observability
    sentry_dsn: str | None = None

    # API Configuration
    api_title: str = "Bangun API"
    api_version: str = "0.1.0"
    api_description: str = "AI-powered construction cost estimation for Indonesia"

    # Rate Limiting
    rate_limit_per_minute: int = 60
    rate_limit_per_hour: int = 1000

    # CORS
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    # Background Jobs
    enable_background_jobs: bool = False  # Set to True in production

    # Development/Testing Options
    use_mock_prices: bool = False  # Set to True to skip Apify and use mock price data

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )


@lru_cache
def get_settings() -> Settings:
    """
    Cached settings instance - created once per application lifecycle

    Returns:
        Settings: Application configuration instance
    """
    return Settings()
