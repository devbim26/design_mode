# -*- coding: utf-8 -*-
"""E2E фазы 4 (Task 11): вьювер ставит камеру по camHint + скриншоты."""
import base64, io, json, re, shutil, time
from pathlib import Path
import requests
from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
NAME = "3D_scene_20260920-001646.ifc"
HINT = {"azimuth_deg": -38.0, "eye_height_m": 1.7, "dist_m": 39.0}

pw = (re.search(r"^SITE_PASSWORD=(.+)$", (ROOT / ".env").read_text(encoding="utf-8"),
                re.M) or [None, ""])[1].strip().strip('"')
s = requests.Session()
r = s.post("http://127.0.0.1:9090/auth/login", data={"password": pw},
           allow_redirects=False, timeout=15)
assert r.status_code in (302, 303), r.status_code

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(
        str(ROOT / "tests" / "_pw_e2e"), channel="chrome", headless=True,
        viewport={"width": 1280, "height": 860})
    ctx.add_cookies([{"name": "devbim_auth", "value": s.cookies.get("devbim_auth"),
                      "url": "http://127.0.0.1:9090"}])

    # --- 1) вьювер: камера по подсказке ---
    page = ctx.new_page()
    page.goto("http://127.0.0.1:9090/ifcviewer.html", wait_until="domcontentloaded")
    page.evaluate(f"localStorage.setItem('devbim:ifc:lastModel','{NAME}');"
                  f"localStorage.setItem('devbim:ifc:camHint','{json.dumps(HINT)}')")
    page.reload(wait_until="domcontentloaded")
    for _ in range(60):
        if page.evaluate("() => !!(window.__ifc && __ifc.model)"):
            break
        time.sleep(1)
    else:
        raise SystemExit("модель не загрузилась")
    page.wait_for_timeout(1500)
    pos, box, hint_left = page.evaluate(
        """() => { const c = __ifc.world.camera.three.position;
                   const b = __ifc.model.box;
                   return [c.toArray(), [b.min.toArray(), b.max.toArray()],
                           localStorage.getItem('devbim:ifc:camHint')]; }""")
    print("camera:", [round(v, 2) for v in pos], "box.min:", [round(v, 2) for v in box[0]])
    assert hint_left is None, "подсказка обязана быть одноразовой (removeItem)"
    assert pos[1] < box[0][1] + 5.0, f"глаз камеры {pos[1]:.2f} не у земли bbox {box[0][1]:.2f}"
    d = page.evaluate("() => __ifc.capture()")
    im = Image.open(io.BytesIO(base64.b64decode(d.split(",", 1)[1]))).convert("RGBA")
    im.convert("RGB").save(ROOT / "docs" / "3d-design-scene-view.png")
    page.close()

    # --- 2) модалка 3D Design с плиткой «Сцена» ---
    page = ctx.new_page()
    page.goto("http://127.0.0.1:9090/", wait_until="domcontentloaded")
    page.wait_for_selector("#devbim-tr-btns #devbim-tr-3d", timeout=30000)
    page.click("#devbim-tr-3d")
    page.wait_for_selector("#devbim-3d-modal", timeout=10000)
    page.click('#devbim-3d-modal .devbim-3d-tile[data-s="scene"]')
    page.wait_for_timeout(400)
    ph = page.eval_on_selector("#devbim-3d-prompt", "el => el.placeholder")
    assert "Сцена" not in ph and ("дома" in ph or "камера" in ph), ph
    page.screenshot(path=str(ROOT / "docs" / "3d-design-scene-modal.png"))
    ctx.close()

# --- 3) план-превью из data/ifc ---
shutil.copy(ROOT / "data" / "ifc" / (Path(NAME).stem + "_preview.png"),
            ROOT / "docs" / "3d-design-scene-plan.png")
print("E2E SCENE OK")
