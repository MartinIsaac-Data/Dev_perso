import { createContext, ReactNode, useContext, useEffect, useState } from "react";
import { portalApi } from "@/lib/portalApi";
import { apiErrorMessage } from "@/lib/api";

export interface PortalCustomer {
  id: string;
  fullName: string;
  phone: string;
  email?: string | null;
  address?: string | null;
  type: string;
}

interface PortalAuthContextValue {
  customer: PortalCustomer | null;
  loading: boolean;
  login: (identifier: string, password: string) => Promise<void>;
  register: (data: {
    fullName: string;
    phone: string;
    email?: string;
    address?: string;
    password: string;
  }) => Promise<void>;
  logout: () => void;
}

const PortalAuthContext = createContext<PortalAuthContextValue | undefined>(undefined);

export function PortalAuthProvider({ children }: { children: ReactNode }) {
  const [customer, setCustomer] = useState<PortalCustomer | null>(() => {
    const stored = localStorage.getItem("pressing_portal_customer");
    return stored ? (JSON.parse(stored) as PortalCustomer) : null;
  });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem("pressing_portal_token");
    if (!token) {
      setLoading(false);
      return;
    }
    portalApi
      .get("/portal-auth/me")
      .then((res) => {
        setCustomer(res.data);
        localStorage.setItem("pressing_portal_customer", JSON.stringify(res.data));
      })
      .catch(() => {
        localStorage.removeItem("pressing_portal_token");
        localStorage.removeItem("pressing_portal_customer");
        setCustomer(null);
      })
      .finally(() => setLoading(false));
  }, []);

  function persist(token: string, customer: PortalCustomer) {
    localStorage.setItem("pressing_portal_token", token);
    localStorage.setItem("pressing_portal_customer", JSON.stringify(customer));
    setCustomer(customer);
  }

  async function login(identifier: string, password: string) {
    try {
      const res = await portalApi.post("/portal-auth/login", { identifier, password });
      persist(res.data.token, res.data.customer);
    } catch (error) {
      throw new Error(apiErrorMessage(error, "Identifiants invalides"));
    }
  }

  async function register(data: {
    fullName: string;
    phone: string;
    email?: string;
    address?: string;
    password: string;
  }) {
    try {
      const res = await portalApi.post("/portal-auth/register", data);
      persist(res.data.token, res.data.customer);
    } catch (error) {
      throw new Error(apiErrorMessage(error, "Impossible de créer le compte"));
    }
  }

  function logout() {
    localStorage.removeItem("pressing_portal_token");
    localStorage.removeItem("pressing_portal_customer");
    setCustomer(null);
  }

  return (
    <PortalAuthContext.Provider value={{ customer, loading, login, register, logout }}>
      {children}
    </PortalAuthContext.Provider>
  );
}

export function usePortalAuth() {
  const ctx = useContext(PortalAuthContext);
  if (!ctx) throw new Error("usePortalAuth must be used within PortalAuthProvider");
  return ctx;
}
