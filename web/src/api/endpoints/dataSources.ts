import { apiJson } from "../client";

export interface TeamDataSource {
  id: string;
  team_id: number;
  type: string;
  display_name: string;
  connection_config: Record<string, unknown>;
  credential_masked: string | null;
  status: "pending" | "connected" | "error" | "disabled";
  last_checked_at: string | null;
  last_error: string | null;
  enabled: boolean;
}

export interface DataSourceInput {
  type: string;
  display_name: string;
  connection_config?: Record<string, unknown>;
  credentials?: Record<string, string> | null;
}

export function listDataSources(teamId: number): Promise<TeamDataSource[]> {
  return apiJson(`/api/teams/${teamId}/data-sources`);
}

export function createDataSource(teamId: number, body: DataSourceInput): Promise<TeamDataSource> {
  return apiJson(`/api/teams/${teamId}/data-sources`, { method: "POST", body: JSON.stringify(body) });
}

export function updateDataSource(teamId: number, dsId: string, body: DataSourceInput): Promise<TeamDataSource> {
  return apiJson(`/api/teams/${teamId}/data-sources/${dsId}`, { method: "PUT", body: JSON.stringify(body) });
}

export function deleteDataSource(teamId: number, dsId: string): Promise<void> {
  return apiJson(`/api/teams/${teamId}/data-sources/${dsId}`, { method: "DELETE" });
}

export function testDataSourceConnection(teamId: number, dsId: string): Promise<{ status: string; last_error: string | null }> {
  return apiJson(`/api/teams/${teamId}/data-sources/${dsId}/test-connection`, { method: "POST" });
}

export interface IngestionKey {
  id: string;
  key_prefix: string;
  label: string | null;
  scopes: string[];
  last_used_at: string | null;
}

export function listIngestionKeys(teamId: number): Promise<IngestionKey[]> {
  return apiJson(`/api/teams/${teamId}/ingestion-keys`);
}

export function createIngestionKey(teamId: number, label: string): Promise<{ id: string; key: string; key_prefix: string; label: string | null }> {
  return apiJson(`/api/teams/${teamId}/ingestion-keys`, { method: "POST", body: JSON.stringify({ label }) });
}

export function revokeIngestionKey(teamId: number, keyId: string): Promise<void> {
  return apiJson(`/api/teams/${teamId}/ingestion-keys/${keyId}`, { method: "DELETE" });
}
