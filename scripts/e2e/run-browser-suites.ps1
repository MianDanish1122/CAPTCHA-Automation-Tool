<#
.SYNOPSIS
  Reproduce the browser test environment and run the Playwright suites (Windows PowerShell 5.1+).

.DESCRIPTION
  For each suite this script:
    * creates an ISOLATED throw-away SQLite database (never data\captcha_tool.db),
    * generates RANDOM credentials in memory for this run only (nothing is hard-coded, nothing is written to disk),
    * starts the backend (uvicorn, :8000) and the production frontend (next start, :3000),
    * runs the suite, then stops ONLY the processes it started.
  It refuses to start if port 8000 or 3000 is already in use (it never kills processes it did not start).
  Evidence (screenshots / JSON) is written to -OutDir (default: .e2e_runs\<timestamp>), NOT to the tracked
  evidence\ folders, so a regression run never rewrites committed evidence.

.PARAMETER Suite
  phase7 | phase6b | batch | demo | all

.PARAMETER Build
  Run "npm run build" in frontend\ first (needed once, and after any frontend change).

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\e2e\run-browser-suites.ps1 -Suite all -Build

.NOTES
  Prerequisites: the project venv (venv\Scripts\python.exe) with requirements installed, "playwright install chromium",
  Node.js + "npm install" in frontend\. The demo suite uses scripts\demo_env.py, which keeps its own isolated
  database and random demo accounts in demo_runtime\ (git-ignored).
#>
[CmdletBinding()]
param(
  [ValidateSet('phase7', 'phase6b', 'batch', 'demo', 'all')][string]$Suite = 'all',
  [switch]$Build,
  [string]$OutDir
)

$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$Py = Join-Path $Root 'venv\Scripts\python.exe'
if (-not (Test-Path $Py)) { throw "Python venv not found at $Py. Create it and install requirements first." }
if (-not $OutDir) { $OutDir = Join-Path $Root ('.e2e_runs\' + (Get-Date -Format 'yyyyMMdd-HHmmss')) }
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$LogDir = Join-Path $OutDir 'logs'
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
foreach ($d in 'phase7_e2e', 'phase6b', 'batch_ui', 'demo_rehearsal') { New-Item -ItemType Directory -Force -Path (Join-Path $OutDir $d) | Out-Null }
$env:E2E_OUT_DIR = $OutDir

function New-RandomSecret([int]$bytes = 18) {
  $b = New-Object byte[] $bytes
  [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b)
  return ([Convert]::ToBase64String($b) -replace '[^A-Za-z0-9]', 'x') + 'Aa1!'
}

function Assert-PortFree([int]$port) {
  if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) {
    throw "Port $port is already in use. Stop that process yourself, then retry (this script never kills processes it did not start)."
  }
}

function Wait-Http([string]$url, [int]$seconds = 90) {
  $deadline = (Get-Date).AddSeconds($seconds)
  while ((Get-Date) -lt $deadline) {
    try { if ((Invoke-WebRequest -UseBasicParsing -Uri $url -TimeoutSec 3).StatusCode -eq 200) { return } } catch { }
    Start-Sleep -Seconds 2
  }
  throw "Timed out waiting for $url"
}

$script:Started = @()
function Start-Tracked([string]$exe, [string[]]$arguments, [string]$workDir, [string]$name) {
  $p = Start-Process -FilePath $exe -ArgumentList $arguments -WorkingDirectory $workDir -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $LogDir "$name.out.log") -RedirectStandardError (Join-Path $LogDir "$name.err.log")
  $script:Started += $p
  return $p
}

function Stop-Started {
  foreach ($p in $script:Started) { if ($p -and -not $p.HasExited) { & taskkill.exe /PID $p.Id /T /F | Out-Null } }
  $script:Started = @()
  Start-Sleep -Seconds 2
}

function New-IsolatedEnv([string]$label) {
  $tmp = Join-Path ([IO.Path]::GetTempPath()) ("captcha_e2e_${label}_" + [Guid]::NewGuid().ToString('N'))
  New-Item -ItemType Directory -Force -Path $tmp | Out-Null
  $env:DATABASE_URL = 'sqlite:///' + ((Join-Path $tmp 'e2e.db') -replace '\\', '/')
  $env:APP_ENV = 'development'
  $env:ALLOW_DEV_LOOPBACK = 'true'
  $env:E2E_OPERATOR_USER = 'e2e_operator'
  $env:E2E_OPERATOR_PASSWORD = New-RandomSecret
  $env:E2E_ADMIN_USER = 'e2e_admin'
  $env:E2E_ADMIN_PASSWORD = New-RandomSecret
  return $tmp
}

function Start-Servers {
  Assert-PortFree 8000; Assert-PortFree 3000
  Start-Tracked $Py @('-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8000') $Root 'backend' | Out-Null
  Start-Tracked 'npm.cmd' @('run', 'start', '--', '-p', '3000') (Join-Path $Root 'frontend') 'frontend' | Out-Null
  Wait-Http 'http://127.0.0.1:8000/health'
  Wait-Http 'http://localhost:3000/login'
}

function Invoke-Py([string[]]$arguments) {
  # Show the output on the console but return ONLY the exit code (otherwise the output lines would be returned
  # too, and Windows PowerShell 5.1 turns native stderr text into error records under -ErrorAction Stop).
  $previous = $ErrorActionPreference
  $ErrorActionPreference = 'Continue'
  try {
    & $Py @arguments 2>&1 | ForEach-Object { Write-Host $_ }
    $code = $LASTEXITCODE
  } finally { $ErrorActionPreference = $previous }
  return [int]$code
}

$results = [ordered]@{}

function Run-ScriptSuite([string]$name, [string]$script, [bool]$hasCleanup) {
  Write-Host "`n=== $name ===" -ForegroundColor Cyan
  $tmp = New-IsolatedEnv $name
  $code = 1
  try {
    Push-Location $Root
    if ((Invoke-Py @($script, 'seed')) -ne 0) { throw "$name seed failed" }
    Start-Servers
    $code = Invoke-Py @($script, 'run')
    if ($hasCleanup) { Invoke-Py @($script, 'cleanup') | Out-Null }
  } catch { Write-Host $_.Exception.Message -ForegroundColor Red }
  finally { Pop-Location; Stop-Started; Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue }
  $results[$name] = if ($code -eq 0) { 'PASS' } else { 'FAIL' }
}

function Run-Demo {
  Write-Host "`n=== demo rehearsal ===" -ForegroundColor Cyan
  $code = 1
  try {
    Push-Location $Root
    # scripts.demo_env keeps an isolated DB + random accounts under demo_runtime\ (git-ignored)
    if ((Invoke-Py @('-m', 'scripts.demo_env', 'setup', '--reset')) -ne 0) { throw 'demo setup failed' }
    $env:DATABASE_URL = 'sqlite:///' + ((Join-Path $Root 'demo_runtime\demo.db') -replace '\\', '/')
    $env:APP_ENV = 'development'; $env:ALLOW_DEV_LOOPBACK = 'true'
    $env:ENABLE_LIVE_SCAN = 'false'; $env:ALLOWED_DOMAINS = 'localhost'
    Assert-PortFree 8090
    Start-Tracked $Py @('-m', 'scripts.demo_env', 'site') $Root 'demo_site' | Out-Null
    Start-Servers
    Wait-Http 'http://127.0.0.1:8090/'
    $code = Invoke-Py @('tests\demo_rehearsal.py')
  } catch { Write-Host $_.Exception.Message -ForegroundColor Red }
  finally { Pop-Location; Stop-Started }
  $results['demo'] = if ($code -eq 0) { 'PASS' } else { 'FAIL' }
}

try {
  if ($Build) {
    Write-Host '=== npm run build ===' -ForegroundColor Cyan
    Push-Location (Join-Path $Root 'frontend'); & npm.cmd run build; $b = $LASTEXITCODE; Pop-Location
    if ($b -ne 0) { throw 'frontend build failed' }
  }
  if ($Suite -in 'phase7', 'all') { Run-ScriptSuite 'phase7' 'tests\e2e_phase7_browser.py' $false }
  if ($Suite -in 'phase6b', 'all') { Run-ScriptSuite 'phase6b' 'tests\e2e_phase6b_browser.py' $true }
  if ($Suite -in 'batch', 'all') { Run-ScriptSuite 'batch' 'tests\e2e_realworld_batch_ui.py' $false }
  if ($Suite -in 'demo', 'all') { Run-Demo }
} finally {
  Stop-Started
  Write-Host "`nResults (evidence and logs in $OutDir):" -ForegroundColor Cyan
  $results.GetEnumerator() | ForEach-Object { Write-Host ("  {0,-8} {1}" -f $_.Key, $_.Value) }
}
if ($results.Values -contains 'FAIL') { exit 1 }
