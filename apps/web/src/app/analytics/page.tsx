import { ErrorBox, Loading } from "../../components/ui";
import { api, errorText } from "../../lib/api/client";
import { pct, useAsync } from "../../lib/hooks";

type A = {
  funnel: Record<string, number>;
  by_category: { category: string; sent: number; reply_rate: number; hire_rate: number }[];
  connects: { spent: number; per_reply: number | null; weekly_budget: number | null };
  cost_latency: { runs: number; p50_latency_s: number | null; p95_latency_s: number | null; usd_total: number; usd_per_run: number | null; declared: Record<string, number> };
  top_rejection_reasons: { reason: string; count: number }[];
  top_skip_reasons: { reason: string; count: number }[];
};

export default function AnalyticsPage() {
  const { data, error, loading, reload } = useAsync(async () => {
    const { data, error } = await api.GET("/api/analytics");
    if (error) throw new Error(errorText(error));
    return data as A;
  });
  if (loading && !data) return <Loading />;
  if (error || !data) return <ErrorBox error={error ?? "error"} retry={reload} />;
  const f = data.funnel;
  const max = Math.max(1, ...Object.values(f));
  return (
    <div className="stack">
      <h1>Analytics</h1>
      <section className="card">
        <h2 style={{ marginTop: 0 }}>Funnel</h2>
        <div className="bars stack">
          {Object.entries(f).map(([k, v]) => (
            <div key={k} className="row" style={{ flexWrap: "nowrap" }}>
              <span style={{ width: 140 }} className="small">{k.replace("_", " ")}</span>
              <div className="bar" style={{ width: `${(v / max) * 60}%`, minWidth: 2 }} />
              <strong>{v}</strong>
            </div>
          ))}
        </div>
      </section>
      <div className="grid three">
        <section className="card"><div className="muted small">Connects spent</div><div className="kpi">{data.connects.spent}</div><div className="small muted">{data.connects.per_reply ?? "–"} per reply · budget {data.connects.weekly_budget}/week</div></section>
        <section className="card"><div className="muted small">p95 latency per job analysed</div><div className="kpi">{data.cost_latency.p95_latency_s ?? "–"}s</div><div className="small muted">declared {data.cost_latency.declared?.p95_latency_s_per_job_analysed}s · p50 {data.cost_latency.p50_latency_s ?? "–"}s</div></section>
        <section className="card"><div className="muted small">LLM cost</div><div className="kpi">${data.cost_latency.usd_total.toFixed(4)}</div><div className="small muted">${data.cost_latency.usd_per_run ?? 0} per run · declared ${data.cost_latency.declared?.usd_per_job_analysed}/job</div></section>
      </div>
      <section className="card table-wrap">
        <h2 style={{ marginTop: 0 }}>Reply and hire rate by category</h2>
        <table>
          <thead><tr><th>Category</th><th>Sent</th><th>Reply rate</th><th>Hire rate</th></tr></thead>
          <tbody>{data.by_category.map((c) => <tr key={c.category}><td>{c.category}</td><td>{c.sent}</td><td>{pct(c.reply_rate)}</td><td>{pct(c.hire_rate)}</td></tr>)}</tbody>
        </table>
      </section>
      <div className="grid two">
        <section className="card"><h2 style={{ marginTop: 0 }}>Top rejection reasons</h2>{data.top_rejection_reasons.length ? <ul>{data.top_rejection_reasons.map((r) => <li key={r.reason}>{r.reason} ({r.count})</li>)}</ul> : <p className="muted">None yet.</p>}</section>
        <section className="card"><h2 style={{ marginTop: 0 }}>Top skip reasons</h2>{data.top_skip_reasons.length ? <ul>{data.top_skip_reasons.map((r) => <li key={r.reason}>{r.reason} ({r.count})</li>)}</ul> : <p className="muted">None yet.</p>}</section>
      </div>
    </div>
  );
}
