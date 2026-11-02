"""세션 폴더 읽기(docs/interfaces.md 1절: audio.wav + meta.json + clicks.csv)."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass
class Session:
    """세션 1개."""

    dir: Path
    meta: dict

    @property
    def session_id(self) -> str:
        return self.meta["session_id"]

    @property
    def audio_path(self) -> Path:
        return self.dir / "audio.wav"

    @property
    def tank(self) -> str:
        return self.meta["tank"]

    @property
    def noise_condition(self) -> str:
        return self.meta.get("noise_condition", "")

    @property
    def feeding_offset_sec(self) -> float:
        return float(self.meta["feeding_offset_sec"])

    @property
    def label(self) -> str | None:
        return self.meta.get("label")

    @property
    def day(self) -> int | None:
        return self.meta.get("day")

    @property
    def split(self) -> str | None:
        return (self.meta.get("synthetic") or {}).get("split") or self.meta.get("split")

    def truth_clicks(self) -> np.ndarray | None:
        """정답 클릭 시각(녹음 시작 기준 초). 라벨이 없으면 None."""
        p = self.dir / "clicks.csv"
        if not p.is_file():
            return None
        with open(p, encoding="utf-8-sig") as f:
            return np.array([float(r["time_sec"]) for r in csv.DictReader(f)])


def load_sessions(root: str | Path, splits: tuple[str, ...] | None = None) -> list[Session]:
    """root 아래 세션 폴더 전부(정렬). splits 를 주면 그 split 만."""
    out = []
    for d in sorted(Path(root).iterdir()):
        m = d / "meta.json"
        if d.is_dir() and m.is_file():
            s = Session(d, json.loads(m.read_text(encoding="utf-8")))
            if splits is None or s.split in splits:
                out.append(s)
    return out
