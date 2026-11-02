# backend

REST API·DB·분석 실행 서버 (FastAPI). 작업 브랜치: `backend`

## 실행 (PowerShell, backend 폴더에서)

```powershell
..\..\.venv\Scripts\python.exe -m pip install -r requirements.txt
..\..\.venv\Scripts\python.exe -m pip install -e ..\ai            # 분석 엔진 shrimp_ai
copy .env.example .env                                             # Gemini 키 입력 (선택)
..\..\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000 # http://localhost:8000/docs
..\..\.venv\Scripts\python.exe -m pytest
```

필요한 것: `ai/artifacts/`(학습된 CNN·정상 기준 — `ai` 폴더에서 train/evaluate 실행), 시연 샘플은
`data_pipeline/data/synthetic/mock_v1/`. 없으면 기능을 줄여 동작한다(CNN 없음 → 후보 검출만, 기준 없음 → 점수 없음).

## 흐름

```
업로드(또는 샘플 선택) ─► 202 + 분석 ID ─► 분석 스레드: FileSource(배속) → StreamingAnalyzer
                                          │   이벤트를 메모리 기록 + DB(분·점수·알림) 저장
화면 ◄── SSE /analyses/{id}/events ◄──────┘   끝나면 인사이트(LangGraph: Gemini → 검증 → 재생성/템플릿)
```

- **배속**: 기본 40배(40분 녹음 → 약 60초). 0 이면 최대 속도. 분석 코드는 실사용과 같고 입력 소스만 다르다.
- **SSE**: 처음 이벤트부터 보내므로 늦게 연결해도 그래프가 빠짐없이 그려진다. 서버 재시작 후에는 DB 상세를 `snapshot` 하나로 보낸다.
- **인사이트**: Gemini 에는 집계 수치만 보낸다(원본 음향·파일명·수조 ID 제외). 원인·질병 단정 표현과 근거 없는 숫자는
  검증에서 걸러 1회 다시 생성하고, 그래도 안 되면 템플릿 문장. 키가 없어도 시연이 끊기지 않는다.
- **시간**: DB 는 UTC 로 저장, 응답은 시간대 포함 ISO8601. 시간대 없는 입력은 한국 시간으로 본다.
- **DB**: SQLite(`data/app.db`, WAL). 시작 시 테이블 생성 + 수조 A1–A3(소음 차단)·B1–B3(운영 소음) 기본 등록.
  표준 타입만 써서 `SHRIMP_DATABASE_URL` 로 PostgreSQL 전환 가능. 스키마가 굳으면 alembic 으로 옮긴다.

## API (`/docs` 에서 직접 시험 가능)

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/health` | 상태 + 분석 엔진(CNN·정상 기준)·LLM 준비 여부 |
| GET | `/api/v1/tanks` | 수조 목록, 정상 기준 유무 |
| GET | `/api/v1/samples` | 시연용 샘플 녹음 목록 |
| POST | `/api/v1/analyses` | WAV 업로드(multipart: `file`, `tank_id`, `fed_at`, `feeding_offset_sec`, `feed_amount_g`, `speed`) → 202 |
| POST | `/api/v1/analyses/from-sample` | `{"sample_id", "speed"}` → 202 (큰 파일 업로드 없이 시연) |
| GET | `/api/v1/analyses` | 분석 이력 |
| GET | `/api/v1/analyses/{id}` | 상세: 분 단위 곡선·정상 범위·점수·알림·비교표·인사이트 |
| GET | `/api/v1/analyses/{id}/events` | 진행 이벤트(SSE) — `docs/interfaces.md` 2·3절 |
| GET | `/api/v1/alerts` | 알림 목록(`acknowledged` 필터) |
| POST | `/api/v1/alerts/{id}/ack` | 알림 확인 |
| GET | `/api/v1/model/report` | 모델 평가 리포트·학습 기록(모크 데이터) |

에러는 모두 `{"error": {"code", "message"(한국어), "details"}}`.

## 구조

```
app/
  main.py               앱 팩토리, lifespan(DB·엔진·실행기 준비)
  core/config.py        설정 (SHRIMP_ 환경변수 / .env)
  core/errors.py        통일 에러 형식
  api/v1.py             라우터 — 입력 받기·서비스 호출·응답만
  services/analyses.py  업로드·샘플 → 분석 행 만들기, 응답 직렬화
  services/runner.py    분석 스레드: 엔진 실행, 이벤트 발행, DB 저장, 인사이트
  services/events.py    분석별 이벤트 기록(SSE 가 처음부터 읽음)
  services/insight.py   LangGraph 인사이트(생성 → 검증 → 재생성/템플릿), Gemini 호출
  services/ai_resources.py  CNN·임계값·정상 기준·평가 리포트 불러오기
  db/models.py, db/session.py
tests/
```

## 확인한 것 (모크 데이터, 실제 서버)
- `demo_abnormal_B1` 40배속: 총 60초. 급이 후 4분 경보가 화면 21초에, 10분 조기 판정 30초, 확정·인사이트 60초.
- `demo_normal_B1`: 끝까지 정상.
- 서버 안 분석 계산은 약 90배속(40배속 재생에 여유). 두 분석을 동시에 돌려도 40배속은 유지되지만 한 번에 하나를 권장.
