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


SOCKETS = SP / "invokeai" / "app" / "api" / "sockets.py"


def patch_sockets(src: Path | None = None) -> None:
    """Комнаты пользователей в socket.io + изоляция queue-событий (sso).

    1) connect: по куке сессии sid вступает в room "user:<id>";
    2) queue-события эмитятся в комнату владельца (image_name/batch_id из
       studio.sqlite), а не в общий room queue_id.
    Идемпотентно: маркер devbim-studio-sso. В password-режиме studio_store
    возвращает None и поведение не меняется.
    """
    path = src or SOCKETS
    s = path.read_text(encoding="utf-8")
    if "devbim-studio-sso" in s:
        print("sockets.py уже пропатчен, пропуск")
        return
    bak = path.with_suffix(".py.studio-bak")
    if not bak.exists():
        shutil.copy2(path, bak)

    anchor_reg = "        self._sio.on(self._unsub_bulk_download, handler=self._handle_unsub_bulk_download)\n"
    insert_reg = anchor_reg + (
        "        # --- devbim-studio-sso: комната пользователя по куке сессии ---\n"
        "        self._sio.on(\"connect\", handler=self._handle_studio_connect)\n"
    )
    assert anchor_reg in s, "не найден якорь регистрации обработчиков в sockets.py"
    s = s.replace(anchor_reg, insert_reg, 1)

    old_handler = (
        "    async def _handle_queue_event(self, event: FastAPIEvent[QueueEventBase]):\n"
        "        await self._sio.emit(event=event[0], data=event[1].model_dump(mode=\"json\"), room=event[1].queue_id)\n"
    )
    new_handler = (
        "    # --- devbim-studio-sso: эмит queue-событий в комнату владельца ---\n"
        "    async def _handle_queue_event(self, event: FastAPIEvent[QueueEventBase]):\n"
        "        room = event[1].queue_id\n"
        "        try:\n"
        "            from invokeai.app.api.routers import studio_store\n"
        "            room = studio_store.socket_room_for_event(event[1].model_dump(mode=\"json\")) or room\n"
        "        except Exception:\n"
        "            pass\n"
        "        await self._sio.emit(event=event[0], data=event[1].model_dump(mode=\"json\"), room=room)\n"
        "\n"
        "    async def _handle_studio_connect(self, sid: str, environ: dict, auth: Any = None) -> None:\n"
        "        try:\n"
        "            from invokeai.app.api.routers import studio_store\n"
        "            room = studio_store.room_for_environ(environ)\n"
        "            if room:\n"
        "                await self._sio.enter_room(sid, room)\n"
        "        except Exception:\n"
        "            pass\n"
    )
    assert old_handler in s, "не найден якорь _handle_queue_event в sockets.py"
    s = s.replace(old_handler, new_handler, 1)

    path.write_text(s, encoding="utf-8")
    print("sockets.py пропатчен (бэкап:", bak.name + ")")


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
    patch_sockets()
    ensure_env_password()
    print("Готово. Перезапустите сервер (launch\\start_server.bat).")
