"""모크 세션 합성: 샘플 클릭음 → 40분 세션(audio.wav + clicks.csv + meta.json).

실제 새우 음향을 재현하는 것이 아니다. 실측 데이터가 오기 전까지 파이프라인·시연·평가
코드를 검증하기 위한 데이터다. 정답 곡선(분당 클릭 수)은 meta.json 의 synthetic 에 남긴다.

실행 예 (data_pipeline 폴더):
    ..\\..\\.venv\\Scripts\\python.exe -m shrimp_data.synthetic ^
        --clicks <새우샘플링\\01_sparse.wav> --labels <새우샘플링\\labels.csv> ^
        --out data/synthetic/mock_v1
"""

from __future__ import annotations

import argparse
import bisect
import csv
import hashlib
import json
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy import signal

from shrimp_data.session import SessionMeta

KST = timezone(timedelta(hours=9))
GENERATOR = "shrimp_data.synthetic v1"


# ---------------------------------------------------------------- 설정값

@dataclass(frozen=True)
class ResponseProfile:
    """급이 반응 곡선(분당 클릭 수) 파라미터. 시간 단위는 급이 = 0분 기준 분."""

    baseline_cpm: float      # 급이 전·반응 전 배경 클릭
    peak_cpm: float          # 최고 CPM
    onset_min: float         # 반응 시작 지연
    rise_min: float          # 반응 시작 → 최고점까지 걸리는 시간
    decay_tau_min: float     # 최고점 이후 감쇠 시간상수
    tail_cpm: float          # 후반 잔류 수준


# 시안의 정상(Peak 100, 초기 10분 AUC ≈ 620, 지연 1.2분)과 이상(Peak 42, AUC ≈ 210, 지연 3.5분)에 맞춘 값
NORMAL = ResponseProfile(baseline_cpm=8, peak_cpm=100, onset_min=1.2, rise_min=3.0,
                         decay_tau_min=9.0, tail_cpm=15)
ABNORMAL = ResponseProfile(baseline_cpm=7, peak_cpm=42, onset_min=3.5, rise_min=3.0,
                           decay_tau_min=6.0, tail_cpm=10)
SCENARIOS = {"normal": NORMAL, "abnormal": ABNORMAL}


@dataclass(frozen=True)
class NoiseLevels:
    """배경 소음 크기(선형 진폭, 16-bit full scale = 1.0)."""

    floor_rms: float          # 센서·전기 잡음(광대역)
    flow_rms: float           # 저주파 수류
    hiss_rms: float = 0.0     # 에어레이션 쉿 소리(2–15 kHz)
    hum_amp: float = 0.0      # 펌프 웅웅거림(기본 주파수 배음)
    bubble_rate_hz: float = 0.0   # 기포 터짐(클릭과 헷갈릴 수 있는 방해음)
    impacts: int = 0          # 장비·작업 충격 횟수(세션당)


NOISE = {
    "blocked": NoiseLevels(floor_rms=0.0012, flow_rms=0.0015),
    "operating": NoiseLevels(floor_rms=0.002, flow_rms=0.004, hiss_rms=0.006, hum_amp=0.02,
                             bubble_rate_hz=3.0, impacts=2),
}


@dataclass(frozen=True)
class SynthConfig:
    """세션 합성 공통 설정."""

    pre_min: float = 10.0               # 급이 전 녹음
    post_min: float = 30.0              # 급이 후 녹음
    block_sec: float = 60.0             # 한 번에 만들어 쓰는 길이(메모리 절약)
    min_click_gap_sec: float = 0.015    # 정답 클릭 사이 최소 간격
    click_amp_median: float = 0.12      # 클릭 최고 진폭 중앙값
    click_amp_sigma: float = 0.4        # 클릭 진폭 로그정규 퍼짐(거리·방향 차이)
    click_amp_range: tuple[float, float] = (0.02, 0.35)
    click_stretch: tuple[float, float] = (0.92, 1.08)   # 클릭 길이·음높이 변형 비율
    rate_wobble: float = 0.12           # 30초 단위 활동량 흔들림(곱셈, 표준편차)
    rate_knot_sec: float = 30.0
    feeding_duration_sec: float = 20.0  # 사료 투입 소요 시간
    pellet_rate_hz: float = 4.0         # 투입 중 사료 알갱이 충돌음
    hum_f0_hz: float = 60.0
    template_pre_sec: float = 0.004     # 템플릿에서 클릭 최고점 앞쪽 길이
    template_post_sec: float = 0.012


# 개체군 차이: 수조별 반응 크기 배율 (조건과 무관한 생물학적 차이)
TANK_SCALE = {"A1": 1.00, "A2": 0.92, "A3": 1.08, "B1": 1.04, "B2": 0.95, "B3": 1.01}
TANK_CONDITION = {t: ("blocked" if t.startswith("A") else "operating") for t in TANK_SCALE}
FIRST_DAY = datetime(2026, 10, 24, 9, 0, tzinfo=KST)


@dataclass
class SessionSpec:
    """만들 세션 1개의 조건."""

    session_id: str
    tank: str
    day: int
    scenario: str            # normal | abnormal
    split: str               # train | val | test_noise | demo
    profile: ResponseProfile | None = None   # None 이면 시나리오 기본값에 수조·일차 변동 적용
    seed: int | None = None
    extra: dict = field(default_factory=dict)

    @property
    def noise_condition(self) -> str:
        return TANK_CONDITION[self.tank]

    def resolved_seed(self, master_seed: int) -> int:
        """세션 ID 와 전체 시드로 재현 가능한 시드."""
        if self.seed is not None:
            return self.seed
        h = hashlib.sha256(f"{master_seed}:{self.session_id}".encode()).digest()
        return int.from_bytes(h[:4], "little")


# ---------------------------------------------------------------- 반응 곡선

def expected_cpm(p: ResponseProfile, t_min) -> np.ndarray:
    """급이 기준 시각(분)에서의 기대 CPM."""
    t = np.asarray(t_min, dtype=float)
    out = np.full(t.shape, float(p.baseline_cpm))
    t_peak = p.onset_min + p.rise_min
    rising = (t >= p.onset_min) & (t < t_peak)
    s = (t[rising] - p.onset_min) / p.rise_min
    out[rising] = p.baseline_cpm + (p.peak_cpm - p.baseline_cpm) * s * s * (3 - 2 * s)
    decay = t >= t_peak
    out[decay] = p.tail_cpm + (p.peak_cpm - p.tail_cpm) * np.exp(-(t[decay] - t_peak) / p.decay_tau_min)
    return out


def jitter_profile(base: ResponseProfile, tank_scale: float, rng: np.random.Generator) -> ResponseProfile:
    """수조 배율 + 일차별 무작위 변동을 준 곡선."""
    n = lambda sd: rng.normal(1.0, sd)  # noqa: E731
    return ResponseProfile(
        baseline_cpm=base.baseline_cpm * n(0.15),
        peak_cpm=base.peak_cpm * tank_scale * n(0.08),
        onset_min=max(0.2, base.onset_min + rng.normal(0, 0.25)),
        rise_min=base.rise_min * n(0.10),
        decay_tau_min=base.decay_tau_min * n(0.10),
        tail_cpm=base.tail_cpm * n(0.15),
    )


def sample_click_times(p: ResponseProfile, cfg: SynthConfig, rng: np.random.Generator) -> np.ndarray:
    """비균질 포아송 과정(thinning)으로 클릭 시각(녹음 시작 기준 초)을 뽑는다."""
    total = (cfg.pre_min + cfg.post_min) * 60
    knots_t = np.arange(0, total + cfg.rate_knot_sec, cfg.rate_knot_sec)
    knots_v = np.clip(rng.normal(1.0, cfg.rate_wobble, len(knots_t)), 0.5, 1.5)
    rate = lambda ts: expected_cpm(p, ts / 60 - cfg.pre_min) / 60 * np.interp(ts, knots_t, knots_v)  # noqa: E731
    grid = np.arange(0, total, 1.0)
    lam_max = rate(grid).max() * 1.1
    cand = np.sort(rng.uniform(0, total, rng.poisson(lam_max * total)))
    kept = cand[rng.uniform(0, lam_max, len(cand)) < rate(cand)]
    out, last = [], -1.0
    for t in kept:
        if t - last >= cfg.min_click_gap_sec:
            out.append(t)
            last = t
    return np.asarray(out)


# ---------------------------------------------------------------- 소리 재료

def load_click_bank(wav_path: str | Path, labels_csv: str | Path, cfg: SynthConfig = SynthConfig(),
                    file_name: str | None = None) -> tuple[np.ndarray, int]:
    """라벨된 클릭 구간에서 최고점 기준으로 맞춘 템플릿들(최고 진폭 1)과 샘플레이트."""
    x, sr = sf.read(wav_path, dtype="float32", always_2d=True)
    x = x[:, 0]
    file_name = file_name or Path(wav_path).name
    with open(labels_csv, encoding="utf-8-sig") as f:
        rows = [r for r in csv.DictReader(f) if r["file"] == file_name]
    if not rows:
        raise ValueError(f"{labels_csv} 에 {file_name} 라벨이 없음")
    pre, post = int(cfg.template_pre_sec * sr), int(cfg.template_post_sec * sr)
    fade = signal.windows.tukey(pre + post, alpha=0.25)
    bank = []
    for r in rows:
        s, e = int(float(r["start_sec"]) * sr), int(float(r["end_sec"]) * sr)
        pk = s + int(np.argmax(np.abs(x[s:e])))
        if pk - pre < 0 or pk + post > len(x):
            continue
        t = x[pk - pre: pk + post] * fade
        bank.append(t / np.abs(t).max())
    return np.stack(bank).astype(np.float32), sr


def damped_tone(sr: int, f_hz: float, decay_sec: float, rng: np.random.Generator) -> np.ndarray:
    """감쇠 사인파(기포 터짐·사료 알갱이 충돌 같은 짧은 방해음)."""
    n = int(decay_sec * 6 * sr)
    t = np.arange(n) / sr
    return (np.sin(2 * np.pi * f_hz * t + rng.uniform(0, 2 * np.pi)) * np.exp(-t / decay_sec)).astype(np.float32)


def noise_burst(sr: int, dur_sec: float, band: tuple[float, float], rng: np.random.Generator) -> np.ndarray:
    """지수 감쇠 광대역 잡음(입수 충격·장비 충격)."""
    n = int(dur_sec * sr)
    sos = signal.butter(4, band, btype="bandpass", fs=sr, output="sos")
    b = signal.sosfilt(sos, rng.standard_normal(n)) * np.exp(-np.arange(n) / (n / 5))
    return (b / np.abs(b).max()).astype(np.float32)


@dataclass
class Event:
    """녹음에 더할 짧은 소리 하나."""

    start: int               # 샘플 위치
    wave: np.ndarray
    kind: str                # click | pellet | splash | bubble | impact
    time_sec: float          # 기록용 시각(클릭은 최고점)
    amp: float


def build_events(times: np.ndarray, bank: np.ndarray, sr: int, cfg: SynthConfig, noise: NoiseLevels,
                 total_sec: float, rng: np.random.Generator) -> tuple[list[Event], list[dict]]:
    """정답 클릭 + 방해음 이벤트 목록과 meta.events(사건 기록)."""
    events: list[Event] = []
    pre = int(cfg.template_pre_sec * sr)
    lo, hi = cfg.click_amp_range
    for t in times:
        w = bank[rng.integers(len(bank))]
        k = rng.uniform(*cfg.click_stretch)
        if abs(k - 1) > 1e-3:
            w = signal.resample(w, int(round(len(w) * k))).astype(np.float32)
            w /= np.abs(w).max()
        amp = float(np.clip(cfg.click_amp_median * rng.lognormal(0, cfg.click_amp_sigma), lo, hi))
        w = w * amp * rng.choice([-1.0, 1.0])
        start = int(round(t * sr)) - int(round(pre * k))
        events.append(Event(start, w.astype(np.float32), "click", float(t), amp))

    feed_t = cfg.pre_min * 60
    sp = noise_burst(sr, 0.6, (200, 8000), rng) * 0.15
    events.append(Event(int(feed_t * sr), sp, "splash", feed_t, 0.15))
    n_pellet = rng.poisson(cfg.pellet_rate_hz * cfg.feeding_duration_sec)
    for t in feed_t + np.sort(rng.uniform(0, cfg.feeding_duration_sec, n_pellet)):
        a = float(rng.uniform(0.02, 0.08))
        w = damped_tone(sr, rng.uniform(2000, 5000), rng.uniform(0.001, 0.002), rng) * a
        events.append(Event(int(t * sr), w, "pellet", float(t), a))

    if noise.bubble_rate_hz > 0:
        n_b = rng.poisson(noise.bubble_rate_hz * total_sec)
        for t in np.sort(rng.uniform(0, total_sec, n_b)):
            a = float(np.clip(0.025 * rng.lognormal(0, 0.5), 0.005, 0.08))
            f = float(np.exp(rng.uniform(np.log(1000), np.log(6000))))
            w = damped_tone(sr, f, rng.uniform(0.002, 0.006), rng) * a
            events.append(Event(int(t * sr), w, "bubble", float(t), a))

    log = []
    for t in np.sort(rng.uniform(60, total_sec - 60, noise.impacts)):
        w = noise_burst(sr, 0.25, (100, 16000), rng) * 0.25
        events.append(Event(int(t * sr), w, "impact", float(t), 0.25))
        log.append({"time_sec": round(float(t), 3), "note": "장비·작업 충격(합성)"})
    log.append({"time_sec": round(feed_t, 3), "note": "사료 투입(입수음·알갱이 충돌, 합성)"})
    events.sort(key=lambda e: e.start)
    return events, sorted(log, key=lambda e: e["time_sec"])


class ContinuousNoise:
    """블록 단위로 이어지는 배경 소음(필터 상태·위상을 블록 사이에 유지)."""

    def __init__(self, sr: int, noise: NoiseLevels, cfg: SynthConfig, rng: np.random.Generator):
        self.sr, self.n, self.cfg, self.rng = sr, noise, cfg, rng
        self.flow_sos = signal.butter(2, 400, btype="lowpass", fs=sr, output="sos")
        self.hiss_sos = signal.butter(4, (2000, 15000), btype="bandpass", fs=sr, output="sos")
        self.flow_zi = np.zeros((self.flow_sos.shape[0], 2))
        self.hiss_zi = np.zeros((self.hiss_sos.shape[0], 2))
        # 필터 이득 보정용 rms 측정
        probe = rng.standard_normal(sr)
        self.flow_gain = 1 / np.std(signal.sosfilt(self.flow_sos, probe))
        self.hiss_gain = 1 / np.std(signal.sosfilt(self.hiss_sos, probe))
        self.hum_phase = rng.uniform(0, 2 * np.pi, 8)

    def render(self, start: int, n: int) -> np.ndarray:
        rng, nl = self.rng, self.n
        out = rng.standard_normal(n) * nl.floor_rms
        f, self.flow_zi = signal.sosfilt(self.flow_sos, rng.standard_normal(n), zi=self.flow_zi)
        out += f * self.flow_gain * nl.flow_rms
        if nl.hiss_rms > 0:
            h, self.hiss_zi = signal.sosfilt(self.hiss_sos, rng.standard_normal(n), zi=self.hiss_zi)
            out += h * self.hiss_gain * nl.hiss_rms
        if nl.hum_amp > 0:
            t = (start + np.arange(n)) / self.sr
            am = 1 + 0.1 * np.sin(2 * np.pi * 0.3 * t)
            for k in range(8):
                out += nl.hum_amp / (k + 1) * am * np.sin(2 * np.pi * self.cfg.hum_f0_hz * (k + 1) * t
                                                          + self.hum_phase[k])
        return out.astype(np.float32)


# ---------------------------------------------------------------- 세션 만들기

def render_session(spec: SessionSpec, bank: np.ndarray, sr: int, out_root: str | Path,
                   cfg: SynthConfig = SynthConfig(), master_seed: int = 2026) -> dict:
    """세션 폴더 1개를 만들고 요약(manifest 한 줄)을 돌려준다."""
    seed = spec.resolved_seed(master_seed)
    rng = np.random.default_rng(seed)
    base = SCENARIOS[spec.scenario]
    profile = spec.profile or jitter_profile(base, TANK_SCALE[spec.tank], rng)
    noise = NOISE[spec.noise_condition]
    total_sec = (cfg.pre_min + cfg.post_min) * 60
    total = int(round(total_sec * sr))

    times = sample_click_times(profile, cfg, rng)
    events, event_log = build_events(times, bank, sr, cfg, noise, total_sec, rng)
    bg = ContinuousNoise(sr, noise, cfg, rng)

    d = Path(out_root) / spec.session_id
    d.mkdir(parents=True, exist_ok=True)
    starts = [e.start for e in events]
    max_len = max(len(e.wave) for e in events)
    block = int(cfg.block_sec * sr)
    clipped = 0
    with sf.SoundFile(d / "audio.wav", "w", samplerate=sr, channels=1, subtype="PCM_16") as f:
        for b0 in range(0, total, block):
            n = min(block, total - b0)
            buf = bg.render(b0, n)
            i0 = bisect.bisect_left(starts, b0 - max_len)
            i1 = bisect.bisect_left(starts, b0 + n)
            for e in events[i0:i1]:
                s, t = max(e.start, b0), min(e.start + len(e.wave), b0 + n)
                if s < t:
                    buf[s - b0: t - b0] += e.wave[s - e.start: t - e.start]
            clipped += int(np.sum(np.abs(buf) > 0.999))
            f.write(np.clip(buf, -0.999, 0.999))

    clicks = [e for e in events if e.kind == "click"]
    with open(d / "clicks.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["time_sec", "amp"])
        w.writerows([f"{e.time_sec:.4f}", f"{e.amp:.4f}"] for e in clicks)
    with open(d / "distractors.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["time_sec", "kind", "amp"])
        w.writerows([f"{e.time_sec:.4f}", e.kind, f"{e.amp:.4f}"] for e in events if e.kind != "click")

    fed_at = FIRST_DAY + timedelta(days=spec.day - 1)
    meta = SessionMeta(
        session_id=spec.session_id, tank=spec.tank, noise_condition=spec.noise_condition, day=spec.day,
        recorded_at=(fed_at - timedelta(minutes=cfg.pre_min)).isoformat(), fed_at=fed_at.isoformat(),
        feeding_offset_sec=cfg.pre_min * 60, feed_amount_g=100.0,
        feeding_duration_sec=cfg.feeding_duration_sec, data_source="synthetic",
        label=spec.scenario, events=event_log,
        residual_feed={"recovered": False, "dry_mass_g": None, "reason": "합성 세션"},
        synthetic={"generator": GENERATOR, "seed": seed, "scenario": spec.scenario, "split": spec.split,
                   "profile": asdict(profile), "noise": asdict(noise), "clipped_samples": clipped,
                   **spec.extra},
        notes="모크 데이터: 실제 새우 음향이 아님",
    )
    (d / "meta.json").write_text(meta.to_json(), encoding="utf-8")
    return {"session_id": spec.session_id, "tank": spec.tank, "noise_condition": spec.noise_condition,
            "day": spec.day, "scenario": spec.scenario, "split": spec.split, "n_clicks": len(clicks),
            **truth_summary(np.array([e.time_sec for e in clicks]), cfg), "clipped_samples": clipped}


def truth_summary(click_times_sec: np.ndarray, cfg: SynthConfig) -> dict:
    """정답 클릭으로 계산한 분당 클릭 수 요약(검산용)."""
    rel_min = click_times_sec / 60 - cfg.pre_min
    edges = np.arange(-cfg.pre_min, cfg.post_min + 1)
    cpm, _ = np.histogram(rel_min, bins=edges)
    post = cpm[int(cfg.pre_min):]
    return {"baseline_cpm": round(float(cpm[: int(cfg.pre_min)].mean()), 1),
            "peak_cpm": int(post.max()), "peak_min": int(post.argmax()),
            "auc10": int(post[:10].sum()), "auc30": int(post.sum())}


def standard_specs() -> list[SessionSpec]:
    """설계서 v2 배정(2조건 × 3수조 × 4일) + 시연용 정상·이상 1개씩."""
    specs = []
    for tank in TANK_SCALE:
        for day in range(1, 5):
            if tank.startswith("A"):
                split = "train" if day <= 3 else "val"
            else:
                split = "test_noise"
            date = (FIRST_DAY + timedelta(days=day - 1)).strftime("%Y-%m-%d")
            specs.append(SessionSpec(f"{date}_{tank}", tank, day, "normal", split))
    # 시연용: 운영 소음(B1)이 주 시나리오, 소음 차단(A1)은 비교용
    for tank in ("B1", "A1"):
        specs.append(SessionSpec(f"demo_normal_{tank}", tank, 5, "normal", "demo"))
        specs.append(SessionSpec(f"demo_abnormal_{tank}", tank, 5, "abnormal", "demo"))
    return specs


def write_tanks(out_root: Path) -> None:
    """수조 정보(tanks.json). 합성이므로 개체 정보는 자리표시 값."""
    tanks = {t: {"noise_condition": c, "shrimp_count": None, "mean_weight_g": None,
                 "feed_lot": None, "sensor_position": None, "synthetic_response_scale": TANK_SCALE[t]}
             for t, c in TANK_CONDITION.items()}
    (out_root / "tanks.json").write_text(json.dumps(tanks, ensure_ascii=False, indent=2), encoding="utf-8")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="모크 세션 합성")
    ap.add_argument("--clicks", required=True, help="클릭이 든 샘플 WAV (예: 01_sparse.wav)")
    ap.add_argument("--labels", required=True, help="샘플의 labels.csv")
    ap.add_argument("--out", required=True, help="출력 폴더 (예: data/synthetic/mock_v1)")
    ap.add_argument("--only", default=None, help="세션 ID 에 이 문자열이 든 것만 (예: demo)")
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--pre-min", type=float, default=SynthConfig.pre_min)
    ap.add_argument("--post-min", type=float, default=SynthConfig.post_min)
    a = ap.parse_args(argv)

    cfg = replace(SynthConfig(), pre_min=a.pre_min, post_min=a.post_min)
    bank, sr = load_click_bank(a.clicks, a.labels, cfg)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    write_tanks(out)
    specs = [s for s in standard_specs() if a.only is None or a.only in s.session_id]
    manifest_path = out / "manifest.csv"
    rows = []
    if manifest_path.exists():
        with open(manifest_path, encoding="utf-8") as f:
            rows = [r for r in csv.DictReader(f) if r["session_id"] not in {s.session_id for s in specs}]
    for s in specs:
        r = render_session(s, bank, sr, out, cfg, a.seed)
        rows.append(r)
        print(f"{r['session_id']:>20}  {r['split']:<10} clicks={r['n_clicks']:5d}  "
              f"peak={r['peak_cpm']:3d}@{r['peak_min']}분  auc10={r['auc10']:4d}  clip={r['clipped_samples']}")
    rows.sort(key=lambda r: r["session_id"])
    with open(manifest_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    (out / "README.md").write_text(
        f"# 모크 데이터셋 ({GENERATOR})\n\n"
        f"- 클릭 재료: `{Path(a.clicks).name}` 의 라벨된 클릭 {len(bank)}개 (최고점 정렬 템플릿)\n"
        f"- 샘플레이트 {sr} Hz, 급이 전 {cfg.pre_min:g}분 + 급이 후 {cfg.post_min:g}분, 시드 {a.seed}\n"
        "- **실제 새우 음향이 아님.** 파이프라인·시연·평가 검증용.\n"
        "- split: train/val = A 수조(소음 차단), test_noise = B 수조(운영 소음), demo = 시연용\n"
        "- 세션 폴더: audio.wav, clicks.csv(정답: 클릭 최고점 시각), distractors.csv(방해음), meta.json\n",
        encoding="utf-8")


if __name__ == "__main__":
    main()
