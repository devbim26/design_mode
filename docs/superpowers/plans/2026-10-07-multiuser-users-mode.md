# Многопользовательский режим «users» — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Вход по email/паролю + персональный токен ImageRouter; физические per-user папки для IFC/PDF/3D; управление пользователями (панель + CLI) — режим `STUDIO_AUTH_MODE=users` поверх существующей SSO-инфраструктуры.

**Architecture:** Расширяется существующая SiteAuthMiddleware/studio.sqlite (пароли и ir_token — новые колонки `users`; новый режим `users` ветвится рядом с `sso`). Ключ ImageRouter выбирается новой функцией `imagerouter.effective_key(studio_user)` (персональный токен; обычному пользователю без токена глобальный ключ НЕ подставляется). ifc/pdf-роутеры пишут файлы в подпапку пользователя `data/<kind>/<email>/` с сохранением плоских имён в API. threed пишет IFC-результат в подпапку пользователя и тегирует его.

**Tech Stack:** Python 3.11 (venv InvokeAI 6.2.0), Starlette ASGI-middleware, sqlite3 (stdlib), PBKDF2 (stdlib), plain-assert тесты (`venv\Scripts\python.exe tests\<имя>.py`).

**Спека:** `docs/superpowers/specs/2026-10-07-multiuser-users-mode-design.md`

## Global Constraints

- Не править `venv/.../site-packages` руками — только setup-скрипты в корне.
- Все setup-скрипты идемпотентны; порядок: imagerouter → ifcviewer → pdfviewer → designcode → threed → site_auth.
- Тесты — plain asserts, печать `OK` в конце; запуск из корня: `venv\Scripts\python.exe tests\<имя>.py`.
- Тесты не ходят в сеть: проверки токена и апстрим-вызовы мокаются (подмена модуля/функции).
- password- и sso-режимы не меняют поведение (существующие `test_site_auth.py`, `test_studio_*.py`, `test_pdf_router.py` проходят без правок).
- В git не входят: `.env`, `companies/*`, `data/*`.
- Кириллица в коде/доках — UTF-8; JS-бандлы после правок проверять парсингом node.
- Каждый таск завершается коммитом (только файлы таска).

---

### Task 1: studio_store — пароли, ir_token, CRUD локальных пользователей

**Files:**
- Modify: `siteauth/studio_store.py`
- Test: `tests/test_userauth_store.py`

**Interfaces (produces, используется всеми следующими тасками):**
- `auth_mode() -> "password"|"sso"|"users"`
- `create_user(email, name="", password=None, role="user", ir_token=None) -> dict` — бросает `ValueError` при кривом email/роли/дубликате
- `find_user_by_email(email) -> dict | None` (регистронезависимо)
- `set_password(user_id, password)`; `check_password(user_id, password) -> bool`
- `set_ir_token(user_id, token | None)`; в `users` появляются колонки `password_hash`, `ir_token` (вернуть их может `get_user`)
- `user_id` локальных: `u_` + sha256(email.lower())[:16]
- `room_for_environ` работает и в режиме `users`

- [ ] **Step 1: тест (fail)**

`tests/test_userauth_store.py` (шаблон — `tests/test_studio_store.py`: tmpdir в INVOKEAI_ROOT, siteauth на sys.path):

```python
# -*- coding: utf-8 -*-
"""Тесты многопользовательского store: пароли, ir_token, CRUD, auth_mode."""
import os, sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "siteauth"))
import studio_store

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
    for bad in (("ivan@mail.ru", "x" * 8, "user"),   # дубликат
                ("not-an-email", "x" * 8, "user"),   # кривой email
                ("a@b.ru", "x" * 8, "boss")):        # кривая роль
        try:
            studio_store.create_user(*bad)
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

    # миграция на «старой» БД (колонок нет) — создаётся в tmp2
    tmp2 = Path(tempfile.mkdtemp(prefix="userauth_store2_"))
    os.environ["INVOKEAI_ROOT"] = str(tmp2)
    import importlib; importlib.reload(studio_store)
    old = tmp2 / "data" / "studio.sqlite"; old.parent.mkdir(parents=True)
    import sqlite3
    c = sqlite3.connect(old)
    c.execute("""CREATE TABLE users(user_id TEXT PRIMARY KEY, email TEXT NOT NULL,
        name TEXT NOT NULL DEFAULT '', role TEXT NOT NULL DEFAULT 'user',
        role_override TEXT, revoked INTEGER NOT NULL DEFAULT 0,
        created_at INTEGER NOT NULL, last_seen INTEGER NOT NULL)""")
    c.execute("INSERT INTO users VALUES('legacy1','l@l.ru','','user',NULL,0,1,1)")
    c.commit(); c.close()
    studio_store.init_db()
    assert studio_store.find_user_by_email("l@l.ru") is not None
    print("OK")

main()
```

- [ ] **Step 2: прогнать — ожидается падение** (`AttributeError: ... has no attribute 'auth_mode'`): `venv\Scripts\python.exe tests\test_userauth_store.py`
- [ ] **Step 3: реализация в `siteauth/studio_store.py`**

Добавить `import hashlib` к импортам. Новые константы/фелды (после `ADMIN_LOCAL`):

```python
PBKDF2_ITER = 240_000
_EMAIL_RE = __import__("re").compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")  # сверху добавить import re
```

В `init_db()` после обоих `CREATE TABLE` добавить миграцию и индекс:

```python
            cols = {r[1] for r in c.execute("PRAGMA table_info(users)")}
            if "password_hash" not in cols:
                c.execute("ALTER TABLE users ADD COLUMN password_hash TEXT")
            if "ir_token" not in cols:
                c.execute("ALTER TABLE users ADD COLUMN ir_token TEXT")
            try:
                c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users(lower(email))")
            except Exception as e:  # noqa: BLE001 — дубли в легаси-бд не должны ронять старт
                print(f"[studio_store] email index skipped: {e}", file=sys.stderr)
```

Новые функции (блок «пользователи»):

```python
def auth_mode() -> str:
    m = env_or("STUDIO_AUTH_MODE", "password").strip().lower()
    return m if m in ("password", "sso", "users") else "password"


def _hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITER)
    return f"pbkdf2_sha256${PBKDF2_ITER}${salt.hex()}${dk.hex()}"


def _check_password_hash(stored: str, password: str) -> bool:
    try:
        algo, iters, salt_hex, want = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"),
                                 bytes.fromhex(salt_hex), int(iters))
        return hmac.compare_digest(dk.hex(), want)
    except Exception:
        return False


def user_id_for_email(email: str) -> str:
    return "u_" + hashlib.sha256((email or "").strip().lower().encode("utf-8")).hexdigest()[:16]


def create_user(email: str, name: str = "", password: str | None = None,
                role: str = "user", ir_token: str | None = None) -> dict:
    email = (email or "").strip()
    if not _EMAIL_RE.match(email):
        raise ValueError("некорректный email")
    if role not in ("user", "admin"):
        raise ValueError("role must be user|admin")
    init_db()
    if find_user_by_email(email):
        raise ValueError("пользователь с такой почтой уже есть")
    now = int(time.time())
    uid = user_id_for_email(email)
    token = (ir_token or "").strip() or None
    with _LOCK, _conn() as c:
        c.execute(
            """INSERT INTO users(user_id,email,name,role,created_at,last_seen,
                                 password_hash,ir_token) VALUES(?,?,?,?,?,?,?,?)""",
            (uid, email, name or "", role, now, now,
             _hash_password(password) if password else None, token),
        )
    u = get_user(uid)
    assert u is not None
    return u


def find_user_by_email(email: str) -> dict | None:
    try:
        with _conn() as c:
            row = c.execute("SELECT * FROM users WHERE lower(email)=lower(?)",
                            ((email or "").strip(),)).fetchone()
            return dict(row) if row else None
    except Exception:
        return None


def set_password(user_id: str, password: str) -> None:
    with _LOCK, _conn() as c:
        c.execute("UPDATE users SET password_hash=? WHERE user_id=?",
                  (_hash_password(password), user_id))


def check_password(user_id: str, password: str) -> bool:
    u = get_user(user_id)
    return bool(u and u.get("password_hash")) and _check_password_hash(u["password_hash"], password or "")


def set_ir_token(user_id: str, token: str | None) -> None:
    with _LOCK, _conn() as c:
        c.execute("UPDATE users SET ir_token=? WHERE user_id=?",
                  ((token or "").strip() or None, user_id))


def get_ir_token(user_id: str) -> "str | None":
    u = get_user(user_id)
    return (u.get("ir_token") or None) if u else None
```

`room_for_environ`: заменить `if env_or("STUDIO_AUTH_MODE", "password").strip().lower() != "sso": return None` на `if env_or("STUDIO_AUTH_MODE", "password").strip().lower() == "password": return None`.

- [ ] **Step 4: прогнать — OK**: `venv\Scripts\python.exe tests\test_userauth_store.py`
- [ ] **Step 5: регресс**: `venv\Scripts\python.exe tests\test_studio_store.py` и `tests\test_studio_sockets.py` — OK
- [ ] **Step 6: commit** `git add siteauth/studio_store.py tests/test_userauth_store.py && git commit -m "feat(userauth): studio_store — пароли PBKDF2, ir_token, CRUD пользователей, режим users"`

---

### Task 2: site_auth — режим users: страница входа, логин, сессии

**Files:**
- Modify: `siteauth/site_auth.py`
- Test: `tests/test_userauth_login.py`

**Interfaces:**
- Consumes: Task 1 (`studio_store.auth_mode/create_user/find_user_by_email/check_password/set_ir_token`)
- Produces: `_mode()` возвращает `"users"` когда так задано; `_validate_ir_token(token) -> (bool, str)` (переопределяется в тестах); страница `_users_login_page(error="")`

- [ ] **Step 1: тест (fail)** — `tests/test_userauth_login.py`. Харнесс как `tests/test_studio_auth.py`: siteauth на sys.path, tmpdir в INVOKEAI_ROOT, подмена `studio_store._db_path`? Нет — БД идёт в `<tmp>/data/studio.sqlite` через INVOKEAI_ROOT (так делает test_studio_auth). Rec-приложение:

```python
# -*- coding: utf-8 -*-
"""Режим users: страница входа, логин по email/паролю, токен IR, сессия."""
import asyncio, os, sys, tempfile
from pathlib import Path
from urllib.parse import parse_qs

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "siteauth"))
import studio_store, site_auth

tmp = Path(tempfile.mkdtemp(prefix="userauth_login_"))
os.environ["INVOKEAI_ROOT"] = str(tmp)
for k in ("STUDIO_AUTH_MODE", "SITE_PASSWORD", "STUDIO_SESSION_SECRET"):
    os.environ.pop(k, None)
os.environ["STUDIO_AUTH_MODE"] = "users"
os.environ["SITE_PASSWORD"] = "owner-pass"
os.environ["STUDIO_SESSION_SECRET"] = "S" * 40
(tmp / ".env").write_text("STUDIO_AUTH_MODE=users\nSITE_PASSWORD=owner-pass\n"
                          "STUDIO_SESSION_SECRET=" + "S" * 40 + "\n", encoding="utf-8")
# .env-кандидаты: root/.env, root.parent/.env, cwd/.env — у tmp родитель другой tmp,
# cwd не трогаем: env_value() найдёт наш .env первым

class Rec:
    def __init__(self): self.events = []
    async def __call__(self, scope, receive, send):
        async def rcv(): return {"type": "http.request", "body": b"", "more_body": False}
        await site_auth.SiteAuthMiddleware(self)(scope, rcv, self._send)
    async def _send(self, msg): self.events.append(msg)
    @property
    def status(self): return next(m["status"] for m in self.events if m["type"] == "http.response.start")
    def headers(self): return dict((k.decode().lower(), v.decode("latin-1"))
                                   for m in self.events if m["type"] == "http.response.start"
                                   for k, v in m.get("headers", []))
    def body(self): return b"".join(m.get("body", b"") for m in self.events if m["type"] == "http.response.body")

def scope_of(method, path, body=b"", cookie=""):
    h = [(b"content-type", b"application/x-www-form-urlencoded")]
    if cookie: h.append((b"cookie", cookie.encode("latin-1")))
    return {"type": "http", "method": method, "path": path, "headers": h,
            "query_string": b"", "root_path": ""}
async def recv_of(body):
    sent = False
    async def rcv():
        nonlocal sent
        if sent: await asyncio.sleep(3600)
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}
    return rcv

async def call(method, path, body=b"", cookie=""):
    rec = Rec()
    mw = site_auth.SiteAuthMiddleware(rec)
    await mw(scope_of(method, path, cookie=cookie), await recv_of(body), rec._send)
    return rec

def form(**kw): return "&".join(f"{k}={v}" for k, v in kw.items()).encode()

async def main():
    # пользователь без токена и с токеном
    studio_store.init_db()
    studio_store.create_user("user@x.ru", "Юзер", "parol12345", "user")
    studio_store.create_user("tok@x.ru", "Ток", "parol12345", "user")
    studio_store.create_user("rev@x.ru", "Рев", "parol12345", "user")
    studio_store.set_revoked(studio_store.find_user_by_email("rev@x.ru")["user_id"], True)

    # подмена сетевой проверки токена
    saved_val = site_auth._validate_ir_token
    async def fake_ok(t): return True, ""
    async def fake_bad(t): return False, "Токен ImageRouter отклонён — проверьте ключ"
    site_auth._validate_ir_token = fake_ok

    # 1) страница входа
    r = await call("GET", "/auth/login")
    assert r.status == 200 and "Почта" in r.body().decode("utf-8"), r.status

    # 2) неверный пароль
    r = await call("POST", "/auth/login", form(email="user@x.ru", password="nope"))
    assert r.status == 401, r.status

    # 3) верный вход (без токена) -> 303 + кука
    r = await call("POST", "/auth/login", form(email="USER@X.RU", password="parol12345"))
    assert r.status == 303, r.status
    sc = r.headers().get("set-cookie", "")
    assert "devbim_session=" in sc and "HttpOnly" in sc and "Secure" not in sc, sc
    cookie = sc.split(";")[0]

    # 4) сессия открывает страницу, /studio/me отдаёт email/роль, заголовок инжектится
    seen = {}
    class Probe:
        async def __call__(self, scope, receive, send):
            seen.update({k.decode().lower(): v.decode("latin-1") for k, v in scope.get("headers", [])})
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})
    mw = site_auth.SiteAuthMiddleware(Probe())
    await mw(scope_of("GET", "/", cookie=cookie), await recv_of(b""), Rec()._send)
    assert seen.get("x-studio-user", "").startswith("u_"), seen
    rec = Rec(); mw2 = site_auth.SiteAuthMiddleware(Probe())
    await mw2(scope_of("GET", "/api/v1/studio/me", cookie=cookie), await recv_of(b""), rec._send)
    import json
    me = json.loads(rec.body())
    assert me["mode"] == "users" and me["email"] == "user@x.ru" and me["role"] == "user", me

    # 5) API без сессии -> 401; страница без сессии -> 303
    r = await call("GET", "/api/v1/images/")
    assert r.status == 401, r.status
    r = await call("GET", "/")
    assert r.status == 303 and "/auth/login" in r.headers().get("location", ""), r.status

    # 6) заблокированный
    r = await call("POST", "/auth/login", form(email="rev@x.ru", password="parol12345"))
    assert r.status == 403, r.status

    # 7) токен: отклонён -> 401, принят -> сохранён
    site_auth._validate_ir_token = fake_bad
    r = await call("POST", "/auth/login", form(email="tok@x.ru", password="parol12345", token="sk-bad"))
    assert r.status == 401 and "Токен" in r.body().decode("utf-8"), r.status
    site_auth._validate_ir_token = fake_ok
    r = await call("POST", "/auth/login", form(email="tok@x.ru", password="parol12345", token="sk-good"))
    assert r.status == 303, r.status
    assert studio_store.get_ir_token(studio_store.find_user_by_email("tok@x.ru")["user_id"]) == "sk-good"

    # 8) вход владельца: пустая почта + SITE_PASSWORD
    r = await call("POST", "/auth/login", form(email="", password="owner-pass"))
    assert r.status == 303 and "devbim_session=" in r.headers().get("set-cookie", ""), r.status

    # 9) logout чистит куку
    r = await call("GET", "/auth/logout", cookie=cookie)
    assert r.status == 303 and "Max-Age=0" in r.headers().get("set-cookie", ""), r.status

    # 10) без секрета сессии вход запрещён (fail-closed)
    os.environ["STUDIO_SESSION_SECRET"] = ""
    (tmp / ".env").write_text("STUDIO_AUTH_MODE=users\nSITE_PASSWORD=owner-pass\n", encoding="utf-8")
    r = await call("POST", "/auth/login", form(email="user@x.ru", password="parol12345"))
    assert r.status == 500 and "STUDIO_SESSION_SECRET" in r.body().decode("utf-8"), r.status
    site_auth._validate_ir_token = saved_val
    print("OK")

asyncio.run(main())
```

- [ ] **Step 2: прогнать — падение** (страница входа отдаёт старую password-форму): `venv\Scripts\python.exe tests\test_userauth_login.py`
- [ ] **Step 3: реализация в `siteauth/site_auth.py`**

1. `_mode()` → `return studio_store.auth_mode()`.
2. CSS страницы `_page()`: селектор `input[type=password]` расширить до `input[type=password],input[type=text],input[type=email]` (и для `:focus`).
3. Новая страница (рядом с `_admin_login_page`):

```python
def _users_login_page(error: str = "") -> bytes:
    err = f'<div class="err">{error}</div>' if error else ""
    return _page("Вход", f"""
{err}<form method="POST" action="/auth/login">
<label for="email">Почта</label>
<input id="email" type="email" name="email" autocomplete="username" autofocus>
<label for="password">Пароль</label>
<input id="password" type="password" name="password" autocomplete="current-password">
<label for="token">Токен ImageRouter <span style="color:#5A6474">(необязательно, если уже сохранён)</span></label>
<input id="token" type="password" name="token" autocomplete="off" placeholder="sk-...">
<button type="submit">Войти</button></form>
<p style="font-size:12px;color:#5A6474;margin-top:14px">Забыли пароль или токен?
Обратитесь к администратору студии.</p>""")
```

4. Проверка токена (после `_session_cookie`):

```python
async def _validate_ir_token(token: str) -> tuple[bool, str]:
    """Проверка токена на апстриме ImageRouter: (ok, ошибка). Сетевой сбой/5xx
    не запирают пользователя (токен сохраняется с предупреждением в лог)."""
    def _call():
        import requests
        return requests.post("https://api.imagerouter.io/v1/auth/test",
                             headers={"Authorization": f"Bearer {token}"}, timeout=15)
    try:
        resp = await asyncio.to_thread(_call)
    except Exception as e:  # noqa: BLE001
        print(f"[studio] IR token check unreachable: {e}", file=sys.stderr)
        return True, ""
    if resp.status_code == 200:
        return True, ""
    if 400 <= resp.status_code < 500:
        return False, "Токен ImageRouter отклонён — проверьте ключ"
    print(f"[studio] IR token check HTTP {resp.status_code}", file=sys.stderr)
    return True, ""
```

5. `_session_cookie`: убрать `Secure` (туннель может терминироваться в http) — `f"{COOKIE_NAME}={v}; Max-Age={ttl}; Path=/; HttpOnly; SameSite=Lax"`.
6. `_session_user`: первой строкой `secret = _session_secret(); if not secret: return None`; использовать его в вызове.
7. Новый обработчик в классе (после `_handle_admin_login`):

```python
    async def _handle_users_login(self, scope, receive, send) -> None:
        if scope.get("method", "GET").upper() == "GET":
            await _send_html(send, 200, _users_login_page())
            return
        body = await _read_body(receive)
        form = parse_qs(body.decode("utf-8", "replace"))
        email = (form.get("email") or [""])[0].strip()
        password = (form.get("password") or [""])[0]
        token = (form.get("token") or [""])[0].strip()
        if not _session_secret():
            await _send_html(send, 500, _users_login_page(
                "Сервер не настроен: задайте STUDIO_SESSION_SECRET в .env и перезапустите"))
            return
        if not email:  # вход владельца: SITE_PASSWORD, почта пустая
            if password and password == _site_password():
                await _redirect(send, "/", set_cookie=_session_cookie(studio_store.ADMIN_LOCAL))
            else:
                await _send_html(send, 401, _users_login_page("Неверный пароль администратора"))
            return
        studio_store.init_db()
        u = studio_store.find_user_by_email(email)
        if not u or not studio_store.check_password(u["user_id"], password):
            await asyncio.sleep(0.3)
            await _send_html(send, 401, _users_login_page("Неверная почта или пароль"))
            return
        if u.get("revoked"):
            await _send_html(send, 403, _users_login_page("Учётная запись заблокирована"))
            return
        if token:
            ok, err = await _validate_ir_token(token)
            if not ok:
                await _send_html(send, 401, _users_login_page(err))
                return
            studio_store.set_ir_token(u["user_id"], token)
        await _redirect(send, "/", set_cookie=_session_cookie(u["user_id"]))
```

8. Точки ветвления в `__call__`:
   - websocket: `ok = (not _expired()) and (_session_user(scope) if _mode() in ("sso", "users") else _legacy_cookie_ok(scope))`
   - logout: `if _mode() in ("sso", "users"):` чистить `COOKIE_NAME`, иначе легаси.
   - секция после `if _mode() == "password": ... return` — сейчас `# ===== sso =====`; оставить как общую для sso/users, но в `LOGIN_PATH`:

```python
        if path == LOGIN_PATH:
            if _mode() == "users":
                await self._handle_users_login(scope, receive, send)
            else:
                await self._handle_admin_login(scope, receive, send)
            return
```

   - `_handle_me`: `"mode": _mode()` вместо жёсткого `"sso"`.
9. `room_for_environ` уже поправлен в Task 1 (sockets-комнаты работают).

- [ ] **Step 4: прогон — OK**: `venv\Scripts\python.exe tests\test_userauth_login.py`
- [ ] **Step 5: регресс**: `tests\test_studio_auth.py`, `tests\test_site_auth.py`, `tests\test_studio_ownership.py` — OK
- [ ] **Step 6: commit** `git add siteauth/site_auth.py tests/test_userauth_login.py && git commit -m "feat(userauth): режим users — вход по email/паролю + токен ImageRouter, кука без Secure, fail-closed секрет"`

---

### Task 3: site_auth — админ-панель: создание пользователей, пароль, токен

**Files:**
- Modify: `siteauth/site_auth.py` (`_admin_panel`, `_ADMIN_PAGE`)
- Test: `tests/test_userauth_admin.py`

**Interfaces:**
- Consumes: Task 1 CRUD, Task 2 `_validate_ir_token`
- Produces: `GET /admin/api/users` теперь отдаёт всех кроме `admin-local` + `has_password`/`has_token`; `POST /admin/api/users` (create), `POST /admin/api/users/{id}/password`, `POST /admin/api/users/{id}/token`

- [ ] **Step 1: тест (fail)** — `tests/test_userauth_admin.py` (харнесс Task 2, вынести общие Rec/scope в файл повторно — дублирование допустимо, тесты независимы):

Сценарии: админ-сессия (вход SITE_PASSWORD) → `POST /admin/api/users {"email":"new@x.ru","password":"parol12345","role":"user"}` → 200; повтор того же email → 409; кривой пароль (5 симв.) → 422; кривая роль → 422; `POST .../password {"password":"newpass123"}` → 200 и `check_password` True; `POST .../token {"token":"sk-zz"}` (с подменённым `_validate_ir_token`→ok) → 200, `get_ir_token=="sk-zz"`; `{"token":""}` → очистка; не-админ (сессия обычного пользователя) на `/admin/api/users` → 403; список содержит `has_password`/`has_token` и НЕ содержит пароль/токен целиком.

- [ ] **Step 2: прогнать — падение** (404 на новых эндпоинтах)
- [ ] **Step 3: реализация**

`_admin_panel`, блок `path == "/admin/api/users"`:
- GET: убрать пропуск `u["role"] == "admin"` (оставить только `ADMIN_LOCAL`); после `u["effective_role"]=...` добавить `u["has_password"] = bool(u.get("password_hash")); u["has_token"] = bool(u.get("ir_token"))` и удалить сами `password_hash`/`ir_token` из словаря (`u.pop("password_hash", None)` и т.д.).
- Новый блок `if path == "/admin/api/users" and method == "POST":` — `json.loads(body)`; `try: u = studio_store.create_user(email=..., name=data.get("name") or "", password=..., role=data.get("role") or "user", ir_token=data.get("token") or None)`; `ValueError` → 409 при «уже есть», иначе 422 с текстом; пароль `<8` симв. → 422; при токене — `ok, err = await _validate_ir_token(token)`, не ok → 400; ответ `{"user_id": ..., "email": ...}`.
- `m = re.match(r"^/admin/api/users/([^/]+)/(role|revoke|password|token)$", path)` — расширить; ветки:

```python
            if m.group(2) == "password":
                pw = str(data.get("password") or "")
                if len(pw) < 8:
                    await _send_json(send, {"detail": "password must be >= 8 chars"}, status=422)
                    return
                studio_store.set_password(uid, pw)
            elif m.group(2) == "token":
                tok = str(data.get("token") or "").strip()
                if tok:
                    ok, err = await _validate_ir_token(tok)
                    if not ok:
                        await _send_json(send, {"detail": err}, status=400)
                        return
                studio_store.set_ir_token(uid, tok or None)
            elif m.group(2) == "role":
                ... (прежняя логика)
```

`_ADMIN_PAGE`: перед таблицей форма создания:

```html
<h2 style="font-size:15px;margin-top:28px">Создать пользователя</h2>
<form id="f" style="margin-top:10px;display:flex;gap:8px;flex-wrap:wrap">
  <input name="email" placeholder="почта" required>
  <input name="name" placeholder="имя">
  <input name="password" placeholder="пароль (8+ символов)" required>
  <select name="role"><option value="user">user</option><option value="admin">admin</option></select>
  <input name="token" placeholder="токен ImageRouter (необязательно)">
  <button type="submit">Создать</button>
</form>
```

CSS-правка для `input` (сейчас стилизованы только select/button — добавить `input { background:#14161A; color:#E6EAF2; border:1px solid #2A2E37; border-radius:6px; padding:5px 8px; font-size:12.5px; }`).
JS: `document.getElementById('f').onsubmit = e => { e.preventDefault(); const fd = new FormData(e.target); const b = {}; fd.forEach((v,k)=>{ if(v) b[k]=v; }); fetch('/admin/api/users', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)}).then(r=>r.json().then(j=>({s:r.status,j}))).then(({s,j})=>{ if(s>=400){alert(j.detail||('HTTP '+s));}else{location.reload();} }); };`
В строке таблицы кнопки: `Пароль…` → `const pw=prompt('Новый пароль (8+ символов)'); if(pw) post('.../password',{password:pw})`; `Токен…` → `const t=prompt('Токен ImageRouter (пусто = очистить)'); if(t!==null) post('.../token',{token:t})`. Колонка «Токен» в таблице: `u.has_token ? 'есть' : '—'`.

- [ ] **Step 4: прогон — OK**; **Step 5: регресс** `tests\test_studio_ownership.py` (админ-панель) — OK
- [ ] **Step 6: commit** `git add siteauth/site_auth.py tests/test_userauth_admin.py && git commit -m "feat(userauth): админ-панель — создание пользователей, смена пароля/токена"`

---

### Task 4: user_manager.py — CLI

**Files:**
- Create: `user_manager.py` (корень, по образцу `company_manager.py`)
- Test: `tests/test_userauth_cli.py`

**Interfaces:**
- Consumes: Task 1 CRUD, `company_manager.gen_password()` (импорт)
- Produces: `python user_manager.py add|list|set-password|set-token|role|revoke|restore [--root <INVOKEAI_ROOT>]`

- [ ] **Step 1: тест (fail)** — `tests/test_userauth_cli.py`: подмена `sys.argv` и вызов `user_manager.main()` в tmp-корне; проверки: `add a@x.ru --password pass12345` создаёт (`find_user_by_email`), `add` без `--password` печатает сгенерированный пароль и он подходит (`check_password`), `list` печатает email, `set-token`/`role`/`revoke`/`restore` меняют состояние (assert по store), `add` дубликата → exit!=0/ValueError пойман.

- [ ] **Step 2: падение** (нет модуля)
- [ ] **Step 3: реализация**

```python
# -*- coding: utf-8 -*-
"""CLI управления пользователями студии (многопользовательский режим users).

Работает с <INVOKEAI_ROOT>/data/studio.sqlite. Ключ --root задаёт INVOKEAI_ROOT
(дефолт ./data — основной экземпляр; для компаний: companies/<код>/data).

Примеры:
    python user_manager.py add ivan@mail.ru --name Иван --role user
    python user_manager.py add ivan@mail.ru --password "МойПароль123" --token sk-...
    python user_manager.py list
    python user_manager.py set-password ivan@mail.ru
    python user_manager.py set-token ivan@mail.ru sk-...
    python user_manager.py role ivan@mail.ru admin
    python user_manager.py revoke ivan@mail.ru | restore ivan@mail.ru
"""
import argparse
import os
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE / "siteauth"))
import studio_store  # noqa: E402
from company_manager import gen_password  # noqa: E402


def _init(root: str | None) -> None:
    os.environ["INVOKEAI_ROOT"] = str(Path(root) if root else BASE / "data")
    studio_store.init_db()


def _by_email(email: str) -> dict:
    u = studio_store.find_user_by_email(email)
    if not u:
        sys.exit(f"Пользователь не найден: {email}")
    return u


def main() -> None:
    p = argparse.ArgumentParser(description="Управление пользователями DevBIM Image Studio")
    p.add_argument("--root", default=None, help="INVOKEAI_ROOT (дефолт ./data)")
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add", help="создать пользователя")
    a.add_argument("email"); a.add_argument("--name", default="")
    a.add_argument("--role", choices=("user", "admin"), default="user")
    a.add_argument("--password", help="без флага — генерируется и печатается")
    a.add_argument("--token", default=None, help="токен ImageRouter")
    s = sub.add_parser("list")
    s = sub.add_parser("set-password"); s.add_argument("email"); s.add_argument("--password")
    s = sub.add_parser("set-token"); s.add_argument("email"); s.add_argument("token")
    s = sub.add_parser("role"); s.add_argument("email"); s.add_argument("role", choices=("user", "admin"))
    s = sub.add_parser("revoke"); s.add_argument("email")
    s = sub.add_parser("restore"); s.add_argument("email")
    args = p.parse_args()
    _init(args.root)

    if args.cmd == "add":
        pw = args.password or gen_password()
        try:
            u = studio_store.create_user(args.email, args.name, pw, args.role, args.token)
        except ValueError as e:
            sys.exit(f"Ошибка: {e}")
        print(f"Создан пользователь: {u['email']} (роль {u['role']}, id {u['user_id']})")
        if not args.password:
            print(f"Сгенерированный пароль: {pw}")
        print("Передайте пользователю пароль и его токен ImageRouter.")
    elif args.cmd == "list":
        rows = studio_store.list_users()
        if not rows:
            print("(пользователей нет)")
        for u in rows:
            st = "ЗАБЛОКИРОВАН" if u["revoked"] else ""
            tok = "токен есть" if u.get("ir_token") else "токена нет"
            print(f"{u['email']:<32} {u['role']:<6} {tok:<12} {st} {u['name']}")
    elif args.cmd == "set-password":
        u = _by_email(args.email)
        pw = args.password or gen_password()
        studio_store.set_password(u["user_id"], pw)
        print(f"Пароль обновлён: {pw}")
    elif args.cmd == "set-token":
        u = _by_email(args.email)
        studio_store.set_ir_token(u["user_id"], None if args.token == "-" else args.token)
        print("Токен обновлён." if args.token != "-" else "Токен очищен.")
    elif args.cmd == "role":
        u = _by_email(args.email)
        studio_store.set_role_override(u["user_id"], args.role)
        print(f"Роль (override): {args.role}")
    elif args.cmd == "revoke":
        u = _by_email(args.email); studio_store.set_revoked(u["user_id"], True); print("Заблокирован.")
    elif args.cmd == "restore":
        u = _by_email(args.email); studio_store.set_revoked(u["user_id"], False); print("Разблокирован.")


if __name__ == "__main__":
    main()
```

(Внимание: `set_role_override` в Task 1 не трогали — он уже есть; role через override согласован с `effective_role`.)
Тест вызывает `user_manager.main()` в try/except SystemExit.

- [ ] **Step 4: прогон — OK**; **Step 5: commit** `git add user_manager.py tests/test_userauth_cli.py && git commit -m "feat(userauth): CLI user_manager.py — add/list/set-password/set-token/role/revoke"`

---

### Task 5: imagerouter — effective_key (персональный токен)

**Files:**
- Modify: `imagerouter/imagerouter_router.py`
- Test: `tests/test_userauth_token.py`

**Interfaces:**
- Consumes: Task 1 (`studio_store.get_user/effective_role/get_ir_token`)
- Produces: `effective_key(studio_user) -> str | None` (импортируется threed в Task 7); поведение `GET /status`, `GET /credits` с `request`

- [ ] **Step 1: тест (fail)** — `tests/test_userauth_token.py`. Импорт: `sys.path.insert(0, imagerouter)`; `import imagerouter_router` (под venv-питоном invokeai импортируется); подмена `sys.modules["invokeai.app.api.routers"] = SimpleNamespace(studio_store=siteauth-копия)` ДО вызовов (ленивые импорты); tmp INVOKEAI_ROOT; `imagerouter_router.get_config = lambda: SimpleNamespace(root_path=str(tmp))`.

Сценарии: user с токеном → `effective_key(uid)=="sk-u"`; user без токена → `None` (глобальный НЕ подставляется: `os.environ["IMAGEROUTER_API_KEY"]="sk-global"`); admin с токеном → свой; admin без токена → `"sk-global"`; `admin-local` → `"sk-global"`; `None` → `"sk-global"`; `_validate`-функция логина (site_auth) — мок `requests.post` через подмену модуля `requests` в `sys.modules` на заглушку с тремя сценариями (200/401/Timeout).

- [ ] **Step 2: падение** (`effective_key` нет)
- [ ] **Step 3: реализация в `imagerouter_router.py`**

После `_load_key()`:

```python
def _studio_store():
    try:
        from invokeai.app.api.routers import studio_store
    except ImportError:  # дерево проекта (тесты)
        import studio_store
    return studio_store


def effective_key(studio_user: "str | None") -> Optional[str]:
    """Ключ ImageRouter для запроса от имени пользователя студии.

    Персональный токен приоритетен. Обычному пользователю (role=user) без
    токена глобальный ключ НЕ подставляется — иначе тратятся кредиты
    владельца; генерация завершится понятной ошибкой. admin / admin-local
    без своего токена работают на глобальном ключе."""
    if studio_user and studio_user != "admin-local":
        try:
            store = _studio_store()
            u = store.get_user(studio_user)
            if u:
                tok = (u.get("ir_token") or "").strip()
                if tok:
                    return tok
                if (store.effective_role(studio_user) or "user") != "admin":
                    return None
        except Exception:  # noqa: BLE001 — БД недоступна: работаем на глобальном
            pass
    return _load_key()


def _key_or_401(studio_user: "str | None") -> str:
    key = effective_key(studio_user)
    if not key:
        if studio_user and studio_user != "admin-local":
            raise HTTPException(
                status_code=401,
                detail="Персональный токен ImageRouter не задан — обратитесь к администратору.")
        raise HTTPException(status_code=401, detail="API key is not configured")
    return key
```

Замены:
- `_handle_canvas_generation` (стр. ~1457) и `_handle_upscale_generation` (стр. ~1843): `key = _load_key()` → `key = effective_key(studio_user)`; сообщения об отсутствии: в canvas-ветке — если `not key and studio_user and studio_user != "admin-local"` → `_IRClientError("Персональный токен ImageRouter не задан — обратитесь к администратору.", 401)`, иначе прежнее сообщение. (В этих синхронных handler'ах свой raise вместо `_key_or_401`, т.к. формат ошибок `_IRClientError`.)
- `_auth_headers()` получает опциональный параметр: `def _auth_headers(studio_user: "str | None" = None) -> dict[str, str]: key = effective_key(studio_user); ...` — вызовы без аргумента сохраняют прежнее поведение.
- `GET /credits`: `def get_credits(request: "Request | None" = None) -> Any:` → `u = request.headers.get("x-studio-user") if request else None; resp = requests.get(CREDITS_URL, headers=_auth_headers(u), ...)` (глобальный ключ остаётся, если пользователя нет).
- `GET /status`: `def get_status(request: "Request | None" = None)`: добавить `u`; если у пользователя есть токен — `hint` по нему и `key_source: "user"`.
- Prompt Enhancer (`POST`-эндпоинт с CHAT_COMPLETIONS_URL, ~стр. 1000–1100, имя уточнить по коду — `_enhance`/`enhance_prompt`): добавить `request: "Request | None" = None`, `u = request.headers.get("x-studio-user") if request else None`, `key = effective_key(u)`, при `not key` → HTTPException 401 с текстом «Персональный токен…» (как в `_key_or_401`). Импорт `Request` уже есть в файле (проверить; иначе добавить `from fastapi import Request`).

- [ ] **Step 4: прогон — OK**; **Step 5: регресс** `tests\test_cloud_nodes.py`, `tests\test_imagerouter*.py` (какие есть) — OK
- [ ] **Step 6: commit** `git add imagerouter/imagerouter_router.py tests/test_userauth_token.py && git commit -m "feat(userauth): effective_key — персональный токен ImageRouter (user без токена не падает на глобальный ключ)"`

---

### Task 6: ifc/pdf — физические per-user подпапки

**Files:**
- Modify: `ifc/ifc_router.py`, `pdf/pdf_router.py`
- Test: `tests/test_userauth_files.py`

**Interfaces:**
- Consumes: Task 1 (`studio_store.get_user/list_users`), существующий `_studio_user`/`_studio_visible`
- Produces: `user_dir(user_id) -> Path | None` (имя каталога = слаг email); список отдаёт `owner` (email) для админа; API-имена остаются плоскими

- [ ] **Step 1: тест (fail)** — `tests/test_userauth_files.py`. Харнесс как `test_pdf_router.py` (`pdf_router.get_config = lambda: SimpleNamespace(root_path=str(tmp))`) + подмена `sys.modules["invokeai.app.api.routers"]` на SimpleNamespace(studio_store=siteauth-копия) и создание пользователей в tmp-БД. Request-заглушка: `SimpleNamespace(headers={"x-studio-user": uid})`.

Сценарии (для ifc; pdf зеркально):
1. upload пользователя A (`uid_a`) → файл лежит в `tmp/ifc/<email-a>/f.ifc`; в корне его нет.
2. `list` A видит свой файл; пользователя B — не видит; admin-local видит корень (пусто) и не видит файлы A? — НЕТ: админ видит всё → видит и файл A (с `owner == email-a`).
3. `file/{name}` B → 404; A → 200; админ → 200.
4. админ (`uid_admin`, role admin) upload → файл в корне `tmp/ifc/x.ifc`.
5. легаси-файл в корне без тега: A не видит в list, `file` → 404; админ видит.
6. легаси-файл в корне, тегированный A (studio_store.tag("ifc", name, uid_a)) → A видит в list и открывает.
7. delete: A удаляет свой; B удалить файл A → 404; админ удаляет корневой.
8. `user_dir` на экзотике: email `"Иван Петров@Майл.ру"` → слаг из `[a-z0-9@._+-]` (кириллица/пробел → `_`), без точек по краям.
9. без `x-studio-user` (password-режим): upload/list в корне — прежнее поведение.

- [ ] **Step 2: падение** (`user_dir` нет)
- [ ] **Step 3: реализация** — в оба роутера (код одинаков по форме; kind и тексты различаются). Для `ifc_router.py`:

```python
_DIR_UNSAFE_RE = re.compile(r"[^a-z0-9@._+-]+")


def user_dir(user_id: "str | None") -> Path | None:
    """Подпапка пользователя (имя = слаг email); None -> корень хранилища
    (admin-local, password-режим). Каталог создаётся при первом upload."""
    if not user_id or user_id == "admin-local":
        return None
    try:
        from invokeai.app.api.routers import studio_store
    except ImportError:
        import studio_store
    u = studio_store.get_user(user_id)
    if not u or not u.get("email"):
        return None
    slug = _DIR_UNSAFE_RE.sub("_", u["email"].strip().lower())[:80].strip(".")
    return _store_dir() / (slug or user_id)


def _is_admin(user_id: "str | None") -> bool:
    if user_id is None:
        return False
    try:
        from invokeai.app.api.routers import studio_store
    except ImportError:
        import studio_store
    return studio_store.effective_role(user_id) == "admin"


def _all_dirs() -> list[Path]:
    """Корень + подпапки пользователей (для админа)."""
    root = _store_dir()
    return [root] + sorted(p for p in root.iterdir() if p.is_dir())


def _safe_in(dir_: Path, name: str) -> Path:
    """Как _safe_path, но в заданном каталоге (имя уже проверено SAFE_NAME_RE)."""
    return dir_ / name


def _resolve(request: Request, name: str) -> Path:
    """Путь к файлу по плоскому имени для данного запроса: своя подпапка ->
    корень; для админа: корень -> подпапки по алфавиту. 404 если не найден
    или не положен."""
    _safe_path(name)  # валидация имени (без построения пути)
    u = _studio_user(request)
    if u is not None and _is_admin(u):
        for d in _all_dirs():
            p = d / name
            if p.is_file():
                return p
        raise HTTPException(status_code=404, detail="Файл не найден")
    d = user_dir(u)
    if d is not None:
        p = d / name
        if p.is_file():
            return p
    p = _store_dir() / name  # легаси-корень: по прежним правилам видимости
    if p.is_file() and _studio_visible(request, "ifc", name):
        return p
    raise HTTPException(status_code=404, detail="Файл не найден")
```

`_safe_path` оставить как есть (валидация), но строить итоговый путь через `user_dir`. `upload_model`: `target = (user_dir(u) or _store_dir()); if u and user_dir(u): user_dir(u).mkdir(parents=True, exist_ok=True); path = _safe_path(name)` — заменить последнюю строку `_safe_path` на: `name_ok = _safe_path(name).name` (валидация) и `path = target / name_ok`. Тег владения — прежний.
`list_models`:

```python
def list_models(request: Request) -> dict:
    u = _studio_user(request)
    admin = u is not None and _is_admin(u)
    if admin:
        from invokeai.app.api.routers import studio_store  # owner -> email
        emails = {x["user_id"]: x["email"] for x in studio_store.list_users()}
        dirs, owner_of = _all_dirs(), lambda p: emails.get(
            studio_store.owner("ifc", p.name))
    else:
        d = user_dir(u)
        dirs = ([d, _store_dir()] if d else [_store_dir()])
    items: dict[str, dict] = {}
    for i, dr in enumerate(dirs):
        for p in sorted(dr.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
            if not p.is_file() or not p.name.lower().endswith(ALLOWED_EXT):
                continue
            if not admin and dr == _store_dir() and not _studio_visible(request, "ifc", p.name):
                continue  # корень: только свои легаси-файлы
            if p.name in items and not admin:
                continue  # своя подпапка приоритетнее корня
            it = {"name": p.name, "size": p.stat().st_size,
                  "modified": int(p.stat().st_mtime)}
            if admin:
                it["owner"] = owner_of(p) if dr != _store_dir() else (
                    emails.get(studio_store.owner("ifc", p.name)))
            items.setdefault(p.name, it)
    out = sorted(items.values(), key=lambda x: x["modified"], reverse=True)
    return {"models": out}
```

`get_model`/`delete_model`: заменить `path = _safe_path(name)` + `path.is_file()` на `path = _resolve(request, name)` (видимость уже внутри; для delete — `path.unlink()`).

`pdf_router.py` — то же самое с kind `"pdf"`, `ALLOWED_EXT = (".pdf",)`, ключ списка `"docs"`, тексты «Документ».

- [ ] **Step 4: прогон — OK**; **Step 5: регресс** `tests\test_pdf_router.py` — OK (без пользователя поведение прежнее)
- [ ] **Step 6: commit** `git add ifc/ifc_router.py pdf/pdf_router.py tests/test_userauth_files.py && git commit -m "feat(userauth): ifc/pdf — физические подпапки data/<kind>/<email>/, плоские имена в API, owner для админа"`

---

### Task 7: threed — per-user каталог, тег IFC-файла, персональный ключ VLM

**Files:**
- Modify: `threed/threed_router.py`
- Test: `tests/test_userauth_threed.py`

**Interfaces:**
- Consumes: Task 5 `effective_key`, Task 6 паттерн `user_dir` (локальная копия — threed не импортирует ifc_router)
- Produces: `_generate_impl(..., ir_user=None, out_dir=None)`; VLM-вызовы идут с ключом пользователя; готовый IFC тегируется `tag("ifc", name, user)`

- [ ] **Step 1: тест (fail)** — `tests/test_userauth_threed.py`: tmp-БД + подмена `sys.modules["invokeai.app.api.routers"]`; проверить чистые функции: `user_out_dir(uid)` → `tmp/ifc/<email-slug>`; `admin-local`/None → `tmp/ifc`; тегирование: смоделировать результат (вызов внутренней точки тегирования либо прямой вызов студийного `tag` из роутера после «сборки» — тестировать фактическую функцию-помощник `_tag_ifc_result(name, user)`, которую добавляем); ключ: `_call_vlm` с monkeypatch `imagerouter.effective_key`-заглушкой (через подмену `sys.modules["invokeai.app.api.routers.imagerouter"]`) — пользовательский ключ уходит в заголовок (мок requests.post перехватывает headers).

- [ ] **Step 2: падение**
- [ ] **Step 3: реализация**

1. Локальный helper каталога (по образцу Task 6, kind не нужен):

```python
_DIR_UNSAFE_RE = re.compile(r"[^a-z0-9@._+-]+")

def user_out_dir(user_id: "str | None") -> Path:
    """Каталог IFC-результатов пользователя (data/ifc/<email-слаг>); без
    пользователя/admin-local — общий корень data/ifc."""
    if not user_id or user_id == "admin-local":
        return _ifc_dir()
    try:
        from invokeai.app.api.routers import studio_store
    except ImportError:
        import studio_store
    u = studio_store.get_user(user_id)
    if not u or not u.get("email"):
        return _ifc_dir()
    slug = _DIR_UNSAFE_RE.sub("_", u["email"].strip().lower())[:80].strip(".")
    d = _ifc_dir() / (slug or user_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _tag_ifc_result(name: str, user_id: "str | None") -> None:
    """Владение готовым IFC-файлом: пользователь видит результат 3D-генерации
    во вкладке IFC (раньше тегировался только job)."""
    if not user_id or not name:
        return
    try:
        from invokeai.app.api.routers import studio_store
    except ImportError:
        import studio_store
    studio_store.tag("ifc", name, user_id)
```

2. `_call_vlm(...)`: добавить параметр `ir_user: "str | None" = None`; импорт: `from invokeai.app.api.routers.imagerouter import CHAT_COMPLETIONS_URL, effective_key`; `key = effective_key(ir_user)`; при `not key` — `ValueError("Персональный токен ImageRouter не задан — обратитесь к администратору.")`. Протянуть `ir_user` через все вызовы `_call_vlm`/`_vlm_counted` внутри `_generate_impl` (сигнатура `_generate_impl(scenario, prompt, image, progress, ir_user=None, out_dir=None)`; дефолт `out_dir=None → _ifc_dir()` — строка 474 уже так; заменить чтение `user`-контекста). ПРИМЕЧАНИЕ: если `_vlm_counted` имеет фикс. сигнатуру — расширить `**`/kw.
3. `generate` (стр. ~929): после `u = _studio_user(request)`: `job["user"] = u`; `out_dir = user_out_dir(u)`; поток: `threading.Thread(target=_run_job, args=(job, body.prompt, image), ...)` — вычислить `ir_user, out_dir` здесь и передать: `_run_job(job, prompt, image)` → внутри вызывает `_generate_impl(..., ir_user=job.get("user"), out_dir=job.get("out_dir"))`; записать `job["out_dir"] = str(out_dir)`.
4. Точка тегирования: в `_generate_impl` после выбора `best` (стр. ~835, рядом с формированием `res`): `_tag_ifc_result(ifc_path.name, ir_user)`.
5. Диагностический дамп `_threed_last.json` — прежний (корень ifc, не трогаем: он не в list из-за расширения .json).

- [ ] **Step 4: прогон — OK**; **Step 5: регресс** `venv\Scripts\python.exe tests\test_threed_router.py` (и соседние test_threed*) — OK
- [ ] **Step 6: commit** `git add threed/threed_router.py tests/test_userauth_threed.py && git commit -m "feat(userauth): threed — per-user каталог IFC-результатов, тег владения файлом, персональный ключ VLM"`

---

### Task 8: баннер (чип пользователя в users-режиме) + setup_site_auth (секрет сессии)

**Files:**
- Modify: `devbim_banner.js` (стр. ~104), `setup_site_auth.py` (`ensure_env_password`)
- Test: ручная проверка `node --check devbim_banner.js`; прогон `tests\test_site_auth.py` (setup не ломает), `tests\test_studio_gzip.py`

**Interfaces:** — (UI/деплой-обвязка)

- [ ] **Step 1: правка баннера**

`if (!d || d.mode !== 'sso' || !d.user_id) return;` →
`if (!d || (d.mode !== 'sso' && d.mode !== 'users') || !d.user_id) return;`
Комментарий над блоком дополнить: «sso и users-режимы».

- [ ] **Step 2: правка `setup_site_auth.py`**

`ensure_env_password()`: `import secrets`; в `defaults` НЕ добавлять (значение уникально); после цикла:

```python
    if "STUDIO_SESSION_SECRET" not in have:
        text += f"STUDIO_SESSION_SECRET={secrets.token_hex(32)}\n"
        print("В .env добавлен сгенерированный STUDIO_SESSION_SECRET")
```

- [ ] **Step 3: проверки**: `node --check devbim_banner.js` → нет вывода/ошибок; `venv\Scripts\python.exe tests\test_studio_gzip.py tests\test_site_auth.py` → OK
- [ ] **Step 4: commit** `git add devbim_banner.js setup_site_auth.py && git commit -m "feat(userauth): чип пользователя в users-режиме; автогенерация STUDIO_SESSION_SECRET при деплое"`

---

### Task 9: деплой, E2E-смоук, HANDOFF/AGENTS, включение режима

**Files:**
- Modify: `HANDOFF.md`, `AGENTS.md`, `.env` (не в git)
- Test: полный прогон тестов + живой смоук на перезапущенном сервере

- [ ] **Step 1: полный прогон**: `for f in tests\test_*.py` — все OK (особенно `test_userauth_*`, `test_studio_*`, `test_pdf_router`, `test_ifc_sections`, `test_threed*`).
- [ ] **Step 2: деплой сетапами** (идемпотентно):
  `venv\Scripts\python.exe setup_imagerouter.py && venv\Scripts\python.exe setup_ifcviewer.py && venv\Scripts\python.exe setup_pdfviewer.py && venv\Scripts\python.exe setup_threed.py && venv\Scripts\python.exe setup_site_auth.py`
- [ ] **Step 3: включить режим**: в корневом `.env` — `STUDIO_AUTH_MODE=users` (секрет добавит setup_site_auth); компании не трогать.
- [ ] **Step 4: перезапуск + смоук**: `launch\_restart_server.ps1`; затем `curl`-смоук:
  - `GET /auth/login` → 200, форма с «Почта»;
  - `POST /auth/login` (пустая почта + SITE_PASSWORD) → 303 + кука;
  - по куке `GET /api/v1/studio/me` → `{"mode":"users","role":"admin"}` (admin@local);
  - `python user_manager.py add test@x.ru --password testpass1` → вход им → me → role user;
  - `POST /api/v1/pdf/upload` под пользователем → файл в `data/pdf/test@x.ru/`; list под ним видит, под админом — с owner.
  - Аккуратно: не тратить кредиты IR (генерацию не дёргать; `/status` достаточно: `key_source`).
- [ ] **Step 5: HANDOFF.md** — новая секция «Многопользовательский режим users (07.10.2026)» (вход, выдача токенов, user_manager, папки, грабли: user без токена не видит генерацию, Secure убран из куки, admin видит все папки). Обновить AGENTS.md: строка про `user_manager.py` и режим users в siteauth-описании.
- [ ] **Step 6: финальный commit** `git add HANDOFF.md AGENTS.md && git commit -m "docs: многопользовательский режим users — HANDOFF/AGENTS"`.

## Self-review

- Покрытие спеки: вход (T2), токен IR (T2/T5), аккаунты (T3/T4), изоляция файлов (T6/T7), картинки — владение уже есть (T2 включает инжект), баннер/деплой (T8/T9), миграция/развёртывание (T1 миграция, T9). Открытые вопросы спеки задач не требуют.
- Типы: `effective_key(str|None)->str|None` одинаков в T5/T7; `user_dir` (T6) и `user_out_dir` (T7) — имена разные осознанно (разные модули), slug-логика идентична.
- Регресс-задачи включены в каждый таск; password/sso контракты зафиксированы существующими тестами.
