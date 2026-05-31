import { createContext, useContext, useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api";
import { authStore } from "@/lib/auth-store";

const AuthCtx = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => authStore.getUser());
  const [loading, setLoading] = useState(false);

  const persist = useCallback((token, u) => {
    authStore.setToken(token);
    authStore.setUser(u);
    setUser(u);
  }, []);

  const login = useCallback(async (email, password) => {
    setLoading(true);
    try {
      const { data } = await api.post("/auth/login", { email, password });
      const u = {
        id: data.user_id, email: data.email, full_name: data.full_name,
        role: data.role, company_id: data.company_id,
        needs_onboarding: data.needs_onboarding ?? false,
      };
      persist(data.access_token, u);
      return u;
    } finally {
      setLoading(false);
    }
  }, [persist]);

  const register = useCallback(async (payload) => {
    setLoading(true);
    try {
      const { data } = await api.post("/auth/register", payload);
      const u = {
        id: data.user_id, email: data.email, full_name: data.full_name,
        role: data.role, company_id: data.company_id,
        needs_onboarding: data.needs_onboarding ?? true,
      };
      persist(data.access_token, u);
      return u;
    } finally {
      setLoading(false);
    }
  }, [persist]);

  const logout = useCallback(() => {
    authStore.clear();
    setUser(null);
  }, []);

  return (
    <AuthCtx.Provider value={{ user, loading, login, register, logout }}>
      {children}
    </AuthCtx.Provider>
  );
}

export const useAuth = () => useContext(AuthCtx);
