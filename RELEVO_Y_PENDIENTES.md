# Relevo Tecnico: MetroScenarioStudio

## Estado Actual

`project-MetroScenarioStudio` queda como monorepo autonomo local. El backend, frontend, pipeline de ML, orquestador diario, datos DVC y configuracion Docker viven bajo esta carpeta.

Verificaciones de referencia de esta fase:

- Backend: `.\.venv\Scripts\python.exe -m pytest platform\backend\tests -q`
- ML pipeline: `.\.venv\Scripts\python.exe -m pytest ml_pipeline\tests -q`
- Frontend: `npm run build` desde `platform\frontend`

## Decisiones Cerradas

- No se modifica ninguna carpeta externa al monorepo.
- `ml_pipeline/conf/base/config.toml` resuelve datos desde `../data`.
- `ml_pipeline/conf/local/config.toml` queda ignorado por Git y reservado solo para overrides locales.
- El backend usa `ml_pipeline` como raiz de artefactos, no un repositorio externo.
- La demanda historica real se lee desde `MSS_HISTORICAL_DEMAND_CSV` o desde `platform/backend/storage/demanda_historica_MM.csv`.
- El pipeline diario resuelve rutas relativas desde la raiz del monorepo.

## Operacion Local

Arranque de la aplicacion:

```powershell
.\MetroScenarioStudio.cmd
```

Pipeline diario:

```powershell
.\.venv\Scripts\python.exe pipelines\run_pipeline.py
```

Configuracion principal:

- `pipelines/pipeline_config.json`
- `ml_pipeline/conf/base/config.toml`
- Variables opcionales: `MSS_HISTORICAL_DEMAND_CSV`, `MSS_METRO_DEMAND_MODELS_ROOT`, `METRO_DATACENTER_BI_LIB_PATH`

## Pendientes No Bloqueantes

- Configurar remoto DVC compartido y ejecutar `dvc push`.
- Definir registry corporativo de contenedores.
- Definir promocion de modelos con MLflow Model Registry.
- Programar ejecucion diaria desatendida con Task Scheduler, Airflow, Prefect o infraestructura corporativa.
- Desplegar Prometheus/Grafana y alertas sobre `/metrics`.

## Notas Para el Siguiente Relevo

- Los datos pesados y artefactos pueden existir localmente, pero deben seguir fuera de Git.
- `M:\...` sigue siendo el origen externo permitido para CSV brutos de validaciones.
- Las carpetas historicas externas pueden consultarse como referencia, pero el desarrollo activo debe ocurrir solo en `project-MetroScenarioStudio`.
