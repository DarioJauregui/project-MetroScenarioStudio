# Metro Scenario Studio Backend

API FastAPI de `project-MetroScenarioStudio`.

Configuracion local relevante:

- `MSS_STORAGE_DIR`: storage local de SQLite, Excel y CSV historico. Por defecto `platform/backend/storage`.
- `MSS_METRO_DEMAND_MODELS_ROOT`: raiz de `ml_pipeline`.
- `MSS_HISTORICAL_DEMAND_CSV`: CSV opcional de demanda historica para enriquecer agregados reales.

Ejecucion desde la raiz del monorepo:

```powershell
.\.venv\Scripts\python.exe -m pytest platform\backend\tests -q
powershell -ExecutionPolicy Bypass -File .\scripts\run-backend-dev.ps1
```
