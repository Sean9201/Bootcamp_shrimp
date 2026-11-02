# data_pipeline

녹음 수집·정리·라벨링·합성 데이터·데이터셋 버전 관리. 작업 브랜치: `data_pipeline`
산출물(세션 폴더 형식)은 [`docs/interfaces.md`](../docs/interfaces.md) 1절을 따르고, `ai` 가 읽어 갑니다.

## 실행 (PowerShell, data_pipeline 폴더에서)

```powershell
..\..\.venv\Scripts\python.exe -m pip install -r requirements.txt
..\..\.venv\Scripts\python.exe -m pytest
```

## 구조 (예정)

```
src/shrimp_data/
  session.py     세션 메타(meta.json) 형식·검증
  ingest.py      원본 녹음 → 세션 폴더 정리 (이름 규칙, 메타 생성)
  labels.py      클릭 라벨(clicks.csv) 가져오기·검수
  synthetic.py   합성 세션 생성
  splits.py      학습/검증/테스트 분할 (수조·날짜 단위로 섞이지 않게)
data/            실제 데이터 (git 제외, data/README.md 참고)
tests/
```

## 데이터셋 버전

| 버전 | 날짜 | 세션 수 (정상/이상) | 변경 |
|---|---|---|---|
| — | — | — | 아직 없음 |

## 할 일
- [ ] 원본 녹음 정리 규칙(파일명·메타) 확정과 `ingest.py`
- [ ] 클릭 라벨링 방식 결정 (도구, 허용오차, 약한 클릭 포함 여부)
- [ ] 합성 데이터 생성기
