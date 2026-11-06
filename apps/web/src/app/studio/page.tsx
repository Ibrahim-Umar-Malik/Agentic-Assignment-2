import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ApprovalPanel } from "../../components/ApprovalPanel";
import { Empty, ErrorBox, Loading, StatusBadge } from "../../components/ui";
import { api, errorText, type ApprovalOut } from "../../lib/api/client";
import { useAsync } from "../../lib/hooks";

/** Proposal studio for one job. The pending approval is loaded from the server, so a refresh never loses it. */
export default function StudioPage() {
  const { id = "" } = useParams();
  const [decided, setDecided] = useState<string | null>(null);
  const { data, error, loading, reload } = useAsync(async () => {
    const { data, error } = await api.GET("/api/approvals", { params: { query: { kind: "proposal" } } });
    if (error) throw new Error(errorText(error));
    return (data as ApprovalOut[]).find((a) => a.job_id === id) ?? null;
  }, [id, decided]);
  const job = useAsync(async () => (await api.GET("/api/jobs/{job_id}", { params: { path: { job_id: id } } })).data, [id, decided]);

  const after = (action: string) => {
    setDecided(action);
    // the graph resumes in the background; poll until the next state is visible
    let n = 0;
    const t = setInterval(() => {
      n += 1;
      void reload();
      void job.reload();
      if (n > 10) clearInterval(t);
    }, 900);
  };

  if (loading && !data && !decided) return <Loading label="Loading draft…" />;
  if (error) return <ErrorBox error={error} retry={reload} />;
  const status = job.data?.status;
  return (
    <div className="stack">
      <div className="row spread">
        <h1 style={{ margin: 0 }}>Proposal studio</h1>
        <Link to={`/jobs/${id}`}>Job details →</Link>
      </div>
      <p className="muted">{(job.data?.job as { title?: string } | undefined)?.title}</p>
      {decided && (
        <div className="banner info" role="status" data-testid="decision-status">
          Decision recorded ({decided}). {status && <>Current state: <StatusBadge status={status} /></>}
          {status === "submitted" && <> Submitted to the marketplace{(job.data?.submission as { connects_spent?: number })?.connects_spent ? ` (${(job.data?.submission as { connects_spent?: number }).connects_spent} Connects)` : ""}.</>}
          {status === "rejected" && <> Rejected; the reason is saved for analytics.</>}
        </div>
      )}
      {data ? (
        <ApprovalPanel key={data.id} approval={data} onDecided={after} />
      ) : (
        !decided && <Empty>No draft is waiting for approval on this job.</Empty>
      )}
    </div>
  );
}
