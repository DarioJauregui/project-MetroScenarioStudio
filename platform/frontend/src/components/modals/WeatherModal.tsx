import { X } from "lucide-react";
import type { WeatherFormState } from "../../types";

export function WeatherModal(props: {
  dates: string[];
  value: WeatherFormState;
  onChange: (value: WeatherFormState) => void;
  onClose: () => void;
  onSave: () => void;
}) {
  const update = (patch: Partial<WeatherFormState>) => props.onChange({ ...props.value, ...patch });
  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true">
      <section className="modal weather-modal">
        <div className="section-heading">
          <h2>Modificar meteorologia</h2>
          <button type="button" className="icon-button" onClick={props.onClose} title="Cerrar">
            <X size={18} />
          </button>
        </div>
        <p className="muted">
          Se aplicara a {props.dates.length === 1 ? props.dates[0] : `${props.dates.length} dias seleccionados`} y
          marcara el escenario como What-if.
        </p>
        <div className="weather-toggle-grid">
          <label className="switch-row">
            <input
              type="checkbox"
              checked={props.value.rain}
              onChange={(event) => update({ rain: event.target.checked })}
            />
            Lluvia prevista
          </label>
          <label className="switch-row">
            <input
              type="checkbox"
              checked={props.value.heavy_rain}
              onChange={(event) => update({ heavy_rain: event.target.checked })}
            />
            Lluvia intensa
          </label>
          <label className="switch-row">
            <input
              type="checkbox"
              checked={props.value.bad_weather}
              onChange={(event) => update({ bad_weather: event.target.checked })}
            />
            Mal tiempo
          </label>
          <label className="switch-row">
            <input
              type="checkbox"
              checked={props.value.hot_day}
              onChange={(event) => update({ hot_day: event.target.checked })}
            />
            Dia caluroso
          </label>
          <label className="switch-row">
            <input
              type="checkbox"
              checked={props.value.cold_day}
              onChange={(event) => update({ cold_day: event.target.checked })}
            />
            Dia frio
          </label>
        </div>
        <div className="weather-grid">
          <label>
            Temperatura aproximada
            <input
              type="number"
              value={props.value.approx_temperature}
              onChange={(event) => update({ approx_temperature: event.target.value })}
            />
          </label>
          <label>
            Temp. minima
            <input
              type="number"
              value={props.value.temp_min}
              onChange={(event) => update({ temp_min: event.target.value })}
            />
          </label>
          <label>
            Temp. media
            <input
              type="number"
              value={props.value.temp_mean}
              onChange={(event) => update({ temp_mean: event.target.value })}
            />
          </label>
          <label>
            Temp. maxima
            <input
              type="number"
              value={props.value.temp_max}
              onChange={(event) => update({ temp_max: event.target.value })}
            />
          </label>
          <label>
            Precipitacion mm
            <input
              type="number"
              min="0"
              value={props.value.precip_mm}
              onChange={(event) => update({ precip_mm: event.target.value })}
            />
          </label>
          <label>
            Horas de lluvia
            <input
              type="number"
              min="0"
              value={props.value.rain_hours}
              onChange={(event) => update({ rain_hours: event.target.value })}
            />
          </label>
          <label>
            Viento km/h
            <input
              type="number"
              min="0"
              value={props.value.wind}
              onChange={(event) => update({ wind: event.target.value })}
            />
          </label>
          <label>
            Humedad %
            <input
              type="number"
              min="0"
              max="100"
              value={props.value.humidity}
              onChange={(event) => update({ humidity: event.target.value })}
            />
          </label>
          <label>
            Codigo meteo
            <input
              value={props.value.weather_code}
              onChange={(event) => update({ weather_code: event.target.value })}
            />
          </label>
          <label>
            Alerta
            <select
              value={props.value.alert_level}
              onChange={(event) => update({ alert_level: event.target.value })}
            >
              <option value="sin_alerta">Sin alerta</option>
              <option value="amarilla">Amarilla</option>
              <option value="naranja">Naranja</option>
              <option value="roja">Roja</option>
            </select>
          </label>
          <label className="modal-grid-full">
            Resumen alerta
            <textarea
              value={props.value.alert_summary}
              onChange={(event) => update({ alert_summary: event.target.value })}
            />
          </label>
        </div>
        <div className="modal-actions">
          <button type="button" onClick={props.onClose}>
            Cancelar
          </button>
          <button type="button" className="primary" onClick={props.onSave}>
            Guardar meteorologia
          </button>
        </div>
      </section>
    </div>
  );
}
