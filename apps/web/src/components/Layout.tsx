import { useState, type ReactNode } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "../lib/auth";
import { useHealth } from "../lib/hooks";

const LINKS = [
  ["/inbox", "Job inbox"],
  ["/pipeline", "Pipeline"],
  ["/messages", "Messages"],
  ["/runs", "Agent runs"],
  ["/analytics", "Analytics"],
  ["/settings", "Settings"],
];

export function DegradedBanner() {
  const { health, unreachable } = useHealth();
  if (unreachable)
    return (
      <div className="banner bad" role="alert" data-testid="degraded-banner">
        GigBid's server is unreachable. Your pending approvals are saved; this page will recover on its own.
      </div>
    );
  if (health && !health.marketplace.ok)
    return (
      <div className="banner warn" role="alert" data-testid="degraded-banner">
        <strong>Marketplace unavailable.</strong> GigBid can't reach the marketplace right now. New work is queued and will
        resume automatically; nothing is lost and nothing is sent until it is back.
      </div>
    );
  return null;
}

export default function Layout({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const nav = useNavigate();
  return (
    <div className="shell">
      <header className="topbar">
        <span className="brand">
          <span className="brand-mark">G</span>GigBid
        </span>
        <button className="btn sm" aria-expanded={open} aria-controls="sidenav" onClick={() => setOpen(!open)}>
          Menu
        </button>
      </header>
      <aside id="sidenav" className={`side ${open ? "open" : ""}`}>
        <div className="brand">
          <span className="brand-mark">G</span>GigBid
        </div>
        <nav className="nav" aria-label="Main">
          {LINKS.map(([to, label]) => (
            <NavLink key={to} to={to} onClick={() => setOpen(false)} className={({ isActive }) => (isActive ? "active" : "")}>
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="side-foot">
          <div>{user?.email}</div>
          <div className="small">Persona: {user?.persona}</div>
          <button
            className="btn sm"
            style={{ marginTop: 6 }}
            onClick={async () => {
              await logout();
              nav("/login");
            }}
          >
            Sign out
          </button>
        </div>
      </aside>
      <main>
        <DegradedBanner />
        {children}
      </main>
    </div>
  );
}
