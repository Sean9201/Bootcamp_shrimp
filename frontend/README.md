# frontend

관리자 웹 화면 (React 18 + Vite 5 + Recharts). 작업 브랜치: `frontend`
외부 CDN·웹폰트 없이 동작한다(발표장 오프라인 시연 대비). 단, AI 인사이트(Gemini)는 백엔드가 인터넷을 쓴다 — 끊기면 템플릿 문장.

## 실행 (PowerShell, frontend 폴더에서)

```powershell
npm ci                               # package-lock.json 기준 설치
npm run dev                          # http://localhost:5500 (포트 고정 — 백엔드 CORS)
npm test                             # Vitest
npm run build; npm run preview       # 시연용 빌드 확인
```

백엔드(`http://localhost:8000`)가 먼저 떠 있어야 한다. 주소를 바꾸려면 `.env.example` 을 `.env.local` 로 복사해 `VITE_API_BASE_URL` 수정.

## 화면

| 경로 | 화면 | 내용 |
|---|---|---|
| `/` | 대시보드 | 수조 6개 최근 판정·정상 기준 유무, 확인하지 않은 알림, 최근 분석 |
| `/analyze` | 분석하기 | 샘플 녹음 선택(시연) 또는 WAV 업로드(진행률 표시) + 배속(20/40/80/최대) |
| `/analyses/:id` | 실시간 분석 | 아래 참고 |
| `/history` | 분석 이력 | 판정·Peak·AUC10 목록 |
| `/alerts` | 알림 내역 | 경보·주의 기록, 확인 처리 |
| `/model` | 모델 성능 | 클릭 검출 비교표, CNN 학습 곡선, 오경보율·합성 이상 탐지율, 재현성 (모크 데이터) |

### 실시간 분석 화면 (`/analyses/:id`)
- 진행 막대(급이 전 10분 + 급이 후 30분, 급이 표시) · 검출 클릭 수
- **경보 배너**: 등급이 오르는 순간 표시. "원인은 단정하지 않습니다" 문구 고정
- 지표 카드: 판정(잠정 → 10분 조기 → 30분 확정) · 현재 Peak · 초기 10분 AUC · 이상 점수(주의 1.25 / 경보 2.0)
- **G(t) 차트**: 정상 범위(μ±σ, 처음부터 회색 띠로) · 정상 평균(점선) · 현재 곡선(분마다 한 점씩) · 경보 지점 · 현재 위치선
- **클릭 검출 띠**: AI 가 확정한 클릭을 시간축에 눈금으로. 최근 1분은 진하게(관객이 "클릭을 잡고 있다"를 보게)
- 이상 점수 추이(주의·경보 기준선), 지표 비교표(30분 후), **AI 인사이트**(Gemini/템플릿 표시)

## 구조

```
src/
  api.js                 fetch 래퍼(통일 에러), 업로드(XHR 진행률), SSE 주소
  stream.js              SSE 이벤트 → 화면 상태(reducer), 80 ms 마다 모아서 그림, 끝나면 연결 닫음
  format.js              등급·조건 이름, 한국 시각, 급이 기준 시각 표시
  components/LiveChart.jsx  G(t) 차트 + 클릭 검출 띠(canvas, 차트와 가로 위치 맞춤)
  components/Bits.jsx    카드·배지·진행 막대·경보 배너·비교표·인사이트·점수 차트
  pages/                 Analyze, AnalysisView, Lists(대시보드·이력·알림), Model
```

- 재접속·새로고침: 서버가 처음 이벤트부터 다시 보내므로 상태를 초기화하고 다시 쌓는다(`meta` 이벤트에서 초기화).
- 끝난 분석을 다시 열면 저장된 이벤트를 한 번에 받아 바로 전체 그래프가 그려진다.
