import { Link, useParams } from "react-router-dom";
import { ErrorBox, Loading } from "../../components/ui";
import { api, errorText } from "../../lib/api/client";
import { useAsync } from "../../lib/hooks";

type Span = { name: string; kind: string; start: number; end: number; attrs: Record<string, any> | null };

/** Public, read-only trace: every node, model call and tool call with tokens, cost and latency (PII masked). */
export default function SharedTracePage() {
  const { id = "" } = useParams();
  const { data, error } = useAsync(async () => {
    const { data, error } = await api.GET("/api/share/trace/{trace_id}", { params: { path: { trace_id: id } } });
    if (error) throw new Error(errorText(error));
    return data as { trace_id: string; spans: Span[]; totals: Record<string, number> };
  }, [id]);
  if (error) return <main><ErrorBox error={error} /></main>;
  if (!data) return <main><Loading /></main>;
  const t0 = Math.min(...data.spans.map((s) => s.start));
  const dur = Math.max(0.001, Math.max(...data.spans.map((s) => s.end)) - t0);
  return (
    <main style={{ margin: "0 auto" }}>
      <div className="row spread">
        <h1>Trace <span className="mono">{id.slice(0, 12)}</span></h1>
        <Link to="/inbox">GigBid</Link>
      </div>
      <div className="row small">
        <span>{data.totals.spans} spans</span><span>{data.totals.duration_s}s</span><span>{data.totals.tokens} tokens</span>
        <span>${data.totals.cost_usd}</span><span>{data.totals.tool_calls} tool calls</span>
      </div>
      <div className="card table-wrap" style={{ marginTop: 12 }}>
        <table>
          <thead><tr><th>Span</th><th>Kind</th><th style={{ width: "35%" }}>Timing</th><th>Details</th></tr></thead>
          <tbody>
            {data.spans.map((s, i) => (
              <tr key={i}>
                <td className="mono">{s.name}</td>
                <td><span className="badge plain">{s.kind}</span></td>
                <td>
                  <div style={{ position: "relative", height: 8, background: "var(--surface-2)", borderRadius: 4 }}>
                    <div style={{ position: "absolute", left: `${((s.start - t0) / dur) * 100}%`, width: `${Math.max(0.5, ((s.end - s.start) / dur) * 100)}%`, height: 8, background: s.attrs?.error ? "var(--bad)" : "var(--accent)", borderRadius: 4 }} />
                  </div>
                  <span className="small muted">{(s.end - s.start).toFixed(3)}s</span>
                </td>
                <td className="small mono" style={{ maxWidth: 380, wordBreak: "break-word" }}>
                  {s.attrs && Object.entries(s.attrs).filter(([k]) => !["output_keys"].includes(k)).map(([k, v]) => `${k}=${typeof v === "object" ? JSON.stringify(v).slice(0, 120) : v}`).join("  ")}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </main>
  );
}
