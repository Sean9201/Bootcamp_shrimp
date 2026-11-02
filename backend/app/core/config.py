"""서버 설정. 환경변수(접두어 SHRIMP_) 또는 backend/.env 로 덮어쓴다."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """백엔드 전역 설정."""

    model_config = SettingsConfigDict(env_prefix="SHRIMP_", env_file=".env", extra="ignore")

    app_name: str = "Bootcamp_shrimp API"
    cors_origins: list[str] = ["http://localhost:5500", "http://127.0.0.1:5500"]
    database_url: str = "sqlite:///./data/app.db"


@lru_cache
def get_settings() -> Settings:
    """캐시된 기본 설정."""
    return Settings()
