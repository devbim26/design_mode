# -*- coding: utf-8 -*-
"""Оверлей-хранилище студии: пользователи SSO, владение контентом, сессии, сокет-комнаты.

Разворачивается setup_site_auth.py в venv (invokeai/app/api/routers/studio_store.py).
Файл БД: <INVOKEAI_ROOT>/data/studio.sqlite (WAL). Чтения при сбое БД -> None
(fail-closed: нет пользователя/владельца -- нет доступа), записи молча логируются
в stderr и не ломают генерацию.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import sqlite3
import sys
import threading
import time
from pathlib import Path

ADMIN_LOCAL = "admin-local"          # синтетический user_id входа по SITE_PASSWORD
COOKIE_NAME = "devbim_session"
PBKDF2_ITER = 240_000                # пароли локальных аккаунтов (режим users)
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
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
            # миграция под локальные аккаунты (режим users): пароль + токен IR
            cols = {r[1] for r in c.execute("PRAGMA table_info(users)")}
            if "password_hash" not in cols:
                c.execute("ALTER TABLE users ADD COLUMN password_hash TEXT")
            if "ir_token" not in cols:
                c.execute("ALTER TABLE users ADD COLUMN ir_token TEXT")
            # персональные настройки Design Code (админ-панель, п.73)
            if "dc_url" not in cols:
                c.execute("ALTER TABLE users ADD COLUMN dc_url TEXT")
            if "dc_code" not in cols:
                c.execute("ALTER TABLE users ADD COLUMN dc_code TEXT")
            # общие настройки инстанса, правятся из /admin без доступа к .env
            c.execute(
                """CREATE TABLE IF NOT EXISTS settings(
                     key TEXT PRIMARY KEY, value TEXT NOT NULL)"""
            )
            try:
                c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users(lower(email))")
            except Exception as e:  # noqa: BLE001 — дубли в легаси-БД не должны ронять старт
                print(f"[studio_store] email index skipped: {e}", file=sys.stderr)
            # журнал генераций для админ-панели (деньги/успех-ошибка/время)
            c.execute(
                """CREATE TABLE IF NOT EXISTS gen_log(
                     id INTEGER PRIMARY KEY AUTOINCREMENT,
                     ts INTEGER NOT NULL,
                     user_id TEXT NOT NULL DEFAULT '',
                     kind TEXT NOT NULL DEFAULT '',
                     model TEXT NOT NULL DEFAULT '',
                     status TEXT NOT NULL DEFAULT 'ok',
                     images INTEGER NOT NULL DEFAULT 0,
                     cost_usd REAL,
                     duration_s REAL NOT NULL DEFAULT 0,
                     error TEXT)"""
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


# --- локальные аккаунты (режим users: вход по email/паролю) ---

def auth_mode() -> str:
    """Активный режим входа: password | sso | users (STUDIO_AUTH_MODE)."""
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
    """Стабильный user_id локального аккаунта: u_ + sha256(email)[:16]."""
    return "u_" + hashlib.sha256((email or "").strip().lower().encode("utf-8")).hexdigest()[:16]


def create_user(email: str, name: str = "", password: "str | None" = None,
                role: str = "user", ir_token: "str | None" = None) -> dict:
    """Создать локальный аккаунт; ValueError при кривом email/роли/дубликате."""
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
    with _LOCK, _conn() as c:
        c.execute(
            """INSERT INTO users(user_id,email,name,role,created_at,last_seen,
                                 password_hash,ir_token) VALUES(?,?,?,?,?,?,?,?)""",
            (uid, email, name or "", role, now, now,
             _hash_password(password) if password else None,
             (ir_token or "").strip() or None),
        )
    u = get_user(uid)
    assert u is not None
    return u


def find_user_by_email(email: str) -> "dict | None":
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


def set_ir_token(user_id: str, token: "str | None") -> None:
    with _LOCK, _conn() as c:
        c.execute("UPDATE users SET ir_token=? WHERE user_id=?",
                  ((token or "").strip() or None, user_id))


def get_ir_token(user_id: str) -> "str | None":
    u = get_user(user_id)
    return (u.get("ir_token") or None) if u else None


# --- персональные настройки Design Code (админ-панель, п.73) ---

def set_design_code(user_id: str, url: "str | None", code: "str | None") -> None:
    """URL сайта дизайн-кода и код доступа конкретного пользователя
    (пусто/None — персонального значения нет, действует общее)."""
    if not _ready:  # вход владельца идёт до init_db — таблицы может ещё не быть
        init_db()
    with _LOCK, _conn() as c:
        c.execute("UPDATE users SET dc_url=?, dc_code=? WHERE user_id=?",
                  (((url or "").strip() or None), ((code or "").strip() or None), user_id))


# --- общие настройки инстанса (правятся из /admin, приоритет над .env) ---

def get_setting(key: str) -> "str | None":
    """Значение из таблицы settings; None — не задано (фолбэк на .env)."""
    try:
        with _conn() as c:
            row = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
            return (row["value"] or None) if row else None
    except Exception:
        return None


def set_setting(key: str, value: "str | None") -> None:
    v = (value or "").strip()
    if not _ready:  # как set_design_code: таблицы settings может ещё не быть
        init_db()
    with _LOCK, _conn() as c:
        if v:
            c.execute("INSERT INTO settings(key,value) VALUES(?,?) "
                      "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, v))
        else:
            c.execute("DELETE FROM settings WHERE key=?", (key,))


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


# --- журнал генераций (админ-панель: деньги, успех/ошибка, время) ---
GEN_LOG_CAP = 20000  # мягкий лимит строк; читается в рантайме (переопределяется тестами)


def log_generation(user_id: str, kind: str, model: str, status: str = "ok",
                   images: int = 0, cost_usd: "float | None" = None,
                   duration_s: float = 0.0, error: "str | None" = None) -> None:
    try:
        if not _ready:
            init_db()
        err_txt = str(error)[:500] if error else None
        with _LOCK, _conn() as c:
            c.execute(
                "INSERT INTO gen_log(ts,user_id,kind,model,status,images,cost_usd,duration_s,error)"
                " VALUES(?,?,?,?,?,?,?,?,?)",
                (int(time.time()), user_id or "", kind or "", model or "",
                 "error" if status == "error" else "ok",
                 max(0, int(images or 0)),
                 float(cost_usd) if isinstance(cost_usd, (int, float)) else None,
                 max(0.0, float(duration_s or 0)), err_txt),
            )
            # прун — журнал не должен расти бесконечно
            c.execute(
                "DELETE FROM gen_log WHERE id <= (SELECT MAX(id) FROM gen_log) - ?",
                (GEN_LOG_CAP,),
            )
    except Exception as e:  # noqa: BLE001 — учёт не должен ломать генерацию
        print(f"[studio_store] log_generation failed: {e}", file=sys.stderr)


def gen_stats(user_id: str) -> dict:
    """Сводка по пользователю для таблицы /admin (cost_usd=None — цен не знаем)."""
    try:
        with _conn() as c:
            r = c.execute(
                """SELECT COUNT(*) total,
                          COALESCE(SUM(status='ok'), 0) ok,
                          COALESCE(SUM(status='error'), 0) failed,
                          COALESCE(SUM(images), 0) images,
                          SUM(cost_usd) cost_usd,
                          AVG(CASE WHEN status='ok' THEN duration_s END) avg_s,
                          MAX(ts) last_ts
                   FROM gen_log WHERE user_id=?""",
                (user_id,),
            ).fetchone()
            return {"total": r["total"] or 0, "ok": r["ok"], "failed": r["failed"],
                    "images": r["images"], "cost_usd": r["cost_usd"],
                    "avg_s": r["avg_s"], "last_ts": r["last_ts"]}
    except Exception:
        return {"total": 0, "ok": 0, "failed": 0, "images": 0,
                "cost_usd": None, "avg_s": None, "last_ts": None}


def gen_log_list(user_id: "str | None" = None, limit: int = 200) -> list[dict]:
    """Последние записи журнала (новые сверху); user_id=None — все пользователи."""
    try:
        q = "SELECT id,ts,user_id,kind,model,status,images,cost_usd,duration_s,error FROM gen_log"
        args: list = []
        if user_id:
            q += " WHERE user_id=?"
            args.append(user_id)
        q += " ORDER BY id DESC LIMIT ?"
        args.append(max(1, min(int(limit or 200), 1000)))
        with _conn() as c:
            return [dict(r) for r in c.execute(q, args)]
    except Exception as e:  # noqa: BLE001
        print(f"[studio_store] gen_log_list failed: {e}", file=sys.stderr)
        return []


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
    """Комната пользователя для socket.io connect (по куке из environ).
    Password-режим -> None; sso и users -> комната user:<id>."""
    if auth_mode() == "password":
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
