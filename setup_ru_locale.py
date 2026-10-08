# -*- coding: utf-8 -*-
"""Дополняет русскую локаль интерфейса отсутствующими ключами.

Что делает:
  dist/locales/ru.json <- глубокий merge словаря locales_patch/ru_missing.json.
  Добавляются ТОЛЬКО отсутствующие ключи (существующие значения ru.json не
  трогаются — идемпотентно и безопасно для повторных запусков). В словаре —
  переводы ключей, которых нет в апстримной ru.json InvokeAI 6.2.0
  (controlLayers-фильтры/выбор объекта, тосты PSD/масок, горячие клавиши,
  launchpad и др.); для плюрализуемых ключей добавлены русские формы
  _one/_few/_many/_other. Разделы workflows.*/nodes.* сознательно не
  переводились (вкладка Workflows скрыта из рейки — UI недостижим).

Порядок запуска: ПОСЛЕ rebrand_devbim.py (rebrand перезаписывает все
locales/*.json своим брендингом Invoke->DevBIM и сотрёт дополнения, если
запустить его позже). Значения словаря уже брендированы «DevBIM».

Статика локалей отдаётся сервером с диска — после деплоя достаточно F5.

Откат: восстановить dist/locales/ru.json из ru.json.ru-locale-bak.
"""
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
DIST = BASE / "venv" / "Lib" / "site-packages" / "invokeai" / "frontend" / "web" / "dist"
PATCH = BASE / "locales_patch" / "ru_missing.json"
RU = DIST / "locales" / "ru.json"


def deep_merge_missing(dst: dict, src: dict) -> int:
    """Влить src в dst, добавляя только отсутствующие ключи. Возврат: сколько добавлено."""
    added = 0
    for k, v in src.items():
        if isinstance(v, dict):
            if k not in dst or not isinstance(dst[k], dict):
                dst[k] = {}
            added += deep_merge_missing(dst[k], v)
        elif k not in dst:
            dst[k] = v
            added += 1
    return added


def main() -> None:
    if not DIST.exists():
        print("Не найден venv InvokeAI:", DIST)
        sys.exit(1)
    if not PATCH.exists():
        print("Нет словаря переводов:", PATCH)
        sys.exit(1)
    if not RU.exists():
        print("Нет dist/locales/ru.json:", RU)
        sys.exit(1)

    ru = json.loads(RU.read_text(encoding="utf-8"))
    patch = json.loads(PATCH.read_text(encoding="utf-8"))

    added = deep_merge_missing(ru, patch)
    if added == 0:
        print("ru.json: все ключи словаря уже на месте, пропуск")
        return

    bak = RU.with_suffix(".json.ru-locale-bak")
    if not bak.exists():
        bak.write_text(RU.read_text(encoding="utf-8"), encoding="utf-8")

    # формат как у rebrand_devbim.py (indent=4 + завершающий перевод строки)
    RU.write_text(json.dumps(ru, ensure_ascii=False, indent=4) + "\n", encoding="utf-8")
    print(f"ru.json: добавлено ключей {added} (бэкап {bak.name})")


if __name__ == "__main__":
    main()
