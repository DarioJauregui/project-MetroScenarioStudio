param(
    [int[]]$Ports = @(80, 3000, 5000, 8000, 8011, 8080, 9090, 5173),
    [switch]$SkipDocker,
    [Alias("WhatIf")]
    [switch]$Preview
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$runtimeDir = Join-Path $repoRoot "platform\backend\storage\runtime"
$pidFiles = @(
    @{ Path = Join-Path $runtimeDir "backend.pid"; Label = "backend" },
    @{ Path = Join-Path $runtimeDir "frontend.pid"; Label = "frontend" }
)

function Stop-PidFileProcess {
    param(
        [string]$PidFile,
        [string]$Label
    )

    if (-not (Test-Path $PidFile)) {
        return
    }

    $rawPid = (Get-Content $PidFile -Raw).Trim()
    if (-not $rawPid) {
        Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
        return
    }

    $targetPid = [int]$rawPid
    $process = Get-Process -Id $targetPid -ErrorAction SilentlyContinue
    if ($null -eq $process) {
        Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
        return
    }

    $description = "$Label process $($process.ProcessName) ($targetPid)"
    if ($Preview) {
        Write-Host "Would stop $description"
        return
    }

    Stop-Process -Id $targetPid -Force -ErrorAction SilentlyContinue
    Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
    Write-Host "Stopped $description"
}

function Stop-PortListener {
    param([int]$Port)

    $connections = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
    if ($connections.Count -eq 0) {
        Write-Host "Port $Port is free."
        return
    }

    foreach ($connection in $connections) {
        $targetPid = $connection.OwningProcess
        if (-not $targetPid) {
            continue
        }

        $process = Get-Process -Id $targetPid -ErrorAction SilentlyContinue
        if ($null -eq $process) {
            Write-Host "Port $Port reports stale listener pid $targetPid; no running process was found."
            continue
        }

        $description = "process $($process.ProcessName) ($targetPid) listening on port $Port"
        if ($Preview) {
            Write-Host "Would stop $description"
            continue
        }

        Stop-Process -Id $targetPid -Force -ErrorAction SilentlyContinue
        Write-Host "Stopped $description"
    }
}

function Stop-DockerComposeStack {
    $composeFile = Join-Path $repoRoot "infrastructure\docker-compose.yml"
    if ($SkipDocker -or -not (Test-Path $composeFile) -or -not (Get-Command docker -ErrorAction SilentlyContinue)) {
        return
    }

    if ($Preview) {
        Write-Host "Would run docker compose down for Metro Scenario Studio."
        return
    }

    docker compose -f $composeFile down
}

if ($Preview) {
    Write-Host "Preview mode: no process will be stopped."
}
Write-Host "Clearing Metro Scenario Studio ports: $($Ports -join ', ')"

foreach ($pidFile in $pidFiles) {
    Stop-PidFileProcess -PidFile $pidFile.Path -Label $pidFile.Label
}

Stop-DockerComposeStack

foreach ($port in $Ports) {
    Stop-PortListener -Port $port
}

Write-Host "Port cleanup finished."
