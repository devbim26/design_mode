@echo off
rem Запуск DevBIM Image Studio (InvokeAI 6.2.0, CPU) из папки проекта.
rem После переноса проекта exe-заглушки venv нерабочие — запускаем напрямую.
setlocal
cd /d "%~dp0"
set "INVOKEAI_ROOT=%~dp0data"
.\venv\Scripts\python.exe -u -c "from invokeai.app.run_app import run_app; run_app()"
