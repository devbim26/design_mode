@echo off
setlocal EnableDelayedExpansion

REM ============================================================
REM  stop-system-design.bat
REM  Stop the DevBIM design stack: backend (:9090) + the design
REM  Cloudflare tunnel. Companion to start-system-design.bat.
REM
REM  Idempotent: safe to run when nothing is up.
REM  Targets ONLY this service:
REM    - backend = the PID listening on :9090
REM    - tunnel  = cloudflared.exe whose command line contains
REM                config-design.yml (sibling tunnels survive;
REM                kills DUPLICATES too)
REM
REM  NOTE: wmic is removed in Win11 24H2 - process lookup uses
REM  PowerShell Get-CimInstance instead.
REM
REM  ASCII ONLY: cmd.exe parses .bat in OEM codepage 866.
REM ============================================================

set "PORT=9090"
set "TUNNEL_CONFIG=config-design.yml"

echo Stopping DevBIM design stack (backend :%PORT% + tunnel design)...
echo.

REM ---------- 1) BACKEND: PID listening on :9090 ----------
set "BE_PID="
for /f "tokens=5" %%P in ('netstat -ano ^| findstr LISTENING ^| findstr ":%PORT% "') do (
    if not "%%P"=="0" if not defined BE_PID set "BE_PID=%%P"
)
if defined BE_PID (
    taskkill /PID !BE_PID! /F >nul 2>&1
    echo [backend] killed PID !BE_PID! on :%PORT%
) else (
    echo [backend] not running (nothing on :%PORT%)
)

REM ---------- 2) TUNNEL: cloudflared.exe with our config ----------
set "KILLED_TUNNEL=0"
for /f "usebackq" %%I in (`powershell -NoProfile -Command "(Get-CimInstance Win32_Process | Where-Object {$_.Name -eq 'cloudflared.exe' -and $_.CommandLine -like '*%TUNNEL_CONFIG%*'}).ProcessId"`) do (
    taskkill /PID %%I /F >nul 2>&1
    echo [tunnel]  killed cloudflared PID %%I
    set "KILLED_TUNNEL=1"
)
if "!KILLED_TUNNEL!"=="0" echo [tunnel]  not running (no cloudflared with %TUNNEL_CONFIG%)

echo.
echo Stopped. https://design.dev-bim.com is unreachable
echo until you run start-system-design.bat again.
pause
endlocal
