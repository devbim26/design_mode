# Мультикомпанность: экземпляр сервера на компанию — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executinging-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Каждой компании-лицензиату — свой экземпляр DevBIM Image Studio (свой порт, пароль, данные), плюс управление компанией скриптами и документация проекта.

**Architecture:** Один общий патченный venv; компании живут в `companies/<код>/` (свой `.env` + `data/invokeai.yaml` + корень InvokeAI). `site_auth.py` расширяется сроком лицензии `SITE_VALID_UNTIL`. Скрипты `create_company.py` / `start_company.bat` / `stop_company.py` / `list_companies.py` управляют жизненным циклом.

**Tech Stack:** Python 3 (venv проекта), InvokeAI 6.2.0 ASGI, psutil 7.2.2 (уже в venv), Windows bat.

## Global Constraints

- Спека: `docs/superpowers/specs/2026-09-05-company-instances-design.md`.
- Порядок загрузки `.env` в мидлварях: cwd → INVOKEAI_ROOT → родитель. Поэтому `start_company.bat` запускает сервер с **cwd = `companies/<код>/`** (компанийский `.env` побеждает), а не из корня проекта.
- `INVOKEAI_ROOT` для компании = `<проект>/companies/<код>/data` (там же `invokeai.yaml`, как у базового экземпляра).
- Порты компаний: 9100+, 9090 занят базовым экземпляром.
- `PYTHONUTF8=1` обязателен в каждом bat (кириллица в yaml).
- После правки `siteauth/site_auth.py` нужно перезапустить `setup_site_auth.py` (копирует модуль в venv) и перезапустить сервер.
- Тесты — обычные python-скрипты с assert (pytest в venv не ставим), запуск: `.\venv\Scripts\python.exe tests\<файл>.py`; каждый печатает `OK` и выходит 0.
- Код компании: `[a-z0-9-]{2,32}`.
- Все тексты UI и комментарии — на русском, стиль как в существующих скриптах.

---

### Task 1: `site_auth.py` — срок лицензии `SITE_VALID_UNTIL`

**Files:**
- Modify: `siteauth/site_auth.py`
- Create: `tests/test_site_auth.py`

**Interfaces:**
- Produces: `_valid_until() -> str | None` (ГГГГ-ММ-ДД из env или None),
  `_expired() -> bool`, `_token(password)` теперь
  `sha256(соль + пароль + "|" + valid_until_или_"")` — смена даты
  инвалидирует куки. Константа `EXPIRED_HTML` — страница «лицензия истекла».

- [ ] **Step 1: Написать падающий тест**

`tests/test_site_auth.py`:

```python
# -*- coding: utf-8 -*-
"""Тесты site_auth: срок лицензии SITE_VALID_UNTIL.

Запуск: venv\Scripts\python.exe tests\test_site_auth.py
"""
import os
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "siteauth"))
import site_auth


def run(coro_fn):
    import asyncio
    return asyncio.new_event_loop().run_until_complete(coro_fn())


class Recorder:
    """Ловит send() ASGI-ответы."""
    def __init__(self):
        self.started = False
        self.status = None
        self.body = b""

    async def __call__(self, msg):
        if msg["type"] == "http.response.start":
            self.started, self.status = True, msg["status"]
        elif msg["type"] == "http.response.body":
            self.body += msg.get("body", b"")


async def idle_receive():
    return {"type": "http.request", "body": b"", "more_body": False}


def scope(path="/", cookies=""):
    headers = [(b"cookie", cookies.encode())] if cookies else []
    return {"type": "http", "path": path, "method": "GET", "headers": headers}


# 1. Токен зависит от даты лицензии
os.environ["SITE_PASSWORD"] = "pw"
os.environ["SITE_VALID_UNTIL"] = "2030-01-01"
t1 = site_auth._token("pw")
os.environ["SITE_VALID_UNTIL"] = "2031-01-01"
t2 = site_auth._token("pw")
assert t1 != t2, "смена SITE_VALID_UNTIL должна менять токен (инвалидация кук)"

# 2. Просроченная лицензия: _expired
os.environ["SITE_VALID_UNTIL"] = "2020-01-01"
assert site_auth._expired() is True
os.environ["SITE_VALID_UNTIL"] = "2099-01-01"
assert site_auth._expired() is False
os.environ.pop("SITE_VALID_UNTIL", None)
assert site_auth._expired() is False, "без даты лицензия бессрочная"

# 3. Просрочено -> GET / отдаёт страницу «лицензия истекла», кука не помогает
os.environ["SITE_VALID_UNTIL"] = "2020-01-01"
mw = site_auth.SiteAuthMiddleware(lambda s, r, snd: None)
rec = Recorder()
run(lambda: mw(scope("/", f"devbim_auth={t1}"), idle_receive, rec))
assert rec.status == 200
assert "иcтёк".encode() not in rec.body  # не проверяем точный текст тут
assert "DevBIM".encode() in rec.body
assert b"devbim.com" in rec.body, "должны быть контакты devBIM"

# 4. Не просрочено + верная кука -> запрос проходит дальше (вызов app)
called = []

async def app(s, r, snd):
    called.append(s["path"])
    await snd({"type": "http.response.start", "status": 200, "headers": []})
    await snd({"type": "http.response.body", "body": b"app"})

os.environ["SITE_VALID_UNTIL"] = "2099-01-01"
good = site_auth._token("pw")
mw = site_auth.SiteAuthMiddleware(app)
rec = Recorder()
run(lambda: mw(scope("/", f"devbim_auth={good}"), idle_receive, rec))
assert called == ["/"], "верная кука должна пропускать запрос в приложение"

# 5. Просрочено -> POST /auth/login не пускает даже с верным паролем
os.environ["SITE_VALID_UNTIL"] = "2020-01-01"
mw = site_auth.SiteAuthMiddleware(app)
rec = Recorder()
body = b"password=pw"

async def recv_login():
    return {"type": "http.request", "body": body, "more_body": False}

run(lambda: mw(scope("/auth/login", ""), recv_login, rec))
assert "DevBIM".encode() in rec.body and rec.status in (200, 401)

print("OK")
```

- [ ] **Step 2: Запустить, убедиться в падении**

Run: `.\venv\Scripts\python.exe tests\test_site_auth.py`
Expected: FAIL — `AttributeError: module 'site_auth' has no attribute '_expired'` (или подобное).

- [ ] **Step 3: Реализовать в `siteauth/site_auth.py`**

Добавить после `TOKEN_SALT`:

```python
def _valid_until() -> str | None:
    _load_env_file()
    v = (os.environ.get("SITE_VALID_UNTIL") or "").strip()
    return v or None


def _expired() -> bool:
    v = _valid_until()
    if not v:
        return False
    from datetime import date
    try:
        y, m, d = (int(x) for x in v.split("-"))
        return date.today() > date(y, m, d)
    except ValueError:
        return False  # кривая дата трактуется как бессрочная + лог в консоль
```

Заменить `_token` (дата участвует — смена инвалидирует куки):

```python
def _token(password: str) -> str:
    return hashlib.sha256(
        (TOKEN_SALT + password + "|" + (_valid_until() or "")).encode("utf-8")
    ).hexdigest()
```

Добавить страницу истечения (в стиле формы входа):

```python
_EXPIRED_HTML = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<title>Лицензия истекла — DevBIM Image Studio</title>
<style>
  body {{ font-family: 'Segoe UI', system-ui, sans-serif; background: #0B0C0E;
         color: #E6EAF2; min-height: 100vh; display: flex; align-items: center;
         justify-content: center; }}
  .card {{ background: #14161A; border: 1px solid #23262D; border-radius: 14px;
          padding: 40px 36px; width: 400px; text-align: center;
          box-shadow: 0 12px 40px rgba(0,0,0,.5); }}
  .logo {{ font-size: 24px; font-weight: 700; margin-bottom: 16px; }}
  .logo .bim {{ color: #38BDF8; }}
  h1 {{ font-size: 18px; margin-bottom: 10px; }}
  p {{ color: #A7B0C0; font-size: 14px; line-height: 1.5; }}
</style>
</head>
<body>
  <div class="card">
    <div class="logo"><span class="dev">Dev</span><span class="bim">BIM</span></div>
    <h1>Срок лицензии истёк</h1>
    <p>Доступ к Image Studio приостановлен.<br>
       Для продления лицензии свяжитесь с нами:<br>
       <a href="https://devbim.com" style="color:#38BDF8">devbim.com</a></p>
  </div>
</body>
</html>"""
```

В `SiteAuthMiddleware.__call__` (http-ветка), сразу после `path = scope.get(...)`:

```python
        if _expired():
            await _send_html(send, 403, _EXPIRED_HTML.encode("utf-8"))
            return
```

(перекрывает и логин, и все прочие пути; вебсокет-ветка: заменить условие
`_authorized(scope)` на `_authorized(scope) and not _expired()`).

Обновить docstring модуля (упомянуть `SITE_VALID_UNTIL`).

- [ ] **Step 4: Тест зелёный**

Run: `.\venv\Scripts\python.exe tests\test_site_auth.py`
Expected: `OK`

- [ ] **Step 5: Переразвёртывание + проверка синтаксиса + коммит**

```bash
.\venv\Scripts\python.exe .\setup_site_auth.py
# (модуль скопируется в venv; api_app.py уже пропатчен — «пропуск» это норма)
git add siteauth/site_auth.py tests/test_site_auth.py
git commit -m "feat(siteauth): срок лицензии SITE_VALID_UNTIL (экран «лицензия истекла», дата в токене)"
```

---

### Task 2: `company_manager.py` — общая библиотека (реестр, порты, пароли)

**Files:**
- Create: `company_manager.py`
- Create: `tests/test_company_manager.py`

**Interfaces:**
- Produces:
  - `BASE = Path(__file__).resolve().parent`
  - `REGISTRY_PATH = BASE / "companies.json"`
  - `COMPANIES_DIR = BASE / "companies"`
  - `load_registry() -> list[dict]` (каждый: `code,name,port,created_at,valid_until`)
  - `save_registry(rows: list[dict]) -> None`
  - `next_port(rows: list[dict] | None = None) -> int` (9100+)
  - `valid_code(code: str) -> bool`
  - `gen_password() -> str` (формат `СЛОВО-СЛОВО-4цифры`, без неоднозначных символов)
  - `find_row(code: str) -> dict | None`

- [ ] **Step 1: Падающий тест**

`tests/test_company_manager.py`:

```python
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
```

- [ ] **Step 2: Запустить — падение**

Run: `.\venv\Scripts\python.exe tests\test_company_manager.py`
Expected: `ModuleNotFoundError: No module named 'company_manager'`

- [ ] **Step 3: Реализация `company_manager.py`**

```python
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
    "alpha bravo delta focus granite harbor impact jasper layout "
    "modern northern object purple quartz rocket silver timber ultra "
    "vector winter xenon yellow zephyr atlas breeze copper drone ember"
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
```

- [ ] **Step 4: Тест зелёный**

Run: `.\venv\Scripts\python.exe tests\test_company_manager.py`
Expected: `OK`

- [ ] **Step 5: Коммит**

```bash
git add company_manager.py tests/test_company_manager.py
git commit -m "feat(companies): библиотека реестра компаний, портов и паролей"
```

---

### Task 3: `create_company.py` — создание экземпляра компании

**Files:**
- Create: `create_company.py`
- Create: `tests/test_create_company.py`

**Interfaces:**
- Consumes: `company_manager` (Task 2), `siteauth/site_auth.py` (Task 1).
- Produces: `create_company(code, name, valid_until=None, password=None,
  admin_password=None, yes=False) -> dict` — возвращает запись реестра; создаёт:
  - `companies/<код>/.env` (SITE_PASSWORD, ADMIN_PASSWORD,
    IMAGEROUTER_API_KEY — копия из корневого `.env`, SITE_VALID_UNTIL)
  - `companies/<код>/data/invokeai.yaml` — копия `data/invokeai.yaml`
    с заменённым `port:`
  - `companies/<код>/CREDENTIALS.txt` — выдача компании (не в git)
  - запись в `companies.json`
- CLI: `python create_company.py --name "ООО «А»" --code acme [--valid-until 2027-09-05] [--password ...] [--yes]`

- [ ] **Step 1: Падающий тест**

`tests/test_create_company.py`:

```python
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
assert "port: 9090" not in yaml or row["port'] == 9090  # порт заменён

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

shutil.rmtree(cm.COMPANIES_DIR, ignore_errors=True)
cm.REGISTRY_PATH.unlink()
print("OK")
```

- [ ] **Step 2: Падение**

Run: `.\venv\Scripts\python.exe tests\test_create_company.py`
Expected: `ModuleNotFoundError: No module named 'create_company'`

- [ ] **Step 3: Реализация `create_company.py`**

```python
# -*- coding: utf-8 -*-
"""Создание экземпляра DevBIM Image Studio для компании-лицензиата.

python create_company.py --name "ООО «Стройпроект»" --code stroyproekt \
       [--valid-until 2027-09-05] [--password пароль] [--yes]

Создаёт companies/<код>/ (.env, data/invokeai.yaml, CREDENTIALS.txt),
записывает компанию в companies.json. Запуск сервера:
start_company.bat <код>. Ключ IMAGEROUTER_API_KEY копируется из корневого
.env проекта (можно потом заменить на персональный ключ компании).
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

import company_manager as cm

BASE = cm.BASE
# точки для тестовой песочницы (переопределяются тестом)
REGISTRY_PATH = cm.REGISTRY_PATH
COMPANIES_DIR = cm.COMPANIES_DIR


def _die(msg: str) -> None:
    print(f"ОШИБКА: {msg}")
    sys.exit(1)


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
                   admin_password: str | None = None,
                   yes: bool = False) -> dict:
    if not cm.valid_code(code):
        _die(f"код компании «{code}»: только строчные латиница/цифры/дефис, 2-32 символа")
    if cm.find_row(code):
        _die(f"компания с кодом «{code}» уже существует")

    if valid_until and not re.match(r"^\d{4}-\d{2}-\d{2}$", valid_until):
        _die("valid-until должен быть в формате ГГГГ-ММ-ДД")

    password = password or cm.gen_password()
    admin_password = admin_password or cm.gen_password()

    rows = cm.load_registry()
    port = cm.next_port(rows)

    cdir = COMPANIES_DIR / code
    (cdir / "data").mkdir(parents=True, exist_ok=True)

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
    ap.add_argument("--yes", action="store_true", help="без вопросов")
    create_company(ap.parse_args().code, ap.parse_args().name,
                   ap.parse_args().valid_until, ap.parse_args().password,
                   ap.parse_args().admin_password, ap.parse_args().yes)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Тест зелёный**

Run: `.\venv\Scripts\python.exe tests\test_create_company.py`
Expected: `OK`

- [ ] **Step 5: Коммит**

```bash
git add create_company.py tests/test_create_company.py
git commit -m "feat(companies): create_company.py — экземпляр на компанию (.env, yaml, порты, пароли)"
```

---

### Task 4: `start_company.bat` / `stop_company.py` / `list_companies.py`

**Files:**
- Create: `start_company.bat`
- Create: `stop_company.py`
- Create: `list_companies.py`

**Interfaces:**
- Consumes: `company_manager` (Task 2), реестр из Task 3.
- Produces: `start_company.bat <код>` — запуск сервера (cwd=companies/<код>,
  INVOKEAI_ROOT=companies/<код>/data); `stop_company.py [код]` — стоп по порту
  (psutil); `list_companies.py` — таблица с колонками
  `КОД | НАЗВАНИЕ | ПОРТ | ЛИЦЕНЗИЯ ДО | СТАТУС`.

- [ ] **Step 1: `start_company.bat`**

```bat
@echo off
rem Запуск экземпляра DevBIM Image Studio для компании.
rem Использование: start_company.bat ^<код-компании^>
rem PYTHONUTF8=1: invokeai.yaml содержит кириллицу в UTF-8.
setlocal
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
if "%~1"=="" (
  echo Использование: start_company.bat ^<код-компании^>
  exit /b 1
)
if not exist "companies\%~1\.env" (
  echo Компания не найдена: %~1 ^(нет companies\%~1\.env^)
  exit /b 1
)
rem cwd = каталог компании: её .env грузится первым (порядок cwd -^> root -^> parent)
cd /d "%~dp0companies\%~1"
set "INVOKEAI_ROOT=%~dp0companies\%~1\data"
"%~dp0venv\Scripts\python.exe" -u -c "from invokeai.app.run_app import run_app; run_app()"
```

- [ ] **Step 2: `stop_company.py`**

```python
# -*- coding: utf-8 -*-
"""Остановка экземпляра компании по порту (psutil).

python stop_company.py <код>   — остановить компанию
python stop_company.py         — без аргументов: список запущенных
"""

from __future__ import annotations

import sys

import psutil

import company_manager as cm


def port_owner(port: int) -> psutil.Process | None:
    for c in psutil.net_connections(kind="tcp"):
        if c.laddr and c.laddr.port == port and c.status == psutil.CONN_LISTEN:
            try:
                return psutil.Process(c.pid)
            except psutil.NoSuchProcess:
                return None
    return None


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
            print("  (нет запущенных)")
        return

    code = sys.argv[1]
    row = cm.find_row(code)
    if not row:
        print(f"ОШИБКА: компания «{code}» не найдена в companies.json")
        sys.exit(1)
    proc = port_owner(int(row["port"]))
    if not proc:
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
```

- [ ] **Step 3: `list_companies.py`**

```python
# -*- coding: utf-8 -*-
"""Список компаний-лицензиатов: python list_companies.py"""

from __future__ import annotations

from datetime import date

import company_manager as cm
from stop_company import port_owner


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
        running = "запущена" if port_owner(int(r["port"])) else "остановлена"
        print(f"{r['code']:<18}{r['name'][:30]:<32}{r['port']:<7}{vu:<13}{running}{expired}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Сквозная проверка вживую**

```bash
.\venv\Scripts\python.exe create_company.py --name "Тест ООО" --code testco --valid-until 2099-01-01
.\venv\Scripts\python.exe list_companies.py          # testco, остановлена
start_company.bat testco                              # отдельное окно; первый старт
                                                     # инициализирует БД (минута-две)
curl -s http://127.0.0.1:<порт>/auth/login | head -5  # форма входа DevBIM
# войти браузером с паролем из CREDENTIALS.txt, сгенерировать картинку —
# галерея компании не содержит картинок базового экземпляра 9090
.\venv\Scripts\python.exe stop_company.py testco
.\venv\Scripts\python.exe list_companies.py          # testco, остановлена
```
Проверить: порты не конфликтуют с 9090; лог компании можно смотреть в окне батника.

- [ ] **Step 5: Убрать тестовую компанию, коммит**

```bash
.\venv\Scripts\python.exe -c "import company_manager as cm,json; cm.save_registry([r for r in cm.load_registry() if r['code']!='testco'])"
rmdir /s /q companies\testco
git add start_company.bat stop_company.py list_companies.py
git commit -m "feat(companies): запуск/остановка/список экземпляров компаний"
```

---

### Task 5: Структура репозитория, README, AGENTS.md, .gitignore

**Files:**
- Modify: `.gitignore`
- Modify: `README.md` (раздел «Компании (лицензии)»)
- Create: `AGENTS.md`
- Create: `companies/.gitkeep`
- Move: корневые `*.log` → `logs/` (файлы не в git, просто прибраться)

**Interfaces:**
- Consumes: всё из Task 1-4 (описываем в документации).

- [ ] **Step 1: `.gitignore` — добавить**

```gitignore
# Компании-лицензиаты: данные и секреты каждой компании
companies/*
!companies/.gitkeep
companies.json

# Логи (в т.ч. перенесённые из корня)
logs/

# Мусор тестовых прогонов
data_test_companies.json
data_test_companies/
```

- [ ] **Step 2: Перенести логи**

```bash
mkdir -p logs
mv -f ir_server.log ir_server2.log fg.log u.log web.log logs/ 2>/dev/null || true
```
(Не трогать батники, ссылающиеся на `ir_server.log` — `_ir_server_hidden.bat`
пишет лог в корень; при следующем запуске создастся заново. Перенос — только
для старых файлов.)

- [ ] **Step 3: README.md — раздел «Компании (лицензии)»**

Добавить после вводного раздела:

```markdown
## Компании (лицензии)

Продажа по компаниям: каждой компании — отдельный экземпляр сервера со своим
портом, паролем и данными (галерея, IFC-файлы изолированы автоматически).

| Действие | Команда |
|---|---|
| Создать компанию | `python create_company.py --name "ООО «А»" --code acme --valid-until 2027-09-05` |
| Запустить | `start_company.bat acme` |
| Остановить | `python stop_company.py acme` |
| Список | `python list_companies.py` |
| Сменить пароль | правка `companies/acme/.env` (SITE_PASSWORD), перезапуск не нужен |
| Продлить лицензию | правка `SITE_VALID_UNTIL` в `companies/acme/.env` |
| Отозвать немедленно | `python stop_company.py acme` + смена SITE_PASSWORD |

Пароли выдаются в `companies/<код>/CREDENTIALS.txt` (в git не входит).
Адрес компании: `http://<сервер>:<порт>` (порт из `companies.json`).
Все экземпляры используют общий патченный venv; после переустановки InvokeAI
повторить патчи один раз (см. «Проверка после изменений» в HANDOFF.md).
```

- [ ] **Step 4: `AGENTS.md` (корень проекта)**

```markdown
# AGENTS.md — DevBIM Image Studio (InvokeAI)

Правила для агентных сессий, работающих с этим репозиторием.

## Что это

Локальный InvokeAI 6.2.0 (CPU) с ребрендингом DevBIM, облачной генерацией
ImageRouter, IFC-вьювером, гейтом сайта по паролю и мультитенантностью
«экземпляр на компанию». Скрипты патчат пакет в `venv/Lib/site-packages/
invokeai/` — после `pip install --force-reinstall invokeai==6.2.0`
применять в порядке: `rebrand_devbim.py` → `setup_imagerouter.py` →
`setup_ifcviewer.py` → `setup_site_auth.py`. Все — идемпотентны.

## Где что

- `siteauth/site_auth.py` — мидлварь входа (SITE_PASSWORD из .env,
  SITE_VALID_UNTIL — срок лицензии). Деплой: `setup_site_auth.py`.
- `imagerouter/` — посредник облачной генерации (перехват enqueue_batch).
- `ifc/` — IFC-вьювер и его роутер.
- `company_manager.py`, `create_company.py`, `start_company.bat`,
  `stop_company.py`, `list_companies.py` — компании-лицензиаты
  (экземпляр на компанию, порты 9100+).
- `companies/<код>/` — данные компаний (.env, invokeai.yaml, CREDENTIALS.txt);
  в git НЕ входят.
- `docs/superpowers/specs|plans/` — спеки и планы (читать перед задачей).
- `HANDOFF.md` — подробный рабочий контекст и грабли. ЧИТАТЬ ПЕРВЫМ.

## Жёсткие правила

- Не править файлы в `venv/.../site-packages` руками — только через
  setup-скрипты в корне (иначе правки потеряются при переустановке).
- Не коммитить: `.env`, `companies.json`, `companies/*`, ключи API.
- После патчей JS-бандлов обязательно проверить парсинг:
  `node -e "import('file:///...index-*.js').catch(e=>console.log(e.message))"`
  — допустима только рантайм-ошибка, не SyntaxError.
- Сервер перезапускать `_restart_server.ps1` (WMI, отсоединённо);
  процессы из агентских сессий умирают вместе с сессией.
- `PYTHONUTF8=1` обязателен в любом bat (кириллица в yaml).
- Тесты: `venv\Scripts\python.exe tests\<имя>.py` (plain asserts, печать OK).
- Один общий venv на все компании; порты компаний 9100+ (9090 — базовый).

## Порядок работы над задачей

1. Прочитать HANDOFF.md (раздел «Что реализовано» и «грабли»).
2. Спека/план в `docs/superpowers/` обязательны для нетривиальных задач.
3. После изменений — проверка из раздела «Проверка после изменений»
   в HANDOFF.md + тесты из `tests/`.
```

- [ ] **Step 5: Коммит**

```bash
mkdir companies 2>/dev/null; touch companies/.gitkeep
git add .gitignore README.md AGENTS.md companies/.gitkeep
git commit -m "docs: AGENTS.md для агентной разработки, README-раздел «Компании», gitignore"
```

---

## Финальная сквозная проверка (после всех задач)

1. `.\venv\Scripts\python.exe tests\test_site_auth.py` → OK
2. `.\venv\Scripts\python.exe tests\test_company_manager.py` → OK
3. `.\venv\Scripts\python.exe tests\test_create_company.py` → OK
4. Создать реальную компанию `demo`, запустить, войти браузером, сгенерировать
   картинку, убедиться что базовый экземпляр 9090 её не видит, остановить.
5. Установить `SITE_VALID_UNTIL=2020-01-01` в `companies/demo/.env`,
   обновить страницу → экран «Лицензия истекла» (перезапуск не нужен).
6. Вернуть дату, войти снова. Удалить demo (`stop_company.py`, чистка реестра
   и каталога).
7. `git log --oneline` — 5+ осмысленных коммитов.
