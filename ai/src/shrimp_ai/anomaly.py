"""모델 B: 정상 기준(분 단위 μ·σ)과 비교한 이상 점수·등급. 학습 모델이 아닌 통계 기준선.

정상 세션들의 G(t) 를 급이 시각에 맞춰 같은 경과 시간끼리 비교하므로, 급이 후 자연스러운
감쇠는 이상으로 잡지 않는다. 섭식 반응이 '줄거나 늦어지는' 쪽만 본다(단측).
점수는 매 분 갱신되며(조기 경보), 30분이 끝나면 확정한다.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

from shrimp_ai.activity import compute_metrics, minute_axis, onset_minute
from shrimp_ai.config import AnalysisConfig, AnomalyConfig

GRADES = ("normal", "watch", "alert")
METRIC_NAMES = ("peak_cpm", "auc10", "auc30", "onset_min", "peak_min")


@dataclass
class Baseline:
    """수조 하나의 정상 기준."""

    tank: str
    n_sessions: int
    session_ids: list[str]
    minutes: list[int]
    mu: list[float]
    sd: list[float]               # 표본 표준편차(보정 전)
    sd_eff: list[float]           # 하한을 적용한 σ (점수 계산용)
    metrics: dict = field(default_factory=dict)   # 지표별 {"mean", "sd"}

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)

    def save(self, path: str | Path) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(self.to_json(), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "Baseline":
        return cls(**json.loads(Path(path).read_text(encoding="utf-8")))

    def band(self) -> tuple[np.ndarray, np.ndarray]:
        """화면용 정상 범위 μ ± σ_eff."""
        mu, sd = np.array(self.mu), np.array(self.sd_eff)
        return np.maximum(mu - sd, 0), mu + sd


def build_baseline(curves: list[np.ndarray], tank: str, session_ids: list[str] | None = None,
                   cfg: AnalysisConfig = AnalysisConfig(), acfg: AnomalyConfig = AnomalyConfig()) -> Baseline:
    """정상 세션들의 분당 클릭 수(분 번호 축 전체) → 기준."""
    if not curves:
        raise ValueError("정상 세션이 없음")
    c = np.stack([np.asarray(x, dtype=float) for x in curves])
    mu = c.mean(0)
    sd = c.std(0, ddof=1) if len(c) > 1 else np.zeros_like(mu)
    sd_eff = np.maximum(sd, acfg.sd_floor_rel * mu + acfg.sd_floor_abs)
    ms = [compute_metrics(x, cfg, acfg).to_dict() for x in c]
    stats = {}
    for name in METRIC_NAMES:
        v = np.array([m[name] for m in ms if m[name] is not None], dtype=float)
        stats[name] = {"mean": float(v.mean()) if len(v) else None,
                       "sd": float(v.std(ddof=1)) if len(v) > 1 else 0.0}
    return Baseline(tank, len(c), session_ids or [], minute_axis(cfg).tolist(), mu.round(3).tolist(),
                    sd.round(3).tolist(), sd_eff.round(3).tolist(), stats)


@dataclass
class ScoreState:
    """급이 후 minute 분까지 본 시점의 점수."""

    minute: int                 # 마지막으로 완료된 급이 후 분 번호
    score: float
    grade: str
    z_auc: float
    z_peak: float
    z_onset: float
    stage: str                  # provisional | early | final

    def to_dict(self) -> dict:
        return {k: (round(v, 3) if isinstance(v, float) else v) for k, v in asdict(self).items()}


def grade_of(score: float, acfg: AnomalyConfig) -> str:
    if score >= acfg.alert_score:
        return "alert"
    if score >= acfg.watch_score:
        return "watch"
    return "normal"


def score_at(counts: np.ndarray, minute: int, base: Baseline, cfg: AnalysisConfig = AnalysisConfig(),
             acfg: AnomalyConfig = AnomalyConfig()) -> ScoreState:
    """분 번호 축 분당 클릭 수에서 급이 후 0..minute 까지를 기준과 비교."""
    pre_n = int(cfg.pre_window_min)
    mu, sd = np.array(base.mu), np.array(base.sd_eff)
    obs = np.asarray(counts, dtype=float)[pre_n: pre_n + minute + 1]
    m_mu, m_sd = mu[pre_n: pre_n + minute + 1], sd[pre_n: pre_n + minute + 1]

    z_auc = float((obs.sum() - m_mu.sum()) / np.sqrt((m_sd ** 2).sum()))
    j = int(m_mu.argmax())
    z_peak = float((obs.max() - m_mu.max()) / m_sd[j])

    on_stat = base.metrics.get("onset_min", {})
    on_mu = on_stat.get("mean")
    z_onset = 0.0
    if on_mu is not None:
        on_sd = max(on_stat.get("sd") or 0.0, acfg.onset_sd_floor_min)
        obs_on = onset_minute(obs, np.asarray(counts, dtype=float)[:pre_n], acfg)
        if obs_on is not None:
            z_onset = (obs_on - on_mu) / on_sd
        elif minute + 1 > on_mu:
            z_onset = (minute + 1 - on_mu) / on_sd   # 아직 시작 안 함 → 최소한 이만큼 늦음

    score = (acfg.w_auc * max(0.0, -z_auc) + acfg.w_peak * max(0.0, -z_peak)
             + acfg.w_onset * max(0.0, z_onset))
    grade = grade_of(score, acfg) if minute + 1 >= acfg.min_minutes_for_alert else "normal"
    last = int(cfg.post_window_min) - 1
    stage = "final" if minute >= last else ("early" if minute + 1 == acfg.early_minute else "provisional")
    return ScoreState(minute, float(score), grade, z_auc, z_peak, float(z_onset), stage)


def score_session(counts: np.ndarray, base: Baseline, cfg: AnalysisConfig = AnalysisConfig(),
                  acfg: AnomalyConfig = AnomalyConfig()) -> list[ScoreState]:
    """급이 후 매 분의 점수 기록(오프라인 평가용, 스트리밍과 같은 계산)."""
    return [score_at(counts, m, base, cfg, acfg) for m in range(int(cfg.post_window_min))]


def compare(counts: np.ndarray, base: Baseline, cfg: AnalysisConfig = AnalysisConfig(),
            acfg: AnomalyConfig = AnomalyConfig()) -> list[dict]:
    """지표별 정상 기준 vs 현재 비교표(화면·인사이트용)."""
    cur = compute_metrics(counts, cfg, acfg).to_dict()
    rows = []
    for name in METRIC_NAMES:
        ref = base.metrics.get(name, {})
        m, v = ref.get("mean"), cur[name]
        change = None if (m in (None, 0) or v is None) else round((v - m) / m * 100, 1)
        rows.append({"metric": name, "normal_mean": None if m is None else round(m, 1),
                     "normal_sd": round(ref.get("sd") or 0.0, 1), "current": v, "change_pct": change})
    return rows
