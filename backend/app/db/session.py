"""DB 엔진·세션. MVP 는 시작 시 테이블 생성(create_all). 스키마가 굳으면 alembic 으로 옮긴다."""

from __future__ import annotations

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.db.models import Base, Tank

# 설계서 v2 수조 배정
DEFAULT_TANKS = [(f"A{i}", f"수조 A{i}", "blocked") for i in (1, 2, 3)] + \
                [(f"B{i}", f"수조 B{i}", "operating") for i in (1, 2, 3)]


def make_engine(settings: Settings) -> Engine:
    url = settings.db_url
    if url.startswith("sqlite"):
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        eng = create_engine(url, connect_args={"check_same_thread": False})

        @event.listens_for(eng, "connect")
        def _pragma(conn, _):  # 분석 스레드가 쓰는 동안 API 가 읽을 수 있게
            cur = conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()
        return eng
    return create_engine(url, pool_pre_ping=True)


def init_db(engine: Engine) -> sessionmaker[Session]:
    """테이블 생성 + 기본 수조 넣기 → 세션 팩토리."""
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as db:
        if db.query(Tank).count() == 0:
            db.add_all(Tank(id=i, name=n, noise_condition=c) for i, n, c in DEFAULT_TANKS)
            db.commit()
    return factory
