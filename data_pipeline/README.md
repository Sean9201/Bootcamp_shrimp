# data_pipeline

녹음 수집·정리·라벨링·합성 데이터·데이터셋 버전 관리. 작업 브랜치: `data_pipeline`
산출물(세션 폴더 형식)은 [`docs/interfaces.md`](../docs/interfaces.md) 1절을 따르고, `ai` 가 읽어 갑니다.

## 실행 (PowerShell, data_pipeline 폴더에서)

```powershell
..\..\.venv\Scripts\python.exe -m pip install -r requirements.txt
..\..\.venv\Scripts\python.exe -m pip install -e .
..\..\.venv\Scripts\python.exe -m pytest
```

## 모크 데이터 만들기 (실측 전, 중간발표용)

샘플 클릭음(`새우샘플링\01_sparse.wav` + `labels.csv`)의 라벨된 클릭 16개를 재료로 40분 세션을 합성한다.
**실제 새우 음향이 아니다.** 파이프라인·시연·평가 검증용.

```powershell
$s = "C:\Users\dudtj\OneDrive\바탕 화면\프로젝트\고급프로그래밍\데이터\새우샘플링"
..\..\.venv\Scripts\python.exe -m shrimp_data.synthetic --clicks "$s\01_sparse.wav" --labels "$s\labels.csv" --out data/synthetic/mock_v1
# 시연 파일 2개만: 뒤에 --only demo
```

- 세션당 약 15초, 230 MB (48 kHz 16-bit 40분). 전체 26개 ≈ 6 GB.
- 클릭 배치: 급이 반응 곡선(`ResponseProfile`)을 따르는 비균질 포아송 과정. 수조별 배율 + 일차별 변동 + 30초 단위 흔들림.
- 클릭 변형: 템플릿 무작위 선택, 길이·음높이 ±8%, 극성, 진폭 로그정규(약한 클릭 포함).
- 방해음: 공통 — 사료 입수음, 알갱이 충돌음(2–5 kHz). B(운영 소음) — 펌프 웅웅거림(60 Hz 배음), 에어레이션 쉿 소리(2–15 kHz), 기포 터짐(1–6 kHz), 장비 충격 2회.

| 세션 | 수조 | split | 용도 |
|---|---|---|---|
| `2026-10-24_A1` … `2026-10-26_A3` | A1–A3, 1–3일차 | train | 모델 A 학습, 정상 기준 |
| `2026-10-27_A1` … `_A3` | A1–A3, 4일차 | val | 모델 A 검증 |
| `2026-10-24_B1` … `2026-10-27_B3` | B1–B3, 1–4일차 | test_noise | 소음 강건성 시험 |
| `demo_normal_A1`, `demo_abnormal_A1` | A1, 5일차 | demo | 시연 (정상 기준에 쓰지 않음) |

시연 곡선은 화면 시안 수치에 맞췄다: 정상 Peak ≈ 100, 초기 10분 AUC ≈ 620, 반응 지연 ≈ 1.2분 / 이상 Peak ≈ 42, AUC ≈ 210, 지연 ≈ 3.5분.

## 구조

```
src/shrimp_data/
  session.py     세션 메타(meta.json) 형식·검증
  synthetic.py   모크 세션 합성
  (예정) ingest.py   원본 녹음 → 세션 폴더 정리
  (예정) labels.py   실측 클릭 라벨 가져오기·검수
data/            데이터 (git 제외, data/README.md 참고)
tests/
```

## 데이터셋 버전

| 버전 | 날짜 | 세션 수 | 변경 |
|---|---|---|---|
| mock_v1 | 2026-11-02 | 26 (정상 25 / 이상 1, 모두 합성) | 샘플 클릭 16개 기반 첫 모크 세트 |

## 할 일
- [ ] 원본 녹음 정리 규칙(파일명·메타) 확정과 `ingest.py`
- [ ] 클릭 라벨링 방식 결정 (도구, 허용오차, 약한 클릭 포함 여부)
- [x] 합성 데이터 생성기
