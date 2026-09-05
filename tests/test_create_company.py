# -*- coding: utf-8 -*-
"""Тесты create_company (в песочнице). Запуск: venv\Scripts\python.exe tests\test_create_company.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import company_manager as cm
import create_company as cc

# песочница
cm.REGISTRY_PATH = Path("data_test_registry.json")
cm.COMPANIES_DIR = Path("data_test_companies")
cc.REGISTRY_PATH = cm.REGISTRY_PATH
cc.COMPANIES_DIR = cm.COMPANIES_DIR

# чистим перед прогоном
import shutil
shutil.rmtree(cm.COMPANIES_DIR, ignore_errors=True)
if cm.REGISTRY_PATH.exists():
    cm.REGISTRY_PATH.unlink()

row = cc.create_company(code="acme", name="ООО «А»", valid_until="2027-09-05")

d = cm.COMPANIES_DIR / "acme"
assert (d / ".env").is_file()
assert (d / "data" / "invokeai.yaml").is_file()
assert (d / "CREDENTIALS.txt").is_file()

env = (d / ".env").read_text(encoding="utf-8")
assert "SITE_PASSWORD=" in env and "ADMIN_PASSWORD=" in env
assert "SITE_VALID_UNTIL=2027-09-05" in env
assert "IMAGEROUTER_API_KEY=" in env, "ключ ImageRouter копируется из корневого .env"

yaml = (d / "data" / "invokeai.yaml").read_text(encoding="utf-8")
assert f"port: {row['port']}" in yaml
assert "port: 9090" not in yaml or row["port"] == 9090  # порт заменён

assert cm.find_row("acme")["name"] == "ООО «А»"

# дубль кода -> ошибка
try:
    cc.create_company(code="acme", name="ещё раз")
    raise SystemExit("дубль не отработан")
except SystemExit as e:
    assert "существует" in str(e) or "already" in str(e).lower()

# вторая компания получает другой порт
row2 = cc.create_company(code="beta", name="ООО «Б»")
assert row2["port"] != row["port"]

# существующий каталог без записи в реестре -> отказ (перезапись запрещена)
shutil.rmtree(cm.COMPANIES_DIR, ignore_errors=True)
cm.REGISTRY_PATH.unlink()
(cm.COMPANIES_DIR / "acme").mkdir(parents=True)
try:
    cc.create_company(code="acme", name="ООО «А»")
    raise SystemExit("перезапись существующего каталога не отработана")
except SystemExit as e:
    assert "уже существует" in str(e), str(e)
shutil.rmtree(cm.COMPANIES_DIR, ignore_errors=True)

# некорректная дата -> отказ
try:
    cc.create_company(code="gamma", name="ООО «Г»", valid_until="2027-13-45")
    raise SystemExit("валидация даты не отработана")
except SystemExit as e:
    assert "ГГГГ-ММ-ДД" in str(e), str(e)

shutil.rmtree(cm.COMPANIES_DIR, ignore_errors=True)
if cm.REGISTRY_PATH.exists():
    cm.REGISTRY_PATH.unlink()
print("OK")
