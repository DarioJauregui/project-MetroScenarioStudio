# Plan Maestro de Migración Técnico Detallado: Metro Scenario Studio

Este documento detalla la hoja de ruta definitiva para refactorizar y migrar el proyecto de predicción de demanda de Metro de Málaga a una arquitectura unificada, robusta y reproducible en producción.

---

## 1. Principios de Operación e Inmutabilidad

1.  **Aislamiento Total del Repositorio:** El directorio `project-MetroScenarioStudio` será autónomo. No se referenciarán carpetas externas al repositorio, con excepción del origen de red `M:\...` que provee las transacciones brutas de validaciones.
2.  **Uso Exclusivo de Rutas Relativas:** Todas las configuraciones locales y del código deberán derivar dinámicamente sus rutas basándose en la raíz del monorepo (`.`). Quedan prohibidos los strings absolutos del sistema de archivos local (`C:\Users\...`).
3.  **Inmutabilidad de Datos de Entrada:** Los maestros y datos meteorológicos de entrada deben versionarse. Los archivos binarios grandes de datos (ej. `.parquet`, `.xlsx`, `.pkl`) no se guardarán en Git, sino que se gestionarán mediante `DVC`.
4.  **Alineación de Entornos de Dependencia:** Se evitará la discrepancia de entornos virtuales cruzados mediante la instalación del monorepo como un workspace unificado o mediante contenedores.

---

## 2. Inventario Exhaustivo de Archivos

### 2.1. Componente: Pipeline de ML (`ml_pipeline/`)
Se migrarán solo los archivos activos del pipeline de modelado diario y se descartarán los que sirvieron únicamente para la memoria académica o análisis exploratorios.

*   **A Migrar e Integrar:**
    *   `metro-demand-models/src/metro_demand_models/data/` $\rightarrow$ Copiar `__init__.py`, `contracts.py`, `inspection.py`, `io.py`, `modeling.py` y `validation.py` a `ml_pipeline/src/data/`.
    *   `metro-demand-models/src/metro_demand_models/data/operations/` $\rightarrow$ Copiar `__init__.py`, `common.py`, `events.py`, `incidents.py`, `pipeline.py` y `services.py` a `ml_pipeline/src/data/operations/`.
    *   `metro-demand-models/src/metro_demand_models/features/daily.py` $\rightarrow$ Copiar a `ml_pipeline/src/features/daily.py`.
    *   `metro-demand-models/src/metro_demand_models/models/` $\rightarrow$ Copiar `__init__.py`, `baselines.py` y `tabular.py` a `ml_pipeline/src/models/`.
    *   `metro-demand-models/src/metro_demand_models/training/daily.py` $\rightarrow$ Copiar a `ml_pipeline/src/training/daily.py`.
    *   `metro-demand-models/src/metro_demand_models/evaluation/daily.py` $\rightarrow$ Copiar a `ml_pipeline/src/evaluation/daily.py`.
    *   `metro-demand-models/src/metro_demand_models/evaluation/special_days.py` $\rightarrow$ Copiar a `ml_pipeline/src/evaluation/special_days.py`.
    *   `metro-demand-models/src/metro_demand_models/evaluation/supervision.py` $\rightarrow$ Copiar a `ml_pipeline/src/evaluation/supervision.py`.
    *   `metro-demand-models/src/metro_demand_models/inference/daily.py` $\rightarrow$ Copiar a `ml_pipeline/src/inference/daily.py`.
    *   `metro-demand-models/src/metro_demand_models/utils/` $\rightarrow$ Copiar `__init__.py`, `environment.py`, `logging.py`, `stations.py` y `tracking.py` a `ml_pipeline/src/utils/`.
    *   `metro-demand-models/conf/base/config.toml` $\rightarrow$ Copiar a `ml_pipeline/conf/base/config.toml`.
    *   `metro-demand-models/scripts/` $\rightarrow$ Copiar los scripts de ejecución del pipeline diario:
        *   `build_daily_training_dataset.py`
        *   `build_operational_datasets.py`
        *   `train.py`
        *   `evaluate.py`
        *   `generate_daily_supervision_artifacts.py`
        *   `generate_special_day_error_analysis.py`
        *   `run_daily_inference_smoke.py`
*   **A Descartar (No copiar por redundancia o desuso):**
    *   `metro-demand-models/scripts/generate_memory_support_artifacts.py` (Solo generaba gráficos de soporte para la memoria académica).
    *   `metro-demand-models/src/metro_demand_models/evaluation/memory_support.py` (Lógica interna para exportar figuras de tesis).
    *   `metro-demand-models/notebooks/` (Todos los Jupyter Notebooks exploratorios se descartan de producción).
    *   `metro-demand-models/scripts/inspect_modeling_data.py` e `inspect_operational_sources.py` (Herramientas de debug inicial de datos).

### 2.2. Componente: Plataforma Web (`platform/`)

*   **A Migrar en `platform/backend/` (FastAPI API):**
    *   `metro-demand-platform/backend/metro_scenario_studio/` $\rightarrow$ Copiar la estructura completa de subcarpetas (`api/`, `core/`, `domain/`, `repositories/`, `services/`) y archivos principales (`__init__.py`, `__main__.py`).
*   **A Migrar en `platform/frontend/` (React SPA):**
    *   `metro-demand-platform/frontend/` $\rightarrow$ Copiar código fuente (`src/`), configuración de Vite (`vite.config.ts`), archivo de dependencias (`package.json`, `package-lock.json`), HTML de entrada (`index.html`) y elementos de entorno `.env`. Descartar la carpeta `node_modules` para regenerarla de forma limpia.

### 2.3. Componente: Pipelines de Ejecución (`pipelines/` $\rightarrow$ `infrastructure/pipelines/`)

*   **A Migrar:**
    *   `pipelines/run_pipeline.py` $\rightarrow$ Copiar a `infrastructure/pipelines/run_pipeline.py`.
    *   `pipelines/export_calendarioEventos.py` $\rightarrow$ Copiar a `infrastructure/pipelines/export_calendarioEventos.py`.
    *   `pipelines/pipeline_config.json` $\rightarrow$ Copiar a `infrastructure/pipelines/pipeline_config.json`.
    *   `pipelines/.env` $\rightarrow$ Copiar credenciales de Azure a `infrastructure/pipelines/.env`.

---

## 3. Guía Detallada de Refactorización y Configuración

### Fase 1: Inicialización del Repositorio y Control de Datos (DVC)

1.  **DVC Setup:** En la raíz del repositorio, inicializar DVC y configurarlo para almacenar datasets.
    ```bash
    git init
    dvc init
    ```
2.  **Configurar Archivo `.gitignore` global:**
    ```text
    # Entornos virtuales e IDEs
    .venv/
    .idea/
    .vscode/
    __pycache__/
    *.pyc
    
    # Datos locales y binarios pesados (Gestionados por DVC)
    data/
    mlruns/
    platform/backend/storage/
    
    # Logs y runtime locales
    *.log
    .pytest_cache/
    .ruff_cache/
    ```
3.  **Configurar estructura de datos bajo control de DVC:**
    Mover los archivos maestros iniciales a `data/external/datos_externos/masters/` e integrarlos a DVC:
    ```bash
    dvc add data/external/datos_externos/masters/stations_master.parquet
    dvc add data/external/datos_externos/masters/lines_master.parquet
    dvc add data/external/datos_externos/masters/equipment_master.parquet
    dvc add data/external/datos_externos/masters/equipment_significant_master.parquet
    dvc add data/external/datos_externos/masters/network_changes_history.parquet
    dvc add data/external/datos_externos/config/metro_stations.csv
    dvc add data/external/datos_externos/Festivos.xlsx
    git add .dvcconfig data/external/datos_externos/masters/.gitignore ...
    ```

### Fase 2: Implementación de Calidad de Datos con Pandera

Para cumplir el control estricto de calidad en la ingesta, se creará un validador basado en **Pandera** en `ml_pipeline/src/validation/schemas.py`:

```python
import pandas as pd
import pandera as pa
from pandera.typing import Series

class ValidationSchema(pa.SchemaModel):
    fecha_validacion: Series[pd.DatetimeTZDtype] = pa.Field(dtype_kwargs={"tz": "Europe/Madrid"})
    linea: Series[str] = pa.Field(coerce=True)
    estacion: Series[str] = pa.Field(coerce=True)
    cod_eq: Series[str] = pa.Field(coerce=True)
    tipo_validacion: Series[str] = pa.Field(coerce=True)
    tipo_titulo: Series[str] = pa.Field(coerce=True)
    id_tarjeta: Series[str] = pa.Field(coerce=True)
    num_tarjeta: Series[str] = pa.Field(coerce=True)
    dinero_deducido: Series[float] = pa.Field(ge=0.0, coerce=True)
    saldo_restante: Series[float] = pa.Field(coerce=True)
    viajes_deducidos: Series[int] = pa.Field(ge=0, coerce=True)
    dia: Series[str] = pa.Field(nullable=False)

    class Config:
        strict = True  # Rechaza columnas adicionales no definidas en el contrato
        coerce = True  # Fuerza el casting de tipos de datos automáticamente
```

Este esquema será importado en `infrastructure/pipelines/run_pipeline.py` en la sección de ingesta de CSVs antes de la consolidación incremental para garantizar que ninguna transacción inválida envenene el parquet consolidado.

### Fase 3: Refactorización de Rutas Relativas

#### A. Backend Config (`platform/backend/metro_scenario_studio/core/config.py`)
Modificar la resolución dinámica para que asuma que el pipeline de ML vive adyacente al backend en el monorepo.

```python
# Modificar en: platform/backend/metro_scenario_studio/core/config.py
def _default_models_root() -> Path:
    # Si la API corre en platform/backend, models root vive en la raíz adyacente: ../../ml_pipeline
    return platform_root().parent / "ml_pipeline"
```

#### B. Pipeline Orchestrator Config (`infrastructure/pipelines/pipeline_config.json`)
Sustituir las rutas absolutas por rutas relativas a la raíz del monorepo:

```json
{
  "data_source_dir": "M:\\AOPJA\\Informes\\1_Inf_diarios\\xx_Automaticos_EnPruebas",
  "models_repo_dir": "../../ml_pipeline",
  "platform_repo_dir": "../../platform",
  "overwrite_threshold_months": 0.05,
  "missing_days_warning_threshold": 2,
  "run_baselines": false,
  "weather_overwrite_days": 14,
  "weather_forecast_days": 14,
  "max_validation_delay_days": 1,
  "latitude": 36.72016,
  "longitude": -4.42034,
  "timezone": "Europe/Madrid"
}
```

---

## 4. Contenedores y Orquestación (Docker)

Para productizar la solución y aislarla del sistema de archivos del host, se usarán imágenes Docker multi-etapa y Docker Compose.

### 4.1. Dockerfile del Backend (`platform/backend/Dockerfile`)
```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Instalar dependencias del sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8011

CMD ["uvicorn", "metro_scenario_studio.api.main:create_app", "--host", "0.0.0.0", "--port", "8011"]
```

### 4.2. Dockerfile del Frontend (`platform/frontend/Dockerfile`)
```dockerfile
# Build stage
FROM node:20-alpine AS build-stage
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
RUN npm run build

# Production stage
FROM nginx:stable-alpine AS production-stage
COPY --from=build-stage /app/dist /usr/share/nginx/html
# Copiar configuración custom de nginx para manejar el fallback de SPA routing
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```

### 4.3. Dockerfile del ML Pipeline (`ml_pipeline/Dockerfile`)
```dockerfile
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
RUN pip install --no-cache-dir .

COPY . .

# Comando por defecto para ejecutar tareas programadas de reentrenamiento
CMD ["python", "scripts/train.py"]
```

### 4.4. Orquestación (`infrastructure/docker-compose.yml`)
```yaml
version: '3.8'

services:
  frontend:
    build:
      context: ../platform/frontend
      dockerfile: Dockerfile
    ports:
      - "80:80"
    depends_on:
      - backend

  backend:
    build:
      context: ../platform/backend
      dockerfile: Dockerfile
    ports:
      - "8011:8011"
    environment:
      - MSS_STORAGE_DIR=/app/storage
      - MSS_SQLITE_PATH=/app/storage/metro_scenario_studio.db
      - MSS_METRO_DEMAND_MODELS_ROOT=/app/ml_pipeline
      - MSS_USE_MOCK_INFERENCE=false
    volumes:
      - backend_storage:/app/storage
      - ../ml_pipeline:/app/ml_pipeline:ro # Monta los artefactos de modelos entrenados como solo lectura

  mlflow:
    image: ghcr.io/mlflow/mlflow:latest
    ports:
      - "5000:5000"
    volumes:
      - ../ml_pipeline/mlruns:/app/mlruns
    command: mlflow server --backend-store-uri sqlite:///mlflow.db --default-artifact-root /app/mlruns --host 0.0.0.0 --port 5000

volumes:
  backend_storage:
```

---

## 5. Plan de Observabilidad y AIOps

### 5.1. Detección de Data Drift (Evidently)
Se añadirá una tarea programada (`ml_pipeline/scripts/monitor_drift.py`) que compare estadísticamente la distribución de las variables de inferencia semanales (`current`) frente al dataset de entrenamiento base registrado (`reference`):

```python
import pandas as pd
from evidently.report import Report
from evidently.metric_preset import DataDriftPreset

def calculate_drift(reference_path: str, current_path: str, output_report_path: str):
    ref_df = pd.read_parquet(reference_path)
    cur_df = pd.read_parquet(current_path)
    
    # Instanciar reporte de drift
    data_drift_report = Report(metrics=[
        DataDriftPreset(),
    ])
    
    data_drift_report.run(reference_data=ref_df, current_data=cur_df)
    data_drift_report.save_html(output_report_path)
    
    # Extraer métricas para Prometheus
    report_dict = data_drift_report.as_dict()
    dataset_drift = report_dict["metrics"][0]["result"]["dataset_drift"]
    return dataset_drift
```

### 5.2. Scrapeo de Métricas (Prometheus + Grafana)
1.  **Prometheus Config (`infrastructure/prometheus/prometheus.yml`):**
    ```yaml
    global:
      scrape_interval: 15s

    scrape_configs:
      - job_name: 'metro-scenario-backend'
        metrics_path: '/api/metrics'
        static_configs:
          - targets: ['backend:8011']
    ```
2.  **Dashboards de Observabilidad (Grafana):**
    Crear paneles para monitorizar:
    *   Latencia del endpoint `/api/scenarios/{id}/run`.
    *   Porcentaje de Data Drift general reportado por Evidently.
    *   Consumo de CPU/Memoria del contenedor de FastAPI.

---

## 6. Automatización de Ciclo de Vida (CI/CD)

El archivo `.github/workflows/ci.yml` ejecutará las pruebas automáticas y validará el formateo en cada cambio:

```yaml
name: CI/CD Pipeline

on:
  push:
    branches: [ main ]
  pull_request:
    branches: [ main ]

jobs:
  validate-and-test:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v3

    - name: Set up Python 3.12
      uses: actions/setup-python@v4
      with:
        python-python-version: '3.12'

    - name: Install Linting Tools
      run: |
        python -m pip install --upgrade pip
        pip install ruff pytest

    - name: Run Linting Checks
      run: ruff check .

    - name: Install Dependencies and Test ML Pipeline
      run: |
        cd ml_pipeline
        pip install -e .
        pytest

    - name: Install Dependencies and Test Backend
      run: |
        cd platform/backend
        pip install -e .
        pytest
```

---

## 7. Plan de Verificación de Migración

Tras mover los archivos a la estructura indicada, se realizarán las siguientes pruebas de consistencia:

1.  **Verificación de Importaciones:** Asegurar que `python -c "import ml_pipeline.src.data"` se ejecuta sin `ModuleNotFoundError`.
2.  **Verificación de Tests:** Ejecutar `pytest` en la raíz del backend y del ML pipeline y confirmar que el 100% de los tests pasan.
3.  **Verificación de Rutas Relativas:** Mover el directorio completo `project-MetroScenarioStudio` a otra ruta local en la máquina y certificar que la aplicación se inicia correctamente sin errores de rutas ausentes.
4.  **Despliegue Local Docker:** Ejecutar `docker-compose up --build -d` en `infrastructure/` y verificar que la interfaz de usuario en `http://localhost` carga las predicciones correctamente.
