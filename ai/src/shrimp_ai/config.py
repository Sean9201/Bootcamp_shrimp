"""분석 파라미터. 대역·임계값·빈 크기 등은 모두 여기서 관리한다(하드코딩 금지).

하이드로폰 샘플레이트·클릭 대역은 미확정이므로 기본값만 두고 실데이터로 조정한다.
시간·주파수는 초·Hz 로 적고, 샘플 수는 실행 시 샘플레이트로 환산한다.
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
    chunk_sec: float = 1.0            # 순차 처리 단위(실시간 입력과 같은 크기)


@dataclass(frozen=True)
class DetectorConfig:
    """1단계 후보 검출(신호처리). 과거 데이터만 쓰는 인과적 처리."""

    band_low_hz: float = 2000.0
    band_high_hz: float = 20000.0
    filter_order: int = 4
    envelope_lp_hz: float = 1500.0    # 에너지 포락선 평활
    noise_block_sec: float = 0.05     # 잡음 수준 추정 블록
    noise_history_sec: float = 5.0    # 잡음 수준 = 최근 이 시간 블록 중앙값들의 중앙값
    refractory_ms: float = 10.0       # 이보다 가까운 최고점은 하나로 합침
    candidate_k: float = 8.0          # 후보 임계값 = 잡음 에너지 × k (넓게 잡기)
    min_noise_energy: float = 1e-10   # 무음 구간 보호


@dataclass(frozen=True)
class PatchConfig:
    """2단계 CNN 입력: 후보 최고점 주변 스펙트로그램."""

    pre_sec: float = 0.012
    post_sec: float = 0.020
    n_fft_sec: float = 0.00533        # 48 kHz 에서 256 샘플
    hop_sec: float = 0.00133          # 48 kHz 에서 64 샘플
    f_low_hz: float = 1000.0
    f_high_hz: float = 20000.0


@dataclass(frozen=True)
class AnomalyConfig:
    """모델 B: 정상 기준 비교와 점수·등급."""

    sd_floor_rel: float = 0.15        # σ 하한 = 평균의 15% + 아래 절대값 (표본 4개 보호)
    sd_floor_abs: float = 3.0
    onset_rise_cpm: float = 10.0      # 반응 시작 = 급이 전 평균보다 이만큼 + 아래 배수 σ 이상
    onset_k_sd: float = 3.0
    onset_sd_floor_min: float = 0.7
    w_auc: float = 0.5                # Score = w_auc·(−z_AUC)+ + w_peak·(−z_peak)+ + w_onset·(z_onset)+
    w_peak: float = 0.3
    w_onset: float = 0.2
    watch_score: float = 1.0          # 주의
    alert_score: float = 2.0          # 경보 (시안의 임계값 2.0)
    min_minutes_for_alert: int = 3    # 급이 후 이 분 수가 지나야 등급을 낸다
    early_minute: int = 10            # 조기 판정 시점
