"""세션 메타(meta.json) 형식과 검증. 형식 정의는 docs/interfaces.md 1절을 따른다."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

DATA_SOURCES = ("real", "synthetic")
LABELS = ("normal", "abnormal", "unknown", None)
NOISE_CONDITIONS = ("blocked", "operating")


@dataclass
class SessionMeta:
    """세션 1개(녹음 1개)의 메타데이터."""

    session_id: str
    tank: str
    noise_condition: str                # blocked(소음 차단) | operating(운영 소음)
    fed_at: str                         # ISO8601, 시간대 포함 (+09:00)
    feeding_offset_sec: float           # 녹음 시작 기준 급이 시각(초)
    day: int | None = None              # 측정 일차
    recorded_at: str | None = None
    feed_amount_g: float | None = None
    feeding_duration_sec: float | None = None
    data_source: str = "real"
    label: str | None = None
    water: dict | None = None           # {"start": {...}, "end": {...}}
    events: list[dict] = field(default_factory=list)   # [{"time_sec", "note"}], WAV 시작 기준
    residual_feed: dict | None = None   # {"recovered", "dry_mass_g", "reason"}
    synthetic: dict | None = None       # 합성 세션일 때 생성 조건(정답 곡선 파라미터 등)
    notes: str = ""

    def validate(self) -> list[str]:
        """형식 문제 목록(비어 있으면 정상)."""
        p: list[str] = []
        if not self.session_id:
            p.append("session_id 가 비어 있음")
        if not self.tank:
            p.append("tank 가 비어 있음")
        if self.noise_condition not in NOISE_CONDITIONS:
            p.append(f"noise_condition 은 {NOISE_CONDITIONS} 중 하나")
        for name in ("fed_at", "recorded_at"):
            v = getattr(self, name)
            if v is None:
                continue
            try:
                if datetime.fromisoformat(v).tzinfo is None:
                    p.append(f"{name} 에 시간대가 없음 (예: +09:00)")
            except ValueError:
                p.append(f"{name} 가 ISO8601 형식이 아님: {v}")
        if self.feeding_offset_sec is None or self.feeding_offset_sec < 0:
            p.append("feeding_offset_sec 는 0 이상이어야 함")
        if self.data_source not in DATA_SOURCES:
            p.append(f"data_source 는 {DATA_SOURCES} 중 하나")
        if self.label not in LABELS:
            p.append(f"label 은 {LABELS} 중 하나")
        if self.residual_feed and self.residual_feed.get("recovered") is False \
                and self.residual_feed.get("dry_mass_g") is not None:
            p.append("잔여 사료 회수 실패인데 dry_mass_g 가 있음 (null 로 둘 것)")
        return p

    def to_json(self) -> str:
        """meta.json 문자열."""
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)


def load_session(session_dir: str | Path) -> tuple[SessionMeta, list[str]]:
    """세션 폴더(audio.wav + meta.json) 읽기 → (메타, 문제 목록)."""
    d = Path(session_dir)
    problems: list[str] = []
    if not (d / "audio.wav").is_file():
        problems.append("audio.wav 없음")
    raw = json.loads((d / "meta.json").read_text(encoding="utf-8"))
    meta = SessionMeta(**{k: v for k, v in raw.items() if k in SessionMeta.__dataclass_fields__})
    return meta, problems + meta.validate()
