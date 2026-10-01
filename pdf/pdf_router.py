# -*- coding: utf-8 -*-
"""
Хранение PDF-документов для вкладки «PDF-вьювер» DevBIM.

Монтируется под /api:
    GET     /api/v1/pdf/list          — список документов на сервере
    POST    /api/v1/pdf/upload        — загрузка документа (multipart, .pdf)
    GET     /api/v1/pdf/file/{name}   — скачать/открыть документ
    DELETE  /api/v1/pdf/file/{name}   — удалить документ

Файлы хранятся в <INVOKEAI_ROOT>/pdf (фактически data/pdf, у каждой
компании своя папка), в браузер отдаётся только содержимое файла —
разбор PDF идёт на клиенте (PDF.js).

Разворачивается в venv скриптом setup_pdfviewer.py.
"""
from __future__ import annotations

import re
import time
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

from invokeai.app.services.config.config_default import get_config

pdf_router = APIRouter(prefix="/v1/pdf", tags=["pdf"])


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
ALLOWED_EXT = (".pdf",)
MAX_UPLOAD_BYTES = 500 * 1024 * 1024  # 500 МБ

# безопасное имя файла: без путей, без управляющих символов
SAFE_NAME_RE = re.compile(r"^[^<>:\"/\\|?*\x00-\x1f]+$")


def _store_dir() -> Path:
    d = Path(get_config().root_path) / "pdf"
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


@pdf_router.get("/list")
def list_docs(request: Request) -> dict:
    items = []
    for p in sorted(_store_dir().iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
        if not p.is_file() or not p.name.lower().endswith(ALLOWED_EXT):
            continue
        if not _studio_visible(request, "pdf", p.name):
            continue
        st = p.stat()
        items.append({"name": p.name, "size": st.st_size, "modified": int(st.st_mtime)})
    return {"docs": items}


@pdf_router.post("/upload")
async def upload_doc(request: Request, file: UploadFile = File(...)) -> dict:
    name = file.filename or "document.pdf"
    path = _safe_path(name)
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
            studio_store.tag("pdf", path.name, u)
        except Exception:
            pass
    return {"name": path.name, "size": size, "seconds": round(time.time() - t0, 1)}


@pdf_router.get("/file/{name}")
def get_doc(request: Request, name: str) -> FileResponse:
    if not _studio_visible(request, "pdf", name):
        raise HTTPException(status_code=404, detail="Файл не найден")
    path = _safe_path(name)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Документ не найден")
    return FileResponse(path, media_type="application/pdf", filename=path.name)


@pdf_router.delete("/file/{name}")
def delete_doc(request: Request, name: str) -> dict:
    if not _studio_visible(request, "pdf", name):
        raise HTTPException(status_code=404, detail="Файл не найден")
    path = _safe_path(name)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Документ не найден")
    path.unlink()
    return {"deleted": path.name}
