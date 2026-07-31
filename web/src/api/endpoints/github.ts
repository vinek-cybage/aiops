import { apiJson } from "../client";

export interface GithubIntegration {
  id: string;
  team_id: number;
  auth_mode: string;
  repo_full_name: string;
  base_branch: string;
  token_masked: string | null;
  status: "pending" | "connected" | "error" | "disabled";
  last_checked_at: string | null;
  last_error: string | null;
  enabled: boolean;
}

export function getGithubIntegration(teamId: number): Promise<GithubIntegration | null> {
  return apiJson(`/api/teams/${teamId}/github-integration`);
}

export function upsertGithubIntegration(
  teamId: number,
  body: { repo_full_name: string; base_branch: string; token?: string },
): Promise<GithubIntegration> {
  return apiJson(`/api/teams/${teamId}/github-integration`, { method: "PUT", body: JSON.stringify(body) });
}

export function deleteGithubIntegration(teamId: number): Promise<void> {
  return apiJson(`/api/teams/${teamId}/github-integration`, { method: "DELETE" });
}

export function testGithubIntegration(teamId: number): Promise<{ status: string; last_error: string | null }> {
  return apiJson(`/api/teams/${teamId}/github-integration/test-connection`, { method: "POST" });
}
