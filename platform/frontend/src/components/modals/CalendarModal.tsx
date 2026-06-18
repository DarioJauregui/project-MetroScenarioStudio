import { useState } from "react";
import { X, Plus, CloudRain, Trash2 } from "lucide-react";
import type { CalendarVariable, EventDraft, EventVariable } from "../../types";
import { weekdayName, eventDates } from "../../utils/formatters";
import { WeatherCompact } from "../common/WeatherCompact";

export function CalendarModal(props: {
  calendarRows: CalendarVariable[];
  manualEvents: EventDraft[];
  externalEvents: EventVariable[];
  weather: Array<Record<string, unknown>>;
  onClose: () => void;
  onUpdateDay: (targetDate: string, patch: Partial<CalendarVariable>) => void;
  onOpenEvent: (targetDate: string) => void;
  onEditManualEvent: (event: EventDraft) => void;
  onEditExternalEvent: (event: EventVariable) => void;
  onOpenWeather: (targetDates: string[]) => void;
  onDeleteManualEvent: (eventId: string) => void;
}) {
  const [selectedDates, setSelectedDates] = useState<string[]>([]);
  const weatherByDate = new Map(props.weather.map((item) => [String(item.target_date), item]));
  const selectedRows = props.calendarRows.filter((row) => selectedDates.includes(row.target_date));
  const selectedAllHoliday = selectedRows.length > 0 && selectedRows.every((row) => row.is_holiday);

  function toggleDate(value: string) {
    setSelectedDates((current) =>
      current.includes(value) ? current.filter((item) => item !== value) : [...current, value]
    );
  }

  function applyBulk(patch: Partial<CalendarVariable>) {
    for (const dateValue of selectedDates) {
      props.onUpdateDay(dateValue, patch);
    }
  }

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true">
      <section className="modal calendar-modal">
        <div className="section-heading">
          <h2>Calendario del rango</h2>
          <button type="button" className="icon-button" onClick={props.onClose} title="Cerrar">
            <X size={18} />
          </button>
        </div>
        <div className="bulk-editor">
          <strong>{selectedDates.length} dias seleccionados</strong>
          <button
            type="button"
            disabled={!selectedDates.length}
            onClick={() => applyBulk({ is_holiday: !selectedAllHoliday })}
          >
            {selectedAllHoliday ? "Desmarcar festivo" : "Marcar festivo"}
          </button>
          <button type="button" onClick={() => props.onOpenEvent(selectedDates[0] ?? props.calendarRows[0]?.target_date)}>
            <Plus size={16} />
            Anadir evento
          </button>
          <button
            type="button"
            disabled={!selectedDates.length}
            onClick={() => props.onOpenWeather(selectedDates)}
          >
            <CloudRain size={16} />
            Modificar meteorologia
          </button>
        </div>
        <div className="calendar-table-wrap">
          <table>
            <thead>
              <tr>
                <th></th>
                <th>Dia</th>
                <th>Dia semana</th>
                <th>Festivo</th>
                <th>Eventos</th>
                <th>Meteorologia</th>
                <th>Acciones</th>
              </tr>
            </thead>
            <tbody>
              {props.calendarRows.map((row) => {
                const manualEvents = props.manualEvents.filter(
                  (event) => event.name.trim() && eventDates(event).includes(row.target_date)
                );
                const externalEvents = props.externalEvents.filter(
                  (event) => String(event.target_date) === row.target_date
                );
                const weather = weatherByDate.get(row.target_date);
                return (
                  <tr key={row.target_date}>
                    <td>
                      <input
                        type="checkbox"
                        checked={selectedDates.includes(row.target_date)}
                        onChange={() => toggleDate(row.target_date)}
                      />
                    </td>
                    <td>{row.target_date}</td>
                    <td>
                      <span className="weekday-pill">{weekdayName(row.target_date)}</span>
                    </td>
                    <td>{row.is_holiday ? row.special_day || "Si" : "No"}</td>
                    <td>
                      <div className="event-chip-list">
                        {externalEvents.map((event, index) => (
                          <button
                            key={`${String(event.event_id ?? event.name ?? "external")}-${index}`}
                            type="button"
                            className="event-chip external"
                            onClick={() => props.onEditExternalEvent(event)}
                            title="Editar como evento del escenario"
                          >
                            {String(event.name ?? "Evento")}
                          </button>
                        ))}
                        {manualEvents.map((event) => (
                          <span key={event.event_id} className="event-chip-group">
                            <button
                              type="button"
                              className="event-chip"
                              onClick={() => props.onEditManualEvent(event)}
                              title="Editar evento"
                            >
                              {event.name}
                            </button>
                            <button
                              type="button"
                              className="event-chip-delete"
                              onClick={() => props.onDeleteManualEvent(event.event_id)}
                              title="Eliminar evento"
                            >
                              <Trash2 size={13} />
                            </button>
                          </span>
                        ))}
                        {!externalEvents.length && !manualEvents.length ? (
                          <span className="muted">Sin eventos</span>
                        ) : null}
                      </div>
                    </td>
                    <td>{weather ? <WeatherCompact weather={weather} /> : "Sin dato"}</td>
                    <td className="table-actions">
                      <button type="button" onClick={() => props.onOpenEvent(row.target_date)}>
                        <Plus size={16} />
                        Evento
                      </button>
                      <button type="button" onClick={() => props.onOpenWeather([row.target_date])}>
                        <CloudRain size={16} />
                        Meteo
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
