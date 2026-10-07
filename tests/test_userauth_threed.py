# -*- coding: utf-8 -*-
"""3D-генерация: per-user каталог IFC-результатов, тег владения, ключ VLM.

Запуск: venv\\Scripts\\python.exe tests\\test_userauth_threed.py
"""
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "siteauth"))
import studio_store  # noqa: E402

# подменяем ЛОКАЛЬНЫМИ копиями studio_store и imagerouter (ленивые import-ы)
sys.modules["invokeai.app.api.routers"] = SimpleNamespace(studio_store=studio_store)

_FAKE_KEYS = {}


def _fake_effective_key(u):
    """Мок effective_key: у пользователя токен из _FAKE_KEYS (нет — None,
    глобальный НЕ подставляется); у админа/без пользователя — глобальный."""
    if u and u != "admin-local":
        return _FAKE_KEYS.get(u)
    return "sk-global"


sys.modules["invokeai.app.api.routers.imagerouter"] = SimpleNamespace(
    CHAT_COMPLETIONS_URL="http://x/chat",
    effective_key=_fake_effective_key,
)

sys.path.insert(0, str(ROOT / "threed"))
import threed_router  # noqa: E402

tmp = Path(tempfile.mkdtemp(prefix="userauth_threed_"))
os.environ["INVOKEAI_ROOT"] = str(tmp)
threed_router.get_config = lambda: SimpleNamespace(root_path=str(tmp))
studio_store.init_db()

UID = studio_store.create_user("d@x.ru", "", "parol12345", "user")["user_id"]


def main():
    # --- каталог пользователя ---
    assert threed_router.user_out_dir(None) == tmp / "ifc"
    assert threed_router.user_out_dir("admin-local") == tmp / "ifc"
    d = threed_router.user_out_dir(UID)
    assert d == tmp / "ifc" / "d@x.ru" and d.is_dir(), d
    import re
    assert re.fullmatch(r"[a-z0-9@._+-]+", d.name), d.name

    # --- тег владения готовым IFC (файл виден автору во вкладке IFC) ---
    threed_router._tag_ifc_result("3D_facade_x.ifc", UID)
    assert studio_store.owner("ifc", "3D_facade_x.ifc") == UID
    threed_router._tag_ifc_result(None, UID)   # не падает
    threed_router._tag_ifc_result("y.ifc", None)

    # --- ключ VLM: пользователь с токеном / без токена / глобальный ---
    calls = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        calls.update(url=url, headers=headers)
        return SimpleNamespace(status_code=200, json=lambda: {
            "choices": [{"message": {"content": "ok"}}], "usage": {}})

    threed_router.requests.post = fake_post

    threed_router._IR_USER_LOCAL.user = UID
    _FAKE_KEYS[UID] = "sk-3d-user"
    threed_router._call_vlm("sys", "p", None, "vlm/x")
    assert calls["headers"]["Authorization"] == "Bearer sk-3d-user", calls

    # пользователь без токена -> ValueError (глобальный НЕ подставляется)
    _FAKE_KEYS.clear()
    try:
        threed_router._call_vlm("sys", "p", None, "vlm/x")
        raise AssertionError("ожидался ValueError")
    except ValueError as e:
        assert "Персональный токен" in str(e), e

    # без пользователя / admin-local -> глобальный ключ
    threed_router._IR_USER_LOCAL.user = None
    threed_router._call_vlm("sys", "p", None, "vlm/x")
    assert calls["headers"]["Authorization"] == "Bearer sk-global", calls

    print("OK")


main()
