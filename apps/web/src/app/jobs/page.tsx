import { Link, useParams } from "react-router-dom";
import { RunTimeline } from "../../components/RunTimeline";
import { ActionBadge, ErrorBox, FitBar, FlagBadge, Loading, StatusBadge } from "../../components/ui";
import { api, errorText, type JobDetail } from "../../lib/api/client";
import { money, useAsync } from "../../lib/hooks";

type Match = { requirement: string; coverage: string; evidence: { item_id: string; title?: string; type?: string; snippet?: string; outcome?: string }[] };

/** Job detail: JobSpec, risk report, requirement-to-evidence matrix, price rationale, bid-or-skip reasoning. */
export default function JobPage() {
  const { id = "" } = useParams();
  const { data, error, loading, reload } = useAsync(async () => {
    const { data, error } = await api.GET("/api/jobs/{job_id}", { params: { path: { job_id: id } } });
    if (error) throw new Error(errorText(error));
    return data as JobDetail;
  }, [id]);
  if (loading && !data) return <Loading />;
  if (error || !data) return <ErrorBox error={error ?? "not found"} retry={reload} />;
  const j = data.job as Record<string, any>;
  const spec = data.spec as Record<string, any> | null;
  const risk = data.risk as Record<string, any> | null;
  const fit = data.fit as { fit_score: number; matrix: Match[]; reasons: string[] } | null;
  const dec = data.decision as { action: string; reasons: string[] } | null;
  const price = data.price as Record<string, any> | null;
  const latest = data.runs?.[0] as { id: string; status: string; trace_id?: string } | undefined;
  const analyse = async () => {
    await api.POST("/api/jobs/{job_id}/analyze", { params: { path: { job_id: id } } });
    setTimeout(reload, 800);
  };
  return (
    <div className="stack">
      <div className="row spread">
        <h1 style={{ margin: 0 }}>{j.title}</h1>
        <div className="row">
          <ActionBadge action={dec?.action} />
          <StatusBadge status={data.status} />
          {data.approval_id && <Link className="btn primary" to={`/studio/${id}`}>Review draft</Link>}
          {!data.thread_id && <button className="btn" onClick={analyse}>Analyse now</button>}
        </div>
      </div>
      <div className="row small muted">
        <span>{j.category}</span>
        <span>{money(j.budget, j.budget_type)} budget</span>
        <span>{j.connects_cost} Connects</span>
        <span>client {j.client_id}</span>
      </div>
      {latest && latest.status === "running" && <RunTimeline runId={latest.id} traceId={latest.trace_id} />}
      <div className="grid two">
        <section className="card">
          <h2 style={{ marginTop: 0 }}>Job post <span className="badge plain">untrusted text</span></h2>
          <p style={{ whiteSpace: "pre-wrap" }}>{j.description}</p>
          {j.screening_questions?.length > 0 && (
            <>
              <h3>Screening questions</h3>
              <ul>{j.screening_questions.map((q: string) => <li key={q}>{q}</li>)}</ul>
            </>
          )}
        </section>
        <section className="card">
          <h2 style={{ marginTop: 0 }}>Bid or skip</h2>
          {dec ? (
            <>
              <p><ActionBadge action={dec.action} /> {dec.reasons.join("; ")}</p>
              <div className="row"><span>Fit</span><FitBar v={fit?.fit_score} /></div>
            </>
          ) : (
            <p className="muted">Not analysed yet.</p>
          )}
          {risk && (
            <>
              <h3>Risk report</h3>
              <p className="small">{risk.summary} (risk {Math.round(risk.risk_score * 100)}%, client quality {Math.round(risk.client_quality * 100)}%)</p>
              <div className="row">{risk.flags.map((f: { kind: string; evidence: string }, i: number) => (
                <span key={i} title={f.evidence}><FlagBadge flag={f.kind} /></span>
              ))}</div>
              {risk.injection_detected && <p className="small">The post contains instructions aimed at AI tools. GigBid removed them before drafting and did not follow them.</p>}
            </>
          )}
          {price && (
            <>
              <h3>Price</h3>
              <p><strong>{money(price.amount, price.budget_type)}</strong> <span className="small muted">{price.rationale}</span></p>
              <p className="small">Connects {price.connects_cost} (≈ ${price.connects_usd}) vs expected value ${price.expected_value_usd}: {price.worth_connects ? "worth it" : "not worth it"}</p>
            </>
          )}
        </section>
      </div>
      {spec && (
        <section className="card">
          <h2 style={{ marginTop: 0 }}>JobSpec</h2>
          <div className="grid three small">
            <div><strong>Deliverables</strong><ul>{spec.deliverables.map((d: string) => <li key={d}>{d}</li>)}</ul></div>
            <div><strong>Hidden needs</strong><ul>{spec.hidden_needs.map((d: string) => <li key={d}>{d}</li>)}</ul></div>
            <div><strong>Timeline</strong><p>{spec.timeline ?? "–"}</p></div>
          </div>
        </section>
      )}
      {fit && (
        <section className="card">
          <h2 style={{ marginTop: 0 }}>Requirement → evidence matrix</h2>
          <div className="table-wrap">
            <table>
              <thead><tr><th>Requirement</th><th>Coverage</th><th>Portfolio items that prove it</th></tr></thead>
              <tbody>
                {fit.matrix.map((m) => (
                  <tr key={m.requirement}>
                    <td>{m.requirement}</td>
                    <td><span className={`badge ${m.coverage === "full" ? "good" : m.coverage === "partial" ? "warn" : "bad"}`}>{m.coverage}</span></td>
                    <td className="small">
                      {m.evidence.length === 0 ? <span className="muted">No evidence: GigBid will not claim this.</span> :
                        m.evidence.map((e) => (
                          <div key={e.item_id} title={e.snippet}><span className="mono">{e.item_id}</span> {e.title && `· ${e.title}`} {e.outcome && <span className="badge plain">{e.outcome}</span>}</div>
                        ))}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
      <section className="card">
        <h2 style={{ marginTop: 0 }}>Agent runs</h2>
        {data.node_log.length > 0 && (
          <ul className="timeline">
            {data.node_log.map((n: Record<string, any>, i: number) => (
              <li key={i}><span className="dot" /><span><strong>{n.node}</strong> <span className="muted">{n.summary}</span></span><span className="small muted">{n.latency_s}s · {n.model}</span></li>
            ))}
          </ul>
        )}
        <div className="row small">
          {data.runs.map((r: Record<string, any>) => (
            <Link key={r.id} to={`/runs/${r.id}`}>run {r.id.slice(0, 6)} ({r.status})</Link>
          ))}
        </div>
      </section>
    </div>
  );
}
