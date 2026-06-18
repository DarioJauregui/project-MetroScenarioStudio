# Pipeline Diario

`pipelines/run_pipeline.py` orquesta el ciclo local de datos y modelos dentro de `project-MetroScenarioStudio`.

## Ejecucion

Desde la raiz del monorepo:

```powershell
.\.venv\Scripts\python.exe pipelines\run_pipeline.py
```

## Fases

1. Actualiza calendario de eventos desde SharePoint Conecta cuando las dependencias y credenciales estan disponibles.
2. Refresca meteorologia con Open-Meteo y actualiza `data/processed/external_features/external_daily_features.parquet`.
3. Actualiza demanda historica real y copia `demanda_historica_MM.csv` a `data/raw` y `platform/backend/storage`.
4. Escanea `data_source_dir` para integrar CSV diarios de validaciones en `data/processed/validaciones/validaciones_consolidado.parquet`.
5. Valida cobertura reciente y huecos de datos.
6. Ejecuta scripts de `ml_pipeline/scripts` para datasets operativos, entrenamiento, evaluacion, supervision, smoke de inferencia y drift.

## Configuracion

`pipeline_config.json` mantiene rutas relativas al monorepo salvo el origen bruto de validaciones:

```json
{
  "data_source_dir": "M:\\AOPJA\\Informes\\1_Inf_diarios\\xx_Automaticos_EnPruebas",
  "models_repo_dir": "ml_pipeline",
  "platform_repo_dir": "platform",
  "overwrite_threshold_months": 0.05,
  "run_baselines": false,
  "weather_overwrite_days": 14,
  "weather_forecast_days": 14,
  "max_validation_delay_days": 1,
  "latitude": 36.72016,
  "longitude": -4.42034,
  "timezone": "Europe/Madrid"
}
```

Opcionalmente se puede declarar `datacenter_bi_lib_path` o la variable de entorno `METRO_DATACENTER_BI_LIB_PATH` para habilitar la libreria corporativa `sp_DataCenterBI`.

## Dependencias

Las dependencias operativas del pipeline estan declaradas en `ml_pipeline/pyproject.toml`, incluyendo `requests`, `pytz`, `msal`, `pandera` y `requests-negotiate-sspi` para Windows.

## Idempotencia

La consolidacion de validaciones elimina en streaming los dias que se re-procesan antes de escribir los nuevos registros, evitando duplicados al relanzar el pipeline.

## Artefactos

Los modelos promovidos se leen desde:

- `ml_pipeline/artifacts/models/daily_modeling/tabular_hgbr__strict_available__all_series__h1.pkl`
- `ml_pipeline/artifacts/models/daily_modeling/tabular_hgbr__forecastable_scenario__all_series__h1.pkl`

Cada ejecucion escribe un resumen auditable en:

- `ml_pipeline/artifacts/monitoring/pipeline_run_summary.json`

El archivo contiene estado global, pasos ejecutados, criticidad, mensajes de fallo no critico, artefactos y tiempos. Los fallos no criticos quedan como `warning`; los fallos criticos abortan el pipeline tras escribir el resumen.

Cada entrenamiento escribe manifests locales de trazabilidad junto a sus metricas:

- `ml_pipeline/artifacts/daily_modeling/metrics/*__run_manifest.json`

El drift se publica en:

- `ml_pipeline/artifacts/monitoring/drift_metrics.json`
- `ml_pipeline/artifacts/monitoring/monitoring_summary.json`

El backend expone estas senales en `/metrics` para Prometheus.

## Reproducibilidad con DVC

El stage DVC principal es `daily_pipeline`:

```powershell
.\.venv\Scripts\dvc.exe repro daily_pipeline
```

Antes de ejecutarlo en una maquina nueva:

```powershell
.\.venv\Scripts\dvc.exe pull
Copy-Item pipelines\.env.example pipelines\.env
```

`pipelines/.env` debe rellenarse con credenciales reales fuera de Git. Los datos y modelos versionados se sincronizan con:

```powershell
.\.venv\Scripts\dvc.exe push
```
