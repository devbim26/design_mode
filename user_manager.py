# -*- coding: utf-8 -*-
"""CLI управления пользователями студии (многопользовательский режим users).

Работает с <INVOKEAI_ROOT>/data/studio.sqlite. Ключ --root задаёт INVOKEAI_ROOT
(дефолт ./data — основной экземпляр; для компаний: companies/<код>/data).
После создания пользователей перезапуск сервера не нужен (БД читается на
каждом запросе).

Примеры:
    python user_manager.py add ivan@mail.ru --name Иван --role user
    python user_manager.py add ivan@mail.ru --password "МойПароль123" --token sk-...
    python user_manager.py list
    python user_manager.py set-password ivan@mail.ru
    python user_manager.py set-token ivan@mail.ru sk-...   (или "-" для очистки)
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
    # --root доступен и до, и после подкоманды (argparse не пропускает опции
    # главного парсера после subcommand — дублируем через parents)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--root", default=None, help="INVOKEAI_ROOT (дефолт ./data)")
    p = argparse.ArgumentParser(description="Управление пользователями DevBIM Image Studio",
                                parents=[common])
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add", help="создать пользователя", parents=[common])
    a.add_argument("email")
    a.add_argument("--name", default="")
    a.add_argument("--role", choices=("user", "admin"), default="user")
    a.add_argument("--password", default=None, help="без флага — генерируется и печатается")
    a.add_argument("--token", default=None, help="токен ImageRouter пользователя")
    s = sub.add_parser("list", help="список пользователей", parents=[common])
    s = sub.add_parser("set-password", help="сменить пароль (без --password — сгенерировать)", parents=[common])
    s.add_argument("email")
    s.add_argument("--password", default=None)
    s = sub.add_parser("set-token", help="задать токен IR ('-' — очистить)", parents=[common])
    s.add_argument("email")
    s.add_argument("token")
    s = sub.add_parser("role", help="роль-override (user|admin)", parents=[common])
    s.add_argument("email")
    s.add_argument("role", choices=("user", "admin"))
    s = sub.add_parser("revoke", help="заблокировать", parents=[common])
    s.add_argument("email")
    s = sub.add_parser("restore", help="разблокировать", parents=[common])
    s.add_argument("email")
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
            print(f"{u['email']:<32} {u['role']:<6} {tok:<12} {st:<14} {u['name']}")
    elif args.cmd == "set-password":
        u = _by_email(args.email)
        pw = args.password or gen_password()
        studio_store.set_password(u["user_id"], pw)
        print(f"Пароль обновлён: {pw}")
    elif args.cmd == "set-token":
        u = _by_email(args.email)
        studio_store.set_ir_token(u["user_id"], None if args.token == "-" else args.token)
        print("Токен очищен." if args.token == "-" else "Токен обновлён.")
    elif args.cmd == "role":
        u = _by_email(args.email)
        studio_store.set_role_override(u["user_id"], args.role)
        print(f"Роль (override): {args.role}")
    elif args.cmd == "revoke":
        u = _by_email(args.email)
        studio_store.set_revoked(u["user_id"], True)
        print("Заблокирован.")
    elif args.cmd == "restore":
        u = _by_email(args.email)
        studio_store.set_revoked(u["user_id"], False)
        print("Разблокирован.")


if __name__ == "__main__":
    main()
