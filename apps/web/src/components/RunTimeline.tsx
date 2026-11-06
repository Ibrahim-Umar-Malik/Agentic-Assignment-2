import { useState } from "react";
import { Link } from "react-router-dom";
import { useSSE } from "../lib/hooks";

type Ev = { type: string; node?: string; summary?: string; latency_s?: number; tokens?: number; model?: string; status?: string; error?: string };

const LABEL: Record<string, string> = {
  scout: "Scout", analyst: "Job Analyst", risk: "Risk Assessor", matcher: "Fit Matcher", decide: "Bid decision", pricing: "Pricing Strategist",
  writer: "Proposal Writer", verifier: "Claim verification", critic: "Critic", compliance: "Compliance Guard", preview: "Dry-run preview",
  approval: "Your approval", submit: "Submit", recheck: "Re-check edit", needs_attention: "Needs attention", context: "Context",
  intent: "Intent", liaison: "Client Liaison", send: "Send",
};

/** Live node-by-node progress streamed from LangGraph (SSE). */
export function RunTimeline({ runId, traceId }: { runId: string; traceId?: string | null }) {
  const [events, setEvents] = useState<Ev[]>([]);
  const [done, setDone] = useState<Ev | null>(null);
  useSSE(`/api/runs/${runId}/stream`, (type, data) => {
    if (type === "ping") return;
    if (type === "end") setDone(data as Ev);
    setEvents((xs) => [...xs, { ...(data as Ev), type }]);
  });
  const nodes = events.filter((e) => e.type === "node" || e.type === "interrupt");
  return (
    <div className="card" aria-live="polite">
      <div className="row spread">
        <h2 style={{ margin: 0 }}>Live progress</h2>
        {traceId && (
          <Link to={`/share/trace/${traceId}`} className="small">
            Full trace →
          </Link>
        )}
      </div>
      <ul className="timeline" data-testid="timeline">
        {nodes.map((e, i) => (
          <li key={i}>
            <span className={`dot ${!done && i === nodes.length - 1 ? "live" : ""}`} />
            <span>
              <strong>{e.type === "interrupt" ? "Waiting for your approval" : LABEL[e.node ?? ""] ?? e.node}</strong>
              {e.summary && <span className="muted"> · {e.summary}</span>}
            </span>
            <span className="small muted">
              {e.latency_s != null ? `${e.latency_s}s` : ""} {e.tokens ? `· ${e.tokens} tok` : ""} {e.model ? `· ${e.model}` : ""}
            </span>
          </li>
        ))}
        {!done && (
          <li>
            <span className="spinner" />
            <span className="muted">Working…</span>
            <span />
          </li>
        )}
      </ul>
      {done && (
        <p className="small">
          Finished: <strong>{done.status}</strong> {done.error && <span className="muted">({done.error})</span>}
        </p>
      )}
    </div>
  );
}
