# ai

클릭 검출(모델 A)·활동 지표·이상 탐지(모델 B)·평가. 작업 브랜치: `ai`
backend 는 이 폴더의 파이썬 패키지 `shrimp_ai` 를 가져다 씁니다.

## 실행 (PowerShell, ai 폴더에서)

```powershell
..\..\.venv\Scripts\python.exe -m pip install -r requirements.txt
..\..\.venv\Scripts\python.exe -m pip install -e .
..\..\.venv\Scripts\python.exe -m pytest

# 학습 (2단계 CNN + 신호처리 베이스라인 임계값) → artifacts/click_cnn.pt, detector.json
..\..\.venv\Scripts\python.exe -m shrimp_ai.train --data ..\data_pipeline\data\synthetic\mock_v1
# 평가 (모델 A·B, 수조별 정상 기준 생성, 시연 세션) → artifacts/eval_report.md, baselines/*.json
..\..\.venv\Scripts\python.exe -m shrimp_ai.evaluate --data ..\data_pipeline\data\synthetic\mock_v1
```

## 구조

```
청크(1초) ─► ① 후보 검출(신호처리) ─► ② CNN 판정 ─► 클릭 시각 ─► 분당 클릭 수 G(t) ─► 모델 B 점수·등급
```

```
src/shrimp_ai/
  config.py            모든 파라미터(대역·임계값·창·가중치). 하드코딩 금지
  sources.py           FileSource(배속 재생) / LiveSource(자리) — 실사용·시연은 이것만 다름
  detect/candidates.py 1단계: 대역통과 → 에너지 포락선 → 최근 5초 잡음 대비 임계값 → 최고점 → 불응기 병합
                       과거만 보고, 청크 크기와 무관하게 같은 결과. k 를 크게 주면 베이스라인 검출기
  detect/cnn.py        2단계: 후보 주변 32 ms 스펙트로그램(1–20 kHz) → 작은 CNN(약 2.4만 파라미터, GroupNorm)
  activity.py          G(t), Peak·초기 10분 AUC·30분 AUC·반응 시작·최고점 도달
  anomaly.py           모델 B: 수조별 정상 기준(분 단위 μ·σ, σ 하한) → 매 분 점수·등급(조기 경보)
  engine.py            StreamingAnalyzer: feed(chunk) → 이벤트(clicks/minute/score/alert/final)
  dataset.py           세션 폴더 읽기
  train.py, evaluate.py
artifacts/             가중치·기준·리포트 (git 제외)
```

### 데이터 사용 원칙
- 모델 A 학습: A 수조(소음 차단) 1–3일차, 검증: A 4일차. **B 수조(운영 소음)는 학습에 쓰지 않고 시험만** → 소음 강건성.
- 증강은 일반 백색 잡음과 ±1 ms 이동만. B 의 기포 소리는 학습 중에 보지 않는다.
- 정상 기준은 정답 클릭이 아니라 **모델 A 출력** G(t) 로 만든다(실사용과 같은 조건).
- 모델 B 평가: 수조 안에서 하루씩 빼고 기준을 만든 뒤 뺀 날로 오경보율, 그 날을 변형한 합성 이상(Peak 감소·지연·조기 감쇠)으로 탐지율.
- 현재 데이터는 모크(샘플 클릭 16개 기반)라 수치는 **파이프라인 검증용이며 실측 성능이 아니다.**

### 모델 B 점수
`Score = 0.5·max(0, −z_AUC) + 0.3·max(0, −z_peak) + 0.2·max(0, z_onset)` — 급이 후 0분부터 지금까지를 같은 경과 시간의 정상 기준과 비교.
주의 ≥ 1.25, 경보 ≥ 2.0, 급이 후 3분부터, **2분 연속** 기준 이상일 때만 등급이 오른다(일시적 흔들림 무시).
10분에 조기 판정, 30분에 확정. 값은 `AnomalyConfig`.

### 베이스라인 두 가지
- `baseline`: 신호처리만, A 검증 세션으로 임계값 선택 (CNN 과 같은 데이터 조건)
- `baseline_day1`: 신호처리만, 설계서 v2 **Day 1 게이트** — 두 조건의 1일차로 임계값을 정하고 2–4일차에 고정.
  B 소리를 본 베이스라인이므로 CNN 과의 공정 비교는 B 2–4일차(`B_day2_4`)에서 한다.
- 임계값은 F1 이 거의 평평할 때 극단값으로 가지 않도록 "최고 F1 에서 0.005 안쪽인 가장 작은 k".

## 할 일
- [x] 신호처리 베이스라인·2단계 CNN·스트리밍 엔진
- [x] 활동 지표 · 정상 기준 · 이상 점수
- [ ] 실측 데이터: Day 1 로 대역·임계값 재설정, 사람 라벨로 CNN 재학습
