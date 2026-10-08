# -*- coding: utf-8 -*-
"""Настройки Design Code и владельца в админ-панели (п.73):
персональные URL/код пользователя, общие settings, пароль владельца,
ключ IR; приоритеты цепочки design_code_router.

Запуск: venv\\Scripts\\python.exe tests\\test_admin_designcode.py
"""
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "siteauth"))
sys.path.insert(0, str(ROOT / "design_code"))
import studio_store  # noqa: E402
import site_auth  # noqa: E402
import design_code_router as dcr  # noqa: E402

site_auth.studio_store = studio_store  # локальная копия (как test_userauth_admin)
dcr._store = lambda: studio_store     # роутер — на ту же герметичную копию

tmp = Path(tempfile.mkdtemp(prefix="admin_dc_"))
os.environ["INVOKEAI_ROOT"] = str(tmp)
os.chdir(tmp)
(tmp / ".env").write_text(
    "STUDIO_AUTH_MODE=users\nSITE_PASSWORD=owner-pass\nSTUDIO_SESSION_SECRET=" + "S" * 40 + "\n"
    "DESIGN_CODE_URL=https://env-site.dev-bim.com/\nDESIGN_CODE_ACCESS_CODE=envcode\n",
    encoding="utf-8")
for k in ("STUDIO_AUTH_MODE", "SITE_PASSWORD", "STUDIO_SESSION_SECRET", "SITE_VALID_UNTIL",
          "DESIGN_CODE_URL", "DESIGN_CODE_ACCESS_CODE"):
    os.environ.pop(k, None)


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


async def call(method, path, body=b"", cookie=""):
    rec = Rec()
    mw = site_auth.SiteAuthMiddleware(rec)
    await mw({"type": "http", "method": method, "path": path,
              "headers": [(b"content-type", b"application/json")] +
                         ([(b"cookie", cookie.encode("latin-1"))] if cookie else []),
              "query_string": b"", "root_path": ""},
             await _recv(body), rec._send)
    return rec


def jbody(**kw):
    return json.dumps(kw).encode()


async def main():
    studio_store.init_db()

    from urllib.parse import quote as _q
    admin = await call("POST", "/auth/login",
                       ("email=&password=" + _q("owner-pass")).encode())
    assert admin.status == 303, admin.status
    admin_cookie = admin.headers().get("set-cookie", "").split(";")[0]

    studio_store.create_user("client@x.ru", "", "clientpass1", "user")
    uid = studio_store.find_user_by_email("client@x.ru")["user_id"]
    client = await call("POST", "/auth/login",
                        ("email=client@x.ru&password=" + _q("clientpass1")).encode())
    client_cookie = client.headers().get("set-cookie", "").split(";")[0]

    # --- гейты: без сессии 401, не-админ 403 ---
    r = await call("GET", "/admin/api/settings/designcode")
    assert r.status == 401, r.status
    r = await call("POST", "/admin/api/users/x/designcode", jbody(url="", code=""), cookie=client_cookie)
    assert r.status == 403, r.status

    # --- персональные настройки Design Code ---
    r = await call("POST", f"/admin/api/users/{quote(uid)}/designcode",
                   jbody(url="https://nw.dev-bim.com/", code="nw2026"), cookie=admin_cookie)
    assert r.status == 200, (r.status, r.body())
    u = studio_store.get_user(uid)
    assert u["dc_url"] == "https://nw.dev-bim.com/" and u["dc_code"] == "nw2026", u

    # кривой URL -> 422; слишком длинный код -> 422
    r = await call("POST", f"/admin/api/users/{quote(uid)}/designcode",
                   jbody(url="nw.dev-bim.com", code="x"), cookie=admin_cookie)
    assert r.status == 422, r.status
    r = await call("POST", f"/admin/api/users/{quote(uid)}/designcode",
                   jbody(url="", code="c" * 300), cookie=admin_cookie)
    assert r.status == 422, r.status

    # GET /admin/api/users отдаёт dc_url/dc_code
    r = await call("GET", "/admin/api/users", cookie=admin_cookie)
    row = next(x for x in json.loads(r.body())["users"] if x["user_id"] == uid)
    assert row["dc_url"] == "https://nw.dev-bim.com/" and row["dc_code"] == "nw2026", row
    assert "password_hash" not in row and "ir_token" not in row  # секреты по-прежнему не светятся

    # очистка персональных
    r = await call("POST", f"/admin/api/users/{quote(uid)}/designcode",
                   jbody(url="", code=""), cookie=admin_cookie)
    assert r.status == 200, r.status
    u = studio_store.get_user(uid)
    assert u["dc_url"] is None and u["dc_code"] is None, u

    # --- общие настройки Design Code ---
    r = await call("GET", "/admin/api/settings/designcode", cookie=admin_cookie)
    assert r.status == 200 and json.loads(r.body()) == {"url": "", "code": ""}, r.body()
    r = await call("POST", "/admin/api/settings/designcode",
                   jbody(url="https://common.dev-bim.com/", code="commoncode"), cookie=admin_cookie)
    assert r.status == 200, r.status
    r = await call("GET", "/admin/api/settings/designcode", cookie=admin_cookie)
    assert json.loads(r.body()) == {"url": "https://common.dev-bim.com/", "code": "commoncode"}
    r = await call("POST", "/admin/api/settings/designcode",
                   jbody(url="ftp://x", code=""), cookie=admin_cookie)
    assert r.status == 422, r.status

    # --- пароль владельца: задаётся из админки, вход по нему работает ---
    r = await call("POST", "/admin/api/settings/site-password",
                   jbody(password="short"), cookie=admin_cookie)
    assert r.status == 422, r.status
    r = await call("POST", "/admin/api/settings/site-password",
                   jbody(password="new-owner-pass-1"), cookie=admin_cookie)
    assert r.status == 200, r.status
    assert site_auth._site_password() == "new-owner-pass-1"
    old = await call("POST", "/auth/login",
                     ("email=&password=" + _q("owner-pass")).encode())
    assert old.status == 401, "старый пароль должен перестать работать"
    new = await call("POST", "/auth/login",
                     ("email=&password=" + _q("new-owner-pass-1")).encode())
    assert new.status == 303, new.status

    # --- ключ IR: пишется в settings, очистка возвращает .env-цепочку ---
    r = await call("POST", "/admin/api/settings/ir-key",
                   jbody(key="sk-from-admin"), cookie=admin_cookie)
    assert r.status == 200, r.status
    assert studio_store.get_setting("imagerouter_api_key") == "sk-from-admin"
    r = await call("POST", "/admin/api/settings/ir-key", jbody(key=""), cookie=admin_cookie)
    assert r.status == 200, r.status
    assert studio_store.get_setting("imagerouter_api_key") is None

    # --- таблица settings: пустое значение удаляется ---
    studio_store.set_setting("design_code_access_code", "")
    assert studio_store.get_setting("design_code_access_code") is None
    studio_store.set_setting("design_code_access_code", "tmp")
    assert studio_store.get_setting("design_code_access_code") == "tmp"

    # --- цепочки design_code_router: персональный > общий > .env ---
    studio_store.set_setting("design_code_url", "https://common.dev-bim.com/")
    studio_store.set_setting("design_code_access_code", "commoncode")
    studio_store.set_design_code(uid, "https://nw.dev-bim.com/", "nw2026")

    assert dcr._access_code(uid) == "nw2026"          # персональный
    assert dcr._default_url(uid) == "https://nw.dev-bim.com/"
    assert dcr._access_code() == "commoncode"         # аноним: общий
    assert dcr._default_url() == "https://common.dev-bim.com/"

    studio_store.set_design_code(uid, "", "")         # персональных нет — общие
    assert dcr._access_code(uid) == "commoncode"
    assert dcr._default_url(uid) == "https://common.dev-bim.com/"

    studio_store.set_setting("design_code_url", "")   # общих нет — .env
    studio_store.set_setting("design_code_access_code", "")
    assert dcr._access_code(uid) == "envcode"
    assert dcr._default_url(uid) == "https://env-site.dev-bim.com/"
    assert dcr._access_code() == "envcode"

    # поля независимы: персональный код без персонального URL
    studio_store.set_design_code(uid, "", "personal-code")
    assert dcr._access_code(uid) == "personal-code"
    assert dcr._default_url(uid) == "https://env-site.dev-bim.com/"

    # --- password-режим: персональных настроек нет (заголовок не инжектится) ---
    (tmp / ".env").write_text(
        "STUDIO_AUTH_MODE=password\nSITE_PASSWORD=p\nDESIGN_CODE_ACCESS_CODE=envcode\n",
        encoding="utf-8")
    studio_store.set_design_code(uid, "https://nw.dev-bim.com/", "nw2026")
    assert dcr._user_cfg(uid) is None, "в password-режиме персональные настройки не действуют"
    assert dcr._access_code(uid) == "envcode"
    (tmp / ".env").write_text(
        "STUDIO_AUTH_MODE=users\nSITE_PASSWORD=p\nDESIGN_CODE_ACCESS_CODE=envcode\n",
        encoding="utf-8")

    # --- admin-local без строки в users — работает на общих ---
    assert dcr._user_cfg("admin-local") is None
    assert dcr._access_code("admin-local") == "envcode"

    # --- POST /auth с заголовком пользователя: персональный код проверяется ---
    studio_store.set_design_code(uid, "", "personal-code")
    body = dcr.AuthBody(url="https://nw.dev-bim.com/", code="personal-code")
    r = dcr.auth(body, x_studio_user=uid)
    assert r["ok"] is True and r["protected"] is True, r
    try:
        dcr.auth(dcr.AuthBody(url="https://nw.dev-bim.com/", code="commoncode"), x_studio_user=uid)
        raise AssertionError("чужой код не должен проходить")
    except Exception as e:
        assert getattr(e, "status_code", None) == 401, e

    # --- admin-панель: ключевые конструкции страницы ---
    page = site_auth._ADMIN_PAGE
    for frag in ("Общие настройки", "dccell", "dcmodal", "dcMSave", "dcMClear",
                 "/admin/api/settings/designcode", "/admin/api/settings/site-password",
                 "/admin/api/settings/ir-key", "users/"):
        assert frag in page, frag
    import re as _re
    import subprocess as _sp
    import tempfile as _tf
    m = _re.search(r"<script>(.*?)</script>", page, _re.S)
    assert m, "скрипт админ-страницы не найден"
    with _tf.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as fh:
        fh.write(m.group(1))
        chk = fh.name
    try:
        r = _sp.run(["node", "--check", chk], capture_output=True, text=True)
        assert r.returncode == 0, "syntax error в _ADMIN_PAGE:\n" + r.stderr
    finally:
        import os as _os
        _os.unlink(chk)

    print("OK")


if __name__ == "__main__":
    asyncio.run(main())
