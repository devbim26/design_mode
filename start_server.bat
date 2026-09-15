@echo off
rem ============================================================
rem  start_server.bat - start/restart DevBIM Image Studio server
rem  (localhost:9090). Kills any old instance on the port, then
rem  starts the server DETACHED via WMI - it keeps running after
rem  this window closes. All launch logic lives in
rem  _restart_server.ps1; this file is only a double-click wrapper.
rem
rem  ASCII ONLY: cmd.exe parses .bat in OEM codepage 866, Cyrillic
rem  literals break parsing. Do not add Russian text here.
rem ============================================================
setlocal
cd /d "%~dp0"

echo Restarting server on port 9090 (detached, via WMI) ...
powershell -NoProfile -ExecutionPolicy Bypass -File _restart_server.ps1

echo Waiting for port 9090 (up to ~90 s) ...
set /a tries=0

:waitloop
ping -n 3 127.0.0.1 >nul
netstat -ano | findstr ":9090" | findstr "LISTENING" >nul
if not errorlevel 1 goto up
set /a tries+=1
if %tries% lss 40 goto waitloop

echo.
echo [FAIL] Port 9090 is not listening after 90 seconds.
echo        Check the log: ir_server.log
echo.
pause
exit /b 1

:up
echo.
echo [OK] Server is up:    http://localhost:9090
echo     Log file:        ir_server.log
echo     Public tunnel:   run-tunnel-design.bat  (design.dev-bim.com)
echo.
pause
exit /b 0
