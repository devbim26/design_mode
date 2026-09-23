@echo off
rem Запуск DevBIM Image Studio (InvokeAI 6.2.0, CPU) из папки проекта.
rem После переноса проекта exe-заглушки venv нерабочие — запускаем напрямую.
rem PYTHONUTF8=1: конфиг invokeai.yaml содержит кириллицу в UTF-8, без этого
rem сервер на Windows падает на чтении конфига (cp1251 не декодирует).
setlocal
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
rem Скрипт лежит в launch\ — корень проекта на уровень выше.
cd /d "%~dp0.."
set "INVOKEAI_ROOT=%CD%\data"
.\venv\Scripts\python.exe -u -c "from invokeai.app.run_app import run_app; run_app()"
