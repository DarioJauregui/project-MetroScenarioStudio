import type { ChartData, ChartDataset } from "chart.js";
import type { EventDraft, PredictionRow, ScenarioComparisonRow, TemporalRow, TimeGrouping } from "../types";

export function groupTemporalRows(
  rows: Array<{ target_date?: string | null; y_pred: number; y_real?: number | null }>,
  grouping: TimeGrouping
): TemporalRow[] {
  const buckets = new Map<string, { y_pred: number; y_real: number; real_count: number }>();
  for (const row of rows) {
    if (!row.target_date) continue;
    const label = grouping === "week" ? weekLabel(row.target_date) : row.target_date;
    const current = buckets.get(label) ?? { y_pred: 0, y_real: 0, real_count: 0 };
    current.y_pred += row.y_pred;
    if (row.y_real !== null && row.y_real !== undefined) {
      current.y_real += row.y_real;
      current.real_count += 1;
    }
    buckets.set(label, current);
  }
  return [...buckets.entries()].map(([label, value]) => ({
    label,
    y_pred: value.y_pred,
    y_real: value.real_count ? value.y_real : null,
  }));
}

export function weekLabel(value: string) {
  const date = parseLocalDate(value);
  const mondayBasedDay = (date.getDay() + 6) % 7;
  const monday = new Date(date);
  monday.setDate(date.getDate() - mondayBasedDay);
  const weekYear = monday.getFullYear();
  const yearStart = new Date(weekYear, 0, 1);
  const firstMondayOffset = (yearStart.getDay() + 6) % 7;
  const firstMonday = new Date(yearStart);
  firstMonday.setDate(yearStart.getDate() - firstMondayOffset);
  const week = Math.floor((monday.getTime() - firstMonday.getTime()) / (7 * 86400000)) + 1;
  return `${weekYear}-W${String(week).padStart(2, "0")}`;
}

export function weekdayFromLabel(value: string) {
  const date = parseLocalDate(value);
  return Number.isNaN(date.getTime()) ? -1 : date.getDay();
}

export function datesBetween(start: string, end: string) {
  const dates: string[] = [];
  const startDate = parseLocalDate(start);
  const endDate = parseLocalDate(end || start);
  if (Number.isNaN(startDate.getTime()) || Number.isNaN(endDate.getTime()) || endDate < startDate) {
    return start ? [start] : [];
  }
  const current = new Date(startDate);
  while (current <= endDate) {
    dates.push(formatLocalDate(current));
    current.setDate(current.getDate() + 1);
  }
  return dates;
}

export function parseLocalDate(value: string) {
  const [year, month, day] = value.split("-").map(Number);
  if (!year || !month || !day) return new Date(Number.NaN);
  return new Date(year, month - 1, day);
}

export function formatLocalDate(value: Date) {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export function weekdayName(value: string) {
  const labels = ["Domingo", "Lunes", "Martes", "Miercoles", "Jueves", "Viernes", "Sabado"];
  const day = weekdayFromLabel(value);
  return labels[day] ?? "";
}

export function eventDates(event: EventDraft) {
  return event.date_mode === "selected_dates" ? event.selected_dates : datesBetween(event.target_date, event.end_date);
}

export function compareValues(a: unknown, b: unknown, direction: "asc" | "desc") {
  const multiplier = direction === "asc" ? 1 : -1;
  if (typeof a === "number" && typeof b === "number") return (a - b) * multiplier;
  return String(a ?? "").localeCompare(String(b ?? "")) * multiplier;
}

export function formatNumber(value: number) {
  return new Intl.NumberFormat("es-ES", { maximumFractionDigits: 0 }).format(value);
}

export function formatPercent(value?: number | null) {
  if (value === null || value === undefined) return "";
  return new Intl.NumberFormat("es-ES", { style: "percent", maximumFractionDigits: 2 }).format(value);
}

export function formatCell(value: unknown) {
  if (typeof value === "number") return new Intl.NumberFormat("es-ES", { maximumFractionDigits: 2 }).format(value);
  if (typeof value === "boolean") return value ? "Sí" : "No";
  if (value === null || value === undefined) return "";
  return String(value);
}

export function optionalNumber(value: unknown) {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export function textNumber(value: unknown) {
  const parsed = optionalNumber(value);
  return parsed === null ? "" : String(parsed);
}

export function nullableText(value: unknown) {
  if (value === null || value === undefined || value === "") return null;
  return String(value);
}

export function formatTableCell(column: string, value: unknown) {
  if (column.includes("pct") || column === "delta_pct") {
    return formatPercent(typeof value === "number" ? value : null);
  }
  if (column === "level") {
    return aggregateLevelLabel(String(value ?? ""));
  }
  return formatCell(value);
}

export function columnLabel(column: string) {
  const labels: Record<string, string> = {
    target_date: "Fecha",
    linea: "Línea",
    estacion: "Estación",
    y_pred: "Viajes previstos",
    y_real: "Viajes reales",
    pct_error: "Error %",
    abs_error: "Error absoluto",
    real_available: "Real disponible",
    level: "Nivel",
    delta_abs: "Diferencia",
    delta_pct: "Diferencia %",
  };
  return labels[column] ?? column.replaceAll("_", " ");
}

export function aggregateLevelLabel(value: string) {
  const labels: Record<string, string> = {
    network: "Total red",
    network_date: "Día",
    line: "Línea",
    station: "Estación",
  };
  return labels[value] ?? value;
}

export function formatDateTime(value: string) {
  if (!value) return "";
  return value.replace("T", " ").slice(0, 16);
}

export function statusLabel(value: string) {
  const labels: Record<string, string> = {
    draft: "Borrador",
    base: "Base",
    what_if: "What-if",
    importada: "Importada",
    derivada: "Derivada",
    historico_evaluado: "Historico evaluado",
  };
  return labels[value] ?? value;
}

export function shortLine(value: string) {
  if (value.includes("1")) return "L1";
  if (value.includes("2")) return "L2";
  return value;
}

export function alertLabel(value: string) {
  const normalized = value.toLowerCase();
  if (normalized.includes("roja")) return "Alerta roja";
  if (normalized.includes("naranja")) return "Alerta naranja";
  if (normalized.includes("amarilla")) return "Alerta amarilla";
  return "Sin alerta";
}

export function warningText(code: string) {
  const labels: Record<string, string> = {
    calendar_only: "Solo hay calendario disponible para el rango seleccionado.",
    historical_evaluation_leakage_risk: "Rango historico evaluado con datos reales; no debe leerse como prediccion operativa.",
    long_range: "El rango es largo; revisa la interpretacion y las agregaciones.",
    missing_events: "No hay eventos planificados para parte del rango.",
    missing_future_weather: "No hay meteorologia disponible para parte del rango.",
    model_horizon_exceeded: "El rango excede el horizonte razonable validado del modelo.",
    model_inference_unavailable: "No se pudo ejecutar el modelo entrenado y se uso una alternativa disponible.",
    model_metadata_missing: "Falta metadata del modelo para construir la matriz de inferencia.",
    model_predictions_unavailable: "No hay predicciones disponibles para el rango solicitado.",
    model_prediction_partial: "El modelo solo devolvio predicciones para parte del rango.",
    model_series_partial: "El modelo no devolvio todas las series de estacion-linea esperadas.",
    precomputed_forecast_fallback_used: "Se uso el forecast precalculado como respaldo.",
    recursive_future_inference_horizon_exceeded:
      "El rango futuro usa features recursivas mas alla del horizonte razonable; interpreta la curva como simulacion de baja confianza.",
  };
  return labels[code] ?? code.replaceAll("_", " ");
}

export function getNested(source: Record<string, unknown> | null, keys: string[]) {
  let current: unknown = source;
  for (const key of keys) {
    if (!current || typeof current !== "object") return "";
    current = (current as Record<string, unknown>)[key];
  }
  return current === null || current === undefined ? "" : String(current);
}

export function getRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

export function getDateRange(value: unknown): { start: string; end: string } | null {
  const record = getRecord(value);
  const start = String(record.start ?? "");
  const end = String(record.end ?? start);
  if (
    !start ||
    !end ||
    Number.isNaN(parseLocalDate(start).getTime()) ||
    Number.isNaN(parseLocalDate(end).getTime()) ||
    end < start
  ) {
    return null;
  }
  return { start, end };
}

export function dateRangeLabel(start: string, end: string) {
  return start === end ? start : `${start} a ${end}`;
}

export function temporalChartData(
  rows: TemporalRow[],
  comparisonRows: ScenarioComparisonRow[],
  showReal: boolean
): ChartData<"line", (number | null)[], string> {
  const isWeek = rows.some((row) => row.label.includes("-W"));
  const comparisonByLabel = new Map<string, number>();
  for (const row of comparisonRows) {
    if (row.level !== "network_date" || !row.target_date) continue;
    const label = isWeek ? weekLabel(row.target_date) : row.target_date;
    const current = comparisonByLabel.get(label) ?? 0;
    comparisonByLabel.set(label, current + row.base_y_pred);
  }

  const datasets: ChartDataset<"line", (number | null)[]>[] = [
    {
      label: "Viajeros previstos",
      data: rows.map((row) => row.y_pred),
      borderColor: "#DC241F",
      backgroundColor: "#DC241F",
      tension: 0.25
    }
  ];
  if (rows.some((row) => row.y_real !== null && row.y_real !== undefined)) {
    datasets.push({
      label: "Viajeros reales",
      data: rows.map((row) => row.y_real ?? null) as unknown as number[],
      borderColor: "#241716",
      backgroundColor: "#241716",
      tension: 0.2,
      hidden: !showReal
    });
  }
  if (comparisonByLabel.size) {
    datasets.push({
      label: "Escenario base",
      data: rows.map((row) => comparisonByLabel.get(row.label) ?? null) as unknown as number[],
      borderColor: "#6B130C",
      backgroundColor: "#6B130C",
      tension: 0.25
    });
  }
  return { labels: rows.map((row) => row.label), datasets };
}

export function rankingChartData(
  rows: PredictionRow[],
  comparisonRows: ScenarioComparisonRow[]
): ChartData<"bar", (number | null)[], string> {
  const labels = rows.map((row) => row.estacion || row.station_abbrev);
  const comparisonByStation = new Map(comparisonRows.map((row) => [row.estacion, row]));
  const datasets: ChartDataset<"bar", (number | null)[]>[] = [
    {
      label: "Viajeros previstos",
      data: rows.map((row) => row.y_pred),
      backgroundColor: "#DC241F"
    }
  ];
  if (comparisonByStation.size) {
    datasets.push({
      label: "Escenario base",
      data: rows.map((row) => comparisonByStation.get(row.estacion)?.base_y_pred ?? null) as unknown as number[],
      backgroundColor: "#DBC8C2"
    });
  }
  return { labels, datasets };
}
