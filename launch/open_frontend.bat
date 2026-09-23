@echo off
rem ============================================================
rem  open_frontend.bat - one-click open of DevBIM Image Studio UI.
rem  If the server (localhost:9090) is not running, starts it via
rem  start_server.bat first, then opens the UI in the default
rem  browser. The frontend has no separate dev server: the web UI
rem  bundle is served by the InvokeAI server itself on port 9090.
rem
rem  ASCII ONLY: cmd.exe parses .bat in OEM codepage 866, Cyrillic
rem  literals break parsing. Do not add Russian text here.
rem ============================================================
setlocal
cd /d "%~dp0"

netstat -ano | findstr ":9090" | findstr "LISTENING" >nul
if not errorlevel 1 goto open

echo Server is down - starting it first ...
echo. | cmd /c start_server.bat

rem Re-check after the start attempt.
netstat -ano | findstr ":9090" | findstr "LISTENING" >nul
if errorlevel 1 (
  echo.
  echo [FAIL] Server did not come up. Check ir_server.log
  pause
  exit /b 1
)

:open
start "" "http://localhost:9090"
exit /b 0
