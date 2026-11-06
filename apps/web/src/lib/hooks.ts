import { useCallback, useEffect, useRef, useState } from "react";
import { api, getToken, type HealthOut } from "./api/client";

export function useAsync<T>(fn: () => Promise<T>, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const run = useCallback(async () => {
    try {
      setLoading(true);
      setData(await fn());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  useEffect(() => {
    void run();
  }, [run]);
  return { data, error, loading, reload: run, setData };
}

export function useHealth(intervalMs = 8000) {
  const [health, setHealth] = useState<HealthOut | null>(null);
  const [unreachable, setUnreachable] = useState(false);
  useEffect(() => {
    let alive = true;
    const tick = async () => {
      try {
        const { data, error } = await api.GET("/api/health");
        if (!alive) return;
        setHealth(data ?? null);
        setUnreachable(!!error);
      } catch {
        if (alive) setUnreachable(true);
      }
    };
    void tick();
    const id = setInterval(tick, intervalMs);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [intervalMs]);
  return { health, unreachable };
}

/** Server-Sent Events with the session token (EventSource cannot set headers, so we stream with fetch). */
export function useSSE(url: string | null, onEvent: (type: string, data: Record<string, unknown>) => void) {
  const cb = useRef(onEvent);
  cb.current = onEvent;
  useEffect(() => {
    if (!url) return;
    const ctrl = new AbortController();
    (async () => {
      try {
        const res = await fetch(url, { headers: { Authorization: `Bearer ${getToken() ?? ""}` }, signal: ctrl.signal });
        const reader = res.body?.getReader();
        if (!reader) return;
        const dec = new TextDecoder();
        let buf = "";
        for (;;) {
          const { value, done } = await reader.read();
          if (done) break;
          buf += dec.decode(value, { stream: true });
          const parts = buf.split(/\r?\n\r?\n/);
          buf = parts.pop() ?? "";
          for (const p of parts) {
            const ev = /event: (.*)/.exec(p)?.[1] ?? "message";
            const data = /data: (.*)/.exec(p)?.[1];
            if (data) {
              try {
                cb.current(ev.trim(), JSON.parse(data));
              } catch {
                /* ignore malformed */
              }
            }
          }
        }
      } catch {
        /* aborted or network */
      }
    })();
    return () => ctrl.abort();
  }, [url]);
}

export const money = (v?: number | null, t?: string | null) =>
  v == null ? "–" : `$${Math.round(v).toLocaleString()}${t === "hourly" ? "/h" : ""}`;
export const pct = (v?: number | null) => (v == null ? "–" : `${Math.round(v * 100)}%`);
export const ago = (ts?: number | null) => {
  if (!ts) return "";
  const s = Date.now() / 1000 - ts;
  return s < 60 ? "just now" : s < 3600 ? `${Math.round(s / 60)} min ago` : s < 86400 ? `${Math.round(s / 3600)} h ago` : `${Math.round(s / 86400)} d ago`;
};
