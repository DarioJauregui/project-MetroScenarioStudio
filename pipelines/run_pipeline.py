import os
import sys
import re
import json
import logging
import unicodedata
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd
import pytz
from path_resolution import missing_workbook_patterns, resolve_pipeline_paths
from run_summary import PipelineRunSummary


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


# Configurar logging
log_format = "%(asctime)s - %(levelname)s - %(message)s"
logging.basicConfig(level=logging.INFO, format=log_format)
logger = logging.getLogger("metro_demand_pipeline")

# Cargar configuración
pipeline_dir = Path(__file__).resolve().parent
load_env_file(pipeline_dir / ".env")
config_path = pipeline_dir / "config.json"
# Fallback to pipeline_config.json if config.json doesn't exist
if not config_path.exists():
    config_path = pipeline_dir / "pipeline_config.json"

if not config_path.exists():
    logger.error(f"No se encontró el archivo de configuración en {config_path}")
    sys.exit(1)

with open(config_path, "r", encoding="utf-8") as f:
    config = json.load(f)

# Agregar handler para archivo de log
log_file_path = pipeline_dir / "pipeline.log"
file_handler = logging.FileHandler(log_file_path, encoding="utf-8")
file_handler.setFormatter(logging.Formatter(log_format))
logger.addHandler(file_handler)

logger.info("Iniciando pipeline de ejecución diaria...")

overwrite_threshold_months = config.get("overwrite_threshold_months", 2)
overwrite_threshold_days = overwrite_threshold_months * 30.5

# Resolver rutas relativas a la raiz del monorepo
monorepo_root = Path(__file__).resolve().parents[1]
resolved_paths = resolve_pipeline_paths(config, monorepo_root=monorepo_root)
data_source_dir = resolved_paths.data_source_dir
models_repo_dir = resolved_paths.models_repo_dir
platform_repo_dir = resolved_paths.platform_repo_dir
consolidated_path = resolved_paths.consolidated_validations_path
python_exe = resolved_paths.python_exe
pipeline_summary = PipelineRunSummary(monorepo_root)

# Validar existencia de rutas
if not data_source_dir.exists():
    logger.error(f"Ruta de origen de datos no encontrada: {data_source_dir}")
    sys.exit(1)
if not models_repo_dir.exists():
    logger.error(f"Repositorio de modelos no encontrado en: {models_repo_dir}")
    sys.exit(1)
if not python_exe.exists():
    logger.error(f"Entorno virtual de Python no encontrado en: {python_exe}")
    sys.exit(1)

# =============================================================================
# ACTUALIZACIÓN DE EVENTOS Y METEOROLOGÍA
# =============================================================================

# 1. Actualizar Calendario de Eventos localmente
logger.info("Iniciando Paso 1: Actualización del calendario de eventos desde SharePoint conecta...")
eventos_excel_path = monorepo_root / "data" / "raw" / "Calendario_Eventos.xlsx"
pipeline_summary.start_step("ingest_events_calendar", critical=False)
try:
    result_events = subprocess.run(
        [str(python_exe), str(pipeline_dir / "export_calendarioEventos.py"), str(eventos_excel_path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result_events.returncode != 0:
        logger.warning(
            f"Advertencia al exportar eventos. Se continuará con el archivo existente. Detalle:\n{result_events.stderr}"
        )
        pipeline_summary.finish_step(
            "ingest_events_calendar",
            status="failed",
            critical=False,
            message=result_events.stderr.strip() or "export_calendarioEventos.py returned non-zero exit code",
        )
    else:
        logger.info("Calendario de eventos exportado con éxito localmente.")
        pipeline_summary.finish_step(
            "ingest_events_calendar",
            status="success",
            critical=False,
            artifacts={"calendar_events_excel": str(eventos_excel_path)},
        )
except Exception as e:
    logger.warning(f"Excepción al ejecutar la exportación de eventos: {e}. Se continuará...")
    pipeline_summary.finish_step("ingest_events_calendar", status="failed", critical=False, message=str(e))


# Función para actualizar meteorología
def update_weather_data(config, models_repo_dir, logger):
    import requests

    parquet_path = monorepo_root / "data" / "processed" / "external_features" / "external_daily_features.parquet"
    if not parquet_path.exists():
        logger.error(f"No se encontró el archivo de clima: {parquet_path}")
        return False

    try:
        df_clima = pd.read_parquet(parquet_path)
    except Exception as e:
        logger.error(f"Error al leer el archivo de clima: {e}")
        return False

    df_clima["date"] = pd.to_datetime(df_clima["date"]).dt.date
    today_dt = datetime.now().date()

    # Filtrar fechas <= hoy para encontrar el límite histórico real (excluyendo previsiones previas)
    df_historical = df_clima[df_clima["date"] <= today_dt]
    if not df_historical.empty:
        max_historical_date = df_historical["date"].max()
    else:
        max_historical_date = today_dt

    logger.info(f"Fecha máxima de clima histórico en parquet: {max_historical_date}")

    overwrite_days = config.get("weather_overwrite_days", 14)
    forecast_days = config.get("weather_forecast_days", 14)

    start_date = max_historical_date - timedelta(days=overwrite_days)
    end_date = today_dt + timedelta(days=forecast_days)

    logger.info(
        f"Descargando datos de clima desde {start_date} hasta {end_date} (incluyendo {forecast_days} días de previsión)..."
    )

    # Hybrid Weather Querying Helper
    def fetch_weather_range(start_dt, end_dt, lat, lon, tz, log):
        today_dt = datetime.now().date()
        archive_limit = today_dt - timedelta(days=30)

        df_hourly_list = []
        df_daily_list = []

        # 1. Archive API for older dates
        if start_dt < archive_limit:
            archive_end = min(end_dt, archive_limit - timedelta(days=1))
            log.info(f"Consultando Archive API desde {start_dt} hasta {archive_end}...")
            url = "https://archive-api.open-meteo.com/v1/archive"
            params = {
                "latitude": lat,
                "longitude": lon,
                "start_date": start_dt.strftime("%Y-%m-%d"),
                "end_date": archive_end.strftime("%Y-%m-%d"),
                "hourly": "temperature_2m,relative_humidity_2m,precipitation,pressure_msl,wind_speed_10m",
                "daily": "weather_code",
                "timezone": tz,
            }
            try:
                r = requests.get(url, params=params, timeout=30)
                if r.status_code != 200:
                    log.error(f"Error Archive API ({r.status_code}): {r.text}")
                    return None, None
                res = r.json()
                h = res.get("hourly", {})
                d = res.get("daily", {})
                if h and d:
                    df_hourly_list.append(
                        pd.DataFrame(
                            {
                                "time": pd.to_datetime(h["time"]),
                                "temp": h["temperature_2m"],
                                "humidity": h["relative_humidity_2m"],
                                "precip": h["precipitation"],
                                "pressure": h["pressure_msl"],
                                "wind": h["wind_speed_10m"],
                            }
                        )
                    )
                    df_daily_list.append(
                        pd.DataFrame({"date": pd.to_datetime(d["time"]).date, "weather_code": d["weather_code"]})
                    )
            except Exception as ex:
                log.error(f"Excepción en Archive API: {ex}")
                return None, None
            start_dt = archive_limit

        # 2. Forecast API for recent dates
        if start_dt <= end_dt:
            log.info(f"Consultando Forecast API desde {start_dt} hasta {end_dt}...")
            url = "https://api.open-meteo.com/v1/forecast"
            params = {
                "latitude": lat,
                "longitude": lon,
                "start_date": start_dt.strftime("%Y-%m-%d"),
                "end_date": end_dt.strftime("%Y-%m-%d"),
                "hourly": "temperature_2m,relative_humidity_2m,precipitation,pressure_msl,wind_speed_10m",
                "daily": "weather_code",
                "timezone": tz,
            }
            try:
                r = requests.get(url, params=params, timeout=30)
                if r.status_code != 200:
                    log.error(f"Error Forecast API ({r.status_code}): {r.text}")
                    return None, None
                res = r.json()
                h = res.get("hourly", {})
                d = res.get("daily", {})
                if h and d:
                    df_hourly_list.append(
                        pd.DataFrame(
                            {
                                "time": pd.to_datetime(h["time"]),
                                "temp": h["temperature_2m"],
                                "humidity": h["relative_humidity_2m"],
                                "precip": h["precipitation"],
                                "pressure": h["pressure_msl"],
                                "wind": h["wind_speed_10m"],
                            }
                        )
                    )
                    df_daily_list.append(
                        pd.DataFrame({"date": pd.to_datetime(d["time"]).date, "weather_code": d["weather_code"]})
                    )
            except Exception as ex:
                log.error(f"Excepción en Forecast API: {ex}")
                return None, None

        if not df_hourly_list:
            return None, None

        df_hourly_res = pd.concat(df_hourly_list, ignore_index=True)
        df_daily_res = pd.concat(df_daily_list, ignore_index=True)
        return df_hourly_res, df_daily_res

    df_hourly, df_daily_api = None, None
    current_end_date = end_date
    while current_end_date >= today_dt:
        logger.info(f"Intentando descargar meteorología hasta: {current_end_date}...")
        df_hourly, df_daily_api = fetch_weather_range(
            start_date,
            current_end_date,
            config.get("latitude", 36.72016),
            config.get("longitude", -4.42034),
            config.get("timezone", "Europe/Madrid"),
            logger,
        )
        if df_hourly is not None and df_daily_api is not None:
            break
        logger.warning(f"Error al descargar clima hasta {current_end_date}. Reintentando con un día menos...")
        current_end_date -= timedelta(days=1)

    if df_hourly is None or df_daily_api is None:
        logger.error("No se pudo obtener datos de meteorología.")
        return False

    df_hourly["date"] = df_hourly["time"].dt.date

    daily_grouped = (
        df_hourly.groupby("date")
        .agg(
            temp_min_c=("temp", "min"),
            temp_max_c=("temp", "max"),
            temp_mean_c=("temp", "mean"),
            precip_mm=("precip", "sum"),
            rain_hours=("precip", lambda x: int((x > 0.0).sum())),
            wind_max_kmh=("wind", "max"),
            wind_mean_kmh=("wind", "mean"),
            humidity_mean_pct=("humidity", "mean"),
            pressure_mean_hpa=("pressure", "mean"),
        )
        .reset_index()
    )

    # Cast temporal de rain_hours
    daily_grouped["rain_hours"] = daily_grouped["rain_hours"].astype("int32")

    df_new_weather = pd.merge(daily_grouped, df_daily_api, on="date", how="left")

    # Manejar posibles NaNs en weather_code
    df_new_weather["weather_code"] = df_new_weather["weather_code"].fillna(0).astype("int64")

    WEATHER_CODE_TO_SUMMARY = {
        0: "clear_sky",
        1: "mainly_clear",
        2: "partly_cloudy",
        3: "overcast",
        45: "fog",
        48: "fog",
        51: "drizzle_light",
        53: "drizzle_moderate",
        55: "drizzle_dense",
        61: "rain_slight",
        63: "rain_moderate",
        65: "rain_heavy",
        71: "snow_light",
        73: "snow_moderate",
        75: "snow_heavy",
        80: "rain_slight",
        81: "rain_moderate",
        82: "rain_heavy",
        95: "thunderstorm",
        96: "thunderstorm",
        99: "thunderstorm",
    }
    df_new_weather["weather_summary"] = df_new_weather["weather_code"].map(
        lambda code: WEATHER_CODE_TO_SUMMARY.get(code, "clear_sky")
    )
    df_new_weather["weather_source"] = "openmeteo"
    df_new_weather["is_rainy_day"] = df_new_weather["precip_mm"] >= 1.0
    df_new_weather["is_heavy_rain_day"] = df_new_weather["precip_mm"] >= 15.0
    df_new_weather["is_hot_day"] = df_new_weather["temp_max_c"] >= 30.0
    df_new_weather["is_cold_day"] = df_new_weather["temp_min_c"] <= 8.0
    df_new_weather["is_bad_weather_day"] = df_new_weather["precip_mm"] >= 5.0

    # Rellenar variables de calendario
    date_col = pd.to_datetime(df_new_weather["date"])
    df_new_weather["year"] = date_col.dt.year
    df_new_weather["month"] = date_col.dt.month
    df_new_weather["day"] = date_col.dt.day
    df_new_weather["quarter"] = date_col.dt.quarter
    df_new_weather["week_of_year"] = date_col.dt.isocalendar().week.astype("int64")
    df_new_weather["day_of_year"] = date_col.dt.dayofyear
    df_new_weather["day_of_week"] = date_col.dt.dayofweek
    df_new_weather["day_of_week_name"] = date_col.dt.day_name()
    df_new_weather["is_weekend"] = df_new_weather["day_of_week"].isin([5, 6])
    df_new_weather["is_month_start"] = date_col.dt.is_month_start
    df_new_weather["is_month_end"] = date_col.dt.is_month_end
    df_new_weather["year_month"] = date_col.dt.strftime("%Y-%m")
    df_new_weather["year_week"] = (
        date_col.dt.year.astype(str) + "-" + date_col.dt.isocalendar().week.astype(str).str.zfill(2)
    )

    # Rellenar Festivos
    festivos_path = monorepo_root / "data" / "external" / "datos_externos" / "Festivos.xlsx"
    if not festivos_path.exists():
        logger.error(f"No se encontró Festivos.xlsx en: {festivos_path}")
        return False

    try:
        df_festivos = pd.read_excel(festivos_path, sheet_name="Festivos")
        df_mmo = pd.read_excel(festivos_path, sheet_name="Festivos_MMO")
    except Exception as e:
        logger.error(f"Error al leer Festivos.xlsx: {e}")
        return False

    df_festivos = df_festivos.dropna(subset=["fecha"])
    df_mmo = df_mmo.dropna(subset=["Festivos"])

    df_festivos["fecha"] = pd.to_datetime(df_festivos["fecha"]).dt.date
    df_mmo["Festivos"] = pd.to_datetime(df_mmo["Festivos"]).dt.date

    dict_festivo_names = df_festivos.set_index("fecha")["festivo"].to_dict()
    set_festivos_mmo = set(df_mmo["Festivos"])
    set_festivos_oficial = set(df_festivos["fecha"])
    all_holiday_dates = sorted(list(set_festivos_oficial | set_festivos_mmo))

    target_dates = df_new_weather["date"].tolist()
    is_holiday_list = []
    is_holiday_mmo_list = []
    holiday_scope_list = []
    holiday_name_list = []
    days_to_next_list = []
    days_since_prev_list = []

    for dt in target_dates:
        is_mmo = dt in set_festivos_mmo
        is_hol = dt in set_festivos_oficial or is_mmo
        is_holiday_list.append(is_hol)
        is_holiday_mmo_list.append(is_mmo)

        if is_mmo:
            holiday_scope_list.append("metro_malaga_operativo")
        elif dt in set_festivos_oficial:
            holiday_scope_list.append("official_calendar")
        else:
            holiday_scope_list.append(None)

        if dt in set_festivos_oficial:
            holiday_name_list.append(dict_festivo_names[dt])
        elif is_mmo:
            holiday_name_list.append("Festivo MMO")
        else:
            holiday_name_list.append(None)

        if is_hol:
            days_to_next_list.append(0.0)
            days_since_prev_list.append(0.0)
        else:
            future_holidays = [h for h in all_holiday_dates if h > dt]
            past_holidays = [h for h in all_holiday_dates if h < dt]
            days_to_next_list.append(float((future_holidays[0] - dt).days) if future_holidays else float("nan"))
            days_since_prev_list.append(float((dt - past_holidays[-1]).days) if past_holidays else float("nan"))

    df_new_weather["is_holiday"] = is_holiday_list
    df_new_weather["is_holiday_mmo"] = is_holiday_mmo_list
    df_new_weather["holiday_scope"] = holiday_scope_list
    df_new_weather["holiday_name"] = holiday_name_list
    df_new_weather["days_to_next_holiday"] = days_to_next_list
    df_new_weather["days_since_prev_holiday"] = days_since_prev_list

    # Descartar previsiones futuras anteriores del parquet (fechas > hoy)
    df_clima_cleaned = df_clima[df_clima["date"] <= today_dt].copy()

    dates_to_overwrite = set(df_new_weather["date"])
    df_clima_filtered = df_clima_cleaned[~df_clima_cleaned["date"].isin(dates_to_overwrite)].copy()
    df_updated = pd.concat([df_clima_filtered, df_new_weather], ignore_index=True)
    df_updated = df_updated.sort_values("date").reset_index(drop=True)

    # Recalcular shift y bridge
    df_updated["is_preholiday"] = df_updated["is_holiday"].shift(-1).fillna(False)
    df_updated["is_postholiday"] = df_updated["is_holiday"].shift(1).fillna(False)
    df_updated["is_bridge_candidate"] = (
        (~df_updated["is_weekend"])
        & (~df_updated["is_holiday"])
        & ((df_updated["days_to_next_holiday"] == 1.0) | (df_updated["days_since_prev_holiday"] == 1.0))
    )

    # Rellenar columnas de eventos que son excluidas pero requeridas en el esquema
    event_cols = [
        "events_total_count",
        "events_high_impact_count",
        "events_estimated_attendance_sum",
        "events_unknown_attendance_count",
        "events_near_metro_count",
        "events_city_center_count",
        "events_culture_count",
        "events_sports_count",
        "events_congress_count",
        "events_university_count",
        "events_religious_count",
        "events_other_count",
        "events_weighted_impact_sum",
        "max_event_impact_score",
        "has_major_event",
        "has_multiple_major_events",
        "events_geocoded_count",
        "events_unique_venue_count",
    ]
    for col in event_cols:
        if col in df_updated.columns:
            df_updated[col] = df_updated[col].fillna(0)

    now_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    df_updated.loc[df_updated["run_id"].isna() | (df_updated["run_id"] == ""), "run_id"] = now_str

    # Alinear tipos exactamente con el esquema original del archivo parquet
    orig_dtypes = df_clima.dtypes
    for col in df_updated.columns:
        if col in orig_dtypes:
            expected_type = orig_dtypes[col]
            if df_updated[col].dtype != expected_type:
                df_updated[col] = df_updated[col].astype(expected_type)

    try:
        df_updated.to_parquet(parquet_path, index=False)
        logger.info(
            f"Meteorología y calendario de festivos actualizados con éxito en {parquet_path}. Total filas: {len(df_updated)}"
        )
        return True
    except Exception as e:
        logger.error(f"Error al escribir el archivo de clima parquet: {e}")
        return False


# 2. Actualizar Meteorología
logger.info("Iniciando Paso 2: Actualización de la meteorología desde Open-Meteo...")
pipeline_summary.start_step("ingest_weather", critical=False)
try:
    weather_success = update_weather_data(config, models_repo_dir, logger)
    if not weather_success:
        logger.warning("Fallo al actualizar la meteorología. El pipeline continuará con los datos de clima existentes.")
        pipeline_summary.finish_step("ingest_weather", status="failed", critical=False)
    else:
        pipeline_summary.finish_step(
            "ingest_weather",
            status="success",
            critical=False,
            artifacts={
                "external_daily_features": str(
                    monorepo_root / "data" / "processed" / "external_features" / "external_daily_features.parquet"
                )
            },
        )
except Exception as e:
    logger.warning(f"Excepción al actualizar la meteorología: {e}. El pipeline continuará...")
    pipeline_summary.finish_step("ingest_weather", status="failed", critical=False, message=str(e))


# 3. Actualizar Datos Históricos Reales (Demanda FLR)
def update_historical_real_data(models_repo_dir, platform_repo_dir, logger):
    import sys

    datacenter_bi_lib_path = config.get("datacenter_bi_lib_path") or os.getenv("METRO_DATACENTER_BI_LIB_PATH")
    if datacenter_bi_lib_path:
        lib_path = str(Path(datacenter_bi_lib_path).expanduser())
        if lib_path not in sys.path:
            sys.path.append(lib_path)

    try:
        from sp_DataCenterBI import download_from_sharepoint
    except ImportError as e:
        logger.error(f"No se pudo importar sp_DataCenterBI: {e}")
        return False

    excel_dir = monorepo_root / "data" / "raw"
    excel_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Descargando Análisis demanda_2.xlsx desde SharePoint...")
    try:
        download_from_sharepoint(
            src_path="TERRALDATA/Análisis Demanda/Análisis demanda_2.xlsx",
            dest_path=str(excel_dir),
        )
    except Exception as e:
        logger.warning(f"No se pudo descargar de SharePoint, se intentará usar el archivo local existente: {e}")

    xlsx_files = [
        f for f in excel_dir.iterdir() if f.is_file() and f.suffix.lower() == ".xlsx" and "demanda" in f.name.lower()
    ]
    if not xlsx_files:
        logger.error(f"No se encontró ningún archivo Excel de demanda en {excel_dir}")
        return False

    latest_xlsx = max(xlsx_files, key=lambda p: p.stat().st_mtime)
    logger.info(f"Procesando Excel de demanda: {latest_xlsx}")

    try:
        df = pd.read_excel(latest_xlsx, sheet_name="Datos", usecols="A:G")
        df["Viajeros"] = pd.to_numeric(df["Viajeros"], errors="coerce")

        # Filtro de filas con 0 viajeros
        zero_positions = df["Viajeros"].fillna(0).eq(0).to_numpy().nonzero()[0]
        if zero_positions.size > 0:
            df = df.iloc[: zero_positions[0]].copy()

        # Mapear día de la semana
        fecha = pd.to_datetime(df["Fecha"], errors="coerce")
        if not fecha.isna().all():
            dia_sem_map = {
                0: "Lunes",
                1: "Martes",
                2: "Miercoles",
                3: "Jueves",
                4: "Viernes",
                5: "Sabado",
                6: "Domingo",
            }
            df["Dia sem"] = fecha.dt.weekday.map(dia_sem_map)

        viajeros_filled = df["Viajeros"].fillna(0)
        df["Acumulado viajeros"] = viajeros_filled.cumsum()

        if fecha.isna().all():
            year_key = df["Anio"]
        else:
            year_key = fecha.dt.year

        df["Acumulado viajeros anio"] = viajeros_filled.groupby(year_key).cumsum()

        for col in ["Viajeros", "Acumulado viajeros", "Acumulado viajeros anio"]:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype("int64")

        # Rutas de salida para el CSV
        csv_models_path = excel_dir / "demanda_historica_MM.csv"
        csv_platform_dir = platform_repo_dir / "backend" / "storage"
        csv_platform_dir.mkdir(parents=True, exist_ok=True)
        csv_platform_path = csv_platform_dir / "demanda_historica_MM.csv"

        # Guardar en repositorio de modelos
        df.to_csv(csv_models_path, index=False)
        logger.info(f"CSV de demanda guardado en repositorio de modelos: {csv_models_path}")

        # Guardar en repositorio de plataforma
        df.to_csv(csv_platform_path, index=False)
        logger.info(f"CSV de demanda guardado en backend de plataforma: {csv_platform_path}")

        return True
    except Exception as e:
        logger.error(f"Error procesando el archivo de demanda histórica: {e}")
        return False


logger.info("Iniciando Paso 3: Actualización de los datos históricos reales recopilados...")
pipeline_summary.start_step("ingest_historical_demand", critical=False)
try:
    historical_success = update_historical_real_data(models_repo_dir, platform_repo_dir, logger)
    if not historical_success:
        logger.warning("Fallo al actualizar los datos históricos reales. El pipeline continuará.")
        pipeline_summary.finish_step("ingest_historical_demand", status="failed", critical=False)
    else:
        pipeline_summary.finish_step(
            "ingest_historical_demand",
            status="success",
            critical=False,
            artifacts={
                "historical_demand_csv": str(platform_repo_dir / "backend" / "storage" / "demanda_historica_MM.csv")
            },
        )
except Exception as e:
    logger.warning(f"Excepción al actualizar los datos históricos reales: {e}. El pipeline continuará...")
    pipeline_summary.finish_step("ingest_historical_demand", status="failed", critical=False, message=str(e))

# Cargar fechas existentes en el parquet consolidated sin leer todo el archivo (por eficiencia en RAM)
existing_dates = []
manifest_map = {}
if consolidated_path.exists():
    logger.info("Leyendo metadatos de validaciones_consolidado.parquet usando PyArrow...")
    try:
        import pyarrow.parquet as pq

        table_meta = pq.read_table(consolidated_path, columns=["dia", "_orden_manifest"])
        grouped_meta = table_meta.group_by("dia").aggregate([("_orden_manifest", "max")])
        df_meta = grouped_meta.to_pandas()

        existing_dates = df_meta["dia"].tolist()
        manifest_map = df_meta.set_index("dia")["_orden_manifest_max"].to_dict()
        logger.info(f"Se encontraron {len(existing_dates)} días históricos consolidados.")
    except Exception as e:
        logger.error(f"Error al leer metadatos de validaciones_consolidado.parquet: {e}")
        pipeline_summary.start_step("validate_existing_validations_metadata")
        pipeline_summary.finish_step("validate_existing_validations_metadata", status="failed", message=str(e))
        pipeline_summary.write()
        sys.exit(1)
else:
    logger.warning("No se encontró validaciones_consolidado.parquet. Se creará uno nuevo.")

# Buscar archivos CSV diarios en el origen
logger.info(f"Escaneando directorio origen de datos: {data_source_dir}...")
csv_files = []
# Buscamos archivos con patrón: data_source_dir\Año\Mes_Año\diamesaño\Validaciones detalladas diamesaño.csv
for csv_path in data_source_dir.glob("*/*/*/Validaciones detalladas *.csv"):
    day_folder = csv_path.parent.name
    month_folder = csv_path.parent.parent.name
    year_folder = csv_path.parent.parent.parent.name

    if (
        re.match(r"^\d{4}$", year_folder)
        and re.match(r"^\d{2}_\d{4}$", month_folder)
        and re.match(r"^\d{6}$", day_folder)
    ):
        csv_files.append(csv_path)

logger.info(f"Se encontraron {len(csv_files)} archivos diarios con el patrón correcto en el origen.")

# Determinar qué archivos procesar
today = datetime.now()
to_process = []
processed_days = []

for csv_path in csv_files:
    day_str = re.search(r"Validaciones detalladas (\d{6})\.csv", csv_path.name).group(1)
    try:
        date_obj = datetime.strptime(day_str, "%d%m%y").date()
    except Exception as e:
        logger.warning(f"No se pudo analizar la fecha del archivo {csv_path.name}: {e}")
        continue

    # Evitar procesar archivos posteriores al límite permitido (configurable en días)
    max_validation_delay_days = config.get("max_validation_delay_days", 1)
    max_allowed_date = today.date() - timedelta(days=max_validation_delay_days)
    if date_obj > max_allowed_date:
        continue

    dia_str = date_obj.strftime("%Y-%m-%d")
    mtime = datetime.fromtimestamp(csv_path.stat().st_mtime)

    days_since_mtime = (today - mtime).days
    days_since_data = (today.date() - date_obj).days

    # Condición de procesamiento:
    # 1. No existe en el parquet consolidado
    # 2. El archivo fue modificado en los últimos 2 meses (60 días)
    # 3. El día representado está en los últimos 2 meses (60 días)
    should_process = (
        dia_str not in existing_dates
        or days_since_mtime <= overwrite_threshold_days
        or days_since_data <= overwrite_threshold_days
    )

    if should_process:
        to_process.append((date_obj, dia_str, csv_path))
        processed_days.append(dia_str)

# Ordenar por fecha para asignación secuencial estable de manifest_map
to_process.sort(key=lambda x: x[0])

logger.info(f"Días a procesar o sobreescribir: {len(to_process)}")
pipeline_summary.start_step(
    "consolidate_validations",
    critical=True,
    metadata={"candidate_files": len(csv_files), "days_to_process": len(to_process)},
)


def clean_columns(df):
    col_mapping = {}
    for col in df.columns:
        norm = str(col).replace("\n", " ").strip().lower()
        norm_clean = "".join(c for c in unicodedata.normalize("NFD", norm) if unicodedata.category(c) != "Mn")

        if "fecha" in norm_clean:
            col_mapping[col] = "fecha_validacion"
        elif "linea" in norm_clean:
            col_mapping[col] = "linea"
        elif "estacion" in norm_clean:
            col_mapping[col] = "estacion"
        elif "codigo equipo" in norm_clean or "cod eq" in norm_clean:
            col_mapping[col] = "cod_eq"
        elif "tipo validacion" in norm_clean:
            col_mapping[col] = "tipo_validacion"
        elif "titulo" in norm_clean:
            col_mapping[col] = "tipo_titulo"
        elif "id tarjeta" in norm_clean:
            col_mapping[col] = "id_tarjeta"
        elif "numero tarjeta" in norm_clean or "num tarjeta" in norm_clean:
            col_mapping[col] = "num_tarjeta"
        elif "dinero" in norm_clean:
            col_mapping[col] = "dinero_deducido"
        elif "saldo" in norm_clean:
            col_mapping[col] = "saldo_restante"
        elif "viajes" in norm_clean:
            col_mapping[col] = "viajes_deducidos"

    return df.rename(columns=col_mapping)


def clean_numeric_col(series):
    cleaned = series.fillna("0").astype(str).str.replace(",", ".")
    cleaned = cleaned.str.replace(r"[^\d\.\-]", "", regex=True)
    cleaned = cleaned.replace("", "0")
    return pd.to_numeric(cleaned, errors="coerce").fillna(0.0)


tz_madrid = pytz.timezone("Europe/Madrid")

new_dfs = []
next_manifest_id = max(list(manifest_map.values()) + [0]) + 1

# Procesar los archivos CSV seleccionados
for date_obj, dia_str, csv_path in to_process:
    logger.info(f"Procesando archivo origen: {csv_path.name} ({dia_str})...")
    try:
        # 1. Leer cabecera (primeras 4 líneas) para metadatos
        with open(csv_path, "r", encoding="latin1") as f:
            line1 = f.readline().strip()
            line2 = f.readline().strip()

        gen_match = re.search(r"Generado:\s*(\d{2}-\d{2}-\d{4}\s+\d{2}:\d{2}(?::\d{2})?)", line2)
        gen_str = gen_match.group(1).strip() if gen_match else None

        range_match = re.search(
            r"Rango de Fechas:\s*(\d{2}-\d{2}-\d{4}\s+\d{2}:\d{2}(?::\d{2})?)\s*-\s*(\d{2}-\d{2}-\d{4}\s+\d{2}:\d{2}(?::\d{2})?)",
            line2,
        )
        range_desde_str = range_match.group(1).strip() if range_match else None
        range_hasta_str = range_match.group(2).strip() if range_match else None
        rango_fechas_raw = f"{range_desde_str} - {range_hasta_str}" if (range_desde_str and range_hasta_str) else ""

        # Parsear timestamps de metadatos
        def parse_dt(dt_str, formats=("%d-%m-%Y %H:%M:%S", "%d-%m-%Y %H:%M")):
            if not dt_str:
                return None
            for fmt in formats:
                try:
                    dt = datetime.strptime(dt_str, fmt)
                    return tz_madrid.localize(dt)
                except ValueError:
                    continue
            return None

        fecha_generacion = parse_dt(gen_str)
        rango_desde = parse_dt(range_desde_str)
        rango_hasta = parse_dt(range_hasta_str)

        # 2. Leer cuerpo del CSV línea por línea de manera robusta
        rows = []
        with open(csv_path, "r", encoding="latin1") as f_in:
            # Saltar 4 líneas de cabecera de metadatos
            for _ in range(4):
                f_in.readline()
            for line in f_in:
                line_str = line.strip()
                if not line_str:
                    continue
                parts = [p.strip().strip('"') for p in line_str.split("|") if p.strip()]
                if len(parts) == 11 and not parts[0].startswith("Fecha") and not parts[0].startswith("Total"):
                    rows.append(parts)

        df = pd.DataFrame(
            rows,
            columns=[
                "fecha_validacion",
                "linea",
                "estacion",
                "cod_eq",
                "tipo_validacion",
                "tipo_titulo",
                "id_tarjeta",
                "num_tarjeta",
                "dinero_deducido",
                "saldo_restante",
                "viajes_deducidos",
            ],
        )

        # Limpiar y castear tipos de datos
        df["fecha_validacion"] = pd.to_datetime(df["fecha_validacion"], format="%d-%m-%Y %H:%M:%S", errors="coerce")
        df["fecha_validacion"] = df["fecha_validacion"].dt.tz_localize("Europe/Madrid")
        df["linea"] = df["linea"].fillna("DESCONOCIDA").astype(str)
        df["estacion"] = df["estacion"].fillna("DESCONOCIDA").astype(str)
        df["cod_eq"] = df["cod_eq"].fillna("DESCONOCIDO").astype(str)
        df["tipo_validacion"] = df["tipo_validacion"].fillna("DESCONOCIDA").astype(str)
        df["tipo_titulo"] = df["tipo_titulo"].fillna("DESCONOCIDO").astype(str)
        df["id_tarjeta"] = df["id_tarjeta"].fillna("No aplica").astype(str)
        df["num_tarjeta"] = df["num_tarjeta"].fillna("").astype(str).str.replace(r"\.0$", "", regex=True)

        df["dinero_deducido"] = clean_numeric_col(df["dinero_deducido"])
        df["saldo_restante"] = clean_numeric_col(df["saldo_restante"])
        df["viajes_deducidos"] = clean_numeric_col(df["viajes_deducidos"]).astype("int64")

        # Asignar campos de metadatos adicionales
        df["fecha_validacion_hora_estimada"] = False
        df["fecha_generacion"] = fecha_generacion
        df["rango_desde"] = rango_desde
        df["rango_hasta"] = rango_hasta
        df["rango_fechas_raw"] = rango_fechas_raw
        df["dia"] = dia_str
        df["archivo_origen"] = str(csv_path.absolute())

        # Cadenas ISO
        df["fecha_validacion_iso"] = df["fecha_validacion"].dt.strftime("%Y-%m-%dT%H:%M:%S%z")
        df["fecha_generacion_iso"] = fecha_generacion.isoformat() if fecha_generacion else ""
        df["rango_desde_iso"] = rango_desde.isoformat() if rango_desde else ""
        df["rango_hasta_iso"] = rango_hasta.isoformat() if rango_hasta else ""

        # Asignar manifest_id secuencial o reutilizar existente
        if dia_str in manifest_map:
            df["_orden_manifest"] = int(manifest_map[dia_str])
        else:
            df["_orden_manifest"] = int(next_manifest_id)
            manifest_map[dia_str] = next_manifest_id
            next_manifest_id += 1

        df["idtarjeta"] = None
        df["idtarjeta"] = df["idtarjeta"].astype(object)

        # Reordenar columnas según el parquet original
        columns_order = [
            "fecha_validacion",
            "linea",
            "estacion",
            "cod_eq",
            "tipo_validacion",
            "tipo_titulo",
            "id_tarjeta",
            "num_tarjeta",
            "dinero_deducido",
            "saldo_restante",
            "viajes_deducidos",
            "fecha_validacion_hora_estimada",
            "fecha_generacion",
            "rango_desde",
            "rango_hasta",
            "rango_fechas_raw",
            "dia",
            "archivo_origen",
            "fecha_validacion_iso",
            "fecha_generacion_iso",
            "rango_desde_iso",
            "rango_hasta_iso",
            "_orden_manifest",
            "idtarjeta",
        ]
        df = df[columns_order]

        # Validar el contrato de datos con Pandera antes de consolidar
        try:
            from metro_demand_models.data.validation_schema import ValidationSchema

            ValidationSchema.validate(df)
            logger.info(f"Fichero {csv_path.name} validado con exito mediante Pandera.")
        except Exception as ve:
            logger.error(f"Fallo de calidad de datos (Pandera) en {csv_path.name}: {ve}")
            raise ve

        new_dfs.append(df)

    except Exception as e:
        logger.error(f"Error procesando el archivo {csv_path.name}: {e}")
        logger.warning(f"Omitiendo el archivo {csv_path.name} debido al error. El pipeline continuará.")
        continue

# Guardar si se procesaron nuevos datos
if new_dfs:
    logger.info("Guardando datos e integrando en validaciones_consolidado.parquet usando PyArrow en streaming...")
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
        import pyarrow.compute as pc

        # Convertir dataframes nuevos a PyArrow Table
        new_tables = [pa.Table.from_pandas(df, preserve_index=False) for df in new_dfs]
        table_new_data = pa.concat_tables(new_tables)

        temp_consolidated_path = consolidated_path.with_suffix(".tmp.parquet")

        if consolidated_path.exists():
            logger.info("Copiando y filtrando datos históricos en streaming a un archivo temporal...")

            total_old_rows = 0
            # Abrir el archivo original con un context manager para asegurar que se libere el handle de Windows
            with open(consolidated_path, "rb") as f_in:
                pf = pq.ParquetFile(f_in)
                schema = pf.schema.to_arrow_schema()

                # Asegurar compatibilidad de tipos con el esquema existente
                table_new_data = table_new_data.cast(schema)

                # Escribir incrementalmente usando ParquetWriter para no sobrecargar RAM
                with pq.ParquetWriter(
                    temp_consolidated_path, schema, use_dictionary=True, compression="snappy"
                ) as writer:
                    # Copiar y filtrar cada row group individualmente
                    for i in range(pf.num_row_groups):
                        table_rg = pf.read_row_group(i)
                        # Excluir los días que se están procesando/sobreescribiendo
                        mask = pc.invert(pc.is_in(table_rg["dia"], value_set=pa.array(processed_days)))
                        filtered_rg = table_rg.filter(mask)

                        if filtered_rg.num_rows > 0:
                            writer.write_table(filtered_rg)
                            total_old_rows += filtered_rg.num_rows

                    # Escribir los nuevos datos al final
                    writer.write_table(table_new_data)

            logger.info(f"Datos antiguos copiados: {total_old_rows} filas.")
            logger.info(f"Datos nuevos agregados: {table_new_data.num_rows} filas.")

            # Reemplazar el archivo original (ambos handles ya están cerrados por los context managers)
            if consolidated_path.exists():
                os.remove(consolidated_path)
            os.rename(temp_consolidated_path, consolidated_path)
            logger.info(f"Guardado exitoso. Total filas estimadas: {total_old_rows + table_new_data.num_rows}")
        else:
            schema = table_new_data.schema
            with pq.ParquetWriter(consolidated_path, schema, use_dictionary=True, compression="snappy") as writer:
                writer.write_table(table_new_data)
            logger.info(f"Guardado exitoso. Creado nuevo parquet consolidado con {table_new_data.num_rows} filas.")

        # Actualizar archivo latest_run.txt
        latest_run_path = monorepo_root / "data" / "raw" / "validaciones" / "latest_run.txt"
        now_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        latest_run_path.write_text(f"{now_str}\n{consolidated_path.parent}\n", encoding="utf-8")
        pipeline_summary.finish_step(
            "consolidate_validations",
            status="success",
            artifacts={
                "consolidated_validations": str(consolidated_path),
                "latest_run": str(latest_run_path),
            },
            metadata={"processed_days": processed_days},
        )

    except Exception as e:
        logger.error(f"Error consolidando archivo parquet con PyArrow: {e}")
        # Intentar limpiar archivo temporal si existe
        temp_file = consolidated_path.with_suffix(".tmp.parquet")
        if temp_file.exists():
            try:
                os.remove(temp_file)
            except OSError:
                pass
        pipeline_summary.finish_step("consolidate_validations", status="failed", message=str(e))
        pipeline_summary.write()
        sys.exit(1)
else:
    logger.info("No hay nuevos datos ni actualizaciones que integrar en el dataset consolidado.")
    pipeline_summary.finish_step(
        "consolidate_validations",
        status="success",
        artifacts={"consolidated_validations": str(consolidated_path)},
        metadata={"processed_days": []},
    )

# 4. Validar Cobertura y generar warnings si faltan datos
logger.info("Validando cobertura de datos...")
try:
    # Usar las fechas consolidadas en memoria actualizándolas con las nuevas procesadas
    all_current_dates = set(existing_dates) | set(processed_days)
    distinct_db_dates = sorted(list(all_current_dates))

    if distinct_db_dates:
        latest_db_day_str = distinct_db_dates[-1]
        latest_db_day = datetime.strptime(latest_db_day_str, "%Y-%m-%d").date()

        max_validation_delay_days = config.get("max_validation_delay_days", 1)
        max_allowed_date = (datetime.now() - timedelta(days=max_validation_delay_days)).date()

        # Generar lista de días calendario entre el último día con datos y la fecha máxima permitida
        if latest_db_day < max_allowed_date:
            logger.warning(
                f"¡AVISO IMPORTANTE! Faltan datos de validaciones. "
                f"El último día con datos consolidado es {latest_db_day_str}, pero debería haber datos hasta {max_allowed_date.strftime('%Y-%m-%d')}."
            )

        # Buscar si existen huecos en los datos en los últimos 3 meses
        three_months_ago = (datetime.now() - timedelta(days=90)).date()
        start_date = max(three_months_ago, datetime.strptime(distinct_db_dates[0], "%Y-%m-%d").date())

        all_range_dates = []
        curr = start_date
        while curr <= max_allowed_date:
            all_range_dates.append(curr.strftime("%Y-%m-%d"))
            curr += timedelta(days=1)

        missing_dates = [d for d in all_range_dates if d not in distinct_db_dates]
        if missing_dates:
            logger.warning(
                f"¡AVISO IMPORTANTE! Se detectaron huecos/días faltantes de datos en el origen en los últimos 3 meses: "
                f"{', '.join(missing_dates)}"
            )
        else:
            logger.info(
                f"Validación de cobertura correcta. No hay huecos en el rango hasta {max_allowed_date.strftime('%Y-%m-%d')}."
            )
except Exception as e:
    logger.error(f"Error validando cobertura de datos: {e}")

# 5. Ejecutar Reentrenamiento y Promoción del Modelo
logger.info("Iniciando proceso de entrenamiento y modelado diario...")

# Lista de scripts a ejecutar secuencialmente en el repositorio de modelos
model_scripts = ["scripts/build_operational_datasets.py", "scripts/build_daily_training_dataset.py"]

# Decidir si ejecutar baselines según la configuración (desactivado por defecto)
if config.get("run_baselines", False):
    model_scripts.append("scripts/run_baselines.py")
else:
    logger.info("Omitiendo scripts/run_baselines.py según la configuración (run_baselines=False).")

model_scripts.extend(
    [
        "scripts/train.py",
        "scripts/evaluate.py",
        "scripts/generate_daily_supervision_artifacts.py",
        "scripts/generate_special_day_error_analysis.py",
        "scripts/run_daily_inference_smoke.py",
        "scripts/run_drift_monitoring.py",
    ]
)

# Definimos cuáles son críticos para detener el pipeline en caso de fallo
critical_scripts = {"scripts/build_daily_training_dataset.py", "scripts/train.py"}
operational_workbook_patterns = ("Servicios Hist*.xlsx", "Calendario_Eventos.xlsx", "Incidencias_Historico.xlsx")

for script in model_scripts:
    logger.info(f"Ejecutando script del repositorio de modelos: {script}...")
    is_critical = script in critical_scripts
    pipeline_summary.start_step(f"model:{script}", critical=is_critical)
    try:
        if script == "scripts/build_operational_datasets.py":
            missing_patterns = missing_workbook_patterns(monorepo_root / "data" / "raw", operational_workbook_patterns)
            if missing_patterns:
                message = (
                    "Omitiendo datasets operativos: faltan workbooks en data/raw para "
                    + ", ".join(missing_patterns)
                )
                logger.warning(message)
                pipeline_summary.finish_step(
                    f"model:{script}",
                    status="skipped",
                    critical=False,
                    message=message,
                    metadata={"missing_patterns": missing_patterns},
                )
                continue

        # Configurar variables de entorno para evitar sobrecargar la CPU en entornos con recursos limitados (OpenMP/BLAS)
        env = os.environ.copy()
        env["OMP_NUM_THREADS"] = "1"
        env["MKL_NUM_THREADS"] = "1"
        env["OPENBLAS_NUM_THREADS"] = "1"
        env["VECLIB_MAXIMUM_THREADS"] = "1"
        env["NUMEXPR_NUM_THREADS"] = "1"

        # Ejecutar el script usando el Python del entorno virtual y como Cwd el repo de modelos.
        # Se monkeypatchea platform.machine() a nivel de comando usando runpy para evitar
        # el cuelgue indefinido de platform.machine() en Windows.
        cmd_code = (
            f"import platform; platform.machine = lambda: 'AMD64'; "
            f"import sys, os; sys.path.insert(0, os.path.abspath('scripts')); "
            f"import runpy; sys.argv=['{script}']; runpy.run_path('{script}', run_name='__main__')"
        )
        result = subprocess.run(
            [str(python_exe), "-c", cmd_code],
            cwd=str(models_repo_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
        if result.returncode != 0:
            logger.error(f"Error ejecutando {script} (Código de salida: {result.returncode})")
            logger.error(f"Salida estándar (Stdout):\n{result.stdout}")
            logger.error(f"Salida de errores (Stderr):\n{result.stderr}")

            # Si es crítico, detenemos la ejecución del pipeline completo
            if script in critical_scripts:
                logger.error(f"El script {script} es crítico. Abortando pipeline.")
                pipeline_summary.finish_step(
                    f"model:{script}",
                    status="failed",
                    critical=True,
                    message=result.stderr.strip() or result.stdout.strip(),
                )
                pipeline_summary.write()
                sys.exit(1)
            else:
                logger.warning(f"El script {script} falló pero no es crítico. Continuando con el pipeline...")
                pipeline_summary.finish_step(
                    f"model:{script}",
                    status="failed",
                    critical=False,
                    message=result.stderr.strip() or result.stdout.strip(),
                )
        else:
            logger.info(f"Script completado con éxito: {script}")
            # Loguear breve resumen del script
            last_lines = [line for line in result.stdout.split("\n") if line.strip()][-3:]
            logger.info("Resumen de salida:\n" + "\n".join(last_lines))
            pipeline_summary.finish_step(
                f"model:{script}",
                status="success",
                critical=is_critical,
                metadata={"stdout_tail": last_lines},
            )

    except Exception as e:
        logger.error(f"Excepción al ejecutar el script {script}: {e}")
        if script in critical_scripts:
            logger.error(f"El script {script} es crítico. Abortando pipeline.")
            pipeline_summary.finish_step(f"model:{script}", status="failed", critical=True, message=str(e))
            pipeline_summary.write()
            sys.exit(1)
        else:
            logger.warning(f"El script {script} falló por excepción pero no es crítico. Continuando...")
            pipeline_summary.finish_step(f"model:{script}", status="failed", critical=False, message=str(e))

# Confirmar la actualización del modelo promovido para ambas variantes principales
promoted_strict_path = (
    models_repo_dir / "artifacts" / "models" / "daily_modeling" / "tabular_hgbr__strict_available__all_series__h1.pkl"
)
promoted_forecastable_path = (
    models_repo_dir
    / "artifacts"
    / "models"
    / "daily_modeling"
    / "tabular_hgbr__forecastable_scenario__all_series__h1.pkl"
)

strict_ok = promoted_strict_path.exists()
forecastable_ok = promoted_forecastable_path.exists()

if strict_ok and forecastable_ok:
    mtime_strict = datetime.fromtimestamp(promoted_strict_path.stat().st_mtime)
    mtime_forecastable = datetime.fromtimestamp(promoted_forecastable_path.stat().st_mtime)
    logger.info(
        f"¡PROCESO DE PIPELINE COMPLETADO EXITOSAMENTE! "
        f"El modelo strict_available se actualizó a las {mtime_strict.strftime('%Y-%m-%d %H:%M:%S')} en {promoted_strict_path.absolute()}. "
        f"El modelo forecastable_scenario se actualizó a las {mtime_forecastable.strftime('%Y-%m-%d %H:%M:%S')} en {promoted_forecastable_path.absolute()}. "
        f"La plataforma de inferencia ya cuenta con ambas variantes actualizadas por defecto."
    )
elif strict_ok:
    mtime_strict = datetime.fromtimestamp(promoted_strict_path.stat().st_mtime)
    logger.warning(
        f"El pipeline finalizó. El modelo strict_available se actualizó a las {mtime_strict.strftime('%Y-%m-%d %H:%M:%S')} en {promoted_strict_path.absolute()}, "
        f"pero no se encontró o no se actualizó el modelo forecastable_scenario en {promoted_forecastable_path.absolute()}."
    )
else:
    logger.error("El pipeline finalizó pero no se encontraron los modelos promovidos esperados.")
    pipeline_summary.start_step("promoted_model_check", critical=True)
    pipeline_summary.finish_step("promoted_model_check", status="failed")
    pipeline_summary.write()
    sys.exit(1)

promoted_model_check_is_critical = not strict_ok
pipeline_summary.start_step("promoted_model_check", critical=promoted_model_check_is_critical)
pipeline_summary.finish_step(
    "promoted_model_check",
    status="success" if strict_ok and forecastable_ok else "failed",
    critical=promoted_model_check_is_critical,
    artifacts={
        "strict_available_model": str(promoted_strict_path),
        "forecastable_scenario_model": str(promoted_forecastable_path),
    },
)
summary_path = pipeline_summary.write()
logger.info("Resumen estructurado del pipeline escrito en %s", summary_path)
