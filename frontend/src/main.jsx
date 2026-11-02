import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
// 글꼴은 파일로 포함(발표장 오프라인 대비): 수조 이름·큰 숫자 = 검은고딕, 본문 = Gothic A1
import "@fontsource/black-han-sans/400.css";
import "@fontsource/gothic-a1/400.css";
import "@fontsource/gothic-a1/500.css";
import "@fontsource/gothic-a1/700.css";
import App from "./App.jsx";
import "./styles.css";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>,
);
