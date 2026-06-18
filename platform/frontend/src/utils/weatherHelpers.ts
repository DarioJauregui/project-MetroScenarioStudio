import type { WeatherFormState, WeatherOverride } from "../types";
import { optionalNumber, textNumber, nullableText } from "./formatters";

export function mergeWeatherRows(
  automaticRows: Array<Record<string, unknown>>,
  overrides: Record<string, WeatherOverride>
) {
  const byDate = new Map(automaticRows.map((row) => [String(row.target_date), { ...row }]));
  for (const [targetDate, override] of Object.entries(overrides)) {
    byDate.set(targetDate, {
      ...(byDate.get(targetDate) ?? { target_date: targetDate }),
      ...override,
      target_date: targetDate,
      source: "manual_scenario",
      modified: true,
      used_by_model: true,
    });
  }
  return [...byDate.values()].sort((a, b) => String(a.target_date).localeCompare(String(b.target_date)));
}

export function weatherFormFromSource(source: Record<string, unknown>): WeatherFormState {
  return {
    rain: Boolean(source.rain),
    heavy_rain: Boolean(source.heavy_rain),
    hot_day: Boolean(source.hot_day),
    cold_day: Boolean(source.cold_day),
    bad_weather: Boolean(source.bad_weather),
    approx_temperature: textNumber(source.approx_temperature ?? source.temp_mean),
    temp_min: textNumber(source.temp_min),
    temp_mean: textNumber(source.temp_mean ?? source.approx_temperature),
    temp_max: textNumber(source.temp_max),
    precip_mm: textNumber(source.precip_mm),
    rain_hours: textNumber(source.rain_hours),
    wind: textNumber(source.wind),
    humidity: textNumber(source.humidity),
    weather_code: String(source.weather_code ?? ""),
    alert_level: String(source.alert_level ?? "sin_alerta"),
    alert_summary: String(source.alert_summary ?? ""),
  };
}

export function weatherOverrideFromForm(form: WeatherFormState): WeatherOverride {
  return {
    rain: form.rain,
    heavy_rain: form.heavy_rain,
    hot_day: form.hot_day,
    cold_day: form.cold_day,
    bad_weather: form.bad_weather || form.rain || form.heavy_rain,
    approx_temperature: optionalNumber(form.approx_temperature),
    temp_min: optionalNumber(form.temp_min),
    temp_mean: optionalNumber(form.temp_mean),
    temp_max: optionalNumber(form.temp_max),
    precip_mm: optionalNumber(form.precip_mm),
    rain_hours: optionalNumber(form.rain_hours),
    wind: optionalNumber(form.wind),
    humidity: optionalNumber(form.humidity),
    weather_code: form.weather_code || null,
    alert_level: form.alert_level || "sin_alerta",
    alert_summary: form.alert_summary || null,
  };
}

export function weatherOverridesFromFinal(rows: Array<Record<string, unknown>>): Record<string, WeatherOverride> {
  return Object.fromEntries(
    rows
      .filter((row) => Boolean(row.modified) || row.source === "manual_scenario")
      .map((row) => [
        String(row.target_date),
        {
          rain: Boolean(row.rain),
          heavy_rain: Boolean(row.heavy_rain),
          hot_day: Boolean(row.hot_day),
          cold_day: Boolean(row.cold_day),
          bad_weather: Boolean(row.bad_weather),
          approx_temperature: optionalNumber(row.approx_temperature),
          temp_min: optionalNumber(row.temp_min),
          temp_mean: optionalNumber(row.temp_mean),
          temp_max: optionalNumber(row.temp_max),
          precip_mm: optionalNumber(row.precip_mm),
          rain_hours: optionalNumber(row.rain_hours),
          wind: optionalNumber(row.wind),
          humidity: optionalNumber(row.humidity),
          weather_code: nullableText(row.weather_code),
          alert_level: nullableText(row.alert_level),
          alert_summary: nullableText(row.alert_summary),
        },
      ])
  );
}

export const emptyWeatherForm = (): WeatherFormState => ({
  rain: false,
  heavy_rain: false,
  hot_day: false,
  cold_day: false,
  bad_weather: false,
  approx_temperature: "",
  temp_min: "",
  temp_mean: "",
  temp_max: "",
  precip_mm: "",
  rain_hours: "",
  wind: "",
  humidity: "",
  weather_code: "",
  alert_level: "sin_alerta",
  alert_summary: "",
});

