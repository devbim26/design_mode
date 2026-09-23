# -*- coding: utf-8 -*-
"""3D Design: деплой роутера threed в venv InvokeAI 6.2.0.

  1. Копирует threed/threed_router.py -> venv/.../routers/threed.py,
     threed/threed_scenarios.py, threed/threed_build.py и
     threed/threed_verify.py -> routers/ (as-is).
  2. Патчит api_app.py: импорт + include_router threed после design_code
     (бэкап *.threed-bak).

Идемпотентен. Запуск: venv\\Scripts\\python.exe setup_threed.py
Порядок после force-reinstall: rebrand → imagerouter → ifcviewer → pdfviewer →
designcode → threed → siteauth (гейт: imagerouter-роутер обязан существовать).
"""
import shutil
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
SRC = BASE / "threed"
API_APP_REL = Path("Lib") / "site-packages" / "invokeai" / "app" / "api_app.py"
ROUTERS_REL = Path("Lib") / "site-packages" / "invokeai" / "app" / "api" / "routers"

IMPORT_ANCHOR = "    design_code,\n"
IMPORT_NEW = "    design_code,\n    threed,\n"
ROUTER_ANCHOR = 'app.include_router(design_code.design_code_router, prefix="/api")\n'
ROUTER_NEW = (ROUTER_ANCHOR + 'app.include_router(threed.threed_router, prefix="/api")\n')


def deploy_files(venv: Path) -> bool:
    routers = venv / ROUTERS_REL
    if not (routers / "imagerouter.py").exists():
        print("ОШИБКА: нет imagerouter-роутера — сначала setup_imagerouter.py")
        sys.exit(1)
    plan = [(SRC / "threed_router.py", routers / "threed.py"),
            (SRC / "threed_scenarios.py", routers / "threed_scenarios.py"),
            (SRC / "threed_build.py", routers / "threed_build.py"),
            (SRC / "threed_verify.py", routers / "threed_verify.py")]
    if all(dst.is_file() and dst.read_bytes() == src.read_bytes() for src, dst in plan):
        print("Файлы threed уже развернуты, пропуск")
        return False
    for src, dst in plan:
        shutil.copy2(src, dst)
        print("Роутер развернут:", dst.name)
    return True


def patch_api_app(api_app: Path) -> bool:
    s = api_app.read_text(encoding="utf-8")
    if "include_router(threed.threed_router" in s:
        print("api_app.py уже пропатчен, пропуск")
        return False
    if "include_router(design_code.design_code_router" not in s:
        print("ОШИБКА: api_app.py без design_code — сначала setup_designcode.py")
        sys.exit(1)
    bak = api_app.with_suffix(".py.threed-bak")
    if not bak.exists():
        shutil.copy2(api_app, bak)
    orig = s
    s = s.replace(IMPORT_ANCHOR, IMPORT_NEW, 1)
    s = s.replace(ROUTER_ANCHOR, ROUTER_NEW, 1)
    if s == orig:
        print("ОШИБКА: не найдены точки вставки в api_app.py")
        sys.exit(1)
    api_app.write_text(s, encoding="utf-8")
    print("api_app.py пропатчен (бэкап:", bak.name + ")")
    return True


def main() -> None:
    venv = BASE / "venv"
    api_app = venv / API_APP_REL
    if not api_app.exists():
        print("Не найден venv InvokeAI:", api_app)
        sys.exit(1)
    deploy_files(venv)
    patch_api_app(api_app)
    print("Готово. Перезапустите сервер (launch\\_restart_server.ps1).")


if __name__ == "__main__":
    main()
