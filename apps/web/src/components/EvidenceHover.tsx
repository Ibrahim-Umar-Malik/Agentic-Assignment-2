import { useState } from "react";

export type Claim = { text: string; label: string; evidence_ids: string[]; score?: number };
export type Ev = { id: string; title?: string | null; type?: string | null; snippet?: string; project?: string | null; outcome?: string | null };

/** A claim in the draft. Hover or focus shows the portfolio evidence behind it (or that there is none). */
export function EvidenceHover({ claim, evidence }: { claim: Claim; evidence: Ev[] }) {
  const [show, setShow] = useState(false);
  const items = claim.evidence_ids
    .map((id) => evidence.find((e) => e.id === id) ?? { id, title: id })
    .slice(0, 3);
  const label = { supported: "Supported", partly_supported: "Partly supported", unsupported: "Not supported" }[claim.label] ?? claim.label;
  return (
    <span
      className={`claim ${claim.label}`}
      tabIndex={0}
      onMouseEnter={() => setShow(true)}
      onMouseLeave={() => setShow(false)}
      onFocus={() => setShow(true)}
      onBlur={() => setShow(false)}
      aria-describedby={show ? `ev-${claim.text.length}` : undefined}
      data-testid="claim"
    >
      {claim.text}
      {show && (
        <span className="hovercard" role="tooltip" id={`ev-${claim.text.length}`}>
          <strong>{label}</strong>
          {claim.score != null && <span className="muted"> · grounding {Math.round(claim.score * 100)}%</span>}
          {items.length === 0 && <div>No portfolio evidence. This sentence cannot be sent as a claim.</div>}
          {items.map((e) => (
            <span key={e.id} style={{ display: "block", marginTop: 6 }}>
              <span className="mono">{e.id}</span>
              {e.title && <> · {e.title}</>}
              {e.snippet && <span style={{ display: "block" }} className="muted">{e.snippet.replace(/[#*]/g, "").slice(0, 220)}…</span>}
            </span>
          ))}
        </span>
      )}
    </span>
  );
}

/** Render a paragraph with its claims highlighted (exact-sentence match from the verifier's output). */
export function Paragraph({ text, claims, evidence }: { text: string; claims: Claim[]; evidence: Ev[] }) {
  const parts: (string | Claim)[] = [text];
  for (const c of claims) {
    for (let i = 0; i < parts.length; i++) {
      const p = parts[i];
      if (typeof p !== "string") continue;
      const at = p.indexOf(c.text);
      if (at >= 0) {
        parts.splice(i, 1, p.slice(0, at), c, p.slice(at + c.text.length));
        break;
      }
    }
  }
  return (
    <>
      {parts.map((p, i) => (typeof p === "string" ? <span key={i}>{p}</span> : <EvidenceHover key={i} claim={p} evidence={evidence} />))}
    </>
  );
}
