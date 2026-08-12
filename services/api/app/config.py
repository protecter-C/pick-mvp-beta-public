from functools import lru_cache
from urllib.parse import urlparse
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "PICK API"
    database_url: str = "postgresql+psycopg://pick:pick@localhost:5432/pick"
    redis_url: str = "redis://localhost:6379/0"
    auth_secret: str = "local-development-secret"
    token_ttl_seconds: int = 60 * 60 * 24 * 30
    environment: str = "production"
    serpapi_key: str | None = None
    provider_timeout_seconds: float = 3.0
    provider_retries: int = 2
    provider_cache_ttl_seconds: int = 300
    provider_location: str = "Austin, Texas, United States"
    provider_location_ko: str = "Seoul, South Korea"
    provider_language: str = "en"
    provider_country: str = "us"
    affiliate_webhook_secret: str = "local-affiliate-secret"
    affiliate_reward_bps: int = 1000
    affiliate_max_reward_points: int = 1000
    affiliate_click_ttl_days: int = 30
    price_tracking_interval_seconds: int = 900
    admin_api_key: str = "local-admin-key"
    analytics_retention_days: int = 90
    analytics_export_path: str = ""

    @property
    def auto_create_schema(self) -> bool:
        return self.environment.lower() in {"development", "test"}

    @property
    def allows_mock_providers(self) -> bool:
        """Mocks are a local/test convenience and are never production data."""
        return self.environment.lower() in {"development", "test"}

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()


def validate_runtime_settings(settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    if settings.environment.lower() in {"development", "test"}:
        return
    problems = []
    if not settings.database_url.startswith("postgresql"):
        problems.append("DATABASE_URL must use PostgreSQL outside development/test")
    if settings.auth_secret == "local-development-secret":
        problems.append("AUTH_SECRET must be set outside development/test")
    if settings.affiliate_webhook_secret == "local-affiliate-secret":
        problems.append("AFFILIATE_WEBHOOK_SECRET must be set outside development/test")
    if urlparse(settings.database_url).hostname is None:
        problems.append("DATABASE_URL must include a database host")
    if settings.admin_api_key == "local-admin-key":
        problems.append("ADMIN_API_KEY must be set outside development/test")
    if not 7 <= settings.analytics_retention_days <= 3650:
        problems.append("ANALYTICS_RETENTION_DAYS must be between 7 and 3650")
    if problems:
        raise RuntimeError("Invalid runtime configuration: " + "; ".join(problems))
