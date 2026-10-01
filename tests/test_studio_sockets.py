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
