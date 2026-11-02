"""분석 파라미터. 대역·임계값·빈 크기 등은 모두 여기서 관리한다(하드코딩 금지).

하이드로폰 샘플레이트·클릭 대역은 미확정이므로 기본값만 두고 실데이터로 조정한다.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class AnalysisConfig:
    """분석 기본 설정."""

    band_low_hz: float = 2000.0       # 클릭 대역 하한
    band_high_hz: float = 20000.0     # 클릭 대역 상한 (나이퀴스트 초과 시 제한)
    bin_sec: float = 60.0             # CPM 집계 단위
    pre_window_min: float = 10.0      # 분석 창: 급이 전
    post_window_min: float = 30.0     # 분석 창: 급이 후
    auc_window_min: float = 10.0      # 급이 후 초기 AUC 구간
    eval_tolerance_ms: float = 5.0    # 클릭 매칭 허용오차(±)
