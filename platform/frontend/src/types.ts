export type ScenarioStatus = "draft" | "base" | "what_if" | "importada" | "derivada" | "historico_evaluado";

export interface ScenarioExecution {
  id: string;
  status: ScenarioStatus;
  real_data_status: string;
  origin_type: string;
  parent_execution_id?: string | null;
  range_start: string;
  range_end: string;
  created_at?: string;
  updated_at?: string;
  executed_at?: string | null;
  author?: string | null;
  comment?: string | null;
  model_name: string;
  model_variant: string;
  dataset_version: string;
  warnings: string[];
  input?: {
    natural_language_comment?: string | null;
    calendar_final?: CalendarVariable[];
    events_final?: EventVariable[];
    weather_final?: Array<Record<string, unknown>>;
    manual_overrides?: Array<Record<string, unknown>>;
    llm_detected_items?: Array<Record<string, unknown>>;
    llm_accepted_items?: Array<Record<string, unknown>>;
    llm_rejected_items?: Array<Record<string, unknown>>;
  };
}

export interface CalendarVariable {
  target_date: string;
  day_of_week: number;
  is_holiday: boolean;
  is_preholiday: boolean;
  is_postholiday: boolean;
  is_bridge: boolean;
  special_day?: string | null;
  source: string;
  modified: boolean;
  used_by_model: boolean;
}

export interface EventVariable {
  event_id: string;
  name: string;
  target_date: string;
  date_mode?: string;
  start_date?: string | null;
  end_date?: string | null;
  selected_dates?: string[];
  all_day?: boolean;
  start_time?: string | null;
  end_time?: string | null;
  event_type: string;
  impact_level: string;
  affected_stations: string[];
  comment?: string | null;
  source?: string | null;
  origin_event_id?: string | null;
  deleted?: boolean;
  modified: boolean;
  used_by_model: boolean;
}

export interface AggregateRow {
  level: string;
  target_date?: string | null;
  linea?: string | null;
  estacion?: string | null;
  y_pred: number;
  y_real?: number | null;
  real_available: boolean;
  abs_error?: number | null;
  pct_error?: number | null;
}

export interface PredictionRow {
  target_date: string;
  linea: string;
  estacion: string;
  series_id: string;
  station_abbrev: string;
  network_order: number;
  y_pred: number;
  y_real?: number | null;
  model_variant: string;
  horizon_days: number;
  forecast_origin_date?: string | null;
  prediction_mode?: string;
  model_artifact?: string | null;
  model_artifact_sha256?: string | null;
  feature_row_hash?: string | null;
}

export interface ExplanationItem {
  section: string;
  item_type: string;
  label: string;
  description: string;
  source: string;
  used_by_model: boolean;
  confidence?: string | null;
  limitation?: string | null;
}

export interface ExecutionResult {
  execution: ScenarioExecution;
  prediction_rows: PredictionRow[];
  aggregates: AggregateRow[];
  explanations: ExplanationItem[];
  narrative_summary?: string | null;
  audit_events?: AuditEvent[];
}

export interface ExternalDataSnapshot {
  range_start?: string;
  range_end?: string;
  calendar: CalendarVariable[];
  events: EventVariable[];
  weather: Array<Record<string, unknown>>;
  coverage: {
    calendar_days: number;
    event_days: number;
    weather_days: number;
    total_days: number;
  };
  warnings: Array<{ code: string; message: string; severity: string }>;
}

export interface StationCatalogItem {
  linea: string;
  estacion: string;
  series_id: string;
  station_abbrev: string;
  network_order: number;
}

export interface LlmParseResult {
  detected_items: Array<Record<string, unknown>>;
  not_used: Array<{ text: string; reason: string }>;
  requires_human_validation: boolean;
  prompt_version?: string;
  raw_response?: Record<string, unknown>;
}

export interface AuditEvent {
  execution_id: string;
  timestamp: string;
  action: string;
  actor?: string | null;
  summary: string;
  payload: Record<string, unknown>;
}

export interface ExcelArtifact {
  execution_id: string;
  artifact_type: string;
  path: string;
  checksum?: string | null;
  schema_version?: string | null;
}

export interface ScenarioComparisonRow {
  level: string;
  target_date?: string | null;
  linea?: string | null;
  estacion?: string | null;
  base_y_pred: number;
  candidate_y_pred: number;
  delta_abs: number;
  delta_pct?: number | null;
}

export interface ScenarioComparison {
  base_execution_id: string;
  candidate_execution_id: string;
  rows: ScenarioComparisonRow[];
  notes: string[];
}

export type ExecutionIntent = "base" | "what_if" | "importada";
export type ResultsTab = "summary" | "temporal" | "ranking" | "detail";
export type TimeGrouping = "day" | "week";
export type SortDirection = "asc" | "desc";
export type TemporalRow = { label: string; y_pred: number; y_real?: number | null };
export type ZoomMode = "fit" | "normal" | "detail";
export type NluFeedback = { tone: "success" | "error"; messages: string[]; applied: string[] };

export interface EventDraft {
  event_id: string;
  name: string;
  date_mode: "selected_dates" | "date_range";
  target_date: string;
  end_date: string;
  selected_dates: string[];
  all_day: boolean;
  start_time: string;
  end_time: string;
  affected_stations: string[];
  event_type: string;
  impact_level: string;
  comment: string;
  origin_event_id?: string | null;
  deleted?: boolean;
}

export interface WeatherOverride {
  rain: boolean;
  heavy_rain: boolean;
  approx_temperature?: number | null;
  hot_day?: boolean;
  cold_day?: boolean;
  bad_weather?: boolean;
  temp_min?: number | null;
  temp_mean?: number | null;
  temp_max?: number | null;
  precip_mm?: number | null;
  rain_hours?: number | null;
  wind?: number | null;
  humidity?: number | null;
  weather_code?: string | null;
  alert_level?: string | null;
  alert_summary?: string | null;
}

export interface WeatherFormState {
  rain: boolean;
  heavy_rain: boolean;
  hot_day: boolean;
  cold_day: boolean;
  bad_weather: boolean;
  approx_temperature: string;
  temp_min: string;
  temp_mean: string;
  temp_max: string;
  precip_mm: string;
  rain_hours: string;
  wind: string;
  humidity: string;
  weather_code: string;
  alert_level: string;
  alert_summary: string;
}

