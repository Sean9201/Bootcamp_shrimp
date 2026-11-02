import { useEffect, useState } from "react";
import { API_BASE, getHealth } from "./api.js";

/** 초기 화면: 백엔드 연결 상태만 표시 (화면은 이후 단계에서 구현) */
export default function App() {
  const [state, setState] = useState({ text: "확인 중…", ok: null });
  useEffect(() => {
    getHealth()
      .then((h) => setState({ text: `서버 연결됨 (${h.status})`, ok: true }))
      .catch((e) => setState({ text: e.message, ok: false }));
  }, []);
  return (
    <main style={{ fontFamily: "Malgun Gothic, system-ui, sans-serif", padding: 32 }}>
      <h1>ShrimpCare</h1>
      <p>흰다리새우 섭식 활동 이상 탐지 및 조기 경보</p>
      <p style={{ color: state.ok === false ? "#b91c1c" : state.ok ? "#15803d" : "#6b7280" }}>
        {state.text} · {API_BASE}
      </p>
    </main>
  );
}
