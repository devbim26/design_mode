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
