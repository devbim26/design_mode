# -*- coding: utf-8 -*-
"""Тесты company_manager. Запуск: venv\Scripts\python.exe tests\test_company_manager.py"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import company_manager as cm

# работа в песочнице, чтобы не трогать реальный companies.json
cm.REGISTRY_PATH = Path("data_test_companies.json")

# 1. код компании
assert cm.valid_code("stroyproekt") is True
assert cm.valid_code("Stroy") is False      # заглавные нельзя
assert cm.valid_code("a") is False          # минимум 2
assert cm.valid_code("comp 1") is False     # пробел нельзя
assert cm.valid_code("comp-1") is True

# 2. порты
rows = [{"port": 9100}, {"port": 9102}]
assert cm.next_port(rows) == 9101, "пропущенные порты не переиспользуем"
assert cm.next_port([]) == 9100

# 3. пароли: читаемый формат, уникальность
pws = {cm.gen_password() for _ in range(50)}
assert len(pws) >= 49, "пароли практически уникальны"
for p in pws:
    parts = p.split("-")
    assert len(parts) == 3 and parts[2].isdigit(), f"формат СЛОВО-СЛОВО-цифры: {p}"
    for ch in "0O1lI":
        assert ch not in p, f"неоднозначный символ {ch} в {p}"

# 4. реестр: save/load roundtrip, find_row
cm.save_registry([{"code": "acme", "name": "ООО «А»", "port": 9100,
                   "created_at": "2026-09-05", "valid_until": None}])
loaded = cm.load_registry()
assert loaded[0]["code"] == "acme"
assert cm.find_row("acme")["port"] == 9100
assert cm.find_row("nope") is None

cm.REGISTRY_PATH.unlink()
print("OK")
