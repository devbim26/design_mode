# -*- coding: utf-8 -*-
"""Код доступа вкладки «Design Code» DevBIM.

Монтируется под /api:
    GET  /api/v1/designcode/auth  — protected (задан ли код) + default_url
    POST /api/v1/designcode/auth  — проверка кода доступа (url + code)

Адрес сайта и код доступа — два НЕЗАВИСИМЫХ поля, у каждого своя цепочка
(первое непустое значение выигрывает):
    1) персональное (админ-панель /admin: users.dc_url / users.dc_code) —
       пользователь из заголовка x-studio-user (инжектит SiteAuthMiddleware
       в режимах users/sso; в password-режиме персональных настроек нет);
    2) общее (таблица settings: design_code_url / design_code_access_code,
       правится из /admin без доступа к серверу);
    3) .env проекта/компании:
         DESIGN_CODE_ACCESS_CODE — код доступа (не задан → защита отключена)
         DESIGN_CODE_URL         — префилл адреса в модальном окне

Всё перечитывается на каждом вызове (как siteauth): смена настроек в
админке действует без перезапуска сервера. Код хранится только на
сервере, в браузер не отдаётся. Сам сайт (например https://nw.dev-bim.com/)
открывается вьювером напрямую — этот роутер лишь гейтит ввод.

Разворачивается в venv скриптом setup_designcode.py.
"""
from __future__ import annotations

import hmac
import os
import time
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

design_code_router = APIRouter(prefix="/v1/designcode", tags=["designcode"])


def _store():
    """studio_store из venv (деплой) или из siteauth/ (тесты); None — нет."""
    try:
        from invokeai.app.api.routers import studio_store
        return studio_store
    except ImportError:
        try:
            import studio_store
            return studio_store
        except ImportError:
            return None


def _user_cfg(uid: "str | None") -> "dict | None":
    """Персональные настройки Design Code пользователя (или None)."""
    if not uid:
        return None
    store = _store()
    if not store:
        return None
    try:
        if store.auth_mode() not in ("users", "sso"):
            return None  # password-режим: заголовок никто не инжектит, спуфить нельзя
        u = store.get_user(uid)
    except Exception:  # noqa: BLE001 — БД недоступна: работают общие цепочки
        return None
    if not u:
        return None
    return {"url": (u.get("dc_url") or "").strip() or None,
            "code": (u.get("dc_code") or "").strip() or None}


def _setting(key: str) -> "str | None":
    store = _store()
    if not store:
        return None
    try:
        return (store.get_setting(key) or "").strip() or None
    except Exception:  # noqa: BLE001
        return None


# --- .env проекта/компании (KEY=VALUE), файл перечитывается на каждом вызове
#     (копия паттерна siteauth: INVOKEAI_ROOT → его родитель → cwd, без
#     перекрытия уже выставленных переменных окружения) ---
def _env_candidates() -> list[Path]:
    root = os.environ.get("INVOKEAI_ROOT")
    if root:
        r = Path(root)
        return [r / ".env", r.parent / ".env", Path.cwd() / ".env"]
    return [Path.cwd() / ".env"]


def _env_value(key: str) -> str | None:
    for env_path in _env_candidates():
        try:
            if not env_path.is_file():
                continue
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                if k.strip() == key:
                    return v.strip().strip('"').strip("'").strip()
        except Exception:
            continue
    return None


def _access_code(uid: "str | None" = None) -> str | None:
    cfg = _user_cfg(uid)
    if cfg and cfg["code"]:
        return cfg["code"]
    v = _setting("design_code_access_code")
    if v:
        return v
    v = _env_value("DESIGN_CODE_ACCESS_CODE")
    if v is None:
        v = os.environ.get("DESIGN_CODE_ACCESS_CODE")
    v = (v or "").strip()  # «KEY=» (пустое значение) = защита выключена
    return v or None


def _default_url(uid: "str | None" = None) -> str | None:
    cfg = _user_cfg(uid)
    if cfg and cfg["url"]:
        return cfg["url"]
    v = _setting("design_code_url")
    if v:
        return v
    v = _env_value("DESIGN_CODE_URL")
    if v is None:
        v = os.environ.get("DESIGN_CODE_URL")
    v = (v or "").strip()
    return v or None


def _check_url(url: str) -> str:
    url = (url or "").strip()
    if not url.lower().startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="Адрес сайта должен начинаться с http:// или https://")
    if len(url) > 2048:
        raise HTTPException(status_code=400, detail="Адрес сайта слишком длинный")
    return url


class AuthBody(BaseModel):
    url: str = Field(min_length=1, max_length=2048)
    code: str = Field(min_length=1, max_length=256)


@design_code_router.get("/auth")
def auth_status(x_studio_user: str | None = Header(default=None, alias="x-studio-user")) -> dict:
    uid = (x_studio_user or "").strip() or None
    return {"protected": _access_code(uid) is not None, "default_url": _default_url(uid)}


@design_code_router.post("/auth")
def auth(body: AuthBody,
         x_studio_user: str | None = Header(default=None, alias="x-studio-user")) -> dict:
    uid = (x_studio_user or "").strip() or None
    url = _check_url(body.url)
    expected = _access_code(uid)
    if expected is None:
        # код не настроен — защита отключена, модалка не запрашивает код
        return {"ok": True, "protected": False, "url": url}
    if hmac.compare_digest(body.code.encode("utf-8"), expected.encode("utf-8")):
        return {"ok": True, "protected": True, "url": url}
    time.sleep(0.3)  # замедлить перебор
    raise HTTPException(status_code=401, detail="Неверный код доступа")
