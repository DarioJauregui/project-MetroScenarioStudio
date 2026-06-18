param(
    [string]$RegistryPrefix = $env:MSS_REGISTRY_PREFIX,
    [string]$Tag = $env:MSS_IMAGE_TAG
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$composeFile = Join-Path $repoRoot "infrastructure\docker-compose.yml"

function Invoke-Docker {
    param([string[]]$Arguments)

    & docker @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "docker $($Arguments -join ' ') failed with exit code $LASTEXITCODE."
    }
}

if (-not $RegistryPrefix) {
    throw "RegistryPrefix is required. Example: -RegistryPrefix registry.example.com/metro"
}

if (-not $Tag) {
    $Tag = (Get-Date -Format "yyyyMMdd-HHmm")
}

Invoke-Docker @("compose", "-f", $composeFile, "build")

$backendImage = "$RegistryPrefix/metro-scenario-studio-backend:$Tag"
$frontendImage = "$RegistryPrefix/metro-scenario-studio-frontend:$Tag"

Invoke-Docker @("tag", "infrastructure-backend:latest", $backendImage)
Invoke-Docker @("tag", "infrastructure-frontend:latest", $frontendImage)

Write-Host "Tagged images:"
Write-Host "  $backendImage"
Write-Host "  $frontendImage"
