import type { EventDraft, EventVariable } from "../types";
import { nullableText } from "./formatters";

export const emptyEvent = (dateValue: string): EventDraft => ({
  event_id: `manual_${Date.now()}`,
  name: "",
  date_mode: "date_range",
  target_date: dateValue,
  end_date: dateValue,
  selected_dates: [dateValue],
  all_day: true,
  start_time: "",
  end_time: "",
  affected_stations: ["all"],
  event_type: "deportivo",
  impact_level: "medio",
  comment: "",
  origin_event_id: null,
  deleted: false,
});

export function eventDraftFromExternal(
  event: EventVariable | Record<string, unknown>,
  fallbackDate: string
): EventDraft {
  const eventRecord = event as Record<string, unknown>;
  const targetDate = String(eventRecord.target_date ?? eventRecord.date ?? fallbackDate);
  return {
    event_id: `manual_${Date.now()}`,
    name: String(eventRecord.name ?? eventRecord.title ?? "Evento"),
    date_mode: "date_range",
    target_date: targetDate,
    end_date: String(eventRecord.end_date ?? targetDate),
    selected_dates: [targetDate],
    all_day: !eventRecord.start_time && !eventRecord.end_time,
    start_time: String(eventRecord.start_time ?? ""),
    end_time: String(eventRecord.end_time ?? ""),
    affected_stations: Array.isArray(eventRecord.affected_stations)
      ? eventRecord.affected_stations.map(String)
      : ["all"],
    event_type: String(eventRecord.event_type ?? "otro"),
    impact_level: String(eventRecord.impact_level ?? "medio"),
    comment: String(
      eventRecord.comment ??
        eventRecord.source ??
        "Evento cargado automaticamente y editado como escenario"
    ),
    origin_event_id: String(eventRecord.event_id ?? ""),
    deleted: false,
  };
}

export function eventDraftsFromFinalEvents(rows: EventVariable[]): EventDraft[] {
  const grouped = new Map<string, EventDraft>();
  for (const row of rows) {
    const eventId = String(row.event_id ?? `manual_${row.target_date ?? Date.now()}`);
    const targetDate = String(row.target_date ?? "");
    if (row.start_date || row.end_date || row.date_mode) {
      grouped.set(eventId, {
        event_id: eventId,
        name: String(row.name ?? "Evento"),
        date_mode: row.date_mode === "selected_dates" ? "selected_dates" : "date_range",
        target_date: String(row.start_date ?? targetDate),
        end_date: String(row.end_date ?? row.start_date ?? targetDate),
        selected_dates: Array.isArray(row.selected_dates) ? row.selected_dates.map(String) : [],
        all_day: Boolean(row.all_day ?? (!row.start_time && !row.end_time)),
        start_time: String(row.start_time ?? ""),
        end_time: String(row.end_time ?? ""),
        affected_stations: Array.isArray(row.affected_stations) ? row.affected_stations.map(String) : ["all"],
        event_type: String(row.event_type ?? "otro"),
        impact_level: String(row.impact_level ?? "medio"),
        comment: String(row.comment ?? ""),
        origin_event_id: nullableText(row.origin_event_id),
        deleted: Boolean(row.deleted),
      });
      continue;
    }
    const current = grouped.get(eventId);
    if (current) {
      current.selected_dates = [...new Set([...current.selected_dates, targetDate])].filter(Boolean);
      current.date_mode = "selected_dates";
      continue;
    }
    grouped.set(eventId, {
      event_id: eventId,
      name: String(row.name ?? "Evento"),
      date_mode: "date_range",
      target_date: targetDate,
      end_date: targetDate,
      selected_dates: targetDate ? [targetDate] : [],
      all_day: !row.start_time && !row.end_time,
      start_time: String(row.start_time ?? ""),
      end_time: String(row.end_time ?? ""),
      affected_stations: Array.isArray(row.affected_stations) ? row.affected_stations.map(String) : ["all"],
      event_type: String(row.event_type ?? "otro"),
      impact_level: String(row.impact_level ?? "medio"),
      comment: String(row.comment ?? ""),
      origin_event_id: nullableText(row.origin_event_id),
      deleted: Boolean(row.deleted),
    });
  }
  return [...grouped.values()];
}

export function patchEventFromSlots(
  event: EventDraft,
  slots: Record<string, unknown>,
  mentioned: Set<string>
): EventDraft {
  const next = { ...event };
  if (mentioned.has("name") && typeof slots.name === "string") next.name = slots.name;
  if (mentioned.has("event_type") && typeof slots.event_type === "string") next.event_type = slots.event_type;
  if (mentioned.has("impact_level") && typeof slots.impact_level === "string") next.impact_level = slots.impact_level;
  if (mentioned.has("affected_stations") && Array.isArray(slots.affected_stations)) {
    next.affected_stations = slots.affected_stations.map(String);
  }
  if (mentioned.has("all_day")) next.all_day = Boolean(slots.all_day);
  if (mentioned.has("start_time")) next.start_time = String(slots.start_time ?? "");
  if (mentioned.has("end_time")) next.end_time = String(slots.end_time ?? "");
  if (mentioned.has("comment") && typeof slots.comment === "string") next.comment = slots.comment;
  return next;
}
