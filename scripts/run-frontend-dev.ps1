Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location (Join-Path $repoRoot "platform\frontend")

$env:VITE_API_BASE = "http://127.0.0.1:8011"
$env:VITE_API_PROXY_TARGET = "http://127.0.0.1:8011"

npm run dev -- --host 127.0.0.1 --port 5173
