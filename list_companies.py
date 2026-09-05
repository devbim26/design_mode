# -*- coding: utf-8 -*-
"""Список компаний-лицензиатов: python list_companies.py"""

from __future__ import annotations

from datetime import date

import company_manager as cm
from stop_company import port_owner, ports_unknown


def main() -> None:
    rows = cm.load_registry()
    if not rows:
        print("Компаний нет. Создание: python create_company.py --name ... --code ...")
        return
    print(f"{'КОД':<18}{'НАЗВАНИЕ':<32}{'ПОРТ':<7}{'ЛИЦЕНЗИЯ ДО':<13}СТАТУС")
    for r in rows:
        vu = r.get("valid_until") or "бессрочно"
        expired = ""
        if r.get("valid_until"):
            try:
                if date.today() > date(*(int(x) for x in r["valid_until"].split("-"))):
                    expired = " (ИСТЕКЛА)"
            except ValueError:
                pass
        if ports_unknown():
            running = "неизвестно"
        else:
            running = "запущена" if port_owner(int(r["port"])) else "остановлена"
        print(f"{r['code']:<18}{r['name'][:30]:<32}{r['port']:<7}{vu:<13}{running}{expired}")


if __name__ == "__main__":
    main()
