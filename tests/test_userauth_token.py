# -*- coding: utf-8 -*-
"""Персональный токен ImageRouter: effective_key, session-мост для облачных нод.

Запуск: venv\\Scripts\\python.exe tests\\test_userauth_token.py
"""
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "siteauth"))
sys.path.insert(0, str(ROOT / "imagerouter"))
import studio_store  # noqa: E402

# ленивые import-ы роутера должны попасть в ЛОКАЛЬНУЮ копию studio_store,
# а не в задеплоенную в venv (подменяем только сам пакет routers; сам invokeai
# импортируется настоящий — нужен get_config)
sys.modules["invokeai.app.api.routers"] = SimpleNamespace(studio_store=studio_store)
import imagerouter_router as ir  # noqa: E402

tmp = Path(tempfile.mkdtemp(prefix="userauth_token_"))
os.environ["INVOKEAI_ROOT"] = str(tmp)
os.environ["IMAGEROUTER_API_KEY"] = "sk-global"
ir.get_config = lambda: SimpleNamespace(root_path=str(tmp))


def main():
    studio_store.init_db()
    u_user = studio_store.create_user("u@x.ru", "", "parol12345", "user")["user_id"]
    u_tok = studio_store.create_user("t@x.ru", "", "parol12345", "user",
                                     ir_token="sk-user-tok")["user_id"]
    u_adm = studio_store.create_user("a@x.ru", "", "parol12345", "admin")["user_id"]
    u_admtok = studio_store.create_user("at@x.ru", "", "parol12345", "admin",
                                        ir_token="sk-adm-tok")["user_id"]

    # --- effective_key ---
    assert ir.effective_key(u_tok) == "sk-user-tok", "личный токен приоритетен"
    assert ir.effective_key(u_user) is None, "user без токена НЕ получает глобальный ключ"
    assert ir.effective_key(u_adm) == "sk-global", "admin без токена — глобальный"
    assert ir.effective_key(u_admtok) == "sk-adm-tok"
    assert ir.effective_key("admin-local") == "sk-global"
    assert ir.effective_key(None) == "sk-global"

    # --- session-мост: тег владельца сессии на enqueue ---
    assert ir.user_for_session("sess-1") is None
    ir._tag_session_owner({"batch": {"graph": {"id": "sess-1"}, "runs": 1}}, u_tok)
    assert ir.user_for_session("sess-1") == u_tok
    ir._tag_session_owner({"batch": {"graph": {"id": "sess-2"}}}, None)
    assert ir.user_for_session("sess-2") is None
    ir._tag_session_owner(None, u_tok)  # не падает на кривом payload
    ir._tag_session_owner({"batch": {}}, u_tok)  # нет graph.id — молча

    # --- подсказка статуса учитывает персональный токен ---
    ir._personal_token(u_tok) == "sk-user-tok"
    assert ir._personal_token(u_user) is None
    assert ir._personal_token("admin-local") is None
    assert ir._personal_token(None) is None

    print("OK")


main()
