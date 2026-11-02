# 영역 간 인터페이스

영역 사이에 주고받는 형식은 구현 전에 여기에 먼저 적는다. 형식이 바뀌면 이 문서를 같은 커밋에서 갱신한다.

## 1. data_pipeline → ai : 세션 데이터셋

세션 1개 = 녹음 1개 + 메타 1개 (+ 라벨 선택).

```
<dataset_root>/<session_id>/
  audio.wav            # 단일 채널 권장, 샘플레이트는 파일에서 읽는다
  meta.json            # 아래 형식
  clicks.csv           # (선택) 정답 클릭: time_sec[,confidence]
```

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

## 2. ai → backend : 분석 엔진 호출

- 미정. 초안: `shrimp_ai` 패키지의 `analyze(wav_path, feeding_offset_sec, baseline) -> AnalysisResult` (JSON 직렬화 가능).

## 3. backend → frontend : REST API

- 미정. 초안: `GET /health`, `POST /api/v1/analyses`(업로드, 202) → `GET /api/v1/analyses/{id}`(폴링) → `/timeseries`.
- 에러 형식: `{"error": {"code": "...", "message": "한국어 메시지", "details": ...}}`
