"""활동 지표: 클릭 시각 → 급이 기준 분당 클릭 수 G(t) → Peak·AUC·반응 시작·최고점 도달.

분 번호 m 은 급이 기준 [m, m+1) 분 구간. 급이 전은 -pre..-1, 급이 후는 0..post-1.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

from shrimp_ai.config import AnalysisConfig, AnomalyConfig


def minute_axis(cfg: AnalysisConfig = AnalysisConfig()) -> np.ndarray:
    """분 번호 배열 (-pre … post-1)."""
    return np.arange(-int(cfg.pre_window_min), int(cfg.post_window_min))


def minute_counts(click_times_sec, feeding_offset_sec: float, cfg: AnalysisConfig = AnalysisConfig()) -> np.ndarray:
    """녹음 시작 기준 클릭 시각(초) → 분 번호 축에 맞춘 분당 클릭 수."""
    rel = (np.asarray(click_times_sec, dtype=float) - feeding_offset_sec) / cfg.bin_sec
    edges = np.append(minute_axis(cfg), int(cfg.post_window_min)).astype(float)
    counts, _ = np.histogram(rel, bins=edges)
    return counts


def onset_minute(post: np.ndarray, pre: np.ndarray, acfg: AnomalyConfig = AnomalyConfig()) -> int | None:
    """반응 시작 분: 급이 전 평균 + max(k·σ, 최소 상승폭)을 처음 넘은 급이 후 분. 없으면 None."""
    if len(pre) == 0:
        return None
    level = pre.mean() + max(acfg.onset_k_sd * pre.std(), acfg.onset_rise_cpm)
    hit = np.flatnonzero(post > level)
    return int(hit[0]) if len(hit) else None


@dataclass
class ActivityMetrics:
    """세션 1개의 활동 지표."""

    baseline_cpm: float      # 급이 전 평균
    peak_cpm: int
    peak_min: int            # 최고점 도달(급이 후 분)
    auc10: int               # 급이 후 0–10분 누적 클릭
    auc30: int               # 급이 후 0–30분 누적 클릭
    onset_min: int | None    # 반응 시작 지연(분)

    def to_dict(self) -> dict:
        return asdict(self)


def compute_metrics(counts: np.ndarray, cfg: AnalysisConfig = AnalysisConfig(),
                    acfg: AnomalyConfig = AnomalyConfig()) -> ActivityMetrics:
    """분 번호 축 전체(급이 전+후) 분당 클릭 수 → 지표. 급이 후가 덜 찼으면 있는 만큼만."""
    pre_n = int(cfg.pre_window_min)
    pre, post = counts[:pre_n], counts[pre_n:]
    auc_n = int(cfg.auc_window_min)
    return ActivityMetrics(
        baseline_cpm=round(float(pre.mean()), 1) if len(pre) else 0.0,
        peak_cpm=int(post.max()) if len(post) else 0,
        peak_min=int(post.argmax()) if len(post) else 0,
        auc10=int(post[:auc_n].sum()),
        auc30=int(post.sum()),
        onset_min=onset_minute(post, pre, acfg),
    )
