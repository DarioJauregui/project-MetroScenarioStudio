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
- Docker Compose levanta backend, frontend, MLflow, Prometheus y Grafana.
- En Docker, las llamadas a LLM local usan `host.docker.internal:1234`; el proxy frontend permite explicaciones largas hasta 900 segundos.

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

Stack Docker local:

```powershell
docker compose -f infrastructure\docker-compose.yml up -d --build
```

URLs principales:

- Frontend: `http://127.0.0.1:8080`
- Backend: `http://127.0.0.1:8011`
- MLflow: `http://127.0.0.1:5000`
- Prometheus: `http://127.0.0.1:9090`
- Grafana: `http://127.0.0.1:3000` (`admin` / `admin`)

## Pendientes No Bloqueantes

- Configurar remoto DVC compartido y ejecutar `dvc push`.
- Definir registry corporativo de contenedores.
- Definir promocion de modelos con MLflow Model Registry.
- Programar ejecucion diaria desatendida con Task Scheduler, Airflow, Prefect o infraestructura corporativa.
- Conectar alertas de Prometheus/Grafana a canales corporativos.
- Anadir, si se necesita, un dashboard/catalogo especifico para calidad de datos y versiones DVC.

## Notas Para el Siguiente Relevo

- Los datos pesados y artefactos pueden existir localmente, pero deben seguir fuera de Git.
- `M:\...` sigue siendo el origen externo permitido para CSV brutos de validaciones.
- Las carpetas historicas externas pueden consultarse como referencia, pero el desarrollo activo debe ocurrir solo en `project-MetroScenarioStudio`.
