"""FastAPI 진입점. 실행: uvicorn app.main:app --reload (backend 폴더에서)"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    """설정으로 앱 생성(테스트는 별도 설정을 넘긴다)."""
    s = settings or get_settings()
    app = FastAPI(title=s.app_name, version="0.1.0")
    app.add_middleware(CORSMiddleware, allow_origins=s.cors_origins,
                       allow_methods=["GET", "POST", "PATCH", "DELETE"], allow_headers=["Content-Type"])

    @app.get("/health")
    def health():
        """서버 상태."""
        return {"status": "ok"}

    return app


app = create_app()
