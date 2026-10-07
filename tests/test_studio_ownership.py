# -*- coding: utf-8 -*-
"""Тесты изоляции API: тегирование upload/бордов, фильтрация списков, 404 чужого.

Запуск: venv\\Scripts\\python.exe tests\\test_studio_ownership.py
"""
import asyncio
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "siteauth"))
import jwt as pyjwt
import studio_store
import site_auth

SECRET = "o" * 40
tmp = Path(tempfile.mkdtemp(prefix="studio_own_test_"))
saved = {k: os.environ.get(k) for k in ("INVOKEAI_ROOT", "STUDIO_AUTH_MODE", "STUDIO_JWT_SECRET",
                                        "STUDIO_SESSION_TTL", "SITE_PASSWORD", "SITE_VALID_UNTIL")}


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
    # фабрика ASGI-receive: отдаёт тело один раз (callable, как требует _read_body)
    async def rcv():
        return {"type": "http.request", "body": body, "more_body": False}
    return rcv


def scope(path, method="GET", cookie=""):
    h = [(b"cookie", cookie.encode())] if cookie else []
    return {"type": "http", "path": path, "method": method, "headers": h}


def session(uid):
    return f"devbim_session={studio_store.mint_session(uid, SECRET)}"


# внутреннее приложение с «заготовленными» ответами InvokeAI
STATE = {"boards": [], "images": []}


async def inner(scope, receive, send):
    path, method = scope["path"], scope["method"]
    if path == "/api/v1/boards/" and method == "GET":
        body = {"items": STATE["boards"], "offset": 0, "limit": 10, "total": len(STATE["boards"])}
    elif path == "/api/v1/boards/" and method == "POST":
        body = {"board_id": "new-board", "board_name": "Test"}
    elif path == "/api/v1/images/" and method == "GET":
        body = {"items": STATE["images"], "offset": 0, "limit": 10, "total": len(STATE["images"])}
    elif path == "/api/v1/images/upload" and method == "POST":
        body = {"image_name": "new-upload.png"}
    else:
        await send({"type": "http.response.start", "status": 200,
                    "headers": [(b"content-type", b"application/json")]})
        await send({"type": "http.response.body", "body": b'{"upstream":true}'})
        return
    raw = json.dumps(body).encode()
    await send({"type": "http.response.start", "status": 200,
                "headers": [(b"content-type", b"application/json"),
                            (b"content-length", str(len(raw)).encode())]})
    await send({"type": "http.response.body", "body": raw})


try:
    os.environ["INVOKEAI_ROOT"] = str(tmp)
    # STUDIO_SESSION_SECRET задаём явно: иначе env_value дотянется до .env
    # репозитория (кандидат cwd/.env) и подпись тестовых кук не сойдётся
    (tmp / ".env").write_text(
        f"STUDIO_AUTH_MODE=sso\nSTUDIO_JWT_SECRET={SECRET}\nSTUDIO_SESSION_SECRET={SECRET}\n"
        f"STUDIO_SESSION_TTL=3600\n"
        "SITE_PASSWORD=pw\nSITE_VALID_UNTIL=2030-01-01\n", encoding="utf-8")
    studio_store.init_db()
    studio_store.upsert_user("u1", "u1@x.io", "One", "user")
    studio_store.upsert_user("u2", "u2@x.io", "Two", "user")
    studio_store.upsert_user("adm", "adm@x.io", "Adm", "admin")
    mw = site_auth.SiteAuthMiddleware(inner)

    c1, c2, cadm = session("u1"), session("u2"), session("adm")

    # 1. создание борда тегируется
    r = Rec()
    run(mw(scope("/api/v1/boards/", "POST", c1), idle(b"{}"), r))
    assert r.status == 200 and studio_store.owner("board", "new-board") == "u1"

    # 2. upload тегируется
    r = Rec()
    run(mw(scope("/api/v1/images/upload", "POST", c1), idle(b""), r))
    assert r.status == 200 and studio_store.owner("image", "new-upload.png") == "u1"

    # 3. списки фильтруются
    STATE["boards"] = [{"board_id": "new-board"}, {"board_id": "u2-board"}]
    studio_store.tag("board", "u2-board", "u2")
    r = Rec()
    run(mw(scope("/api/v1/boards/", "GET", c1), idle(), r))
    d = r.json()
    assert [b["board_id"] for b in d["items"]] == ["new-board"] and d["total"] == 1, d

    STATE["images"] = [{"image_name": "new-upload.png"}, {"image_name": "u2.png"},
                       {"image_name": "legacy.png"}]
    studio_store.tag("image", "u2.png", "u2")
    r = Rec()
    run(mw(scope("/api/v1/images/", "GET", c1), idle(), r))
    d = r.json()
    assert [i["image_name"] for i in d["items"]] == ["new-upload.png"] and d["total"] == 1, d

    # админ видит всё, включая легаси
    r = Rec()
    run(mw(scope("/api/v1/images/", "GET", cadm), idle(), r))
    assert len(r.json()["items"]) == 3

    # 4. прямой доступ к чужой картинке -> 404, к своей -> проксируется
    r = Rec()
    run(mw(scope("/api/v1/images/i/u2.png/full", "GET", c1), idle(), r))
    assert r.status == 404, r.status
    r = Rec()
    run(mw(scope("/api/v1/images/i/new-upload.png/full", "GET", c1), idle(), r))
    assert r.status == 200 and r.json() == {"upstream": True}
    r = Rec()  # легаси без владельца: не-админу 404
    run(mw(scope("/api/v1/images/i/legacy.png/full", "GET", c1), idle(), r))
    assert r.status == 404
    r = Rec()
    run(mw(scope("/api/v1/images/i/legacy.png/full", "GET", cadm), idle(), r))
    assert r.status == 200

    # 5. body-эндпоинты: чужое имя -> 403
    r = Rec()
    run(mw(scope("/api/v1/images/delete", "POST", c1), idle(json.dumps({"image_names": ["u2.png"]}).encode()), r))
    assert r.status == 403, r.status
    r = Rec()
    run(mw(scope("/api/v1/images/star", "POST", c1), idle(json.dumps({"image_names": ["new-upload.png"]}).encode()), r))
    assert r.status == 200

    # 6. запись style_presets/workflows: user -> 403, admin -> проксируется
    r = Rec()
    run(mw(scope("/api/v1/style_presets/i/x", "PUT", c1), idle(b"{}"), r))
    assert r.status == 403, r.status
    r = Rec()
    run(mw(scope("/api/v1/workflows/", "POST", c1), idle(b"{}"), r))
    assert r.status == 403
    r = Rec()
    run(mw(scope("/api/v1/style_presets/i/x", "PUT", cadm), idle(b"{}"), r))
    assert r.status == 200

    # 7. очередь фильтруется по batch-владельцу (реальные пути 6.2.0:
    #    queue/{id}/list -> {items:[...]}, queue/{id}/list_all -> голый список)
    async def q_inner(scope, receive, send):
        if scope["path"].endswith("list_all"):
            payload = [{"batch_id": "b1"}, {"batch_id": "b2"}]
        else:
            payload = {"items": [{"batch_id": "b1"}, {"batch_id": "b2"}], "total": 2}
        raw = json.dumps(payload).encode()
        await send({"type": "http.response.start", "status": 200,
                    "headers": [(b"content-type", b"application/json")]})
        await send({"type": "http.response.body", "body": raw})

    studio_store.tag("batch", "b1", "u1")
    studio_store.tag("batch", "b2", "u2")
    mwq = site_auth.SiteAuthMiddleware(q_inner)
    r = Rec()
    run(mwq(scope("/api/v1/queue/default/list", "GET", c1), idle(), r))
    d = r.json()
    assert [i["batch_id"] for i in d["items"]] == ["b1"] and d["total"] == 1, d
    r = Rec()
    run(mwq(scope("/api/v1/queue/default/list_all", "GET", c1), idle(), r))
    d = r.json()
    assert isinstance(d, list) and [i["batch_id"] for i in d] == ["b1"], d

    # 8. админ-панель: список пользователей и действия
    r = Rec()
    run(mw(scope("/admin/api/users", "GET", cadm), idle(), r))
    d = r.json()
    emails = {u["email"] for u in d["users"]}
    assert emails == {"u1@x.io", "u2@x.io"}, emails
    r = Rec()
    body = json.dumps({"role": "admin"}).encode()
    run(mw(scope("/admin/api/users/u2/role", "POST", cadm), idle(body), r))
    assert r.status == 200 and studio_store.effective_role("u2") == "admin"
    r = Rec()
    run(mw(scope("/admin/api/users/u2/role", "POST", c1), idle(body), r))
    assert r.status == 403, r.status  # не-админ не имеет доступа к /admin
    r = Rec()
    run(mw(scope("/admin/api/users/u2/role", "POST", cadm), idle(b"not-json{"), r))
    assert r.status == 422, r.status  # кривой JSON не мутирует состояние

    # 9. destructive-эндпоинты (финальное ревью I1)
    r = Rec()
    run(mw(scope("/api/v1/images/uncategorized", "DELETE", c1), idle(), r))
    assert r.status == 403, r.status  # массовая чистка — админу
    r = Rec()
    run(mw(scope("/api/v1/images/uncategorized", "DELETE", cadm), idle(), r))
    assert r.status == 200 and r.json() == {"upstream": True}
    r = Rec()
    body = json.dumps({"board_id": "new-board", "image_names": ["new-upload.png"]}).encode()
    run(mw(scope("/api/v1/board_images/batch", "POST", c1), idle(body), r))
    assert r.status == 200 and r.json() == {"upstream": True}  # всё своё -> проксируется
    r = Rec()
    body = json.dumps({"board_id": "new-board", "image_names": ["u2.png"]}).encode()
    run(mw(scope("/api/v1/board_images/batch", "POST", c1), idle(body), r))
    assert r.status == 403, r.status  # чужая картинка в списке
    r = Rec()
    run(mw(scope("/api/v1/queue/default/i/5", "DELETE", c1), idle(), r))
    assert r.status == 403, r.status  # пункты очереди (id без карты владения) — админу

    # 9b. массовые queue-операции — админу (follow-up N1; реальные пути 6.2.0)
    r = Rec()
    run(mw(scope("/api/v1/queue/default/clear", "PUT", c1), idle(), r))
    assert r.status == 403, r.status
    r = Rec()
    run(mw(scope("/api/v1/queue/default/processor/resume", "PUT", c1), idle(), r))
    assert r.status == 403, r.status
    r = Rec()
    run(mw(scope("/api/v1/queue/default/d/generation", "DELETE", c1), idle(), r))
    assert r.status == 403, r.status
    r = Rec()
    run(mw(scope("/api/v1/queue/default/clear", "PUT", cadm), idle(), r))
    assert r.status == 200 and r.json() == {"upstream": True}

    # 9c. batch/delete без board_id (реальное тело 6.2.0) — только владение
    #     картинками (follow-up N2: регрессия — всегда 403)
    r = Rec()
    body = json.dumps({"image_names": ["new-upload.png"]}).encode()
    run(mw(scope("/api/v1/board_images/batch/delete", "POST", c1), idle(body), r))
    assert r.status == 200 and r.json() == {"upstream": True}
    r = Rec()
    body = json.dumps({"image_names": ["u2.png"]}).encode()
    run(mw(scope("/api/v1/board_images/batch/delete", "POST", c1), idle(body), r))
    assert r.status == 403, r.status  # чужая картинка без board_id всё равно запрещена

    # 9d. единичный board_images (POST/DELETE, тело {board_id,image_name})
    #     под тем же гейтом (follow-up N3)
    r = Rec()
    body = json.dumps({"board_id": "new-board", "image_name": "new-upload.png"}).encode()
    run(mw(scope("/api/v1/board_images/", "POST", c1), idle(body), r))
    assert r.status == 200 and r.json() == {"upstream": True}  # всё своё
    r = Rec()
    body = json.dumps({"board_id": "u2-board", "image_name": "new-upload.png"}).encode()
    run(mw(scope("/api/v1/board_images/", "POST", c1), idle(body), r))
    assert r.status == 403, r.status  # чужой борд
    r = Rec()
    body = json.dumps({"board_id": "new-board", "image_name": "u2.png"}).encode()
    run(mw(scope("/api/v1/board_images/", "POST", c1), idle(body), r))
    assert r.status == 403, r.status  # чужая картинка
    r = Rec()
    body = json.dumps({"image_name": "u2.png"}).encode()  # DELETE без board_id
    run(mw(scope("/api/v1/board_images/", "DELETE", c1), idle(body), r))
    assert r.status == 403, r.status
    r = Rec()
    body = json.dumps({"image_name": "new-upload.png"}).encode()
    run(mw(scope("/api/v1/board_images/", "DELETE", c1), idle(body), r))
    assert r.status == 200 and r.json() == {"upstream": True}

    print("OK")
finally:
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
