# -*- coding: utf-8 -*-
"""
Хранение IFC-моделей для вкладки «IFC-вьювер» DevBIM.

Монтируется под /api:
    GET     /api/v1/ifc/list          — список моделей пользователя
    POST    /api/v1/ifc/upload        — загрузка модели (multipart, .ifc/.ifczip)
    GET     /api/v1/ifc/file/{name}   — скачать/открыть модель
    DELETE  /api/v1/ifc/file/{name}   — удалить модель

Файлы каждого пользователя лежат в своей подпапке
<INVOKEAI_ROOT>/ifc/<email-слаг>/ (имена в API остаются плоскими — фронт не
меняется); без пользователя (password-режим) и у admin-local — общий корень.
Админ видит корень + все подпапки (в списке поле owner — email владельца).
Легаси-файлы корня видит владелец по тегу studio.sqlite и админ.
В браузер отдаётся только содержимое файла — разбор IFC идёт на клиенте
(web-ifc WASM).

Разворачивается в venv скриптом setup_ifcviewer.py.
"""
from __future__ import annotations

import re
import time
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

from invokeai.app.services.config.config_default import get_config

ifc_router = APIRouter(prefix="/v1/ifc", tags=["ifc"])


def _studio_user(request: Request) -> str | None:
    u = request.headers.get("x-studio-user")
    return u or None


def _studio_visible(request: Request, kind: str, name: str) -> bool:
    """Виден ли файл пользователю: свой; без владельца (легаси) — только админу."""
    u = _studio_user(request)
    if u is None:                     # password-режим — изоляции нет
        return True
    from invokeai.app.api.routers import studio_store
    o = studio_store.owner(kind, name)
    return o == u or (o is None and studio_store.effective_role(u) == "admin")


# допустимые расширения и лимит размера загрузки
ALLOWED_EXT = (".ifc", ".ifczip", ".ifcxml")
MAX_UPLOAD_BYTES = 500 * 1024 * 1024  # 500 МБ

# безопасное имя файла: без путей, без управляющих символов
SAFE_NAME_RE = re.compile(r"^[^<>:\"/\\|?*\x00-\x1f]+$")

# слаг email для имени подпапки пользователя
_DIR_UNSAFE_RE = re.compile(r"[^a-z0-9@._+-]+")


def _store_dir() -> Path:
    d = Path(get_config().root_path) / "ifc"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _safe_path(name: str) -> Path:
    """Имя файла -> путь внутри хранилища; отказ для всего подозрительного."""
    name = (name or "").strip().strip('"')
    if not name or name in (".", "..") or "/" in name or "\\" in name:
        raise HTTPException(status_code=400, detail="Недопустимое имя файла")
    if not SAFE_NAME_RE.match(name):
        raise HTTPException(status_code=400, detail="Недопустимое имя файла")
    if not name.lower().endswith(ALLOWED_EXT):
        raise HTTPException(status_code=400, detail=f"Разрешены только файлы {', '.join(ALLOWED_EXT)}")
    return _store_dir() / name


def _studio_store():
    try:
        from invokeai.app.api.routers import studio_store
    except ImportError:  # дерево проекта (тесты)
        import studio_store
    return studio_store


def user_dir(user_id: "str | None") -> "Path | None":
    """Подпапка пользователя (имя = слаг email, только [a-z0-9@._+-]);
    None -> общий корень (admin-local / password-режим). Каталог создаёт upload."""
    if not user_id or user_id == "admin-local":
        return None
    try:
        u = _studio_store().get_user(user_id)
    except Exception:
        return None
    if not u or not u.get("email"):
        return None
    slug = _DIR_UNSAFE_RE.sub("_", u["email"].strip().lower())[:80].strip(".")
    return _store_dir() / (slug or user_id)


def _is_admin(user_id: "str | None") -> bool:
    if not user_id:
        return False
    try:
        return _studio_store().effective_role(user_id) == "admin"
    except Exception:
        return False


def _all_dirs() -> list[Path]:
    """Корень + подпапки пользователей (для админа)."""
    root = _store_dir()
    return [root] + sorted(p for p in root.iterdir() if p.is_dir())


def _resolve(request: Request, name: str) -> Path:
    """Путь к файлу по плоскому имени: пользователь — своя подпапка, затем
    корень (легаси по правилам видимости); админ — корень, затем подпапки
    по алфавиту. 404, если не найден или не положен."""
    _safe_path(name)  # валидация имени (сам путь результата не используется)
    u = _studio_user(request)
    if _is_admin(u):
        for d in _all_dirs():
            p = d / name
            if p.is_file():
                return p
        raise HTTPException(status_code=404, detail="Файл не найден")
    d = user_dir(u)
    if d is not None and (d / name).is_file():
        return d / name
    if _studio_visible(request, "ifc", name):
        p = _store_dir() / name
        if p.is_file():
            return p
    raise HTTPException(status_code=404, detail="Файл не найден")


@ifc_router.get("/list")
def list_models(request: Request) -> dict:
    u = _studio_user(request)
    admin = _is_admin(u)
    items: dict[str, dict] = {}
    if admin:
        emails = {x["user_id"]: x["email"] for x in _studio_store().list_users()}
        dirs = _all_dirs()
    else:
        d = user_dir(u)
        dirs = [d, _store_dir()] if d else [_store_dir()]
    for dr in dirs:
        try:
            entries = sorted(dr.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True)
        except OSError:
            continue  # подпапки ещё нет (первый вход)
        for p in entries:
            if not p.is_file() or not p.name.lower().endswith(ALLOWED_EXT):
                continue
            if not admin:
                if p.name in items:
                    continue  # своя подпапка (первая в списке) приоритетнее корня
                if dr == _store_dir() and not _studio_visible(request, "ifc", p.name):
                    continue
            st = p.stat()
            it = {"name": p.name, "size": st.st_size, "modified": int(st.st_mtime)}
            if admin:
                try:
                    it["owner"] = emails.get(_studio_store().owner("ifc", p.name))
                except Exception:
                    it["owner"] = None
            items[p.name] = it
    out = sorted(items.values(), key=lambda x: x["modified"], reverse=True)
    return {"models": out}


@ifc_router.post("/upload")
async def upload_model(request: Request, file: UploadFile = File(...)) -> dict:
    name = _safe_path(file.filename or "model.ifc").name
    target_dir = user_dir(_studio_user(request)) or _store_dir()
    if target_dir != _store_dir():
        target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / name
    size = 0
    t0 = time.time()
    try:
        with open(path, "wb") as out:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail=f"Файл больше лимита {MAX_UPLOAD_BYTES // (1024 * 1024)} МБ",
                    )
                out.write(chunk)
    except HTTPException:
        path.unlink(missing_ok=True)
        raise
    except Exception as e:  # noqa: BLE001
        path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Не удалось сохранить файл: {e}") from e
    finally:
        await file.close()
    u = _studio_user(request)
    if u:
        try:
            from invokeai.app.api.routers import studio_store
            studio_store.tag("ifc", path.name, u)
        except Exception:
            pass
    return {"name": path.name, "size": size, "seconds": round(time.time() - t0, 1)}


@ifc_router.get("/file/{name}")
def get_model(request: Request, name: str) -> FileResponse:
    path = _resolve(request, name)
    # IFC — текстовый STEP-файл; отдаём как octet-stream, чтобы браузер скачивал,
    # а вьювер читает через fetch сам
    return FileResponse(path, media_type="application/octet-stream", filename=path.name)


@ifc_router.delete("/file/{name}")
def delete_model(request: Request, name: str) -> dict:
    path = _resolve(request, name)
    path.unlink()
    return {"deleted": path.name}
