"""서버 설정. 환경변수(접두어 SHRIMP_) 또는 backend/.env 로 덮어쓴다."""

from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """백엔드 전역 설정."""

    model_config = SettingsConfigDict(env_prefix="SHRIMP_", env_file=".env", extra="ignore")

    app_name: str = "Bootcamp_shrimp API"
    cors_origins: list[str] = ["http://localhost:5500", "http://127.0.0.1:5500"]
    data_dir: Path = Path("./data")                       # DB·업로드 파일 (git 제외)
    database_url: str | None = None                       # 비우면 data_dir/app.db (SQLite)

    # 분석 엔진(ai 패키지) 산출물·시연 샘플
    ai_artifacts_dir: Path = Path("../ai/artifacts")
    samples_dir: Path = Path("../data_pipeline/data/synthetic/mock_v1")
    sample_split: str = "demo"                            # 이 split 의 세션만 샘플로 노출

    # 분석 실행
    default_speed: float = 40.0                           # 시연 배속(0 = 최대 속도)
    max_speed: float = 400.0
    default_feeding_offset_sec: float = 600.0             # 녹음 시작 10분 뒤 급이
    max_upload_mb: int = 600
    analysis_workers: int = 2
    event_poll_sec: float = 0.05                          # SSE 가 새 이벤트를 확인하는 간격

    # 인사이트(LLM). 키가 없으면 템플릿 문장
    gemini_api_key: SecretStr | None = None
    gemini_model: str = "gemini-2.5-flash"
    llm_timeout_sec: float = 20.0
    llm_temperature: float = 0.3
    insight_max_retries: int = 1                          # 검증 실패 시 다시 생성하는 횟수

    @property
    def db_url(self) -> str:
        return self.database_url or f"sqlite:///{(self.data_dir / 'app.db').as_posix()}"

    @property
    def upload_dir(self) -> Path:
        return self.data_dir / "uploads"


@lru_cache
def get_settings() -> Settings:
    """캐시된 기본 설정."""
    return Settings()
