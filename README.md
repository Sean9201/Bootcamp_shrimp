# Bootcamp_shrimp

흰다리새우 섭식 활동 이상 탐지 및 조기 경보 시스템 (PKNU AI 부트캠프, 개인 작업 저장소)

> 하이드로폰 녹음 → 클릭 검출 → 분당 클릭 수 G(t) → 정상 기준과 비교한 이상 점수 → 관리자 점검 알림

## 구성

| 폴더 | 담당 브랜치 | 내용 |
|---|---|---|
| [`frontend/`](frontend/) | `frontend` | 관리자 웹 화면 (React + Vite) |
| [`backend/`](backend/) | `backend` | REST API·DB·분석 실행 (FastAPI) |
| [`ai/`](ai/) | `ai` | 클릭 검출(모델 A)·이상 탐지(모델 B)·평가 |
| [`data_pipeline/`](data_pipeline/) | `data_pipeline` | 녹음 수집·정리·라벨링·합성 데이터·데이터셋 버전 관리 |
| [`docs/`](docs/) | `main` | 아키텍처·결정 기록 |

## 브랜치 전략

```
main ─────────────●──────────────●──────────────●────────▶  (항상 동작하는 통합본)
                 ╱              ╱              ╱
frontend ──●──●─╯   backend ──●╯   ai ──●──●─╯   data_pipeline ──●──▶
```

- `main`: 통합본. 각 영역 브랜치에서 작업이 한 단위로 끝나면 `main`으로 병합합니다.
- 영역 브랜치(`frontend`, `backend`, `ai`, `data_pipeline`): 해당 폴더만 수정합니다. 다른 영역을 바꿔야 하면 그 영역 브랜치에서 작업합니다.
- 다른 영역의 최신 변경이 필요하면 `main`을 영역 브랜치로 병합해 따라잡습니다 (`git merge main`).
- 큰 기능은 영역 브랜치에서 다시 갈라 작업해도 됩니다 (예: `backend/upload-api` → `backend`).
- 커밋 접두어: `feat:` `fix:` `test:` `docs:` `refactor:` `chore:`

```bash
git switch backend          # 백엔드 작업 시작
git merge main              # 다른 영역 변경 따라잡기
# … 작업·커밋 …
git switch main && git merge --no-ff backend   # 한 단위 끝나면 통합
```

## 영역 간 약속

- **데이터 흐름**: `data_pipeline` → (정리된 WAV·메타·라벨) → `ai` → (학습된 모델·기준) → `backend` → (REST API) → `frontend`
- **인터페이스 문서**: 영역 사이에 주고받는 형식은 [`docs/interfaces.md`](docs/interfaces.md)에 먼저 적고 구현합니다.
- **원본 음향·시설 정보는 외부 API(LLM 등)로 보내지 않습니다.**
- 녹음 파일·데이터셋·모델 가중치는 git에 올리지 않습니다 (`.gitignore`). 위치와 버전은 문서로 관리합니다.

각 폴더의 README에 실행 방법이 있습니다.
