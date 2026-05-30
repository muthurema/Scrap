import { createContext, useContext, useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api";

const AuthCtx = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => {
    try { return JSON.parse(localStorage.getItem("ehs_user") || "null"); } catch { return null; }
  });
  const [loading, setLoading] = useState(false);

  const persist = (token, u) => {
    localStorage.setItem("ehs_token", token);
    localStorage.setItem("ehs_user", JSON.stringify(u));
    setUser(u);
  };

  const login = useCallback(async (email, password) => {
    setLoading(true);
    try {
      const { data } = await api.post("/auth/login", { email, password });
      const u = { id: data.user_id, email: data.email, full_name: data.full_name, role: data.role, company_id: data.company_id };
      persist(data.access_token, u);
      return u;
    } finally {
      setLoading(false);
    }
  }, []);

  const register = useCallback(async (payload) => {
    setLoading(true);
    try {
      const { data } = await api.post("/auth/register", payload);
      const u = { id: data.user_id, email: data.email, full_name: data.full_name, role: data.role, company_id: data.company_id };
      persist(data.access_token, u);
      return u;
    } finally {
      setLoading(false);
    }
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem("ehs_token");
    localStorage.removeItem("ehs_user");
    setUser(null);
  }, []);

  return (
    <AuthCtx.Provider value={{ user, loading, login, register, logout }}>
      {children}
    </AuthCtx.Provider>
  );
}

export const useAuth = () => useContext(AuthCtx);
