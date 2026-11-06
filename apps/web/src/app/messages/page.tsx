import { useState } from "react";
import { Empty, ErrorBox, Loading } from "../../components/ui";
import { api, errorText } from "../../lib/api/client";
import { useAsync } from "../../lib/hooks";

type Msg = { id: string; sender?: string; from?: string; body: string };
type Row = {
  thread: { id: string; job_id?: string; messages: Msg[] };
  approval: { id: string; payload: Record<string, any> } | null;
};

function ThreadCard({ row, reload }: { row: Row; reload: () => void }) {
  const p = row.approval?.payload;
  const [body, setBody] = useState<string>(p?.reply?.body ?? "");
  const [slot, setSlot] = useState(0);
  const [busy, setBusy] = useState(false);
  const [reason, setReason] = useState("");
  const decide = async (action: "approve" | "edit" | "reject") => {
    if (!row.approval) return;
    setBusy(true);
    await api.POST("/api/approvals/{approval_id}/decide", {
      params: { path: { approval_id: row.approval.id } },
      body: action === "edit" ? { action, body } : action === "reject" ? { action, reason: reason || "not now" } : { action, slot },
    });
    setBusy(false);
    setTimeout(reload, 1200);
  };
  return (
    <section className="card stack" data-testid="thread">
      <div className="row spread">
        <strong>Thread {row.thread.id}</strong>
        <span className="small muted">job {row.thread.job_id}</span>
      </div>
      <div className="stack">
        {row.thread.messages.map((m) => (
          <div key={m.id} className={`para ${(m.sender ?? m.from) === "client" ? "" : "muted"}`}>
            <span className="badge plain">{(m.sender ?? m.from) === "client" ? "Client" : "You"}</span> {m.body}
          </div>
        ))}
      </div>
      {p && (
        <div className="stack">
          <div className="row">
            <span className={`badge ${p.intent?.intent === "scam_signal" ? "bad" : "info"}`}>{p.intent?.intent?.replace("_", " ")}</span>
            <span className="small muted">{p.intent?.summary}</span>
          </div>
          {p.compliance?.violations?.length > 0 && (
            <div className="comment">Compliance: {p.compliance.violations.map((v: { rule_id: string; detail: string }) => `${v.rule_id} ${v.detail}`).join("; ")}</div>
          )}
          <label htmlFor={`reply-${row.thread.id}`}>Suggested reply (edit before approving if you like)</label>
          <textarea id={`reply-${row.thread.id}`} style={{ minHeight: 110 }} value={body} onChange={(e) => setBody(e.target.value)} />
          {p.slots?.length > 0 && (
            <fieldset className="row" style={{ border: 0, padding: 0 }}>
              <legend className="small">Interview slot to hold (tentative) if the client accepts:</legend>
              {p.slots.map((s: { start: string }, i: number) => (
                <label key={s.start} className="row small" style={{ fontWeight: 400 }}>
                  <input type="radio" name={`slot-${row.thread.id}`} checked={slot === i} onChange={() => setSlot(i)} /> {new Date(s.start).toLocaleString()}
                </label>
              ))}
            </fieldset>
          )}
          <div className="row">
            <button className="btn primary" disabled={busy || body !== p.reply?.body} onClick={() => decide("approve")}>Approve and send</button>
            <button className="btn" disabled={busy || body === p.reply?.body} onClick={() => decide("edit")}>Save edit and re-check</button>
            <input type="text" aria-label="Reason to reject" placeholder="reason" style={{ maxWidth: 180 }} value={reason} onChange={(e) => setReason(e.target.value)} />
            <button className="btn danger" disabled={busy} onClick={() => decide("reject")}>Reject</button>
          </div>
        </div>
      )}
    </section>
  );
}

/** Client threads with suggested replies and interview slots; nothing is sent before approval. */
export default function MessagesPage() {
  const { data, error, loading, reload } = useAsync(async () => {
    const { data, error } = await api.GET("/api/messages");
    if (error) throw new Error(errorText(error));
    return data as { threads: Row[]; marketplace_available: boolean };
  });
  if (loading && !data) return <Loading />;
  if (error || !data) return <ErrorBox error={error ?? "error"} retry={reload} />;
  return (
    <div className="stack">
      <div className="row spread">
        <h1 style={{ margin: 0 }}>Messages</h1>
        <button className="btn" onClick={() => api.POST("/api/messages/sync").then(() => setTimeout(reload, 1500))}>Check for new messages</button>
      </div>
      {!data.marketplace_available && <div className="banner warn">Marketplace unavailable: showing nothing new until it is back.</div>}
      {data.threads.length === 0 ? <Empty>No client conversations yet.</Empty> : data.threads.map((r) => <ThreadCard key={r.thread.id + (r.approval?.id ?? "")} row={r} reload={reload} />)}
    </div>
  );
}
