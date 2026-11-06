import { Link, useParams } from "react-router-dom";
import { RunTimeline } from "../../components/RunTimeline";
import { Empty, ErrorBox, Loading, StatusBadge } from "../../components/ui";
import { api, errorText, type RunOut } from "../../lib/api/client";
import { ago, useAsync, useSSE } from "../../lib/hooks";

export default function RunsPage() {
  const { data, error, loading, reload } = useAsync(async () => {
    const { data, error } = await api.GET("/api/runs");
    if (error) throw new Error(errorText(error));
    return data as RunOut[];
  });
  useSSE("/api/events", (type) => (type === "run_started" || type === "run_finished") && void reload());
  if (loading && !data) return <Loading />;
  if (error) return <ErrorBox error={error} retry={reload} />;
  return (
    <div className="stack">
      <h1>Agent runs</h1>
      {!data?.length ? (
        <Empty>No runs yet.</Empty>
      ) : (
        <div className="card table-wrap">
          <table>
            <thead><tr><th>Run</th><th>Graph</th><th>Job</th><th>Status</th><th>Started</th><th>Tokens</th><th>Cost</th></tr></thead>
            <tbody>
              {data.map((r) => (
                <tr key={r.id}>
                  <td><Link to={`/runs/${r.id}`} className="mono">{r.id.slice(0, 8)}</Link></td>
                  <td>{r.graph}</td>
                  <td>{r.job_id && <Link to={`/jobs/${r.job_id}`}>{r.job_id}</Link>}</td>
                  <td><StatusBadge status={r.status} /></td>
                  <td className="small">{ago(r.started_at)}</td>
                  <td>{r.tokens ?? 0}</td>
                  <td>${(r.cost_usd ?? 0).toFixed(4)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

/** One run: live node-by-node progress, then the full trace. */
export function RunPage() {
  const { id = "" } = useParams();
  const { data, error } = useAsync(async () => {
    const { data, error } = await api.GET("/api/runs/{run_id}", { params: { path: { run_id: id } } });
    if (error) throw new Error(errorText(error));
    return data as RunOut;
  }, [id]);
  if (error) return <ErrorBox error={error} />;
  if (!data) return <Loading />;
  return (
    <div className="stack">
      <h1>Run {id.slice(0, 8)}</h1>
      <div className="row small">
        <StatusBadge status={data.status} /> <span>{data.graph} graph</span>
        {data.job_id && <Link to={`/jobs/${data.job_id}`}>job {data.job_id}</Link>}
        {data.trace_id && <Link to={`/share/trace/${data.trace_id}`}>trace</Link>}
      </div>
      <RunTimeline runId={id} traceId={data.trace_id} />
    </div>
  );
}
