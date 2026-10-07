# -*- coding: utf-8 -*-
"""Админ-панель в режиме users: создание пользователей, пароль, токен, гейты.

Запуск: venv\\Scripts\\python.exe tests\\test_userauth_admin.py
"""
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "siteauth"))
import studio_store  # noqa: E402
import site_auth  # noqa: E402

site_auth.studio_store = studio_store  # локальная копия (см. test_userauth_login)

tmp = Path(tempfile.mkdtemp(prefix="userauth_admin_"))
os.environ["INVOKEAI_ROOT"] = str(tmp)
(tmp / ".env").write_text(
    "STUDIO_AUTH_MODE=users\nSITE_PASSWORD=owner-pass\nSTUDIO_SESSION_SECRET=" + "S" * 40 + "\n",
    encoding="utf-8")
for k in ("STUDIO_AUTH_MODE", "SITE_PASSWORD", "STUDIO_SESSION_SECRET", "SITE_VALID_UNTIL"):
    os.environ.pop(k, None)


class Rec:
    def __init__(self):
        self.events = []

    async def _send(self, msg):
        self.events.append(msg)

    @property
    def status(self):
        return next(m["status"] for m in self.events if m["type"] == "http.response.start")

    def headers(self):
        return {k.decode().lower(): v.decode("latin-1")
                for m in self.events if m["type"] == "http.response.start"
                for k, v in m.get("headers", [])}

    def body(self):
        return b"".join(m.get("body", b"") for m in self.events
                        if m["type"] == "http.response.body")


async def _recv(body=b""):
    sent = False

    async def rcv():
        nonlocal sent
        if sent:
            await asyncio.sleep(3600)
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    return rcv


def scope_of(method, path, cookie="", ctype=b"application/json"):
    h = [(b"content-type", ctype)]
    if cookie:
        h.append((b"cookie", cookie.encode("latin-1")))
    return {"type": "http", "method": method, "path": path, "headers": h,
            "query_string": b"", "root_path": ""}


async def call(method, path, body=b"", cookie=""):
    rec = Rec()
    mw = site_auth.SiteAuthMiddleware(rec)
    await mw(scope_of(method, path, cookie=cookie), await _recv(body), rec._send)
    return rec


def jbody(**kw):
    return json.dumps(kw).encode()


async def main():
    studio_store.init_db()

    async def fake_ok(t):
        return True, ""

    site_auth._validate_ir_token = fake_ok

    # сессии: админ (владелец) и обычный пользователь
    r = await call("POST", "/auth/login", jbody(), cookie="")  # разогрев: POST JSON не форма
    # (ожидаем 401: пустая почта/пароль не совпали) — просто убеждаемся, что не падает
    assert r.status == 401, r.status
    from urllib.parse import quote as _q
    admin = await call("POST", "/auth/login",
                       ("email=&password=" + _q("owner-pass")).encode())
    assert admin.status == 303, admin.status
    admin_cookie = admin.headers().get("set-cookie", "").split(";")[0]

    studio_store.create_user("plain@x.ru", "", "plainpass1", "user")
    plain = await call("POST", "/auth/login",
                       ("email=plain@x.ru&password=" + _q("plainpass1")).encode())
    assert plain.status == 303, plain.status
    plain_cookie = plain.headers().get("set-cookie", "").split(";")[0]

    # --- создание пользователя админом ---
    r = await call("POST", "/admin/api/users",
                   jbody(email="new@x.ru", name="Новый", password="parol12345", role="user"),
                   cookie=admin_cookie)
    assert r.status == 200, (r.status, r.body())
    created = json.loads(r.body())
    assert created["user_id"].startswith("u_"), created

    # дубликат -> 409; кривой пароль -> 422; кривая роль -> 422
    r = await call("POST", "/admin/api/users",
                   jbody(email="new@x.ru", password="parol12345"), cookie=admin_cookie)
    assert r.status == 409, r.status
    r = await call("POST", "/admin/api/users",
                   jbody(email="short@x.ru", password="12345"), cookie=admin_cookie)
    assert r.status == 422, r.status
    r = await call("POST", "/admin/api/users",
                   jbody(email="badrole@x.ru", password="parol12345", role="boss"),
                   cookie=admin_cookie)
    assert r.status == 422, r.status

    # с токеном: сохраняется
    r = await call("POST", "/admin/api/users",
                   jbody(email="tok@x.ru", password="parol12345", token="sk-admin-set"),
                   cookie=admin_cookie)
    assert r.status == 200, r.status
    assert studio_store.get_ir_token(created["user_id"]) is None
    assert studio_store.get_ir_token(
        studio_store.find_user_by_email("tok@x.ru")["user_id"]) == "sk-admin-set"

    # --- смена пароля ---
    uid = created["user_id"]
    r = await call("POST", f"/admin/api/users/{quote(uid)}/password",
                   jbody(password="newpass123"), cookie=admin_cookie)
    assert r.status == 200, r.status
    assert studio_store.check_password(uid, "newpass123")
    r = await call("POST", f"/admin/api/users/{quote(uid)}/password",
                   jbody(password="12345"), cookie=admin_cookie)
    assert r.status == 422, r.status

    # --- токен: задать/очистить ---
    r = await call("POST", f"/admin/api/users/{quote(uid)}/token",
                   jbody(token="sk-xyz"), cookie=admin_cookie)
    assert r.status == 200, r.status
    assert studio_store.get_ir_token(uid) == "sk-xyz"
    r = await call("POST", f"/admin/api/users/{quote(uid)}/token",
                   jbody(token=""), cookie=admin_cookie)
    assert r.status == 200, r.status
    assert studio_store.get_ir_token(uid) is None

    # отклонённый токен -> 400 (подмена валидатора)
    async def fake_bad(t):
        return False, "Токен ImageRouter отклонён — проверьте ключ"
    site_auth._validate_ir_token = fake_bad
    r = await call("POST", f"/admin/api/users/{quote(uid)}/token",
                   jbody(token="sk-bad"), cookie=admin_cookie)
    assert r.status == 400, r.status
    site_auth._validate_ir_token = fake_ok

    # --- список: флаги has_password/has_token, без секретов; admin виден ---
    r = await call("GET", "/admin/api/users", cookie=admin_cookie)
    assert r.status == 200, r.status
    users = json.loads(r.body())["users"]
    by_email = {u["email"]: u for u in users}
    assert "new@x.ru" in by_email and "plain@x.ru" in by_email, by_email.keys()
    nu = by_email["new@x.ru"]
    assert nu["has_password"] is True and nu["has_token"] is False, nu
    raw = r.body().decode("utf-8")
    assert "parol12345" not in raw and "newpass123" not in raw and "sk-" not in raw, raw
    assert all(u["user_id"] != "admin-local" for u in users)

    # --- гейты: обычный пользователь не админ ---
    r = await call("GET", "/admin/api/users", cookie=plain_cookie)
    assert r.status == 403, r.status
    r = await call("POST", "/admin/api/users",
                   jbody(email="hack@x.ru", password="parol12345"), cookie=plain_cookie)
    assert r.status == 403, r.status
    r = await call("GET", "/admin", cookie=plain_cookie)
    assert r.status == 403, r.status

    # админ-страница рендерится с формой создания
    r = await call("GET", "/admin", cookie=admin_cookie)
    assert r.status == 200 and "Создать пользователя" in r.body().decode("utf-8"), r.status

    print("OK")


asyncio.run(main())
