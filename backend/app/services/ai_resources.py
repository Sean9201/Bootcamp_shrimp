"""분석 엔진(ai 패키지) 산출물 불러오기: CNN, 검출 임계값, 수조별 정상 기준.

파일이 없으면 기능을 줄여서 동작한다(CNN 없음 → 후보 검출만, 기준 없음 → 점수 없이 G(t) 만).
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path

from shrimp_ai.anomaly import Baseline
from shrimp_ai.config import DetectorConfig
from shrimp_ai.detect.cnn import ClickClassifier

log = logging.getLogger(__name__)


class AIResources:
    """한 번 읽어 두고 분석마다 같이 쓴다(읽기 전용)."""

    def __init__(self, artifacts_dir: Path):
        self.dir = Path(artifacts_dir)
        self._lock = threading.Lock()
        self._clf: ClickClassifier | None = None
        self._loaded = False
        self._baselines: dict[str, Baseline | None] = {}
        self.detector: dict = {"candidate_k": DetectorConfig().candidate_k}

    def _load(self) -> None:
        with self._lock:
            if self._loaded:
                return
            p = self.dir / "click_cnn.pt"
            if p.is_file():
                self._clf = ClickClassifier.load(p)
            else:
                log.warning("CNN 가중치가 없음(%s) — 1단계 후보 검출만 사용", p)
            d = self.dir / "detector.json"
            if d.is_file():
                self.detector = json.loads(d.read_text(encoding="utf-8"))
            self._loaded = True

    @property
    def classifier(self) -> ClickClassifier | None:
        self._load()
        return self._clf

    @property
    def candidate_k(self) -> float:
        self._load()
        return float(self.detector.get("candidate_k", DetectorConfig().candidate_k))

    def baseline(self, tank_id: str) -> Baseline | None:
        if tank_id not in self._baselines:
            p = self.dir / "baselines" / f"{tank_id}.json"
            self._baselines[tank_id] = Baseline.load(p) if p.is_file() else None
        return self._baselines[tank_id]

    def eval_report(self) -> dict | None:
        p = self.dir / "eval_report.json"
        return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None

    def training_info(self) -> dict | None:
        """CNN 학습 기록(epoch 별 손실·검증 F1)."""
        p = self.dir / "click_cnn.json"
        if not p.is_file():
            return None
        m = json.loads(p.read_text(encoding="utf-8"))
        return {k: m.get(k) for k in ("history", "threshold", "val_f1", "n_train_patches", "n_train_clicks",
                                      "augmentation")}

    def status(self) -> dict:
        return {"classifier": self.classifier is not None,
                "baselines": sorted(p.stem for p in (self.dir / "baselines").glob("*.json"))
                if (self.dir / "baselines").is_dir() else []}
