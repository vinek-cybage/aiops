import { createContext, useContext, useMemo, useState, type ReactNode } from "react";

// Cosmetic access gate only — this tool has no real backend auth (see
// log-viewer-ui/api/main.py's own docstring: "No auth: internal tool, same
// trust boundary as log-viewer/aiops-db themselves"). This just keeps casual
// visitors off the dashboard; anyone reading the source (or the network tab —
// every API call still works with zero credentials) can bypass it entirely.
// Do not reuse this pattern anywhere real auth is actually required.
const ACCESS_CODE = "aiops2026";

const STORAGE_KEY = "log_viewer_ui_authed";

interface AuthContextValue {
  isAuthenticated: boolean;
  login: (code: string) => boolean;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [isAuthenticated, setIsAuthenticated] = useState(() => sessionStorage.getItem(STORAGE_KEY) === "1");

  const value = useMemo<AuthContextValue>(
    () => ({
      isAuthenticated,
      login: (code: string) => {
        const ok = code === ACCESS_CODE;
        if (ok) {
          sessionStorage.setItem(STORAGE_KEY, "1");
          setIsAuthenticated(true);
        }
        return ok;
      },
      logout: () => {
        sessionStorage.removeItem(STORAGE_KEY);
        setIsAuthenticated(false);
      },
    }),
    [isAuthenticated],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
