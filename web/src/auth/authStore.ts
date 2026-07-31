import { create } from "zustand";
import type { AuthUser } from "./types";

interface AuthState {
  accessToken: string | null;
  user: AuthUser | null;
  status: "booting" | "authenticated" | "anonymous";
  setSession: (accessToken: string, user: AuthUser) => void;
  clearSession: () => void;
  setStatus: (status: AuthState["status"]) => void;
}

// Access token lives in memory only (not localStorage) to limit XSS exposure —
// the refresh token that survives reloads is an httpOnly cookie the browser
// manages, never touched by JS. See client.ts for the silent-refresh-on-boot flow.
export const useAuthStore = create<AuthState>((set) => ({
  accessToken: null,
  user: null,
  status: "booting",
  setSession: (accessToken, user) => set({ accessToken, user, status: "authenticated" }),
  clearSession: () => set({ accessToken: null, user: null, status: "anonymous" }),
  setStatus: (status) => set({ status }),
}));
