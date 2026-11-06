import { useState } from "react";
import { Link } from "react-router-dom";
import { ActionBadge, Empty, ErrorBox, FitBar, FlagBadge, Loading, StatusBadge } from "../../components/ui";
import { api, errorText, type JobCard } from "../../lib/api/client";
import { money, useAsync, useSSE } from "../../lib/hooks";

/** Job inbox: new jobs ranked by fit with risk badges, recommended action, price and Connects cost. */
export default function InboxPage() {
  const [filter, setFilter] = useState<string>("");
  const [q, setQ] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const { data, error, loading, reload } = useAsync(async () => {
    const { data, error } = await api.GET("/api/jobs", { params: { query: { action: filter || undefined, q: q || undefined } } });
    if (error) throw new Error(errorText(error));
    return data as JobCard[];
  }, [filter, q]);
  useSSE("/api/events", (type) => {
    if (type === "run_finished") void reload();
  });
  const scout = async () => {
    setMsg("Scouting…");
    const { data } = await api.POST("/api/scout/run");
    setMsg(data?.status === "marketplace_unavailable" ? "Marketplace unavailable: will retry automatically." : `Scout: ${data?.detail ?? data?.status}`);
    void reload();
  };
  const skip = async (id: string) => {
    await api.POST("/api/jobs/{job_id}/skip", { params: { path: { job_id: id } } });
    void reload();
  };
  const pending = (data ?? []).filter((j) => j.has_approval).length;
  return (
    <div className="stack">
      <div className="row spread">
        <h1 style={{ margin: 0 }}>Job inbox</h1>
        <div className="row">
          <button className="btn" onClick={scout} data-testid="scout-now">Scout now</button>
        </div>
      </div>
      {msg && <div className="banner info" role="status">{msg}</div>}
      {pending > 0 && <div className="banner info">{pending} proposal draft(s) are waiting for your approval.</div>}
      <div className="row">
        <label className="sr-only" htmlFor="inbox-filter">Recommended action</label>
        <select id="inbox-filter" style={{ width: "auto" }} value={filter} onChange={(e) => setFilter(e.target.value)}>
          <option value="">All recommendations</option>
          <option value="bid">Bid</option>
          <option value="watch">Watch</option>
          <option value="skip">Skip</option>
        </select>
        <label className="sr-only" htmlFor="inbox-q">Search</label>
        <input id="inbox-q" type="text" style={{ maxWidth: 260 }} placeholder="Search titles" value={q} onChange={(e) => setQ(e.target.value)} />
      </div>
      {error && <ErrorBox error={error} retry={reload} />}
      {loading && !data ? (
        <Loading label="Loading jobs…" />
      ) : !data?.length ? (
        <Empty>No jobs yet. Press "Scout now" to run your saved searches.</Empty>
      ) : (
        <div className="card" style={{ padding: 0 }} data-testid="job-list">
          {data.map((j) => (
            <div className="job-row" key={j.job_id} data-testid="job-row">
              <div>
                <Link className="job-title" to={j.has_approval ? `/studio/${j.job_id}` : `/jobs/${j.job_id}`}>{j.title}</Link>
                <div className="row small muted" style={{ marginTop: 4 }}>
                  <span>{j.category}</span>
                  <span>{money(j.budget, j.budget_type)} budget</span>
                  <span>{j.connects ?? "–"} Connects</span>
                  {j.price != null && <span>suggested {money(j.price, j.budget_type)}</span>}
                </div>
                <div className="row" style={{ marginTop: 6, gap: 6 }}>
                  {j.risk_flags?.map((f) => <FlagBadge key={f} flag={f} />)}
                </div>
              </div>
              <div className="stack" style={{ textAlign: "right" }}>
                <div className="row" style={{ justifyContent: "flex-end" }}>
                  <ActionBadge action={j.action} />
                  <StatusBadge status={j.status} />
                </div>
                <FitBar v={j.fit} />
                <div className="row" style={{ justifyContent: "flex-end" }}>
                  {j.has_approval && <Link className="btn sm primary" to={`/studio/${j.job_id}`}>Review draft</Link>}
                  <Link className="btn sm" to={`/jobs/${j.job_id}`}>Open</Link>
                  {j.status !== "skipped" && !j.has_approval && (
                    <button className="btn sm" onClick={() => skip(j.job_id)}>Skip</button>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
