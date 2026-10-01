# Image Studio на devbim.com: SSO, роли, личные воркспейсы — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Встроить DevBIM Image Studio как страницу кабинета devbim.com: вход по JWT-токену сайта (Google-авторизация), роли admin/user, персональная изоляция галереи/бордов/аплоадов/IFC/PDF/3D через оверлей-БД.

**Architecture:** Одна инстанция студии; внешняя ASGI-мидлварь `SiteAuthMiddleware` (режим `STUDIO_AUTH_MODE=sso`) обменивает JWT сайта на подписанную куку сессии, тегирует и фильтрует API-ответы по владельцу из `data/studio.sqlite`; патч `sockets.py` разводит socket.io-события по комнатам `user:<id>`; ImageRouter-прокси и кастомные роутеры IFC/PDF/3D записывают владение. Режим `password` (компании-лицензиаты) не меняется.

**Tech Stack:** Python 3.11 (venv InvokeAI 6.2.0), PyJWT 2.15 (уже в venv), sqlite3 (stdlib), ASGI/Starlette, plain-assert тесты репозитория.

**Спека:** `docs/superpowers/specs/2026-10-01-devbim-sso-workspaces-design.md`

## Global Constraints

- Тесты: `venv\Scripts\python.exe tests\<имя>.py` (plain asserts, в конце `print("OK")`).
- Не править `venv/.../site-packages` руками — только через setup-скрипты в корне (идемпотентно, бэкапы `*-bak`).
- Не коммитить: `.env`, `companies.json`, `companies/*`, ключи API.
- `PYTHONUTF8=1` обязателен в любом bat/sh.
- После JS-правок: `node --check <файл>` / для бандлов — `node -e "import('file:///...').catch(e=>console.log(e.message))"` (допустима только runtime-ошибка, не SyntaxError).
- Перезапуск сервера из агентской сессии — только `launch\_restart_server.ps1`.
- Коммиты — в стиле репозитория (`feat(studio): ...`, `docs: ...`), на ветке `feature/studio-sso`.
- Секреты в тестах — фиктивные; БД тестов — во временных каталогах (`INVOKEAI_ROOT` → tmp).

---

### Task 1: Оверлей-хранилище `studio_store.py`

**Files:**
- Create: `siteauth/studio_store.py`
- Test: `tests/test_studio_store.py`

**Interfaces:**
- Produces (используют задачи 2–8): `env_value(key) -> str|None`; `init_db()`; `upsert_user(user_id, email, name="", role="user")`; `get_user(user_id) -> dict|None`; `touch_user(user_id)`; `set_role_override(user_id, role|None)`; `set_revoked(user_id, bool)`; `list_users() -> list[dict]`; `effective_role(user_id) -> str|None`; `tag(kind, key, user_id)`; `owner(kind, key) -> str|None`; `owned_count(user_id) -> dict`; `validate_token(token, secret) -> dict` (raise `StudioAuthError`); `mint_session(user_id, secret) -> str`; `session_user(cookie, secret, ttl) -> str|None`; `socket_room_for_event(data) -> str|None`; `room_for_environ(environ) -> str|None`; константа `ADMIN_LOCAL = "admin-local"`; `db_path() -> Path`.

- [ ] **Step 1: Создать ветку**

```bash
cd "C:\Users\Lenovo\Desktop\проект SOFT_2\Дизайн\InvokeAI\InvokeAI"
git checkout -b feature/studio-sso
```

- [ ] **Step 2: Написать проваливающийся тест**

`tests/test_studio_store.py` (полностью):

```python
# -*- coding: utf-8 -*-
"""Тесты studio_store: JWT, куки сессии, пользователи, владение, сокет-комнаты.

Запуск: venv\\Scripts\\python.exe tests\\test_studio_store.py
"""
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "siteauth"))
import studio_store

SECRET = "x" * 40

tmp = Path(tempfile.mkdtemp(prefix="studio_store_test_"))
os.environ["INVOKEAI_ROOT"] = str(tmp)
studio_store.init_db()


def _jwt(claims_delta=None, secret=SECRET, **claims):
    import jwt as pyjwt
    now = int(time.time())
    data = {"sub": "u1", "email": "u1@x.io", "role": "user",
            "iat": now, "exp": now + 60, "jti": "j1"}
    data.update(claims)
    data.update(claims_delta or {})
    return pyjwt.encode(data, secret, algorithm="HS256")


# --- JWT ---
d = studio_store.validate_token(_jwt(), SECRET)
assert d["sub"] == "u1" and d["role"] == "user"

try:
    studio_store.validate_token(_jwt(), "wrong" + SECRET); assert False
except studio_store.StudioAuthError: pass

try:  # истёкший
    studio_store.validate_token(_jwt(iat=time.time() - 120, exp=time.time() - 60), SECRET); assert False
except studio_store.StudioAuthError: pass

try:  # нет обязательного claim
    studio_store.validate_token(_jwt(email=None), SECRET); assert False
except studio_store.StudioAuthError: pass

assert studio_store.validate_token(_jwt(jti="j2"), SECRET)  # новый jti — ок
try:  # replay того же jti
    studio_store.validate_token(_jwt(jti="j2"), SECRET); assert False
except studio_store.StudioAuthError: pass

# --- кука сессии ---
c = studio_store.mint_session("u1", SECRET)
assert studio_store.session_user(c, SECRET, 60) == "u1"
assert studio_store.session_user(c, SECRET + "!", 60) is None      # неверная подпись
assert studio_store.session_user(c + "x", SECRET, 60) is None      # кривой формат
assert studio_store.session_user(c, SECRET, -1) is None            # истекла (ttl)

# --- пользователи ---
studio_store.upsert_user("u1", "u1@x.io", "User One", "user")
studio_store.upsert_user("u2", "u2@x.io", "User Two", "user")
u = studio_store.get_user("u1")
assert u["email"] == "u1@x.io" and u["role"] == "user" and not u["revoked"]
assert studio_store.effective_role("u1") == "user"
assert studio_store.effective_role(studio_store.ADMIN_LOCAL) == "admin"
studio_store.upsert_user("u1", "u1@x.io", "User One", "admin")     # роль из токена обновилась
assert studio_store.effective_role("u1") == "admin"
studio_store.set_role_override("u1", "user")                        # локальное переопределение
assert studio_store.effective_role("u1") == "user"
studio_store.set_role_override("u1", None)
assert studio_store.effective_role("u1") == "admin"
studio_store.set_revoked("u1", True)
assert studio_store.effective_role("u1") is None                    # отозван — нет доступа
studio_store.set_revoked("u1", False)
assert studio_store.effective_role("u1") == "admin"
assert {row["user_id"] for row in studio_store.list_users()} == {"u1", "u2"}

# --- владение ---
studio_store.tag("image", "a.png", "u1")
studio_store.tag("board", "b1", "u1")
studio_store.tag("batch", "bat1", "u1")
assert studio_store.owner("image", "a.png") == "u1"
assert studio_store.owner("image", "nope.png") is None
counts = studio_store.owned_count("u1")
assert counts == {"images": 1, "boards": 1, "ifc": 0, "pdf": 0, "threed": 0}

# --- сокет-комнаты ---
assert studio_store.socket_room_for_event({"result": {"image_name": "a.png"}}) == "user:u1"
assert studio_store.socket_room_for_event({"batch_id": "bat1"}) == "user:u1"
assert studio_store.socket_room_for_event({"batch_id": "other"}) is None
assert studio_store.socket_room_for_event({}) is None

os.environ["STUDIO_AUTH_MODE"] = "sso"
os.environ["STUDIO_JWT_SECRET"] = SECRET
os.environ["STUDIO_SESSION_TTL"] = "3600"
env = {"HTTP_COOKIE": f"devbim_session={studio_store.mint_session('u2', SECRET)}"}
assert studio_store.room_for_environ(env) == "user:u2"
assert studio_store.room_for_environ({"HTTP_COOKIE": ""}) is None
os.environ["STUDIO_AUTH_MODE"] = "password"
assert studio_store.room_for_environ(env) is None                   # password-режим — без комнат

print("OK")
```

- [ ] **Step 3: Запустить, убедиться в провале**

Run: `venv\Scripts\python.exe tests\test_studio_store.py`
Expected: `ModuleNotFoundError: No module named 'studio_store'`

- [ ] **Step 4: Реализовать `siteauth/studio_store.py`** (полностью):

```python
# -*- coding: utf-8 -*-
"""Оверлей-хранилище студии: пользователи SSO, владение контентом, сессии, сокет-комнаты.

Разворачивается setup_site_auth.py в venv (invokeai/app/api/routers/studio_store.py).
Файл БД: <INVOKEAI_ROOT>/data/studio.sqlite (WAL). Чтения при сбое БД -> None
(fail-closed: нет пользователя/владельца -- нет доступа), записи молча логируются
в stderr и не ломают генерацию.
"""
from __future__ import annotations

import hmac
import os
import sqlite3
import sys
import threading
import time
from pathlib import Path

ADMIN_LOCAL = "admin-local"          # синтетический user_id входа по SITE_PASSWORD
COOKIE_NAME = "devbim_session"
_LOCK = threading.Lock()
_jti_cache: dict[str, int] = {}      # jti -> exp (unix sec)
_ready = False


class StudioAuthError(Exception):
    """Невалидный токен/сессия (текст уходит в лог, не в браузер)."""


# --- .env проекта: KEY=VALUE, файл-источник, env не перекрываем ---
def _env_candidates() -> list[Path]:
    root = os.environ.get("INVOKEAI_ROOT")
    if root:
        r = Path(root)
        return [r / ".env", r.parent / ".env", Path.cwd() / ".env"]
    return [Path.cwd() / ".env"]


def env_value(key: str) -> str | None:
    """Значение ключа из .env-файлов (перечитывается на каждом вызове); None -> caller fallback на os.environ."""
    for env_path in _env_candidates():
        try:
            if not env_path.is_file():
                continue
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                if k.strip() == key:
                    return v.strip().strip('"').strip("'").strip()
        except Exception:
            continue
    return None


def env_or(key: str, default: str = "") -> str:
    return env_value(key) or os.environ.get(key, default)


# --- БД ---
def db_path() -> Path:
    root = os.environ.get("INVOKEAI_ROOT")
    return (Path(root) if root else Path.cwd()) / "data" / "studio.sqlite"


def _conn() -> sqlite3.Connection:
    p = db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(p, timeout=10)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    return c


def init_db() -> None:
    global _ready
    with _LOCK:
        with _conn() as c:
            c.execute(
                """CREATE TABLE IF NOT EXISTS users(
                     user_id TEXT PRIMARY KEY, email TEXT NOT NULL,
                     name TEXT NOT NULL DEFAULT '', role TEXT NOT NULL DEFAULT 'user',
                     role_override TEXT, revoked INTEGER NOT NULL DEFAULT 0,
                     created_at INTEGER NOT NULL, last_seen INTEGER NOT NULL)"""
            )
            c.execute(
                """CREATE TABLE IF NOT EXISTS ownership(
                     kind TEXT NOT NULL, key TEXT NOT NULL, user_id TEXT NOT NULL,
                     PRIMARY KEY(kind, key))"""
            )
        _ready = True


def _users(c: sqlite3.Connection, user_id: str) -> sqlite3.Row | None:
    return c.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()


# --- пользователи ---
def upsert_user(user_id: str, email: str, name: str = "", role: str = "user") -> None:
    now = int(time.time())
    try:
        with _LOCK, _conn() as c:
            c.execute(
                """INSERT INTO users(user_id,email,name,role,created_at,last_seen)
                   VALUES(?,?,?,?,?,?)
                   ON CONFLICT(user_id) DO UPDATE SET
                     email=excluded.email, name=excluded.name,
                     role=excluded.role, last_seen=excluded.last_seen""",
                (user_id, email, name, role, now, now),
            )
    except Exception as e:  # noqa: BLE001
        print(f"[studio_store] upsert_user failed: {e}", file=sys.stderr)


def get_user(user_id: str) -> dict | None:
    try:
        with _conn() as c:
            row = _users(c, user_id)
            return dict(row) if row else None
    except Exception as e:  # noqa: BLE001
        print(f"[studio_store] get_user failed: {e}", file=sys.stderr)
        return None


def touch_user(user_id: str) -> None:
    try:
        with _conn() as c:
            c.execute("UPDATE users SET last_seen=? WHERE user_id=?", (int(time.time()), user_id))
    except Exception:
        pass


def set_role_override(user_id: str, role: str | None) -> None:
    try:
        with _LOCK, _conn() as c:
            c.execute("UPDATE users SET role_override=? WHERE user_id=?", (role, user_id))
    except Exception as e:  # noqa: BLE001
        print(f"[studio_store] set_role_override failed: {e}", file=sys.stderr)


def set_revoked(user_id: str, flag: bool) -> None:
    try:
        with _LOCK, _conn() as c:
            c.execute("UPDATE users SET revoked=? WHERE user_id=?", (1 if flag else 0, user_id))
    except Exception as e:  # noqa: BLE001
        print(f"[studio_store] set_revoked failed: {e}", file=sys.stderr)


def list_users() -> list[dict]:
    try:
        with _conn() as c:
            return [dict(r) for r in c.execute("SELECT * FROM users ORDER BY created_at")]
    except Exception as e:  # noqa: BLE001
        print(f"[studio_store] list_users failed: {e}", file=sys.stderr)
        return []


def effective_role(user_id: str) -> str | None:
    """admin/user либо None (нет такого/отозван). Локальный вход паролем -- всегда admin."""
    if user_id == ADMIN_LOCAL:
        return "admin"
    u = get_user(user_id)
    if not u or u["revoked"]:
        return None
    return u["role_override"] or u["role"]


# --- владение ---
def tag(kind: str, key: str, user_id: str) -> None:
    if not (kind and key and user_id):
        return
    try:
        if not _ready:
            init_db()
        with _LOCK, _conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO ownership(kind,key,user_id) VALUES(?,?,?)",
                (kind, str(key), user_id),
            )
    except Exception as e:  # noqa: BLE001
        print(f"[studio_store] tag({kind}) failed: {e}", file=sys.stderr)


def owner(kind: str, key: str) -> str | None:
    try:
        with _conn() as c:
            row = c.execute("SELECT user_id FROM ownership WHERE kind=? AND key=?", (kind, str(key))).fetchone()
            return row["user_id"] if row else None
    except Exception:
        return None


def owned_count(user_id: str) -> dict:
    try:
        with _conn() as c:
            out = {"images": 0, "boards": 0, "ifc": 0, "pdf": 0, "threed": 0}
            for r in c.execute(
                "SELECT kind, COUNT(*) n FROM ownership WHERE user_id=? GROUP BY kind", (user_id,)
            ):
                k = {"image": "images", "board": "boards"}.get(r["kind"], r["kind"])
                if k in out:
                    out[k] = r["n"]
            return out
    except Exception:
        return {"images": 0, "boards": 0, "ifc": 0, "pdf": 0, "threed": 0}


# --- JWT (HS256) ---
def validate_token(token: str, secret: str, max_exp_window: int = 600) -> dict:
    import jwt  # PyJWT из venv; лениво -- модуль не нужен в password-режиме

    try:
        data = jwt.decode(token, secret, algorithms=["HS256"])
    except Exception as e:  # noqa: BLE001
        raise StudioAuthError(f"invalid token: {e}") from e
    for k in ("sub", "email", "role"):
        if not data.get(k):
            raise StudioAuthError(f"missing claim: {k}")
    if data["role"] not in ("admin", "user"):
        raise StudioAuthError(f"bad role: {data['role']}")
    if "exp" not in data:
        raise StudioAuthError("missing claim: exp")
    if data["exp"] - data.get("iat", data["exp"]) > max_exp_window:
        raise StudioAuthError("exp window too long")
    jti = data.get("jti")
    if jti and not _remember_jti(str(jti), int(data["exp"])):
        raise StudioAuthError("token replayed")
    return data


def _remember_jti(jti: str, exp: int) -> bool:
    now = int(time.time())
    with _LOCK:
        for j, e in list(_jti_cache.items()):
            if e < now:
                del _jti_cache[j]
        if jti in _jti_cache:
            return False
        _jti_cache[jti] = exp
        return True


# --- кука сессии: "<user_id>|<issued>|<hmac_sha256 hex>" ---
def mint_session(user_id: str, secret: str) -> str:
    issued = int(time.time())
    sig = hmac.new(secret.encode("utf-8"), f"{user_id}|{issued}".encode("utf-8"), "sha256").hexdigest()
    return f"{user_id}|{issued}|{sig}"


def session_user(cookie: str, secret: str, ttl: int) -> str | None:
    parts = (cookie or "").split("|")
    if len(parts) != 3:
        return None
    user_id, issued, sig = parts
    want = hmac.new(secret.encode("utf-8"), f"{user_id}|{issued}".encode("utf-8"), "sha256").hexdigest()
    if not hmac.compare_digest(sig, want):
        return None
    try:
        if int(time.time()) - int(issued) > ttl:
            return None
    except ValueError:
        return None
    return user_id


# --- сокеты ---
def socket_room_for_event(data: dict) -> str | None:
    """Комната владельца для queue-события (по image_name или batch_id), None -> прежний роуминг."""
    try:
        res = data.get("result") or {}
        name = res.get("image_name")
        if name:
            u = owner("image", name)
            if u:
                return f"user:{u}"
        b = data.get("batch_id")
        if b:
            u = owner("batch", b)
            if u:
                return f"user:{u}"
    except Exception:
        return None
    return None


def _cookie_value(header: str) -> str:
    for part in (header or "").split(";"):
        name, _, val = part.strip().partition("=")
        if name == COOKIE_NAME:
            return val
    return ""


def room_for_environ(environ: dict) -> str | None:
    """Комната пользователя для socket.io connect (по куке из environ). Password-режим -> None."""
    if env_or("STUDIO_AUTH_MODE", "password").strip().lower() != "sso":
        return None
    secret = env_or("STUDIO_SESSION_SECRET") or env_or("STUDIO_JWT_SECRET")
    if not secret:
        return None
    try:
        ttl = int(env_or("STUDIO_SESSION_TTL", "43200"))
    except ValueError:
        ttl = 43200
    uid = session_user(_cookie_value(environ.get("HTTP_COOKIE", "")), secret, ttl)
    if uid and effective_role(uid):
        return f"user:{uid}"
    return None
```

- [ ] **Step 5: Прогнать тест**

Run: `venv\Scripts\python.exe tests\test_studio_store.py`
Expected: `OK`

- [ ] **Step 6: Коммит**

```bash
git add siteauth/studio_store.py tests/test_studio_store.py
git commit -m "feat(studio): оверлей-хранилище studio_store — JWT/сессии/пользователи/владение/сокет-комнаты"
```

---

### Task 2: SSO-мидлварь: сессии, /auth/sso, /api/v1/studio/me, CSP

Мидлварь `site_auth.py` переписывается: режим `password` сохраняет прежнее поведение дословно (компании!), режим `sso` — весь новый флоу. Фильтрация владения — хук `_apply_ownership` (пока passthrough, заполнит Task 3).

**Files:**
- Modify: `siteauth/site_auth.py` (полная замена)
- Modify: `setup_site_auth.py` (копирует 2 модуля, env-ключи)
- Test: `tests/test_studio_auth.py`

**Interfaces:**
- Consumes: `studio_store.*` (Task 1).
- Produces: `SiteAuthMiddleware` с хуком `async def _apply_ownership(self, scope, receive, send, user: str, role: str)` (Task 3 заменяет тело); заголовок `x-studio-user` инжектится в scope для всех авторизованных sso-запросов; эндпоинты `GET /auth/sso?t=`, `GET|POST /auth/login` (админ-пароль), `GET /auth/logout`, `GET /api/v1/studio/me`.

- [ ] **Step 1: Проваливающийся тест**

`tests/test_studio_auth.py` (полностью):

```python
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
import jwt as pyjwt
import studio_store
import site_auth

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
    run(mw(scope("/auth/sso", query=b"t=" + quote(token()).encode()), idle_receive(), r))
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
    run(mw(scope("/auth/sso", query=b"t=" + quote(token(secret="bad")).encode()), idle_receive(), r))
    assert r.status == 401 and not r.h("set-cookie")

    # 3. без сессии: API -> 401 JSON, страница -> 303 на /auth/login
    r = Rec()
    run(mw(scope("/api/v1/boards/"), idle_receive(), r))
    assert r.status == 401
    r = Rec()
    run(mw(scope("/"), idle_receive(), r))
    assert r.status == 303 and r.h("location") == [b"/auth/login"]

    # 4. сессия: запрос проходит, в scope прокинут заголовок пользователя
    seen = {}

    async def spy_app(scope, receive, send):
        seen["user"] = [v for k, v in scope.get("headers", []) if k == b"x-studio-user"]
        await inner_app(scope, receive, send)

    mw2 = site_auth.SiteAuthMiddleware(spy_app)
    r = Rec()
    run(mw2(scope("/api/v1/boards/", cookie=cookie_u1), idle_receive(), r))
    assert r.status == 200 and seen["user"] == [b"u1"], seen

    # 4a. входящий x-studio-user (спуфинг) вырезается
    spoof = dict(scope("/api/v1/boards/", cookie=cookie_u1))
    spoof["headers"] = list(spoof["headers"]) + [(b"x-studio-user", b"attacker")]
    r = Rec()
    run(mw2(spoof, idle_receive(), r))
    assert seen["user"] == [b"u1"], seen

    # 5. /api/v1/studio/me
    r = Rec()
    run(mw2(scope("/api/v1/studio/me", cookie=cookie_u1), idle_receive(), r))
    me = json.loads(r.body)
    assert me == {"mode": "sso", "user_id": "u1", "email": "u1@x.io",
                  "name": "User One", "role": "user"}, me

    # 6. админ-вход паролем в sso-режиме
    async def login_body():
        return {"type": "http.request", "body": b"password=pw", "more_body": False}

    r = Rec()
    run(mw(scope("/auth/login", method="POST"), login_body(), r))
    assert r.status == 303 and "devbim_session=" in r.cookies(), (r.status, r.h("set-cookie"))
    cookie_admin = r.cookies().split(";")[0]
    r = Rec()
    run(mw2(scope("/api/v1/studio/me", cookie=cookie_admin), idle_receive(), r))
    me = json.loads(r.body)
    assert me["role"] == "admin" and me["user_id"] == studio_store.ADMIN_LOCAL, me

    # 7. отозванный пользователь не проходит
    studio_store.set_revoked("u1", True)
    r = Rec()
    run(mw2(scope("/api/v1/boards/", cookie=cookie_u1), idle_receive(), r))
    assert r.status == 401
    studio_store.set_revoked("u1", False)

    # 8. CSP frame-ancestors на страничных ответах sso-режима
    r = Rec()
    run(mw2(scope("/", cookie=cookie_u1), idle_receive(), r))
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
    run(mw(scope("/", cookie=f"devbim_auth={old}"), idle_receive(), r))
    assert r.status == 200, r.status

    print("OK")
finally:
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def scope_ws(cookie=""):
    headers = [(b"cookie", cookie.encode())] if cookie else []
    return {"type": "websocket", "path": "/ws/socket.io/", "headers": headers}
```

- [ ] **Step 2: Запустить, убедиться в провале**

Run: `venv\Scripts\python.exe tests\test_studio_auth.py`
Expected: `AttributeError: module 'site_auth' has no attribute ...` (нет `_sso`/нового флоу; тест 1 падает раньше — `assert r.status == 303`).

- [ ] **Step 3: Переписать `siteauth/site_auth.py`** (полностью; старый файл уже прочитан — шапку docstring обновить):

```python
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
```

Примечания к коду (важно для исполнителя):
- `Secure` в куке `devbim_session` — студия работает за HTTPS-туннелем. Локальная отладка по `http://127.0.0.1` всё равно работает: браузер ставит куки и без Secure на localhost; тесты читают `Set-Cookie` напрямую.
- `_handle_admin_login` в password-режиме недостижим (поток уходит в `_password_flow` раньше) — ветка `if _mode() == "password"` внутри оставлена как защита.
- Совместимость со старым `tests/test_site_auth.py`: в самом низу файла (после `_password_login_page`) оставить алиасы:

```python
# --- совместимость со старыми тестами/вызовами password-режима ---
_token = _legacy_token
_authorized = _legacy_cookie_ok
_login_page = _password_login_page
```

- [ ] **Step 4: Обновить `setup_site_auth.py`**

Заменить функции `deploy_module()` и `ensure_env_password()` и `__main__` (остальное не трогать):

```python
def deploy_module() -> None:
    shutil.copy2(SRC, DST)
    print("Модуль развернут:", DST)
    src2 = BASE / "siteauth" / "studio_store.py"
    dst2 = SP / "invokeai" / "app" / "api" / "routers" / "studio_store.py"
    shutil.copy2(src2, dst2)
    print("Модуль развернут:", dst2)


def ensure_env_password() -> None:
    env = BASE / ".env"
    text = env.read_text(encoding="utf-8") if env.exists() else ""
    if text and not text.endswith("\n"):
        text += "\n"
    defaults = {
        "SITE_PASSWORD": "devbim",
        "STUDIO_AUTH_MODE": "password",
        # STUDIO_JWT_SECRET не добавляем: генерируется при включении sso (см. README)
        "STUDIO_SESSION_TTL": "43200",
        "STUDIO_FRAME_ANCESTORS": "https://devbim.com http://localhost:* http://127.0.0.1:*",
    }
    have = {ln.split("=", 1)[0].strip() for ln in text.splitlines() if "=" in ln}
    for k, v in defaults.items():
        if k not in have:
            text += f"{k}={v}\n"
            print(f"В .env добавлен {k}={v}")
    env.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    deploy_module()
    patch_api_app()
    ensure_env_password()
    print("Готово. Перезапустите сервер (launch\\start_server.bat).")
```

- [ ] **Step 5: Прогнать оба теста**

Run: `venv\Scripts\python.exe tests\test_studio_auth.py && venv\Scripts\python.exe tests\test_studio_store.py && venv\Scripts\python.exe tests\test_site_auth.py`
Expected: три `OK` (старый `test_site_auth.py` проверяет password-режим — не должен сломаться; если упал — regres в `_password_flow`, чинить до зелёного).

- [ ] **Step 6: Коммит**

```bash
git add siteauth/site_auth.py setup_site_auth.py tests/test_studio_auth.py
git commit -m "feat(studio): SSO-мидлварь — /auth/sso (JWT+jti), кука сессии, /studio/me, CSP, админ-пароль fallback; password-режим нетронут"
```

---

### Task 3: Фильтрация владения и ролевые гейты в API

Тело `_apply_ownership` из Task 2 заменяется на реальную фильтрацию. Правила: фильтр работает только в sso-режиме для `role != "admin"`; контент без владельца (легаси) виден только админу; админ не фильтруется вовсе.

**Files:**
- Modify: `siteauth/site_auth.py` (заменить `_apply_ownership`; добавить regex-константы и хелперы)
- Test: `tests/test_studio_ownership.py`

**Interfaces:**
- Consumes: `studio_store.tag/owner`, `self.app` (внутреннее приложение), `_read_body` (уже в файле).
- Produces: HTTP-изоляция: `GET|POST /api/v1/boards/`, `GET|DELETE|PATCH /api/v1/boards/{id}`, `GET /api/v1/images/`, `POST /api/v1/images/upload`, `GET|DELETE|PATCH /api/v1/images/i/{name}/*`, `POST /api/v1/images/{delete,download,star,unstar}`, `GET /api/v1/session_queue[/batches]`; ролевой гейт записи `^/api/v1/(style_presets|workflows)`.

- [ ] **Step 1: Проваливающийся тест**

`tests/test_studio_ownership.py` (полностью):

```python
# -*- coding: utf-8 -*-
"""Тесты изоляции API: тегирование upload/бордов, фильтрация списков, 404 чужого.

Запуск: venv\\Scripts\\python.exe tests\\test_studio_ownership.py
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
import jwt as pyjwt
import studio_store
import site_auth

SECRET = "o" * 40
tmp = Path(tempfile.mkdtemp(prefix="studio_own_test_"))
saved = {k: os.environ.get(k) for k in ("INVOKEAI_ROOT", "STUDIO_AUTH_MODE", "STUDIO_JWT_SECRET",
                                        "STUDIO_SESSION_TTL", "SITE_PASSWORD", "SITE_VALID_UNTIL")}


def run(c):
    return asyncio.new_event_loop().run_until_complete(c)


class Rec:
    def __init__(self):
        self.status = None
        self.headers = []
        self.body = b""

    async def __call__(self, m):
        if m["type"] == "http.response.start":
            self.status, self.headers = m["status"], m.get("headers", [])
        elif m["type"] == "http.response.body":
            self.body += m.get("body", b"")

    def json(self):
        return json.loads(self.body or b"{}")


async def idle(body=b""):
    return {"type": "http.request", "body": body, "more_body": False}


def scope(path, method="GET", cookie=""):
    h = [(b"cookie", cookie.encode())] if cookie else []
    return {"type": "http", "path": path, "method": method, "headers": h}


def session(uid):
    return f"devbim_session={studio_store.mint_session(uid, SECRET)}"


# внутреннее приложение с «заготовленными» ответами InvokeAI
STATE = {"boards": [], "images": []}


async def inner(scope, receive, send):
    path, method = scope["path"], scope["method"]
    if path == "/api/v1/boards/" and method == "GET":
        body = {"items": STATE["boards"], "offset": 0, "limit": 10, "total": len(STATE["boards"])}
    elif path == "/api/v1/boards/" and method == "POST":
        body = {"board_id": "new-board", "board_name": "Test"}
    elif path == "/api/v1/images/" and method == "GET":
        body = {"items": STATE["images"], "offset": 0, "limit": 10, "total": len(STATE["images"])}
    elif path == "/api/v1/images/upload" and method == "POST":
        body = {"image_name": "new-upload.png"}
    else:
        await send({"type": "http.response.start", "status": 200,
                    "headers": [(b"content-type", b"application/json")]})
        await send({"type": "http.response.body", "body": b'{"upstream":true}'})
        return
    raw = json.dumps(body).encode()
    await send({"type": "http.response.start", "status": 200,
                "headers": [(b"content-type", b"application/json"),
                            (b"content-length", str(len(raw)).encode())]})
    await send({"type": "http.response.body", "body": raw})


try:
    os.environ["INVOKEAI_ROOT"] = str(tmp)
    (tmp / ".env").write_text(
        f"STUDIO_AUTH_MODE=sso\nSTUDIO_JWT_SECRET={SECRET}\nSTUDIO_SESSION_TTL=3600\n"
        "SITE_PASSWORD=pw\nSITE_VALID_UNTIL=2030-01-01\n", encoding="utf-8")
    studio_store.init_db()
    studio_store.upsert_user("u1", "u1@x.io", "One", "user")
    studio_store.upsert_user("u2", "u2@x.io", "Two", "user")
    studio_store.upsert_user("adm", "adm@x.io", "Adm", "admin")
    mw = site_auth.SiteAuthMiddleware(inner)

    c1, c2, cadm = session("u1"), session("u2"), session("adm")

    # 1. создание борда тегируется
    r = Rec()
    run(mw(scope("/api/v1/boards/", "POST", c1), idle(b"{}"), r))
    assert r.status == 200 and studio_store.owner("board", "new-board") == "u1"

    # 2. upload тегируется
    r = Rec()
    run(mw(scope("/api/v1/images/upload", "POST", c1), idle(b""), r))
    assert r.status == 200 and studio_store.owner("image", "new-upload.png") == "u1"

    # 3. списки фильтруются
    STATE["boards"] = [{"board_id": "new-board"}, {"board_id": "u2-board"}]
    studio_store.tag("board", "u2-board", "u2")
    r = Rec()
    run(mw(scope("/api/v1/boards/", "GET", c1), idle(), r))
    d = r.json()
    assert [b["board_id"] for b in d["items"]] == ["new-board"] and d["total"] == 1, d

    STATE["images"] = [{"image_name": "new-upload.png"}, {"image_name": "u2.png"},
                       {"image_name": "legacy.png"}]
    studio_store.tag("image", "u2.png", "u2")
    r = Rec()
    run(mw(scope("/api/v1/images/", "GET", c1), idle(), r))
    d = r.json()
    assert [i["image_name"] for i in d["items"]] == ["new-upload.png"] and d["total"] == 1, d

    # админ видит всё, включая легаси
    r = Rec()
    run(mw(scope("/api/v1/images/", "GET", cadm), idle(), r))
    assert len(r.json()["items"]) == 3

    # 4. прямой доступ к чужой картинке -> 404, к своей -> проксируется
    r = Rec()
    run(mw(scope("/api/v1/images/i/u2.png/full", "GET", c1), idle(), r))
    assert r.status == 404, r.status
    r = Rec()
    run(mw(scope("/api/v1/images/i/new-upload.png/full", "GET", c1), idle(), r))
    assert r.status == 200 and r.json() == {"upstream": True}
    r = Rec()  # легаси без владельца: не-админу 404
    run(mw(scope("/api/v1/images/i/legacy.png/full", "GET", c1), idle(), r))
    assert r.status == 404
    r = Rec()
    run(mw(scope("/api/v1/images/i/legacy.png/full", "GET", cadm), idle(), r))
    assert r.status == 200

    # 5. body-эндпоинты: чужое имя -> 403
    r = Rec()
    run(mw(scope("/api/v1/images/delete", "POST", c1), idle(json.dumps({"image_names": ["u2.png"]}).encode()), r))
    assert r.status == 403, r.status
    r = Rec()
    run(mw(scope("/api/v1/images/star", "POST", c1), idle(json.dumps({"image_names": ["new-upload.png"]}).encode()), r))
    assert r.status == 200

    # 6. запись style_presets/workflows: user -> 403, admin -> проксируется
    r = Rec()
    run(mw(scope("/api/v1/style_presets/i/x", "PUT", c1), idle(b"{}"), r))
    assert r.status == 403, r.status
    r = Rec()
    run(mw(scope("/api/v1/workflows/", "POST", c1), idle(b"{}"), r))
    assert r.status == 403
    r = Rec()
    run(mw(scope("/api/v1/style_presets/i/x", "PUT", cadm), idle(b"{}"), r))
    assert r.status == 200

    # 7. очередь фильтруется по batch-владельцу
    async def q_inner(scope, receive, send):
        raw = json.dumps({"items": [{"batch_id": "b1"}, {"batch_id": "b2"}], "total": 2}).encode()
        await send({"type": "http.response.start", "status": 200,
                    "headers": [(b"content-type", b"application/json")]})
        await send({"type": "http.response.body", "body": raw})

    studio_store.tag("batch", "b1", "u1")
    studio_store.tag("batch", "b2", "u2")
    mwq = site_auth.SiteAuthMiddleware(q_inner)
    r = Rec()
    run(mwq(scope("/api/v1/session_queue/", "GET", c1), idle(), r))
    d = r.json()
    assert [i["batch_id"] for i in d["items"]] == ["b1"] and d["total"] == 1, d

    print("OK")
finally:
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
```

- [ ] **Step 2: Запустить, убедиться в провале**

Run: `venv\Scripts\python.exe tests\test_studio_ownership.py`
Expected: первый assert падает (`owner("board","new-board") is None` — passthrough не тегирует).

- [ ] **Step 3: Реализовать фильтрацию**

В `siteauth/site_auth.py` добавить импорт `re`, `unquote` (расширить строку `from urllib.parse import parse_qs, quote` до `from urllib.parse import parse_qs, quote, unquote`) и блок regex рядом с константами:

```python
import re

_RE_BOARDS = re.compile(r"^/api/v1/boards/?$")
_RE_BOARD_ID = re.compile(r"^/api/v1/boards/([^/]+)$")
_RE_IMAGES = re.compile(r"^/api/v1/images/?$")
_RE_IMAGE_ITEM = re.compile(r"^/api/v1/images/i/([^/]+)(?:/.*)?$")
_RE_UPLOAD = re.compile(r"^/api/v1/images/upload/?$")
_RE_IMAGES_BODY = re.compile(r"^/api/v1/images/(delete|download|star|unstar)/?$")
_RE_QUEUE_LIST = re.compile(r"^/api/v1/session_queue/(?:|batches/?)$")
_RE_WRITE_ADMIN = re.compile(r"^/api/v1/(style_presets|workflows)(?:/|$)")
```

Заменить метод `_apply_ownership` на:

```python
    # ---------- изоляция владения (sso, role != admin) ----------
    @staticmethod
    def _visible(uid: str, owner_or_none: str | None) -> bool:
        return owner_or_none == uid  # легаси без владельца видно только админу (он не фильтруется)

    async def _proxy_json(self, scope, receive, send, mutator) -> None:
        """Проксирует ответ приложения и правит JSON-тело через mutator(data)->data."""
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
            data = mutator(data)
            raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
        except Exception:
            pass  # не-JSON ответ -> пропускаем как есть
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

        if role == "admin":  # админ не фильтруется
            await self.app(scope, receive, send)
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
            def filt(d):
                if isinstance(d, dict) and isinstance(d.get("items"), list):
                    orig = d["items"]
                    d["items"] = [it for it in orig if self._visible(
                        uid, studio_store.owner("batch", str((it or {}).get("batch_id", ""))))]
                    try:
                        d["total"] = max(0, int(d.get("total") or len(orig))
                                         - (len(orig) - len(d["items"])))
                    except (TypeError, ValueError):
                        d["total"] = len(d["items"])
                return d

            await self._proxy_json(scope, receive, send, filt)
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

            async def replay():
                sent = False

                async def rcv():
                    nonlocal sent
                    if sent:
                        await asyncio.sleep(3600)
                    sent = True
                    return {"type": "http.request", "body": body, "more_body": False}

                return rcv

            await self.app(scope, await replay(), send)
            return

        await self.app(scope, receive, send)
```

Добавить `import asyncio` в шапку файла (нужен для replay-хелпера).

- [ ] **Step 4: Прогнать тесты**

Run: `venv\Scripts\python.exe tests\test_studio_ownership.py && venv\Scripts\python.exe tests\test_studio_auth.py && venv\Scripts\python.exe tests\test_studio_store.py`
Expected: три `OK`.

- [ ] **Step 5: Коммит**

```bash
git add siteauth/site_auth.py tests/test_studio_ownership.py
git commit -m "feat(studio): изоляция API — тегирование upload/бордов, фильтрация списков/очереди, 404 чужого, 403 записи пресетов/воркфлоу для не-админов"
```

---

### Task 4: Изоляция socket.io — патч `sockets.py` через setup

`setup_site_auth.py` получает функцию `patch_sockets()`: connect-хук заводит соединение в комнату `user:<id>` (по куке из environ), эмит queue-событий уходит в комнату владельца (по image_name/batch_id из оверлей-БД), а не в общий room `queue_id`.

**Files:**
- Modify: `setup_site_auth.py` (добавить `patch_sockets(src: Path | None = None)` + вызов в `__main__`)
- Test: `tests/test_studio_sockets.py`

**Interfaces:**
- Consumes: `studio_store.socket_room_for_event(data)`, `studio_store.room_for_environ(environ)` (Task 1).
- Produces: патченный `venv/.../invokeai/app/api/sockets.py` (маркер `# --- devbim-studio-sso ---`).

- [ ] **Step 1: Проваливающийся тест**

`tests/test_studio_sockets.py` (полностью):

```python
# -*- coding: utf-8 -*-
"""Тесты патча sockets.py: комнаты пользователей и изоляция queue-событий.

Запуск: venv\\Scripts\\python.exe tests\\test_studio_sockets.py
"""
import shutil
import sys
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
sys.path.insert(0, str(BASE / "siteauth"))
import setup_site_auth

ORIG = BASE / "venv/Lib/site-packages/invokeai/app/api/sockets.py"
assert ORIG.is_file(), "нет venv-копии sockets.py"


def patched_copy() -> str:
    tmp = Path(tempfile.mkdtemp(prefix="sockets_patch_")) / "sockets.py"
    shutil.copy2(ORIG, tmp)
    setup_site_auth.patch_sockets(tmp)   # идемпотентно: двойной вызов не ломает
    setup_site_auth.patch_sockets(tmp)
    return tmp.read_text(encoding="utf-8")


s = patched_copy()

# 1. маркеры на месте
assert "devbim-studio-sso" in s
assert 'self._sio.on("connect", handler=self._handle_studio_connect)' in s

# 2. эмит queue-событий идёт через комнату владельца
assert "socket_room_for_event" in s
assert "room=event[1].queue_id" not in s.replace(
    "room=room", "")  # прямой эмит в queue_id остаётся только внутри fallback

# 3. python-синтаксис копии валиден
compile(s, "sockets_patched.py", "exec")

print("OK")
```

- [ ] **Step 2: Запустить, убедиться в провале**

Run: `venv\Scripts\python.exe tests\test_studio_sockets.py`
Expected: `AttributeError: module 'setup_site_auth' has no attribute 'patch_sockets'`

- [ ] **Step 3: Добавить `patch_sockets` в `setup_site_auth.py`**

(вставить после `patch_api_app`; `SP` уже определён в файле)

```python
SOCKETS = SP / "invokeai" / "app" / "api" / "sockets.py"


def patch_sockets(src: Path | None = None) -> None:
    """Комнаты пользователей в socket.io + изоляция queue-событий (sso).

    1) connect: по куке сессии sid вступает в room "user:<id>";
    2) queue-события эмитятся в комнату владельца (image_name/batch_id из
       studio.sqlite), а не в общий room queue_id.
    Идемпотентно: маркер devbim-studio-sso. В password-режиме studio_store
    возвращает None и поведение не меняется.
    """
    path = src or SOCKETS
    s = path.read_text(encoding="utf-8")
    if "devbim-studio-sso" in s:
        print("sockets.py уже пропатчен, пропуск")
        return
    bak = path.with_suffix(".py.studio-bak")
    if not bak.exists():
        shutil.copy2(path, bak)

    anchor_reg = "        self._sio.on(self._unsub_bulk_download, handler=self._handle_unsub_bulk_download)\n"
    insert_reg = anchor_reg + (
        "        # --- devbim-studio-sso: комната пользователя по куке сессии ---\n"
        "        self._sio.on(\"connect\", handler=self._handle_studio_connect)\n"
    )
    assert anchor_reg in s, "не найден якорь регистрации обработчиков в sockets.py"
    s = s.replace(anchor_reg, insert_reg, 1)

    old_handler = (
        "    async def _handle_queue_event(self, event: FastAPIEvent[QueueEventBase]):\n"
        "        await self._sio.emit(event=event[0], data=event[1].model_dump(mode=\"json\"), room=event[1].queue_id)\n"
    )
    new_handler = (
        "    # --- devbim-studio-sso: эмит queue-событий в комнату владельца ---\n"
        "    async def _handle_queue_event(self, event: FastAPIEvent[QueueEventBase]):\n"
        "        room = event[1].queue_id\n"
        "        try:\n"
        "            from invokeai.app.api.routers import studio_store\n"
        "            room = studio_store.socket_room_for_event(event[1].model_dump(mode=\"json\")) or room\n"
        "        except Exception:\n"
        "            pass\n"
        "        await self._sio.emit(event=event[0], data=event[1].model_dump(mode=\"json\"), room=room)\n"
        "\n"
        "    async def _handle_studio_connect(self, sid: str, environ: dict, auth: Any = None) -> None:\n"
        "        try:\n"
        "            from invokeai.app.api.routers import studio_store\n"
        "            room = studio_store.room_for_environ(environ)\n"
        "            if room:\n"
        "                await self._sio.enter_room(sid, room)\n"
        "        except Exception:\n"
        "            pass\n"
    )
    assert old_handler in s, "не найден якорь _handle_queue_event в sockets.py"
    s = s.replace(old_handler, new_handler, 1)

    path.write_text(s, encoding="utf-8")
    print("sockets.py пропатчен (бэкап:", bak.name + ")")
```

И вызвать в `__main__` (после `patch_api_app()`): `patch_sockets()`.

- [ ] **Step 4: Прогнать тест**

Run: `venv\Scripts\python.exe tests\test_studio_sockets.py`
Expected: `OK`

- [ ] **Step 5: Коммит**

```bash
git add setup_site_auth.py tests/test_studio_sockets.py
git commit -m "feat(studio): патч sockets.py — connect в комнату user:<id>, queue-события только владельцу"
```

---

### Task 5: Тегирование генераций в ImageRouter-прокси

Перехват `enqueue_batch` уже знает HTTP-контекст: мидлварь Task 2 инжектит `x-studio-user` в scope. Прокси читает его, передаёт в обработчики, тегирует batch и картинки.

**Files:**
- Modify: `imagerouter/imagerouter_router.py` (5 точек правки, см. шаги)

**Interfaces:**
- Consumes: заголовок `x-studio-user` в scope (Task 2), `studio_store.tag` (Task 1; импорт через venv-модуль `invokeai.app.api.routers.studio_store`, лениво и с try/except — без деплоя ничего не ломается).
- Produces: `_studio_user_from_scope(scope) -> str | None`; сигнатуры `_handle_canvas_generation(queue_id, payload, studio_user=None) -> dict` и `_handle_upscale_generation(queue_id, payload, studio_user=None) -> dict`; `_studio_tag(kind, key, user)`.

- [ ] **Step 1: Хелперы (вставить после `_ir_error_body`, ~строка 2051):**

```python
def _studio_user_from_scope(scope) -> "str | None":
    """Пользователь студии, инжектированный SiteAuthMiddleware (sso-режим)."""
    for k, v in scope.get("headers", []):
        if k == b"x-studio-user":
            return v.decode("latin-1") or None
    return None


def _studio_tag(kind: str, key, user: "str | None") -> None:
    """Записать владение в оверлей-БД; без деплоя studio_store — молча пропустить."""
    if not user or not key:
        return
    try:
        from invokeai.app.api.routers import studio_store
        studio_store.tag(kind, str(key), user)
    except Exception:
        pass
```

- [ ] **Step 2: Передать пользователя в обработчик**

В `ImageRouterCanvasMiddleware.__call__`, заменить блок вызова (строки ~2143–2144):

```python
                try:
                    studio_user = _studio_user_from_scope(scope)
                    result = await asyncio.to_thread(handler, queue_id, payload, studio_user)
```

(остальное в `try`/`except` не меняется).

- [ ] **Step 3: Сигнатуры обработчиков**

`def _handle_canvas_generation(queue_id: str, payload: dict, studio_user: str | None = None) -> dict:`
`def _handle_upscale_generation(queue_id: str, payload: dict, studio_user: str | None = None) -> dict:`

- [ ] **Step 4: Тегирование batch**

В обоих обработчиках сразу после `events.dispatch(BatchEnqueuedEvent(...))` (canvas ~строка 1476, upscale ~строка 1865) добавить:

```python
    _studio_tag("batch", batch_id, studio_user)
```

- [ ] **Step 5: Тегирование картинок**

В обоих обработчиках сразу после `dto = services.images.create(...)` (canvas ~строка 1752, upscale ~строка 1951) добавить:

```python
                    _studio_tag("image", dto.image_name, studio_user)
```

(с тем же отступом, что и `dto = ...`).

- [ ] **Step 6: Синтаксис и существующие тесты**

Run: `venv\Scripts\python.exe -c "import ast;ast.parse(open(r'imagerouter/imagerouter_router.py',encoding='utf-8').read());print('OK')"`
Expected: `OK`
Run: `venv\Scripts\python.exe tests\test_upscale_cloud.py && venv\Scripts\python.exe tests\test_main_models.py`
Expected: `OK` (существующие тесты прокси не сломаны; если тест обращается к `_handle_canvas_generation` напрямую — обновить вызов с новым опциональным параметром).

- [ ] **Step 7: Коммит**

```bash
git add imagerouter/imagerouter_router.py
git commit -m "feat(studio): тегирование владения в ImageRouter-прокси — batch при enqueue, image после images.create"
```

---

### Task 6: Изоляция кастомных роутеров IFC / PDF / 3D

**Files:**
- Modify: `ifc/ifc_router.py`, `pdf/pdf_router.py`, `threed/threed_router.py`

**Interfaces:**
- Consumes: заголовок `x-studio-user` (Task 2), `studio_store.tag/owner/effective_role` (Task 1).
- Produces: у каждого роутера хелпер `_studio_user(request) -> str | None` и проверка владения в list/file/delete/jobs; `PUT /v1/threed/model` — только admin.

- [ ] **Step 1: `ifc/ifc_router.py`**

Добавить импорты: `from fastapi import Request` (расширить существующую строку fastapi) и после `ifc_router = ...`:

```python
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
```

`list_models` — добавить параметр и фильтр:

```python
@ifc_router.get("/list")
def list_models(request: Request) -> dict:
    items = []
    for p in sorted(_store_dir().iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
        if not p.is_file() or not p.name.lower().endswith(ALLOWED_EXT):
            continue
        if not _studio_visible(request, "ifc", p.name):
            continue
        st = p.stat()
        items.append({"name": p.name, "size": st.st_size, "modified": int(st.st_mtime)})
    return {"models": items}
```

`upload_model` — добавить `request: Request` первым параметром и после успешного сохранения (перед `return`) — тег:

```python
    u = _studio_user(request)
    if u:
        try:
            from invokeai.app.api.routers import studio_store
            studio_store.tag("ifc", path.name, u)
        except Exception:
            pass
    return {"name": path.name, "size": size, "seconds": round(time.time() - t0, 1)}
```

`get_model` и `delete_model` — добавить `request: Request` и первой строкой тела:

```python
    if not _studio_visible(request, "ifc", name):
        raise HTTPException(status_code=404, detail="Файл не найден")
```

- [ ] **Step 2: `pdf/pdf_router.py`**

Те же хелперы, что в IFC (`_studio_user`, `_studio_visible` — с `kind="pdf"`; импорт `Request` добавить к строке fastapi). Затем:

`list_docs` — параметр и фильтр:

```python
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
```

`upload_doc` — добавить `request: Request` и перед `return` тег:

```python
    u = _studio_user(request)
    if u:
        try:
            from invokeai.app.api.routers import studio_store
            studio_store.tag("pdf", path.name, u)
        except Exception:
            pass
    return {"name": path.name, "size": size, "seconds": round(time.time() - t0, 1)}
```

`get_doc` и `delete_doc` — добавить `request: Request`, первой строкой тела:

```python
    if not _studio_visible(request, "pdf", name):
        raise HTTPException(status_code=404, detail="Файл не найден")
```

- [ ] **Step 3: `threed/threed_router.py`**

`generate` (POST `/v1/threed/generate`): добавить `request: Request`; после создания job (в `_job_new`/регистрации) — тег:

```python
    u = _studio_user(request)   # хелпер как в ifc_router
    if u:
        try:
            from invokeai.app.api.routers import studio_store
            studio_store.tag("threed", job["id"], u)
        except Exception:
            pass
```

`get_job` (GET `/v1/threed/jobs/{job_id}`): до возврата —

```python
    u = _studio_user(request)
    if u is not None:
        from invokeai.app.api.routers import studio_store
        o = studio_store.owner("threed", job_id)
        if not (o == u or (o is None and studio_store.effective_role(u) == "admin")):
            raise HTTPException(status_code=404, detail="Job not found")
```

`put_model` (PUT `/v1/threed/model`): в начало тела —

```python
    u = _studio_user(request)
    if u is not None:
        from invokeai.app.api.routers import studio_store
        if studio_store.effective_role(u) != "admin":
            raise HTTPException(status_code=403, detail="Administrator only")
```

- [ ] **Step 4: Синтаксис + существующие тесты**

Run: `venv\Scripts\python.exe -c "import ast;[ast.parse(open(f,encoding='utf-8').read()) for f in [r'ifc/ifc_router.py',r'pdf/pdf_router.py',r'threed/threed_router.py']];print('OK')"`
Run: `venv\Scripts\python.exe tests\test_pdf_router.py && venv\Scripts\python.exe tests\test_threed.py`
Expected: `OK` (тесты этих роутеров работают без заголовка x-studio-user — путь `u is None` возвращает прежнее поведение).

- [ ] **Step 5: Коммит**

```bash
git add ifc/ifc_router.py pdf/pdf_router.py threed/threed_router.py
git commit -m "feat(studio): изоляция IFC/PDF/3D — фильтрация списков и доступа по владельцу, выбор модели 3D только админу"
```

---

### Task 7: Админ-панель `/admin`

Заменяет заглушку `_admin_panel` из Task 2: таблица пользователей (email/имя/роль/счётчики/last_seen), переопределение роли, отзыв, JSON API.

**Files:**
- Modify: `siteauth/site_auth.py` (заменить `_admin_panel`; добавить `_admin_api`)

**Interfaces:**
- Consumes: `studio_store.list_users/owned_count/set_role_override/set_revoked/effective_role` (Task 1), `self._inject_user_header` (Task 2).
- Produces: `GET /admin` (HTML), `GET /admin/api/users` (JSON), `POST /admin/api/users/{user_id}/role` (body `{"role": "admin"|"user"|null}`), `POST /admin/api/users/{user_id}/revoke` (body `{"revoked": bool}`).

- [ ] **Step 1: Реализация (заменить метод-заглушку)**

```python
    async def _admin_panel(self, scope, receive, send, user: str, role: str) -> None:
        path, method = scope.get("path", ""), scope.get("method", "GET").upper()
        if path == "/admin/api/users" and method == "GET":
            users = []
            for u in studio_store.list_users():
                if u["user_id"] == studio_store.ADMIN_LOCAL:
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
                data = {}
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

        await _send_html(send, 200, _ADMIN_PAGE)
```

И модульная константа (внизу файла, рядом с другими страницами):

```python
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
fetch('/admin/api/users').then(r => r.json()).then(d => {
  const tb = document.querySelector('#t tbody');
  for (const u of d.users) {
    const tr = document.createElement('tr');
    if (u.revoked) tr.className = 'revoked';
    const when = new Date(u.last_seen * 1000).toLocaleString();
    tr.innerHTML = '<td>' + u.email + '</td><td>' + (u.name || '') + '</td>' +
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
```

- [ ] **Step 2: Расширить тест владения админ-панелью (в `tests/test_studio_ownership.py`, перед `print("OK")` внутри `try`):**

```python
    # 8. админ-панель: список пользователей и действия
    r = Rec()
    run(mw(scope("/admin/api/users", "GET", cadm), idle(), r))
    d = r.json()
    emails = {u["email"] for u in d["users"]}
    assert emails == {"u1@x.io", "u2@x.io"}, emails
    r = Rec()
    body = json.dumps({"role": "admin"}).encode()
    run(mw(scope("/admin/api/users/u2/role", "POST", cadm), idle(body), r))
    assert r.status == 200 and studio_store.effective_role("u2") == "admin"
    r = Rec()
    run(mw(scope("/admin/api/users/u2/role", "POST", c1), idle(body), r))
    assert r.status == 403, r.status  # не-админ не имеет доступа к /admin
```

- [ ] **Step 3: Прогнать**

Run: `venv\Scripts\python.exe tests\test_studio_ownership.py`
Expected: `OK`

- [ ] **Step 4: Коммит**

```bash
git add siteauth/site_auth.py tests/test_studio_ownership.py
git commit -m "feat(studio): админ-панель /admin — пользователи, переопределение роли, блокировка"
```

---

### Task 8: JS — гейт по роли и пользователь в баннере

**Files:**
- Modify: `imagerouter/devbim_admin.js` (роль вместо пароля в sso-режиме)
- Modify: `devbim_banner.js` (email + «Выйти»)

**Interfaces:**
- Consumes: `GET /api/v1/studio/me` → `{"mode","user_id","email","name","role"}` (Task 2).
- Produces: глобальное поведение — в sso-режиме admin входит в Model Manager/Настройки без пароля, user получает отказ; баннер показывает email и кнопку выхода.

- [ ] **Step 1: `imagerouter/devbim_admin.js` — кэш роли**

Вставить после строки `var AUTH_URL = '/api/v1/imagerouter/admin-auth';` (строка 26):

```javascript
  // --- DevBIM studio SSO: роль из /api/v1/studio/me (mode==='sso') ---
  var ssoRole = null;   // 'admin' | 'user' | null (password-режим или ошибка)

  function warmRole() {
    fetch('/api/v1/studio/me', { credentials: 'same-origin' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) { ssoRole = (d && d.mode === 'sso') ? d.role : null; })
      .catch(function () { ssoRole = null; });
  }
```

Заменить `ensureUnlocked` (строки 171–176) на:

```javascript
  function ensureUnlocked(onSuccess) {
    if (ssoRole === 'admin') { unlocked = true; window.__devbimUnlocked = true; onSuccess(); return; }
    if (ssoRole === 'user') { alert('Доступно только администратору'); return; }
    isProtected(function (on) {
      if (!on || unlocked) { if (on) window.__devbimUnlocked = true; onSuccess(); return; }
      askPassword(onSuccess);
    });
  }
```

В обработчике клика по шестерёнке заменить строку 208 `if (protectedCache === false) return; // защиты нет — пропускаем исходный клик` на:

```javascript
    if (protectedCache === false && ssoRole !== 'user') return; // защиты нет и юзер не sso — пропускаем
```

В конце IIFE рядом с прогревом (строка 236 `isProtected(function () {});`) добавить:

```javascript
  warmRole(); // прогрев кэша роли студии
```

- [ ] **Step 2: `devbim_banner.js` — пользователь и выход**

В CSS-строку (после правила `.devbim-tagline`, строка 48) добавить:

```javascript
    '#devbim-banner .devbim-user{display:flex;align-items:center;gap:10px;white-space:nowrap;' +
    'font-size:12.5px;color:#E6EAF2}' +
    '#devbim-banner .devbim-user button{background:#38BDF8;color:#06121C;border:0;border-radius:6px;' +
    'padding:4px 10px;font-size:12px;font-weight:600;cursor:pointer}' +
    '#devbim-banner .devbim-user button:hover{background:#5CC9FA}' +
```

В `init()` после `banner.appendChild(tagline);` (строка 115) добавить:

```javascript
    loadUser(banner);
```

И перед `init` добавить функцию:

```javascript
  // --- SSO: email пользователя + «Выйти» (только в sso-режиме) ---
  function loadUser(banner) {
    fetch('/api/v1/studio/me', { credentials: 'same-origin' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) {
        if (!d || d.mode !== 'sso' || !d.user_id) return;
        var chip = document.createElement('span');
        chip.className = 'devbim-user';
        var who = document.createElement('span');
        who.textContent = d.email || d.name || d.user_id;
        if (d.role === 'admin') who.textContent += ' · admin';
        var out = document.createElement('button');
        out.type = 'button';
        out.textContent = 'Выйти';
        out.onclick = function () { location.href = '/auth/logout'; };
        chip.appendChild(who);
        chip.appendChild(out);
        banner.appendChild(chip);
      })
      .catch(function () { /* без панели — не страшно */ });
  }
```

- [ ] **Step 3: Синтаксис-проверки**

Run: `node --check imagerouter/devbim_admin.js && node --check devbim_banner.js`
Expected: пусто (обе команды молча успешны).

- [ ] **Step 4: Коммит**

```bash
git add imagerouter/devbim_admin.js devbim_banner.js
git commit -m "feat(studio): гейт Model Manager/Настроек по роли SSO; баннер — email пользователя и выход"
```

---

### Task 9: Деплой-обвязка — токен-утилита, Linux-лаунчер, ТЗ для сайта, README/HANDOFF

**Files:**
- Create: `tools/mint_test_token.py`, `launch/start_server.sh`, `docs/INTEGRATION-devbim-com.md`
- Modify: `README.md`, `HANDOFF.md`

**Interfaces:**
- Consumes: `studio_store.validate_token` (проверка утилиты), `launch/start_devbim.bat` (образец запуска).

- [ ] **Step 1: `tools/mint_test_token.py`**

```python
# -*- coding: utf-8 -*-
"""Утилита локальной проверки SSO: минт тестового JWT как у devbim.com.

Запуск (из корня, venv-питоном):
  venv\\Scripts\\python.exe tools\\mint_test_token.py --email a@b.io --role admin
Секрет: STUDIO_JWT_SECRET из .env (или --secret). Печатает токен и готовый URL.
"""
from __future__ import annotations

import argparse
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "siteauth"))
import jwt  # PyJWT из venv

import studio_store


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--sub", default="test-user")
    p.add_argument("--email", default="test@example.com")
    p.add_argument("--name", default="Test User")
    p.add_argument("--role", default="user", choices=["user", "admin"])
    p.add_argument("--ttl", type=int, default=300)
    p.add_argument("--secret", default=None)
    p.add_argument("--base", default="http://127.0.0.1:9090")
    a = p.parse_args()

    secret = a.secret or studio_store.env_or("STUDIO_JWT_SECRET")
    if not secret:
        sys.exit("Нет STUDIO_JWT_SECRET (в .env или --secret)")
    now = int(time.time())
    claims = {"sub": a.sub, "email": a.email, "name": a.name, "role": a.role,
              "iat": now, "exp": now + a.ttl, "jti": str(uuid.uuid4())}
    token = jwt.encode(claims, secret, algorithm="HS256")
    print(token)
    print(f"{a.base}/auth/sso?t={token}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: `launch/start_server.sh`** (зеркало `start_devbim.bat` для Linux-хостинга)

```bash
#!/usr/bin/env bash
# Запуск DevBIM Image Studio на Linux (хостинг devbim.com).
# До запуска: python3.11 -m venv venv && venv/bin/pip install invokeai==6.2.0 &&
#   применить setup-скрипты корня в порядке из README (rebrand -> ... -> site_auth).
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8
export INVOKEAI_ROOT="${INVOKEAI_ROOT:-$(pwd)/data}"
exec venv/bin/python -u -c "from invokeai.app.run_app import run_app; run_app()"
```

Run: `git update-index --add --chmod=+x launch/start_server.sh` (исполняемый бит в git).

- [ ] **Step 3: `docs/INTEGRATION-devbim-com.md`** — ТЗ для разработчика сайта (полное содержание):

```markdown
# Интеграция Image Studio в devbim.com — ТЗ для основного сервиса

Студия: https://studio.devbim.com (отдельный сервис, iframe внутри кабинета).

## 1. Эндпоинт токена (бэкенд devbim.com)

Выдаёт JWT для iframe-авторизации студии; доступен только авторизованному
(Google-сессия) пользователю.

- JWT HS256, секрет ≥32 символов — передаётся администратору студии вне канала
  и совпадает с `STUDIO_JWT_SECRET` в .env студии.
- Claims: `sub` (ID пользователя сайта, строка), `email`, `name` (опц.),
  `picture` (опц.), `role`: `"admin"|"user"` (email'ы devBIM → admin),
  `iat`, `exp` (= iat + ≤600 с, рекомендуем 300 с), `jti` (UUID, одноразовость).
- Рекомендуемое имя: `GET /api/studio-token` → `{"token": "...", "url": "https://studio.devbim.com"}`.

## 2. Страница кабинета `/designing/image-studio`

1. При открытии (и при перезагрузке iframe): fetch токена со своего бэкенда.
2. `iframe.src = "https://studio.devbim.com/auth/sso?t=" + token`.
3. Атрибуты: `allow="clipboard-write; fullscreen"`, `referrerpolicy="no-referrer"`,
   высота — во весь экран контента, `border: 0`.
4. Никаких своих куки студии не нужно — студия ставит свои (same-site: оба на devbim.com).

## 3. DNS

`studio.devbim.com` → сервер/туннель студии (CNAME; согласовать с администратором студии).

## 4. SHOULD: авто-обновление сессии

Студия при истёкшей сессии шлёт в родитель `postMessage('studio:expired', '*')`
и показывает страницу «войдите заново». Рекомендуется слушать событие и
перезагружать iframe с новым токеном:

    window.addEventListener('message', (e) => {
      if (e.data === 'studio:expired') reloadIframeWithFreshToken();
    });

## 5. Что НЕ надо делать

- Не встраивать студию на другие домены (CSP `frame-ancestors` это заблокирует).
- Не кэшировать токен дольше его `exp`; не логгировать URL с `?t=`.
- Не передавать токен третьим сторонам — он даёт вход в аккаунт пользователя.
```

- [ ] **Step 4: README/HANDOFF**

В `README.md` — новый раздел «Многопользовательский режим (devbim.com)»: краткое описание режимов (`STUDIO_AUTH_MODE`), ключей `.env`, включение sso (сгенерировать секрет `python -c "import secrets;print(secrets.token_urlsafe(32))"` → `STUDIO_JWT_SECRET`), ссылка на `docs/INTEGRATION-devbim-com.md`, локальная проверка через `tools/mint_test_token.py`.

В `HANDOFF.md` — раздел «Что реализовано» дополнить пунктом про SSO/воркспейсы (по факту сделанного, кратко: режимы, файлы, тесты, грабли — «легаси-контент без владельца видит только админ», «очередь default общая, изоляция через комнаты user:<id>»).

- [ ] **Step 5: Проверка утилиты**

Run: `venv\Scripts\python.exe tools\mint_test_token.py --email t@x.io --role admin --secret 0123456789abcdef0123456789abcdef`
Expected: две строки — JWT и URL (токен начинается с `eyJ`).

- [ ] **Step 6: Коммит**

```bash
git add tools/mint_test_token.py launch/start_server.sh docs/INTEGRATION-devbim-com.md README.md HANDOFF.md
git commit -m "feat(studio): деплой-обвязка — mint-утилита, Linux-лаунчер, ТЗ интеграции devbim.com, README/HANDOFF"
```

---

### Task 10: Сквозная деплой-проверка на venv

**Files:**
- Modify: `venv/...` (через setup-скрипт — НЕ руками)

- [ ] **Step 1: Развернуть в venv**

```bash
venv\Scripts\python.exe setup_site_auth.py
```
Expected: «Модуль развернут» ×2, «api_app.py уже пропатчен, пропуск» (или патч), «sockets.py пропатчен (бэкап: sockets.py.studio-bak)», env-ключи добавлены.

- [ ] **Step 2: Все тесты студии + старые**

```bash
venv\Scripts\python.exe tests\test_studio_store.py && venv\Scripts\python.exe tests\test_studio_auth.py && venv\Scripts\python.exe tests\test_studio_ownership.py && venv\Scripts\python.exe tests\test_studio_sockets.py && venv\Scripts\python.exe tests\test_site_auth.py && venv\Scripts\python.exe tests\test_pdf_router.py && venv\Scripts\python.exe tests\test_threed.py
```
Expected: все `OK`.

- [ ] **Step 3: Импорт проверка развернутых модулей**

```bash
venv\Scripts\python.exe -c "from invokeai.app.api.routers import site_auth, studio_store; print('OK')"
```
Expected: `OK`

- [ ] **Step 4: Перезапуск сервера**

```bash
powershell -NoProfile -ExecutionPolicy Bypass -File launch\_restart_server.ps1
```
Ждать порт 9090 (до ~90 с; `netstat -ano | findstr :9090`).

- [ ] **Step 5: curl-проверки (password-режим по умолчанию — регресс компаний)**

```bash
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:9090/auth/login   # 200
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:9090/api/v1/boards/  # 303 (редирект на логин)
```

- [ ] **Step 6: SMOKE sso-режима (временно)**

В `.env` базы инстанса выставить `STUDIO_AUTH_MODE=sso`, `STUDIO_JWT_SECRET=<из mint-утилиты>`, перезапустить сервер, затем:

```bash
venv\Scripts\python.exe tools\mint_test_token.py --email smoke@x.io --role admin > /tmp/tok.txt
TOK=$(head -1 /tmp/tok.txt)
curl -s -i "http://127.0.0.1:9090/auth/sso?t=$TOK" | grep -E "HTTP|set-cookie|location"  # 303 + devbim_session
```
Вырезать куку из ответа и:

```bash
curl -s -H "Cookie: devbim_session=<...>" http://127.0.0.1:9090/api/v1/studio/me  # {"mode":"sso",...}
```
Вернуть `STUDIO_AUTH_MODE=password` в `.env`, перезапустить сервер (базовый инстанс остаётся в password до решения о переезде на studio.devbim.com).

- [ ] **Step 7: Ручной чек-лист (за пользователем, по желанию)**

Два браузера: (1) админ по паролю через `/auth/login`; (2) «пользователь» по ссылке из mint-утилиты. Проверить: генерации не пересекаются в галереях; прогресс-бар другого пользователя не виден; чужая картинка по прямому URL — 404; у user нет «Настроек»/Model Manager (alert «только администратору»), у admin — есть без пароля; баннер показывает email и «Выйти»; `/admin` — таблица.

- [ ] **Step 8: Финальный коммит (если что-то правилось по итогам smoke)**

```bash
git add -A
git commit -m "chore(studio): деплой-проверка sso на venv — мелкие правки по итогам smoke"
```

---

## Вне плана (внешние зависимости — после интеграции)

- **Переключение туннеля на `studio.devbim.com`**: правка `~/.cloudflared/config-design.yml` (hostname) + DNS-запись CNAME на стороне devbim.com (см. ТЗ §3). Делается, когда разработчик сайта подтвердит готовность эндпоинта токена; до этого базовый инстанс остаётся в password-режиме.
- **Включение `STUDIO_AUTH_MODE=sso` на боевом инстансе** — одновременно с переездом на поддомен.

## Самопроверка плана (выполнена при написании)

1. **Покрытие спеки**: §Аутентификация → Tasks 1–2; §Роли/права → Tasks 2–3, 7–8; §Оверлей-БД → Tasks 1, 3, 5, 6; §Изоляция HTTP → Task 3; §Сокеты → Task 4; §Кастомные роутеры → Task 6; §Админ-панель/баннер → Tasks 7–8; §Развертывание → Tasks 2, 9–10; §ТЗ сайта → Task 9; §Проверка → тесты в Tasks 1–4, 7, 10.
2. Отступление от спеки (улучшение): кнопка «назначить легаси-контент мне» не нужна — легаси без владельца уже трактуется как админское (`_visible` + admin не фильтруется); тот же результат без миграции.
3. **Плейсхолдеры**: нет TBD; единственная осознанная ловушка — дублированная строка content-length в `_send_json` Task 2 с явным указанием удалить первую.
4. **Типы/имена**: `studio_store.*` сверены между задачами; `_apply_ownership(scope, receive, send, user, role)` сигнатура едина (Task 2 объявляет, Task 3 заменяет тело); `x-studio-user` — единое имя заголовка; `tag(kind,...)` kind-значения: `image|board|batch|ifc|pdf|threed`.
