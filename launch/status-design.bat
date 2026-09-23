@echo off
setlocal EnableDelayedExpansion

REM ============================================================
REM  status-design.bat
REM  Read-only health check of the DevBIM design stack:
REM    backend :9090 listen + HTTP probe
REM    tunnel  : cloudflared with config-design.yml (+ dup warn)
REM    public  : https://design.dev-bim.com HTTP code
REM
REM  ASCII ONLY: cmd.exe parses .bat in OEM codepage 866.
REM ============================================================

set "PORT=9090"
set "TUNNEL_CONFIG=config-design.yml"
set "PUBLIC_HOST=design.dev-bim.com"

echo === DevBIM design stack status ===
echo.

REM ---------- backend listen ----------
netstat -ano | findstr LISTENING | findstr ":%PORT% " >nul 2>&1
if not errorlevel 1 (set "BE=UP") else set "BE=DOWN"

REM ---------- backend HTTP ----------
set "BE_HTTP=000"
for /f %%C in ('curl -s -m 5 -o nul -w "%%{http_code}" http://127.0.0.1:%PORT%/') do set "BE_HTTP=%%C"

REM ---------- tunnel ----------
set "TUNNEL_PIDS="
for /f "usebackq" %%I in (`powershell -NoProfile -Command "(Get-CimInstance Win32_Process | Where-Object {$_.Name -eq 'cloudflared.exe' -and $_.CommandLine -like '*%TUNNEL_CONFIG%*'}).ProcessId"`) do set "TUNNEL_PIDS=!TUNNEL_PIDS! %%I"

REM ---------- public ----------
set "PUB_HTTP=000"
for /f %%C in ('curl -s -m 20 -o nul -w "%%{http_code}" https://%PUBLIC_HOST%/') do set "PUB_HTTP=%%C"

REM ---------- report ----------
echo backend  :%PORT%              : %BE%  (HTTP %BE_HTTP%)
if "!BE!"=="DOWN" echo   ^> fix: run start-system-design.bat or start_server.bat
if not "!TUNNEL_PIDS!"=="" (
    echo tunnel   design             : RUNNING - PID!TUNNEL_PIDS!
) else (
    echo tunnel   design             : NOT RUNNING
    echo   ^> fix: run start-system-design.bat
)
echo public   https://%PUBLIC_HOST%/ : HTTP %PUB_HTTP%

if "!PUB_HTTP!"=="000" echo   ^> site unreachable: backend+tunnel must both be UP
if not "!PUB_HTTP!"=="000" echo   ^> any HTTP code here means the tunnel chain works

echo.
pause
endlocal
