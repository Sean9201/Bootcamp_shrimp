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

`meta.json` (초안)

```json
{
  "session_id": "2026-10-24_A_0900",
  "tank": "A",
  "recorded_at": "2026-10-24T08:50:00+09:00",
  "fed_at": "2026-10-24T09:00:00+09:00",
  "feeding_offset_sec": 600,
  "feed_amount_g": 120,
  "data_source": "real",
  "label": "normal",
  "notes": ""
}
```

- `data_source`: `real` | `synthetic`
- `label`: `normal` | `abnormal` | `unknown` | `null`

## 2. ai → backend : 분석 엔진 호출

- 미정. 초안: `shrimp_ai` 패키지의 `analyze(wav_path, feeding_offset_sec, baseline) -> AnalysisResult` (JSON 직렬화 가능).

## 3. backend → frontend : REST API

- 미정. 초안: `GET /health`, `POST /api/v1/analyses`(업로드, 202) → `GET /api/v1/analyses/{id}`(폴링) → `/timeseries`.
- 에러 형식: `{"error": {"code": "...", "message": "한국어 메시지", "details": ...}}`
