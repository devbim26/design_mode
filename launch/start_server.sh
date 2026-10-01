#!/usr/bin/env bash
# Запуск DevBIM Image Studio на Linux (хостинг devbim.com).
# До запуска: python3.11 -m venv venv && venv/bin/pip install invokeai==6.2.0 &&
#   применить setup-скрипты корня в порядке из README (rebrand -> ... -> site_auth).
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8
export INVOKEAI_ROOT="${INVOKEAI_ROOT:-$(pwd)/data}"
exec venv/bin/python -u -c "from invokeai.app.run_app import run_app; run_app()"
