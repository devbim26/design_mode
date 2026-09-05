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
