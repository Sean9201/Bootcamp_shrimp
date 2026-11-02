// API 기본 주소. .env.local 의 VITE_API_BASE_URL 로 바꾼다.
export const API_BASE = (import.meta.env.VITE_API_BASE_URL || "http://localhost:8000").replace(/\/$/, "");

/** 백엔드 통일 에러 형식 {error:{message}} 를 읽어 Error 로 던진다 */
export async function request(path, options) {
  let res;
  try {
    res = await fetch(API_BASE + path, options);
  } catch {
    throw new Error("서버에 연결할 수 없습니다");
  }
  const body = await res.json().catch(() => null);
  if (!res.ok) throw new Error(body?.error?.message ?? `요청 실패 (HTTP ${res.status})`);
  return body;
}

export const getHealth = () => request("/health");
