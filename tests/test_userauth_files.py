# -*- coding: utf-8 -*-
"""Пер-пользовательские подпапки IFC/PDF: upload/list/file/delete, админ, легаси.

Запуск: venv\\Scripts\\python.exe tests\\test_userauth_files.py
"""
import asyncio
import os
import re
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "siteauth"))
import studio_store  # noqa: E402

# ленивые import-ы роутеров должны попасть в ЛОКАЛЬНУЮ копию studio_store,
# а не в задеплоенную в venv (подменяем пакет до первого обращения)
sys.modules["invokeai.app.api.routers"] = SimpleNamespace(studio_store=studio_store)

sys.path.insert(0, str(ROOT / "ifc"))
sys.path.insert(0, str(ROOT / "pdf"))
import ifc_router  # noqa: E402
import pdf_router  # noqa: E402

tmp = Path(tempfile.mkdtemp(prefix="userauth_files_"))
os.environ["INVOKEAI_ROOT"] = str(tmp)
for mod in (ifc_router, pdf_router):
    mod.get_config = lambda: SimpleNamespace(root_path=str(tmp))
studio_store.init_db()

UID_A = studio_store.create_user("a@x.ru", "", "parol12345", "user")["user_id"]
UID_B = studio_store.create_user("b@x.ru", "", "parol12345", "user")["user_id"]
UID_ADM = studio_store.create_user("adm@x.ru", "", "parol12345", "admin")["user_id"]
UID_EXOTIC = studio_store.create_user("ИванПетров@Майл.ру", "", "parol12345", "user")["user_id"]


def req(uid):
    return SimpleNamespace(headers={"x-studio-user": uid} if uid else {})


class FakeUpload:
    def __init__(self, filename, data=b"x"):
        self.filename = filename
        self._data = data

    async def read(self, n=-1):
        d = self._data[:n]
        self._data = self._data[len(d):]
        return d

    async def close(self):
        pass


def expect_404(fn):
    from fastapi import HTTPException
    try:
        fn()
    except HTTPException as e:
        assert e.status_code == 404, e.status_code
        return
    raise AssertionError("ожидался 404")


def run_suite(mod, store_name, ext, kind, list_key, fn_up, fn_list, fn_get, fn_del):
    store = tmp / store_name

    def upload(uid, name):
        return asyncio.run(getattr(mod, fn_up)(req(uid), FakeUpload(name)))

    def names(uid):
        return {i["name"] for i in getattr(mod, fn_list)(req(uid))[list_key]}

    # 1) upload пользователя A -> своя подпапка (не корень), тег владения
    r = upload(UID_A, "mine" + ext)
    assert r["name"] == "mine" + ext, r
    assert (store / "a@x.ru" / ("mine" + ext)).is_file()
    assert not (store / ("mine" + ext)).exists()
    assert studio_store.owner(kind, "mine" + ext) == UID_A

    # 2) список: A видит свой, B — нет; file/delete: A ок, B — 404
    assert ("mine" + ext) in names(UID_A)
    assert ("mine" + ext) not in names(UID_B)
    assert getattr(mod, fn_get)(req(UID_A), "mine" + ext).path.name == "mine" + ext
    expect_404(lambda: getattr(mod, fn_get)(req(UID_B), "mine" + ext))
    expect_404(lambda: getattr(mod, fn_del)(req(UID_B), "mine" + ext))

    # 3) легаси в корне без тега: A не видит (404), админ видит
    (store / ("legacy" + ext)).write_bytes(b"legacy")
    assert ("legacy" + ext) not in names(UID_A)
    expect_404(lambda: getattr(mod, fn_get)(req(UID_A), "legacy" + ext))
    assert ("legacy" + ext) in names(UID_ADM)
    assert getattr(mod, fn_get)(req(UID_ADM), "legacy" + ext).path.name == "legacy" + ext

    # 4) легаси, тегированный A: A видит и открывает
    studio_store.tag(kind, "legacy" + ext, UID_A)
    assert ("legacy" + ext) in names(UID_A)
    assert getattr(mod, fn_get)(req(UID_A), "legacy" + ext).path.name == "legacy" + ext

    # 5) админ: корень + все подпапки, owner = email владельца
    upload(UID_B, "bfile" + ext)
    items = {i["name"]: i for i in getattr(mod, fn_list)(req(UID_ADM))[list_key]}
    assert items["mine" + ext]["owner"] == "a@x.ru", items["mine" + ext]
    assert items["bfile" + ext]["owner"] == "b@x.ru"
    assert items["legacy" + ext]["owner"] == "a@x.ru"

    # 6) admin-local: каталог — корень; обычный пользователь корневой файл не видит
    assert mod.user_dir("admin-local") is None
    upload("admin-local", "rootfile" + ext)
    assert (store / ("rootfile" + ext)).is_file()
    expect_404(lambda: getattr(mod, fn_get)(req(UID_B), "rootfile" + ext))
    assert getattr(mod, fn_get)(req(UID_ADM), "rootfile" + ext).path.name == "rootfile" + ext

    # 7) без пользователя (password-режим): корень, свои файлы
    assert mod.user_dir(None) is None
    upload(None, "pw" + ext)
    assert (store / ("pw" + ext)).is_file()
    n = names(None)
    assert ("pw" + ext) in n and ("mine" + ext) not in n, n

    # 8) удаление своего
    getattr(mod, fn_del)(req(UID_A), "mine" + ext)
    assert not (store / "a@x.ru" / ("mine" + ext)).exists()
    expect_404(lambda: getattr(mod, fn_get)(req(UID_A), "mine" + ext))

    # 9) слаг экзотического email: только безопасные символы, непустой
    d = mod.user_dir(UID_EXOTIC)
    assert d is not None and d.parent == store, d
    assert re.fullmatch(r"[a-z0-9@._+-]+", d.name), d.name


def main():
    run_suite(ifc_router, "ifc", ".ifc", "ifc", "models",
              "upload_model", "list_models", "get_model", "delete_model")
    run_suite(pdf_router, "pdf", ".pdf", "pdf", "docs",
              "upload_doc", "list_docs", "get_doc", "delete_doc")
    print("OK")


main()
