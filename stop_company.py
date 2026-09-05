# -*- coding: utf-8 -*-
"""Остановка экземпляра компании по порту (psutil).

python stop_company.py <код>   — остановить компанию
python stop_company.py         — без аргументов: список запущенных
"""

from __future__ import annotations

import sys

import psutil

import company_manager as cm

# Флаг: psutil.net_connections может требовать прав администратора на Windows.
_ports_access_denied = False


def port_owner(port: int) -> psutil.Process | None:
    """Процесс, слушающий порт; None — порт свободен ИЛИ статус неизвестен."""
    global _ports_access_denied
    try:
        conns = psutil.net_connections(kind="tcp")
    except psutil.AccessDenied:
        if not _ports_access_denied:
            print("ВНИМАНИЕ: нужны права администратора для статуса портов "
                  "(psutil.AccessDenied); статус — «неизвестно»")
            _ports_access_denied = True
        return None
    for c in conns:
        if c.laddr and c.laddr.port == port and c.status == psutil.CONN_LISTEN:
            try:
                return psutil.Process(c.pid)
            except psutil.NoSuchProcess:
                return None
    return None


def ports_unknown() -> bool:
    return _ports_access_denied


def main() -> None:
    rows = cm.load_registry()
    if len(sys.argv) < 2:
        print("Запущенные компании:")
        found = False
        for r in rows:
            if port_owner(int(r["port"])):
                print(f"  {r['code']:<16} порт {r['port']}")
                found = True
        if not found:
            suffix = " (статус портов неизвестен)" if ports_unknown() else ""
            print(f"  (нет запущенных){suffix}")
        return

    code = sys.argv[1]
    row = cm.find_row(code)
    if not row:
        print(f"ОШИБКА: компания «{code}» не найдена в companies.json")
        sys.exit(1)
    proc = port_owner(int(row["port"]))
    if not proc:
        if ports_unknown():
            print(f"Компания {code}: статус порта {row['port']} неизвестен "
                  "(нет прав администратора) — остановка невозможна")
            sys.exit(1)
        print(f"Компания {code} не запущена (порт {row['port']} свободен)")
        return
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except psutil.TimeoutExpired:
        proc.kill()
    print(f"Компания {code} остановлена (порт {row['port']}, pid {proc.pid})")


if __name__ == "__main__":
    main()
