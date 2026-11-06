import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, errorText, getToken } from "../../lib/api/client";
import { useAuth } from "../../lib/auth";

/** Onboarding: persona or own profile, connect a marketplace, upload portfolio, rates, filters, Connects budget. */
export default function OnboardingPage() {
  const { user, refresh } = useAuth();
  const s = (user?.settings ?? {}) as Record<string, any>;
  const [persona, setPersona] = useState(user?.persona ?? "ai_ml");
  const [floor, setFloor] = useState<number>(s.hourly_floor ?? 40);
  const [budget, setBudget] = useState<number>(s.weekly_connects_budget ?? 60);
  const [hours, setHours] = useState<number>(s.hours_per_week ?? 20);
  const [query, setQuery] = useState("");
  const [uploaded, setUploaded] = useState<string[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const nav = useNavigate();

  const upload = async (f: File) => {
    const fd = new FormData();
    fd.append("file", f);
    const r = await fetch("/api/portfolio/upload", { method: "POST", body: fd, headers: { Authorization: `Bearer ${getToken() ?? ""}` } });
    if (r.ok) setUploaded((u) => [...u, f.name]);
    else setErr(`Upload failed: ${(await r.json()).detail}`);
  };
  const connectUpwork = async () => {
    const { data, error } = await api.GET("/api/connect/upwork/start");
    if (error) return setErr(errorText(error));
    window.location.href = (data as { authorize_url: string }).authorize_url;
  };
  const finish = async () => {
    const { error } = await api.PUT("/api/settings", {
      body: { persona: persona as "ai_ml", hourly_floor: floor, weekly_connects_budget: budget, hours_per_week: hours, onboarded: true },
    });
    if (error) return setErr(errorText(error));
    if (query.trim()) await api.POST("/api/searches", { body: { query, interval_min: 30 } });
    await api.POST("/api/scout/run");
    await refresh();
    nav("/inbox");
  };

  return (
    <div className="stack" style={{ maxWidth: 720 }}>
      <h1>Set up GigBid</h1>
      <section className="card">
        <h2 style={{ marginTop: 0 }}>1. Your profile</h2>
        <label htmlFor="ob-persona">Portfolio</label>
        <select id="ob-persona" value={persona} onChange={(e) => setPersona(e.target.value)}>
          <option value="ai_ml">Persona: AI/ML engineer</option>
          <option value="fullstack">Persona: full-stack web developer</option>
          <option value="data_analyst">Persona: data analyst</option>
        </select>
        <p className="small muted">Add your own work on top (Markdown, text or PDF case studies, or your CV). It is indexed only for you.</p>
        <input type="file" accept=".md,.txt,.pdf" aria-label="Upload portfolio file" onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} />
        {uploaded.length > 0 && <p className="small">Uploaded: {uploaded.join(", ")}</p>}
      </section>
      <section className="card">
        <h2 style={{ marginTop: 0 }}>2. Marketplace</h2>
        <p className="small">GigSim (simulator) is connected. Live Upwork uses Upwork's official MCP server with OAuth; every write is a draft you confirm on Upwork.</p>
        <div className="row">
          <span className="badge good">GigSim connected</span>
          <button className="btn sm" type="button" onClick={connectUpwork}>Connect Upwork (OAuth)</button>
        </div>
      </section>
      <section className="card">
        <h2 style={{ marginTop: 0 }}>3. Rates, filters and budget</h2>
        <div className="grid three">
          <div className="field">
            <label htmlFor="ob-floor">Hourly floor (USD)</label>
            <input id="ob-floor" type="number" min={0} value={floor} onChange={(e) => setFloor(Number(e.target.value))} />
          </div>
          <div className="field">
            <label htmlFor="ob-budget">Weekly Connects budget</label>
            <input id="ob-budget" type="number" min={0} value={budget} onChange={(e) => setBudget(Number(e.target.value))} />
          </div>
          <div className="field">
            <label htmlFor="ob-hours">Hours per week</label>
            <input id="ob-hours" type="number" min={1} max={80} value={hours} onChange={(e) => setHours(Number(e.target.value))} />
          </div>
        </div>
        <div className="field">
          <label htmlFor="ob-q">Extra saved search (optional)</label>
          <input id="ob-q" type="text" placeholder="e.g. LangGraph" value={query} onChange={(e) => setQuery(e.target.value)} />
        </div>
      </section>
      {err && <div className="banner bad" role="alert">{err}</div>}
      <button className="btn primary" onClick={finish} data-testid="finish-onboarding">
        Finish and find jobs
      </button>
    </div>
  );
}
