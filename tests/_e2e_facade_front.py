# -*- coding: utf-8 -*-
"""E2E этапа A4: дефолтная камера fitModel видит фасад с окнами."""
import base64, io, re, time
from pathlib import Path
import numpy as np, requests
from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
import sys; sys.path.insert(0, str(ROOT))
from invokeai.app.api.routers import threed_build, threed_scenarios

scene = {
    "storeys": 7, "floor_height": 3.1, "width_m": 27.0, "depth_m": 12.0,
    "roof": "flat", "roof_height": 0.5,
    "windows": {"rows": 1, "cols": 9, "w_m": 1.25, "h_m": 2.0,
                "margin_x_m": 1.2, "margin_y_m": 0.55,
                "skip": [[False] * 5 + [True] + [False] * 3]},
    "balconies": [{"floor": f, "x_m": 1.5, "w_m": 3.0, "d_m": 1.2}
                  for f in range(2, 8)],
    "colors": {"walls": "#c9b49a", "roof": "#52616b", "plinth": "#8d8d8d"},
}
clean, _ = threed_scenarios.validate_facade(scene)
ifc = ROOT / "data" / "ifc" / "3D_facade_frontchk.ifc"
threed_build.build_facade(clean, ifc, ROOT / "data" / "ifc" / "_frontchk_prev.png",
                          {"Scenario": "facade", "Source": "E2E"})

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
    page = ctx.new_page()
    page.goto("http://127.0.0.1:9090/ifcviewer.html", wait_until="domcontentloaded")
    page.evaluate("localStorage.setItem('devbim:ifc:lastModel','3D_facade_frontchk.ifc')")
    page.reload(wait_until="domcontentloaded")
    for _ in range(60):
        if page.evaluate("() => !!(window.__ifc && __ifc.model)"):
            break
        time.sleep(1)
    else:
        raise SystemExit("модель не загрузилась")
    page.wait_for_timeout(1500)
    d = page.evaluate("() => __ifc.capture()")  # ДЕФОЛТНЫЙ вид (fitModel)
    im = Image.open(io.BytesIO(base64.b64decode(d.split(",", 1)[1]))).convert("RGBA")
    im.convert("RGB").save(ROOT / "docs" / "3d-facade-default-view.png")
    a = np.array(im)
    vis = a[..., 3] > 30
    px = a[vis][:, :3]
    dark = ((px[:, 0] < 90) & (px[:, 1] < 90) & (px[:, 2] < 110)).mean()
    print(f"dark fraction: {dark:.2%}")
    assert dark > 0.05, "с дефолтного ракурса не видно окон (фасад не на -Y?)"
    ctx.close()
print("E2E A4 OK")
