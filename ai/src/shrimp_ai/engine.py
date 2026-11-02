"""스트리밍 분석 엔진: 청크 → 클릭 → 분당 클릭 수 → (정상 기준이 있으면) 점수·경보.

입력 소스(실시간/파일 배속)와 무관하게 feed(chunk) 를 순서대로 부르면 된다.
반환하는 이벤트는 JSON 으로 바로 보낼 수 있는 dict 이다.

  progress  {"t_sec"}                         처리한 위치(급이 기준 초)
  clicks    {"t": [...급이 기준 초]}           이번 청크에서 확정된 클릭
  minute    {"minute", "cpm", "mu", "lo", "hi"} 한 분이 끝남
  score     {ScoreState}                       급이 후 매 분 점수 (stage: provisional/early/final)
  alert     {"minute", "level", "score"}       등급이 올라감(watch/alert)
  final     {"metrics", "score", "comparison", "counts", ...}
"""

from __future__ import annotations

import time

import numpy as np

from shrimp_ai.activity import compute_metrics, minute_axis
from shrimp_ai.anomaly import GRADES, Baseline, compare, score_at
from shrimp_ai.config import AnalysisConfig, AnomalyConfig
from shrimp_ai.detect.candidates import Candidate, StreamingCandidateDetector
from shrimp_ai.detect.cnn import ClickClassifier


class StreamingAnalyzer:
    """세션 1개를 순차 분석한다."""

    def __init__(self, sr: int, feeding_offset_sec: float, detector: StreamingCandidateDetector,
                 classifier: ClickClassifier | None = None, baseline: Baseline | None = None,
                 cfg: AnalysisConfig = AnalysisConfig(), acfg: AnomalyConfig = AnomalyConfig()):
        self.sr, self.feed_sec = sr, feeding_offset_sec
        self.det, self.clf, self.base = detector, classifier, baseline
        self.cfg, self.acfg = cfg, acfg
        self.axis = minute_axis(cfg)
        self.counts = np.zeros(len(self.axis), dtype=int)
        self.pre_n = int(cfg.pre_window_min)
        self.next_minute = 0                      # 다음에 완료 처리할 분 번호 축 위치
        self.queue: list[Candidate] = []
        self.buf = np.empty(0, dtype=np.float32)  # 패치 자르기용 최근 원신호
        self.buf_start = 0
        self.pos = 0
        self.click_times: list[float] = []        # 녹음 시작 기준 초
        self.n_candidates = 0
        self.grade = "normal"
        self.last_score = None
        self.elapsed = 0.0                        # 순수 계산 시간(초)
        if baseline is not None:
            self.lo, self.hi = baseline.band()

    # ------------------------------------------------------------ 내부
    def _classify_ready(self, final: bool) -> list[float]:
        """패치를 자를 수 있게 된 후보를 판정 → 확정 클릭 시각(초)."""
        if not self.queue:
            return []
        if self.clf is None:
            ready, self.queue = self.queue, []
            return [c.index / self.sr for c in ready]
        spec = self.clf.spec
        end = self.buf_start + len(self.buf)
        ready = [c for c in self.queue if final or c.index + spec.post <= end]
        self.queue = [c for c in self.queue if not (final or c.index + spec.post <= end)]
        patches, keep = [], []
        for c in ready:
            p = spec.cut(self.buf, c.index, self.buf_start)
            if p is not None:
                patches.append(p)
                keep.append(c)
        if not keep:
            return []
        prob = self.clf.predict_proba(np.stack(patches))
        return [c.index / self.sr for c, p in zip(keep, prob) if p >= self.clf.threshold]

    def _complete_minutes(self, final: bool) -> list[dict]:
        """스트림 위치가 지나간 분을 마감하고 분·점수·경보 이벤트를 만든다."""
        ev = []
        lag = 0.05 if not final else 0.0
        pos_rel_min = (self.pos / self.sr - self.feed_sec) / self.cfg.bin_sec
        while self.next_minute < len(self.axis):
            m = int(self.axis[self.next_minute])
            if not final and pos_rel_min < m + 1 + lag / self.cfg.bin_sec:
                break
            e = {"type": "minute", "minute": m, "cpm": int(self.counts[self.next_minute])}
            if self.base is not None:
                i = self.next_minute
                e.update(mu=self.base.mu[i], lo=round(float(self.lo[i]), 2), hi=round(float(self.hi[i]), 2))
            ev.append(e)
            if self.base is not None and m >= 0:
                s = score_at(self.counts, m, self.base, self.cfg, self.acfg)
                self.last_score = s
                ev.append({"type": "score", **s.to_dict()})
                if GRADES.index(s.grade) > GRADES.index(self.grade):
                    ev.append({"type": "alert", "minute": m, "level": s.grade, "score": round(s.score, 3),
                               "stage": s.stage})
                self.grade = s.grade if GRADES.index(s.grade) > GRADES.index(self.grade) else self.grade
            self.next_minute += 1
        return ev

    def _add_clicks(self, times: list[float]) -> list[dict]:
        if not times:
            return []
        self.click_times += times
        rel = (np.asarray(times) - self.feed_sec) / self.cfg.bin_sec
        idx = np.floor(rel).astype(int) - int(self.axis[0])
        for i in idx[(idx >= 0) & (idx < len(self.axis))]:
            self.counts[i] += 1
        return [{"type": "clicks", "t": [round(t - self.feed_sec, 3) for t in times]}]

    # ------------------------------------------------------------ 공개
    def feed(self, chunk: np.ndarray) -> list[dict]:
        """청크 하나 처리."""
        t0 = time.perf_counter()
        cands = self.det.process(chunk)
        self.n_candidates += len(cands)
        self.queue += cands
        self.buf = np.concatenate([self.buf, chunk.astype(np.float32)])
        self.pos += len(chunk)
        ev = self._add_clicks(self._classify_ready(final=False))
        keep = len(chunk) + int(0.2 * self.sr)
        if len(self.buf) > keep:
            self.buf_start += len(self.buf) - keep
            self.buf = self.buf[-keep:]
        ev += self._complete_minutes(final=False)
        ev.append({"type": "progress", "t_sec": round(self.pos / self.sr - self.feed_sec, 3)})
        self.elapsed += time.perf_counter() - t0
        return ev

    def finish(self) -> list[dict]:
        """스트림 끝: 남은 후보·분을 마감하고 최종 결과."""
        t0 = time.perf_counter()
        self.queue += self.det.flush()
        ev = self._add_clicks(self._classify_ready(final=True))
        ev += self._complete_minutes(final=True)
        metrics = compute_metrics(self.counts, self.cfg, self.acfg).to_dict()
        final = {"type": "final", "metrics": metrics, "counts": self.counts.tolist(),
                 "minutes": self.axis.tolist(), "n_clicks": len(self.click_times),
                 "n_candidates": self.n_candidates, "max_grade": self.grade}
        if self.base is not None:
            final["score"] = self.last_score.to_dict() if self.last_score else None
            final["comparison"] = compare(self.counts, self.base, self.cfg, self.acfg)
            final["baseline"] = {"tank": self.base.tank, "n_sessions": self.base.n_sessions}
        self.elapsed += time.perf_counter() - t0
        final["compute_sec"] = round(self.elapsed, 3)
        return ev + [final]
