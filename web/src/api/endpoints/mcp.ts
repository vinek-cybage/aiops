import { apiJson } from "../client";

export interface CredentialField {
  key: string;
  label: string;
  type: "secret" | "string" | "number" | "boolean" | "url";
  required?: boolean;
  help_text?: string;
}

export interface McpCatalogEntry {
  id: string;
  slug: string;
  name: string;
  vendor: string | null;
  description: string | null;
  icon_url: string | null;
  category: string | null;
  connection_type: string;
  default_endpoint_url: string | null;
  credential_schema: CredentialField[];
  config_schema: CredentialField[];
  is_verified: boolean;
}

export interface TeamMcpInstance {
  id: string;
  team_id: number;
  catalog_entry_id: string | null;
  source: "catalog" | "custom";
  display_name: string;
  connection_type: string;
  endpoint_url: string | null;
  config: Record<string, unknown>;
  credential_masked: string | null;
  status: "pending" | "connected" | "error" | "disabled";
  last_checked_at: string | null;
  last_error: string | null;
  enabled: boolean;
}

export function listMcpCatalog(): Promise<McpCatalogEntry[]> {
  return apiJson("/api/mcp/catalog");
}

export function listTeamMcpInstances(teamId: number): Promise<TeamMcpInstance[]> {
  return apiJson(`/api/teams/${teamId}/mcp-instances`);
}

export interface McpInstanceInput {
  catalog_entry_id?: string | null;
  source: "catalog" | "custom";
  display_name: string;
  connection_type: string;
  endpoint_url?: string | null;
  config?: Record<string, unknown>;
  credentials?: Record<string, string> | null;
}

export function createTeamMcpInstance(teamId: number, body: McpInstanceInput): Promise<TeamMcpInstance> {
  return apiJson(`/api/teams/${teamId}/mcp-instances`, { method: "POST", body: JSON.stringify(body) });
}

export function updateTeamMcpInstance(teamId: number, instanceId: string, body: McpInstanceInput): Promise<TeamMcpInstance> {
  return apiJson(`/api/teams/${teamId}/mcp-instances/${instanceId}`, { method: "PUT", body: JSON.stringify(body) });
}

export function deleteTeamMcpInstance(teamId: number, instanceId: string): Promise<void> {
  return apiJson(`/api/teams/${teamId}/mcp-instances/${instanceId}`, { method: "DELETE" });
}

export function testMcpInstanceConnection(teamId: number, instanceId: string): Promise<{ status: string; last_error: string | null }> {
  return apiJson(`/api/teams/${teamId}/mcp-instances/${instanceId}/test-connection`, { method: "POST" });
}
