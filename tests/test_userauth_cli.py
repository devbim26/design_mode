# -*- coding: utf-8 -*-
"""CLI user_manager.py: add/list/set-password/set-token/role/revoke/restore.

Запуск: venv\\Scripts\\python.exe tests\\test_userauth_cli.py
"""
import io
import os
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "siteauth"))
import studio_store  # noqa: E402
import user_manager  # noqa: E402

tmp = Path(tempfile.mkdtemp(prefix="userauth_cli_"))
os.environ["INVOKEAI_ROOT"] = str(tmp / "data")


def run_cli(*argv):
    saved = sys.argv
    out = io.StringIO()
    sys.argv = ["user_manager.py"] + list(argv)
    try:
        with redirect_stdout(out):
            code = None
            try:
                user_manager.main()
            except SystemExit as e:
                code = e.code
    finally:
        sys.argv = saved
    return out.getvalue(), code


def main():
    # add с явным паролем
    out, _ = run_cli("add", "a@x.ru", "--name", "Аня", "--password", "parol12345",
                     "--root", str(tmp / "data"))
    assert "Создан пользователь" in out and "a@x.ru" in out, out
    u = studio_store.find_user_by_email("a@x.ru")
    assert u and studio_store.check_password(u["user_id"], "parol12345")
    assert not studio_store.get_ir_token(u["user_id"])

    # add без пароля: генерирует и печатает
    out, _ = run_cli("add", "b@x.ru", "--root", str(tmp / "data"))
    assert "Сгенерированный пароль:" in out, out
    gen = out.split("Сгенерированный пароль:")[1].strip().splitlines()[0].strip()
    b = studio_store.find_user_by_email("b@x.ru")
    assert studio_store.check_password(b["user_id"], gen)

    # add с токеном
    out, _ = run_cli("add", "c@x.ru", "--password", "parol12345", "--token", "sk-cli",
                     "--root", str(tmp / "data"))
    assert studio_store.get_ir_token(studio_store.find_user_by_email("c@x.ru")["user_id"]) == "sk-cli"

    # дубликат -> SystemExit с сообщением
    out, code = run_cli("add", "a@x.ru", "--password", "parol12345", "--root", str(tmp / "data"))
    assert code is not None, (out, code)

    # list печатает email
    out, _ = run_cli("list", "--root", str(tmp / "data"))
    for mail in ("a@x.ru", "b@x.ru", "c@x.ru"):
        assert mail in out, out

    # set-password (генерация)
    out, _ = run_cli("set-password", "a@x.ru", "--root", str(tmp / "data"))
    new_pw = out.split("Пароль обновлён:")[1].strip().splitlines()[0].strip()
    assert studio_store.check_password(u["user_id"], new_pw)

    # set-token / очистка
    run_cli("set-token", "a@x.ru", "sk-t2", "--root", str(tmp / "data"))
    assert studio_store.get_ir_token(u["user_id"]) == "sk-t2"
    run_cli("set-token", "a@x.ru", "-", "--root", str(tmp / "data"))
    assert studio_store.get_ir_token(u["user_id"]) is None

    # role (override) / revoke / restore
    run_cli("role", "a@x.ru", "admin", "--root", str(tmp / "data"))
    assert studio_store.effective_role(u["user_id"]) == "admin"
    run_cli("revoke", "a@x.ru", "--root", str(tmp / "data"))
    assert studio_store.effective_role(u["user_id"]) is None
    run_cli("restore", "a@x.ru", "--root", str(tmp / "data"))
    assert studio_store.effective_role(u["user_id"]) == "admin"

    # неизвестный пользователь -> SystemExit
    out, code = run_cli("revoke", "ghost@x.ru", "--root", str(tmp / "data"))
    assert code is not None, (out, code)

    print("OK")


main()
