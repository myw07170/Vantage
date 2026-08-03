<#
.SYNOPSIS
    Start, stop, restart or inspect the local Vantage stack.

.DESCRIPTION
    Runs the FastAPI backend and the Vite dev server as background processes,
    waits until both actually answer, and records their PIDs so they can be
    stopped again cleanly.

    Design notes, because a few things here are deliberate:

    * Each service is launched through a small generated .cmd wrapper in
      .run-logs\. That is what gives one merged log per service — uvicorn writes
      to stderr and Vite to stdout, and Start-Process cannot redirect both to a
      single file. The wrapper is left on disk so you can see exactly what ran.

    * Stopping kills the whole process tree (taskkill /T). `uv run` and
      `npm run` are launchers; killing them alone would orphan the actual
      python.exe and node.exe.

    * Reload is off by default. A file-watch restart mid-run would kill an
      in-flight research pipeline and its SSE connection. Pass -Reload while
      working on backend code.

.EXAMPLE
    .\scripts\vantage.ps1                      # start both, open the browser
    .\scripts\vantage.ps1 -Action stop
    .\scripts\vantage.ps1 -Action status
    .\scripts\vantage.ps1 -Reload -Show        # dev mode, visible consoles
#>
[CmdletBinding()]
param(
    [ValidateSet('start', 'stop', 'restart', 'status')]
    [string]$Action = 'start',

    [int]$BackendPort = 8010,
    [int]$FrontendPort = 5173,

    # Skip `uv sync` / `npm install`.
    [switch]$SkipInstall,
    # Do not open a browser on a successful start.
    [switch]$NoBrowser,
    # Give each service a visible console window instead of logging to a file.
    [switch]$Show,
    # Enable uvicorn --reload. Off by default: see the note above.
    [switch]$Reload
)

$ErrorActionPreference = 'Stop'

$Root = Split-Path -Parent $PSScriptRoot
$RunDir = Join-Path $Root '.run-logs'
$Services = @('backend', 'frontend')

# ── output helpers ───────────────────────────────────────────────────────────
function Write-Head($m) { Write-Host ''; Write-Host $m -ForegroundColor Cyan }
function Write-Step($m) { Write-Host "  - $m" -ForegroundColor Gray }
function Write-Good($m) { Write-Host "  + $m" -ForegroundColor Green }
function Write-Note($m) { Write-Host "  ! $m" -ForegroundColor Yellow }
function Write-Bad($m) { Write-Host "  x $m" -ForegroundColor Red }

# ── process / port helpers ───────────────────────────────────────────────────

<# PIDs listening on a port. Get-NetTCPConnection is the clean route; netstat is
   the fallback for hosts where the NetTCPIP module is unavailable. #>
function Get-PortOwner([int]$Port) {
    $found = @()
    try {
        $conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction Stop
        foreach ($c in $conns) { $found += [int]$c.OwningProcess }
    }
    catch {
        try {
            $rows = netstat.exe -ano -p TCP | Select-String 'LISTENING'
            foreach ($r in $rows) {
                $cols = ($r.ToString().Trim() -split '\s+')
                if ($cols.Length -ge 5 -and $cols[1] -match ":$Port$") { $found += [int]$cols[-1] }
            }
        }
        catch { }
    }
    return @($found | Sort-Object -Unique)
}

function Get-ProcessNameSafe([int]$ProcessId) {
    try { return (Get-Process -Id $ProcessId -ErrorAction Stop).ProcessName }
    catch { return $null }
}

<# /T because `uv run` and `npm run` are launchers - killing them alone orphans
   the real python.exe / node.exe. Output is discarded rather than merged; see
   the note on Install-Dependencies. #>
function Stop-Tree([int]$ProcessId) {
    if (-not (Get-ProcessNameSafe $ProcessId)) { return $false }
    try { & taskkill.exe /PID $ProcessId /T /F > $null 2> $null } catch { }
    Start-Sleep -Milliseconds 250
    return (-not (Get-ProcessNameSafe $ProcessId))
}

function Get-PidFile([string]$Name) { Join-Path $RunDir "$Name.pid" }

function Read-ServicePid([string]$Name) {
    $f = Get-PidFile $Name
    if (-not (Test-Path $f)) { return 0 }
    $raw = (Get-Content $f -ErrorAction SilentlyContinue | Select-Object -First 1)
    $n = 0
    if ([int]::TryParse("$raw".Trim(), [ref]$n)) { return $n }
    return 0
}

<# True once the URL answers. Returns early if the process already died, so a
   crash on startup surfaces immediately instead of after the full timeout. #>
function Wait-ForUrl {
    param([string]$Url, [int]$TimeoutSec = 60, $Proc = $null)
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        if ($Proc -and $Proc.HasExited) { return $false }
        try {
            $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
            if ($r.StatusCode -ge 200 -and $r.StatusCode -lt 500) { return $true }
        }
        catch { }
        Start-Sleep -Milliseconds 400
    }
    return $false
}

# ── launching ────────────────────────────────────────────────────────────────
function Start-VantageService {
    param(
        [string]$Name,
        [string]$WorkDir,
        [string]$CommandLine,
        [hashtable]$EnvVars = @{}
    )

    $log = Join-Path $RunDir "$Name.log"
    $cmdFile = Join-Path $RunDir "$Name.cmd"
    if (Test-Path $log) { Remove-Item $log -Force -ErrorAction SilentlyContinue }

    $lines = @('@echo off', "cd /d `"$WorkDir`"")
    foreach ($k in $EnvVars.Keys) { $lines += "set `"$k=$($EnvVars[$k])`"" }
    # `call` so control returns from npm.cmd; the redirect merges both streams.
    if ($Show) { $lines += "call $CommandLine" }
    else { $lines += "call $CommandLine > `"$log`" 2>&1" }
    Set-Content -Path $cmdFile -Value $lines -Encoding Oem

    $style = 'Hidden'
    if ($Show) { $style = 'Normal' }
    $proc = Start-Process -FilePath $cmdFile -WindowStyle $style -PassThru
    Set-Content -Path (Get-PidFile $Name) -Value $proc.Id -Encoding Ascii
    return $proc
}

# ── preflight ────────────────────────────────────────────────────────────────
function Test-Prerequisites {
    $missing = @()
    foreach ($tool in @('uv', 'npm')) {
        if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) { $missing += $tool }
    }
    if ($missing.Count -gt 0) {
        Write-Bad "Not on PATH: $($missing -join ', ')"
        if ($missing -contains 'uv') { Write-Step 'uv   -> https://docs.astral.sh/uv/getting-started/installation/' }
        if ($missing -contains 'npm') { Write-Step 'node -> https://nodejs.org/ (v20 or newer)' }
        return $false
    }
    return $true
}

function Initialize-EnvFile {
    $envFile = Join-Path $Root 'backend\.env'
    $example = Join-Path $Root 'backend\.env.example'
    if (-not (Test-Path $envFile)) {
        if (Test-Path $example) {
            Copy-Item $example $envFile
            Write-Note 'Created backend\.env from the example.'
        }
        else {
            Write-Note 'backend\.env is missing and there is no example to copy.'
            return
        }
    }
    $key = Select-String -Path $envFile -Pattern '^\s*GEMINI_API_KEY\s*=\s*(\S+)' -ErrorAction SilentlyContinue
    if (-not $key) {
        Write-Note 'GEMINI_API_KEY is not set in backend\.env - collection will work, the model will not.'
        Write-Step 'Get a key: https://aistudio.google.com/apikey'
    }
}

<# Native tools are run WITHOUT `2>&1`. Merging a native stderr into the
   PowerShell pipeline wraps every line in an ErrorRecord, which under
   $ErrorActionPreference='Stop' turns `uv sync`'s ordinary progress output into
   a fatal error. Their output goes straight to the console, which is what you
   want from a setup step anyway; success is judged on $LASTEXITCODE. #>
function Install-Dependencies {
    if ($SkipInstall) { Write-Step 'Skipping dependency install (-SkipInstall).'; return $true }

    Write-Step 'uv sync'
    Push-Location $Root
    try {
        & uv sync
        if ($LASTEXITCODE -ne 0) { Write-Bad 'uv sync failed. Run it manually to see why.'; return $false }
    }
    finally { Pop-Location }

    # npm install is slow, so only when the tree is missing or older than the manifest.
    $fe = Join-Path $Root 'frontend'
    $modules = Join-Path $fe 'node_modules'
    $needs = $true
    if (Test-Path $modules) {
        $pkg = Get-Item (Join-Path $fe 'package.json')
        $needs = ((Get-Item $modules).LastWriteTime -lt $pkg.LastWriteTime)
    }
    if ($needs) {
        Write-Step 'npm install (first run or package.json changed - this takes a minute)'
        Push-Location $fe
        try {
            & npm install --no-fund --no-audit
            if ($LASTEXITCODE -ne 0) { Write-Bad 'npm install failed.'; return $false }
        }
        finally { Pop-Location }
    }
    else { Write-Step 'npm dependencies are current.' }
    return $true
}

# ── actions ──────────────────────────────────────────────────────────────────
function Invoke-Start {
    Write-Head 'Starting Vantage'

    if (-not (Test-Prerequisites)) { return 1 }
    if (-not (Test-Path $RunDir)) { $null = New-Item -ItemType Directory -Path $RunDir }

    foreach ($p in @(@{n = 'Backend'; v = $BackendPort }, @{n = 'Frontend'; v = $FrontendPort })) {
        $owners = Get-PortOwner $p.v
        if ($owners.Count -gt 0) {
            $who = Get-ProcessNameSafe $owners[0]
            Write-Bad "$($p.n) port $($p.v) is already in use by $who (PID $($owners[0]))."
            Write-Step 'Run  .\scripts\vantage.ps1 -Action stop  first, or pass a different port.'
            return 1
        }
    }

    Initialize-EnvFile
    if (-not (Install-Dependencies)) { return 1 }

    # The dev server proxies /api server-side, so the browser stays same-origin
    # and CORS is not involved. Both are passed anyway so a non-default port
    # combination still works.
    $backendEnv = @{
        FRONTEND_ORIGIN = "http://localhost:$FrontendPort,http://127.0.0.1:$FrontendPort"
    }
    $backendCmd = "uv run uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port $BackendPort"
    if ($Reload) { $backendCmd += ' --reload' }

    Write-Step "Backend  -> http://127.0.0.1:$BackendPort"
    $beProc = Start-VantageService -Name 'backend' -WorkDir $Root -CommandLine $backendCmd -EnvVars $backendEnv

    if (-not (Wait-ForUrl -Url "http://127.0.0.1:$BackendPort/health" -TimeoutSec 90 -Proc $beProc)) {
        Write-Bad 'The backend did not come up.'
        Write-Step "Log: $(Join-Path $RunDir 'backend.log')"
        if (Test-Path (Join-Path $RunDir 'backend.log')) {
            Get-Content (Join-Path $RunDir 'backend.log') -Tail 15 | ForEach-Object { Write-Host "      $_" -ForegroundColor DarkGray }
        }
        Invoke-Stop -Quiet | Out-Null
        return 1
    }

    $llmOk = $false
    try {
        $h = Invoke-RestMethod -Uri "http://127.0.0.1:$BackendPort/health" -TimeoutSec 5
        $llmOk = [bool]$h.llm_configured
    }
    catch { }
    Write-Good "Backend ready (PID $($beProc.Id))"
    if (-not $llmOk) { Write-Note 'The backend reports no usable model key. Set GEMINI_API_KEY in backend\.env.' }

    $frontEnv = @{}
    if ($BackendPort -ne 8010) {
        # vite.config.ts hardcodes the proxy target, so a moved backend has to be
        # reached directly. That makes it cross-origin, which the FRONTEND_ORIGIN
        # above already allows.
        $frontEnv['VITE_API_BASE'] = "http://127.0.0.1:$BackendPort"
    }
    $frontCmd = "npm run dev -- --port $FrontendPort --strictPort"

    Write-Step "Frontend -> http://localhost:$FrontendPort"
    $feProc = Start-VantageService -Name 'frontend' -WorkDir (Join-Path $Root 'frontend') -CommandLine $frontCmd -EnvVars $frontEnv

    # localhost, not 127.0.0.1: Vite binds IPv6 [::1] on Windows and the literal
    # v4 address will not answer.
    if (-not (Wait-ForUrl -Url "http://localhost:$FrontendPort/" -TimeoutSec 90 -Proc $feProc)) {
        Write-Bad 'The frontend did not come up.'
        Write-Step "Log: $(Join-Path $RunDir 'frontend.log')"
        if (Test-Path (Join-Path $RunDir 'frontend.log')) {
            Get-Content (Join-Path $RunDir 'frontend.log') -Tail 15 | ForEach-Object { Write-Host "      $_" -ForegroundColor DarkGray }
        }
        Invoke-Stop -Quiet | Out-Null
        return 1
    }
    Write-Good "Frontend ready (PID $($feProc.Id))"

    Write-Head 'Vantage is running'
    Write-Host "  App      http://localhost:$FrontendPort"  -ForegroundColor White
    Write-Host "  API      http://127.0.0.1:$BackendPort/health" -ForegroundColor White
    if (-not $Show) { Write-Host "  Logs     $RunDir" -ForegroundColor DarkGray }
    Write-Host "  Stop     .\stop.bat   (or scripts\vantage.ps1 -Action stop)" -ForegroundColor DarkGray
    Write-Host ''

    if (-not $NoBrowser) { Start-Process "http://localhost:$FrontendPort" | Out-Null }
    return 0
}

function Invoke-Stop {
    param([switch]$Quiet)
    if (-not $Quiet) { Write-Head 'Stopping Vantage' }
    $killed = 0

    # Recorded PIDs first. Verify the process looks like our wrapper before
    # killing it, because Windows recycles PIDs.
    foreach ($name in $Services) {
        $servicePid = Read-ServicePid $name
        if ($servicePid -gt 0) {
            $pname = Get-ProcessNameSafe $servicePid
            if ($pname -and ($pname -match '^(cmd|uv|node|python|npm)')) {
                if (Stop-Tree $servicePid) {
                    if (-not $Quiet) { Write-Good "$name stopped (PID $servicePid)" }
                    $killed++
                }
            }
            Remove-Item (Get-PidFile $name) -Force -ErrorAction SilentlyContinue
        }
    }

    # Then anything still holding the ports - covers a service started by hand,
    # or a child that outlived its parent.
    foreach ($port in @($BackendPort, $FrontendPort)) {
        foreach ($owner in (Get-PortOwner $port)) {
            $pname = Get-ProcessNameSafe $owner
            if ($pname) {
                if (Stop-Tree $owner) {
                    if (-not $Quiet) { Write-Good "Freed port $port (was $pname, PID $owner)" }
                    $killed++
                }
                else {
                    if (-not $Quiet) { Write-Bad "Could not stop $pname (PID $owner) on port $port." }
                }
            }
        }
    }

    if (-not $Quiet) {
        if ($killed -eq 0) { Write-Step 'Nothing was running.' }
        Write-Host ''
    }
    return 0
}

function Invoke-Status {
    Write-Head 'Vantage status'
    foreach ($s in @(
            @{ name = 'backend'; label = 'Backend '; port = $BackendPort },
            @{ name = 'frontend'; label = 'Frontend'; port = $FrontendPort })) {
        $owners = Get-PortOwner $s.port
        if ($owners.Count -gt 0) {
            $pname = Get-ProcessNameSafe $owners[0]
            Write-Good "$($s.label) listening on $($s.port)  (PID $($owners[0]), $pname)"
        }
        else {
            Write-Step "$($s.label) not running (port $($s.port) free)"
        }
    }
    try {
        $h = Invoke-RestMethod -Uri "http://127.0.0.1:$BackendPort/health" -TimeoutSec 3
        $model = 'no key'
        if ($h.llm_configured) { $model = 'model key present' }
        Write-Good "Health   $($h.status), $model"
    }
    catch { Write-Step 'Health   no answer' }
    Write-Host ''
    return 0
}

# ── dispatch ─────────────────────────────────────────────────────────────────
switch ($Action) {
    'start' { exit (Invoke-Start) }
    'stop' { exit (Invoke-Stop) }
    'status' { exit (Invoke-Status) }
    'restart' {
        Invoke-Stop | Out-Null
        Start-Sleep -Seconds 1
        exit (Invoke-Start)
    }
}
