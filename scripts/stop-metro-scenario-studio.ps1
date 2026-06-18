Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$runtimeDir = Join-Path $repoRoot "platform\backend\storage\runtime"
$backendPidPath = Join-Path $runtimeDir "backend.pid"
$frontendPidPath = Join-Path $runtimeDir "frontend.pid"

function Stop-ManagedProcess {
    param(
        [string]$PidFile,
        [string]$Label
    )

    if (-not (Test-Path $PidFile)) {
        return
    }

    $rawPid = (Get-Content $PidFile -Raw).Trim()
    Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
    if (-not $rawPid) {
        return
    }

    $targetPid = [int]$rawPid
    $process = Get-Process -Id $targetPid -ErrorAction SilentlyContinue
    if ($null -ne $process) {
        Write-Host "Stopping managed $Label process $targetPid"
        Stop-Process -Id $targetPid -Force -ErrorAction SilentlyContinue
    }
}

function Stop-PortListeners {
    param([int[]]$Ports)
    foreach ($port in $Ports) {
        $connections = @(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
        foreach ($connection in $connections) {
            $targetPid = $connection.OwningProcess
            if (-not $targetPid) {
                continue
            }
            $process = Get-Process -Id $targetPid -ErrorAction SilentlyContinue
            if ($null -eq $process) {
                continue
            }
            Write-Host "Stopping process $($process.ProcessName) ($targetPid) listening on port $port"
            Stop-Process -Id $targetPid -Force -ErrorAction SilentlyContinue
        }
    }
}

Stop-ManagedProcess -PidFile $backendPidPath -Label "backend"
Stop-ManagedProcess -PidFile $frontendPidPath -Label "frontend"
Stop-PortListeners -Ports @(8011, 5173)
Write-Host "Metro Scenario Studio stopped."
