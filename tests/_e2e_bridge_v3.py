# -*- coding: utf-8 -*-
"""E2E моста вьювер -> холст V3 (25.09, п.56): переход на канвас из вьювера
НЕ создаёт слой «Маска перерисовки», рамка = 3:2 (locked), картинка вписана
в рамку (fit to bbox). Вызывает мост напрямую из контекста приложения —
тот же window.__devbimIfc.toCanvas, что вызывают кнопки «To Canvas»
в IFC/PDF/Design Code вьюверах (после монтада вкладки-держателя контекста).

Запуск: venv\\Scripts\\python.exe tests\\_e2e_bridge_v3.py (сервер на 9090).
"""
import re
import time
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs"

pw = (re.search(r"^SITE_PASSWORD=(.+)$", (ROOT / ".env").read_text(encoding="utf-8"),
                re.M) or [None, ""])[1].strip().strip('"')
s = requests.Session()
r = s.post("http://127.0.0.1:9090/auth/login", data={"password": pw},
           allow_redirects=False, timeout=15)
assert r.status_code in (302, 303), r.status_code

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(
        str(ROOT / "tests" / "_pw_e2e"), channel="chrome", headless=True,
        viewport={"width": 1600, "height": 900})
    ctx.add_cookies([{"name": "devbim_auth", "value": s.cookies.get("devbim_auth"),
                      "url": "http://127.0.0.1:9090"}])
    page = ctx.new_page()
    errors = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.goto("http://127.0.0.1:9090/", wait_until="domcontentloaded")
    page.wait_for_selector(".positive-prompt-textarea", timeout=60000)
    time.sleep(2)

    # смонтировать вкладку-держателя контекста моста (PDFE ловит __devbimIfcCtx)
    page.get_by_role("button", name="PDF", exact=True).click()
    page.wait_for_selector('iframe[src*="pdfviewer"]', timeout=30000)
    time.sleep(2)
    has_ctx = page.evaluate("() => !!window.__devbimIfcCtx")
    print("контекст моста после монтажа вкладки PDF:", has_ctx)
    assert has_ctx, "вкладка PDF не захватила __devbimIfcCtx"

    # тот же путь, что uploadImage() вьюверов: картинка 800x1000 (НЕ 3:2)
    dto = page.evaluate("""async () => {
        const c = document.createElement('canvas');
        c.width = 800; c.height = 1000;
        const x = c.getContext('2d');
        x.fillStyle = '#3a6ea5'; x.fillRect(0, 0, 800, 1000);
        x.fillStyle = '#f2d16b'; x.fillRect(60, 80, 680, 840);
        const blob = await new Promise(res => c.toBlob(res, 'image/png'));
        const fd = new FormData();
        fd.append('file', blob, 'e2e-bridge-v3.png');
        const r = await fetch('/api/v1/images/upload?image_category=general&is_intermediate=false',
                              {method: 'POST', body: fd});
        if (!r.ok) throw new Error('upload HTTP ' + r.status);
        return await r.json();
    }""")
    print("ImageDTO:", dto["image_name"], dto["width"], "x", dto["height"])

    t0 = time.time()
    page.evaluate("async dto => await window.__devbimIfc.toCanvas(dto, false)", dto)
    print(f"toCanvas выполнен за {time.time()-t0:.1f}с")

    res = page.evaluate("""() => {
        const store = (window.__devbimIfcCtx || (window.__devbimCanvasBridge
                       && window.__devbimCanvasBridge.getManager()
                       && window.__devbimCanvasBridge.getManager().stateApi.store)).getState();
        let cs = store.canvas;
        if (cs && cs.present) cs = cs.present;
        const sel = cs.selectedEntityIdentifier;
        // applyTransform запекает вписанную картинку единственным объектом
        // слоя — габариты берём из объектов состояния (синхронно, источник
        // истины); $pixelRect трансформера пересчитывается с задержкой
        const rl = cs.rasterLayers.entities.find(e => e.id === (sel && sel.id));
        const img = rl && rl.objects.find(o => o.type === 'image');
        return {
            ratioId: cs.bbox.aspectRatio.id,
            locked: cs.bbox.aspectRatio.isLocked,
            bbox: cs.bbox.rect,
            masks: cs.inpaintMasks.entities.length,
            rasterCount: cs.rasterLayers.entities.length,
            fit: img ? {width: img.image.width, height: img.image.height} : null,
        };
    }""")
    print("canvas:", res)

    ok = True
    def check(cond, msg):
        global ok
        print(("  OK:" if cond else "  FAIL:") , msg)
        ok = ok and cond

    check(res["ratioId"] == "3:2", f"рамка 3:2 (получили {res['ratioId']})")
    check(res["locked"] is True, "рамка залочена")
    w, h = res["bbox"]["width"], res["bbox"]["height"]
    check(abs(w / h - 1.5) < 0.01, f"пропорция rect {w}x{h} = {w/h:.3f}")
    check(res["masks"] == 0, f"слоёв маски {res['masks']} (ожидалось 0)")
    check(res["fit"] is not None, "raster-слой с запечённой картинкой создан")
    f = res["fit"]
    check(f and f["width"] <= w + 2 and f["height"] <= h + 2,
          f"картинка вписана в рамку: слой {f and f['width']}x{f and f['height']} ≤ bbox {w}x{h}" if f else "слой не найден")
    if f:
        check(abs(f["width"] / f["height"] - 0.8) < 0.02, "пропорции картинки сохранены (800x1000)")

    page.screenshot(path=str(OUT / "bridge-v3-canvas.png"), full_page=False)
    print("скриншот:", OUT / "bridge-v3-canvas.png")
    hard = [e for e in errors if "favicon" not in e.lower()]
    if hard:
        print("console errors:", hard[:5])
    ctx.close()

assert ok, "E2E НЕ ПРОЙДЕН"
print("E2E OK: без маски, рамка 3:2, картинка вписана")
