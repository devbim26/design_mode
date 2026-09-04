@echo off
chcp 65001 >nul
rem Start DevBIM Image Studio (backend, port 9090) + Cloudflare tunnel (design.dev-bim.com)
rem Two windows: backend and tunnel. Backend is skipped if port 9090 already listens.

netstat -ano | findstr ":9090 .*LISTENING" >nul 2>&1
if errorlevel 1 (
    start "DevBIM backend 9090" cmd /c "%~dp0start_devbim.bat"
    echo Waiting for backend on port 9090...
    timeout /t 25 /nobreak >nul
) else (
    echo Backend already running on 9090.
)

start "DevBIM tunnel design" cmd /c "%~dp0run-tunnel-design.bat"
echo.
echo Site: https://design.dev-bim.com
pause
