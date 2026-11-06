import type { ReactNode } from "react";

export const Loading = ({ label = "Loading…" }: { label?: string }) => (
  <div className="empty" role="status" aria-live="polite">
    <span className="spinner" /> {label}
  </div>
);
export const Empty = ({ children }: { children: ReactNode }) => <div className="empty">{children}</div>;
export const ErrorBox = ({ error, retry }: { error: string; retry?: () => void }) => (
  <div className="banner bad" role="alert">
    {error}{" "}
    {retry && (
      <button className="btn sm" onClick={retry}>
        Retry
      </button>
    )}
  </div>
);

const ACTION: Record<string, string> = { bid: "good", watch: "warn", skip: "plain" };
const STATUS: Record<string, string> = {
  awaiting_approval: "info", submitted: "good", skipped: "plain", watching: "warn", analysing: "info", queued: "plain",
  rejected: "plain", blocked: "bad", needs_attention: "bad", dead_letter: "bad", waiting_marketplace: "warn", approved: "good",
  running: "info", done: "good", sent: "good",
};
const FLAG_LABEL: Record<string, string> = {
  scam: "Scam", off_platform: "Off-platform", free_work: "Free work", contact_harvest: "Wants contact", advance_fee: "Fee scam",
  injection: "Injected text", unverified_payment: "Payment unverified", new_client: "New client", other: "Low rating",
};
const BAD_FLAGS = ["scam", "off_platform", "free_work", "contact_harvest", "advance_fee"];

export const ActionBadge = ({ action }: { action?: string | null }) =>
  action ? <span className={`badge ${ACTION[action] ?? "plain"}`}>{action === "bid" ? "Bid" : action === "watch" ? "Watch" : "Skip"}</span> : null;
export const StatusBadge = ({ status }: { status: string }) => (
  <span className={`badge ${STATUS[status] ?? "plain"}`}>{status.replace(/_/g, " ")}</span>
);
export const FlagBadge = ({ flag }: { flag: string }) => (
  <span className={`badge ${BAD_FLAGS.includes(flag) ? "bad" : "warn"}`}>{FLAG_LABEL[flag] ?? flag}</span>
);
export const FitBar = ({ v }: { v?: number | null }) => (
  <span className="row" style={{ gap: 6 }} aria-label={`fit ${Math.round((v ?? 0) * 100)} percent`}>
    <span className="fitbar">
      <span style={{ width: `${Math.round((v ?? 0) * 100)}%` }} />
    </span>
    <span className="small muted">{v == null ? "–" : `${Math.round(v * 100)}%`}</span>
  </span>
);
