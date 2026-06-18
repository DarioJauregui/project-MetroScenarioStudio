import { X, Trash2 } from "lucide-react";
import type { EventDraft, StationCatalogItem } from "../../types";
import { shortLine } from "../../utils/formatters";
import { MultiCheckDropdown } from "../common/MultiCheckDropdown";

const eventTypes = ["deportivo", "cultural", "universitario", "religioso", "feria/congreso", "otro"];
const impactLevels = ["bajo", "medio", "alto", "muy alto"];

export function EventModal(props: {
  value: EventDraft;
  stations: StationCatalogItem[];
  availableDates: string[];
  rangeStart: string;
  rangeEnd: string;
  isEditing: boolean;
  onChange: (value: EventDraft) => void;
  onClose: () => void;
  onSave: () => void;
  onDelete?: () => void;
}) {
  const update = (patch: Partial<EventDraft>) => props.onChange({ ...props.value, ...patch });
  const stationOptions = [
    { series_id: "all", estacion: "Todas las estaciones", linea: "Red completa", station_abbrev: "all", network_order: -1 },
    ...props.stations,
  ];

  function updateSelectedOptions(values: string[]) {
    const previous = props.value.affected_stations;
    const selectedAllNow = values.includes("all") && !previous.includes("all");
    const selectedStationNow = values.some((value) => value !== "all" && !previous.includes(value));
    if (selectedAllNow) {
      update({ affected_stations: ["all"] });
      return;
    }
    if (selectedStationNow) {
      update({ affected_stations: values.filter((value) => value !== "all") });
      return;
    }
    update({
      affected_stations:
        values.includes("all") && values.length === 1
          ? ["all"]
          : values.filter((value) => value !== "all"),
    });
  }

  const dateOptions = props.availableDates.map((dateValue) => ({ value: dateValue, label: dateValue }));
  const stationDropdownOptions = stationOptions.map((station) => ({
    value: station.series_id,
    label: station.network_order >= 0 ? `${station.estacion} (${shortLine(station.linea)})` : station.estacion,
  }));

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true">
      <section className="modal">
        <div className="section-heading">
          <h2>{props.isEditing ? "Editar evento" : "Anadir evento"}</h2>
          <button type="button" className="icon-button" onClick={props.onClose} title="Cerrar">
            <X size={18} />
          </button>
        </div>
        <div className="event-name-row">
          <label>
            Nombre *<input value={props.value.name} onChange={(event) => update({ name: event.target.value })} />
          </label>
          <label>
            Modo de fechas *
            <select
              value={props.value.date_mode}
              onChange={(event) => update({ date_mode: event.target.value as EventDraft["date_mode"] })}
            >
              <option value="date_range">Rango de fechas</option>
              <option value="selected_dates">Seleccion de fechas</option>
            </select>
          </label>
        </div>
        <div className="modal-grid">
          {props.value.date_mode === "selected_dates" ? (
            <div className="event-date-row selected-dates-row">
              <MultiCheckDropdown
                label="Fechas disponibles *"
                options={dateOptions}
                values={props.value.selected_dates}
                onChange={(selected_dates) => update({ selected_dates })}
              />
              <label className="switch-row all-day-inline">
                <input
                  type="checkbox"
                  checked={props.value.all_day}
                  onChange={(event) => update({ all_day: event.target.checked })}
                />
                Todo el dia
              </label>
            </div>
          ) : (
            <div className="event-date-row">
              <label>
                Fecha inicio *
                <input
                  type="date"
                  min={props.rangeStart}
                  max={props.rangeEnd}
                  value={props.value.target_date}
                  onChange={(event) =>
                    update({ target_date: event.target.value, end_date: props.value.end_date || event.target.value })
                  }
                />
              </label>
              <label>
                Fecha fin
                <input
                  type="date"
                  min={props.rangeStart}
                  max={props.rangeEnd}
                  value={props.value.end_date}
                  onChange={(event) => update({ end_date: event.target.value })}
                />
              </label>
              <label className="switch-row all-day-inline">
                <input
                  type="checkbox"
                  checked={props.value.all_day}
                  onChange={(event) => update({ all_day: event.target.checked })}
                />
                Todo el dia
              </label>
            </div>
          )}
          {!props.value.all_day ? (
            <>
              <label>
                Hora inicio
                <input
                  type="time"
                  value={props.value.start_time}
                  onChange={(event) => update({ start_time: event.target.value })}
                />
              </label>
              <label>
                Hora fin
                <input
                  type="time"
                  value={props.value.end_time}
                  onChange={(event) => update({ end_time: event.target.value })}
                />
              </label>
            </>
          ) : null}
          <label>
            Tipo *
            <select value={props.value.event_type} onChange={(event) => update({ event_type: event.target.value })}>
              {eventTypes.map((type) => (
                <option key={type}>{type}</option>
              ))}
            </select>
          </label>
          <label>
            Impacto *
            <select
              value={props.value.impact_level}
              onChange={(event) => update({ impact_level: event.target.value })}
            >
              {impactLevels.map((impact) => (
                <option key={impact}>{impact}</option>
              ))}
            </select>
          </label>
        </div>
        <MultiCheckDropdown
          label="Estaciones afectadas *"
          options={stationDropdownOptions}
          values={props.value.affected_stations}
          onChange={updateSelectedOptions}
        />
        <label>
          Comentario
          <textarea value={props.value.comment} onChange={(event) => update({ comment: event.target.value })} />
        </label>
        <div className="modal-actions">
          {props.onDelete ? (
            <button type="button" className="danger" onClick={props.onDelete}>
              <Trash2 size={16} />
              Eliminar evento
            </button>
          ) : null}
          <button type="button" onClick={props.onClose}>
            Cancelar
          </button>
          <button type="button" className="primary" onClick={props.onSave}>
            Guardar evento
          </button>
        </div>
      </section>
    </div>
  );
}
