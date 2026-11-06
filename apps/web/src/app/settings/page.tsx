import { useState } from "react";
import { ErrorBox, Loading } from "../../components/ui";
import { api, errorText } from "../../lib/api/client";
import { useAuth } from "../../lib/auth";
import { useAsync } from "../../lib/hooks";

/** Autonomy, budgets, saved searches, connected accounts, portfolio items and the memory viewer. */
export default function SettingsPage() {
  const { user, refresh } = useAuth();
  const s = (user?.settings ?? {}) as Record<string, any>;
  const [autonomy, setAutonomy] = useState(s.autonomy ?? "suggest");
  const [floor, setFloor] = useState<number>(s.hourly_floor ?? 40);
  const [budget, setBudget] = useState<number>(s.weekly_connects_budget ?? 60);
  const [mode, setMode] = useState(s.marketplace ?? "gigsim");
  const [msg, setMsg] = useState<string | null>(null);
  const [newQ, setNewQ] = useState("");
  const searches = useAsync(async () => (await api.GET("/api/searches")).data ?? []);
  const memory = useAsync(async () => (await api.GET("/api/memory")).data ?? []);
  const portfolio = useAsync(async () => (await api.GET("/api/portfolio")).data ?? []);
  const conn = useAsync(async () => (await api.GET("/api/connect/status")).data as { upwork: boolean; mode: string });

  const save = async () => {
    const { error } = await api.PUT("/api/settings", { body: { autonomy, hourly_floor: floor, weekly_connects_budget: budget, marketplace: mode } });
    setMsg(error ? errorText(error) : "Saved.");
    await refresh();
  };
  if (!user) return <Loading />;
  return (
    <div className="stack" style={{ maxWidth: 900 }}>
      <h1>Settings</h1>
      {msg && <div className="banner info" role="status">{msg}</div>}
      <section className="card">
        <h2 style={{ marginTop: 0 }}>Autonomy and budgets</h2>
        <div className="grid three">
          <div className="field">
            <label htmlFor="autonomy">Autonomy</label>
            <select id="autonomy" value={autonomy} onChange={(e) => setAutonomy(e.target.value)}>
              <option value="suggest">Suggest only</option>
              <option value="auto_skip_low_fit">Auto-skip low-fit jobs</option>
            </select>
            <p className="small muted">GigBid never sends anything on its own, at any level.</p>
          </div>
          <div className="field">
            <label htmlFor="floor">Hourly floor (USD)</label>
            <input id="floor" type="number" value={floor} onChange={(e) => setFloor(Number(e.target.value))} />
          </div>
          <div className="field">
            <label htmlFor="budget">Weekly Connects budget</label>
            <input id="budget" type="number" value={budget} onChange={(e) => setBudget(Number(e.target.value))} />
          </div>
        </div>
        <div className="field">
          <label htmlFor="mode">Marketplace</label>
          <select id="mode" value={mode} onChange={(e) => setMode(e.target.value)} style={{ maxWidth: 320 }}>
            <option value="gigsim">GigSim (simulator)</option>
            <option value="upwork_live" disabled={!conn.data?.upwork}>Live Upwork {conn.data?.upwork ? "" : "(connect first)"}</option>
          </select>
        </div>
        <div className="row">
          <button className="btn primary" onClick={save}>Save settings</button>
          <button className="btn" onClick={async () => {
            const { data, error } = await api.GET("/api/connect/upwork/start");
            if (error) setMsg(errorText(error)); else window.location.href = (data as { authorize_url: string }).authorize_url;
          }}>{conn.data?.upwork ? "Reconnect Upwork" : "Connect Upwork (OAuth)"}</button>
        </div>
      </section>
      <section className="card">
        <h2 style={{ marginTop: 0 }}>Saved searches</h2>
        <ul>
          {(searches.data ?? []).map((q) => (
            <li key={q.id} className="row">
              <span>"{q.query}" every {q.interval_min} min</span>
              <button className="btn sm" onClick={async () => { await api.DELETE("/api/searches/{sid}", { params: { path: { sid: q.id } } }); void searches.reload(); }}>Remove</button>
            </li>
          ))}
        </ul>
        <div className="row">
          <label className="sr-only" htmlFor="newq">New search</label>
          <input id="newq" type="text" placeholder="keywords" value={newQ} onChange={(e) => setNewQ(e.target.value)} style={{ maxWidth: 260 }} />
          <button className="btn" disabled={!newQ.trim()} onClick={async () => { await api.POST("/api/searches", { body: { query: newQ, interval_min: 30 } }); setNewQ(""); void searches.reload(); }}>Add</button>
        </div>
      </section>
      <section className="card" data-testid="memory">
        <h2 style={{ marginTop: 0 }}>What GigBid has learned</h2>
        <p className="small muted">Only knowledge that passed a promotion rule appears here (style: the same edit in 2+ drafts; outcomes: 3+ results with a clear reply-rate gap). Delete anything you disagree with.</p>
        {memory.error && <ErrorBox error={memory.error} />}
        {(memory.data ?? []).length === 0 ? <p className="muted">Nothing learned yet.</p> : (
          <ul>
            {(memory.data ?? []).map((m) => (
              <li key={m.namespace.join("/") + m.key} className="row">
                <span className="badge plain">{m.namespace[0]}</span> <span>{m.rule ?? m.key}</span>
                <button className="btn sm danger" onClick={async () => {
                  await api.DELETE("/api/memory", { params: { query: { namespace: m.namespace.join("/"), key: m.key } } });
                  void memory.reload();
                }}>Delete</button>
              </li>
            ))}
          </ul>
        )}
      </section>
      <section className="card">
        <h2 style={{ marginTop: 0 }}>Portfolio evidence ({(portfolio.data ?? []).length})</h2>
        <p className="small muted">Hidden items can no longer back any claim; drafts that relied on them lose those claims when regenerated.</p>
        <div className="table-wrap" style={{ maxHeight: 360, overflowY: "auto" }}>
          <table>
            <thead><tr><th>Item</th><th>Type</th><th>Project</th><th /></tr></thead>
            <tbody>
              {(portfolio.data ?? []).map((p) => (
                <tr key={p.id}>
                  <td className="mono">{p.id}</td><td>{p.type}</td><td>{p.project}</td>
                  <td>
                    {p.deleted ? (
                      <button className="btn sm" onClick={async () => { await api.POST("/api/portfolio/{item_id}/restore", { params: { path: { item_id: p.id } } }); await refresh(); void portfolio.reload(); }}>Restore</button>
                    ) : (
                      <button className="btn sm danger" onClick={async () => { await api.DELETE("/api/portfolio/{item_id}", { params: { path: { item_id: p.id } } }); await refresh(); void portfolio.reload(); }}>Hide</button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
