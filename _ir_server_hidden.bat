@echo off
rem Запуск сервера DevBIM в фоне (без окна), лог — ir_server.log.
rem Используется для запуска через WMI, когда нужно полностью
rem отсоединиться от породившей сессии.
rem PYTHONUTF8=1: конфиг invokeai.yaml содержит кириллицу в UTF-8, без этого
rem сервер на Windows падает на чтении конфига (cp1251 не декодирует).
setlocal
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
set "INVOKEAI_ROOT=%~dp0data"
.\venv\Scripts\python.exe -u -c "from invokeai.app.run_app import run_app; run_app()" >> ir_server.log 2>&1
