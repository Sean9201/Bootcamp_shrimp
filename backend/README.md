# backend

REST API·DB·분석 실행 서버 (FastAPI). 작업 브랜치: `backend`

## 실행 (PowerShell, backend 폴더에서)

```powershell
..\..\.venv\Scripts\python.exe -m pip install -r requirements.txt
..\..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload   # http://localhost:8000/docs
..\..\.venv\Scripts\python.exe -m pytest
```

설정은 `SHRIMP_` 접두어 환경변수나 `backend/.env`로 바꿉니다(`app/core/config.py`).

## 구조 (예정)

```
app/
  main.py          앱 팩토리, 라우터 등록
  core/config.py   설정 (매직넘버 금지)
  api/v1/          라우터 — 로직 없이 서비스 호출만
  services/        업무 로직 (업로드·분석 실행·기준·알림)
  db/              SQLAlchemy 모델·세션, alembic
  schemas/         요청/응답 모델
tests/
```

## 할 일
- [ ] DB 모델·마이그레이션 (수조, 급이 이벤트, 녹음, 분석, 결과, 알림, 정상 기준)
- [ ] 업로드 → 비동기 분석 → 결과 저장 흐름 (`ai` 패키지 호출)
- [ ] API 형식을 `docs/interfaces.md` 3절에 확정
