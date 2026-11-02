"""분석 실행기: 백그라운드 스레드에서 녹음 → 엔진 → 이벤트 발행·DB 저장 → 인사이트.

입력은 FileSource(배속 재생). 실시간 하이드로폰이 붙으면 소스만 LiveSource 로 바꾼다.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from sqlalchemy.orm import Session, sessionmaker

from shrimp_ai.config import AnalysisConfig, AnomalyConfig
from shrimp_ai.detect.candidates import StreamingCandidateDetector
from shrimp_ai.engine import StreamingAnalyzer
from shrimp_ai.sources import FileSource

from app.core.config import Settings
from app.db.models import Alert, Analysis, Insight, MinutePoint, ScorePoint
from app.services.ai_resources import AIResources
from app.services.events import EventBus
from app.services.insight import build_facts, make_gemini, run_insight

log = logging.getLogger(__name__)


def baseline_band(base) -> dict | None:
    """화면이 처음부터 회색 정상 범위를 그릴 수 있도록 미리 보내는 기준."""
    if base is None:
        return None
    lo, hi = base.band()
    return {"tank": base.tank, "n_sessions": base.n_sessions, "minutes": base.minutes, "mu": base.mu,
            "lo": [round(float(v), 2) for v in lo], "hi": [round(float(v), 2) for v in hi],
            "metrics": base.metrics}


class Runner:
    """분석 작업 큐."""

    def __init__(self, settings: Settings, sessions: sessionmaker[Session], ai: AIResources, bus: EventBus):
        self.s, self.sessions, self.ai, self.bus = settings, sessions, ai, bus
        self.pool = ThreadPoolExecutor(max_workers=settings.analysis_workers, thread_name_prefix="analysis")
        self.cfg, self.acfg = AnalysisConfig(), AnomalyConfig()

    def submit(self, analysis_id: int) -> None:
        self.bus.open(analysis_id)
        self.pool.submit(self._run_safe, analysis_id)

    def shutdown(self) -> None:
        self.pool.shutdown(wait=False, cancel_futures=True)

    # ------------------------------------------------------------------
    def _run_safe(self, analysis_id: int) -> None:
        try:
            self._run(analysis_id)
        except Exception as e:  # 실패도 화면에 알린다
            log.exception("분석 %s 실패", analysis_id)
            with self.sessions() as db:
                a = db.get(Analysis, analysis_id)
                a.status, a.error, a.finished_at = "failed", f"{type(e).__name__}: {e}", datetime.now(timezone.utc)
                db.commit()
            self.bus.publish(analysis_id, {"type": "error", "message": "분석 중 오류가 발생했습니다.",
                                           "detail": f"{type(e).__name__}: {e}"})
        finally:
            self.bus.close(analysis_id)

    def _run(self, analysis_id: int) -> None:
        with self.sessions() as db:
            a = db.get(Analysis, analysis_id)
            a.status, a.started_at = "running", datetime.now(timezone.utc)
            db.commit()
            tank_id, noise = a.tank_id, a.tank.noise_condition
            path, offset, speed = a.file_path, a.feeding_offset_sec, a.speed

        base = self.ai.baseline(tank_id)
        src = FileSource(path, self.cfg.chunk_sec, speed=speed)
        eng = StreamingAnalyzer(src.sr, offset, StreamingCandidateDetector(src.sr, k=self.ai.candidate_k),
                                self.ai.classifier, base, self.cfg, self.acfg)
        self.bus.publish(analysis_id, {
            "type": "meta", "analysis_id": analysis_id, "tank_id": tank_id, "noise_condition": noise,
            "speed": speed, "duration_sec": round(src.duration_sec, 1), "feeding_offset_sec": offset,
            "pre_min": self.cfg.pre_window_min, "post_min": self.cfg.post_window_min,
            "thresholds": {"watch": self.acfg.watch_score, "alert": self.acfg.alert_score},
            "baseline": baseline_band(base), "classifier": self.ai.classifier is not None})

        alerts: list[dict] = []
        last_progress = 0.0
        for chunk in src:
            evs = eng.feed(chunk)
            self._handle(analysis_id, tank_id, evs, alerts)
            last_progress = evs[-1]["t_sec"] if evs and evs[-1]["type"] == "progress" else last_progress
        final_evs = eng.finish()
        self._handle(analysis_id, tank_id, final_evs, alerts)
        final = final_evs[-1]

        with self.sessions() as db:
            a = db.get(Analysis, analysis_id)
            a.metrics, a.comparison = final["metrics"], final.get("comparison")
            a.max_grade = final["max_grade"] if base is not None else None
            a.final_score = (final.get("score") or {}).get("score")
            a.baseline_info, a.n_clicks, a.compute_sec = final.get("baseline"), final["n_clicks"], final["compute_sec"]
            a.progress_sec = last_progress
            db.commit()

        self.bus.publish(analysis_id, {"type": "insight_pending"})
        facts = build_facts(final, alerts, noise, self.acfg.watch_score, self.acfg.alert_score)
        key = self.s.gemini_api_key.get_secret_value() if self.s.gemini_api_key else None
        llm = make_gemini(key, self.s.gemini_model, self.s.llm_timeout_sec, self.s.llm_temperature) if key else None
        res = run_insight(facts, llm, self.s.gemini_model, self.s.insight_max_retries)
        with self.sessions() as db:
            db.add(Insight(analysis_id=analysis_id, **res))
            a = db.get(Analysis, analysis_id)
            a.status, a.finished_at = "done", datetime.now(timezone.utc)
            db.commit()
        self.bus.publish(analysis_id, {"type": "insight", **res, "facts": facts})
        self.bus.publish(analysis_id, {"type": "done", "analysis_id": analysis_id})

    def _handle(self, analysis_id: int, tank_id: str, events: list[dict], alerts: list[dict]) -> None:
        """이벤트 발행 + 분·점수·알림은 DB 에도 저장."""
        rows = []
        for e in events:
            self.bus.publish(analysis_id, e)
            t = e["type"]
            if t == "minute":
                rows.append(MinutePoint(analysis_id=analysis_id, minute=e["minute"], cpm=e["cpm"],
                                        mu=e.get("mu"), lo=e.get("lo"), hi=e.get("hi")))
            elif t == "score":
                rows.append(ScorePoint(analysis_id=analysis_id, **{k: e[k] for k in (
                    "minute", "score", "grade", "raw_grade", "z_auc", "z_peak", "z_onset", "stage")}))
            elif t == "alert":
                alerts.append(e)
                rows.append(Alert(analysis_id=analysis_id, tank_id=tank_id, minute=e["minute"], level=e["level"],
                                  score=e["score"], stage=e["stage"]))
        if rows:
            with self.sessions() as db:
                db.add_all(rows)
                db.commit()
