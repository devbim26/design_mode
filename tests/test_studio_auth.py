# -*- coding: utf-8 -*-
"""Тесты SSO-мидлвари site_auth: /auth/sso, кука, роли, password-режим, /studio/me.

Запуск: venv\\Scripts\\python.exe tests\\test_studio_auth.py
"""
import asyncio
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "siteauth"))
import warnings

import jwt as pyjwt
import studio_store
import site_auth

# PyJWT предупреждает о коротком HMAC-ключе — в тесте 2 секрет "bad" намеренно короткий
warnings.filterwarnings("ignore", message="The HMAC key is")

SECRET = "s" * 40
tmp = Path(tempfile.mkdtemp(prefix="studio_auth_test_"))
saved = {k: os.environ.get(k) for k in ("INVOKEAI_ROOT", "STUDIO_AUTH_MODE", "STUDIO_JWT_SECRET",
                                        "STUDIO_SESSION_TTL", "SITE_PASSWORD", "SITE_VALID_UNTIL")}


def write_env(**kv):
    (tmp / ".env").write_text("\n".join(f"{k}={v}" for k, v in kv.items()) + "\n", encoding="utf-8")


def token(sub="u1", email="u1@x.io", role="user", ttl=60, jti=None, secret=SECRET):
    now = int(time.time())
    claims = {"sub": sub, "email": email, "name": "User One", "role": role,
              "iat": now, "exp": now + ttl, "jti": jti or f"j-{sub}-{now}-{ttl}"}
    return pyjwt.encode(claims, secret, algorithm="HS256")


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class Rec:
    def __init__(self):
        self.status = None
        self.headers = []
        self.body = b""

    async def __call__(self, msg):
        if msg["type"] == "http.response.start":
            self.status, self.headers = msg["status"], msg.get("headers", [])
        elif msg["type"] == "http.response.body":
            self.body += msg.get("body", b"")

    def h(self, name):
        return [v for k, v in self.headers if k.decode("latin-1").lower() == name]

    def cookies(self):
        out = ""
        for v in self.h("set-cookie"):
            c = v.decode("latin-1").split(";")[0]
            out += c + "; "
        return out


async def idle_receive(body=b""):
    return {"type": "http.request", "body": body, "more_body": False}


def scope(path="/", method="GET", cookie="", query=b""):
    headers = []
    if cookie:
        headers.append((b"cookie", cookie.encode("latin-1")))
    return {"type": "http", "path": path, "method": method, "headers": headers,
            "query_string": query}


def scope_ws(cookie=""):
    headers = [(b"cookie", cookie.encode())] if cookie else []
    return {"type": "websocket", "path": "/ws/socket.io/", "headers": headers}


async def inner_app(scope, receive, send):
    await send({"type": "http.response.start", "status": 200,
                "headers": [(b"content-type", b"application/json")]})
    await send({"type": "http.response.body", "body": b'{"ok":true}'})


try:
    os.environ["INVOKEAI_ROOT"] = str(tmp)
    write_env(SITE_PASSWORD="pw", SITE_VALID_UNTIL="2030-01-01",
              STUDIO_AUTH_MODE="sso", STUDIO_JWT_SECRET=SECRET, STUDIO_SESSION_TTL=3600)
    studio_store.init_db()
    mw = site_auth.SiteAuthMiddleware(inner_app)

    # 1. /auth/sso: валидный токен -> кука + редирект на /
    r = Rec()
    run(mw(scope("/auth/sso", query=b"t=" + quote(token()).encode()), idle_receive, r))
    assert r.status == 303 and r.h("location") == [b"/"], (r.status, r.h("location"))
    ck = r.cookies()
    assert "devbim_session=" in ck and "HttpOnly" in "".join(
        v.decode() for v in r.h("set-cookie")), r.h("set-cookie")
    cookie_u1 = ck.split(";")[0]

    # пользователь создан
    u = studio_store.get_user("u1")
    assert u and u["email"] == "u1@x.io" and u["role"] == "user"

    # 2. кривая подпись -> 401, без куки
    r = Rec()
    run(mw(scope("/auth/sso", query=b"t=" + quote(token(secret="bad")).encode()), idle_receive, r))
    assert r.status == 401 and not r.h("set-cookie")

    # 3. без сессии: API -> 401 JSON, страница -> 303 на /auth/login
    r = Rec()
    run(mw(scope("/api/v1/boards/"), idle_receive, r))
    assert r.status == 401
    r = Rec()
    run(mw(scope("/"), idle_receive, r))
    assert r.status == 303 and r.h("location") == [b"/auth/login"]

    # 4. сессия: запрос проходит, в scope прокинут заголовок пользователя
    seen = {}

    async def spy_app(scope, receive, send):
        seen["user"] = [v for k, v in scope.get("headers", []) if k == b"x-studio-user"]
        await inner_app(scope, receive, send)

    mw2 = site_auth.SiteAuthMiddleware(spy_app)
    r = Rec()
    run(mw2(scope("/api/v1/boards/", cookie=cookie_u1), idle_receive, r))
    assert r.status == 200 and seen["user"] == [b"u1"], seen

    # 4a. входящий x-studio-user (спуфинг) вырезается
    spoof = dict(scope("/api/v1/boards/", cookie=cookie_u1))
    spoof["headers"] = list(spoof["headers"]) + [(b"x-studio-user", b"attacker")]
    r = Rec()
    run(mw2(spoof, idle_receive, r))
    assert seen["user"] == [b"u1"], seen

    # 5. /api/v1/studio/me
    r = Rec()
    run(mw2(scope("/api/v1/studio/me", cookie=cookie_u1), idle_receive, r))
    me = json.loads(r.body)
    assert me == {"mode": "sso", "user_id": "u1", "email": "u1@x.io",
                  "name": "User One", "role": "user"}, me

    # 6. админ-вход паролем в sso-режиме
    async def login_body():
        return {"type": "http.request", "body": b"password=pw", "more_body": False}

    r = Rec()
    run(mw(scope("/auth/login", method="POST"), login_body, r))
    assert r.status == 303 and "devbim_session=" in r.cookies(), (r.status, r.h("set-cookie"))
    cookie_admin = r.cookies().split(";")[0]
    r = Rec()
    run(mw2(scope("/api/v1/studio/me", cookie=cookie_admin), idle_receive, r))
    me = json.loads(r.body)
    assert me["role"] == "admin" and me["user_id"] == studio_store.ADMIN_LOCAL, me

    # 7. отозванный пользователь не проходит
    studio_store.set_revoked("u1", True)
    r = Rec()
    run(mw2(scope("/api/v1/boards/", cookie=cookie_u1), idle_receive, r))
    assert r.status == 401
    studio_store.set_revoked("u1", False)

    # 8. CSP frame-ancestors на страничных ответах sso-режима
    r = Rec()
    run(mw2(scope("/", cookie=cookie_u1), idle_receive, r))
    csp = [v for k, v in r.headers if k.decode("latin-1").lower() == "content-security-policy"]
    assert csp and b"frame-ancestors" in csp[0], r.headers

    # 9. websocket без сессии закрывается
    ws_closed = {}

    async def ws_recv():
        return {"type": "websocket.connect"}

    async def ws_send(msg):
        ws_closed[msg["type"]] = msg

    run(mw(scope_ws(), ws_recv, ws_send))
    assert "websocket.close" in ws_closed

    # 10. password-режим не тронут: старая кука работает как раньше
    write_env(SITE_PASSWORD="pw", SITE_VALID_UNTIL="2030-01-01", STUDIO_AUTH_MODE="password")
    os.environ["STUDIO_AUTH_MODE"] = "password"
    old = site_auth._token("pw")
    r = Rec()
    run(mw(scope("/", cookie=f"devbim_auth={old}"), idle_receive, r))
    assert r.status == 200, r.status

    print("OK")
finally:
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
