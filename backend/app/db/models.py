"""DB 모델. SQLite 로 시작하고 PostgreSQL 에서도 그대로 쓰도록 표준 타입(JSON 포함)만 쓴다."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Tank(Base):
    """수조."""

    __tablename__ = "tanks"
    id: Mapped[str] = mapped_column(String(16), primary_key=True)          # A1 … B3
    name: Mapped[str] = mapped_column(String(64))
    noise_condition: Mapped[str] = mapped_column(String(16))               # blocked | operating


class Analysis(Base):
    """녹음 1개의 분석 실행."""

    __tablename__ = "analyses"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tank_id: Mapped[str] = mapped_column(ForeignKey("tanks.id"))
    source: Mapped[str] = mapped_column(String(16))                        # upload | sample
    original_filename: Mapped[str] = mapped_column(String(255))
    file_path: Mapped[str] = mapped_column(Text)
    sample_rate: Mapped[int] = mapped_column(Integer)
    duration_sec: Mapped[float] = mapped_column(Float)
    fed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    feeding_offset_sec: Mapped[float] = mapped_column(Float)
    feed_amount_g: Mapped[float | None] = mapped_column(Float)
    speed: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(16), default="queued")      # queued | running | done | failed
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    progress_sec: Mapped[float | None] = mapped_column(Float)              # 급이 기준 처리 위치
    max_grade: Mapped[str | None] = mapped_column(String(16))
    final_score: Mapped[float | None] = mapped_column(Float)
    metrics: Mapped[dict | None] = mapped_column(JSON)
    comparison: Mapped[list | None] = mapped_column(JSON)
    baseline_info: Mapped[dict | None] = mapped_column(JSON)
    n_clicks: Mapped[int | None] = mapped_column(Integer)
    compute_sec: Mapped[float | None] = mapped_column(Float)

    tank: Mapped[Tank] = relationship()
    minutes: Mapped[list[MinutePoint]] = relationship(order_by="MinutePoint.minute", cascade="all, delete-orphan")
    scores: Mapped[list[ScorePoint]] = relationship(order_by="ScorePoint.minute", cascade="all, delete-orphan")
    alerts: Mapped[list[Alert]] = relationship(order_by="Alert.minute", cascade="all, delete-orphan")
    insight: Mapped[Insight | None] = relationship(cascade="all, delete-orphan", uselist=False)


class MinutePoint(Base):
    """급이 기준 1분 구간의 클릭 수와 정상 범위."""

    __tablename__ = "minute_points"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    analysis_id: Mapped[int] = mapped_column(ForeignKey("analyses.id"), index=True)
    minute: Mapped[int] = mapped_column(Integer)
    cpm: Mapped[int] = mapped_column(Integer)
    mu: Mapped[float | None] = mapped_column(Float)
    lo: Mapped[float | None] = mapped_column(Float)
    hi: Mapped[float | None] = mapped_column(Float)


class ScorePoint(Base):
    """급이 후 매 분 이상 점수."""

    __tablename__ = "score_points"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    analysis_id: Mapped[int] = mapped_column(ForeignKey("analyses.id"), index=True)
    minute: Mapped[int] = mapped_column(Integer)
    score: Mapped[float] = mapped_column(Float)
    grade: Mapped[str] = mapped_column(String(16))
    raw_grade: Mapped[str] = mapped_column(String(16))
    z_auc: Mapped[float] = mapped_column(Float)
    z_peak: Mapped[float] = mapped_column(Float)
    z_onset: Mapped[float] = mapped_column(Float)
    stage: Mapped[str] = mapped_column(String(16))


class Alert(Base):
    """등급 상승(주의·경보) 알림."""

    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    analysis_id: Mapped[int] = mapped_column(ForeignKey("analyses.id"), index=True)
    tank_id: Mapped[str] = mapped_column(ForeignKey("tanks.id"))
    minute: Mapped[int] = mapped_column(Integer)
    level: Mapped[str] = mapped_column(String(16))                         # watch | alert
    score: Mapped[float] = mapped_column(Float)
    stage: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)


class Insight(Base):
    """분석 결과 설명 문장(LLM 또는 템플릿)."""

    __tablename__ = "insights"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    analysis_id: Mapped[int] = mapped_column(ForeignKey("analyses.id"), unique=True)
    source: Mapped[str] = mapped_column(String(16))                        # gemini | template
    model: Mapped[str | None] = mapped_column(String(64))
    content: Mapped[dict] = mapped_column(JSON)                            # summary, bullets, recommendation
    attempts: Mapped[int] = mapped_column(Integer)
    problems: Mapped[list] = mapped_column(JSON)                           # 검증에서 걸린 내용(재생성·대체 사유)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
