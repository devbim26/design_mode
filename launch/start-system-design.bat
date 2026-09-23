@echo off
setlocal EnableDelayedExpansion

REM ============================================================
REM  start-system-design.bat
REM  FULL STACK starter: DevBIM Image Studio backend (:9090)
REM  + Cloudflare tunnel (design.dev-bim.com).
REM
REM  Idempotent - safe to double-click any time:
REM    1. backend : if :9090 not listening -> start DETACHED via
REM       _restart_server.ps1 (WMI: survives window close,
REM       log: ir_server.log). If already up -> keep it as is.
REM    2. tunnel  : if no cloudflared with config-design.yml is
REM       running -> open window with run-tunnel-design.bat.
REM       If already running (or a duplicate) -> do nothing.
REM
REM  Companions:
REM    stop-system-design.bat  - stop backend + tunnel
REM    status-design.bat       - read-only health check
REM    start_server.bat        - force backend restart (code changes)
REM    run-tunnel-design.bat   - tunnel window only
REM
REM  ASCII ONLY: cmd.exe parses .bat in OEM codepage 866.
REM ============================================================

set "PORT=9090"
set "TUNNEL_CONFIG=config-design.yml"
set "PUBLIC_HOST=design.dev-bim.com"

REM ---------- 1) BACKEND ----------
netstat -ano | findstr LISTENING | findstr ":%PORT% " >nul 2>&1
if not errorlevel 1 goto backend_up

echo [backend] not running - starting detached via WMI ...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0_restart_server.ps1"
echo [backend] waiting for port %PORT% (up to ~90 s) ...
set /a TRIES=0

:wait_backend
ping -n 4 127.0.0.1 >nul
netstat -ano | findstr LISTENING | findstr ":%PORT% " >nul 2>&1
if not errorlevel 1 goto backend_up
set /a TRIES+=1
echo ...attempt !TRIES!/30
if !TRIES! LSS 30 goto wait_backend
echo [WARN] backend did not come up in ~90 s - check ir_server.log
goto tunnel_part

:backend_up
echo [backend] running on :%PORT%

REM ---------- 2) TUNNEL ----------
:tunnel_part
set "TUNNEL_PIDS="
for /f "usebackq" %%I in (`powershell -NoProfile -Command "(Get-CimInstance Win32_Process | Where-Object {$_.Name -eq 'cloudflared.exe' -and $_.CommandLine -like '*%TUNNEL_CONFIG%*'}).ProcessId"`) do set "TUNNEL_PIDS=!TUNNEL_PIDS! %%I"
if defined TUNNEL_PIDS (
    echo [tunnel]  already running - PID!TUNNEL_PIDS! - skip
    goto summary
)
echo [tunnel]  starting window ...
start "DevBIM tunnel design" cmd /k "%~dp0run-tunnel-design.bat"

:summary
echo.
echo ------------------------------------------------------------
echo  Site : https://%PUBLIC_HOST%/  (login: /auth/login)
echo  Stop : stop-system-design.bat    Check: status-design.bat
echo  Log  : ir_server.log (backend)
echo ------------------------------------------------------------
pause
endlocal
