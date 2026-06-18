param(
    [string]$RegistryPrefix = $env:MSS_REGISTRY_PREFIX,
    [string]$Tag = $env:MSS_IMAGE_TAG
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not $RegistryPrefix) {
    throw "RegistryPrefix is required. Example: -RegistryPrefix registry.example.com/metro"
}

if (-not $Tag) {
    throw "Tag is required. Use the same tag produced by scripts\build-docker-images.ps1."
}

$backendImage = "$RegistryPrefix/metro-scenario-studio-backend:$Tag"
$frontendImage = "$RegistryPrefix/metro-scenario-studio-frontend:$Tag"

function Invoke-Docker {
    param([string[]]$Arguments)

    & docker @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "docker $($Arguments -join ' ') failed with exit code $LASTEXITCODE."
    }
}

Invoke-Docker @("push", $backendImage)
Invoke-Docker @("push", $frontendImage)

Write-Host "Pushed images:"
Write-Host "  $backendImage"
Write-Host "  $frontendImage"
