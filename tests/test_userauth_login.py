# -*- coding: utf-8 -*-
"""Режим users: страница входа, логин по email/паролю, токен IR, сессия.

Запуск: venv\\Scripts\\python.exe tests\\test_userauth_login.py
"""
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "siteauth"))
import studio_store  # noqa: E402
import site_auth  # noqa: E402

# тесты — против ЛОКАЛЬНОЙ копии studio_store (site_auth иначе возьмёт
# задеплоенную в venv, которая меняется только после setup_site_auth.py)
site_auth.studio_store = studio_store

tmp = Path(tempfile.mkdtemp(prefix="userauth_login_"))
os.environ["INVOKEAI_ROOT"] = str(tmp)
# cwd -> tmp: иначе env_value дотянется до .env репозитория (кандидат
# cwd/.env; там с 07.10 есть STUDIO_SESSION_SECRET) и сценарий «секрета нет»
# перестанет быть герметичным
_saved_cwd = os.getcwd()
os.chdir(tmp)
ENV_TEXT = "STUDIO_AUTH_MODE=users\nSITE_PASSWORD=owner-pass\nSTUDIO_SESSION_SECRET=" + "S" * 40 + "\n"
(tmp / ".env").write_text(ENV_TEXT, encoding="utf-8")
for k in ("STUDIO_AUTH_MODE", "SITE_PASSWORD", "STUDIO_SESSION_SECRET", "SITE_VALID_UNTIL"):
    os.environ.pop(k, None)


class Rec:
    """Приёмник ASGI-сообщений: статус/заголовки/тело ответа."""

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


def scope_of(method, path, cookie="", ctype=b"application/x-www-form-urlencoded"):
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


def form(**kw):
    from urllib.parse import quote
    return "&".join(f"{k}={quote(str(v))}" for k, v in kw.items()).encode()


async def main():
    studio_store.init_db()
    studio_store.create_user("user@x.ru", "Юзер", "parol12345", "user")
    studio_store.create_user("tok@x.ru", "Ток", "parol12345", "user")
    studio_store.create_user("rev@x.ru", "Рев", "parol12345", "user")
    studio_store.set_revoked(studio_store.find_user_by_email("rev@x.ru")["user_id"], True)

    # подмена сетевой проверки токена
    saved_val = site_auth._validate_ir_token

    async def fake_ok(t):
        return True, ""

    async def fake_bad(t):
        return False, "Токен ImageRouter отклонён — проверьте ключ"

    site_auth._validate_ir_token = fake_ok

    # 1) страница входа: три поля
    r = await call("GET", "/auth/login")
    assert r.status == 200, r.status
    page = r.body().decode("utf-8")
    for label in ("Почта", "Пароль", "Токен ImageRouter"):
        assert label in page, label

    # 2) неверный пароль
    r = await call("POST", "/auth/login", form(email="user@x.ru", password="nope"))
    assert r.status == 401 and "Неверная почта или пароль" in r.body().decode("utf-8"), r.status

    # 3) верный вход (без токена) -> 303 + кука (HttpOnly, БЕЗ Secure)
    r = await call("POST", "/auth/login", form(email="USER@X.RU", password="parol12345"))
    assert r.status == 303, r.status
    sc = r.headers().get("set-cookie", "")
    assert "devbim_session=" in sc and "HttpOnly" in sc and "Secure" not in sc, sc
    cookie = sc.split(";")[0]

    # 4) сессия открывает страницу: инжект x-studio-user в scope приложения
    seen = {}

    class Probe:
        async def __call__(self, scope, receive, send):
            seen.update({k.decode().lower(): v.decode("latin-1")
                         for k, v in scope.get("headers", [])})
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})

    mw = site_auth.SiteAuthMiddleware(Probe())
    await mw(scope_of("GET", "/", cookie=cookie), await _recv(), Rec()._send)
    assert seen.get("x-studio-user", "").startswith("u_"), seen

    # /studio/me отдаёт email/роль/режим
    rec = Rec()
    mw2 = site_auth.SiteAuthMiddleware(Probe())
    await mw2(scope_of("GET", "/api/v1/studio/me", cookie=cookie), await _recv(), rec._send)
    me = json.loads(rec.body())
    assert me["mode"] == "users" and me["email"] == "user@x.ru" and me["role"] == "user", me

    # 5) без сессии: API -> 401, страница -> 303 на /auth/login
    r = await call("GET", "/api/v1/images/")
    assert r.status == 401, r.status
    r = await call("GET", "/")
    assert r.status == 303 and "/auth/login" in r.headers().get("location", ""), r.status

    # 6) заблокированный
    r = await call("POST", "/auth/login", form(email="rev@x.ru", password="parol12345"))
    assert r.status == 403 and "заблокирована" in r.body().decode("utf-8"), r.status

    # 7) токен: отклонён -> 401; принят -> сохранён в профиле
    site_auth._validate_ir_token = fake_bad
    r = await call("POST", "/auth/login",
                   form(email="tok@x.ru", password="parol12345", token="sk-bad"))
    assert r.status == 401 and "Токен" in r.body().decode("utf-8"), r.status
    site_auth._validate_ir_token = fake_ok
    r = await call("POST", "/auth/login",
                   form(email="tok@x.ru", password="parol12345", token="sk-good"))
    assert r.status == 303, r.status
    assert studio_store.get_ir_token(
        studio_store.find_user_by_email("tok@x.ru")["user_id"]) == "sk-good"

    # 8) вход владельца: пустая почта + SITE_PASSWORD -> admin-local
    r = await call("POST", "/auth/login", form(email="", password="owner-pass"))
    assert r.status == 303, r.status
    admin_cookie = r.headers().get("set-cookie", "").split(";")[0]
    rec = Rec()
    mw3 = site_auth.SiteAuthMiddleware(Probe())
    await mw3(scope_of("GET", "/api/v1/studio/me", cookie=admin_cookie), await _recv(), rec._send)
    me = json.loads(rec.body())
    assert me["role"] == "admin" and me["user_id"] == "admin-local", me

    # 9) logout чистит куку сессии
    r = await call("GET", "/auth/logout", cookie=cookie)
    assert r.status == 303, r.status
    assert "Max-Age=0" in r.headers().get("set-cookie", ""), r.headers()

    # 10) без секрета сессии вход запрещён (fail-closed, подпись не подделать)
    (tmp / ".env").write_text("STUDIO_AUTH_MODE=users\nSITE_PASSWORD=owner-pass\n",
                              encoding="utf-8")
    os.environ.pop("STUDIO_SESSION_SECRET", None)
    r = await call("POST", "/auth/login", form(email="user@x.ru", password="parol12345"))
    assert r.status == 500 and "STUDIO_SESSION_SECRET" in r.body().decode("utf-8"), r.status
    (tmp / ".env").write_text(ENV_TEXT, encoding="utf-8")

    site_auth._validate_ir_token = saved_val
    print("OK")


asyncio.run(main())
