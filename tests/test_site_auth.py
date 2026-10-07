# -*- coding: utf-8 -*-
"""Тесты site_auth: срок лицензии SITE_VALID_UNTIL, перечитывание .env.

Запуск: venv\Scripts\python.exe tests\test_site_auth.py
"""
import os
import shutil
import sys
import tempfile
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


# --- окружение: tmp-каталог с .env, подменяем INVOKEAI_ROOT ---
tmp = Path(tempfile.mkdtemp(prefix="site_auth_test_"))
saved = {k: os.environ.get(k) for k in ("INVOKEAI_ROOT", "SITE_PASSWORD", "SITE_VALID_UNTIL",
                                        "STUDIO_AUTH_MODE", "STUDIO_SESSION_SECRET")}
prev_cwd = os.getcwd()


def write_env(**kv):
    (tmp / ".env").write_text(
        "\n".join(f"{k}={v}" for k, v in kv.items()) + "\n", encoding="utf-8"
    )


try:
    os.environ["INVOKEAI_ROOT"] = str(tmp)
    # герметичность: env_value сканирует и cwd/.env — без chdir тест из корня
    # репо подхватит боевой STUDIO_AUTH_MODE=users и завалит legacy-куку
    os.chdir(tmp)
    os.environ.pop("STUDIO_AUTH_MODE", None)
    os.environ.pop("STUDIO_SESSION_SECRET", None)
    write_env(SITE_PASSWORD="pw", SITE_VALID_UNTIL="2030-01-01")

    # 1. Токен зависит от даты лицензии; правка .env подхватывается без рестарта
    t1 = site_auth._token("pw")
    write_env(SITE_PASSWORD="pw", SITE_VALID_UNTIL="2031-01-01")
    t2 = site_auth._token("pw")
    assert t1 != t2, "смена SITE_VALID_UNTIL в .env должна менять токен без перезапуска"

    # 2. Просроченная лицензия: _expired
    write_env(SITE_PASSWORD="pw", SITE_VALID_UNTIL="2020-01-01")
    assert site_auth._expired() is True
    write_env(SITE_PASSWORD="pw", SITE_VALID_UNTIL="2099-01-01")
    assert site_auth._expired() is False

    # 3. Ключа нет в .env -> fallback на os.environ
    write_env(SITE_PASSWORD="pw")
    os.environ["SITE_VALID_UNTIL"] = "2031-01-01"
    assert site_auth._valid_until() == "2031-01-01", "fallback на os.environ"
    os.environ.pop("SITE_VALID_UNTIL", None)
    assert site_auth._valid_until() is None, "без даты лицензия бессрочная"

    # 3b. Пустое значение в файле («SITE_VALID_UNTIL=») -> бессрочная
    write_env(SITE_PASSWORD="pw", SITE_VALID_UNTIL="")
    assert site_auth._valid_until() is None, "пустой SITE_VALID_UNTIL в файле = бессрочно"
    assert site_auth._expired() is False

    # 4. Просрочено -> GET / отдаёт страницу «лицензия истекла», кука не помогает
    write_env(SITE_PASSWORD="pw", SITE_VALID_UNTIL="2020-01-01")
    mw = site_auth.SiteAuthMiddleware(lambda s, r, snd: None)
    rec = Recorder()
    run(lambda: mw(scope("/", f"devbim_auth={t1}"), idle_receive, rec))
    assert rec.status == 200
    assert "истек".encode() in rec.body or "истёк".encode() in rec.body
    assert "DevBIM".encode() in rec.body
    assert b"devbim.com" in rec.body, "должны быть контакты devBIM"

    # 5. Не просрочено + верная кука -> запрос проходит дальше (вызов app)
    called = []

    async def app(s, r, snd):
        called.append(s["path"])
        await snd({"type": "http.response.start", "status": 200, "headers": []})
        await snd({"type": "http.response.body", "body": b"app"})

    write_env(SITE_PASSWORD="pw", SITE_VALID_UNTIL="2099-01-01")
    good = site_auth._token("pw")
    mw = site_auth.SiteAuthMiddleware(app)
    rec = Recorder()
    run(lambda: mw(scope("/", f"devbim_auth={good}"), idle_receive, rec))
    assert called == ["/"], "верная кука должна пропускать запрос в приложение"

    # 6. Просрочено -> POST /auth/login не пускает даже с верным паролем
    write_env(SITE_PASSWORD="pw", SITE_VALID_UNTIL="2020-01-01")
    mw = site_auth.SiteAuthMiddleware(app)
    rec = Recorder()

    async def recv_login():
        return {"type": "http.request", "body": b"password=pw", "more_body": False}

    run(lambda: mw(scope("/auth/login", ""), recv_login, rec))
    assert rec.status == 200
    assert "DevBIM".encode() in rec.body, "должна быть страница «лицензия истекла»"

    print("OK")
finally:
    # --- очистка os.environ, cwd и tmp ---
    os.chdir(prev_cwd)
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    shutil.rmtree(tmp, ignore_errors=True)
