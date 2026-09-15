# -*- coding: utf-8 -*-
"""Код доступа вкладки «Design Code» DevBIM.

Монтируется под /api:
    GET  /api/v1/designcode/auth  — protected (задан ли код) + default_url
    POST /api/v1/designcode/auth  — проверка кода доступа (url + code)

Код доступа и адрес сайта по умолчанию — .env проекта/компании:
    DESIGN_CODE_ACCESS_CODE — код доступа к базе дизайн-кода (выдаётся
                              пользователю; не задан → защита отключена,
                              любой код принимается — как ADMIN_PASSWORD
                              у imagerouter)
    DESIGN_CODE_URL         — префилл адреса в модальном окне (опционально)

.env перечитывается на каждом вызове (как siteauth): смена кода действует
без перезапуска сервера. Код хранится только на сервере, в браузер не
отдаётся. Сам сайт (например https://nw.dev-bim.com/) открывается
вьювером напрямую — этот роутер лишь гейтит ввод.

Разворачивается в venv скриптом setup_designcode.py.
"""
from __future__ import annotations

import hmac
import os
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

design_code_router = APIRouter(prefix="/v1/designcode", tags=["designcode"])


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


def _access_code() -> str | None:
    v = _env_value("DESIGN_CODE_ACCESS_CODE")
    if v is None:
        v = os.environ.get("DESIGN_CODE_ACCESS_CODE")
    v = (v or "").strip()  # «KEY=» (пустое значение) = защита выключена
    return v or None


def _default_url() -> str | None:
    v = _env_value("DESIGN_CODE_URL")
    if v is None:
        v = (os.environ.get("DESIGN_CODE_URL") or "").strip()
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
def auth_status() -> dict:
    return {"protected": _access_code() is not None, "default_url": _default_url()}


@design_code_router.post("/auth")
def auth(body: AuthBody) -> dict:
    url = _check_url(body.url)
    expected = _access_code()
    if expected is None:
        # код не настроен — защита отключена, модалка не запрашивает код
        return {"ok": True, "protected": False, "url": url}
    if hmac.compare_digest(body.code.encode("utf-8"), expected.encode("utf-8")):
        return {"ok": True, "protected": True, "url": url}
    time.sleep(0.3)  # замедлить перебор
    raise HTTPException(status_code=401, detail="Неверный код доступа")
