# -*- coding: utf-8 -*-
"""SiteAuthMiddleware — вход на DevBIM Image Studio. Два режима (STUDIO_AUTH_MODE):

password (по умолчанию, локальные компании) — прежнее поведение: одна кука
  devbim_auth = sha256(соль+пароль+срок), форма /auth/login, срок лицензии.

sso (devbim.com) — обмен JWT-токена сайта на сессию студии:
  GET  /auth/sso?t=<JWT HS256>  — validate (подпись/exp/jti) -> пользователь
         в studio.sqlite -> кука devbim_session (HMAC, HttpOnly, SameSite=Lax)
  GET|POST /auth/login          — вход администратора по SITE_PASSWORD (fallback)
  GET  /auth/logout             — сброс куки
  GET  /api/v1/studio/me        — {mode,user_id,email,name,role}
  /admin*                       — админ-панель (см. _admin_panel)
  Роль читается из БД на каждом запросе (role_override/revoked мгновенны).
  Авторизованным запросам в scope инжектится заголовок x-studio-user
  (входящий — вырезается), его читают ImageRouter-прокси и роутеры ifc/pdf/threed.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from urllib.parse import parse_qs, quote

try:  # задеплоено в venv (пакет invokeai.app.api.routers)
    from invokeai.app.api.routers import studio_store
except ImportError:  # дерево проекта (тесты: siteauth/ на sys.path)
    import studio_store

COOKIE_NAME = studio_store.COOKIE_NAME          # devbim_session (sso)
LEGACY_COOKIE = "devbim_auth"                   # password-режим
LOGIN_PATH = "/auth/login"
LOGOUT_PATH = "/auth/logout"
SSO_PATH = "/auth/sso"
ME_PATH = "/api/v1/studio/me"
TOKEN_SALT = "devbim-site-auth-v1:"
LEGACY_MAX_AGE = 30 * 24 * 3600
STUDIO_USER_HDR = b"x-studio-user"


# ---------- .env / режимы ----------
def _env(key: str, default: str = "") -> str:
    return studio_store.env_or(key, default)


def _mode() -> str:
    return "sso" if _env("STUDIO_AUTH_MODE", "password").strip().lower() == "sso" else "password"


def _site_password() -> str:
    v = studio_store.env_value("SITE_PASSWORD")
    if v is None:
        v = os.environ.get("SITE_PASSWORD") or ""
    return v.strip() or "devbim"


def _valid_until() -> str | None:
    v = studio_store.env_value("SITE_VALID_UNTIL")
    if v is None:
        v = os.environ.get("SITE_VALID_UNTIL") or ""
    return v.strip() or None


def _expired() -> bool:
    v = _valid_until()
    if not v:
        return False
    from datetime import date
    try:
        y, m, d = (int(x) for x in v.split("-"))
        return date.today() > date(y, m, d)
    except ValueError:
        return False


def _jwt_secret() -> str:
    return _env("STUDIO_JWT_SECRET")


def _session_secret() -> str:
    return _env("STUDIO_SESSION_SECRET") or _jwt_secret()


def _session_ttl() -> int:
    try:
        return int(_env("STUDIO_SESSION_TTL", "43200"))
    except ValueError:
        return 43200


def _frame_ancestors() -> str:
    return _env("STUDIO_FRAME_ANCESTORS", "https://devbim.com http://localhost:* http://127.0.0.1:*")


# ---------- password-режим: прежняя кука ----------
def _legacy_token(password: str) -> str:
    return hashlib.sha256(
        (TOKEN_SALT + password + "|" + (_valid_until() or "")).encode("utf-8")
    ).hexdigest()


def _cookie_from_scope(scope) -> str:
    for key, value in scope.get("headers", []):
        if key == b"cookie":
            for part in value.decode("latin-1").split(";"):
                name, _, val = part.strip().partition("=")
                if name == COOKIE_NAME:
                    return val
    return ""


def _legacy_cookie_ok(scope) -> bool:
    for key, value in scope.get("headers", []):
        if key == b"cookie":
            for part in value.decode("latin-1").split(";"):
                name, _, val = part.strip().partition("=")
                if name == LEGACY_COOKIE:
                    return val == _legacy_token(_site_password())
    return False


# ---------- sso: сессия ----------
def _session_user(scope) -> str | None:
    uid = studio_store.session_user(_cookie_from_scope(scope), _session_secret(), _session_ttl())
    if uid and studio_store.effective_role(uid):
        return uid
    return None


def _session_cookie(user_id: str) -> str:
    v = studio_store.mint_session(user_id, _session_secret())
    return (f"{COOKIE_NAME}={v}; Max-Age={_session_ttl()}; "
            "Path=/; HttpOnly; SameSite=Lax; Secure")


# ---------- HTML-страницы ----------
def _page(title: str, body: str) -> bytes:
    return ("""<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>""" + title + """ — DevBIM Image Studio</title>
<style>
  * { margin:0; padding:0; box-sizing:border-box; }
  body { font-family:'Segoe UI',system-ui,sans-serif; background:#0B0C0E; color:#E6EAF2;
         min-height:100vh; display:flex; align-items:center; justify-content:center; }
  .card { background:#14161A; border:1px solid #23262D; border-radius:14px; padding:40px 36px;
          width:380px; max-width:calc(100vw - 32px); text-align:center;
          box-shadow:0 12px 40px rgba(0,0,0,.5); }
  .logo { font-size:26px; font-weight:700; margin-bottom:6px; }
  .logo .dev { color:#E6EAF2; } .logo .bim { color:#38BDF8; }
  .sub { color:#7C8598; font-size:13px; margin-bottom:24px; }
  p { color:#A7B0C0; font-size:14px; line-height:1.55; margin-bottom:14px; }
  a { color:#38BDF8; }
  label { display:block; font-size:13px; color:#A7B0C0; margin:6px 0; text-align:left; }
  input[type=password] { width:100%; padding:11px 13px; border-radius:8px; border:1px solid #2A2E37;
          background:#0B0C0E; color:#E6EAF2; font-size:15px; outline:none; margin-bottom:16px; }
  input[type=password]:focus { border-color:#38BDF8; }
  button { width:100%; padding:12px; border:0; border-radius:8px; background:#38BDF8;
           color:#06121C; font-size:15px; font-weight:600; cursor:pointer; }
  button:hover { background:#5CC9FA; }
  .err { background:rgba(239,68,68,.12); border:1px solid rgba(239,68,68,.4); color:#FCA5A5;
         border-radius:8px; padding:10px 12px; font-size:13px; margin-bottom:16px; }
  .admin-link { display:block; margin-top:18px; font-size:12px; color:#5A6474; }
</style></head><body><div class="card">
<div class="logo"><span class="dev">Dev</span><span class="bim">BIM</span></div>
<div class="sub">Image Studio</div>""" + body + """</div></body></html>""").encode("utf-8")


def _sso_fail_page() -> bytes:
    return _page("Вход", """
<p>Не удалось подтвердить вход.<br>Откройте Image Studio заново из кабинета
<a href="https://devbim.com" style="color:#38BDF8">devbim.com</a>.</p>
<a class="admin-link" href="/auth/login">Вход администратора</a>
<script>try{parent.postMessage('studio:expired','*')}catch(e){}</script>""")


def _sso_hello_page() -> bytes:
    return _page("Вход", """
<p>Войдите через кабинет <a href="https://devbim.com" style="color:#38BDF8">devbim.com</a>:<br>
откройте страницу «Image Studio» в личном кабинете сайта.</p>
<a class="admin-link" href="/auth/login">Вход администратора</a>""")


def _admin_login_page(error: str = "") -> bytes:
    err = f'<div class="err">{error}</div>' if error else ""
    return _page("Администратор", f"""
{err}<form method="POST" action="/auth/login">
<label for="password">Пароль администратора</label>
<input id="password" type="password" name="password" autofocus autocomplete="current-password">
<button type="submit">Войти</button></form>""")


def _expired_page() -> bytes:
    return _page("Лицензия истекла", """
<h1 style="font-size:18px;margin-bottom:10px">Срок лицензии истёк</h1>
<p>Доступ к Image Studio приостановлен.<br>Для продления свяжитесь с нами:<br>
<a href="https://devbim.com" style="color:#38BDF8">devbim.com</a></p>""")


# ---------- ASGI-хелперы ----------
async def _read_body(receive) -> bytes:
    chunks = []
    while True:
        msg = await receive()
        chunks.append(msg.get("body", b""))
        if not msg.get("more_body", False):
            break
    return b"".join(chunks)


async def _send_html(send, status: int, body: bytes) -> None:
    headers = [(b"content-type", b"text/html; charset=utf-8"), (b"cache-control", b"no-store")]
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})


async def _send_json(send, data, status: int = 200) -> None:
    body = json.dumps(data, ensure_ascii=False).encode("utf-8")
    headers = [(b"content-type", b"application/json"),
               (b"content-length", str(len(body)).encode("latin-1"))]
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})


async def _redirect(send, location: str, set_cookie: str = "", clear_cookie: str = "") -> None:
    headers = [(b"location", location.encode("utf-8")), (b"cache-control", b"no-store")]
    if set_cookie:
        headers.append((b"set-cookie", set_cookie.encode("latin-1")))
    if clear_cookie:
        headers.append((b"set-cookie", clear_cookie.encode("latin-1")))
    await send({"type": "http.response.start", "status": 303, "headers": headers})
    await send({"type": "http.response.body", "body": b""})


def _query(scope) -> dict:
    qs = scope.get("query_string", b"").decode("latin-1")
    return {k: v[-1] for k, v in parse_qs(qs).items()}


# ---------- мидлварь ----------
class SiteAuthMiddleware:
    def __init__(self, app):
        self.app = app

    # --- публичные запросы sso-режима ---
    async def _handle_sso(self, scope, receive, send) -> None:
        token = _query(scope).get("t", "")
        try:
            claims = studio_store.validate_token(token, _jwt_secret())
        except Exception:
            await _send_html(send, 401, _sso_fail_page())
            return
        studio_store.init_db()
        studio_store.upsert_user(claims["sub"], claims["email"],
                                 claims.get("name") or "", claims["role"])
        await _redirect(send, "/", set_cookie=_session_cookie(claims["sub"]))

    async def _handle_admin_login(self, scope, receive, send) -> None:
        if scope.get("method", "GET").upper() == "GET":
            await _send_html(send, 200, _admin_login_page())
            return
        body = await _read_body(receive)
        form = parse_qs(body.decode("utf-8", "replace"))
        password = (form.get("password") or [""])[0].strip()
        if _mode() == "password":
            await _redirect(send, "/", set_cookie=self._legacy_cookie(password))
            return
        if password and password == _site_password():
            await _redirect(send, "/", set_cookie=_session_cookie(studio_store.ADMIN_LOCAL))
        else:
            await _send_html(send, 401, _admin_login_page("Неверный пароль"))

    def _legacy_cookie(self, password: str) -> str:
        if not (password and password == _site_password()):
            return ""  # вызов с пустым паролем -> просто редирект (не бывает: см. проверку выше)
        return (f"{LEGACY_COOKIE}={_legacy_token(password)}; Max-Age={LEGACY_MAX_AGE}; "
                "Path=/; HttpOnly; SameSite=Lax")

    async def _handle_me(self, send, user: str) -> None:
        if user == studio_store.ADMIN_LOCAL:
            await _send_json(send, {"mode": "sso", "user_id": user,
                                    "email": "admin@local", "name": "Administrator",
                                    "role": "admin"})
            return
        u = studio_store.get_user(user) or {}
        await _send_json(send, {"mode": "sso", "user_id": user,
                                "email": u.get("email", ""), "name": u.get("name", ""),
                                "role": studio_store.effective_role(user) or "user"})

    async def _admin_panel(self, scope, receive, send, user: str, role: str) -> None:
        """Задача 7 заменяет на полную панель; здесь — заглушка-страница."""
        await _send_html(send, 200, _page("Админ", "<p>Админ-панель студии.</p>"))

    # --- хук фильтрации (заполняет задача 3) ---
    async def _apply_ownership(self, scope, receive, send, user: str, role: str) -> None:
        await self.app(scope, receive, send)

    def _inject_user_header(self, scope, user: str | None) -> None:
        headers = [(k, v) for k, v in scope.get("headers", []) if k.lower() != STUDIO_USER_HDR]
        if user:
            headers.append((STUDIO_USER_HDR, user.encode("latin-1")))
        scope["headers"] = headers

    async def _csp_wrap(self, scope, receive, send) -> None:
        csp = f"frame-ancestors 'self' {_frame_ancestors()}"

        async def wrapped(message):
            if message["type"] == "http.response.start":
                message = dict(message)
                message["headers"] = list(message.get("headers", [])) + [
                    (b"content-security-policy", csp.encode("latin-1"))]
            await send(message)

        await self.app(scope, receive, wrapped)

    # --- точка входа ---
    async def __call__(self, scope, receive, send):
        if scope["type"] == "websocket":
            ok = (not _expired()) and (
                _session_user(scope) if _mode() == "sso" else _legacy_cookie_ok(scope))
            if ok:
                await self.app(scope, receive, send)
            else:
                await receive()
                await send({"type": "websocket.close", "code": 4001})
            return

        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        method = scope.get("method", "GET").upper()

        if _expired():
            await _send_html(send, 200, _expired_page())
            return

        if path == LOGOUT_PATH:
            if _mode() == "sso":
                await _redirect(send, LOGIN_PATH,
                                clear_cookie=f"{COOKIE_NAME}=; Max-Age=0; Path=/; HttpOnly; SameSite=Lax")
            else:
                await _redirect(send, LOGIN_PATH,
                                clear_cookie=f"{LEGACY_COOKIE}=; Max-Age=0; Path=/; HttpOnly; SameSite=Lax")
            return

        if _mode() == "password":
            await self._password_flow(scope, receive, send, path, method)
            return

        # ===================== sso =====================
        if path == SSO_PATH and method == "GET":
            await self._handle_sso(scope, receive, send)
            return

        if path == LOGIN_PATH:
            await self._handle_admin_login(scope, receive, send)
            return

        user = _session_user(scope)
        role = studio_store.effective_role(user) if user else None

        if path == ME_PATH:
            if user:
                studio_store.touch_user(user)
                await self._handle_me(send, user)
            else:
                await _send_json(send, {"detail": "not authenticated"}, status=401)
            return

        if path.startswith("/admin"):
            if role == "admin":
                await self._admin_panel(scope, receive, send, user, role)
            else:
                await _send_html(send, 403, _page("Нет доступа", "<p>Раздел доступен только администратору.</p>"))
            return

        if user is None:
            if path.startswith("/api/") or path.startswith("/ws/"):
                await _send_json(send, {"detail": "not authenticated"}, status=401)
            else:
                await _redirect(send, LOGIN_PATH)
            return

        studio_store.touch_user(user)
        self._inject_user_header(scope, user)

        if not (path.startswith("/api/") or path.startswith("/ws/")):
            await self._csp_wrap(scope, receive, send)
            return
        await self._apply_ownership(scope, receive, send, user, role or "user")

    # --- password-режим: прежняя логика дословно ---
    async def _password_flow(self, scope, receive, send, path, method) -> None:
        if path == LOGIN_PATH:
            if method == "GET":
                await _send_html(send, 200, _password_login_page())
                return
            if method == "POST":
                body = await _read_body(receive)
                form = parse_qs(body.decode("utf-8", "replace"))
                password = (form.get("password") or [""])[0].strip()
                if password and password == _site_password():
                    cookie = (f"{LEGACY_COOKIE}={_legacy_token(password)}; "
                              f"Max-Age={LEGACY_MAX_AGE}; Path=/; HttpOnly; SameSite=Lax")
                    await _redirect(send, "/", set_cookie=cookie)
                else:
                    await _send_html(send, 401, _password_login_page("Неверный пароль"))
                return
            await _send_html(send, 405, _password_login_page("Метод не поддерживается"))
            return

        if _legacy_cookie_ok(scope):
            await self.app(scope, receive, send)
        else:
            await _redirect(send, LOGIN_PATH)


def _password_login_page(error: str = "") -> bytes:
    err = f'<div class="err">{error}</div>' if error else ""
    return _page("Вход", f"""
{err}<form method="POST" action="/auth/login">
<label for="password">Пароль</label>
<input id="password" type="password" name="password" autofocus autocomplete="current-password">
<button type="submit">Войти</button></form>""")


# --- совместимость со старыми тестами/вызовами password-режима ---
_token = _legacy_token
_authorized = _legacy_cookie_ok
_login_page = _password_login_page
