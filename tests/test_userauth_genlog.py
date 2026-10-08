# -*- coding: utf-8 -*-
"""Журнал генераций (п.67): studio_store.gen_log, админ-API /admin/api/genlog
и gen-поля /admin/api/users, запись из enqueue-ветки ImageRouterCanvasMiddleware.

Запуск: venv\\Scripts\\python.exe tests\\test_userauth_genlog.py
"""
import asyncio
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "siteauth"))
sys.path.insert(0, str(ROOT / "imagerouter"))

tmp = Path(tempfile.mkdtemp(prefix="userauth_genlog_"))
os.environ["INVOKEAI_ROOT"] = str(tmp)
(tmp / ".env").write_text(
    "STUDIO_AUTH_MODE=users\nSITE_PASSWORD=owner-pass\nSTUDIO_SESSION_SECRET=" + "S" * 40 + "\n",
    encoding="utf-8")
for k in ("STUDIO_AUTH_MODE", "SITE_PASSWORD", "STUDIO_SESSION_SECRET", "STUDIO_VALID_UNTIL"):
    os.environ.pop(k, None)

import studio_store  # noqa: E402
import site_auth  # noqa: E402

site_auth.studio_store = studio_store  # локальная копия (см. test_userauth_admin)

import imagerouter_router as ir  # noqa: E402

ir._studio_store = lambda: studio_store  # tmp-БД, не задеплоенная копия


# ---------- харнесс site_auth (как test_userauth_admin) ----------
class Rec:
    def __init__(self):
        self.events = []

    async def _send(self, msg):
        self.events.append(msg)

    @property
    def status(self):
        return next(m["status"] for m in self.events if m["type"] == "http.response.start")

    def headers(self):
        return {k.decode().lower(): v.decode("latin-1")
                for m in self.events if m["type"] == "http.response.start"
                for k, v in m.get("headers", [])}

    def body(self):
        return b"".join(m.get("body", b"") for m in self.events
                        if m["type"] == "http.response.body")


async def _recv(body=b""):
    sent = False

    async def rcv():
        nonlocal sent
        if sent:
            await asyncio.sleep(3600)
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    return rcv


def scope_of(method, path, cookie="", qs=b""):
    h = [(b"content-type", b"application/json")]
    if cookie:
        h.append((b"cookie", cookie.encode("latin-1")))
    return {"type": "http", "method": method, "path": path, "headers": h,
            "query_string": qs, "root_path": ""}


async def call(method, path, body=b"", cookie="", qs=b""):
    rec = Rec()
    mw = site_auth.SiteAuthMiddleware(rec)
    await mw(scope_of(method, path, cookie=cookie, qs=qs), await _recv(body), rec._send)
    return rec


# ---------- 1. studio_store: log_generation / gen_stats / gen_log_list ----------
def test_store():
    studio_store.init_db()
    uid = "u_abc"
    studio_store.log_generation(uid, "txt2img", "openai/gpt-image", "ok",
                                images=2, cost_usd=0.02, duration_s=8.5)
    studio_store.log_generation(uid, "inpaint", "openai/gpt-image", "ok",
                                images=1, cost_usd=0.01, duration_s=4.0)
    studio_store.log_generation(uid, "upscale", "x/up", "error",
                                images=0, duration_s=1.2, error="x" * 800)
    studio_store.log_generation("admin-local", "txt2img", "no-price/model", "ok",
                                images=1, duration_s=3.0)

    st = studio_store.gen_stats(uid)
    assert st["total"] == 3 and st["ok"] == 2 and st["failed"] == 1, st
    assert st["images"] == 3, st
    assert abs(st["cost_usd"] - 0.03) < 1e-9, st
    assert st["avg_s"] is not None and abs(st["avg_s"] - 6.25) < 1e-9, st  # только успешные
    assert st["last_ts"] is not None, st

    # цены нет ни у одной строки -> cost_usd None (не 0)
    other = "u_noprice"
    studio_store.log_generation(other, "txt2img", "m", "ok", images=1)
    assert studio_store.gen_stats(other)["cost_usd"] is None

    rows = studio_store.gen_log_list(uid)
    assert len(rows) == 3, rows
    assert rows[0]["kind"] == "upscale" and rows[0]["status"] == "error", rows[0]
    assert len(rows[0]["error"]) == 500, "текст ошибки обрезается до 500 символов"
    assert rows[2]["cost_usd"] == 0.02, rows[2]

    # фильтр по пользователю и лимит
    assert all(r["user_id"] == uid for r in studio_store.gen_log_list(uid, limit=2))
    assert len(studio_store.gen_log_list(None, limit=2)) == 2
    assert len(studio_store.gen_log_list()) == 5  # 3 uid + admin-local + u_noprice

    # кап журнала: GEN_LOG_CAP читается в рантайме (прун при записи)
    studio_store.GEN_LOG_CAP = 6
    for i in range(10):
        studio_store.log_generation("u_cap", "txt2img", "m", "ok", images=1)
    assert len(studio_store.gen_log_list("u_cap")) == 6
    print("OK: store — журнал, статистика, прун")


# ---------- 2. админ-API: gen-поля и /admin/api/genlog ----------
async def test_admin_api():
    studio_store.create_user("gen@x.ru", "", "parol12345", "user")
    uid = studio_store.find_user_by_email("gen@x.ru")["user_id"]
    studio_store.log_generation(uid, "txt2img", "openai/gpt-image", "ok",
                                images=2, cost_usd=0.02, duration_s=8.0)
    studio_store.log_generation("admin-local", "upscale", "x/up", "error",
                                images=0, duration_s=1.0, error="boom")

    admin = await call("POST", "/auth/login",
                       ("email=&password=" + quote("owner-pass")).encode())
    assert admin.status == 303, admin.status
    admin_cookie = admin.headers().get("set-cookie", "").split(";")[0]

    r = await call("GET", "/admin/api/users", cookie=admin_cookie)
    assert r.status == 200, r.status
    data = json.loads(r.body())
    by_email = {u["email"]: u for u in data["users"]}
    g = by_email["gen@x.ru"]["gen"]
    assert g["total"] == 1 and g["ok"] == 1 and g["cost_usd"] == 0.02, g
    assert data["owner_gen"]["total"] == 1 and data["owner_gen"]["failed"] == 1, data["owner_gen"]

    r = await call("GET", "/admin/api/genlog",
                   cookie=admin_cookie, qs=("user=" + quote(uid)).encode())
    assert r.status == 200, r.status
    items = json.loads(r.body())["items"]
    assert len(items) == 1 and items[0]["user_id"] == uid and items[0]["model"] == "openai/gpt-image"

    # без фильтра — все; лимит работает; новые сверху
    r = await call("GET", "/admin/api/genlog", cookie=admin_cookie, qs=b"limit=1")
    items = json.loads(r.body())["items"]
    assert len(items) == 1 and items[0]["user_id"] == "admin-local", items

    # кривой лимит не роняет эндпоинт
    r = await call("GET", "/admin/api/genlog", cookie=admin_cookie, qs=b"limit=abc")
    assert r.status == 200, r.status

    # гейты: без сессии 401, не-админ 403
    r = await call("GET", "/admin/api/genlog")
    assert r.status == 401, r.status
    plain = await call("POST", "/auth/login",
                       ("email=gen@x.ru&password=" + quote("parol12345")).encode())
    plain_cookie = plain.headers().get("set-cookie", "").split(";")[0]
    r = await call("GET", "/admin/api/genlog", cookie=plain_cookie)
    assert r.status == 403, r.status

    # страница панели: колонки и кнопки журнала
    r = await call("GET", "/admin", cookie=admin_cookie)
    html = r.body().decode("utf-8")
    assert r.status == 200 and "Журнал всех генераций" in html and "Генерации ок/ош" in html, r.status
    print("OK: админ-API — gen-поля, /admin/api/genlog, гейты 401/403")


# ---------- 3. роутер: _gen_log_entry + enqueue-ветка мидлвари ----------
def _batch(model_key="imagerouter/test/m1"):
    return {"batch": {"runs": 1, "graph": {"id": "sess-1", "nodes": {
        "n1": {"id": "n1", "type": "sdxl_model_loader", "model": {"key": model_key}}
    }}}}


class Rec2(Rec):
    pass


def test_gen_log_entry():
    uid = "u_router"
    # цена только из кэша каталога (сетевых запросов из журнала нет — грабля
    # заморозки event loop); инжектим кэш, а не _ir_model_by_id
    ir._ir_models_cache = {"items": [{"id": "test/m1", "pricing": {"average": 0.01}}],
                           "ts": time.time()}
    ir._gen_log_entry(uid, {"model_key": "imagerouter/test/m1", "mode": "txt2img"},
                      "ok", images=2, duration_s=5.0)
    row = studio_store.gen_log_list(uid)[0]
    assert row["model"] == "test/m1" and row["kind"] == "txt2img", row
    assert row["status"] == "ok" and row["images"] == 2 and row["cost_usd"] == 0.02, row

    # цены нет в каталоге -> cost None, строка всё равно пишется
    ir._gen_log_entry(uid, {"model_key": "imagerouter/unknown/m9", "mode": "img2img"},
                      "ok", images=1, duration_s=2.0)
    row = studio_store.gen_log_list(uid)[0]
    assert row["cost_usd"] is None and row["kind"] == "img2img", row

    # каталог не в кэше -> журнал НЕ ходит в сеть (грабля: сетевой запрос из
    # async-мидлвари замораживал event loop до TIMEOUT_SHORT)
    saved_fetch = ir._fetch_ir_models

    def _no_fetch(force=False):
        raise AssertionError("журнал не должен ходить в сеть за каталогом")

    ir._fetch_ir_models = _no_fetch
    try:
        ir._ir_models_cache = {"items": [], "ts": 0.0}
        ir._gen_log_entry(uid, {"model_key": "imagerouter/test/m1"}, "ok",
                          images=1, duration_s=1.0)
        row = studio_store.gen_log_list(uid)[0]
        assert row["status"] == "ok" and row["cost_usd"] is None, row
    finally:
        ir._fetch_ir_models = saved_fetch
        ir._ir_models_cache = {"items": [{"id": "test/m1", "pricing": {"average": 0.01}}],
                               "ts": time.time()}

    # ошибка: без стоимости, с текстом
    ir._gen_log_entry(uid, {"model_key": "imagerouter/test/m1", "mode": "txt2img"},
                      "error", images=0, duration_s=0.4, error="boom")
    row = studio_store.gen_log_list(uid)[0]
    assert row["status"] == "error" and row["cost_usd"] is None and row["error"] == "boom", row

    # апскейл: kind/model из upscale_model_key
    ir._gen_log_entry(uid, {"is_upscale": True, "model_key": "imagerouter/main/x",
                            "upscale_model_key": "imagerouter-upscale/up/m2"},
                      "ok", images=1, duration_s=3.0)
    row = studio_store.gen_log_list(uid)[0]
    assert row["kind"] == "upscale" and row["model"] == "up/m2", row

    # без пользователя (password-режим) журнал не пишется
    n = len(studio_store.gen_log_list())
    ir._gen_log_entry(None, {"model_key": "imagerouter/test/m1"}, "ok", 1, 1.0)
    assert len(studio_store.gen_log_list()) == n
    print("OK: роутер — _gen_log_entry (цена/без цены/ошибка/апскейл/без пользователя)")


async def test_middleware_enqueue():
    ir.get_config = lambda: SimpleNamespace(root_path=str(tmp))  # дамп графа — в tmp
    uid = "u_mw"
    body = json.dumps(_batch()).encode()
    scope = {"type": "http", "method": "POST", "path": "/api/v1/queue/Q1/enqueue_batch",
             "headers": [(b"content-type", b"application/json"),
                         (b"x-studio-user", uid.encode())],
             "query_string": b"", "root_path": ""}

    async def run(fake_handler):
        saved = ir._handle_canvas_generation
        ir._handle_canvas_generation = fake_handler
        try:
            rec = Rec2()
            await ir.ImageRouterCanvasMiddleware(rec)(scope, await _recv(body), rec._send)
            return rec
        finally:
            ir._handle_canvas_generation = saved

    # успех: item_ids -> ok-запись с ценой и длительностью
    def fake_ok(queue_id, payload, studio_user):
        assert studio_user == uid
        return {"queue_id": queue_id, "item_ids": [0, 0]}

    rec = await run(fake_ok)
    assert rec.status == 200, (rec.status, rec.body())
    row = studio_store.gen_log_list(uid)[0]
    assert row["status"] == "ok" and row["images"] == 2 and row["cost_usd"] == 0.02, row
    assert row["duration_s"] >= 0, row  # фейковый хендлер мгновенный; у живых — секунды

    # ошибка _IRClientError -> 422 тосту UI + error-запись
    def fake_fail(queue_id, payload, studio_user):
        raise ir._IRClientError("boom", 400)

    rec = await run(fake_fail)
    assert rec.status == 422, rec.status
    assert json.loads(rec.body())["detail"][0]["msg"] == "boom"
    row = studio_store.gen_log_list(uid)[0]
    assert row["status"] == "error" and row["error"] == "boom" and row["images"] == 0, row

    # неожиданное исключение -> тоже error-запись
    def fake_crash(queue_id, payload, studio_user):
        raise RuntimeError("surprise")

    rec = await run(fake_crash)
    assert rec.status == 422, rec.status
    row = studio_store.gen_log_list(uid)[0]
    assert row["status"] == "error" and "surprise" in row["error"], row
    print("OK: мидлварь — enqueue ok/error пишутся в журнал, UI-ответ не меняется")


async def main():
    test_store()
    await test_admin_api()
    test_gen_log_entry()
    await test_middleware_enqueue()
    print("OK")


asyncio.run(main())
