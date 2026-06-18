import { alertLabel, formatCell } from "../../utils/formatters";

export function WeatherCompact(props: { weather: Record<string, unknown> }) {
  const temperature = props.weather.approx_temperature ?? props.weather.temp_mean;
  const rain = Boolean(props.weather.rain);
  const precip = props.weather.precip_mm;
  const wind = props.weather.wind;
  const alertLevel = String(props.weather.alert_level ?? "sin_alerta");
  const simulated = Boolean(props.weather.modified) || props.weather.source === "manual_scenario";
  return (
    <div className={simulated ? "weather-compact simulated" : "weather-compact"}>
      <span>
        {temperature !== null && temperature !== undefined ? `${formatCell(temperature)} °C` : "Temp. s/d"}
      </span>
      <span>{rain ? "Lluvia" : "Sin lluvia"}</span>
      {precip !== null && precip !== undefined ? <span>{formatCell(precip)} mm</span> : null}
      {wind !== null && wind !== undefined ? <span>{formatCell(wind)} km/h</span> : null}
      <span className={`alert-pill ${alertLevel}`}>{alertLabel(alertLevel)}</span>
      {simulated ? <span className="sim-pill">Simulada</span> : null}
    </div>
  );
}
