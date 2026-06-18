Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$backendRoot = Join-Path $repoRoot "platform\backend"
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    $python = "python"
}

Set-Location $backendRoot

$env:PYTHONPATH = $backendRoot
$env:MSS_STORAGE_DIR = Join-Path $backendRoot "storage"
$env:MSS_DATA_ROOT = Join-Path $repoRoot "data"
$env:MSS_METRO_DEMAND_MODELS_ROOT = Join-Path $repoRoot "ml_pipeline"
if (-not $env:MSS_EXPLANATION_LLM_ENABLED) {
    $env:MSS_EXPLANATION_LLM_ENABLED = "true"
}
if (-not $env:MSS_EXPLANATION_LLM_ENDPOINT) {
    $env:MSS_EXPLANATION_LLM_ENDPOINT = "http://127.0.0.1:1234/v1/chat/completions"
}
if (-not $env:MSS_EXPLANATION_LLM_MODEL) {
    $env:MSS_EXPLANATION_LLM_MODEL = "qwen3.6-35b-a3b"
}

& $python -c "from metro_scenario_studio.api.main import create_app; from metro_scenario_studio.core.config import get_settings; import uvicorn; uvicorn.run(create_app(get_settings()), host='127.0.0.1', port=8011, reload=False)"
