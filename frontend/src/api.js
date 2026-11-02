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

const json = (method, body) => ({ method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

export const getHealth = () => request("/health");
export const getTanks = () => request("/api/v1/tanks");
export const getSamples = () => request("/api/v1/samples");
export const getAnalyses = (limit = 50) => request(`/api/v1/analyses?limit=${limit}`);
export const getAnalysis = (id) => request(`/api/v1/analyses/${id}`);
export const getAlerts = (acknowledged) =>
  request(`/api/v1/alerts${acknowledged === undefined ? "" : `?acknowledged=${acknowledged}`}`);
export const ackAlert = (id) => request(`/api/v1/alerts/${id}/ack`, { method: "POST" });
export const getModelReport = () => request("/api/v1/model/report");
export const startSample = (sampleId, speed) => request("/api/v1/analyses/from-sample", json("POST", { sample_id: sampleId, speed }));
export const eventsUrl = (id) => `${API_BASE}/api/v1/analyses/${id}/events`;

/**
 * WAV 업로드(진행률 표시를 위해 XHR). fields: tank_id, fed_at, feeding_offset_sec, feed_amount_g, speed
 * onProgress(0..1)
 */
export function uploadAnalysis(file, fields, onProgress) {
  return new Promise((resolve, reject) => {
    const fd = new FormData();
    fd.append("file", file);
    for (const [k, v] of Object.entries(fields)) if (v !== "" && v !== null && v !== undefined) fd.append(k, v);
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_BASE}/api/v1/analyses`);
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress?.(e.loaded / e.total);
    xhr.onerror = () => reject(new Error("서버에 연결할 수 없습니다"));
    xhr.onload = () => {
      let body = null;
      try { body = JSON.parse(xhr.responseText); } catch { /* 빈 응답 */ }
      if (xhr.status >= 200 && xhr.status < 300) resolve(body);
      else reject(new Error(body?.error?.message ?? `업로드 실패 (HTTP ${xhr.status})`));
    };
    xhr.send(fd);
  });
}
