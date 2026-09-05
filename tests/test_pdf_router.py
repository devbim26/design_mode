# -*- coding: utf-8 -*-
"""Тесты pdf_router: имена файлов, расширения, хранилище per-company.

Запуск: venv\\Scripts\\python.exe tests\\test_pdf_router.py
"""
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pdf"))

import pdf_router  # noqa: E402
from fastapi import HTTPException  # noqa: E402


def expect_reject(name):
    try:
        pdf_router._safe_path(name)
    except HTTPException as e:
        assert e.status_code == 400, (name, e.status_code)
        return
    raise AssertionError(f"ожидался отказ для {name!r}")


def main():
    tmp = Path(tempfile.mkdtemp())
    pdf_router.get_config = lambda: SimpleNamespace(root_path=str(tmp))

    # хранилище создаётся под root_path и переиспользуется
    d1 = pdf_router._store_dir()
    d2 = pdf_router._store_dir()
    assert d1 == d2 == tmp / "pdf" and d1.is_dir(), d1

    # корректные имена
    for name in ("doc.pdf", "СП 51.13330.pdf", "план этажа (2).pdf", "X.PDF"):
        p = pdf_router._safe_path(name)
        assert p.parent == d1, (name, p)
        assert p.name == name

    # отказы: пути, служебные имена, расширения, управляющие символы
    for bad in (
        "", ".", "..", "../evil.pdf", "a/b.pdf", "a\\b.pdf",
        "doc.txt", "model.ifc", "noext", "a<b.pdf", 'a"b.pdf', "a\tb.pdf",
    ):
        expect_reject(bad)

    # лимит и расширения
    assert pdf_router.ALLOWED_EXT == (".pdf",)
    assert pdf_router.MAX_UPLOAD_BYTES == 500 * 1024 * 1024

    print("OK")


if __name__ == "__main__":
    main()
