# -*- coding: utf-8 -*-
"""Тесты многопользовательского store: пароли, ir_token, CRUD, auth_mode.

Запуск: venv\\Scripts\\python.exe tests\\test_userauth_store.py
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "siteauth"))
import studio_store  # noqa: E402

tmp = Path(tempfile.mkdtemp(prefix="userauth_store_"))
os.environ["INVOKEAI_ROOT"] = str(tmp)


def main():
    studio_store.init_db()
    assert studio_store.auth_mode() in ("password", "sso", "users")

    # create + find (регистр почты не важен)
    u = studio_store.create_user("Ivan@Mail.RU", "Иван", "parol12345", "user", ir_token="sk-test-1")
    assert u["user_id"].startswith("u_") and len(u["user_id"]) == 18, u
    assert studio_store.find_user_by_email("ivan@mail.ru")["user_id"] == u["user_id"]
    assert studio_store.find_user_by_email("no@no.no") is None

    # пароль
    assert studio_store.check_password(u["user_id"], "parol12345")
    assert not studio_store.check_password(u["user_id"], "wrong")
    assert not studio_store.check_password(u["user_id"], "")

    # токен: set/get/clear
    assert studio_store.get_ir_token(u["user_id"]) == "sk-test-1"
    studio_store.set_ir_token(u["user_id"], "sk-test-2")
    assert studio_store.get_ir_token(u["user_id"]) == "sk-test-2"
    studio_store.set_ir_token(u["user_id"], None)
    assert studio_store.get_ir_token(u["user_id"]) is None

    # дубликат email и валидация
    for bad in ({"email": "ivan@mail.ru", "password": "x" * 8},            # дубликат
                {"email": "not-an-email", "password": "x" * 8},            # кривой email
                {"email": "a@b.ru", "password": "x" * 8, "role": "boss"}):  # кривая роль
        try:
            studio_store.create_user(**bad)
            raise AssertionError(f"ожидался ValueError для {bad}")
        except ValueError:
            pass

    # пароль не задан -> check_password False; смена пароля
    u2 = studio_store.create_user("p@p.ru", "", None)
    assert not studio_store.check_password(u2["user_id"], "")
    studio_store.set_password(u2["user_id"], "newpassword1")
    assert studio_store.check_password(u2["user_id"], "newpassword1")

    # revoke по-прежнему работает
    studio_store.set_revoked(u["user_id"], True)
    assert studio_store.effective_role(u["user_id"]) is None
    studio_store.set_revoked(u["user_id"], False)
    assert studio_store.effective_role(u["user_id"]) == "user"

    # миграция на «старой» БД (колонок password_hash/ir_token нет)
    import importlib
    import sqlite3

    tmp2 = Path(tempfile.mkdtemp(prefix="userauth_store2_"))
    os.environ["INVOKEAI_ROOT"] = str(tmp2)
    importlib.reload(studio_store)
    old = tmp2 / "data" / "studio.sqlite"
    old.parent.mkdir(parents=True)
    c = sqlite3.connect(old)
    c.execute("""CREATE TABLE users(user_id TEXT PRIMARY KEY, email TEXT NOT NULL,
        name TEXT NOT NULL DEFAULT '', role TEXT NOT NULL DEFAULT 'user',
        role_override TEXT, revoked INTEGER NOT NULL DEFAULT 0,
        created_at INTEGER NOT NULL, last_seen INTEGER NOT NULL)""")
    c.execute("INSERT INTO users VALUES('legacy1','l@l.ru','','user',NULL,0,1,1)")
    c.commit()
    c.close()
    studio_store.init_db()
    legacy = studio_store.find_user_by_email("l@l.ru")
    assert legacy is not None and legacy["user_id"] == "legacy1"
    assert legacy.get("password_hash") is None and legacy.get("ir_token") is None

    print("OK")


main()
