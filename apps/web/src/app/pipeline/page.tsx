import { Link } from "react-router-dom";
import { Empty, ErrorBox, Loading } from "../../components/ui";
import { api, errorText } from "../../lib/api/client";
import { money, useAsync, useSSE } from "../../lib/hooks";

type Card = { job_id: string; title?: string; stage: string; bid?: number; connects?: number; approval_id?: string; category?: string };

/** Kanban: drafted, submitted, viewed, replied, interview, hired, lost. Cards update from marketplace events. */
export default function PipelinePage() {
  const { data, error, loading, reload } = useAsync(async () => {
    const { data, error } = await api.GET("/api/pipeline");
    if (error) throw new Error(errorText(error));
    return data as { stages: string[]; columns: Record<string, Card[]> };
  });
  useSSE("/api/events", (type) => type === "run_finished" && void reload());
  const tick = async () => {
    await api.POST("/api/demo/tick");
    setTimeout(reload, 1200);
  };
  if (loading && !data) return <Loading />;
  if (error || !data) return <ErrorBox error={error ?? "error"} retry={reload} />;
  const total = Object.values(data.columns).reduce((n, c) => n + c.length, 0);
  return (
    <div className="stack">
      <div className="row spread">
        <h1 style={{ margin: 0 }}>Pipeline</h1>
        <div className="row">
          <button className="btn" onClick={() => api.POST("/api/messages/sync").then(() => setTimeout(reload, 1200))}>Sync marketplace</button>
          <button className="btn" onClick={tick} title="GigSim only: advance simulated time">Advance GigSim time</button>
        </div>
      </div>
      {total === 0 && <Empty>Nothing in the pipeline yet. Approve a proposal from the inbox to start.</Empty>}
      <div className="kanban" data-testid="kanban">
        {data.stages.map((s) => (
          <section className="col" key={s} aria-label={s}>
            <h3>{s} <span className="muted small">{data.columns[s]?.length ?? 0}</span></h3>
            {(data.columns[s] ?? []).map((c) => (
              <div className="kcard" key={c.job_id}>
                <Link to={c.approval_id ? `/studio/${c.job_id}` : `/jobs/${c.job_id}`}>{c.title ?? c.job_id}</Link>
                <div className="small muted">{money(c.bid)} {c.connects ? `· ${c.connects} Connects` : ""}</div>
              </div>
            ))}
          </section>
        ))}
      </div>
    </div>
  );
}
