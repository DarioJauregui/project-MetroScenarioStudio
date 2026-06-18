Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$script:RepoRoot = Split-Path -Parent $PSScriptRoot
$script:RuntimeDir = Join-Path $script:RepoRoot "platform\backend\storage\runtime"
$script:BackendPidPath = Join-Path $script:RuntimeDir "backend.pid"
$script:FrontendPidPath = Join-Path $script:RuntimeDir "frontend.pid"
$script:BackendLogPath = Join-Path $script:RuntimeDir "backend.log"
$script:BackendErrorLogPath = Join-Path $script:RuntimeDir "backend.err.log"
$script:FrontendLogPath = Join-Path $script:RuntimeDir "frontend.log"
$script:FrontendErrorLogPath = Join-Path $script:RuntimeDir "frontend.err.log"
$script:BackendPort = 8011
$script:FrontendPort = 5173

function Write-Section {
    param([string]$Message)
    Write-Host ""
    Write-Host "== $Message ==" -ForegroundColor Cyan
}

function Assert-Command {
    param([string]$Name)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command '$Name' is not available."
    }
}

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

function Wait-HttpReady {
    param(
        [string]$Url,
        [int]$TimeoutSeconds,
        [string]$Label
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
                Write-Host "$Label is ready at $Url" -ForegroundColor Green
                return
            }
        } catch {
            Start-Sleep -Milliseconds 500
        }
    }

    throw "$Label did not become ready in $TimeoutSeconds seconds. Check logs in $script:RuntimeDir."
}

New-Item -ItemType Directory -Force -Path $script:RuntimeDir | Out-Null

Write-Section "Checking prerequisites"
if (-not (Test-Path (Join-Path $script:RepoRoot ".venv\Scripts\python.exe"))) {
    Assert-Command python
}
Assert-Command npm

Write-Section "Stopping previous Metro Scenario Studio processes"
Stop-ManagedProcess -PidFile $script:BackendPidPath -Label "backend"
Stop-ManagedProcess -PidFile $script:FrontendPidPath -Label "frontend"
Stop-PortListeners -Ports @($script:BackendPort, $script:FrontendPort)

Write-Section "Starting backend"
$null = Remove-Item $script:BackendLogPath -Force -ErrorAction SilentlyContinue
$null = Remove-Item $script:BackendErrorLogPath -Force -ErrorAction SilentlyContinue
$backendProcess = Start-Process powershell -ArgumentList @(
    "-NoLogo",
    "-NoProfile",
    "-ExecutionPolicy",
    "Bypass",
    "-File",
    (Join-Path $script:RepoRoot "scripts\run-backend-dev.ps1")
) -WorkingDirectory $script:RepoRoot -RedirectStandardOutput $script:BackendLogPath -RedirectStandardError $script:BackendErrorLogPath -WindowStyle Hidden -PassThru
Set-Content -Path $script:BackendPidPath -Value $backendProcess.Id
Wait-HttpReady -Url "http://127.0.0.1:$script:BackendPort/api/health" -TimeoutSeconds 45 -Label "Backend"

Write-Section "Starting frontend"
$null = Remove-Item $script:FrontendLogPath -Force -ErrorAction SilentlyContinue
$null = Remove-Item $script:FrontendErrorLogPath -Force -ErrorAction SilentlyContinue
$frontendProcess = Start-Process powershell -ArgumentList @(
    "-NoLogo",
    "-NoProfile",
    "-ExecutionPolicy",
    "Bypass",
    "-File",
    (Join-Path $script:RepoRoot "scripts\run-frontend-dev.ps1")
) -WorkingDirectory $script:RepoRoot -RedirectStandardOutput $script:FrontendLogPath -RedirectStandardError $script:FrontendErrorLogPath -WindowStyle Hidden -PassThru
Set-Content -Path $script:FrontendPidPath -Value $frontendProcess.Id
Wait-HttpReady -Url "http://127.0.0.1:$script:FrontendPort" -TimeoutSeconds 60 -Label "Frontend"

Write-Section "Metro Scenario Studio ready"
Write-Host "Frontend: http://127.0.0.1:$script:FrontendPort"
Write-Host "Backend:  http://127.0.0.1:$script:BackendPort"
Write-Host "Logs:     $script:RuntimeDir"

Start-Process "http://127.0.0.1:$script:FrontendPort" | Out-Null
