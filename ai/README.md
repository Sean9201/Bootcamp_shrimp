# ai

클릭 검출(모델 A)·활동 지표·이상 탐지(모델 B)·평가. 작업 브랜치: `ai`
backend 는 이 폴더의 파이썬 패키지 `shrimp_ai` 를 가져다 씁니다.

## 실행 (PowerShell, ai 폴더에서)

```powershell
..\..\.venv\Scripts\python.exe -m pip install -r requirements.txt
..\..\.venv\Scripts\python.exe -m pytest
# backend 에서 쓰려면: ..\..\.venv\Scripts\python.exe -m pip install -e .
```

## 구조 (예정)

```
src/shrimp_ai/
  config.py      분석 파라미터 (대역·빈 크기·분석 창 — 하드코딩 금지)
  metrics.py     평가 지표 (클릭 매칭 F1, CPM MAE)
  detect/        클릭 검출기: 신호처리 Baseline → CNN (같은 인터페이스)
  activity.py    CPM 집계, 급이 정렬 G(t), Peak·AUC·onset
  anomaly.py     정상 기준(분 단위) 생성·비교 → 이상 점수·등급
notebooks/       실험 노트북 (출력은 지우고 커밋)
configs/         실험 설정
artifacts/       모델 가중치·기준 JSON (git 제외)
tests/
```

## 할 일
- [ ] 신호처리 Baseline 검출기와 평가 스크립트
- [ ] 활동 지표 · 정상 기준 · 이상 점수
- [ ] 실데이터 라벨이 모이면 CNN 검출기 (KPI: F1 ≥ 0.85, CPM MAE 20% 감소)
