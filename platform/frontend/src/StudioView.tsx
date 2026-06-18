import { useEffect, useMemo, useRef, useState } from "react";
import {
  CalendarDays,
  Brain,
  History,
  Save,
  Play,
  Download,
  Sparkles,
  Settings,
  Info,
  LoaderCircle,
} from "lucide-react";

import {
  compareScenarios,
  createScenario,
  downloadScenarioExcel,
  getExternalData,
  explainScenario,
  getScenarioArtifacts,
  getScenarioAudit,
  getScenarioResult,
  getStations,
  listScenarios,
  parseComment,
  runScenario,
  updateScenario,
  uploadImport,
} from "./api";
import type {
  AuditEvent,
  CalendarVariable,
  ExcelArtifact,
  ExecutionResult,
  ExternalDataSnapshot,
  LlmParseResult,
  PredictionRow,
  ScenarioComparison,
  ScenarioExecution,
  StationCatalogItem,
  ExecutionIntent,
  ResultsTab,
  TimeGrouping,
  SortDirection,
  NluFeedback,
  EventDraft,
  WeatherOverride,
  WeatherFormState,
} from "./types";

import {
  datesBetween,
  statusLabel,
  groupTemporalRows,
  getRecord,
  getDateRange,
  dateRangeLabel,
  warningText,
} from "./utils/formatters";

import {
  emptyEvent,
  eventDraftFromExternal,
  eventDraftsFromFinalEvents,
  patchEventFromSlots,
} from "./utils/eventHelpers";

import {
  emptyWeatherForm,
  mergeWeatherRows,
  weatherFormFromSource,
  weatherOverrideFromForm,
  weatherOverridesFromFinal,
} from "./utils/weatherHelpers";

import { StatusBadge } from "./components/common/StatusBadge";
import { ToastStack } from "./components/common/ToastStack";
import { Accordion } from "./components/common/Accordion";
import { SectionTitle } from "./components/common/SectionTitle";
import { Metric } from "./components/common/Metric";
import { NluFeedbackBox } from "./components/common/NluFeedbackBox";
import { TraceList } from "./components/common/TraceList";
import { ComparisonPanel } from "./components/history/ComparisonPanel";
import { ResultsPanel } from "./components/scenarios/ResultsPanel";
import { TraceabilityPanel } from "./components/scenarios/TraceabilityPanel";
import { CalendarModal } from "./components/modals/CalendarModal";
import { EventModal } from "./components/modals/EventModal";
import { ComparisonDiffModal } from "./components/modals/ComparisonDiffModal";
import { WeatherModal } from "./components/modals/WeatherModal";
import { HistoryDrawer } from "./components/history/HistoryDrawer";

const getTodayString = () => {
  const d = new Date();
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
};

const getTwoWeeksLaterString = () => {
  const d = new Date();
  d.setDate(d.getDate() + 14);
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
};

const defaultStart = getTodayString();
const defaultEnd = getTwoWeeksLaterString();

export function StudioView() {
  const [rangeStart, setRangeStart] = useState(defaultStart);
  const [rangeEnd, setRangeEnd] = useState(defaultEnd);
  const [executionIntent, setExecutionIntent] = useState<ExecutionIntent>("base");
  const [comment, setComment] = useState("");
  const [events, setEvents] = useState<EventDraft[]>([emptyEvent(defaultStart)]);
  const [eventModalOpen, setEventModalOpen] = useState(false);
  const [calendarModalOpen, setCalendarModalOpen] = useState(false);
  const [comparisonDiffOpen, setComparisonDiffOpen] = useState(false);
  const [weatherModalDates, setWeatherModalDates] = useState<string[]>([]);
  const [eventForm, setEventForm] = useState<EventDraft>(emptyEvent(defaultStart));
  const [editingEventId, setEditingEventId] = useState<string | null>(null);
  const [eventModalIsEditing, setEventModalIsEditing] = useState(false);
  const [weatherForm, setWeatherForm] = useState<WeatherFormState>(emptyWeatherForm);
  const [stations, setStations] = useState<StationCatalogItem[]>([]);
  const [calendarOverrides, setCalendarOverrides] = useState<Record<string, Partial<CalendarVariable>>>({});
  const [weatherOverrides, setWeatherOverrides] = useState<Record<string, WeatherOverride>>({});
  const [acceptedLlm, setAcceptedLlm] = useState(false);
  const [scenarioId, setScenarioId] = useState<string | null>(null);
  const [externalData, setExternalData] = useState<ExternalDataSnapshot | null>(null);
  const [llmResult, setLlmResult] = useState<LlmParseResult | null>(null);
  const [nluFeedback, setNluFeedback] = useState<NluFeedback | null>(null);
  const [nluBusy, setNluBusy] = useState(false);
  const [result, setResult] = useState<ExecutionResult | null>(null);
  const [auditEvents, setAuditEvents] = useState<AuditEvent[]>([]);
  const [artifacts, setArtifacts] = useState<ExcelArtifact[]>([]);
  const [history, setHistory] = useState<ScenarioExecution[]>([]);
  const [showHistory, setShowHistory] = useState(false);
  const [comparisonEnabled, setComparisonEnabled] = useState(false);
  const [compareBaseId, setCompareBaseId] = useState("");
  const [compareCandidateId, setCompareCandidateId] = useState("");
  const [comparison, setComparison] = useState<ScenarioComparison | null>(null);
  const [comparisonBaseResult, setComparisonBaseResult] = useState<ExecutionResult | null>(null);
  const [comparisonCandidateResult, setComparisonCandidateResult] = useState<ExecutionResult | null>(null);
  const [comparisonWarning, setComparisonWarning] = useState<string | null>(null);
  const [resultsTab, setResultsTab] = useState<ResultsTab>("summary");
  const [timeGrouping, setTimeGrouping] = useState<TimeGrouping>("day");
  const [detailFilter, setDetailFilter] = useState("");
  const [detailSort, setDetailSort] = useState<{ key: keyof PredictionRow; direction: SortDirection }>({
    key: "y_pred",
    direction: "desc",
  });
  const [exportPath, setExportPath] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const importInputRef = useRef<HTMLInputElement | null>(null);

  const calendarRows = useMemo(
    () =>
      (externalData?.calendar ?? []).map((row) => ({
        ...row,
        ...(calendarOverrides[row.target_date] ?? {}),
        modified: Boolean(calendarOverrides[row.target_date]?.modified ?? row.modified),
      })),
    [calendarOverrides, externalData]
  );

  const networkTotal = useMemo(
    () => result?.aggregates.find((row) => row.level === "network" && !row.target_date),
    [result]
  );

  const weatherRows = useMemo(
    () => mergeWeatherRows(externalData?.weather ?? [], weatherOverrides),
    [externalData, weatherOverrides]
  );

  const comparisonNetwork = useMemo(
    () => comparison?.rows.find((row) => row.level === "network"),
    [comparison]
  );

  const temporalRows = useMemo(
    () => groupTemporalRows(result?.aggregates.filter((row) => row.level === "network_date") ?? [], timeGrouping),
    [result, timeGrouping]
  );

  const stationRanking = useMemo(
    () => stationRankingRows(result?.prediction_rows ?? []),
    [result]
  );

  const filteredDetailRows = useMemo(() => {
    const filter = detailFilter.trim().toLowerCase();
    return [...(result?.prediction_rows ?? [])]
      .filter((row) =>
        filter ? `${row.linea} ${row.estacion} ${row.station_abbrev}`.toLowerCase().includes(filter) : true
      )
      .sort((a, b) => compareValues(a[detailSort.key], b[detailSort.key], detailSort.direction));
  }, [detailFilter, detailSort, result]);

  const confidence = useMemo(() => {
    if (!result) return "Pendiente";
    const warnings = result.execution?.warnings ?? [];
    if (warnings.length > 2) return "Baja";
    if (warnings.length > 0) return "Media";
    return "Alta";
  }, [result]);

  const hasScenarioChanges = useMemo(
    () =>
      acceptedLlm ||
      events.some((item) => item.name.trim()) ||
      calendarRows.some((row) => row.modified) ||
      Object.keys(weatherOverrides).length > 0,
    [acceptedLlm, calendarRows, events, weatherOverrides]
  );

  useEffect(() => {
    if (!notice && !error) return undefined;
    const timer = window.setTimeout(
      () => {
        setNotice(null);
        setError(null);
      },
      error ? 9000 : 6500
    );
    return () => window.clearTimeout(timer);
  }, [error, notice]);

  const visibleStatus = useMemo(() => {
    if (executionIntent === "importada") return "importada";
    if (hasScenarioChanges) return "what_if";
    if (result?.execution?.status) return result.execution.status;
    return "base";
  }, [executionIntent, hasScenarioChanges, result]);

  async function loadExternalData(selectedStart = rangeStart, selectedEnd = rangeEnd) {
    setBusy(true);
    setError(null);
    try {
      const snapshot = await getExternalData(selectedStart, selectedEnd);
      setExternalData(snapshot);
      setNotice("Variables externas actualizadas para el rango seleccionado.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al cargar variables externas");
    } finally {
      setBusy(false);
    }
  }

  async function refreshHistory() {
    try {
      setHistory(await listScenarios());
    } catch {
      setHistory([]);
    }
  }

  async function refreshStations() {
    try {
      setStations(await getStations());
    } catch {
      setStations([]);
    }
  }

  async function interpretComment() {
    setNluBusy(true);
    setError(null);
    setNluFeedback(null);
    try {
      const parsed = await parseComment(comment, rangeStart, rangeEnd);
      setLlmResult(parsed);
      const feedback = applyNluResult(parsed);
      setNluFeedback(feedback);
      setAcceptedLlm(feedback.applied.length > 0);
      if (feedback.tone === "error") {
        setError(feedback.messages[0] ?? "No se pudo aplicar la instruccion NLU.");
      } else {
        setNotice("Comentario interpretado y aplicado al formulario. Revisa los cambios antes de guardar.");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al interpretar comentario");
    } finally {
      setNluBusy(false);
    }
  }

  async function saveDraft() {
    setBusy(true);
    setError(null);
    try {
      const scenario = scenarioId
        ? await updateScenario(scenarioId, buildScenarioPayload())
        : await createScenario(buildScenarioPayload());
      setScenarioId(scenario.id);
      setNotice(`Escenario guardado como borrador: ${scenario.id}`);
      await refreshHistory();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al guardar escenario");
    } finally {
      setBusy(false);
    }
  }

  async function executeScenario() {
    setBusy(true);
    setError(null);
    try {
      const scenario = scenarioId
        ? await updateScenario(scenarioId, buildScenarioPayload())
        : await createScenario(buildScenarioPayload());
      setScenarioId(scenario.id);
      const executionResult = await runScenario(scenario.id);
      setResult(executionResult);
      setExecutionIntent(executionResult.execution.status === "what_if" ? "what_if" : "base");
      hydrateUiFromExecution(executionResult.execution);
      setExportPath(null);
      setBusy(false);

      // Fetch traceability and history asynchronously in background
      void loadTraceability(executionResult.execution.id);
      void refreshHistory();
      setNotice("Prediccion ejecutada y guardada con trazabilidad.");

      if (executionResult.narrative_summary === "__GENERATING__") {
        void (async () => {
          try {
            const explainedResult = await explainScenario(scenario.id);
            setResult((prev) => {
              if (prev && prev.execution.id === executionResult.execution.id) {
                return explainedResult;
              }
              return prev;
            });
            void refreshHistory();
          } catch (e) {
            console.error("Error generating scenario explanation:", e);
            setResult((prev) => {
              if (prev && prev.execution.id === executionResult.execution.id) {
                return { ...prev, narrative_summary: "Error al generar la explicación con IA." };
              }
              return prev;
            });
          }
        })();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al ejecutar prediccion");
      setBusy(false);
    }
  }

  async function exportCurrentScenario() {
    if (!result) return;
    setBusy(true);
    setError(null);
    try {
      await downloadScenarioExcel(result.execution.id);
      setExportPath(`${result.execution.id}.xlsx descargado`);
      await loadTraceability(result.execution.id);
      setNotice("Prediccion exportada y descargada como Excel estructurado.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al exportar Excel");
    } finally {
      setBusy(false);
    }
  }

  async function importExcel(file: File | null) {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const imported = await uploadImport(file);
      setResult(imported);
      if (imported?.execution) {
        setScenarioId(imported.execution.id);
        setRangeStart(imported.execution.range_start);
        setRangeEnd(imported.execution.range_end);
        setComment(imported.execution.comment ?? imported.execution.input?.natural_language_comment ?? "");
        setExecutionIntent("importada");
        hydrateUiFromExecution(imported.execution);
        await loadTraceability(imported.execution.id);
      }
      await refreshHistory();
      setNotice(`Prediccion importada: ${imported.execution.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al importar Excel");
    } finally {
      setBusy(false);
    }
  }

  async function openHistoryItem(id: string) {
    setBusy(true);
    setError(null);
    try {
      const loaded = await getScenarioResult(id);
      setResult(loaded);
      setScenarioId(id);
      if (loaded?.execution) {
        setRangeStart(loaded.execution.range_start);
        setRangeEnd(loaded.execution.range_end);
        setComment(loaded.execution.comment ?? loaded.execution.input?.natural_language_comment ?? "");
        setExecutionIntent(
          loaded.execution.status === "importada"
            ? "importada"
            : loaded.execution.status === "what_if"
              ? "what_if"
              : "base"
        );
        hydrateUiFromExecution(loaded.execution);
        await loadTraceability(id);
      }
      setNotice(`Prediccion abierta como referencia: ${id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "No hay resultado almacenado para esa prediccion");
    } finally {
      setBusy(false);
    }
  }

  async function createDerivedFromHistory(id: string) {
    setBusy(true);
    setError(null);
    try {
      const response = await fetch(`/api/scenarios/${id}/derive`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ comment: "Copia derivada editable" }),
      });
      if (!response.ok) throw new Error(await response.text());
      const derived = (await response.json()) as ScenarioExecution;
      setScenarioId(derived.id);
      setRangeStart(derived.range_start);
      setRangeEnd(derived.range_end);
      setComment(derived.comment ?? derived.input?.natural_language_comment ?? "");
      hydrateUiFromExecution(derived);
      setResult(null);
      setExecutionIntent("what_if");
      setNotice(`Derivada creada: ${derived.id}`);
      await refreshHistory();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al crear derivada");
    } finally {
      setBusy(false);
    }
  }

  async function loadTraceability(id: string) {
    const [audit, artifactRows] = await Promise.all([
      getScenarioAudit(id).catch(() => []),
      getScenarioArtifacts(id).catch(() => []),
    ]);
    setAuditEvents(audit);
    setArtifacts(artifactRows);
  }

  async function compareSelectedScenarios() {
    if (!compareBaseId || !compareCandidateId) {
      setError("Selecciona una prediccion base y una candidata para comparar.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const [baseResult, candidateResult] = await Promise.all([
        getScenarioResult(compareBaseId),
        getScenarioResult(compareCandidateId),
      ]);
      setComparisonBaseResult(baseResult);
      setComparisonCandidateResult(candidateResult);
      if (
        baseResult.execution.range_start !== candidateResult.execution.range_start ||
        baseResult.execution.range_end !== candidateResult.execution.range_end
      ) {
        setComparisonWarning(
          "Las predicciones no cubren exactamente los mismos dias; interpreta la diferencia con cautela."
        );
      } else {
        setComparisonWarning(null);
      }
      const payload = await compareScenarios(compareBaseId, compareCandidateId);
      setComparison(payload);
      setResult(candidateResult);
      setScenarioId(compareCandidateId);
      if (candidateResult?.execution) {
        setRangeStart(candidateResult.execution.range_start);
        setRangeEnd(candidateResult.execution.range_end);
        setComment(candidateResult.execution.comment ?? candidateResult.execution.input?.natural_language_comment ?? "");
        setExecutionIntent(
          candidateResult.execution.status === "importada"
            ? "importada"
            : candidateResult.execution.status === "what_if"
              ? "what_if"
              : "base"
        );
        hydrateUiFromExecution(candidateResult.execution);
      }
      setNotice("Comparacion calculada. Recuerda que no representa causalidad.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al comparar escenarios");
    } finally {
      setBusy(false);
    }
  }

  function hydrateUiFromExecution(execution: ScenarioExecution) {
    if (!execution) return;
    const input = execution.input;
    if (!input?.calendar_final?.length && !input?.weather_final?.length && !input?.events_final?.length) {
      void loadExternalData(execution.range_start, execution.range_end);
      return;
    }
    const automaticEvents = (input.events_final ?? []).filter((item) => !item.modified);
    const manualEvents = eventDraftsFromFinalEvents((input.events_final ?? []).filter((item) => item.modified));
    setCalendarOverrides(Object.fromEntries((input.calendar_final ?? []).map((item) => [item.target_date, item])));
    setEvents(manualEvents);
    setWeatherOverrides(weatherOverridesFromFinal(input.weather_final ?? []));
    setExternalData({
      range_start: execution.range_start,
      range_end: execution.range_end,
      calendar: input.calendar_final ?? [],
      events: automaticEvents,
      weather: input.weather_final ?? [],
      coverage: {
        calendar_days: input.calendar_final?.length ?? 0,
        event_days: new Set((input.events_final ?? []).map((item) => String(item.target_date))).size,
        weather_days: input.weather_final?.length ?? 0,
        total_days: datesBetween(execution.range_start, execution.range_end).length,
      },
      warnings: (execution?.warnings ?? []).map((code) => ({ code, message: warningText(code), severity: "warning" })),
    });
  }

  function updateCalendarOverride(targetDate: string, patch: Partial<CalendarVariable>) {
    setCalendarOverrides((current) => ({
      ...current,
      [targetDate]: {
        ...(current[targetDate] ?? {}),
        ...patch,
        modified: true,
        source: "manual_scenario",
      },
    }));
    setExecutionIntent("what_if");
  }

  function updateWeatherOverride(targetDate: string, patch: WeatherOverride) {
    setWeatherOverrides((current) => ({ ...current, [targetDate]: patch }));
    setExecutionIntent("what_if");
  }

  function openWeatherModal(dates: string[]) {
    const selected = dates.filter(Boolean);
    if (!selected.length) {
      setError("Selecciona al menos un dia para modificar meteorologia.");
      return;
    }
    const firstDate = selected[0];
    const automatic =
      weatherRows.find((item) => String(item.target_date) === firstDate) ??
      externalData?.weather.find((item) => String(item.target_date) === firstDate);
    const override = weatherOverrides[firstDate];
    setWeatherForm(
      weatherFormFromSource({
        ...(automatic ?? {}),
        ...(override ?? {}),
      })
    );
    setWeatherModalDates(selected);
  }

  function saveWeatherModal() {
    for (const dateValue of weatherModalDates) {
      updateWeatherOverride(dateValue, weatherOverrideFromForm(weatherForm));
    }
    setWeatherModalDates([]);
    setNotice("Meteorologia modificada para el escenario.");
  }

  function saveEventFromModal() {
    if (!eventForm.name.trim()) {
      setError("El evento necesita un nombre.");
      return;
    }
    if (eventForm.date_mode === "selected_dates" && eventForm.selected_dates.length === 0) {
      setError("Selecciona al menos una fecha del rango.");
      return;
    }
    if (eventForm.date_mode === "date_range" && eventForm.end_date < eventForm.target_date) {
      setError("La fecha fin del evento no puede ser anterior a la fecha inicio.");
      return;
    }
    setEvents((current) => {
      const savedEvent = { ...eventForm, event_id: eventForm.event_id || `manual_${Date.now()}` };
      if (editingEventId) {
        return current.map((event) => (event.event_id === editingEventId ? savedEvent : event));
      }
      return [...current, savedEvent];
    });
    setExecutionIntent("what_if");
    setEditingEventId(null);
    setEventModalIsEditing(false);
    setEventForm(emptyEvent(rangeStart));
    setEventModalOpen(false);
    setNotice(editingEventId ? "Evento actualizado en el escenario." : "Evento anadido al escenario.");
  }

  function deleteEventFromModal() {
    if (!editingEventId) return;
    setEvents((current) => current.filter((event) => event.event_id !== editingEventId));
    setExecutionIntent("what_if");
    setEditingEventId(null);
    setEventModalIsEditing(false);
    setEventForm(emptyEvent(rangeStart));
    setEventModalOpen(false);
    setNotice("Evento eliminado del escenario.");
  }

  function applyNluResult(parsed: LlmParseResult): NluFeedback {
    const blocked = parsed.not_used.map((item) => `${item.text}: ${item.reason}`);
    if (!parsed.detected_items.length) {
      return {
        tone: "error",
        messages: blocked.length ? blocked : ["No se ha encontrado ningun cambio seguro para aplicar."],
        applied: [],
      };
    }

    const applied: string[] = [];
    const rejected: string[] = [...blocked];
    for (const item of parsed.detected_items) {
      const payload = getRecord(item.payload);
      const domain = String(payload.domain ?? "");
      const intent = String(payload.intent ?? "");
      const dateRange = getDateRange(payload.date_range);
      const slots = getRecord(payload.slots);
      const mentioned = new Set(Array.isArray(payload.mentioned_fields) ? payload.mentioned_fields.map(String) : []);
      if (!dateRange) {
        rejected.push("Debes indicar el dia o rango de dias al que quieres aplicar el cambio o cambios.");
        continue;
      }
      if (domain === "meteorologia" && intent === "modificar_meteorologia") {
        const dates = datesBetween(dateRange.start, dateRange.end);
        applyNluWeather(dates, slots, mentioned);
        applied.push(`Meteorologia actualizada para ${dateRangeLabel(dateRange.start, dateRange.end)}.`);
        continue;
      }
      if (domain === "calendario" && intent === "marcar_festivo") {
        const dates = datesBetween(dateRange.start, dateRange.end);
        applyNluCalendar(dates, slots, mentioned);
        applied.push(`Calendario marcado para ${dateRangeLabel(dateRange.start, dateRange.end)}.`);
        continue;
      }
      if (domain === "eventos") {
        const eventFeedback = applyNluEvent(intent, dateRange, slots, mentioned, String(item.name ?? comment));
        if (eventFeedback.applied) {
          applied.push(eventFeedback.message);
        } else {
          rejected.push(eventFeedback.message);
        }
      }
    }
    if (applied.length) {
      setExecutionIntent("what_if");
    }
    return {
      tone: applied.length ? "success" : "error",
      messages: rejected,
      applied,
    };
  }

  function applyNluWeather(dates: string[], slots: Record<string, unknown>, mentioned: Set<string>) {
    setWeatherOverrides((current) => {
      const next = { ...current };
      for (const targetDate of dates) {
        const automatic =
          weatherRows.find((item) => String(item.target_date) === targetDate) ??
          externalData?.weather.find((item) => String(item.target_date) === targetDate);
        const base = weatherFormFromSource({
          ...(automatic ?? {}),
          ...(current[targetDate] ?? {}),
        });
        const patch: WeatherFormState = { ...base };
        for (const field of mentioned) {
          if (!(field in slots)) continue;
          const value = slots[field];
          if (
            field === "rain" ||
            field === "heavy_rain" ||
            field === "hot_day" ||
            field === "cold_day" ||
            field === "bad_weather"
          ) {
            patch[field] = Boolean(value);
          }
          if (
            field === "approx_temperature" ||
            field === "temp_min" ||
            field === "temp_mean" ||
            field === "temp_max" ||
            field === "precip_mm" ||
            field === "rain_hours" ||
            field === "wind" ||
            field === "humidity"
          ) {
            patch[field] = value === null || value === undefined ? "" : String(value);
          }
          if (field === "weather_code" || field === "alert_level" || field === "alert_summary") {
            patch[field] = value === null || value === undefined ? "" : String(value);
          }
        }
        next[targetDate] = weatherOverrideFromForm(patch);
      }
      return next;
    });
  }

  function applyNluCalendar(dates: string[], slots: Record<string, unknown>, mentioned: Set<string>) {
    if (!mentioned.has("is_holiday")) return;
    setCalendarOverrides((current) => {
      const next = { ...current };
      for (const targetDate of dates) {
        next[targetDate] = {
          ...(next[targetDate] ?? {}),
          is_holiday: Boolean(slots.is_holiday),
          modified: true,
          source: "manual_scenario",
        };
      }
      return next;
    });
  }

  function applyNluEvent(
    intent: string,
    dateRange: { start: string; end: string },
    slots: Record<string, unknown>,
    mentioned: Set<string>,
    fallbackName: string
  ): { applied: boolean; message: string } {
    const eventTypesList = ["deportivo", "cultural", "universitario", "religioso", "feria/congreso", "otro"];
    const impactLevelsList = ["bajo", "medio", "alto", "muy alto"];
    if (intent === "crear_evento") {
      const draft: EventDraft = {
        event_id: `nlu_${Date.now()}`,
        name: String(slots.name ?? (fallbackName === "Evento sin nombre" ? fallbackName : "Evento sin nombre")).slice(
          0,
          90
        ),
        date_mode: "date_range",
        target_date: dateRange.start,
        end_date: dateRange.end,
        selected_dates: [dateRange.start],
        all_day: mentioned.has("all_day") ? Boolean(slots.all_day) : true,
        start_time: mentioned.has("start_time") ? String(slots.start_time ?? "") : "",
        end_time: mentioned.has("end_time") ? String(slots.end_time ?? "") : "",
        affected_stations: Array.isArray(slots.affected_stations) ? slots.affected_stations.map(String) : [],
        event_type: eventTypesList.includes(String(slots.event_type ?? "")) ? String(slots.event_type) : "otro",
        impact_level: impactLevelsList.includes(String(slots.impact_level ?? ""))
          ? String(slots.impact_level)
          : "medio",
        comment: `Creado desde NLU: ${comment}`,
        origin_event_id: null,
        deleted: false,
      };
      setEvents((current) => [...current, draft]);
      return { applied: true, message: `Evento creado para ${dateRangeLabel(dateRange.start, dateRange.end)}.` };
    }

    const matchesDate = (event: EventDraft) =>
      event.date_mode === "selected_dates"
        ? event.selected_dates.some((dateValue) => dateValue >= dateRange.start && dateValue <= dateRange.end)
        : datesBetween(event.target_date, event.end_date).some(
            (dateValue) => dateValue >= dateRange.start && dateValue <= dateRange.end
          );
    const matchingEvents = events.filter(matchesDate);
    if (!matchingEvents.length) {
      return {
        applied: false,
        message: `No hay evento manual existente en ${dateRangeLabel(dateRange.start, dateRange.end)} para ${intent}.`,
      };
    }
    if (intent === "eliminar_evento") {
      setEvents((current) => current.filter((event) => !matchesDate(event)));
      return { applied: true, message: `Evento eliminado para ${dateRangeLabel(dateRange.start, dateRange.end)}.` };
    }
    if (intent === "modificar_evento") {
      setEvents((current) =>
        current.map((event) => (matchesDate(event) ? patchEventFromSlots(event, slots, mentioned) : event))
      );
      return { applied: true, message: `Evento modificado para ${dateRangeLabel(dateRange.start, dateRange.end)}.` };
    }
    return { applied: false, message: `Intent no soportado: ${intent}.` };
  }

  function buildScenarioPayload() {
    const replacedAutomaticEventIds = new Set(events.map((item) => item.origin_event_id).filter(Boolean).map(String));
    const automaticEventPayload = (externalData?.events ?? [])
      .filter((item) => !replacedAutomaticEventIds.has(String(item.event_id)))
      .map((item) => ({
        ...item,
        modified: false,
        used_by_model: Boolean(item.used_by_model ?? true),
      }));
    const eventPayload = events
      .filter((item) => item.name.trim())
      .map((item) => ({
        event_id: item.event_id,
        name: item.name.trim(),
        target_date: item.target_date,
        date_mode: item.date_mode === "selected_dates" ? "selected_dates" : "range",
        start_date: item.date_mode === "date_range" ? item.target_date : null,
        end_date: item.date_mode === "date_range" ? item.end_date : null,
        selected_dates: item.date_mode === "selected_dates" ? item.selected_dates : [],
        all_day: item.all_day,
        start_time: item.start_time || null,
        event_type: item.event_type,
        impact_level: item.impact_level,
        end_time: item.all_day ? null : item.end_time || null,
        affected_stations: item.affected_stations,
        comment: [
          item.comment || "Evento definido desde la interfaz",
          item.all_day
            ? "Duracion: todo el dia"
            : `Horario: ${item.start_time || "sin inicio"}-${item.end_time || "sin fin"}`,
          item.end_date !== item.target_date ? `Fin del evento: ${item.end_date}` : '',
        ]
          .filter(Boolean)
          .join(" | "),
        source: "usuario",
        origin_event_id: item.origin_event_id ?? null,
        deleted: Boolean(item.deleted),
        modified: true,
        used_by_model: true,
      }));

    return {
      range_start: rangeStart,
      range_end: rangeEnd,
      author: "local",
      comment,
      natural_language_comment: comment,
      manual_overrides: [
        ...Object.keys(weatherOverrides).map((target_date) => ({
          type: "weather",
          field: "daily_weather",
          target_date,
        })),
        ...eventPayload.map((item) => ({ type: "event", field: "event", value: item.name })),
        ...calendarRows
          .filter((row) => row.modified)
          .map((row) => ({ type: "calendar", field: "day_flags", target_date: row.target_date })),
      ],
      calendar_final: calendarRows,
      events_final: [...automaticEventPayload, ...eventPayload],
      weather_final: weatherRows,
      llm_accepted_items: acceptedLlm ? llmResult?.detected_items ?? [] : [],
    };
  }

  function onDateChange(nextStart: string, nextEnd: string) {
    setRangeStart(nextStart);
    setRangeEnd(nextEnd);
    setCalendarOverrides({});
    setWeatherOverrides({});
    setExecutionIntent("base");
    setResult(null);
    void loadExternalData(nextStart, nextEnd);
  }

  useEffect(() => {
    void loadExternalData();
    void refreshHistory();
    void refreshStations();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <main className="studio-shell">
      <header className="hero-bar">
        <div className="hero-mark" aria-hidden="true">
          <span />
          <span />
          <span />
        </div>
        <div className="hero-main">
          <p className="eyebrow">Metro Scenario Studio</p>
          <h1 className="hero-title-main">
            Metro Scenario Studio: <span>prediccion diaria y escenarios</span>
          </h1>
        </div>
        <div className="status-stack">
          <StatusBadge value={visibleStatus} />
          <span className="info-tooltip" tabIndex={0}>
            <Info size={17} />
            <span role="tooltip">
              Plataforma local para construir escenarios, ejecutar predicciones y conservar trazabilidad exportable.
            </span>
          </span>
        </div>
      </header>

      <ToastStack
        error={error}
        notice={notice}
        onCloseError={() => setError(null)}
        onCloseNotice={() => setNotice(null)}
      />

      <section className="operation-panel">
        <div className="date-grid">
          <label>
            Fecha inicio
            <input
              type="date"
              value={rangeStart}
              onChange={(event) => onDateChange(event.target.value, rangeEnd)}
            />
          </label>
          <label>
            Fecha fin
            <input type="date" value={rangeEnd} onChange={(event) => onDateChange(rangeStart, event.target.value)} />
          </label>
        </div>
        <div className="state-panel" aria-label="Tipo de predicción calculado">
          <span>Tipo de predicción: {statusLabel(visibleStatus)}</span>
        </div>
        <div className="action-group">
          <button type="button" onClick={() => setShowHistory(true)}>
            <History size={18} />
            Predicciones
          </button>
          <button type="button" onClick={saveDraft} disabled={busy}>
            <Save size={18} />
            Guardar escenario
          </button>
          <button type="button" className="primary" onClick={executeScenario} disabled={busy}>
            <Play size={18} />
            Ejecutar prediccion
          </button>
          <button type="button" onClick={exportCurrentScenario} disabled={!result || busy}>
            <Download size={18} />
            Exportar prediccion
          </button>
        </div>
      </section>

      <section className="workspace-grid">
        <aside className="scenario-panel">
          <SectionTitle
            icon={<Settings size={19} />}
            title="Escenario"
            subtitle="Variables externas y comentario del usuario"
          />

          <Accordion icon={<CalendarDays size={18} />} title="Calendario" badge={`${calendarRows.length} dias`}>
            <div className="coverage-strip">
              <Metric label="Calendario" value={externalData?.coverage.calendar_days ?? 0} />
              <Metric label="Eventos" value={externalData?.coverage.event_days ?? 0} />
              <Metric label="Meteorologia" value={externalData?.coverage.weather_days ?? 0} />
            </div>
            <div className="panel-actions">
              <button type="button" onClick={() => setCalendarModalOpen(true)}>
                <CalendarDays size={18} />
                Ver y editar dias del calendario
              </button>
            </div>
            {externalData?.warnings?.length ? (
              <details className="calendar-warnings-details">
                <summary>Advertencias a tener en cuenta en la predicción ({externalData.warnings?.length ?? 0})</summary>
                <ul className="warning-list">
                  {(externalData?.warnings ?? []).map((warning) => (
                    <li key={warning.code}>{warning.message}</li>
                  ))}
                </ul>
              </details>
            ) : null}
          </Accordion>

          <Accordion
            icon={<Brain size={18} />}
            title="¿Qué pasaría si...?"
            badge={acceptedLlm ? "validado" : "pendiente"}
          >
            <textarea
              value={comment}
              onChange={(event) => setComment(event.target.value)}
              placeholder="Introduce, indicando una fecha o rango de fechas, un supuesto en lenguaje natural para modificar eventos, meteorología, etc."
              aria-label="Supuesto en lenguaje natural"
            />
            <div className="panel-actions">
              <button type="button" onClick={interpretComment} disabled={busy || nluBusy} aria-busy={nluBusy}>
                <Sparkles size={18} />
                Interpretar comentario
                {nluBusy ? <LoaderCircle className="spin-icon" size={17} aria-hidden="true" /> : null}
              </button>
            </div>
            {llmResult && nluFeedback ? (
              <div className="llm-box">
                <NluFeedbackBox feedback={nluFeedback} />
              </div>
            ) : null}
          </Accordion>
        </aside>

        <section className="main-flow">
          <ComparisonPanel
            enabled={comparisonEnabled}
            history={history}
            baseId={compareBaseId}
            candidateId={compareCandidateId}
            comparison={comparison}
            warning={comparisonWarning}
            onToggle={setComparisonEnabled}
            onBaseChange={setCompareBaseId}
            onCandidateChange={setCompareCandidateId}
            onCompare={compareSelectedScenarios}
            onOpenDiff={() => setComparisonDiffOpen(true)}
          />

          <ResultsPanel
            result={result}
            networkTotal={networkTotal?.y_pred ?? 0}
            comparisonNetwork={comparisonEnabled ? comparisonNetwork : undefined}
            confidence={confidence}
            activeTab={resultsTab}
            onTabChange={setResultsTab}
            temporalRows={temporalRows}
            timeGrouping={timeGrouping}
            onTimeGroupingChange={setTimeGrouping}
            stationRanking={stationRanking}
            comparisonRows={comparisonEnabled ? comparison?.rows ?? [] : []}
            detailRows={filteredDetailRows}
            detailFilter={detailFilter}
            onDetailFilterChange={setDetailFilter}
            detailSort={detailSort}
            onDetailSort={setDetailSort}
            comparisonBaseResult={comparisonEnabled ? comparisonBaseResult : undefined}
          />

          <TraceabilityPanel
            result={result}
            llmResult={llmResult}
            acceptedLlm={acceptedLlm}
            auditEvents={auditEvents}
            artifacts={artifacts}
            exportPath={exportPath}
          />
        </section>
      </section>

      {calendarModalOpen ? (
        <CalendarModal
          calendarRows={calendarRows}
          manualEvents={events}
          externalEvents={externalData?.events ?? []}
          weather={weatherRows}
          onClose={() => setCalendarModalOpen(false)}
          onUpdateDay={updateCalendarOverride}
          onOpenEvent={(dateValue) => {
            setEditingEventId(null);
            setEventModalIsEditing(false);
            setEventForm(emptyEvent(dateValue));
            setEventModalOpen(true);
          }}
          onEditManualEvent={(event) => {
            setEditingEventId(event.event_id);
            setEventModalIsEditing(true);
            setEventForm(event);
            setEventModalOpen(true);
          }}
          onEditExternalEvent={(event) => {
            setEditingEventId(null);
            setEventModalIsEditing(true);
            setEventForm(eventDraftFromExternal(event, rangeStart));
            setEventModalOpen(true);
          }}
          onOpenWeather={openWeatherModal}
          onDeleteManualEvent={(eventId) => {
            setEvents((current) => current.filter((event) => event.event_id !== eventId));
            setExecutionIntent("what_if");
            setNotice("Evento eliminado del escenario.");
          }}
        />
      ) : null}
      {eventModalOpen ? (
        <EventModal
          value={eventForm}
          stations={stations}
          availableDates={calendarRows.map((row) => row.target_date)}
          rangeStart={rangeStart}
          rangeEnd={rangeEnd}
          isEditing={eventModalIsEditing}
          onChange={setEventForm}
          onClose={() => {
            setEditingEventId(null);
            setEventModalIsEditing(false);
            setEventModalOpen(false);
          }}
          onSave={saveEventFromModal}
          onDelete={editingEventId ? deleteEventFromModal : undefined}
        />
      ) : null}
      {comparisonDiffOpen ? (
        <ComparisonDiffModal
          baseResult={comparisonBaseResult}
          candidateResult={comparisonCandidateResult}
          onClose={() => setComparisonDiffOpen(false)}
        />
      ) : null}
      {weatherModalDates.length ? (
        <WeatherModal
          dates={weatherModalDates}
          value={weatherForm}
          onChange={setWeatherForm}
          onClose={() => setWeatherModalDates([])}
          onSave={saveWeatherModal}
        />
      ) : null}
      {showHistory ? (
        <HistoryDrawer
          history={history}
          importInputRef={importInputRef}
          onClose={() => setShowHistory(false)}
          onImportClick={() => importInputRef.current?.click()}
          onImport={importExcel}
          onOpen={openHistoryItem}
          onDerive={createDerivedFromHistory}
        />
      ) : null}
    </main>
  );
}

function stationRankingRows(rows: PredictionRow[]) {
  const byStation = new Map<string, PredictionRow>();
  for (const row of rows) {
    const key = row.estacion;
    const current = byStation.get(key);
    if (!current) {
      byStation.set(key, { ...row });
      continue;
    }
    byStation.set(key, {
      ...current,
      y_pred: current.y_pred + row.y_pred,
      y_real:
        current.y_real !== null && current.y_real !== undefined && row.y_real !== null && row.y_real !== undefined
          ? current.y_real + row.y_real
          : current.y_real ?? row.y_real ?? null,
    });
  }
  return [...byStation.values()].sort((a, b) => b.y_pred - a.y_pred);
}

function compareValues(a: unknown, b: unknown, direction: SortDirection) {
  const multiplier = direction === "asc" ? 1 : -1;
  if (typeof a === "number" && typeof b === "number") return (a - b) * multiplier;
  return String(a ?? "").localeCompare(String(b ?? "")) * multiplier;
}
export default StudioView;
