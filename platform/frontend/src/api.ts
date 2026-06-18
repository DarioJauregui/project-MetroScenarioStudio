import type {
  AuditEvent,
  ExcelArtifact,
  ExecutionResult,
  ExternalDataSnapshot,
  LlmParseResult,
  ScenarioComparison,
  ScenarioExecution,
  StationCatalogItem
} from "./types";

const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined)?.replace(/\/$/, "") ?? "";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...(options?.headers ?? {}) },
    ...options
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Request failed with ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export function createScenario(payload: {
  range_start: string;
  range_end: string;
  author?: string;
  comment?: string;
  natural_language_comment?: string;
  calendar_final?: Array<Record<string, unknown>>;
  manual_overrides?: Array<Record<string, unknown>>;
  events_final?: Array<Record<string, unknown>>;
  weather_final?: Array<Record<string, unknown>>;
  llm_detected_items?: Array<Record<string, unknown>>;
  llm_accepted_items?: Array<Record<string, unknown>>;
  llm_rejected_items?: Array<Record<string, unknown>>;
}) {
  return request<ScenarioExecution>("/api/scenarios", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function updateScenario(id: string, payload: Record<string, unknown>) {
  return request<ScenarioExecution>(`/api/scenarios/${id}`, {
    method: "PATCH",
    body: JSON.stringify(payload)
  });
}

export function listScenarios() {
  return request<ScenarioExecution[]>("/api/scenarios");
}

export function getScenarioResult(id: string) {
  return request<ExecutionResult>(`/api/scenarios/${id}/result`);
}

export function getScenarioAudit(id: string) {
  return request<AuditEvent[]>(`/api/scenarios/${id}/audit`);
}

export function getScenarioArtifacts(id: string) {
  return request<ExcelArtifact[]>(`/api/scenarios/${id}/artifacts`);
}

export function runScenario(id: string) {
  return request<ExecutionResult>(`/api/scenarios/${id}/run`, { method: "POST" });
}

export function explainScenario(id: string) {
  return request<ExecutionResult>(`/api/scenarios/${id}/explain`, { method: "POST" });
}

export function exportScenario(id: string) {
  return request<{ path: string }>(`/api/scenarios/${id}/export`, { method: "POST" });
}

export async function downloadScenarioExcel(id: string) {
  const response = await fetch(`${API_BASE}/api/scenarios/${id}/export/download`, { method: "POST" });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Download failed with ${response.status}`);
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `${id}.xlsx`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export function getExternalData(start: string, end: string) {
  return request<ExternalDataSnapshot>(`/api/external-data?start=${start}&end=${end}`);
}

export function getStations() {
  return request<StationCatalogItem[]>("/api/stations");
}

export function compareScenarios(baseId: string, candidateId: string) {
  return request<ScenarioComparison>(`/api/scenarios/compare?base_id=${baseId}&candidate_id=${candidateId}`);
}

export function parseComment(comment: string, rangeStart: string, rangeEnd: string) {
  return request<LlmParseResult>("/api/nlp/parse", {
    method: "POST",
    body: JSON.stringify({ comment, range_start: rangeStart, range_end: rangeEnd })
  });
}

export async function uploadImport(file: File) {
  const body = new FormData();
  body.append("file", file);
  const response = await fetch(`${API_BASE}/api/imports/upload`, {
    method: "POST",
    body
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Upload failed with ${response.status}`);
  }
  return response.json() as Promise<ExecutionResult>;
}

export function getMetrics() {
  return request<Record<string, unknown>>("/api/metrics");
}
