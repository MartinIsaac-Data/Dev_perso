import { createContext, ReactNode, useContext, useEffect, useState } from "react";
import { api, apiErrorMessage } from "@/lib/api";
import type { AuthUser } from "@/types";

interface AuthContextValue {
  user: AuthUser | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  hasPermission: (permission: string) => boolean;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(() => {
    const stored = localStorage.getItem("pressing_user");
    return stored ? (JSON.parse(stored) as AuthUser) : null;
  });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem("pressing_token");
    if (!token) {
      setLoading(false);
      return;
    }
    api
      .get("/auth/me")
      .then((res) => {
        setUser(res.data);
        localStorage.setItem("pressing_user", JSON.stringify(res.data));
      })
      .catch(() => {
        localStorage.removeItem("pressing_token");
        localStorage.removeItem("pressing_user");
        setUser(null);
      })
      .finally(() => setLoading(false));
  }, []);

  async function login(email: string, password: string) {
    try {
      const res = await api.post("/auth/login", { email, password });
      localStorage.setItem("pressing_token", res.data.token);
      localStorage.setItem("pressing_user", JSON.stringify(res.data.user));
      setUser(res.data.user);
    } catch (error) {
      throw new Error(apiErrorMessage(error, "Identifiants invalides"));
    }
  }

  function logout() {
    localStorage.removeItem("pressing_token");
    localStorage.removeItem("pressing_user");
    setUser(null);
  }

  function hasPermission(permission: string) {
    return user?.permissions.includes(permission) ?? false;
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, logout, hasPermission }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
