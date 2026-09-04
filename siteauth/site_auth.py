# -*- coding: utf-8 -*-
"""SiteAuthMiddleware — форма входа по паролю для всего сайта DevBIM Image Studio.

Ставится внешней мидлварью в api_app.py (setup_site_auth.py). Пока куки
devbim_auth нет/она неверна, любой HTTP-запрос редиректится на /auth/login,
вебсокеты закрываются.

Эндпоинты мидлвари (перехватываются до основного приложения):
  GET  /auth/login   — форма входа (DevBIM-стиль: чёрный + #38BDF8)
  POST /auth/login   — проверка пароля (поле password), установка куки
  GET  /auth/logout  — сброс куки, назад на форму

Пароль: .env в корне проекта, ключ SITE_PASSWORD. По умолчанию «devbim».
Кука — sha256(соль + пароль): смена пароля в .env мгновенно инвалидирует
все выданные куки, сервер перезапускать не нужно.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from urllib.parse import parse_qs

COOKIE_NAME = "devbim_auth"
LOGIN_PATH = "/auth/login"
LOGOUT_PATH = "/auth/logout"
TOKEN_SALT = "devbim-site-auth-v1:"
COOKIE_MAX_AGE = 30 * 24 * 3600  # 30 дней


# --- .env проекта (KEY=VALUE), не переопределяя уже выставленные переменные ---
def _load_env_file() -> None:
    candidates = [Path.cwd() / ".env"]
    root = os.environ.get("INVOKEAI_ROOT")
    if root:
        r = Path(root)
        candidates += [r / ".env", r.parent / ".env"]
    for env_path in candidates:
        try:
            if not env_path.is_file():
                continue
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                k, v = k.strip(), v.strip().strip('"').strip("'")
                if k and k not in os.environ:
                    os.environ[k] = v
            break
        except Exception:
            continue


def _site_password() -> str:
    _load_env_file()
    return (os.environ.get("SITE_PASSWORD") or "").strip() or "devbim"


def _token(password: str) -> str:
    return hashlib.sha256((TOKEN_SALT + password).encode("utf-8")).hexdigest()


def _cookie_from_scope(scope) -> str:
    for key, value in scope.get("headers", []):
        if key == b"cookie":
            for part in value.decode("latin-1").split(";"):
                name, _, val = part.strip().partition("=")
                if name == COOKIE_NAME:
                    return val
    return ""


def _authorized(scope) -> bool:
    return _cookie_from_scope(scope) == _token(_site_password())


_LOGIN_HTML = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Вход — DevBIM Image Studio</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: 'Segoe UI', system-ui, sans-serif;
    background: #0B0C0E; color: #E6EAF2;
    min-height: 100vh; display: flex; align-items: center; justify-content: center;
  }}
  .card {{
    background: #14161A; border: 1px solid #23262D; border-radius: 14px;
    padding: 40px 36px; width: 360px; max-width: calc(100vw - 32px);
    box-shadow: 0 12px 40px rgba(0,0,0,.5);
  }}
  .logo {{ font-size: 26px; font-weight: 700; text-align: center; margin-bottom: 6px; }}
  .logo .dev {{ color: #E6EAF2; }}
  .logo .bim {{ color: #38BDF8; }}
  .sub {{ text-align: center; color: #7C8598; font-size: 13px; margin-bottom: 28px; }}
  label {{ display: block; font-size: 13px; color: #A7B0C0; margin-bottom: 6px; }}
  input[type=password] {{
    width: 100%; padding: 11px 13px; border-radius: 8px;
    border: 1px solid #2A2E37; background: #0B0C0E; color: #E6EAF2;
    font-size: 15px; outline: none; margin-bottom: 18px;
  }}
  input[type=password]:focus {{ border-color: #38BDF8; }}
  button {{
    width: 100%; padding: 12px; border: 0; border-radius: 8px;
    background: #38BDF8; color: #06121C; font-size: 15px; font-weight: 600;
    cursor: pointer;
  }}
  button:hover {{ background: #5CC9FA; }}
  .err {{
    background: rgba(239,68,68,.12); border: 1px solid rgba(239,68,68,.4);
    color: #FCA5A5; border-radius: 8px; padding: 10px 12px;
    font-size: 13px; margin-bottom: 18px; text-align: center;
  }}
</style>
</head>
<body>
  <form class="card" method="POST" action="/auth/login">
    <div class="logo"><span class="dev">Dev</span><span class="bim">BIM</span></div>
    <div class="sub">Image Studio — вход</div>
    {error}
    <label for="password">Пароль</label>
    <input id="password" type="password" name="password" autofocus autocomplete="current-password">
    <button type="submit">Войти</button>
  </form>
</body>
</html>"""


def _login_page(error: str = "") -> bytes:
    err = f'<div class="err">{error}</div>' if error else ""
    return _LOGIN_HTML.format(error=err).encode("utf-8")


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


async def _redirect(send, location: str, set_cookie: str = "", clear_cookie: bool = False) -> None:
    headers = [(b"location", location.encode("utf-8")), (b"cache-control", b"no-store")]
    if set_cookie:
        headers.append((b"set-cookie", set_cookie.encode("latin-1")))
    if clear_cookie:
        headers.append((b"set-cookie", (f"{COOKIE_NAME}=; Max-Age=0; Path=/; HttpOnly; SameSite=Lax").encode("latin-1")))
    await send({"type": "http.response.start", "status": 303, "headers": headers})
    await send({"type": "http.response.body", "body": b""})


def _auth_cookie() -> str:
    return (
        f"{COOKIE_NAME}={_token(_site_password())}; Max-Age={COOKIE_MAX_AGE}; "
        "Path=/; HttpOnly; SameSite=Lax"
    )


class SiteAuthMiddleware:
    """Внешняя ASGI-мидлварь: форма входа по паролю для всего сайта."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "websocket":
            if _authorized(scope):
                await self.app(scope, receive, send)
            else:
                # закрыть неавторизованный вебсокет (socket.io переподключится после логина)
                await receive()
                await send({"type": "websocket.close", "code": 4001})
            return

        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")

        if path == LOGOUT_PATH:
            await _redirect(send, LOGIN_PATH, clear_cookie=True)
            return

        if path == LOGIN_PATH:
            method = scope.get("method", "GET").upper()
            if method == "GET":
                await _send_html(send, 200, _login_page())
                return
            if method == "POST":
                body = await _read_body(receive)
                form = parse_qs(body.decode("utf-8", "replace"))
                password = (form.get("password") or [""])[0].strip()
                if password and password == _site_password():
                    await _redirect(send, "/", set_cookie=_auth_cookie())
                else:
                    await _send_html(send, 401, _login_page("Неверный пароль"))
                return
            await _send_html(send, 405, _login_page("Метод не поддерживается"))
            return

        if _authorized(scope):
            await self.app(scope, receive, send)
        else:
            await _redirect(send, LOGIN_PATH)
