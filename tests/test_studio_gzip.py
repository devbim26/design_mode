# -*- coding: utf-8 -*-
"""C1 (финальное ревью): порядок SiteAuth/GZip — фильтрация списков под сжатием.

Правильный порядок add_middleware в api_app.py (GZip добавлен ПОЗЖЕ ->
снаружи): GZipMiddleware(SiteAuthMiddleware(app)). Тогда SiteAuth правит
несжатый JSON, GZip сжимает уже отфильтрованный ответ. Обратный порядок
(SiteAuth снаружи — баг до фикса) воспроизведён ниже: SiteAuth видит
gzip-байты, пропускает их с предупреждением (не-JSON passthrough, fix A).

Также: fail-closed мутатор (fix A) и order-aware патч api_app.py
(setup_site_auth.patch_api_app, fix C1).

Запуск: venv\\Scripts\\python.exe tests\\test_studio_gzip.py
"""
import asyncio
import contextlib
import gzip
import io
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # setup_site_auth
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "siteauth"))
from starlette.middleware.gzip import GZipMiddleware
import studio_store
import site_auth
import setup_site_auth

SECRET = "g" * 40
tmp = Path(tempfile.mkdtemp(prefix="studio_gzip_test_"))
saved = {k: os.environ.get(k) for k in ("INVOKEAI_ROOT", "STUDIO_AUTH_MODE", "STUDIO_JWT_SECRET",
                                        "STUDIO_SESSION_SECRET", "STUDIO_SESSION_TTL",
                                        "SITE_PASSWORD", "SITE_VALID_UNTIL")}
prev_cwd = os.getcwd()


def run(c):
    return asyncio.new_event_loop().run_until_complete(c)


class Rec:
    def __init__(self):
        self.status = None
        self.headers = []
        self.body = b""

    async def __call__(self, m):
        if m["type"] == "http.response.start":
            self.status, self.headers = m["status"], m.get("headers", [])
        elif m["type"] == "http.response.body":
            self.body += m.get("body", b"")

    def json(self):
        return json.loads(self.body or b"{}")


def idle(body=b""):
    async def rcv():
        return {"type": "http.request", "body": body, "more_body": False}
    return rcv


def scope(path, method="GET", cookie=""):
    # браузер всегда шлёт accept-encoding: gzip — GZip сработает на >1000b
    h = [(b"accept-encoding", b"gzip")]
    if cookie:
        h.append((b"cookie", cookie.encode()))
    return {"type": "http", "path": path, "method": method, "headers": h}


def session(uid):
    return f"devbim_session={studio_store.mint_session(uid, SECRET)}"


def boards_body():
    # два борда (свой + чужой), JSON заведомо >1000 байт — GZip сожмёт
    return {"items": [
        {"board_id": "gz-mine", "board_name": "Mine", "filler": "x" * 600},
        {"board_id": "gz-foreign", "board_name": "Foreign", "filler": "y" * 600},
    ], "offset": 0, "limit": 10, "total": 2}


async def inner(scope, receive, send):
    raw = json.dumps(boards_body()).encode()
    await send({"type": "http.response.start", "status": 200,
                "headers": [(b"content-type", b"application/json")]})
    await send({"type": "http.response.body", "body": raw})


try:
    os.environ["INVOKEAI_ROOT"] = str(tmp)
    # герметичность: env_value сканирует и cwd/.env — без chdir тест из корня
    # репо возьмёт боевой STUDIO_SESSION_SECRET для проверки сессии (minted
    # другим секретом -> 401)
    os.chdir(tmp)
    os.environ.pop("STUDIO_SESSION_SECRET", None)
    (tmp / ".env").write_text(
        f"STUDIO_AUTH_MODE=sso\nSTUDIO_JWT_SECRET={SECRET}\nSTUDIO_SESSION_SECRET={SECRET}\n"
        f"STUDIO_SESSION_TTL=3600\n"
        "SITE_PASSWORD=pw\nSITE_VALID_UNTIL=2030-01-01\n", encoding="utf-8")
    studio_store.init_db()
    studio_store.upsert_user("u1", "u1@x.io", "One", "user")
    studio_store.upsert_user("u2", "u2@x.io", "Two", "user")
    studio_store.tag("board", "gz-mine", "u1")
    studio_store.tag("board", "gz-foreign", "u2")
    c1 = session("u1")

    # 1. правильный порядок (как в api_app.py после фикса): GZip снаружи —
    #    фильтрация работает, клиент получает сжатый уже отфильтрованный ответ
    app = GZipMiddleware(site_auth.SiteAuthMiddleware(inner))
    r = Rec()
    run(app(scope("/api/v1/boards/", "GET", c1), idle(), r))
    assert r.status == 200, r.status
    enc = [v for k, v in r.headers if k.decode("latin-1").lower() == "content-encoding"]
    assert enc == [b"gzip"], r.headers
    d = json.loads(gzip.decompress(r.body))
    assert [b["board_id"] for b in d["items"]] == ["gz-mine"] and d["total"] == 1, d

    # 2. обратный порядок (баг до фикса C1): SiteAuth снаружи GZip — видит
    #    gzip-байты, не-JSON passthrough с громким предупреждением (fix A)
    buggy = site_auth.SiteAuthMiddleware(GZipMiddleware(inner))
    err = io.StringIO()
    r2 = Rec()
    with contextlib.redirect_stderr(err):
        run(buggy(scope("/api/v1/boards/", "GET", c1), idle(), r2))
    assert r2.status == 200, r2.status
    d2 = json.loads(gzip.decompress(r2.body))
    assert [b["board_id"] for b in d2["items"]] == ["gz-mine", "gz-foreign"], d2  # нефильтровано
    assert "non-JSON body" in err.getvalue(), err.getvalue()

    # 3. fix A: ошибка мутатора — fail-closed 502, тело наружу не уходит
    mw = site_auth.SiteAuthMiddleware(inner)
    r3 = Rec()
    err3 = io.StringIO()
    with contextlib.redirect_stderr(err3):
        run(mw._proxy_json(scope("/api/v1/boards/", "GET", c1), idle(), r3,
                           lambda d: 1 / 0))
    assert r3.status == 502 and r3.json() == {"detail": "studio filter error"}, (r3.status, r3.body)
    assert "mutator" in err3.getvalue(), err3.getvalue()

    # 4. fix C1 (деплой): patch_api_app order-aware — существующий патч с
    #    site_auth ПОСЛЕ GZip переносится ПЕРЕД GZip; повтор — уже правильно
    syn = tmp / "api_app_syn.py"
    syn.write_text(
        "from invokeai.app.api.routers import (\n"
        "    imagerouter,\n"
        "    site_auth,\n"
        ")\n"
        "app = FastAPI()\n"
        "app.add_middleware(CORSMiddleware)\n"
        "app.add_middleware(GZipMiddleware, minimum_size=1000)\n"
        "app.add_middleware(site_auth.SiteAuthMiddleware)\n",
        encoding="utf-8")
    setup_site_auth.API_APP = syn
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        setup_site_auth.patch_api_app()
    lines = [ln.strip() for ln in syn.read_text(encoding="utf-8").splitlines()]
    assert lines.index("app.add_middleware(site_auth.SiteAuthMiddleware)") < \
        lines.index("app.add_middleware(GZipMiddleware, minimum_size=1000)"), lines
    with contextlib.redirect_stdout(out):
        setup_site_auth.patch_api_app()  # второй запуск: порядок уже верный
    assert "уже пропатчен" in out.getvalue(), out.getvalue()

    print("OK")
finally:
    os.chdir(prev_cwd)
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
