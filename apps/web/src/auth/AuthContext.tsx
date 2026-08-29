import { createContext, useContext, useEffect, useState, ReactNode } from "react";
import { api, ApiError } from "../api/client";

export interface Me {
  user: { id: number; email: string; role: "owner" | "staff" | "superadmin" };
  salon: {
    id: number;
    name: string;
    status: string;
    onboarding_step: number;
    timezone: string;
  } | null;
  is_support: boolean;
}

interface AuthCtx {
  me: Me | null;
  loading: boolean;
  setMe: (me: Me | null) => void;
  refresh: () => Promise<void>;
  logout: () => Promise<void>;
}

const Ctx = createContext<AuthCtx>(null!);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = async () => {
    try {
      setMe(await api<Me>("/api/auth/me"));
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) setMe(null);
    }
  };

  useEffect(() => {
    refresh().finally(() => setLoading(false));
  }, []);

  const logout = async () => {
    await api("/api/auth/logout", { method: "POST" });
    setMe(null);
  };

  return (
    <Ctx.Provider value={{ me, loading, setMe, refresh, logout }}>{children}</Ctx.Provider>
  );
}

export const useAuth = () => useContext(Ctx);
