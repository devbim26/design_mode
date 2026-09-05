@echo off
rem Запуск экземпляра DevBIM Image Studio для компании.
rem Использование: start_company.bat ^<код-компании^>
rem PYTHONUTF8=1: invokeai.yaml содержит кириллицу в UTF-8.
setlocal
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
if "%~1"=="" (
  echo Использование: start_company.bat ^<код-компании^>
  exit /b 1
)
if not exist "companies\%~1\.env" (
  echo Компания не найдена: %~1 ^(нет companies\%~1\.env^)
  exit /b 1
)
rem cwd = каталог компании: её .env грузится первым (порядок cwd -^> root -^> parent)
cd /d "%~dp0companies\%~1"
set "INVOKEAI_ROOT=%~dp0companies\%~1\data"
"%~dp0venv\Scripts\python.exe" -u -c "from invokeai.app.run_app import run_app; run_app()"
