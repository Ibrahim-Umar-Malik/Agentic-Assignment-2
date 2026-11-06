import { useState, type FormEvent } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { api, errorText, setToken } from "../../lib/api/client";
import { useAuth } from "../../lib/auth";

export default function LoginPage() {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [persona, setPersona] = useState<"ai_ml" | "fullstack" | "data_analyst">("ai_ml");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const { refresh } = useAuth();
  const nav = useNavigate();
  const loc = useLocation() as { state?: { from?: string } };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    const res =
      mode === "login"
        ? await api.POST("/api/auth/login", { body: { email, password } })
        : await api.POST("/api/auth/register", { body: { email, password, name, persona } });
    setBusy(false);
    if (res.error || !res.data) return setErr(errorText(res.error));
    setToken(res.data.token);
    await refresh();
    nav(res.data.user.settings?.onboarded ? loc.state?.from ?? "/inbox" : "/onboarding");
  };

  return (
    <div className="auth-wrap">
      <div className="brand" style={{ justifyContent: "center", fontSize: "1.4rem" }}>
        <span className="brand-mark">G</span>GigBid
      </div>
      <p className="muted" style={{ textAlign: "center" }}>
        A team of agents finds jobs, judges them and drafts grounded proposals. You approve everything that leaves.
      </p>
      <form className="card" onSubmit={submit} aria-label={mode === "login" ? "Sign in" : "Create account"}>
        <h1>{mode === "login" ? "Sign in" : "Create your account"}</h1>
        <div className="field">
          <label htmlFor="email">Email</label>
          <input id="email" type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="password">Password</label>
          <input id="password" type="password" autoComplete={mode === "login" ? "current-password" : "new-password"} required minLength={6}
            value={password} onChange={(e) => setPassword(e.target.value)} />
        </div>
        {mode === "register" && (
          <>
            <div className="field">
              <label htmlFor="name">Name</label>
              <input id="name" type="text" value={name} onChange={(e) => setName(e.target.value)} />
            </div>
            <div className="field">
              <label htmlFor="persona">Start from a persona (you can upload your own portfolio next)</label>
              <select id="persona" value={persona} onChange={(e) => setPersona(e.target.value as typeof persona)}>
                <option value="ai_ml">AI/ML engineer</option>
                <option value="fullstack">Full-stack web developer</option>
                <option value="data_analyst">Data analyst</option>
              </select>
            </div>
          </>
        )}
        {err && <div className="banner bad" role="alert">{err}</div>}
        <div className="row spread">
          <button className="btn primary" type="submit" disabled={busy}>
            {mode === "login" ? "Sign in" : "Create account"}
          </button>
          <button type="button" className="btn sm" onClick={() => setMode(mode === "login" ? "register" : "login")}>
            {mode === "login" ? "New here? Create an account" : "Have an account? Sign in"}
          </button>
        </div>
      </form>
    </div>
  );
}
