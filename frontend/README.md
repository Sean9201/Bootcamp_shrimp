# frontend

관리자 웹 화면 (React 18 + Vite 5). 작업 브랜치: `frontend`
외부 CDN·웹폰트 없이 동작하게 만듭니다(발표장 오프라인 시연 대비).

## 실행 (PowerShell, frontend 폴더에서)

```powershell
npm ci                               # package-lock.json 기준 설치
npm run dev                          # http://localhost:5500 (포트 고정 — 백엔드 CORS)
npm test                             # Vitest
npm run build; npm run preview       # 시연용 빌드 확인
```

백엔드 주소는 `.env.example`을 `.env.local`로 복사해 `VITE_API_BASE_URL`로 바꿉니다.

## 구조 (예정)

```
src/
  api.js          fetch 래퍼(통일 에러 처리) → 이후 api/ 폴더로 엔드포인트별 분리
  pages/          대시보드 · 분석하기 · 결과 상세 · 분석 이력 · 알림 · 수조 관리 · 시스템 정보
  components/     레이아웃, 등급 배지, 진행 단계, G(t) 차트(Recharts)
  hooks/          분석 상태 폴링 등
  utils/          KST 시간 변환, 지표 포맷
```

## 할 일
- [ ] 백엔드 API 형식이 정해지면(`docs/interfaces.md` 3절) 화면 구현
- [ ] 라우팅(react-router-dom), 레이아웃
