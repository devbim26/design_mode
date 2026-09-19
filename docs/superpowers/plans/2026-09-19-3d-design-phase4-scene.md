# 3D Design: фиксы фасада + сценарий «Сцена» — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** починить размещение/ориентацию фасада (балконы в габарите, окна на камеру) и добавить четвёртый сценарий «Сцена» — грубая уличная 3D-сцена из примитивов по фото с оценкой камеры (база для «здания под новым углом», спека `2026-09-19-3d-design-scene-design.md`).

**Architecture:** этап A правит существующие `validate_facade`/`build_facade` (TDD); этап B добавляет `SYSTEM_SCENE`/`validate_scene`/`build_scene` в модули threed, сценарий `scene` в роутер (ответ несёт `camHint`), плитку «Сцена» в модалку, обработку `devbim:ifc:camHint` в IFC-вьювере (камера после загрузки вместо fitModel).

**Tech Stack:** Python (ifcopenshell 0.8.5, FastAPI, matplotlib), JS (ES-модуль вьювера @thatopen, виджет devbim_topright_buttons.js), деплой setup-скриптами.

## Global Constraints

- Параллельные сессии работают в этом же репозитории: перед каждой правкой ПЕРЕЧИТАТЬ файл; коммит только явными pathspec (`git commit -m "…" -- <файлы>`).
- `PYTHONUTF8=1` в любой команде python (кириллица).
- Тесты: `PYTHONUTF8=1 ../venv/Scripts/python.exe -c "import test_threed as t; t.<имя>()"` из каталога `tests/` (грабля п.40.3: site-packages/tests затеняет); полный прогон: `PYTHONUTF8=1 venv/Scripts/python.exe tests/test_threed.py` из корня.
- После правок `threed/*` сперва `PYTHONUTF8=1 venv/Scripts/python.exe setup_threed.py`, потом роутерные тесты (грабля п.38.5).
- JS-файлы виджета/вьювера проверять `node --check` (в тестах уже есть).
- Сервер перезапускать только `_restart_server.ps1` (Task 11).
- НЕ трогать: interior-код (фаза 3, HANDOFF п.40), чужие staged-файлы (design_code, imagerouter_router.py и пр.).

---

### Task 1: validate_facade — балкон целиком в фасаде

**Files:**
- Modify: `threed/threed_scenarios.py` (блок балконов validate_facade, ~строки 286–308)
- Test: `tests/test_threed.py`

**Interfaces:**
- Produces: контракт `out["balconies"][i]["x_m"]` — центр плиты, плита всегда влезает в `[0, width_m]` (опираются Task 2, 5).

- [ ] **Step 1: Write the failing test** — добавить в конец `tests/test_threed.py` (перед `if __name__ == "__main__"` если есть, иначе в конец):

```python
def test_validate_facade_balcony_fit():
    """Спека этапа A2: плита балкона целиком в фасаде — кламп центра."""
    from threed.threed_scenarios import validate_facade
    s = sample_facade_scene()
    s["balconies"] = [{"floor": 2, "x_m": 23.5, "w_m": 3.0, "d_m": 1.2},
                      {"floor": 3, "x_m": 0.5, "w_m": 3.0, "d_m": 1.2}]
    out, warn = validate_facade(s)
    assert [b["x_m"] for b in out["balconies"]] == [22.5, 1.5], out["balconies"]
    assert any("Балкон 1" in w for w in warn), warn
    assert any("Балкон 2" in w for w in warn), warn
    # влезающий балкон не сдвигается и не даёт предупреждений
    s["balconies"] = [{"floor": 2, "x_m": 4.0, "w_m": 3.0, "d_m": 1.2}]
    out2, warn2 = validate_facade(s)
    assert out2["balconies"][0]["x_m"] == 4.0 and warn2 == []
    print("test_validate_facade_balcony_fit OK")
```

И добавить вызов `test_validate_facade_balcony_fit()` в блок прогонов в конце файла (найти по образцу: там перечислены `test_validate_facade()` и т.п.).

- [ ] **Step 2: Run test to verify it fails**

```bash
cd tests && PYTHONUTF8=1 ../venv/Scripts/python.exe -c "import test_threed as t; t.test_validate_facade_balcony_fit()"
```

Expected: FAIL — первый балкон проходит без клампа (`[23.5, 0.5] != [22.5, 1.5]`).

- [ ] **Step 3: Implement** — в `threed/threed_scenarios.py` заменить блок проверки размеров балкона:

```python
        if not (0.0 <= x <= out["width_m"]) or not (0.5 <= w_b <= out["width_m"]) \
                or not (0.3 <= d_b <= 5.0):
            warnings.append(f"Балкон {idx}: размеры вне диапазона — пропущен")
            continue
        out["balconies"].append({"floor": floor, "x_m": x, "w_m": w_b, "d_m": d_b})
```

на:

```python
        if x != x or w_b != w_b or d_b != d_b:  # NaN
            warnings.append(f"Балкон {idx}: неверные размеры — пропущен")
            continue
        if not (0.5 <= w_b <= out["width_m"]) or not (0.3 <= d_b <= 5.0):
            warnings.append(f"Балкон {idx}: размеры вне диапазона — пропущен")
            continue
        # плита целиком в фасаде: центр в [w_b/2, width-w_b/2] (кламп, не дроп)
        lo, hi = w_b / 2, out["width_m"] - w_b / 2
        if x < lo or x > hi:
            clamped = max(lo, min(hi, x))
            warnings.append(
                f"Балкон {idx}: центр {x:g} — плита выходит за фасад, "
                f"центр смещён до {clamped:g}")
            x = clamped
        out["balconies"].append({"floor": floor, "x_m": x, "w_m": w_b, "d_m": d_b})
```

- [ ] **Step 4: Run tests** —focused (Step 2 команда) + соседний `t.test_validate_facade()` — оба PASS.

- [ ] **Step 5: Commit**

```bash
git commit -m "fix(3d): validate_facade — балкон целиком в фасаде (кламп центра, NaN-гвард)" -- threed/threed_scenarios.py tests/test_threed.py
```

---

### Task 2: build_facade — балконы в мировых координатах + превью

**Files:**
- Modify: `threed/threed_build.py` (размещение балконов ~строка 366; превью-балконы в `_draw_facade_preview` ~строки 442–452)
- Test: `tests/test_threed.py` (расширение `test_build_facade`)

**Interfaces:**
- Consumes: `balconies[i]["x_m"]` — центр «от левого края фасада» (Task 1).
- Produces: мировой центр балкона `x_m − width/2`; превью в том же фрейме (совпадение чертежа и 3D).

- [ ] **Step 1: Write the failing test** — в `test_build_facade` после существующего `assert abs(get_local_placement(bal2.ObjectPlacement)[2, 3] …` добавить:

```python
    # спека A1: мировой центр балкона = x_m - width/2 (4.0 - 12.0 = -8.0)
    assert abs(get_local_placement(bal2.ObjectPlacement)[0, 3] - (4.0 - 24.0 / 2)) < 1e-6
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd tests && PYTHONUTF8=1 ../venv/Scripts/python.exe -c "import test_threed as t; t.test_build_facade()"
```

Expected: FAIL — placement X равен 4.0 (нет сдвига −w/2).

- [ ] **Step 3: Implement** — в `build_facade` заменить:

```python
        box(f"Балкон {b_idx} · этаж {bal['floor']}", bal["w_m"], bal["d_m"], 0.18,
            bal["x_m"], d / 2 + bal["d_m"] / 2, bal_z, "balcony",
            storeys[bal["floor"] - 1], object_type="CONCEPTUAL_BALCONY")
```

на:

```python
        # x_m — от левого края фасада; здание центрировано -> мир: x_m - w/2
        box(f"Балкон {b_idx} · этаж {bal['floor']}", bal["w_m"], bal["d_m"], 0.18,
            bal["x_m"] - w / 2, d / 2 + bal["d_m"] / 2, bal_z, "balcony",
            storeys[bal["floor"] - 1], object_type="CONCEPTUAL_BALCONY")
```

В `_draw_facade_preview` заменить блок балконов:

```python
    for b_idx, bal in enumerate(data["balconies"], start=1):
        bal_lo = (bal["floor"] - 1) * fh
        ax.add_patch(PlotPolygon(
            [[bal["x_m"] - bal["w_m"] / 2, bal_lo],
             [bal["x_m"] + bal["w_m"] / 2, bal_lo],
             [bal["x_m"] + bal["w_m"] / 2, bal_lo + 1.0],
             [bal["x_m"] - bal["w_m"] / 2, bal_lo + 1.0]],
            facecolor="none", edgecolor=colors["balcony"], hatch="////", linewidth=1.2))
        ax.text(bal["x_m"], bal_lo + 0.5, f"Б{b_idx}", ha="center", va="center",
                fontsize=7, color="#15232e")
```

на (общий мировые координаты с окнами):

```python
    for b_idx, bal in enumerate(data["balconies"], start=1):
        bal_lo = (bal["floor"] - 1) * fh
        bx = bal["x_m"] - w / 2  # тот же мировой фрейм, что у окон
        ax.add_patch(PlotPolygon(
            [[bx - bal["w_m"] / 2, bal_lo],
             [bx + bal["w_m"] / 2, bal_lo],
             [bx + bal["w_m"] / 2, bal_lo + 1.0],
             [bx - bal["w_m"] / 2, bal_lo + 1.0]],
            facecolor="none", edgecolor=colors["balcony"], hatch="////", linewidth=1.2))
        ax.text(bx, bal_lo + 0.5, f"Б{b_idx}", ha="center", va="center",
                fontsize=7, color="#15232e")
```

- [ ] **Step 4: Run tests** — `t.test_build_facade()` PASS. (Превью-PNG перезапишется тем же тестом.)

- [ ] **Step 5: Commit**

```bash
git commit -m "fix(3d): балконы фасада в мировых координатах x_m-w/2 (сборщик и превью единый фрейм)" -- threed/threed_build.py tests/test_threed.py
```

---

### Task 3: build_facade — фасад на IFC −Y (дефолтная камера видит окна)

**Files:**
- Modify: `threed/threed_build.py` (окна ~354–359, балконы Task 2 строка cy, матрица двускатной крыши ~383–390)
- Test: `tests/test_threed.py`

**Interfaces:**
- Produces: фасадная грань (окна/балконы/фронт крыши) на стороне IFC −Y; после мирового трансформа вьювера (ifc −Y → world +Z) дефолтная камера fitModel видит фасад. Опираются Task 6 (сцена строит фронт так же) и Task 10 (camHint считает фронт = +Z мира).

- [ ] **Step 1: Write the failing test** — в `test_build_facade` добавить (после X-проверки балкона из Task 2):

```python
    # спека A4: фасад на IFC -Y (окна/балконы на отрицательной стороне Y)
    assert abs(get_local_placement(win1.ObjectPlacement)[1, 3] - (-12.0 / 2)) < 1e-6
    assert abs(get_local_placement(bal2.ObjectPlacement)[1, 3]
               - (-(12.0 / 2 + 1.2 / 2))) < 1e-6
```

и выше по функции, где выбирается `bal2`, добавить выбор `win1`:

```python
    win1 = [p for p in proxies if p.ObjectType == "CONCEPTUAL_WINDOW"][0]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd tests && PYTHONUTF8=1 ../venv/Scripts/python.exe -c "import test_threed as t; t.test_build_facade()"
```

Expected: FAIL — окна на +6.0, а не −6.0.

- [ ] **Step 3: Implement** — три правки в `build_facade`:

(a) окна, заменить:

```python
                box(f"Окно Э{f + 1}-{i + 1}", win["w_m"], 0.12, win["h_m"],
                    # центр по Y = d/2: наполовину в стене, передняя грань
                    # на 0.06 м перед фасадом — иначе луч выбора вьювера
                    # упирается в стену заподлицо и окно не кликабельно в 3D
                    x + win["w_m"] / 2, d / 2, f * fh + z_in, "glazing",
                    storeys[f], object_type="CONCEPTUAL_WINDOW")
```

на:

```python
                box(f"Окно Э{f + 1}-{i + 1}", win["w_m"], 0.12, win["h_m"],
                    # центр по Y = -d/2: фасад на IFC -Y (после трансформа
                    # вьювера -> world +Z, дефолтная камера видит окна);
                    # передняя грань на 0.06 м перед фасадом — иначе луч
                    # выбора упирается в стену заподлицо и окно не кликается
                    x + win["w_m"] / 2, -d / 2, f * fh + z_in, "glazing",
                    storeys[f], object_type="CONCEPTUAL_WINDOW")
```

(b) балконы (строка из Task 2), `cy` со знаком минус:

```python
        box(f"Балкон {b_idx} · этаж {bal['floor']}", bal["w_m"], bal["d_m"], 0.18,
            bal["x_m"] - w / 2, -(d / 2 + bal["d_m"] / 2), bal_z, "balcony",
            storeys[bal["floor"] - 1], object_type="CONCEPTUAL_BALCONY")
```

(c) матрица двускатной крыши, заменить:

```python
        # локальная X -> мировая X; локальная Y (высота профиля) -> мировая Z;
        # выдавливание (+Z локали) -> -Y (от лицевой грани вглубь), origin на грани
        matrix = np.array([
            [1.0, 0.0, 0.0, 0.0],
            [0.0, 0.0, -1.0, d / 2],
            [0.0, 1.0, 0.0, n * fh],
            [0.0, 0.0, 0.0, 1.0],
        ])
```

на:

```python
        # локальная X -> мировая X; локальная Y (высота профиля) -> мировая Z;
        # выдавливание (+Z локали) -> +Y (от лицевой грани -Y вглубь), origin на грани
        matrix = np.array([
            [1.0, 0.0, 0.0, 0.0],
            [0.0, 0.0, 1.0, -d / 2],
            [0.0, 1.0, 0.0, n * fh],
            [0.0, 0.0, 0.0, 1.0],
        ])
```

- [ ] **Step 4: Run tests** — `t.test_build_facade()` PASS (старые assert-ы по Z-отметкам и объёмам не затронуты).

- [ ] **Step 5: Commit**

```bash
git commit -m "fix(3d): фасад на IFC -Y — дефолтная камера вьювера видит окна (жалоба «параллелепипед без окон»)" -- threed/threed_build.py tests/test_threed.py
```

---

### Task 4: Деплой этапа A + E2E дефолтного вида

**Files:**
- Deploy: `setup_threed.py` (без правок самого скрипта), артефакт `data/ifc/3D_facade_frontchk.ifc` + скриншот `docs/3d-facade-default-view.png`

**Interfaces:**
- Consumes: Task 1–3 (deployed в venv).

- [ ] **Step 1: Деплой и тесты**

```bash
PYTHONUTF8=1 venv/Scripts/python.exe setup_threed.py
PYTHONUTF8=1 venv/Scripts/python.exe tests/test_threed.py
```

Expected: все тесты OK (16+1 функций; печатается OK по каждой).

- [ ] **Step 2: E2E тёмных пикселей с дефолтного ракурса** — сборка свежего фасадного IFC в `data/ifc` и headless-проверка (адаптация зонда `data/probe/shoot.py`; логин/cookie — оттуда же):

```python
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
```

Сохранить как `tests/_e2e_facade_front.py`, запустить `PYTHONUTF8=1 venv/Scripts/python.exe tests/_e2e_facade_front.py`. Expected: `E2E A4 OK`, dark > 5%.

- [ ] **Step 3: Commit** (скрипт E2E не коммитим — временный; артефакты data/ не в git; скриншот в docs):

```bash
git add docs/3d-facade-default-view.png
git commit -m "docs(3d): E2E этапа A — дефолтный вид фасада с окна (>5% остекления)" -- docs/3d-facade-default-view.png
```

---

### Task 5: SYSTEM_SCENE + validate_scene

**Files:**
- Modify: `threed/threed_scenarios.py` (новая секция в конце файла)
- Test: `tests/test_threed.py`

**Interfaces:**
- Produces: `SYSTEM_SCENE: str`; `validate_scene(scene: dict) -> tuple[dict, list[str]]`, поднимает `ValueError` если нет зданий. Формат чистой сцены: `{"camera": {"azimuth_deg","eye_height_m","dist_m"}, "buildings": [{"main","x_m","y_m","width_m","depth_m","storeys","floor_height","roof","roof_height","windows":{rows,cols,w_m,h_m,margin_x_m,margin_y_m},"balconies":[{floor,x_m,w_m,d_m}],"colors":{...}}], "context": {"trees":[{x_m,y_m,h_m,crown_d_m}],"cars":[{x_m,y_m,rot_deg}],"people":[{x_m,y_m}]}}`. Потребители: Task 6–8.

- [ ] **Step 1: Write the failing test** — добавить в `tests/test_threed.py`:

```python
def sample_scene_scene():
    """Сцена: главное 7-эт. здание в (0,0), второе 3-эт. в (30,8); камера
    азимут -30 (слева), деревья/машины/люди."""
    return {
        "camera": {"azimuth_deg": -30, "eye_height_m": 1.7, "dist_m": 40},
        "buildings": [
            {"main": True, "x_m": 0, "y_m": 0, "width_m": 27.0, "depth_m": 12.0,
             "storeys": 7, "floor_height": 3.1, "roof": "flat", "roof_height": 0.5,
             "windows": {"rows": 1, "cols": 8, "w_m": 1.4, "h_m": 1.8,
                         "margin_x_m": 1.5, "margin_y_m": 0.6},
             "balconies": [{"floor": 2, "x_m": 1.5, "w_m": 3.0, "d_m": 1.2}],
             "colors": {"walls": "#c9b49a", "roof": "#52616b", "plinth": "#8d8d8d"}},
            {"main": False, "x_m": 32.0, "y_m": 8.0, "width_m": 14.0, "depth_m": 10.0,
             "storeys": 3, "floor_height": 3.0, "roof": "gable", "roof_height": 2.0,
             "windows": {"rows": 1, "cols": 4, "w_m": 1.4, "h_m": 1.6,
                         "margin_x_m": 1.0, "margin_y_m": 0.7},
             "balconies": [], "colors": {}},
            {"main": True, "x_m": -40.0, "y_m": 0.0, "width_m": 10.0, "depth_m": 10.0,
             "storeys": 2, "floor_height": 3.0, "roof": "flat", "roof_height": 1.0,
             "windows": {}, "balconies": [], "colors": {}},
        ],
        "context": {
            "trees": [{"x_m": 8.0, "y_m": -12.0, "h_m": 7.0, "crown_d_m": 3.5},
                      {"x_m": "bad"}, {"x_m": 15.0, "y_m": -14.0, "h_m": 99,
                                       "crown_d_m": 3.0}],
            "cars": [{"x_m": -6.0, "y_m": -10.0, "rot_deg": 15}],
            "people": [{"x_m": 5.0, "y_m": -9.0}, {"x_m": 6.0, "y_m": -9.5}],
        },
    }


def test_validate_scene():
    from threed.threed_scenarios import validate_scene, SYSTEM_SCENE
    assert "azimuth_deg" in SYSTEM_SCENE and "crown_d_m" in SYSTEM_SCENE
    out, warn = validate_scene(sample_scene_scene())
    assert out["camera"] == {"azimuth_deg": -30, "eye_height_m": 1.7, "dist_m": 40}
    b0, b1 = out["buildings"][0], out["buildings"][1]
    assert b0["main"] is True and b1["main"] is False
    assert len(out["buildings"]) == 2          # третий отброшен: >3
    assert any("больше 3" in w for w in warn)
    # второй main тихо понижен; окна дефолтованы; балкон влез
    assert b1["windows"]["cols"] == 4 and b1["windows"]["w_m"] == 1.4
    # дерево: 'bad'-элемент выкинут, h_m=99 -> кламп 30
    assert len(out["context"]["trees"]) == 2
    assert out["context"]["trees"][1]["h_m"] == 30.0
    assert any("tree.h_m" in w for w in warn)
    assert len(out["context"]["people"]) == 2
    # гейты
    for bad in (None, {}, {"buildings": []}, {"buildings": "x"}):
        try:
            validate_scene(bad)
            raise AssertionError("ожидалась ошибка")
        except ValueError:
            pass
    print("test_validate_scene OK")
```

Вызвать `test_validate_scene()` в блоке прогонов.

- [ ] **Step 2: Run test to verify it fails**

```bash
cd tests && PYTHONUTF8=1 ../venv/Scripts/python.exe -c "import test_threed as t; t.test_validate_scene()"
```

Expected: FAIL — `ImportError: cannot import name 'validate_scene'`.

- [ ] **Step 3: Implement** — добавить в конец `threed/threed_scenarios.py`:

```python
# ===================== Фаза 4: сценарий «Сцена» (camera mapping) =====================

SYSTEM_SCENE = """You are a BIM street-scene analyst. Look at the attached PHOTO of a
street / yard with 1-3 buildings, trees, cars and people. Reconstruct a rough 3D
massing scene as parametric JSON. Reply with STRICT JSON ONLY - no markdown
fences, no comments, no extra keys.

Schema (ALL VALUES ARE METERS; plan axes: X east, Y north; the MAIN building
facade faces SOUTH = -Y and stands near the origin):
{
 "camera": {
   "azimuth_deg": <float -75..75; 0 = camera straight in front of the main facade
     (south of it, looking north); positive = camera moved to the RIGHT of the
     facade (east side)>,
   "eye_height_m": <camera eye height; street-level photo ~1.5-1.8>,
   "dist_m": <distance from camera to the main facade, 10..200>
 },
 "buildings": [
   {"main": <bool; true ONLY for the building closest to the camera>,
    "x_m": <center X>, "y_m": <center Y>,
    "width_m": <facade length along X>, "depth_m": <along Y>,
    "storeys": <int 1-30>, "floor_height": <2.0-6.0, typical 3.0>,
    "roof": "flat" | "gable", "roof_height": <ridge above eave>,
    "windows": {"rows": <1-2>, "cols": <1-10>, "w_m": <>, "h_m": <>,
      "margin_x_m": <>, "margin_y_m": <>},
    "balconies": [{"floor": <int, 2..storeys>, "x_m": <center from facade LEFT
      edge, m>, "w_m": <>, "d_m": <projection depth>}],
    "colors": {"walls": "#rrggbb", "roof": "#rrggbb", "plinth": "#rrggbb"}}
 ],
 "context": {
   "trees": [{"x_m": <>, "y_m": <>, "h_m": <5-15>, "crown_d_m": <2-6>}],
   "cars": [{"x_m": <>, "y_m": <>, "rot_deg": <heading; 0 = along X>}],
   "people": [{"x_m": <>, "y_m": <>}]
 }
}

Rules:
- Scale anchors: storey ~3 m, window ~1.5 x 1.5 m, door ~2.1 m, car 4.5 x 1.8 m,
  tree 5-8 m, person 1.7 m. Printed dimension lines are exact.
- The MAIN building is the one closest to the camera: place it at x_m=0, y_m=0
  with its main facade facing -Y (south). Other buildings: offsets in meters.
- Count storeys and window columns of the MAIN building CAREFULLY; perspective in
  photos: treat facades as flat (orthographic).
- Side walls get a simplified window grid automatically - do not invent them.
- The USER PROMPT overrides your guesses wherever it states them.
"""


def validate_scene(scene):
    """Сцена улицы от VLM -> (чистая сцена, warnings). ValueError — нет зданий."""
    if not isinstance(scene, dict) or not isinstance(scene.get("buildings"), list) \
            or not scene["buildings"]:
        raise ValueError("Не удалось распознать сцену на картинке (нет зданий)")
    warnings = []
    out = {"camera": {}, "buildings": [], "context": {}}

    cam = scene.get("camera") if isinstance(scene.get("camera"), dict) else {}
    out["camera"]["azimuth_deg"] = _facade_float(
        cam.get("azimuth_deg", 25.0), 25.0, -75.0, 75.0, "camera.azimuth_deg", warnings)
    out["camera"]["eye_height_m"] = _facade_float(
        cam.get("eye_height_m", 1.6), 1.6, 0.3, 30.0, "camera.eye_height_m", warnings)
    out["camera"]["dist_m"] = _facade_float(
        cam.get("dist_m", 35.0), 35.0, 10.0, 200.0, "camera.dist_m", warnings)

    main_seen = False
    for idx, b in enumerate(scene["buildings"][:3], start=1):
        if not isinstance(b, dict):
            warnings.append(f"Здание {idx}: не объект — пропущено")
            continue
        main = bool(b.get("main")) and not main_seen
        if bool(b.get("main")) and main_seen:
            warnings.append(f"Здание {idx}: main уже назначен — обычное здание")
        main_seen = main_seen or main
        bld = {"main": main}
        bld["x_m"] = _facade_float(b.get("x_m", 0.0), 0.0, -150.0, 150.0,
                                   f"Здание {idx}.x_m", warnings)
        bld["y_m"] = _facade_float(b.get("y_m", 0.0), 0.0, -150.0, 150.0,
                                   f"Здание {idx}.y_m", warnings)
        bld["width_m"] = _facade_float(b.get("width_m", 18.0), 18.0, 3.0, 120.0,
                                       f"Здание {idx}.width_m", warnings)
        bld["depth_m"] = _facade_float(b.get("depth_m", 12.0), 12.0, 3.0, 60.0,
                                       f"Здание {idx}.depth_m", warnings)
        bld["storeys"] = int(_facade_float(b.get("storeys", 5), 5, 1, 30,
                                           f"Здание {idx}.storeys", warnings))
        bld["floor_height"] = _facade_float(b.get("floor_height", 3.0), 3.0, 2.0, 6.0,
                                            f"Здание {idx}.floor_height", warnings)
        roof = b.get("roof", "flat")
        if roof not in ("flat", "gable"):
            warnings.append(f"Здание {idx}: крыша «{roof}» не поддержана — flat")
            roof = "flat"
        bld["roof"] = roof
        bld["roof_height"] = _facade_float(b.get("roof_height", 2.5), 2.5, 0.5, 8.0,
                                           f"Здание {idx}.roof_height", warnings)
        wsrc = b.get("windows") if isinstance(b.get("windows"), dict) else {}
        win = {}
        win["rows"] = int(_facade_float(wsrc.get("rows", 1), 1, 1, 2,
                                        f"Здание {idx}.windows.rows", warnings))
        win["cols"] = int(_facade_float(wsrc.get("cols", 4), 4, 1, 10,
                                        f"Здание {idx}.windows.cols", warnings))
        win["margin_x_m"] = _facade_float(wsrc.get("margin_x_m", 1.0), 1.0, 0.05, 5.0,
                                          f"Здание {idx}.windows.margin_x_m", warnings)
        win["margin_y_m"] = _facade_float(wsrc.get("margin_y_m", 0.8), 0.8, 0.05, 3.0,
                                          f"Здание {idx}.windows.margin_y_m", warnings)
        win["w_m"] = _facade_float(wsrc.get("w_m", 1.5), 1.5, 0.3, 5.0,
                                   f"Здание {idx}.windows.w_m", warnings)
        win["h_m"] = _facade_float(wsrc.get("h_m", 1.5), 1.5, 0.3, 4.0,
                                   f"Здание {idx}.windows.h_m", warnings)
        max_mx = max(0.05, (bld["width_m"] - 0.3 * win["cols"]) / 2)
        win["margin_x_m"] = min(win["margin_x_m"], max_mx)
        max_my = max(0.05, (bld["floor_height"] - 0.3 * win["rows"]) / 2)
        win["margin_y_m"] = min(win["margin_y_m"], max_my)
        win["w_m"] = min(win["w_m"], (bld["width_m"] - 2 * win["margin_x_m"]) / win["cols"])
        win["h_m"] = min(win["h_m"], (bld["floor_height"] - 2 * win["margin_y_m"]) / win["rows"])
        bld["windows"] = win
        bals = []
        raw_bals = b.get("balconies") if isinstance(b.get("balconies"), list) else []
        for j, bal in enumerate(raw_bals[:20], start=1):
            if not isinstance(bal, dict):
                warnings.append(f"Здание {idx} балкон {j}: не объект — пропущен")
                continue
            try:
                floor = int(bal.get("floor", 0))
                x = float(bal.get("x_m", bld["width_m"] / 2))
                w_b = float(bal.get("w_m", 3.0))
                d_b = float(bal.get("d_m", 1.2))
            except (TypeError, ValueError):
                warnings.append(f"Здание {idx} балкон {j}: неверные размеры — пропущен")
                continue
            if x != x or w_b != w_b or d_b != d_b:  # NaN
                continue
            if floor < 2 or floor > bld["storeys"]:
                continue  # 1-й этаж — не балкон; вне диапазона — тихий skip
            if not (0.5 <= w_b <= bld["width_m"]) or not (0.3 <= d_b <= 5.0):
                warnings.append(f"Здание {idx} балкон {j}: размеры вне диапазона — пропущен")
                continue
            lo, hi = w_b / 2, bld["width_m"] - w_b / 2
            if x < lo or x > hi:
                x = max(lo, min(hi, x))
                warnings.append(f"Здание {idx} балкон {j}: центр вне фасада — кламп {x:g}")
            bals.append({"floor": floor, "x_m": x, "w_m": w_b, "d_m": d_b})
        bld["balconies"] = bals
        src_colors = b.get("colors") if isinstance(b.get("colors"), dict) else {}
        colors = {}
        for key, default in (("walls", "#c8b89a"), ("roof", "#52616b"),
                             ("plinth", "#8d8d8d")):
            v = src_colors.get(key)
            colors[key] = v if _is_hex(v) else default
        bld["colors"] = colors
        out["buildings"].append(bld)
    if len(scene["buildings"]) > 3:
        warnings.append("buildings: больше 3 — лишние отброшены")
    if not out["buildings"]:
        raise ValueError("На картинке не найдено зданий для 3D-модели")
    if not main_seen:
        out["buildings"][0]["main"] = True  # первое — главное

    ctx_raw = scene.get("context") if isinstance(scene.get("context"), dict) else {}
    ctx = {"trees": [], "cars": [], "people": []}
    raw_trees = ctx_raw.get("trees")
    if isinstance(raw_trees, list):
        for it in raw_trees[:40]:
            if not isinstance(it, dict):
                continue
            try:
                x, y = float(it.get("x_m", 0.0)), float(it.get("y_m", 0.0))
            except (TypeError, ValueError):
                continue
            if x != x or y != y:
                continue
            ctx["trees"].append({
                "x_m": _clamp(x, -150.0, 150.0), "y_m": _clamp(y, -150.0, 150.0),
                "h_m": _facade_float(it.get("h_m", 6.0), 6.0, 2.0, 30.0,
                                     "tree.h_m", warnings),
                "crown_d_m": _facade_float(it.get("crown_d_m", 3.0), 3.0, 1.0, 10.0,
                                           "tree.crown_d_m", warnings)})
    raw_cars = ctx_raw.get("cars")
    if isinstance(raw_cars, list):
        for it in raw_cars[:20]:
            if not isinstance(it, dict):
                continue
            try:
                x, y = float(it.get("x_m", 0.0)), float(it.get("y_m", 0.0))
                rot = float(it.get("rot_deg", 0.0))
            except (TypeError, ValueError):
                continue
            if x != x or y != y:
                continue
            ctx["cars"].append({"x_m": _clamp(x, -150.0, 150.0),
                                "y_m": _clamp(y, -150.0, 150.0),
                                "rot_deg": _clamp(rot, -180.0, 180.0)})
    raw_people = ctx_raw.get("people")
    if isinstance(raw_people, list):
        for it in raw_people[:40]:
            if not isinstance(it, dict):
                continue
            try:
                x, y = float(it.get("x_m", 0.0)), float(it.get("y_m", 0.0))
            except (TypeError, ValueError):
                continue
            if x != x or y != y:
                continue
            ctx["people"].append({"x_m": _clamp(x, -150.0, 150.0),
                                  "y_m": _clamp(y, -150.0, 150.0)})
    out["context"] = ctx
    return out, warnings
```

- [ ] **Step 4: Run tests** — `t.test_validate_scene()` PASS; весь файл: из корня `PYTHONUTF8=1 venv/Scripts/python.exe tests/test_threed.py` — OK.

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(3d): промпт и валидация сценария «Сцена» (камера, 1-3 здания, деревья/машины/люди)" -- threed/threed_scenarios.py tests/test_threed.py
```

---

### Task 6: build_scene — здания, окна трёх граней, земля

**Files:**
- Modify: `threed/threed_build.py` (новая секция после блока интерьера)
- Test: `tests/test_threed.py`

**Interfaces:**
- Consumes: чистая сцена Task 5 (`validate_scene` выход).
- Produces: `build_scene(scene: dict, ifc_path: Path, preview_path: Path, meta: dict) -> Path`; элементы: CONCEPTUAL_STOREY/WINDOW/BALCONY/PLINTH/ROOF/TREE/CAR/PERSON/GROUND; pset `SceneModel` на IfcBuilding, pset `CameraHint` на IfcProject (`AzimuthDeg`, `EyeHeightM`, `DistM`). Потребитель: Task 8 (роутер).

- [ ] **Step 1: Write the failing test** — добавить в `tests/test_threed.py`:

```python
def test_build_scene():
    import ifcopenshell
    from threed.threed_scenarios import validate_scene
    from threed.threed_build import build_scene

    clean, _ = validate_scene(sample_scene_scene())
    TMP.mkdir(exist_ok=True)
    ifc = TMP / "3D_scene_test.ifc"
    prev = TMP / "3D_scene_test_preview.png"
    path = build_scene(clean, ifc, prev,
                       {"Scenario": "scene", "Prompt": "тест", "Model": "test/model",
                        "Source": "3D Design"})
    assert path == ifc and ifc.is_file() and prev.is_file()

    m = ifcopenshell.open(str(ifc))
    assert m.schema == "IFC4"
    gids = [r.GlobalId for r in m.by_type("IfcRoot")]
    assert len(gids) == len(set(gids)), "GlobalId не уникальны"
    proxies = m.by_type("IfcBuildingElementProxy")
    by_type = {}
    for p in proxies:
        by_type[p.ObjectType] = by_type.get(p.ObjectType, 0) + 1
    assert by_type.get("CONCEPTUAL_STOREY") == 7 + 3      # тома-этажи 2 зданий
    assert by_type.get("CONCEPTUAL_PLINTH") == 2
    assert by_type.get("CONCEPTUAL_ROOF") == 1            # gable у второго
    # главное: фронт 7 этажей × 8 окон + боковины 2 × 7 × side_cols
    # depth 12: side_cols = clamp(round((12-1.6)/2.4475),1,6)=4 -> 7*(8+2*4)=112
    assert by_type.get("CONCEPTUAL_WINDOW") == 112 + 3 * 4
    assert by_type.get("CONCEPTUAL_BALCONY") == 1
    assert by_type.get("CONCEPTUAL_TREE") == 2            # ствол+крона = 2proxy на дерево
    assert by_type.get("CONCEPTUAL_CAR") == 1
    assert by_type.get("CONCEPTUAL_PERSON") == 2
    assert by_type.get("CONCEPTUAL_GROUND") == 1
    # фронт главного здания на IFC -Y: окна при y_m=0 -> центры -depth/2
    from ifcopenshell.util.placement import get_local_placement
    wins = [p for p in proxies if p.ObjectType == "CONCEPTUAL_WINDOW"
            and "Гл" in (p.Name or "")]
    assert wins and all(get_local_placement(w.ObjectPlacement)[1, 3] < -5.0 for w in wins)
    # CameraHint на проекте
    from ifcopenshell.util.element import get_psets
    hint = get_psets(m.by_type("IfcProject")[0]).get("CameraHint", {})
    assert abs(hint.get("AzimuthDeg", 999) - (-30)) < 1e-6
    assert abs(hint.get("EyeHeightM", 0) - 1.7) < 1e-6
    sm = get_psets(m.by_type("IfcBuilding")[0]).get("SceneModel", {})
    assert sm.get("Buildings") == 2 and sm.get("WindowsTotal") == 112 + 12
    print("test_build_scene OK")
```

Вызвать `test_build_scene()` в блоке прогонов.

- [ ] **Step 2: Run test to verify it fails**

```bash
cd tests && PYTHONUTF8=1 ../venv/Scripts/python.exe -c "import test_threed as t; t.test_build_scene()"
```

Expected: FAIL — `ImportError: cannot import name 'build_scene'`.

- [ ] **Step 3: Implement** — добавить в конец `threed/threed_build.py`:

```python
# ===================== Фаза 4: сценарий «Сцена» (camera mapping) =====================

ASSUMPTION_SCENE = (
    "Концептуальная уличная сцена по фотографии (3D Design). Здания, деревья, "
    "автомобили и люди — схематичные объёмы-примитивы; перспектива принята за "
    "ортогональную, размеры оценочные по опорным объектам. Не использовать как "
    "обмерную или рабочую документацию."
)

SCENE_COLORS = {
    "walls": "#c8b89a", "roof": "#52616b", "plinth": "#8d8d8d",
    "glazing": "#202830", "balcony": "#9aa3ad", "tree": "#4e7a4e",
    "trunk": "#7a5b3a", "car": "#5a6470", "person": "#38424e", "ground": "#b9c2b4",
}


def _scene_box(model, body, fstyles, container, name, bw, bd, bh,
               cx, cy, z, color_key, object_type, rot_deg=0.0):
    """Примитив-бокс сцены (как box() фасада, +поворот вокруг Z)."""
    product = _api("root.create_entity", file=model, ifc_class="IfcBuildingElementProxy",
                   predefined_type="USERDEFINED", name=name)
    product.ObjectType = object_type
    pts = [[-bw / 2, -bd / 2], [bw / 2, -bd / 2], [bw / 2, bd / 2], [-bw / 2, bd / 2]]
    profile = _api("profile.add_arbitrary_profile", file=model, profile=pts, name=name)
    representation = _api("geometry.add_profile_representation", file=model, context=body,
                          profile=profile, depth=bh, cardinal_point=None)
    _api("geometry.assign_representation", file=model, product=product,
         representation=representation)
    _api("spatial.assign_container", file=model, products=[product],
         relating_structure=container)
    matrix = np.eye(4)
    rad = np.radians(rot_deg)
    matrix[0, 0], matrix[0, 1] = np.cos(rad), -np.sin(rad)
    matrix[1, 0], matrix[1, 1] = np.sin(rad), np.cos(rad)
    matrix[:3, 3] = [float(cx), float(cy), float(z)]
    _api("geometry.edit_object_placement", file=model, product=product, matrix=matrix)
    _api("style.assign_representation_styles", file=model,
         shape_representation=representation, styles=[fstyles[color_key]])
    return product


def build_scene(scene, ifc_path, preview_path, meta):
    """Сцена улицы (validate_scene) -> IFC4 + PNG-план. Возвращает ifc_path."""
    data = dict(scene)
    data.setdefault("camera", {})
    data.setdefault("buildings", [])
    data.setdefault("context", {})
    colors = dict(SCENE_COLORS)

    model = _api("project.create_file", version="IFC4")
    project = _api("root.create_entity", file=model, ifc_class="IfcProject",
                   name=data.get("project_name", "3D Design — сцена"))
    project.Description = ASSUMPTION_SCENE
    units = [_api("unit.add_si_unit", file=model, unit_type=t)
             for t in ("LENGTHUNIT", "AREAUNIT", "VOLUMEUNIT")]
    _api("unit.assign_unit", file=model, units=units)
    context = _api("context.add_context", file=model, context_type="Model")
    body = _api("context.add_context", file=model, context_type="Model",
                context_identifier="Body", target_view="MODEL_VIEW", parent=context)
    site = _api("root.create_entity", file=model, ifc_class="IfcSite", name="Участок")
    _api("aggregate.assign_object", file=model, products=[site], relating_object=project)
    _api("geometry.edit_object_placement", file=model, product=site, matrix=np.eye(4))
    _properties(model, project, "DevBIM", {
        "Source": meta.get("Source", "3D Design"), "Scenario": meta.get("Scenario", "scene"),
        "Prompt": (meta.get("Prompt") or "")[:1024], "Model": meta.get("Model", ""),
        "ApproximateGeometry": True, "Notes": ASSUMPTION_SCENE,
    })
    building = _api("root.create_entity", file=model, ifc_class="IfcBuilding",
                    name="Сцена по фото")
    building.Description = ASSUMPTION_SCENE
    _api("aggregate.assign_object", file=model, products=[building], relating_object=site)
    _api("geometry.edit_object_placement", file=model, product=building, matrix=np.eye(4))
    storey = _api("root.create_entity", file=model, ifc_class="IfcBuildingStorey",
                  name="Уровень сцены")
    storey.Elevation = 0.0
    _api("aggregate.assign_object", file=model, products=[storey], relating_object=building)
    _api("geometry.edit_object_placement", file=model, product=storey, matrix=np.eye(4))

    fstyles = {}
    for key, color in colors.items():
        r, g, b = matplotlib.colors.to_rgb(color)
        style = _api("style.add_style", file=model, name=f"Scene{key.capitalize()}")
        _api("style.add_surface_style", file=model, style=style,
             ifc_class="IfcSurfaceStyleShading",
             attributes={"SurfaceColour": {"Name": key, "Red": r, "Green": g, "Blue": b},
                         "Transparency": 0.0})
        fstyles[key] = style

    def boxx(name, bw, bd, bh, cx, cy, z, color_key, otype, rot=0.0):
        return _scene_box(model, body, fstyles, storey, name, bw, bd, bh,
                          cx, cy, z, color_key, otype, rot)

    windows_total = 0
    main_done = False
    for b_idx, b in enumerate(data["buildings"], start=1):
        w, d = b["width_m"], b["depth_m"]
        fh, n = b["floor_height"], b["storeys"]
        cx0, cy0 = b["x_m"], b["y_m"]
        tag = "Гл" if b.get("main") else f"Д{b_idx}"
        win = b["windows"]
        for f in range(n):
            boxx(f"Стены {tag} · этаж {f + 1}", w, d, fh, cx0, cy0, f * fh,
                 "walls", "CONCEPTUAL_STOREY")
        # фронт (IFC -Y): сетка как у фасада, x_m балкона — от левого края
        usable = w - 2 * win["margin_x_m"]
        gap = (usable - win["cols"] * win["w_m"]) / (win["cols"] - 1) \
            if win["cols"] > 1 else 0.0
        pitch = win["w_m"] + max(gap, 0.0)
        xs = [cx0 - w / 2 + win["margin_x_m"] + i * pitch + win["w_m"] / 2
              for i in range(win["cols"])]
        zs = [win["margin_y_m"] + win["h_m"] / 2]  # rows=1..2; центр строки
        if win["rows"] > 1:
            mid = (fh - 2 * win["margin_y_m"]) / 2
            zs = [win["margin_y_m"] + win["h_m"] / 2, mid + win["h_m"] / 2]
        for f in range(n):
            for z_in in zs:
                for x in xs:
                    boxx(f"Окно {tag} Э{f + 1}-{xs.index(x) + 1}", win["w_m"], 0.12,
                         win["h_m"], x, cy0 - d / 2, f * fh + z_in,
                         "glazing", "CONCEPTUAL_WINDOW")
                    windows_total += 1
        main_done = main_done or b.get("main")
        if b.get("main"):
            # боковины ±X упрощённой сеткой (глухие боковины рендер не достраивает)
            side_cols = max(1, min(6, round((d - 2 * win["margin_x_m"]) / pitch))) \
                if pitch > 0 else 1
            ys = [cy0 - d / 2 + win["margin_x_m"] + k * pitch + win["w_m"] / 2
                  for k in range(side_cols)]
            for f in range(n):
                for z_in in zs:
                    for sgn, sname in ((-1, "L"), (1, "R")):
                        for y in ys:
                            boxx(f"Окно {tag} Э{f + 1}{sname}-{ys.index(y) + 1}",
                                 0.12, win["w_m"], win["h_m"],
                                 cx0 + sgn * (w / 2 + 0.06), y, f * fh + z_in,
                                 "glazing", "CONCEPTUAL_WINDOW")
                            windows_total += 1
        for j, bal in enumerate(b["balconies"], start=1):
            bal_z = (bal["floor"] - 1) * fh - 0.18
            boxx(f"Балкон {tag} {j} · этаж {bal['floor']}", bal["w_m"], bal["d_m"], 0.18,
                 cx0 + bal["x_m"] - w / 2, cy0 - (d / 2 + bal["d_m"] / 2), bal_z,
                 "balcony", "CONCEPTUAL_BALCONY")
        boxx(f"Цоколь {tag}", w + 0.2, d + 0.2, 0.6, cx0, cy0, 0.0,
             "plinth", "CONCEPTUAL_PLINTH")
        if b["roof"] == "gable" and b["roof_height"] > 0.05:
            ridge = _api("root.create_entity", file=model,
                         ifc_class="IfcBuildingElementProxy",
                         predefined_type="USERDEFINED", name=f"Крыша {tag} двускатная")
            ridge.ObjectType = "CONCEPTUAL_ROOF"
            prof = [[-w / 2, 0.0], [w / 2, 0.0], [0.0, b["roof_height"]]]
            profile = _api("profile.add_arbitrary_profile", file=model, profile=prof,
                           name=f"Крыша {tag}")
            representation = _api("geometry.add_profile_representation", file=model,
                                  context=body, profile=profile, depth=d,
                                  cardinal_point=None)
            _api("geometry.assign_representation", file=model, product=ridge,
                 representation=representation)
            _api("spatial.assign_container", file=model, products=[ridge],
                 relating_structure=storey)
            matrix = np.array([
                [1.0, 0.0, 0.0, cx0],
                [0.0, 0.0, 1.0, cy0 - d / 2],
                [0.0, 1.0, 0.0, n * fh],
                [0.0, 0.0, 0.0, 1.0],
            ])
            _api("geometry.edit_object_placement", file=model, product=ridge,
                 matrix=matrix)
            _api("style.assign_representation_styles", file=model,
                 shape_representation=representation, styles=[fstyles["roof"]])

    ctx = data["context"]
    for t_idx, tr in enumerate(ctx.get("trees", []), start=1):
        h, crown = tr["h_m"], tr["crown_d_m"]
        boxx(f"Дерево {t_idx} · ствол", 0.3, 0.3, h * 0.4, tr["x_m"], tr["y_m"], 0.0,
             "trunk", "CONCEPTUAL_TREE")
        boxx(f"Дерево {t_idx} · крона", crown, crown, h * 0.6, tr["x_m"], tr["y_m"],
             h * 0.4, "tree", "CONCEPTUAL_TREE")
    for c_idx, car in enumerate(ctx.get("cars", []), start=1):
        boxx(f"Машина {c_idx}", 1.8, 4.5, 1.4, car["x_m"], car["y_m"], 0.0,
             "car", "CONCEPTUAL_CAR", rot=car.get("rot_deg", 0.0))
    for p_idx, per in enumerate(ctx.get("people", []), start=1):
        boxx(f"Человек {p_idx}", 0.5, 0.3, 1.7, per["x_m"], per["y_m"], 0.0,
             "person", "CONCEPTUAL_PERSON")

    # земля: общий габарит + запас 4 м
    all_xy = [(b["x_m"] - b["width_m"] / 2, b["y_m"] - b["depth_m"] / 2,
               b["x_m"] + b["width_m"] / 2, b["y_m"] + b["depth_m"] / 2)
              for b in data["buildings"]]
    for it in ctx.get("trees", []) + ctx.get("cars", []) + ctx.get("people", []):
        all_xy.append((it["x_m"] - 2, it["y_m"] - 2, it["x_m"] + 2, it["y_m"] + 2))
    x0 = min(p[0] for p in all_xy) - 4 if all_xy else -20
    y0 = min(p[1] for p in all_xy) - 4 if all_xy else -20
    x1 = max(p[2] for p in all_xy) + 4 if all_xy else 20
    y1 = max(p[3] for p in all_xy) + 4 if all_xy else 20
    boxx("Земля", x1 - x0, y1 - y0, 0.25, (x0 + x1) / 2, (y0 + y1) / 2, -0.25,
         "ground", "CONCEPTUAL_GROUND")

    cam = data["camera"]
    _properties(model, project, "CameraHint", {
        "AzimuthDeg": cam.get("azimuth_deg", 25.0),
        "EyeHeightM": cam.get("eye_height_m", 1.6),
        "DistM": cam.get("dist_m", 35.0),
    })
    _properties(model, building, "SceneModel", {
        "Buildings": len(data["buildings"]),
        "Trees": len(ctx.get("trees", [])),
        "Cars": len(ctx.get("cars", [])),
        "People": len(ctx.get("people", [])),
        "WindowsTotal": windows_total,
        "OrthoAssumption": True, "Source": "3D Design", "Notes": ASSUMPTION_SCENE,
    })

    _write_header(model, ifc_path)
    model.write(str(ifc_path))
    _draw_scene_preview(data, preview_path)
    return ifc_path
```

- [ ] **Step 4: Run test** — `t.test_build_scene()` PASS. При расхождении счётчика окон сверить арифметику: фронт 7×8=56, боковины 7×4×2=56, итого главное 112; второе 3×4=12.

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(3d): сборщик сцены — здания (окна фронта+боковин, балконы, крыши), примитивы, земля, pset CameraHint" -- threed/threed_build.py tests/test_threed.py
```

---

### Task 7: Превью-план сцены

**Files:**
- Modify: `threed/threed_build.py` (`_draw_scene_preview`, вызывается из Task 6)
- Test: `tests/test_threed.py` (расширение `test_build_scene`)

**Interfaces:**
- Consumes: данные Task 6.

- [ ] **Step 1: Write the failing test** — дополнить `test_build_scene` (Task 6 уже пишет prev):

```python
    from PIL import Image
    im = Image.open(prev)
    assert im.size[0] > 400 and im.size[1] > 300
```

(план рисуется; содержательную проверку даёт E2E Task 11).

- [ ] **Step 2: Run test** — `t.test_build_scene()` FAIL (`_draw_scene_preview` не определена — NameError при вызове build_scene).

- [ ] **Step 3: Implement** — добавить в конец `threed/threed_build.py`:

```python
def _draw_scene_preview(data, preview_path):
    """План сцены сверху: здания, контекст, маркер камеры с направлением."""
    import matplotlib.pyplot as plt
    import matplotlib.transforms
    from matplotlib.patches import Circle, FancyArrow, Rectangle

    fig, ax = plt.subplots(figsize=(10, 8), dpi=140)
    ctx = data["context"]
    for b in data["buildings"]:
        face = "#d9c7a7" if b.get("main") else "#c4cdd8"
        ax.add_patch(Rectangle((b["x_m"] - b["width_m"] / 2, b["y_m"] - b["depth_m"] / 2),
                               b["width_m"], b["depth_m"], facecolor=face,
                               edgecolor="#263747", linewidth=1.2))
        ax.text(b["x_m"], b["y_m"], f"{b['storeys']} эт.", ha="center", va="center",
                fontsize=9, color="#15232e", fontweight="bold")
    for t in ctx.get("trees", []):
        ax.add_patch(Circle((t["x_m"], t["y_m"]), t["crown_d_m"] / 2,
                            facecolor="#7fae7f", edgecolor="#3c603c", alpha=.85))
    for c in ctx.get("cars", []):
        rot = c.get("rot_deg", 0.0) or 0.0
        tr = matplotlib.transforms.Affine2D().rotate_deg_around(
            c["x_m"], c["y_m"], rot) + ax.transData
        rect = Rectangle((c["x_m"] - 0.9, c["y_m"] - 2.25), 1.8, 4.5,
                         facecolor="#9aa3ad", edgecolor="#263747")
        rect.set_transform(tr)
        ax.add_patch(rect)
    for p in ctx.get("people", []):
        ax.add_patch(Circle((p["x_m"], p["y_m"]), 0.4, facecolor="#38424e"))
    cam = data["camera"]
    az = np.radians(cam.get("azimuth_deg", 25.0))
    dist = cam.get("dist_m", 35.0)
    main = next((b for b in data["buildings"] if b.get("main")), {"x_m": 0, "y_m": 0})
    cxp = main["x_m"] + dist * np.sin(az)
    cyp = main["y_m"] + dist * np.cos(az)
    ax.add_patch(Circle((cxp, cyp), 1.2, facecolor="#e2574c", edgecolor="#7a1f18"))
    ax.add_patch(FancyArrow(cxp, cyp, -dist * np.sin(az) * 0.3, -dist * np.cos(az) * 0.3,
                            width=0.5, head_width=2.0, color="#e2574c", alpha=.8))
    ax.text(cxp, cyp + 2.5, f"камера {cam.get('azimuth_deg', 25):g}° · {dist:g} м",
            ha="center", fontsize=8, color="#7a1f18")
    ax.set_aspect("equal")
    ax.autoscale(True)
    ax.set_title("3D Design — сцена: план (схематично, метры)", fontsize=13)
    ax.axis("off")
    fig.tight_layout()
    preview_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(preview_path, facecolor="white")
    plt.close(fig)
```

- [ ] **Step 4: Run tests** — `t.test_build_scene()` PASS.

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(3d): превью сцены — план с контекстом и маркером камеры" -- threed/threed_build.py tests/test_threed.py
```

---

### Task 8: Роутер — сценарий scene + camHint в ответе

**Files:**
- Modify: `threed/threed_router.py` (SCENARIOS, ветвления, return)
- Test: `tests/test_threed.py`

**Interfaces:**
- Consumes: Task 5/6/7 (`SYSTEM_SCENE`, `validate_scene`, `build_scene`).
- Produces: `POST /api/v1/threed/generate {scenario:"scene"}` -> `{name, warnings, camHint:{azimuth_deg,eye_height_m,dist_m}}` (потребитель — Task 9).

- [ ] **Step 1: Write the failing test** — добавить в `tests/test_threed.py`:

```python
def test_generate_impl_scene():
    from PIL import Image
    import threed.threed_router as R
    R._vlm_list_cached = lambda: []  # тесты без сети
    scene = sample_scene_scene()
    R._call_vlm = _mock_vlm_ok("```json\n" + json.dumps(scene, ensure_ascii=False) + "\n```")
    TMP.mkdir(exist_ok=True)
    img = Image.new("RGB", (691, 647), (250, 250, 250))
    res = R._generate_impl("scene", "тест сцены", img, TMP)
    assert res["name"].startswith("3D_scene_") and res["name"].endswith(".ifc")
    assert (TMP / res["name"]).is_file()
    assert res["camHint"] == {"azimuth_deg": -30, "eye_height_m": 1.7, "dist_m": 40}
    assert "scene" in R.SCENARIOS
    try:
        R._generate_impl("attic", "", img, TMP)
        raise AssertionError("ожидалась ошибка")
    except ValueError as e:
        assert "scene" in str(e)
    print("test_generate_impl_scene OK")
```

Вызвать в блоке прогонов.

- [ ] **Step 2: Run test to verify it fails**

```bash
cd tests && PYTHONUTF8=1 ../venv/Scripts/python.exe -c "import test_threed as t; t.test_generate_impl_scene()"
```

Expected: FAIL — `scene` не в SCENARIOS (ValueError «в разработке»).

- [ ] **Step 3: Implement** — четыре правки в `threed/threed_router.py`:

(a) `SCENARIOS = {"plan", "facade", "interior"}` → `SCENARIOS = {"plan", "facade", "interior", "scene"}`;

(b) сообщение об ошибки: `(доступны: plan, facade, interior)` → `(доступны: plan, facade, interior, scene)`;

(c) цепочка промпта:

```python
        system = (threed_scenarios.SYSTEM_SCENE if scenario == "scene"
                  else threed_scenarios.SYSTEM_INTERIOR if scenario == "interior"
                  else threed_scenarios.SYSTEM_FACADE if scenario == "facade"
                  else threed_scenarios.SYSTEM_GENPLAN)
```

(d) ветвление валидации (после блока interior) и сборки, и ответ. Валидация:

```python
    if scenario == "interior":
        scene, warnings = threed_scenarios.validate_interior(
            scene, image.width, image.height)
    elif scenario == "scene":
        scene, warnings = threed_scenarios.validate_scene(scene)
    elif scenario == "facade":
        scene, warnings = threed_scenarios.validate_facade(scene)
    else:
        scene, warnings = threed_scenarios.validate_genplan(
            scene, image.width, image.height)
```

Сборка:

```python
    if scenario == "interior":
        threed_build.build_interior(scene, ifc_path, preview_path, meta)
    elif scenario == "scene":
        threed_build.build_scene(scene, ifc_path, preview_path, meta)
    elif scenario == "facade":
        threed_build.build_facade(scene, ifc_path, preview_path, meta)
    else:
        threed_build.build_genplan(scene, image, ifc_path, preview_path, meta)
```

Ответ (заменить `return {"name": name, "warnings": warnings}`):

```python
    res = {"name": name, "warnings": warnings}
    if scenario == "scene":
        res["camHint"] = scene["camera"]
    return res
```

- [ ] **Step 4: Деплой и тесты**

```bash
PYTHONUTF8=1 venv/Scripts/python.exe setup_threed.py
cd tests && PYTHONUTF8=1 ../venv/Scripts/python.exe -c "import test_threed as t; t.test_generate_impl_scene(); t.test_generate_impl(); t.test_generate_impl_facade(); t.test_generate_impl_interior()"
```

Expected: все OK.

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(3d): роутер принимает сценарий scene, ответ несёт camHint (камера фото)" -- threed/threed_router.py tests/test_threed.py
```

---

### Task 9: Модалка — плитка «Сцена», placeholder, camHint

**Files:**
- Modify: `imagerouter/devbim_topright_buttons.js` (TEXTS RU/EN, плитки, карта ph, run3D)
- Test: `tests/test_threed.py` (расширение `test_widget_3d_modal`)

**Interfaces:**
- Consumes: ответ роутера Task 8 (`j.camHint`).
- Produces: плитка `data-s="scene"`, `promptPhScene` RU/EN, запись `localStorage["devbim:ifc:camHint"]` (потребитель — Task 10).

- [ ] **Step 1: Write the failing test** — дополнить `test_widget_3d_modal`:

```python
    # фаза 4: плитка «Сцена» активна, placeholder, camHint
    assert '<button class="devbim-3d-tile" data-s="scene"><span>🌇</span>' in src
    assert 'data-s="scene" disabled' not in src
    assert "promptPhScene: 'Уточнения:" in src
    assert "promptPhScene: 'Hints:" in src
    assert "var ph = {plan: t().promptPhPlan" in src and "scene: t().promptPhScene" in src
    assert "devbim:ifc:camHint" in src
```

- [ ] **Step 2: Run test** — `t.test_widget_3d_modal()` FAIL (нет плитки scene).

- [ ] **Step 3: Implement** — в `devbim_topright_buttons.js`:

(a) RU TEXTS (рядом с interior): `scene: 'Сцена'` и `promptPhScene: 'Уточнения: «2 дома: главный 7 этажей, второй 3 справа; деревья вдоль дороги; камера слева»'`;

(b) EN TEXTS: `scene: 'Scene'` и `promptPhScene: 'Hints: "2 houses: main 7 storeys, second 3 on the right; trees along the road; camera on the left"'`;

(c) плитка после интерьера:

```js
      '<button class="devbim-3d-tile" data-s="scene"><span>🌇</span>' + t().scene + '</button>' +
```

(d) карта placeholder-ов:

```js
          var ph = {plan: t().promptPhPlan, facade: t().promptPhFacade,
                    interior: t().promptPhInterior, scene: t().promptPhScene};
```

(e) в run3D после `localStorage.setItem('devbim:ifc:lastModel', j.name)`:

```js
      if (j.camHint) { try { localStorage.setItem('devbim:ifc:camHint',
        JSON.stringify(j.camHint)); } catch (e) {} }
```

- [ ] **Step 4: Run tests + node --check** — `t.test_widget_3d_modal()` PASS (внутри уже есть `node --check`).

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(3d): плитка «Сцена» в модалке 3D Design + camHint в localStorage" -- imagerouter/devbim_topright_buttons.js tests/test_threed.py
```

---

### Task 10: Вьювер — applyCamHint вместо fitModel

**Files:**
- Modify: `ifc/ifcviewer.html` (функция applyCamHint + вызов в loadIfc)
- Test: `tests/test_threed.py` (расширение `test_ifcviewer_autoload`)

**Interfaces:**
- Consumes: `localStorage["devbim:ifc:camHint"]` = `{"azimuth_deg","eye_height_m","dist_m"}` (Task 9); фронт сцены/фасада после трансформа = world +Z (Task 3/6).
- Produces: камера после загрузки модели стоит как на фото (az 0 = фронтально с юга, уровень глаза из подсказки); подсказка одноразовая.

- [ ] **Step 1: Write the failing test** — дополнить `test_ifcviewer_autoload`:

```python
    # фаза 4: camHint — камера по подсказке генерации сцены
    assert "function applyCamHint()" in m.group(1)
    assert "devbim:ifc:camHint" in m.group(1)
    assert "if (!applyCamHint()) fitModel();" in m.group(1)
```

- [ ] **Step 2: Run test** — `t.test_ifcviewer_autoload()` FAIL.

- [ ] **Step 3: Implement** — в `ifc/ifcviewer.html`:

(a) после функции `fitModel()` добавить:

```js
// Фаза 4 (сцена): одноразовая подсказка камеры от 3D-генерации — камера
// как на фото (az 0 = фронтально со стороны world +Z, «+» = вправо).
function applyCamHint() {
  let hint = null;
  try { hint = JSON.parse(localStorage.getItem("devbim:ifc:camHint") || "null"); }
  catch { hint = null; }
  try { localStorage.removeItem("devbim:ifc:camHint"); } catch {}
  if (!hint || typeof hint.azimuth_deg !== "number") return false;
  const box = modelBox();
  if (!box || box.isEmpty()) return false;
  const c = box.getCenter(new Vector3());
  const size = box.getSize(new Vector3());
  const dist = Math.max(hint.dist_m || 35, size.length() * 0.35);
  const az = hint.azimuth_deg * Math.PI / 180;
  const h = Math.max(0.5, Math.min(30, hint.eye_height_m || 1.6));
  world.camera.controls.setLookAt(
    c.x + dist * Math.sin(az), box.min.y + h, c.z + dist * Math.cos(az),
    c.x, c.y, c.z);
  world.camera.controls.update();
  setStatus("Камера по подсказке сцены (как на фото)");
  return true;
}
```

(b) в `loadIfc` заменить вызов `fitModel();` на:

```js
  if (!applyCamHint()) fitModel();
```

- [ ] **Step 4: Деплой и тесты**

```bash
PYTHONUTF8=1 venv/Scripts/python.exe setup_ifcviewer.py
cd tests && PYTHONUTF8=1 ../venv/Scripts/python.exe -c "import test_threed as t; t.test_ifcviewer_autoload()"
```

Expected: PASS (node --check внутри).

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(3d): applyCamHint в IFC-вьювере — камера по подсказке сцены вместо fitModel" -- ifc/ifcviewer.html tests/test_threed.py
```

---

### Task 11: Деплой, живой smoke, скриншоты, документация

**Files:**
- Deploy: `setup_threed.py`, `setup_imagerouter.py`, `setup_ifcviewer.py`
- Docs: `HANDOFF.md` (п.42), `README.md`, скриншоты `docs/3d-design-scene-{modal,plan,view}.png`

**Interfaces:**
- Consumes: всё выше.

- [ ] **Step 1: Полный деплой + рестарт + тесты**

```bash
PYTHONUTF8=1 venv/Scripts/python.exe setup_imagerouter.py
PYTHONUTF8=1 venv/Scripts/python.exe setup_threed.py
PYTHONUTF8=1 venv/Scripts/python.exe setup_ifcviewer.py
powershell -ExecutionPolicy Bypass -File _restart_server.ps1
PYTHONUTF8=1 venv/Scripts/python.exe tests/test_threed.py
```

Expected: все функции OK.

- [ ] **Step 2: Живой smoke (1 генерация, ~$0.05–0.15)** — POST /api/v1/threed/generate со сценарием scene и `data/probe/ref_photo.png` (dataURL), cookie devbim_auth. Проверки: 200, `name` = 3D_scene_*.ifc, `camHint.azimuth_deg` в [-75, 75], файл и превью в data/ifc, warnings — записать в отчёт.

```bash
PYTHONUTF8=1 venv/Scripts/python.exe - <<'EOF'
import base64, json, re, requests
from pathlib import Path
ROOT = Path('.').resolve()
pw = (re.search(r"^SITE_PASSWORD=(.+)$", (ROOT/'.env').read_text(encoding='utf-8'), re.M) or [None,''])[1].strip().strip('"')
s = requests.Session()
r = s.post('http://127.0.0.1:9090/auth/login', data={'password': pw}, allow_redirects=False, timeout=15)
durl = 'data:image/png;base64,' + base64.b64encode((ROOT/'data'/'probe'/'ref_photo.png').read_bytes()).decode()
r = s.post('http://127.0.0.1:9090/api/v1/threed/generate',
           json={'scenario': 'scene', 'prompt': '', 'image': durl}, timeout=300)
print(r.status_code, r.text[:400])
assert r.status_code == 200
j = r.json()
assert j['name'].startswith('3D_scene_') and -75 <= j['camHint']['azimuth_deg'] <= 75
print('SMOKE OK:', j['name'], j['camHint'], j['warnings'])
EOF
```

- [ ] **Step 3: E2E вьювера с камерой** — headless: localStorage lastModel = fresh scene IFC + camHint из ответа smoke → загрузить → проверить позицию камеры (`__ifc.world.camera.three.position` ≈ ожидаемой по hint: глаз ≈ box.min.y + eye_h) и сделать скриншоты: план-превью из data/ifc, вид вьювера. Скриншоты в `docs/3d-design-scene-{plan,view}.png`. Паттерн — Task 4 E2E-скрипт (заменить имя модели и проверку: `pos.y < box.min.y + 5`).

- [ ] **Step 4: Документация** — HANDOFF.md п.42 (конвейер, файлы, грабли: «_properties с float — IfcReal ок», «qwen-image-edit не подходит под спеку 3 — выводы зонда», «камера — одноразовый localStorage»), README — строка сценария. Формат — по образцу п.40.

- [ ] **Step 5: Финальный коммит**

```bash
git add HANDOFF.md README.md docs/3d-design-scene-modal.png docs/3d-design-scene-plan.png docs/3d-design-scene-view.png
git commit -m "docs(3d): 3D Design — сценарий «Сцена» и фиксы фасада: HANDOFF п.42, README, скриншоты" -- HANDOFF.md README.md docs/3d-design-scene-modal.png docs/3d-design-scene-plan.png docs/3d-design-scene-view.png
```

---

## Самопроверка плана (выполнена при написании)

- Спека покрыта: A1 (Task 2), A2 (Task 1), A3 (Task 2), A4 (Task 3+4), B1 (Task 9), B2 (Task 5), B3 (Task 5), B4 (Task 6), B5 (Task 7), B6 (Task 10), B7 (Task 8), B8 (все задачи), приёмка (Task 4 + 11).
- Именование едино: `validate_scene`/`build_scene`/`SYSTEM_SCENE`/`SCENARIOS`/`camHint`/`applyCamHint`/`CONCEPTUAL_*`.
- Живая генерация — ровно одна (Task 11, smoke).
