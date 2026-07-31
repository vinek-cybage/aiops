import { apiJson } from "../client";
import { useAuthStore } from "../../auth/authStore";

export interface CaseAction {
  id: number;
  action_id: number;
  similarity_score: number | null;
  status: string;
  applied_by: string | null;
  applied_at: string | null;
  result: Record<string, unknown> | null;
  name: string;
  action_type: string;
  description: string;
}

export interface Incident {
  inc_id: string;
  title: string;
  severity: string;
  status: "open" | "resolved";
  services: string[];
  team: string;
  hypotheses: Array<{ rank: number; text: string; confidence: number }>;
  evidence: Array<{ type: string; label: string; text: string }>;
  timeline: Array<{ time: string; event: string; color: string }>;
  ai_summary: string;
  occurrences: number;
  first_seen: string | null;
  last_seen: string | null;
  actions?: CaseAction[];
}

// The incidents/cases routes still key off the legacy X-User-Id header for
// team-scoping and action-attribution (aiops/main.py, aiops/cases.py) — they
// haven't been ported to JWT auth yet (planned alongside the Phase 3 tenant-
// scoping work on the cases table). Bridge the current JWT-authenticated
// user's id through as X-User-Id so scoping/attribution keeps working.
function legacyUserHeaders(): Record<string, string> {
  const userId = useAuthStore.getState().user?.id;
  return userId ? { "X-User-Id": String(userId) } : {};
}

export function listIncidents(): Promise<Incident[]> {
  return apiJson("/api/incidents", { headers: legacyUserHeaders() });
}

export function getIncident(incId: string): Promise<Incident> {
  return apiJson(`/api/incidents/${incId}`);
}

export function resolveIncident(incId: string): Promise<Incident> {
  return apiJson(`/api/incidents/${incId}/resolve`, { method: "PATCH" });
}

export function applyAction(incId: string, actionId: number): Promise<{ result: unknown; case: Incident }> {
  return apiJson(`/api/incidents/${incId}/actions/${actionId}/apply`, {
    method: "POST",
    headers: legacyUserHeaders(),
  });
}

export interface Catalog {
  apps: string[];
  services: string[];
  last_updated: string | null;
}

export function getCatalog(): Promise<Catalog> {
  return apiJson("/api/catalog");
}

export function uploadLogFile(file: File): Promise<Incident> {
  const form = new FormData();
  form.append("file", file);
  return apiJson("/api/analyze/upload", { method: "POST", body: form });
}
