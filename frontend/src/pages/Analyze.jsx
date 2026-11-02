import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { getSamples, getTanks, startSample, uploadAnalysis } from "../api.js";
import { Card, ErrorBox } from "../components/Bits.jsx";
import { conditionLabel } from "../format.js";

const SPEEDS = [
  { v: 20, label: "20배속 (약 2분)" },
  { v: 40, label: "40배속 (약 1분) · 시연" },
  { v: 80, label: "80배속 (약 30초)" },
  { v: 0, label: "최대 속도" },
];

/** datetime-local 기본값: 지금(한국 시각) */
function nowLocal() {
  const d = new Date(Date.now() + 9 * 3600 * 1000);
  return d.toISOString().slice(0, 16);
}

export default function Analyze() {
  const nav = useNavigate();
  const [params] = useSearchParams();
  const [mode, setMode] = useState("sample");
  const [samples, setSamples] = useState([]);
  const [tanks, setTanks] = useState([]);
  const [sampleId, setSampleId] = useState("");
  const [speed, setSpeed] = useState(40);
  const [file, setFile] = useState(null);
  // 수조 현황·분석 화면에서 넘어오면 그 수조를 미리 고른다(?tank=B1)
  const [form, setForm] = useState({ tank_id: params.get("tank") || "B1", fed_at: nowLocal(), offset_min: 10, feed_amount_g: 100 });
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    getSamples().then((list) => {
      // 시연 순서: 운영 소음 먼저, 정상 → 이상
      const rank = (x) => (x.noise_condition === "operating" ? 0 : 2) + (x.label === "abnormal" ? 1 : 0);
      const s = [...list].sort((a, b) => rank(a) - rank(b));
      setSamples(s);
      setSampleId((cur) => cur || s[0]?.id || "");
    }).catch((e) => setErr(e.message));
    getTanks().then(setTanks).catch((e) => setErr(e.message));
  }, []);

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  async function start() {
    setErr(null);
    setBusy(true);
    try {
      let a;
      if (mode === "sample") {
        if (!sampleId) throw new Error("샘플을 고르세요.");
        a = await startSample(sampleId, speed);
      } else {
        if (!file) throw new Error("WAV 파일을 고르세요.");
        a = await uploadAnalysis(file, {
          tank_id: form.tank_id, fed_at: form.fed_at ? `${form.fed_at}:00+09:00` : "",
          feeding_offset_sec: Number(form.offset_min) * 60, feed_amount_g: form.feed_amount_g, speed,
        }, setProgress);
      }
      nav(`/analyses/${a.id}`);
    } catch (e) {
      setErr(e.message);
      setBusy(false);
      setProgress(null);
    }
  }

  return (
    <div className="page narrow">
      <div className="page-h">
        <div>
          <h1>급이 분석</h1>
          <p>급이 전 10분 ~ 급이 후 30분 수중 녹음(WAV)을 넣으면 클릭을 검출하고 같은 수조의 정상 반응과 비교합니다.</p>
        </div>
      </div>

      <div className="tabs" role="tablist">
        <button role="tab" aria-selected={mode === "sample"} className={mode === "sample" ? "on" : ""} onClick={() => setMode("sample")}>
          샘플 녹음 (시연)
        </button>
        <button role="tab" aria-selected={mode === "upload"} className={mode === "upload" ? "on" : ""} onClick={() => setMode("upload")}>
          파일 업로드
        </button>
      </div>

      {mode === "sample" ? (
        <Card title="① 녹음 고르기" right={<span className="muted small">합성 모크 데이터</span>}>
          <div className="samples">
            {samples.map((s) => (
              <label key={s.id} className={`sample ${sampleId === s.id ? "on" : ""}`}>
                <input type="radio" name="sample" value={s.id} checked={sampleId === s.id} onChange={() => setSampleId(s.id)} />
                <b>{conditionLabel(s.noise_condition)} · {s.label === "abnormal" ? "이상 예시" : "정상 예시"}</b>
                <span className="muted small">수조 {s.tank_id} · {s.id} · {s.size_mb} MB</span>
              </label>
            ))}
            {!samples.length && <p className="muted">샘플이 없습니다. data_pipeline 에서 모크 데이터를 먼저 만드세요.</p>}
          </div>
        </Card>
      ) : (
        <Card title="① 기본 정보와 파일">
          <div className="form">
            <label>수조
              <select value={form.tank_id} onChange={set("tank_id")}>
                {tanks.map((t) => (
                  <option key={t.id} value={t.id}>{t.name} ({conditionLabel(t.noise_condition)}){t.has_baseline ? "" : " · 기준 없음"}</option>
                ))}
              </select>
            </label>
            <label>급이 시각<input type="datetime-local" value={form.fed_at} onChange={set("fed_at")} /></label>
            <label>녹음 시작 후 급이까지 (분)<input type="number" min="0" step="0.5" value={form.offset_min} onChange={set("offset_min")} /></label>
            <label>급이량 (g)<input type="number" min="0" value={form.feed_amount_g} onChange={set("feed_amount_g")} /></label>
            <label className="drop">
              <input type="file" accept=".wav,audio/wav" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
              {file ? <span><b>{file.name}</b> · {(file.size / 1e6).toFixed(1)} MB</span> : <span>WAV 파일을 고르거나 여기로 끌어 놓으세요 (최대 600 MB)</span>}
            </label>
          </div>
        </Card>
      )}

      <Card title="② 재생 속도">
        <div className="speeds">
          {SPEEDS.map((s) => (
            <label key={s.v} className={`pill ${speed === s.v ? "on" : ""}`}>
              <input type="radio" name="speed" checked={speed === s.v} onChange={() => setSpeed(s.v)} />{s.label}
            </label>
          ))}
        </div>
        <p className="muted small">분석 방법은 실제 현장(하이드로폰 실시간 입력)과 같습니다. 녹음 파일을 정해진 배속으로 흘려 넣을 뿐입니다.</p>
      </Card>

      <ErrorBox message={err} />
      <div className="row end">
        {progress !== null && <span className="muted">업로드 {(progress * 100).toFixed(0)}%</span>}
        <button className="btn primary big" onClick={start} disabled={busy}>
          {busy ? "시작하는 중…" : "③ 분석 시작"}
        </button>
      </div>
    </div>
  );
}
