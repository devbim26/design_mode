# -*- coding: utf-8 -*-
"""Развёртывание SiteAuthMiddleware (форма входа по паролю) в venv InvokeAI.

1. Копирует siteauth/site_auth.py в venv/.../invokeai/app/api/routers/site_auth.py.
2. Патчит api_app.py (бэкап *.siteauth-bak): импорт + add_middleware ПОСЛЕ
   GZip — внешняя мидлварь, срабатывает раньше всего остального.
3. Добавляет SITE_PASSWORD в .env (по умолчанию devbim), если ключа нет.

После запуска перезапустить сервер (launch\start_server.bat).
Идемпотентно: повторный запуск ничего не ломает.
"""

import shutil
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
SRC = BASE / "siteauth" / "site_auth.py"
VENV = BASE / "venv"
SP = VENV / "Lib" / "site-packages"
DST = SP / "invokeai" / "app" / "api" / "routers" / "site_auth.py"
API_APP = SP / "invokeai" / "app" / "api_app.py"


def deploy_module() -> None:
    shutil.copy2(SRC, DST)
    print("Модуль развернут:", DST)
    src2 = BASE / "siteauth" / "studio_store.py"
    dst2 = SP / "invokeai" / "app" / "api" / "routers" / "studio_store.py"
    shutil.copy2(src2, dst2)
    print("Модуль развернут:", dst2)


def patch_api_app() -> None:
    s = API_APP.read_text(encoding="utf-8")
    if "site_auth.SiteAuthMiddleware" in s:
        print("api_app.py уже пропатчен, пропуск")
        return
    bak = API_APP.with_suffix(".py.siteauth-bak")
    if not bak.exists():
        shutil.copy2(API_APP, bak)
    orig = s
    s = s.replace("    imagerouter,\n", "    imagerouter,\n    site_auth,\n", 1)
    # добавляется ПОСЛЕДНИМ -> внешняя мидлварь (срабатывает первой)
    s = s.replace(
        "app.add_middleware(GZipMiddleware, minimum_size=1000)\n",
        "app.add_middleware(GZipMiddleware, minimum_size=1000)\n"
        "app.add_middleware(site_auth.SiteAuthMiddleware)\n",
        1,
    )
    if s == orig:
        print("ОШИБКА: не найдены точки вставки в api_app.py — патч не применён")
        sys.exit(1)
    API_APP.write_text(s, encoding="utf-8")
    print("api_app.py пропатчен (бэкап:", bak.name + ")")


def ensure_env_password() -> None:
    env = BASE / ".env"
    text = env.read_text(encoding="utf-8") if env.exists() else ""
    if text and not text.endswith("\n"):
        text += "\n"
    defaults = {
        "SITE_PASSWORD": "devbim",
        "STUDIO_AUTH_MODE": "password",
        # STUDIO_JWT_SECRET не добавляем: генерируется при включении sso (см. README)
        "STUDIO_SESSION_TTL": "43200",
        "STUDIO_FRAME_ANCESTORS": "https://devbim.com http://localhost:* http://127.0.0.1:*",
    }
    have = {ln.split("=", 1)[0].strip() for ln in text.splitlines() if "=" in ln}
    for k, v in defaults.items():
        if k not in have:
            text += f"{k}={v}\n"
            print(f"В .env добавлен {k}={v}")
    env.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    deploy_module()
    patch_api_app()
    ensure_env_password()
    print("Готово. Перезапустите сервер (launch\\start_server.bat).")
