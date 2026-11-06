import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, setToken, type UserOut } from "./api/client";

type Auth = { user: UserOut | null; loading: boolean; refresh: () => Promise<void>; logout: () => Promise<void> };
const Ctx = createContext<Auth>({ user: null, loading: true, refresh: async () => {}, logout: async () => {} });

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserOut | null>(null);
  const [loading, setLoading] = useState(true);
  const refresh = useCallback(async () => {
    try {
      const { data } = await api.GET("/api/auth/me");
      setUser(data ?? null);
    } catch {
      setUser(null);
    }
    setLoading(false);
  }, []);
  const logout = useCallback(async () => {
    await api.POST("/api/auth/logout");
    setToken(null);
    setUser(null);
  }, []);
  useEffect(() => {
    void refresh();
  }, [refresh]);
  return <Ctx.Provider value={{ user, loading, refresh, logout }}>{children}</Ctx.Provider>;
}
export const useAuth = () => useContext(Ctx);
