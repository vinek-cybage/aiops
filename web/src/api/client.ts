import { useAuthStore } from "../auth/authStore";
import type { AuthUser } from "../auth/types";

const API_BASE = ""; // same-origin in production; Vite dev proxy handles /api in dev

interface RequestOptions extends RequestInit {
  skipAuthRetry?: boolean;
}

let refreshPromise: Promise<string | null> | null = null;

async function doRefresh(): Promise<string | null> {
  const res = await fetch(`${API_BASE}/api/auth/refresh`, {
    method: "POST",
    credentials: "include",
  });
  if (!res.ok) return null;
  const data = await res.json();
  return data.access_token as string;
}

async function refreshAccessToken(): Promise<string | null> {
  if (!refreshPromise) {
    refreshPromise = doRefresh().finally(() => {
      refreshPromise = null;
    });
  }
  return refreshPromise;
}

export async function apiFetch(path: string, options: RequestOptions = {}): Promise<Response> {
  const { accessToken } = useAuthStore.getState();
  const headers = new Headers(options.headers);
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
  // Skip for FormData — the browser must set its own multipart boundary.
  if (options.body && !(options.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers, credentials: "include" });

  if (res.status === 401 && !options.skipAuthRetry) {
    const newToken = await refreshAccessToken();
    if (newToken) {
      useAuthStore.setState({ accessToken: newToken });
      return apiFetch(path, { ...options, skipAuthRetry: true });
    }
    useAuthStore.getState().clearSession();
  }
  return res;
}

export async function apiJson<T>(path: string, options?: RequestOptions): Promise<T> {
  const res = await apiFetch(path, options);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ? JSON.stringify(body.detail) : `Request failed: ${res.status}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

// Called once on app boot: attempt a silent refresh so a returning user with a
// valid refresh cookie doesn't see a login flash before routes render.
export async function bootstrapSession(): Promise<void> {
  const token = await refreshAccessToken();
  if (!token) {
    useAuthStore.getState().clearSession();
    return;
  }
  useAuthStore.setState({ accessToken: token });
  try {
    const user = await apiJson<AuthUser>("/api/auth/me");
    useAuthStore.getState().setSession(token, user);
  } catch {
    useAuthStore.getState().clearSession();
  }
}
