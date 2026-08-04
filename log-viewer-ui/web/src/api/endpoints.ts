import { apiJson } from "./client";

export interface TimelineEntry {
  time: string;
  event: string;
  color: string;
}

export interface RawLog {
  id: number;
  ts: string;
  service: string;
  event: string;
  trace_id: string | null;
  message: string;
}

export interface IncidentSummary {
  inc_id: string;
  title: string;
  severity: string;
  status: string;
  services: string[];
  occurrences: number;
  first_seen: string;
  last_seen: string;
}

export interface IncidentDetail extends IncidentSummary {
  team: string | null;
  hypotheses: unknown;
  evidence: unknown;
  timeline: TimelineEntry[] | null;
  ai_summary: string | null;
  cascades: unknown[];
  latest_logs: RawLog[] | null;
}

export interface ServiceMetric {
  service: string;
  incident_count: number;
  occurrence_count: number;
}

export interface DashboardMetrics {
  total_incidents: number;
  open_incidents: number;
  total_occurrences: number;
  deduped_count: number;
  by_service: ServiceMetric[];
  recent_incidents: IncidentSummary[];
}

export interface GraphNode {
  incident_id: string;
  title: string;
  service: string;
  status: string;
  occurrences: number;
  first_seen: string;
  last_seen: string;
  sample_logs: string[];
}

export interface GraphEdge {
  source: string;
  target: string;
  reason: string;
  similarity: number | null;
  seconds_apart: number | null;
}

export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export const listIncidents = () => apiJson<IncidentSummary[]>("/api/incidents");
export const getIncident = (incId: string) => apiJson<IncidentDetail>(`/api/incidents/${incId}`);
export const getMetrics = () => apiJson<DashboardMetrics>("/api/metrics");
export const getGraph = () => apiJson<GraphData>("/api/graph");
