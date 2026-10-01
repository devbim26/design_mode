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

import asyncio
import hashlib
import json
import os
import re
import sys
import traceback
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote

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

# --- маршруты изоляции владения (задача 3) ---
_RE_BOARDS = re.compile(r"^/api/v1/boards/?$")
_RE_BOARD_ID = re.compile(r"^/api/v1/boards/([^/]+)$")
_RE_IMAGES = re.compile(r"^/api/v1/images/?$")
_RE_IMAGE_ITEM = re.compile(r"^/api/v1/images/i/([^/]+)(?:/.*)?$")
_RE_UPLOAD = re.compile(r"^/api/v1/images/upload/?$")
_RE_IMAGES_BODY = re.compile(r"^/api/v1/images/(delete|download|star|unstar)/?$")
# очередь 6.2.0: /api/v1/queue/{id}/list -> {items:[...]}, list_all -> [...]
_RE_QUEUE_LIST = re.compile(r"^/api/v1/queue/[^/]+/list(?:_all)?$")
# destructive-эндпоинты без собственных гейтов (финальное ревью I1)
_RE_IMAGES_UNCAT = re.compile(r"^/api/v1/images/uncategorized/?$")
# batch/batch/delete и единичные POST|DELETE / (follow-up N2/N3: в 6.2.0
# у batch/delete и единичного DELETE тело БЕЗ board_id — гейт по картинкам)
_RE_BOARD_IMAGES = re.compile(r"^/api/v1/board_images(?:/(?:batch/delete|batch))?/?$")
_RE_QUEUE_ITEM = re.compile(r"^/api/v1/queue/[^/]+/i/[^/]+(?:/cancel)?/?$")
# массовые queue-операции без карты владения (follow-up N1) — админ-only;
# processor/resume|pause — через альтернативу processor + /[^/]+;
# d/{destination} — DELETE по назначению (real router 6.2.0)
_RE_QUEUE_ADMIN = re.compile(
    r"^/api/v1/queue/[^/]+/(cancel_all_except_current|delete_all_except_current"
    r"|cancel_by_batch_ids|cancel_by_destination|retry_items_by_id|clear|prune"
    r"|processor|d)(?:/[^/]+)?/?$")
_RE_WRITE_ADMIN = re.compile(r"^/api/v1/(style_presets|workflows)(?:/|$)")


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


def _replay_body(body: bytes):
    """Фабрика ASGI-receive: отдаёт прочитанное тело один раз (для повтора)."""
    sent = False

    async def rcv():
        nonlocal sent
        if sent:
            await asyncio.sleep(3600)
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    return rcv


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
        path, method = scope.get("path", ""), scope.get("method", "GET").upper()
        if path == "/admin/api/users" and method == "GET":
            users = []
            for u in studio_store.list_users():
                # админы-операторы (базовая роль admin из devbim.com и локальный
                # SITE_PASSWORD-админ) в таблице членов студии не показываются;
                # участники с override-ролью admin остаются видимыми (пометка «*»)
                if u["user_id"] == studio_store.ADMIN_LOCAL or u["role"] == "admin":
                    continue
                u = dict(u)
                u["effective_role"] = studio_store.effective_role(u["user_id"])
                u["counts"] = studio_store.owned_count(u["user_id"])
                users.append(u)
            await _send_json(send, {"users": users})
            return

        m = re.match(r"^/admin/api/users/([^/]+)/(role|revoke)$", path)
        if m and method == "POST":
            body = await _read_body(receive)
            try:
                data = json.loads(body or b"{}")
            except ValueError:
                await _send_json(send, {"detail": "invalid JSON body"}, status=422)
                return
            uid = unquote(m.group(1))
            if m.group(2) == "role":
                r = data.get("role")
                if r not in ("admin", "user", None):
                    await _send_json(send, {"detail": "role must be admin|user|null"}, status=422)
                    return
                studio_store.set_role_override(uid, r)
            else:
                studio_store.set_revoked(uid, bool(data.get("revoked")))
            await _send_json(send, {"ok": True})
            return

        await _send_html(send, 200, _ADMIN_PAGE.encode("utf-8"))

    # ---------- изоляция владения (sso, role != admin) ----------
    @staticmethod
    def _visible(uid: str, owner_or_none: str | None) -> bool:
        return owner_or_none == uid  # легаси без владельца видно только админу (он не фильтруется)

    async def _proxy_json(self, scope, receive, send, mutator) -> None:
        """Проксирует ответ приложения и правит JSON-тело через mutator(data)->data.

        Не-JSON тело (бинарный/уже сжатый ответ) проходит как есть, но с
        громким предупреждением в stderr; ошибка мутатора — fail-closed:
        502 studio filter error, нефильтрованное тело наружу не уходит.
        """
        status_code, headers, chunks = 200, [], []

        async def wrapped(message):
            if message["type"] == "http.response.start":
                nonlocal status_code, headers
                status_code, headers = message["status"], list(message.get("headers", []))
            elif message["type"] == "http.response.body":
                chunks.append(message.get("body", b""))

        await self.app(scope, receive, wrapped)
        raw = b"".join(chunks)
        try:
            data = json.loads(raw or b"{}")
        except ValueError:
            print(f"[studio] proxy_json: non-JSON body ({len(raw)}b) passed through",
                  file=sys.stderr)
            data = None
        if data is not None:
            try:
                raw = json.dumps(mutator(data), ensure_ascii=False).encode("utf-8")
            except Exception:
                print(f"[studio] proxy_json: mutator failed on "
                      f"{scope.get('method', '?')} {scope.get('path', '?')} — fail closed (502)",
                      file=sys.stderr)
                traceback.print_exc()
                body = b'{"detail": "studio filter error"}'
                hdrs = [(k, v) for k, v in headers if k.lower() != b"content-length"]
                hdrs.append((b"content-length", str(len(body)).encode("latin-1")))
                await send({"type": "http.response.start", "status": 502, "headers": hdrs})
                await send({"type": "http.response.body", "body": body})
                return
        headers = [(k, v) for k, v in headers if k.lower() != b"content-length"]
        headers.append((b"content-length", str(len(raw)).encode("latin-1")))
        await send({"type": "http.response.start", "status": status_code, "headers": headers})
        await send({"type": "http.response.body", "body": raw})

    def _filter_list(self, uid: str, data, kind: str, id_field: str):
        """Фильтрует список (или items в словаре) по владению; поправляет total."""
        if isinstance(data, list):
            return [it for it in data
                    if self._visible(uid, studio_store.owner(kind, str(it.get(id_field, ""))))]
        if isinstance(data, dict) and isinstance(data.get("items"), list):
            orig = data["items"]
            data["items"] = [it for it in orig
                             if self._visible(uid, studio_store.owner(kind, str(it.get(id_field, ""))))]
            try:
                data["total"] = max(0, int(data.get("total") or len(orig))
                                    - (len(orig) - len(data["items"])))
            except (TypeError, ValueError):
                data["total"] = len(data["items"])
        return data

    async def _apply_ownership(self, scope, receive, send, user: str, role: str) -> None:
        path, method = scope.get("path", ""), scope.get("method", "GET").upper()
        uid = user

        # --- ролевой гейт записи (style presets / workflows) ---
        if method in ("POST", "PUT", "PATCH", "DELETE") and _RE_WRITE_ADMIN.match(path) and role != "admin":
            await _send_json(send, {"detail": "Administrator only"}, status=403)
            return

        # --- массовые queue-операции без карты владения — админу (N1) ---
        if method in ("POST", "PUT", "DELETE") and _RE_QUEUE_ADMIN.match(path) and role != "admin":
            print(f"[studio] bulk queue op denied (admin only): {method} {path}",
                  file=sys.stderr)
            await _send_json(send, {"detail": "Administrator only"}, status=403)
            return

        if role == "admin":  # админ не фильтруется
            await self.app(scope, receive, send)
            return

        # --- destructive-эндпоинты без собственных гейтов (финальное ревью I1) ---
        if method == "DELETE" and _RE_IMAGES_UNCAT.match(path):
            await _send_json(send, {"detail": "Administrator only"}, status=403)
            return

        if method in ("POST", "DELETE") and _RE_BOARD_IMAGES.match(path):
            body = await _read_body(receive)
            try:
                data = json.loads(body or b"{}") or {}
            except ValueError:
                data = {}
            names = [str(n) for n in (data.get("image_names") or [])]
            if data.get("image_name"):
                names.append(str(data["image_name"]))
            # у batch/delete и единичного DELETE board_id в теле нет (6.2.0) —
            # борд не проверяем, только владение всеми картинками (N2)
            bid = data.get("board_id")
            ok = (not bid or self._visible(uid, studio_store.owner("board", str(bid)))) \
                and all(self._visible(uid, studio_store.owner("image", n)) for n in names)
            if not ok:
                await _send_json(send, {"detail": "Forbidden: foreign board or images"}, status=403)
                return
            await self.app(scope, _replay_body(body), send)
            return

        if method in ("DELETE", "PUT") and _RE_QUEUE_ITEM.match(path):
            # id пунктов — сквозные целые без карты владения в overlay: админ
            print(f"[studio] queue item op denied (admin only): {method} {path}",
                  file=sys.stderr)
            await _send_json(send, {"detail": "Administrator only"}, status=403)
            return

        # --- тегирование созданий (мутаторы — обычные функции, не async) ---
        if method == "POST" and _RE_UPLOAD.match(path):
            def tag_upload(data):
                name = (data or {}).get("image_name")
                if name:
                    studio_store.tag("image", str(name), uid)
                return data

            await self._proxy_json(scope, receive, send, tag_upload)
            return

        if method == "POST" and _RE_BOARDS.match(path):
            def tag_board(data):
                bid = (data or {}).get("board_id")
                if bid:
                    studio_store.tag("board", str(bid), uid)
                return data

            await self._proxy_json(scope, receive, send, tag_board)
            return

        # --- фильтрация списков ---
        if method == "GET" and _RE_BOARDS.match(path):
            await self._proxy_json(scope, receive, send,
                                   lambda d: self._filter_list(uid, d, "board", "board_id"))
            return

        if method == "GET" and _RE_IMAGES.match(path):
            await self._proxy_json(scope, receive, send,
                                   lambda d: self._filter_list(uid, d, "image", "image_name"))
            return

        if method == "GET" and _RE_QUEUE_LIST.match(path):
            # list -> {items:[...]} (total поправится), list_all -> голый список;
            # _filter_list умеет обе формы
            await self._proxy_json(scope, receive, send,
                                   lambda d: self._filter_list(uid, d, "batch", "batch_id"))
            return

        # --- единичный доступ: борды ---
        m = _RE_BOARD_ID.match(path)
        if m and method in ("GET", "DELETE", "PATCH", "PUT"):
            if not self._visible(uid, studio_store.owner("board", unquote(m.group(1)))):
                await _send_json(send, {"detail": "not found"}, status=404)
                return

        # --- единичный доступ: картинки (full/thumbnail/metadata/urls/…) ---
        m = _RE_IMAGE_ITEM.match(path)
        if m and method in ("GET", "DELETE", "PATCH", "PUT"):
            if not self._visible(uid, studio_store.owner("image", unquote(m.group(1)))):
                await _send_json(send, {"detail": "not found"}, status=404)
                return

        # --- body-эндпоинты (delete/download/star/unstar): все имена должны быть своими ---
        if method == "POST" and _RE_IMAGES_BODY.match(path):
            body = await _read_body(receive)
            try:
                names = (json.loads(body or b"{}") or {}).get("image_names") or []
            except ValueError:
                names = []
            for n in names:
                if not self._visible(uid, studio_store.owner("image", str(n))):
                    await _send_json(send, {"detail": "Forbidden: foreign image in list"}, status=403)
                    return
            await self.app(scope, _replay_body(body), send)
            return

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


# --- админ-панель /admin (задача 7) ---
_ADMIN_PAGE = """<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Пользователи — DevBIM Image Studio</title>
<style>
  body { font-family:'Segoe UI',system-ui,sans-serif; background:#0B0C0E; color:#E6EAF2; margin:0; padding:32px; }
  h1 { font-size:20px; } a { color:#38BDF8; }
  table { border-collapse:collapse; width:100%; margin-top:20px; font-size:13.5px; }
  th, td { text-align:left; padding:8px 10px; border-bottom:1px solid #23262D; }
  th { color:#7C8598; font-weight:600; }
  select, button { background:#14161A; color:#E6EAF2; border:1px solid #2A2E37;
        border-radius:6px; padding:5px 8px; font-size:12.5px; cursor:pointer; }
  button:hover { border-color:#38BDF8; }
  .revoked { color:#FCA5A5; }
</style></head><body>
<h1>Пользователи студии</h1>
<p><a href="/">← к студии</a></p>
<table id="t"><thead><tr>
  <th>Email</th><th>Имя</th><th>Роль</th><th>Картинки</th><th>Борды</th>
  <th>IFC</th><th>PDF</th><th>3D</th><th>Последний вход</th><th>Действия</th>
</tr></thead><tbody></tbody></table>
<script>
function esc(s) {
  const d = document.createElement('div');
  d.textContent = s == null ? '' : String(s);
  return d.innerHTML;
}
fetch('/admin/api/users').then(r => r.json()).then(d => {
  const tb = document.querySelector('#t tbody');
  for (const u of d.users) {
    const tr = document.createElement('tr');
    if (u.revoked) tr.className = 'revoked';
    const when = new Date(u.last_seen * 1000).toLocaleString();
    tr.innerHTML = '<td>' + esc(u.email) + '</td><td>' + esc(u.name || '') + '</td>' +
      '<td>' + u.effective_role + (u.role_override ? ' *' : '') + '</td>' +
      '<td>' + u.counts.images + '</td><td>' + u.counts.boards + '</td>' +
      '<td>' + u.counts.ifc + '</td><td>' + u.counts.pdf + '</td><td>' + u.counts.threed + '</td>' +
      '<td>' + when + '</td><td></td>';
    const td = tr.lastElementChild;
    const sel = document.createElement('select');
    for (const v of ['—', 'user', 'admin']) {
      const o = document.createElement('option');
      o.value = v === '—' ? '' : v; o.textContent = v;
      if ((u.role_override || '') === o.value) o.selected = true;
      sel.appendChild(o);
    }
    sel.onchange = () => post('/admin/api/users/' + encodeURIComponent(u.user_id) + '/role',
      { role: sel.value || null });
    const btn = document.createElement('button');
    btn.textContent = u.revoked ? 'Разблокировать' : 'Заблокировать';
    btn.onclick = () => post('/admin/api/users/' + encodeURIComponent(u.user_id) + '/revoke',
      { revoked: !u.revoked }).then(() => location.reload());
    td.appendChild(sel); td.appendChild(document.createTextNode(' ')); td.appendChild(btn);
    tb.appendChild(tr);
  }
});
function post(url, body) {
  return fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body) }).then(() => location.reload());
}
</script></body></html>"""


# --- совместимость со старыми тестами/вызовами password-режима ---
_token = _legacy_token
_authorized = _legacy_cookie_ok
_login_page = _password_login_page
