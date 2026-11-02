"""FastAPI 진입점. 실행: uvicorn app.main:app (backend 폴더에서)"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import router as v1
from app.core import errors
from app.core.config import Settings, get_settings
from app.db.session import init_db, make_engine
from app.services.ai_resources import AIResources
from app.services.events import EventBus
from app.services.runner import Runner


def create_app(settings: Settings | None = None) -> FastAPI:
    """설정으로 앱 생성(테스트는 별도 설정을 넘긴다)."""
    s = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        engine = make_engine(s)
        app.state.settings = s
        app.state.sessions = init_db(engine)
        app.state.ai = AIResources(s.ai_artifacts_dir)
        app.state.bus = EventBus()
        app.state.runner = Runner(s, app.state.sessions, app.state.ai, app.state.bus)
        yield
        app.state.runner.shutdown()
        engine.dispose()

    app = FastAPI(title=s.app_name, version="0.2.0", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=s.cors_origins,
                       allow_methods=["GET", "POST", "PATCH", "DELETE"], allow_headers=["Content-Type"])
    errors.install(app)
    app.include_router(v1)

    @app.get("/health")
    def health(request: Request):
        """서버 상태 + 분석 엔진·LLM 준비 여부."""
        st = request.app.state
        return {"status": "ok", "ai": st.ai.status(),
                "llm": {"provider": "gemini", "configured": s.gemini_api_key is not None, "model": s.gemini_model}}

    return app


app = create_app()
