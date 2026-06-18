# Metro Scenario Studio

Monorepo local autonomo para prediccion diaria de demanda, simulacion de escenarios y supervision tecnica de modelos de Metro de Malaga.

La carpeta `project-MetroScenarioStudio` es ahora la unidad de trabajo y es la unión de los repos legacy externos metro-demand-models y metro-demand-platform. Estos no son dependencias runtime del monorepo.

## Estructura

- `ml_pipeline/`: paquete Python `metro-demand-models`, entrenamiento, inferencia, drift y artefactos de modelos.
- `platform/backend/`: API FastAPI, SQLite local, exportacion/importacion Excel y endpoint Prometheus `/metrics`.
- `platform/frontend/`: aplicacion React/Vite.
- `pipelines/`: orquestador diario local para refrescar datos, reentrenar y validar modelos.
- `data/`: datos locales y punteros DVC para maestros pesados.
- `infrastructure/`: Docker Compose local.

## Instalacion Local

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e "ml_pipeline[dev]"
.\.venv\Scripts\python.exe -m pip install -e "platform/backend[dev]"
cd platform\frontend
npm ci
```

`ml_pipeline/conf/base/config.toml` resuelve los datos desde `../data` y los artefactos desde `ml_pipeline/artifacts`. Si un equipo necesita sobrescrituras locales, copie `ml_pipeline/conf/local/config.template.toml` a `ml_pipeline/conf/local/config.toml`; ese archivo esta ignorado por Git.

## Arranque de la Plataforma

```powershell
.\MetroScenarioStudio.cmd
```

URLs:

- Frontend: `http://127.0.0.1:5173`
- Backend: `http://127.0.0.1:8011`
- Metricas Prometheus: `http://127.0.0.1:8011/metrics`

El backend lee eventos y meteorologia desde `data/` mediante `MSS_DATA_ROOT`. Por defecto apunta a la carpeta `data` del monorepo. Si se necesita otra ubicacion:

```powershell
$env:MSS_DATA_ROOT = "D:\metro\data"
```

Para parar procesos lanzados por el script:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\stop-metro-scenario-studio.ps1
```

Para liberar puertos habituales del proyecto (`80`, `8000`, `8011`, `5173`) y bajar el stack Docker si esta activo:

```powershell
.\VaciarPuertosMetroScenarioStudio.cmd
```

Modo simulacion, sin parar procesos:

```powershell
.\VaciarPuertosMetroScenarioStudio.cmd -WhatIf
```

Puertos concretos:

```powershell
.\VaciarPuertosMetroScenarioStudio.cmd -Ports 8000,8011,5173
```

## Verificacion

```powershell
.\.venv\Scripts\python.exe -m pytest platform\backend\tests -q
.\.venv\Scripts\python.exe -m pytest ml_pipeline\tests -q
cd platform\frontend
npm run build
```

## Pipeline Diario

El pipeline se ejecuta desde la raiz del monorepo:

```powershell
.\.venv\Scripts\python.exe pipelines\run_pipeline.py
```

La configuracion vive en `pipelines/pipeline_config.json`. `models_repo_dir` y `platform_repo_dir` son relativos a la raiz del monorepo por defecto. El unico origen externo admitido en esta fase es la carpeta de validaciones brutas configurada en `data_source_dir` (`M:\...` en el entorno local actual).

Para construir datasets operativos completos, deben existir en `data/raw` los workbooks configurados en `ml_pipeline/conf/base/config.toml`, por ejemplo `Servicios Hist*.xlsx`. Si faltan, el pipeline continua con los pasos no criticos, pero no genera esos datasets operativos.

## Trazabilidad MLOps

Cada entrenamiento tabular registra en MLflow y deja un manifest local junto a las metricas:

- `ml_pipeline/artifacts/daily_modeling/metrics/*__run_manifest.json`
- parametros efectivos del modelo y variante
- columnas de features utilizadas
- ruta y hash del dataset cuando esta disponible
- hash, tamano y existencia de artefactos generados
- commit/branch/estado Git detectado

MLflow usa por defecto `ml_pipeline/mlruns`; puede apuntar a un servidor externo mediante `ml_pipeline/conf/local/config.toml` o la configuracion base.

El pipeline diario genera un resumen estructurado en:

- `ml_pipeline/artifacts/monitoring/pipeline_run_summary.json`

La monitorizacion genera:

- `ml_pipeline/artifacts/monitoring/drift_metrics.json`
- `ml_pipeline/artifacts/monitoring/monitoring_summary.json`

El endpoint `/metrics` expone WAPE/SMAPE, drift, estado de monitorizacion, estado de ultima ejecucion del pipeline y edad de artefactos clave.

## Docker y Registry

Construccion local:

```powershell
docker compose -f infrastructure\docker-compose.yml build
docker compose -f infrastructure\docker-compose.yml up -d
```

Pruebas esperadas:

```powershell
Invoke-WebRequest http://127.0.0.1/api/health -UseBasicParsing
Invoke-WebRequest http://127.0.0.1 -UseBasicParsing
```

Para etiquetar imagenes hacia un registry:

```powershell
$env:MSS_REGISTRY_PREFIX = "registry.example.com/metro"
$env:MSS_IMAGE_TAG = "dev-20260617"
.\scripts\build-docker-images.ps1
```

Para publicar:

```powershell
docker login registry.example.com
.\scripts\push-docker-images.ps1
```

El prefijo debe incluir host y namespace/proyecto, pero no el nombre final de cada imagen. Los nombres publicados son:

- `metro-scenario-studio-backend`
- `metro-scenario-studio-frontend`

## Datos y DVC

Los datos pesados permanecen fuera de Git. DVC esta configurado con un remoto local por defecto:

```powershell
C:\Users\d.jauregui\DVCRemotes\MetroScenarioStudio
```

El repositorio versiona con DVC:

- maestros externos en `data/external/datos_externos`;
- features externas finales en `data/processed/external_features/external_daily_features.parquet`;
- agregados operativos finales en `data/processed/operations`;
- validacion consolidada actual en `data/processed/validaciones/validaciones_consolidado.parquet`;
- modelos diarios promovidos en `ml_pipeline/artifacts/models/daily_modeling`.

Flujo habitual:

```powershell
.\.venv\Scripts\dvc.exe pull
.\.venv\Scripts\dvc.exe repro daily_pipeline
.\.venv\Scripts\dvc.exe push
```

`dvc.yaml` define el stage `daily_pipeline` para ejecutar `pipelines/run_pipeline.py` y registrar metricas operativas ligeras. El remoto corporativo compartido queda como fase posterior: basta con cambiar `remote.localremote.url` o anadir un nuevo remoto DVC.

## Limites de Esta Fase

Esta fase deja el monorepo listo para uso local autonomo. Quedan como fase posterior: DVC remoto compartido, registry de modelos, despliegue corporativo, CI/CD de contenedores, orquestador productivo y alertas corporativas.
