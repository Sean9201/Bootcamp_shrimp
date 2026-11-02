import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 백엔드 CORS 가 5500 만 허용하므로 개발·미리보기 모두 5500 고정
export default defineConfig({
  plugins: [react()],
  server: { port: 5500, strictPort: true },
  preview: { port: 5500, strictPort: true },
  test: { environment: "jsdom", include: ["src/**/*.test.{js,jsx}"] },
});
