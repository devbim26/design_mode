# -*- coding: utf-8 -*-
"""Общая библиотека управления компаниями-лицензиатами DevBIM Image Studio.

Реестр companies.json + выделение портов + генерация читаемых паролей.
Используется create_company.py / list_companies.py / stop_company.py.
"""

from __future__ import annotations

import json
import random
import re
from datetime import date
from pathlib import Path

BASE = Path(__file__).resolve().parent
COMPANIES_DIR = BASE / "companies"
REGISTRY_PATH = BASE / "companies.json"

PORT_BASE = 9100          # 9090 занят базовым экземпляром
CODE_RE = re.compile(r"^[a-z0-9-]{2,32}$")

# Короткие однозначные слова для читаемых паролей (без 0/O, 1/l/I)
_WORDS = (
    # прим.: из исходного списка брифа убраны слова с буквой l
    # (alpha, delta, layout, purple, silver, ultra, yellow) — тест
    # запрещает неоднозначный символ l в паролях
    "bravo focus granite harbor impact jasper modern northern object "
    "quartz rocket timber vector winter xenon zephyr breeze "
    "copper drone ember"
).split()
_DIGITS = "23456789"      # без 0 и 1


def valid_code(code: str) -> bool:
    return bool(CODE_RE.match(code or ""))


def gen_password() -> str:
    w = random.sample(_WORDS, 2)
    n = "".join(random.choice(_DIGITS) for _ in range(4))
    return f"{w[0]}-{w[1]}-{n}"


def load_registry() -> list[dict]:
    if not REGISTRY_PATH.is_file():
        return []
    try:
        data = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def save_registry(rows: list[dict]) -> None:
    REGISTRY_PATH.write_text(
        json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def find_row(code: str) -> dict | None:
    for r in load_registry():
        if r.get("code") == code:
            return r
    return None


def next_port(rows: list[dict] | None = None) -> int:
    """Минимальный свободный от реестра порт >= 9100 (пропуски не переиспользуем)."""
    rows = rows if rows is not None else load_registry()
    used = {int(r["port"]) for r in rows if "port" in r}
    port = PORT_BASE
    while port in used:
        port += 1
    return port


def today() -> str:
    return date.today().isoformat()
