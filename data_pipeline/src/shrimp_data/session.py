"""세션 메타(meta.json) 형식과 검증. 형식 정의는 docs/interfaces.md 1절을 따른다."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

DATA_SOURCES = ("real", "synthetic")
LABELS = ("normal", "abnormal", "unknown", None)


@dataclass
class SessionMeta:
    """세션 1개(녹음 1개)의 메타데이터."""

    session_id: str
    tank: str
    fed_at: str                         # ISO8601, 시간대 포함 (+09:00)
    feeding_offset_sec: float           # 녹음 시작 기준 급이 시각(초)
    recorded_at: str | None = None
    feed_amount_g: float | None = None
    data_source: str = "real"
    label: str | None = None
    notes: str = ""
    problems: list[str] = field(default_factory=list, repr=False)

    def validate(self) -> list[str]:
        """형식 문제 목록(비어 있으면 정상)."""
        p: list[str] = []
        if not self.session_id:
            p.append("session_id 가 비어 있음")
        if not self.tank:
            p.append("tank 가 비어 있음")
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
        return p


def load_session(session_dir: str | Path) -> tuple[SessionMeta, list[str]]:
    """세션 폴더(audio.wav + meta.json) 읽기 → (메타, 문제 목록)."""
    d = Path(session_dir)
    problems: list[str] = []
    if not (d / "audio.wav").is_file():
        problems.append("audio.wav 없음")
    raw = json.loads((d / "meta.json").read_text(encoding="utf-8"))
    meta = SessionMeta(**{k: v for k, v in raw.items() if k in SessionMeta.__dataclass_fields__})
    return meta, problems + meta.validate()
