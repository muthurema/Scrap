/**
 * Auth storage shim.
 * sessionStorage is used instead of localStorage so the JWT does not survive
 * tab/window close — this reduces XSS-stolen-token exposure window.
 * The previous_localStorage migration below also clears legacy long-lived
 * tokens left from earlier builds.
 *
 * NOTE: For a true production-grade fix, the backend would issue httpOnly
 * SameSite=strict cookies. That requires a broader CORS / credentials change
 * and is tracked in the PRD backlog ("Refresh-token rotation + httpOnly cookies").
 */
const T_KEY = "ehs_token";
const U_KEY = "ehs_user";

// One-time migration: pull any pre-existing localStorage values into sessionStorage and wipe localStorage.
try {
  if (typeof window !== "undefined") {
    const oldT = window.localStorage.getItem(T_KEY);
    const oldU = window.localStorage.getItem(U_KEY);
    if (oldT) window.sessionStorage.setItem(T_KEY, oldT);
    if (oldU) window.sessionStorage.setItem(U_KEY, oldU);
    window.localStorage.removeItem(T_KEY);
    window.localStorage.removeItem(U_KEY);
  }
} catch (e) {
  console.warn("[auth-store] migration skipped:", e?.message);
}

export const authStore = {
  getToken() {
    try { return sessionStorage.getItem(T_KEY); } catch { return null; }
  },
  setToken(token) {
    try { sessionStorage.setItem(T_KEY, token); } catch (e) { console.error("[auth-store] setToken failed:", e); }
  },
  getUser() {
    try { return JSON.parse(sessionStorage.getItem(U_KEY) || "null"); } catch { return null; }
  },
  setUser(user) {
    try { sessionStorage.setItem(U_KEY, JSON.stringify(user)); } catch (e) { console.error("[auth-store] setUser failed:", e); }
  },
  clear() {
    try {
      sessionStorage.removeItem(T_KEY);
      sessionStorage.removeItem(U_KEY);
    } catch (e) { console.error("[auth-store] clear failed:", e); }
  },
};
