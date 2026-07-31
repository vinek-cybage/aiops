import { apiJson } from "../client";
import type { AuthUser } from "../../auth/types";

interface AuthResponse {
  access_token: string;
  user: AuthUser;
}

export function login(email: string, password: string): Promise<AuthResponse> {
  return apiJson("/api/auth/login", { method: "POST", body: JSON.stringify({ email, password }) });
}

export function registerOrg(orgName: string, name: string, email: string, password: string): Promise<AuthResponse> {
  return apiJson("/api/auth/register", {
    method: "POST",
    body: JSON.stringify({ org_name: orgName, name, email, password }),
  });
}

export function logout(): Promise<void> {
  return apiJson("/api/auth/logout", { method: "POST" });
}
