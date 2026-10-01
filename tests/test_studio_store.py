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
