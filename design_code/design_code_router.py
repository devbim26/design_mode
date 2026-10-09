# -*- coding: utf-8 -*-
"""Код доступа вкладки «Design Code» DevBIM.

Монтируется под /api:
    GET  /api/v1/designcode/auth  — protected (задан ли код) + default_url
    POST /api/v1/designcode/auth  — проверка кода доступа (url + code)

Адрес сайта и код доступа — два НЕЗАВИСИМЫХ поля. Один дизайн-код
принадлежит ровно одному клиенту (п.74):
    1) обычный пользователь (role=user, режимы users/sso) — ТОЛЬКО его
       персональные настройки (админ-панель /admin: users.dc_url /
       users.dc_code); персонального кода нет → вкладка закрыта
       (GET {denied:true}, POST 403);
    2) владелец/админы и password-режим (компании) — цепочка на каждое
       поле (первое непустое выигрывает): персональное → общее
       (таблица settings: design_code_url / design_code_access_code,
       правится из /admin без доступа к серверу) → .env:
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


def _is_regular_user(uid: "str | None") -> bool:
    """Обычный (не-админ) пользователь режимов users/sso — дизайн-код
    выдаётся ТОЛЬКО персонально (п.74: один дизайн-код = один клиент)."""
    if not uid:
        return False
    store = _store()
    if not store:
        return False
    try:
        if store.auth_mode() not in ("users", "sso"):
            return False
        return (store.effective_role(uid) or "user") != "admin"
    except Exception:  # noqa: BLE001 — БД недоступна: не запираем вкладку
        return False


def _resolve_dc(uid: "str | None" = None) -> "tuple[str | None, str | None, bool]":
    """(url, код, denied) для пользователя.

    Обычному пользователю users/sso — только его персональные настройки;
    персонального кода нет → denied (вкладка закрыта, POST — 403).
    Админам/анонимам/password-режиму — прежняя цепочка на каждое поле:
    персональное → общее (settings) → .env → os.environ."""
    cfg = _user_cfg(uid)
    p_url = cfg["url"] if cfg else None
    p_code = cfg["code"] if cfg else None
    if _is_regular_user(uid):
        return p_url, p_code, not p_code
    url = p_url
    if not url:
        url = _setting("design_code_url")
    if not url:
        v = _env_value("DESIGN_CODE_URL")
        if v is None:
            v = os.environ.get("DESIGN_CODE_URL")
        url = (v or "").strip() or None
    code = p_code
    if not code:
        code = _setting("design_code_access_code")
    if not code:
        v = _env_value("DESIGN_CODE_ACCESS_CODE")
        if v is None:
            v = os.environ.get("DESIGN_CODE_ACCESS_CODE")
        code = (v or "").strip() or None
    return url, code, False


def _access_code(uid: "str | None" = None) -> str | None:
    return _resolve_dc(uid)[1]


def _default_url(uid: "str | None" = None) -> str | None:
    return _resolve_dc(uid)[0]


def _denied(uid: "str | None" = None) -> bool:
    return _resolve_dc(uid)[2]


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
    url, code, denied = _resolve_dc(uid)
    if denied:
        # п.74: дизайн-код не выдан этому пользователю — вкладка закрыта
        return {"denied": True, "protected": True, "default_url": None}
    return {"protected": code is not None, "default_url": url}


@design_code_router.post("/auth")
def auth(body: AuthBody,
         x_studio_user: str | None = Header(default=None, alias="x-studio-user")) -> dict:
    uid = (x_studio_user or "").strip() or None
    _, expected, denied = _resolve_dc(uid)
    if denied:
        raise HTTPException(status_code=403,
                            detail="Доступ к дизайн-коду не выдан для этой учётной записи")
    url = _check_url(body.url)
    if expected is None:
        # код не настроен — защита отключена, модалка не запрашивает код
        return {"ok": True, "protected": False, "url": url}
    if hmac.compare_digest(body.code.encode("utf-8"), expected.encode("utf-8")):
        return {"ok": True, "protected": True, "url": url}
    time.sleep(0.3)  # замедлить перебор
    raise HTTPException(status_code=401, detail="Неверный код доступа")
