import { apiJson } from "../client";

export interface OrgSummary {
  id: string;
  name: string;
  slug: string;
  is_active: boolean;
  created_at: string;
  team_count: number;
  user_count: number;
}

export interface OrgDetail extends Omit<OrgSummary, "team_count" | "user_count"> {
  teams: Array<{ id: number; name: string; services: string[] }>;
  users: Array<{ id: number; name: string; email: string; role: string; is_active: boolean }>;
}

export function listOrganizations(): Promise<OrgSummary[]> {
  return apiJson("/api/platform/organizations");
}

export function getOrganization(orgId: string): Promise<OrgDetail> {
  return apiJson(`/api/platform/organizations/${orgId}`);
}

export function setOrganizationActive(orgId: string, isActive: boolean): Promise<{ id: string; is_active: boolean }> {
  return apiJson(`/api/platform/organizations/${orgId}`, {
    method: "PATCH",
    body: JSON.stringify({ is_active: isActive }),
  });
}
