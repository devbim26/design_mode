# -*- coding: utf-8 -*-
"""Создание экземпляра DevBIM Image Studio для компании-лицензиата.

python create_company.py --name "ООО «Стройпроект»" --code stroyproekt \
       [--valid-until 2027-09-05] [--password пароль]

Создаёт companies/<код>/ (.env, data/invokeai.yaml, CREDENTIALS.txt),
записывает компанию в companies.json. Запуск сервера:
start_company.bat <код>. Ключ IMAGEROUTER_API_KEY копируется из корневого
.env проекта (можно потом заменить на персональный ключ компании).
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

import company_manager as cm

BASE = cm.BASE
# точки для тестовой песочницы (переопределяются тестом)
REGISTRY_PATH = cm.REGISTRY_PATH
COMPANIES_DIR = cm.COMPANIES_DIR


def _die(msg: str) -> None:
    print(f"ОШИБКА: {msg}")
    sys.exit(f"ОШИБКА: {msg}")


def _ir_key() -> str:
    """IMAGEROUTER_API_KEY из корневого .env (может отсутствовать)."""
    env = BASE / ".env"
    if env.is_file():
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("IMAGEROUTER_API_KEY="):
                return line.partition("=")[2].strip().strip('"').strip("'")
    return ""


ENV_TEMPLATE = """# DevBIM Image Studio — компания «{name}» (код: {code}).
# Выдаётся компанией devBIM. Смена значений вступает в силу после
# перезапуска сервера (кроме SITE_PASSWORD/SITE_VALID_UNTIL — читаются
# на каждый запрос).

# Пароль входа сотрудников компании.
SITE_PASSWORD={password}

# Админский пароль («Менеджер моделей», шестерёнка в меню).
ADMIN_PASSWORD={admin_password}

# Срок лицензии (ГГГГ-ММ-ДД). После этой даты вход закрывается страницей
# «Лицензия истекла». Удалите строку для бессрочной лицензии.
SITE_VALID_UNTIL={valid_until}

# API-ключ ImageRouter (общий или персональный ключ компании).
IMAGEROUTER_API_KEY={ir_key}
"""


def create_company(code: str, name: str, valid_until: str | None = None,
                   password: str | None = None,
                   admin_password: str | None = None) -> dict:
    if not cm.valid_code(code):
        _die(f"код компании «{code}»: только строчные латиница/цифры/дефис, 2-32 символа")
    if cm.find_row(code):
        _die(f"компания с кодом «{code}» уже существует")

    if valid_until:
        try:
            date.fromisoformat(valid_until)
        except ValueError:
            _die(f"valid-until «{valid_until}» — не дата; формат ГГГГ-ММ-ДД (например 2027-09-05)")

    password = password or cm.gen_password()
    admin_password = admin_password or cm.gen_password()

    rows = cm.load_registry()
    port = cm.next_port(rows)

    cdir = COMPANIES_DIR / code
    if cdir.exists():
        _die(f"каталог {cdir} уже существует (компания без записи в реестре?) — удалите его или восстановите companies.json")
    (cdir / "data").mkdir(parents=True)

    # invokeai.yaml: копия базового с заменой порта
    src_yaml = BASE / "data" / "invokeai.yaml"
    if not src_yaml.is_file():
        _die("не найден data/invokeai.yaml базового экземпляра")
    yaml = src_yaml.read_text(encoding="utf-8")
    yaml, n = re.subn(r"(?m)^port:\s*\d+", f"port: {port}", yaml)
    if n != 1:
        _die("в invokeai.yaml не найдена строка port:")
    (cdir / "data" / "invokeai.yaml").write_text(yaml, encoding="utf-8")

    # .env компании
    vu = valid_until or ""
    (cdir / ".env").write_text(
        ENV_TEMPLATE.format(name=name, code=code, password=password,
                            admin_password=admin_password,
                            valid_until=vu, ir_key=_ir_key()),
        encoding="utf-8",
    )

    # выдача компании
    (cdir / "CREDENTIALS.txt").write_text(
        f"DevBIM Image Studio — доступ для компании «{name}»\n"
        f"=================================================\n"
        f"Адрес:        http://<адрес-сервера>:{port}\n"
        f"Пароль входа: {password}\n"
        f"Админ-пароль: {admin_password}\n"
        f"Лицензия до:  {valid_until or 'бессрочно'}\n"
        f"Создан:       {cm.today()}\n",
        encoding="utf-8",
    )

    row = {"code": code, "name": name, "port": port,
           "created_at": cm.today(), "valid_until": valid_until}
    rows.append(row)
    cm.save_registry(rows)

    print(f"Компания создана: {name} ({code})")
    print(f"  Порт:        {port}")
    print(f"  Пароль:      {password}")
    print(f"  Админ-пароль:{admin_password}")
    print(f"  Лицензия до: {valid_until or 'бессрочно'}")
    print(f"  Запуск:      start_company.bat {code}")
    print(f"  Выдача:      {cdir / 'CREDENTIALS.txt'}")
    return row


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--name", required=True, help="название компании")
    ap.add_argument("--code", required=True, help="код (латиница/цифры/дефис)")
    ap.add_argument("--valid-until", default=None, help="срок лицензии ГГГГ-ММ-ДД")
    ap.add_argument("--password", default=None, help="пароль входа (иначе генерируется)")
    ap.add_argument("--admin-password", default=None)
    args = ap.parse_args()
    create_company(code=args.code, name=args.name,
                   valid_until=args.valid_until, password=args.password,
                   admin_password=args.admin_password)


if __name__ == "__main__":
    main()
