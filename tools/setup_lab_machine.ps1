<#
  setup_lab_machine.ps1 — one-time firewall setup for the GigE camera.

  THE PROBLEM THIS SOLVES (it cost us days):
  The Xenics Bobcat 320 streams images over GigE Vision, which delivers
  frames as INBOUND UDP (GVSP) packets. Windows Firewall blocks inbound
  UDP per-executable. Xeneth64.exe is whitelisted by the Xeneth installer,
  so the Xeneth GUI streams fine — but our Python (a different .exe) is NOT
  whitelisted, so its frames get silently dropped. Symptom: the app says
  "Camera Online" (the control channel works) but the preview is dead /
  "No signal". It is NOT a light, exposure, calibration, or driver problem.

  This script adds the inbound UDP allow rule(s) for the interpreter(s) we
  actually run, and is safe to run repeatedly (idempotent).

  Usage (it will self-elevate to admin):
      powershell -ExecutionPolicy Bypass -File tools\setup_lab_machine.ps1
#>

# --- self-elevate to administrator (firewall changes require it) -------------
$isAdmin = ([Security.Principal.WindowsPrincipal] `
    [Security.Principal.WindowsIdentity]::GetCurrent()
    ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "Requesting administrator rights..." -ForegroundColor Yellow
    Start-Process powershell.exe -Verb RunAs -ArgumentList `
        "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
    exit
}

$repo = Split-Path -Parent $PSScriptRoot   # tools\.. = repo root
Write-Host "Repo root: $repo`n"

function Ensure-InboundUdpRule {
    param([string]$DisplayName, [string]$Program)
    if (-not (Test-Path $Program)) {
        Write-Host "  - skip (not found): $Program" -ForegroundColor DarkGray
        return
    }
    $existing = Get-NetFirewallRule -DisplayName $DisplayName -ErrorAction SilentlyContinue
    if ($existing) {
        Write-Host "  = already allowed: $DisplayName" -ForegroundColor Green
        return
    }
    New-NetFirewallRule -DisplayName $DisplayName -Direction Inbound `
        -Program $Program -Action Allow -Profile Any -Protocol UDP | Out-Null
    Write-Host "  + ALLOWED: $DisplayName" -ForegroundColor Green
    Write-Host "            -> $Program" -ForegroundColor DarkGray
}

Write-Host "Adding inbound GigE-stream firewall rules..."

# 1) The venv interpreter — used by the tkinter app (start.bat / main.py)
#    and by the Tauri dev sidecar (start-tauri.bat).
Ensure-InboundUdpRule "Holography venv python (GigE inbound)" `
    (Join-Path $repo ".venv\Scripts\python.exe")

# 2) The PyInstaller-bundled sidecar, if a release build exists in-repo.
Get-ChildItem -Path (Join-Path $repo "app\src-tauri\binaries") `
    -Filter "holography-sidecar-*.exe" -ErrorAction SilentlyContinue |
    ForEach-Object {
        Ensure-InboundUdpRule "Holography sidecar (GigE inbound)" $_.FullName
    }

Write-Host "`nDone. If the camera still shows 'No signal':" -ForegroundColor Cyan
Write-Host "  - make sure Xeneth is fully CLOSED (only one app can stream),"
Write-Host "  - confirm the camera shows a live image in Xeneth first,"
Write-Host "  - for the INSTALLED app, the sidecar lives in Program Files;"
Write-Host "    re-run this after installing, or allow that exe when Windows"
Write-Host "    prompts on first launch."
