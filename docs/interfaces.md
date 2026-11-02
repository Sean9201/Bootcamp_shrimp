# 영역 간 인터페이스

영역 사이에 주고받는 형식은 구현 전에 여기에 먼저 적는다. 형식이 바뀌면 이 문서를 같은 커밋에서 갱신한다.

## 1. data_pipeline → ai : 세션 데이터셋

세션 1개 = 녹음 1개 + 메타 1개 (+ 라벨 선택).

```
<dataset_root>/<session_id>/
  audio.wav            # 단일 채널 권장, 샘플레이트는 파일에서 읽는다
  meta.json            # 아래 형식
  clicks.csv           # (선택) 정답 클릭
  distractors.csv      # (선택, 합성 세션) 방해음 기록 — 오검출 분석용
<dataset_root>/tanks.json    # 수조 정보
<dataset_root>/manifest.csv  # 세션 목록·split·정답 곡선 요약
```

- `clicks.csv`: `time_sec,amp` — `time_sec` 은 **WAV 시작 기준, 클릭 파형의 최고점 시각(초)**. 평가는 ±5 ms 1:1 매칭.
  `amp` 는 최고 진폭(선택). 판별 불가 구간의 클릭은 넣지 않는다.
- `distractors.csv`: `time_sec,kind,amp` — `kind` ∈ `splash`(사료 입수) · `pellet`(알갱이 충돌) · `bubble`(기포) · `impact`(장비 충격).
- 합성 세션은 `meta.json` 의 `synthetic` 에 생성 조건(정답 곡선 파라미터, split, 시드)을 둔다.

`meta.json` (초안 v2 — 실험 설계서 v2 의 현장 기록 항목 반영, `docs/project-brief.md` 2절)

```json
{
  "session_id": "2026-10-24_A1",
  "tank": "A1",
  "noise_condition": "blocked",
  "day": 1,
  "recorded_at": "2026-10-24T08:50:00+09:00",
  "fed_at": "2026-10-24T09:00:00+09:00",
  "feeding_offset_sec": 600,
  "feed_amount_g": 120,
  "feeding_duration_sec": 20,
  "data_source": "real",
  "label": "normal",
  "water": {
    "start": {"temp_c": 28.1, "salinity_psu": 30.0, "do_mg_l": 6.2, "ph": 7.9},
    "end": {"temp_c": 28.0, "salinity_psu": 30.0, "do_mg_l": 5.8, "ph": 7.8}
  },
  "events": [{"time_sec": 1320, "note": "수조 벽 충격"}],
  "residual_feed": {"recovered": true, "dry_mass_g": 18.5, "reason": null},
  "notes": ""
}
```

- 필수: `session_id`, `tank`, `noise_condition`, `fed_at`, `feeding_offset_sec`. 나머지는 없으면 `null`.
- `tank`: `A1`–`A3`(조건 1), `B1`–`B3`(조건 2). 수조 정보(개체수·체중·사료 lot·센서 위치)는 별도 `tanks.json` 에 둔다.
- `noise_condition`: `blocked`(소음 차단) | `operating`(운영 소음)
- `day`: 측정 일차 1–4
- `events[].time_sec`: WAV 시작 기준 초
- `residual_feed`: 회수 실패면 `recovered: false` + `reason`. 0 으로 채우지 않는다.
- `data_source`: `real` | `synthetic`
- `label`: `normal` | `abnormal` | `unknown` | `null`

## 2. ai → backend : 스트리밍 분석 엔진

backend 는 `shrimp_ai` 를 패키지로 설치(`pip install -e ai`)해 쓴다. 모델 파일은 `ai/artifacts/`(git 제외).

```python
from shrimp_ai.anomaly import Baseline
from shrimp_ai.detect.candidates import StreamingCandidateDetector
from shrimp_ai.detect.cnn import ClickClassifier
from shrimp_ai.engine import StreamingAnalyzer
from shrimp_ai.sources import FileSource

clf = ClickClassifier.load("ai/artifacts/click_cnn.pt")
k = json.load(open("ai/artifacts/detector.json"))["candidate_k"]
base = Baseline.load(f"ai/artifacts/baselines/{tank}.json")      # 없으면 None → 점수 없이 G(t) 만
src = FileSource(wav_path, chunk_sec=1.0, speed=40)              # 실사용: LiveSource(1배)
eng = StreamingAnalyzer(src.sr, feeding_offset_sec, StreamingCandidateDetector(src.sr, k=k), clf, base)
for chunk in src:
    for ev in eng.feed(chunk): send(ev)        # 청크마다 이벤트(JSON 직렬화 가능 dict)
for ev in eng.finish(): send(ev)
```

이벤트 (`type` 으로 구분, 시각은 모두 **급이 기준**):

| type | 필드 | 언제 |
|---|---|---|
| `progress` | `t_sec` | 청크마다 (처리한 위치, 초) |
| `clicks` | `t: [초…]` | 이번 청크에서 확정된 클릭이 있을 때 |
| `minute` | `minute, cpm, mu, lo, hi` | 1분 구간이 끝날 때 (`minute` -10…29, 정상 범위 `lo`–`hi` 는 기준이 있을 때) |
| `score` | `minute, score, grade, raw_grade, z_auc, z_peak, z_onset, stage` | 급이 후 매 분. `stage`: `provisional` → `early`(10분) → `final`(30분) |
| `alert` | `minute, level, score, stage` | 등급이 올라갈 때 (`watch` / `alert`) |
| `final` | `metrics, counts, minutes, score, comparison, max_grade, n_clicks, compute_sec, baseline` | 마지막 1회 |

- `grade`: `normal` · `watch`(주의) · `alert`(경보). 등급은 2분 연속 기준 이상일 때만 오른다.
- `metrics`: `baseline_cpm, peak_cpm, peak_min, auc10, auc30, onset_min`
- `comparison`: 지표별 `{metric, normal_mean, normal_sd, current, change_pct}` — 화면 비교표와 LLM 입력에 그대로 쓴다.
- LLM(Gemini)에는 `final` 의 `metrics`·`comparison`·`score`·`alert` 기록만 보낸다(원본 음향·수조/시설 식별 정보 제외).

## 3. backend → frontend : REST API

기본 주소 `http://localhost:8000`. 자세한 입력·응답은 서버의 `/docs`, 설명은 `backend/README.md`.

| 메서드 | 경로 | 응답 |
|---|---|---|
| GET | `/health` | `{status, ai: {classifier, baselines[]}, llm: {provider, configured, model}}` |
| GET | `/api/v1/tanks` | `[{id, name, noise_condition, has_baseline}]` |
| GET | `/api/v1/samples` | `[{id, tank_id, noise_condition, label, feeding_offset_sec, fed_at, feed_amount_g, size_mb}]` |
| POST | `/api/v1/analyses` | multipart `file`(WAV), `tank_id`, `fed_at`?, `feeding_offset_sec`?(기본 600), `feed_amount_g`?, `speed`?(기본 40) → **202** 분석 요약 |
| POST | `/api/v1/analyses/from-sample` | JSON `{sample_id, speed?}` → **202** 분석 요약 |
| GET | `/api/v1/analyses?limit&tank_id` | 분석 요약 목록(최신순) |
| GET | `/api/v1/analyses/{id}` | 상세: 요약 + `baseline{minutes, mu, lo, hi, metrics}` + `minutes[]` + `scores[]` + `alerts[]` + `comparison[]` + `metrics` + `insight` |
| GET | `/api/v1/analyses/{id}/events` | **SSE**(text/event-stream), 줄마다 `data: {json}` |
| GET | `/api/v1/alerts?acknowledged` | 알림 목록 |
| POST | `/api/v1/alerts/{id}/ack` | 확인 처리된 알림 |
| GET | `/api/v1/model/report` | 모델 평가(모크)·학습 기록 |

분석 요약: `{id, tank_id, source(upload|sample), filename, status(queued|running|done|failed), speed, duration_sec,
fed_at, feed_amount_g, created_at, max_grade, final_score, peak_cpm, auc10, error}`. 시각은 모두 시간대 포함 ISO8601.

SSE 이벤트 순서: `meta` → (`progress`·`clicks`·`minute`·`score`·`alert` 반복) → `final` → `insight_pending` → `insight` → `done`.
실패하면 `error` 후 종료. 2절의 엔진 이벤트에 아래가 더해진다.

| type | 필드 |
|---|---|
| `meta` | `analysis_id, tank_id, noise_condition, speed, duration_sec, feeding_offset_sec, pre_min, post_min, thresholds{watch, alert, onset_sd_floor_min}, baseline(위 상세와 같음 또는 null), classifier` |
| `insight_pending` | — (LLM 응답 기다리는 중) |
| `insight` | `content{summary, bullets[], recommendation}, source(gemini|template), model, attempts, problems[], facts` |
| `done` / `error` | `analysis_id` / `message, detail` |
| `snapshot` | 서버 재시작 등으로 이벤트 기록이 없을 때 상세 응답 전체를 한 번에 |

- 처음 이벤트부터 다시 보내므로 화면은 언제 연결해도 그래프를 처음부터 그릴 수 있다.
- 에러 형식: `{"error": {"code": "...", "message": "한국어 메시지", "details": ...}}`
