import { useState } from "react";
import { api, errorText, type ApprovalOut, type DecisionIn } from "../lib/api/client";
import { money } from "../lib/hooks";
import { Paragraph, type Claim, type Ev } from "./EvidenceHover";

type Draft = { cover_letter: string; screening_answers?: { question: string; answer: string }[]; claims?: Claim[]; version?: number };
type Issue = { kind: string; detail: string; paragraph?: number | null };
type Violation = { rule_id: string; detail: string; action: string };

/** Proposal studio: every claim shows its evidence; critic and compliance comments inline; approve / edit / reject,
 * regenerate one paragraph; the dry-run preview shows exactly what will be sent and what it costs. */
export function ApprovalPanel({ approval, onDecided }: { approval: ApprovalOut; onDecided: (action: string) => void }) {
  const p = approval.payload as Record<string, any>;
  const draft = p.draft as Draft;
  const evidence = (p.evidence ?? []) as Ev[];
  const critique = ((p.critiques ?? []) as { score: number; approve: boolean; issues: Issue[] }[]).at(-1);
  const compliance = p.compliance as { status: string; violations: Violation[]; policy_version?: number } | undefined;
  const preview = p.preview as { would_send?: { cover_letter: string; bid_amount: number }; connects_cost?: number; connects_balance_after?: number; marketplace?: string };
  const price = p.price as { amount: number; budget_type: string; rationale: string; connects_cost: number; worth_connects: boolean } | undefined;
  const verification = p.verification as { unsupported_before?: number; unsupported_after?: number; n_claims?: number } | undefined;
  const blocked = !!p.blocked;

  const [mode, setMode] = useState<"view" | "edit" | "reject">("view");
  const [text, setText] = useState(draft.cover_letter);
  const [answers, setAnswers] = useState(draft.screening_answers ?? []);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const decide = async (body: DecisionIn) => {
    setBusy(true);
    setErr(null);
    const { error } = await api.POST("/api/approvals/{approval_id}/decide", { params: { path: { approval_id: approval.id } }, body });
    setBusy(false);
    if (error) setErr(errorText(error));
    else onDecided(body.action);
  };

  const paragraphs = draft.cover_letter.split("\n\n");
  const claims = draft.claims ?? [];
  return (
    <div className="grid two" data-testid="approval-panel">
      <section className="card stack" aria-label="Draft">
        <div className="row spread">
          <h2 style={{ margin: 0 }}>Cover letter {draft.version ? <span className="muted small">v{draft.version}</span> : null}</h2>
          <span className="small muted">{draft.cover_letter.split(/\s+/).length} words</span>
        </div>
        {blocked && (
          <div className="banner bad" role="alert" data-testid="blocked">
            <strong>Blocked by the Compliance Guard.</strong> Edit the draft to fix:{" "}
            {compliance?.violations.filter((v) => v.action === "block").map((v) => `${v.rule_id} ${v.detail}`).join("; ")}
          </div>
        )}
        {mode === "edit" ? (
          <>
            <label htmlFor="draft-text">Edit the letter (your edits are diffed, re-checked by Compliance and may teach style memory)</label>
            <textarea id="draft-text" value={text} onChange={(e) => setText(e.target.value)} data-testid="draft-editor" />
            {answers.map((a, i) => (
              <div className="field" key={i}>
                <label htmlFor={`ans-${i}`}>{a.question}</label>
                <textarea
                  id={`ans-${i}`}
                  style={{ minHeight: 80 }}
                  value={a.answer}
                  onChange={(e) => setAnswers(answers.map((x, j) => (j === i ? { ...x, answer: e.target.value } : x)))}
                />
              </div>
            ))}
          </>
        ) : (
          <div data-testid="draft-view">
            {paragraphs.map((para, i) => (
              <div className="para" key={i}>
                <span className="para-tools">
                  <button
                    className="btn sm"
                    disabled={busy}
                    title="Rewrite just this paragraph"
                    onClick={() => decide({ action: "regenerate", paragraph: i, instruction: "more specific to this client" })}
                  >
                    Regenerate
                  </button>
                </span>
                <Paragraph text={para} claims={claims} evidence={evidence} />
                {critique?.issues
                  .filter((x) => x.paragraph === i)
                  .map((x, k) => (
                    <div className="comment" key={k}>
                      Critic · {x.kind}: {x.detail}
                    </div>
                  ))}
              </div>
            ))}
            {answers.length > 0 && <h3>Screening answers</h3>}
            {answers.map((a, i) => (
              <div key={i} className="para">
                <div className="small muted">{a.question}</div>
                {a.answer}
              </div>
            ))}
          </div>
        )}
        <div>
          {critique && (
            <div className={`comment ${critique.approve ? "good" : ""}`}>
              Critic score {Math.round(critique.score * 100)}%{critique.approve ? " · approved" : ""}
              {critique.issues.filter((x) => x.paragraph == null).map((x) => ` · ${x.kind}: ${x.detail}`).join("")}
            </div>
          )}
          {compliance && compliance.violations.length > 0 && (
            <div className={`comment ${compliance.status === "block" ? "bad" : ""}`}>
              Compliance ({compliance.status}): {compliance.violations.map((v) => `${v.rule_id} ${v.detail} [${v.action}]`).join("; ")}
            </div>
          )}
          {compliance && compliance.violations.length === 0 && <div className="comment good">Compliance: passes policy pack v{compliance.policy_version}</div>}
          {verification && (
            <div className="small muted">
              Claim check: {verification.n_claims ?? 0} claims, unsupported {verification.unsupported_before ?? 0} → {verification.unsupported_after ?? 0} after verification
            </div>
          )}
        </div>
        {err && <div className="banner bad" role="alert">{err}</div>}
        {mode === "reject" && (
          <div className="field">
            <label htmlFor="reason">Why reject? (feeds analytics)</label>
            <input id="reason" type="text" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. rate too low" />
          </div>
        )}
        <div className="row">
          {mode === "view" && (
            <>
              <button className="btn primary" disabled={busy || blocked} onClick={() => decide({ action: "approve" })} data-testid="approve">
                Approve and submit
              </button>
              <button className="btn" disabled={busy} onClick={() => setMode("edit")} data-testid="edit">
                Edit
              </button>
              <button className="btn danger" disabled={busy} onClick={() => setMode("reject")} data-testid="reject">
                Reject
              </button>
            </>
          )}
          {mode === "edit" && (
            <>
              <button className="btn primary" disabled={busy || text.trim().length < 50} onClick={() => decide({ action: "edit", cover_letter: text, screening_answers: answers })} data-testid="save-edit">
                Save edit and re-check
              </button>
              <button className="btn" onClick={() => { setMode("view"); setText(draft.cover_letter); }}>
                Cancel
              </button>
            </>
          )}
          {mode === "reject" && (
            <>
              <button className="btn danger" disabled={busy || !reason.trim()} onClick={() => decide({ action: "reject", reason })} data-testid="confirm-reject">
                Reject with reason
              </button>
              <button className="btn" onClick={() => setMode("view")}>
                Cancel
              </button>
            </>
          )}
        </div>
      </section>
      <aside className="stack">
        <section className="card" aria-label="Dry-run preview">
          <h2 style={{ marginTop: 0 }}>What will be sent</h2>
          <p className="small muted">
            Dry run on {preview?.marketplace ?? "marketplace"}: nothing is sent until you approve.
          </p>
          <div className="row">
            <span>
              Bid <strong>{money(preview?.would_send?.bid_amount ?? price?.amount, price?.budget_type)}</strong>
            </span>
            <span>
              Connects <strong data-testid="connects-cost">{preview?.connects_cost ?? price?.connects_cost ?? "–"}</strong>
            </span>
            <span className="muted">balance after {preview?.connects_balance_after ?? "–"}</span>
          </div>
          <details>
            <summary className="small">Exact payload</summary>
            <div className="preview">{preview?.would_send?.cover_letter}</div>
          </details>
        </section>
        {price && (
          <section className="card">
            <h3 style={{ marginTop: 0 }}>Price rationale</h3>
            <p className="small">{price.rationale}</p>
            {!price.worth_connects && <span className="badge warn">Connects may not be worth it</span>}
          </section>
        )}
        {p.risk && (
          <section className="card">
            <h3 style={{ marginTop: 0 }}>Risk</h3>
            <p className="small">{(p.risk as { summary: string }).summary}</p>
          </section>
        )}
        <section className="card">
          <h3 style={{ marginTop: 0 }}>Evidence available ({evidence.length})</h3>
          <ul className="small" style={{ paddingLeft: 18, margin: 0 }}>
            {evidence.slice(0, 8).map((e) => (
              <li key={e.id}>
                <span className="mono">{e.id}</span> {e.outcome && <span className="badge plain">{e.outcome}</span>}
              </li>
            ))}
          </ul>
        </section>
      </aside>
    </div>
  );
}
