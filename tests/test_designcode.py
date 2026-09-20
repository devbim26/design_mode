# -*- coding: utf-8 -*-
"""Тесты design_code: проверка кода доступа, валидация URL, патчи бандлов.

Запуск: venv\\Scripts\\python.exe tests\\test_designcode.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "design_code"))

import design_code_router as dcr  # noqa: E402
from fastapi import HTTPException  # noqa: E402


def expect(status, fn, *args):
    try:
        fn(*args)
    except HTTPException as e:
        assert e.status_code == status, (status, e.status_code, e.detail)
        return e
    raise AssertionError(f"ожидался HTTP {status}")


def main():
    # --- валидация URL ---
    assert dcr._check_url("https://nw.dev-bim.com/") == "https://nw.dev-bim.com/"
    assert dcr._check_url("  http://127.0.0.1:8020  ") == "http://127.0.0.1:8020"
    for bad in ("", "nw.dev-bim.com", "ftp://x", "file:///c:/x", "javascript:alert(1)"):
        expect(400, dcr._check_url, bad)
    expect(400, dcr._check_url, "https://" + "a" * 2100)

    body = dcr.AuthBody(url="https://nw.dev-bim.com/", code="nw2026")

    # --- код задан: верный/неверный (через _env_value — как в бою) ---
    dcr._env_value = lambda key: {"DESIGN_CODE_ACCESS_CODE": "nw2026"}.get(key)
    r = dcr.auth(body)
    assert r == {"ok": True, "protected": True, "url": "https://nw.dev-bim.com/"}, r
    e = expect(401, dcr.auth, dcr.AuthBody(url="https://nw.dev-bim.com/", code="wrong"))
    assert "код" in e.detail.lower() or "Код" in e.detail, e.detail
    expect(400, dcr.auth, dcr.AuthBody(url="about:blank", code="nw2026"))

    # --- код не задан: защита отключена, любой код принимается ---
    dcr._env_value = lambda key: None
    r = dcr.auth(dcr.AuthBody(url="http://127.0.0.1:8020", code="-"))
    assert r["ok"] is True and r["protected"] is False, r

    # --- статус: protected + default_url из .env ---
    dcr._env_value = lambda key: {"DESIGN_CODE_ACCESS_CODE": "nw2026",
                                  "DESIGN_CODE_URL": "https://nw.dev-bim.com/"}[key]
    st = dcr.auth_status()
    assert st == {"protected": True, "default_url": "https://nw.dev-bim.com/"}, st
    dcr._env_value = lambda key: {"DESIGN_CODE_ACCESS_CODE": "  ",
                                  "DESIGN_CODE_URL": ""}[key]
    st = dcr.auth_status()
    # пустое/пробельное значение ключа = код выключен, префикс тоже гаснет
    assert st == {"protected": False, "default_url": None}, st
    dcr._env_value = lambda key: None
    st = dcr.auth_status()
    assert st == {"protected": False, "default_url": None}, st

    # _default_url: os.environ-фолбэк
    import os
    os.environ["DESIGN_CODE_URL"] = "http://127.0.0.1:8020"
    dcr._env_value = lambda key: None
    assert dcr._default_url() == "http://127.0.0.1:8020"
    del os.environ["DESIGN_CODE_URL"]

    # --- патчи setup_designcode.py: фрагменты самосогласованы ---
    sys.path.insert(0, str(ROOT))
    import setup_designcode as sd  # noqa: E402

    assert sd.JS_NAVBAR_NEW.startswith(sd.JS_NAVBAR_OLD), "кнопка должна добавляться ПОСЛЕ PDF"
    assert sd.JS_NAVBAR_NEW.count('tab:"designcode"') == 1
    assert sd.JS_TABCONTENT_NEW.startswith(sd.JS_TABCONTENT_OLD)
    assert sd.JS_TABCONTENT_NEW.count('designcode') == 1
    assert 'src:"/design_code_viewer.html"' in sd.JS_DESIGNCODE_TAB_V2
    assert 'unregisterTab("designcode")' in sd.JS_DESIGNCODE_TAB_V2
    assert sd.JS_DESIGNCODE_TAB_V2.count("M200.77,53.89") == 1  # палитра на месте
    assert sd.JS_DESIGNCODE_TAB_V2.startswith("function DCI(") and sd.JS_DESIGNCODE_TAB_V2.endswith('DCE.displayName="DesignCodeTab";')
    assert "__devbimIfcCtx=e" in sd.JS_DESIGNCODE_TAB_V2, \
        "DCE v2 должен захватывать контекст моста «To Canvas»"
    assert sd.JS_DESIGNCODE_TAB_V2 != sd.JS_DESIGNCODE_TAB, "v1 != v2"
    assert sd.JS_ENUM_NEW == 'ct(["generate","canvas","upscaling","workflows","models","queue","ifc","pdf","designcode"])'

    # идемпотентность: NEW-фрагмент не совпадает с OLD и не содержит их повторно
    assert sd.JS_NAVBAR_OLD not in sd.JS_NAVBAR_NEW.replace(sd.JS_NAVBAR_OLD, "", 1)
    assert sd.JS_ENUM_OLD not in sd.JS_ENUM_NEW.replace(sd.JS_ENUM_OLD, "", 1)

    # страница вьювера: ключевые конструкции
    page = (ROOT / "design_code" / "design_code_viewer.html").read_text(encoding="utf-8")
    for frag in ("/api/v1/designcode/auth", "devbim:designcode:url", "devbim:designcode:unlocked",
                 'id="btnReload"', 'id="btnTab"', 'id="btnChange"', "sessionStorage"):
        assert frag in page, frag

    # --- нижняя панель: фрагмент сайта -> холст/ассеты (как в PDF-вьювере) ---
    for frag in ('id="capbar"', 'id="btnCapture"', 'id="btnToCanvas"', 'id="btnToAssets"',
                 'id="btnCapCancel"', 'id="freeze"', 'id="freezeCanvas"', 'id="selLayer"',
                 'id="selRect"', 'id="dcToast"'):
        assert frag in page, frag
    assert "getDisplayMedia" in page and "preferCurrentTab: true" in page, \
        "захват области сайта — Screen Capture API с предвыбором текущей вкладки"
    assert "rectInTop" in page, "кроп кадра по прямоугольнику iframe сайта в координатах вкладки"
    assert "/api/v1/images/upload" in page and "image_category=" in page, \
        "отправка фрагмента — тот же multipart-upload, что у IFC/PDF"
    assert "__devbimIfc" in page, "«To Canvas» — общий мост __devbimIfc.toCanvas"
    assert "toCanvasViaBridge" in page and "__devbimSendToCanvas" in page \
           and "__devbimCanvasBridge" in page, \
        "фолбэк моста для старого App-бандла (страница без F5), исполнение в контексте приложения"
    assert 'capbarOn();' in page and 'capbarOff();' in page, \
        "панель следует за открытием сайта/гейта"
    # скрипт страницы синтаксически валиден (node --check)
    import re as _re
    import subprocess as _sp
    import tempfile as _tf
    m = _re.search(r"<script>(.*?)</script>", page, _re.S)
    assert m, "скрипт страницы не найден"
    with _tf.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as fh:
        fh.write(m.group(1))
        chk = fh.name
    try:
        r = _sp.run(["node", "--check", chk], capture_output=True, text=True)
        assert r.returncode == 0, "syntax error в design_code_viewer.html:\n" + r.stderr
    finally:
        import os as _os
        _os.unlink(chk)

    # --- фикс 15.09: локальный адрес — не «сайт» + кнопка сброса Default ---
    assert page.count("isLocalSiteUrl(") >= 3, \
        "гвард локальных URL: определение + вызовы в submit и на старте"
    assert 'id="btnDefault"' in page, "кнопка «↺ Default» в модалке"
    assert "localStorage.removeItem(LS_URL)" in page, \
        "сохранённый при тестах локальный URL вычищается при загрузке"
    assert "window.__dc" in page, "отладочный хук __dc (как __ifc/__pdf)"
    fn = _re.search(r"function isLocalSiteUrl\(url\) \{.*?\n  \}", page, _re.S)
    assert fn, "функция isLocalSiteUrl не найдена"
    with _tf.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as fh:
        fh.write("var location={hostname:'app.local'};\n" + fn.group(0) + """
function T(u, exp){ var r = isLocalSiteUrl(u); if (r !== exp){ console.error('fail:', u, '->', r); process.exit(1); } }
T('http://127.0.0.1:9090/pdfviewer.html', true);
T('http://localhost:8080/', true);
T('http://[::1]:9090/', true);
T('http://app.local:9100/page', true);
T('https://nw.dev-bim.com/', false);
T('http://other.host:9090/', false);
T('not a url', false);
""")
        guard_chk = fh.name
    try:
        r = _sp.run(["node", guard_chk], capture_output=True, text=True)
        assert r.returncode == 0, "isLocalSiteUrl ведёт себя не так:\n" + r.stdout + r.stderr
    finally:
        _os.unlink(guard_chk)

    print("OK")


if __name__ == "__main__":
    main()
