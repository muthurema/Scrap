import axios from "axios";
import { authStore } from "@/lib/auth-store";

// In a single-service Railway deploy the React app is served by FastAPI at the
// same origin, so REACT_APP_BACKEND_URL can be empty/undefined and axios will
// hit the same host. On Emergent's split deploy it's set to the backend URL.
const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "";
export const API = `${BACKEND_URL}/api`;

export const api = axios.create({
  baseURL: API,
});

api.interceptors.request.use((config) => {
  const token = authStore.getToken();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

api.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err?.response?.status === 401) {
      authStore.clear();
      if (window.location.pathname !== "/login") {
        window.location.href = "/login";
      }
    }
    return Promise.reject(err);
  }
);
