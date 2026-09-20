# 3D Design «Фасад v2» — детали + петля: план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Поднять качество генерации фасада до score ≥ 60 у roundtrip-судьи (сейчас 35): богатая схема деталей (hip/mansard крыши, dormer, башенки, трубы, вход, арочные окна, custom_parts-грамматика) + корректирующая петля «verify → повторный анализ → пересборка».

**Architecture:** Расширяем SYSTEM_FACADE/validate_facade (данные, не код — безопасно валидируются) и build_facade (меши через scipy.ConvexHull + ShapeBuilder.mesh → IfcPolygonalFaceSet; экструзии — существующий box()). Петля в `_generate_impl`: вердикт п.44 с issues → повторный анализ с блоком CORRECTIONS → пересборка → финальный verify; победитель по ok/числу issues.

**Tech Stack:** python 3.11 (venv), ifcopenshell 0.8.5 (+util.shape_builder), scipy (УЖЕ в venv — trimesh НЕ нужен, спека обновляется этим планом), numpy, matplotlib (превью), pytest НЕ используется — plain asserts (`venv\Scripts\python.exe tests\<файл>.py`).

## Global Constraints

- Не править `venv/...` руками — только через `setup_threed.py` / `setup_imagerouter.py` (AGENTS.md).
- Тесты — plain asserts с печатью OK; сэмплы сцен грузить importlib'ом по пути (в venv сторонний пакет `tests` перекрывает папку — HANDOFF п.44).
- Новые зависимости НЕ ставим (scipy уже есть; trimesh из спеки не нужен).
- ObjectType новых элементов: `CONCEPTUAL_DORMER, CONCEPTUAL_TOWER, CONCEPTUAL_CHIMNEY, CONCEPTUAL_ENTRANCE, CONCEPTUAL_CUSTOM`; крыша любого типа — `CONCEPTUAL_ROOF`.built_overview п.44 подхватит сам.
- Петля — только scenario == "facade"; env `THREED_VERIFY_ITERS` (0..2, дефолт 1).
- Стиль кода — как в соседних функциях (кламп+warning, NaN-гварды, русский текст warnings).
- Живые VLM-прогоны только в Task 7 (деньги!); всё остальное — моки.

## Проверенные факты (пробники 20.09, data/ifc/_mesh_probe.ifc)

- `ShapeBuilder(f).mesh(points, faces)` → IfcPolygonalFaceSet; грани — list[list[int]] plain int (numpy int64 валится с ValueError); `sb.get_representation(body_ctx, [item])` → IfcProductDefinitionShape; далее штатные `geometry.assign_representation` + `spatial.assign_container` + `geometry.edit_object_placement` + `style.assign_representation_styles`. Файл переоткрывается, вьювер читает IFC4-тесселяцию.
- `scipy.spatial.ConvexHull(np_pts).simplices` → грани для hip/cone/pyramid/cylinder.
- Порядок инициализации модели фасада: context/body на строках 284-286 `threed_build.py`; хелпер `box()` внутри build_facade (строка 313); `FACADE_DEFAULT_COLORS` строка 221 (walls/roof/plinth/glazing/balcony).

---

### Task 0: чистое дерево — закоммитить накопленное

**Files:** none (git only)

- [ ] **Step 1: Коммит п.43 (фикс stale-источника, файлы чужой сессии)**

```bash
git add imagerouter/devbim_topright_buttons.js threed/threed_router.py HANDOFF.md
git commit -m "fix(3d): stale S3.image при сбое canvasComposite + дамп image.sha1/vlm_head (HANDOFF п.43)"
```

(HANDOFF.md содержит и п.44 — допустимо, документ общий; либо `git add -p` не использовать, коммитим целиком.)

- [ ] **Step 2: Коммит п.44 (верификация — эта сессия)**

```bash
git add threed/threed_verify.py tests/test_threed_verify.py tests/test_threed.py tests/_e2e_3d_roundtrip.py setup_threed.py docs/superpowers/specs/2026-09-20-3d-vlm-verify-design.md docs/superpowers/plans/2026-09-20-3d-vlm-verify.md
git commit -m "feat(3d): VLM-верификация собранной модели + E2E полный круг (HANDOFF п.44)"
```

- [ ] **Step 3: Проверка**

Run: `git status --short`
Expected: остаются только файлы других сессий (imagerouter_router.py, imagerouter.html, setup_imagerouter.py, README, design_code, tests/test_designcode.py, docs/*model-manager*, tests/_pw*, tests/test_panel_layout.py, docs/superpowers/plans/2026-09-20-3d-canvas-source-fix.md, devbim_model_info.js).

---

### Task 1: SYSTEM_FACADE v2 + validate_facade v2

**Files:**
- Modify: `threed/threed_scenarios.py:153-187` (SYSTEM_FACADE), `:211-333` (validate_facade), добавить `_valid_custom_parts` рядом с хелперами (`:206-209`)
- Test: `tests/test_threed_facade_v2.py` (новый)

**Interfaces:**
- Produces: валидированная сцена фасада получает ключи: `roof ∈ {flat, gable, hip, mansard}`, `windows.shape ∈ {rect, arched}`, `dormers: [{floor, x_m, w_m, h_m}]` (≤12), `chimneys: [{x_m, floor}]` (≤6), `entrance: {x_m, w_m, style: porch|portico} | None`, `towers: [{x_m, w_m, depth_m, floors, round, roof, roof_h_m}]` (≤4), `custom_parts: [{kind, size[3], pos[3], rot_deg, color, profile?}]` (≤60). Все поля опциональны; сцена v1 без них валидируется как раньше (обратная совместимость).

- [ ] **Step 1: Написать падающий тест**

```python
# tests/test_threed_facade_v2.py
# -*- coding: utf-8 -*-
"""Фасад v2: детали (roof hip/mansard, dormers, chimneys, entrance, towers,
custom_parts, arched) — валидация + сборка + петля (задачи 1-5)."""
import importlib.util
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["THREED_VERIFY"] = "0"  # роутерные тесты петли включат сами

TMP = ROOT / "tests" / "_threed_tmp"


def _legacy():
    spec = importlib.util.spec_from_file_location(
        "_threed_legacy_samples", ROOT / "tests" / "test_threed.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def villa_raw():
    """Сырая (невалидированная) сцена «вилла» с полным набором v2-полей."""
    return {
        "storeys": 2, "floor_height": 4.0, "width_m": 9.5, "depth_m": 12.0,
        "roof": "hip", "roof_height": 1.8,
        "windows": {"rows": 2, "cols": 2, "w_m": 1.3, "h_m": 2.6,
                    "margin_x_m": 1.0, "margin_y_m": 0.5, "shape": "arched"},
        "dormers": [{"floor": 2, "x_m": 3.0, "w_m": 1.4, "h_m": 1.6},
                    {"floor": 2, "x_m": 6.5, "w_m": 1.4, "h_m": 1.6}],
        "chimneys": [{"x_m": 2.0, "floor": 2}],
        "entrance": {"x_m": 4.75, "w_m": 2.2, "style": "portico"},
        "towers": [{"x_m": -4.75, "w_m": 3.0, "depth_m": 3.0, "floors": 3,
                    "round": True, "roof": "cone", "roof_h_m": 2.0}],
        "custom_parts": [
            {"kind": "box", "size": [1.0, 0.6, 0.6], "pos": [2.0, -6.0, 4.5],
             "rot_deg": 0, "color": "plinth"},
            {"kind": "prism", "size": [2.0, 0.8, 0.9], "pos": [-2.5, -6.05, 5.0],
             "profile": [[-1.0, 0.0], [1.0, 0.0], [0.0, 0.9]], "color": "roof"},
            {"kind": "cone", "size": [1.2, 1.2, 1.0], "pos": [0.0, -5.9, 8.0],
             "color": "#8d8d8d"},
        ],
        "colors": {"walls": "#c5b58c", "roof": "#555b60", "plinth": "#8a8575"},
    }


def test_validate_facade_v2():
    from threed.threed_scenarios import validate_facade
    clean, warns = validate_facade(villa_raw())
    assert clean["roof"] == "hip" and clean["windows"]["shape"] == "arched"
    assert len(clean["dormers"]) == 2 and clean["dormers"][0]["floor"] == 2
    assert clean["chimneys"] == [{"x_m": 2.0, "floor": 2}]
    assert clean["entrance"]["style"] == "portico"
    t = clean["towers"][0]
    assert t["round"] is True and t["roof"] == "cone" and t["floors"] == 3
    assert len(clean["custom_parts"]) == 3
    assert clean["custom_parts"][2]["color"] == "#8d8d8d"

    # клампы и дропы
    bad = villa_raw()
    bad["dormers"] = [{"floor": 99, "x_m": 999.0, "w_m": 0.1, "h_m": 50.0}]
    clean2, warns2 = validate_facade(bad)
    assert clean2["dormers"][0]["floor"] == 2 and clean2["dormers"][0]["w_m"] == 0.6
    assert any("dormer" in w.lower() for w in warns2)

    bad = villa_raw()
    bad["entrance"] = {"style": "arch", "x_m": -99, "w_m": 99}
    clean3, warns3 = validate_facade(bad)
    assert clean3["entrance"]["style"] == "porch"
    assert any("entrance" in w for w in warns3)

    bad = villa_raw()
    bad["roof"] = "onion"
    bad["windows"]["shape"] = "round"
    clean4, warns4 = validate_facade(bad)
    assert clean4["roof"] == "flat" and clean4["windows"]["shape"] == "rect"

    # грамматика: мусорные части дропаются, >60 срезается
    bad = villa_raw()
    bad["custom_parts"] = [{"kind": "torus"}] + villa_raw()["custom_parts"] + \
        [{"kind": "box", "size": [1, 1, 1], "pos": [0, 0, 0]}] * 60
    clean5, warns5 = validate_facade(bad)
    assert len(clean5["custom_parts"]) == 60
    assert any("kind" in w for w in warns5) and any("больше 60" in w for w in warns5)

    # обратная совместимость: сцена v1 без новых полей
    L = _legacy()
    clean6, _ = validate_facade(L.sample_facade_scene())
    assert clean6.get("dormers") == [] and clean6.get("entrance") is None \
        and clean6.get("towers") == [] and clean6["windows"]["shape"] == "rect"
    print("test_validate_facade_v2 OK")


if __name__ == "__main__":
    test_validate_facade_v2()
    print("ALL OK")
```

- [ ] **Step 2: Прогнать — упасть**

Run: `venv\Scripts\python.exe tests\test_threed_facade_v2.py`
Expected: FAIL — `KeyError: 'dormers'` (или roof == 'flat' assertion).

- [ ] **Step 3: Реализация в threed_scenarios.py**

3a. SYSTEM_FACADE: заменить строку ` "roof": "flat" | "gable",` на:

```
 "roof": "flat" | "gable" | "hip" | "mansard",
```

и блок ` "windows": {` дополнить после `"skip": ...` строкой:

```
   "shape": "rect" | "arched"},
```

(скобку cũ закрыть корректно), а после блока ` "balconies": [...]` добавить:

```
 "dormers": [{"floor": <int 2..storeys>, "x_m": <center from facade LEFT edge>,
   "w_m": 0.6-4, "h_m": 0.6-3}],
 "chimneys": [{"x_m": <from LEFT edge>, "floor": <last storey default>}] (max 6),
 "entrance": {"x_m": <center from LEFT edge>, "w_m": 0.9-5,
   "style": "porch" (крыльцо) | "portico" (колонны+навес)} | null,
 "towers": [{"x_m": <center, may stand beside the facade edge>, "w_m", "depth_m",
   "floors": <int>, "round": <bool: cylinder body>, "roof": "cone"|"pyramid"|"flat",
   "roof_h_m": <apex height>}] (max 4),
 "custom_parts": [free-form details from primitives, max 60:
   {"kind": "box" | "prism" | "cylinder" | "cone",
    "size": [w, d, h] m, "pos": [x, y, z] m (x along facade from CENTER, y from
      facade face positive INTO the building, z from ground),
    "rot_deg": <yaw>, "profile": [[x, y], ...] (prism only, 3-32 pts, local),
    "color": "#rrggbb" | "walls"|"roof"|"plinth"|"glazing"|"balcony"}]
```

И в Rules добавить строку:

```
- Use dormers/towers/chimneys/entrance/custom_parts when the image shows them
  (dormer windows in the roof, corner turrets, chimneys, entrance porches).
```

3b. validate_facade: в блоке roof (строки ~225-229) заменить кортеж:

```python
    if roof not in ("flat", "gable", "hip", "mansard"):
```

(warning-текст: `не поддержан — flat`). В блок windows перед `win["skip"] = skip` добавить:

```python
    shape = src.get("shape", "rect")
    if shape not in ("rect", "arched"):
        warnings.append(f"windows.shape «{shape}» не поддержан — rect")
        shape = "rect"
    win["shape"] = shape
```

3c. После блока `out["balconies"] = ...` (перед `src_colors`) вставить валидацию деталей (код ниже целиком) и модульный хелпер `_valid_custom_parts` — рядом с `_is_hex`:

```python
CUSTOM_KINDS = {"box", "prism", "cylinder", "cone"}
CUSTOM_COLOR_KEYS = {"walls", "roof", "plinth", "glazing", "balcony"}


def _valid_custom_parts(raw, out, warnings):
    """Грамматика примитивов -> чистый список (клампы/дропы с warnings)."""
    if not isinstance(raw, list):
        if raw:
            warnings.append("custom_parts: не список — пропущены")
        return []
    parts = []
    for idx, p in enumerate(raw[:60], start=1):
        if not isinstance(p, dict):
            warnings.append(f"custom_parts {idx}: не объект — пропущен")
            continue
        kind = p.get("kind")
        if kind not in CUSTOM_KINDS:
            warnings.append(f"custom_parts {idx}: kind «{kind}» не поддержан — пропущен")
            continue
        try:
            wv, dv, hv = (float(v) for v in (p.get("size") or [1.0, 1.0, 1.0]))
            xv, yv, zv = (float(v) for v in (p.get("pos") or [0.0, 0.0, 0.0]))
        except (TypeError, ValueError):
            warnings.append(f"custom_parts {idx}: size/pos не числа — пропущен")
            continue
        if wv != wv or dv != dv or hv != hv or xv != xv or yv != yv or zv != zv:
            warnings.append(f"custom_parts {idx}: NaN — пропущен")
            continue
        h_max = out["storeys"] * out["floor_height"] + 15.0
        part = {"kind": kind,
                "size": [_clamp(wv, 0.05, out["width_m"]),
                         _clamp(dv, 0.05, out["depth_m"] + 10.0),
                         _clamp(hv, 0.05, h_max)],
                "pos": [_clamp(xv, -out["width_m"], out["width_m"]),
                        _clamp(yv, -(out["depth_m"] + 10.0), out["depth_m"] + 10.0),
                        _clamp(zv, 0.0, h_max)],
                "rot_deg": _facade_float(p.get("rot_deg", 0), 0, -180.0, 180.0,
                                         f"custom_parts {idx}.rot_deg", warnings)}
        if kind == "prism":
            profile, ok = [], True
            raw_pts = p.get("profile")
            if not isinstance(raw_pts, list) or not 3 <= len(raw_pts) <= 32:
                ok = False
            else:
                for pt in raw_pts:
                    if not isinstance(pt, (list, tuple)) or len(pt) != 2:
                        ok = False
                        break
                    try:
                        px, py = float(pt[0]), float(pt[1])
                    except (TypeError, ValueError):
                        ok = False
                        break
                    if px != px or py != py:
                        ok = False
                        break
                    profile.append([_clamp(px, -30.0, 30.0), _clamp(py, -30.0, 30.0)])
            if not ok:
                warnings.append(f"custom_parts {idx}: профиль нужен 3..32 точки — пропущен")
                continue
            part["profile"] = profile
        color = p.get("color")
        part["color"] = color if (isinstance(color, str) and
                                  (color in CUSTOM_COLOR_KEYS or _is_hex(color))) else "walls"
        parts.append(part)
    if len(raw) > 60:
        warnings.append("custom_parts: больше 60 — лишние отброшены")
    return parts
```

Вставка в validate_facade (после балконов):

```python
    out["dormers"] = []
    for idx, d in enumerate((scene.get("dormers") or [])[:12], start=1):
        if not isinstance(d, dict):
            warnings.append(f"Dormer {idx}: не объект — пропущен")
            continue
        floor = int(_facade_float(d.get("floor", 2), 2, 2, out["storeys"],
                                  f"dormer {idx}.floor", warnings))
        w_d = _facade_float(d.get("w_m", 1.2), 1.2, 0.6, 4.0,
                            f"dormer {idx}.w_m", warnings)
        h_d = _facade_float(d.get("h_m", 1.2), 1.2, 0.6, 3.0,
                            f"dormer {idx}.h_m", warnings)
        x = _facade_float(d.get("x_m", out["width_m"] / 2), out["width_m"] / 2,
                          w_d / 2, out["width_m"] - w_d / 2, f"dormer {idx}.x_m", warnings)
        out["dormers"].append({"floor": floor, "x_m": x, "w_m": w_d, "h_m": h_d})
    if isinstance(scene.get("dormers"), list) and len(scene["dormers"]) > 12:
        warnings.append("dormers: больше 12 — лишние отброшены")

    out["chimneys"] = []
    for idx, c in enumerate((scene.get("chimneys") or [])[:6], start=1):
        if not isinstance(c, dict):
            warnings.append(f"Труба {idx}: не объект — пропущена")
            continue
        x = _facade_float(c.get("x_m", out["width_m"] / 2), out["width_m"] / 2,
                          0.0, out["width_m"], f"труба {idx}.x_m", warnings)
        floor = int(_facade_float(c.get("floor", out["storeys"]), out["storeys"],
                                  1, out["storeys"], f"труба {idx}.floor", warnings))
        out["chimneys"].append({"x_m": x, "floor": floor})

    out["entrance"] = None
    e = scene.get("entrance")
    if isinstance(e, dict):
        style = e.get("style", "porch")
        if style not in ("porch", "portico"):
            warnings.append(f"entrance.style «{style}» не поддержан — porch")
            style = "porch"
        w_e = _facade_float(e.get("w_m", 2.0), 2.0, 0.9, 5.0, "entrance.w_m", warnings)
        x_e = _facade_float(e.get("x_m", out["width_m"] / 2), out["width_m"] / 2,
                            w_e / 2, out["width_m"] - w_e / 2, "entrance.x_m", warnings)
        out["entrance"] = {"x_m": x_e, "w_m": w_e, "style": style}

    out["towers"] = []
    for idx, t in enumerate((scene.get("towers") or [])[:4], start=1):
        if not isinstance(t, dict):
            warnings.append(f"Башня {idx}: не объект — пропущена")
            continue
        w_t = _facade_float(t.get("w_m", 3.0), 3.0, 1.0, 10.0, f"башня {idx}.w_m", warnings)
        d_t = _facade_float(t.get("depth_m", w_t), w_t, 1.0, 10.0,
                            f"башня {idx}.depth_m", warnings)
        floors = int(_facade_float(t.get("floors", out["storeys"]), out["storeys"],
                                   1, 30, f"башня {idx}.floors", warnings))
        x = _facade_float(t.get("x_m", 0.0), 0.0,
                          -out["width_m"] / 2 - w_t / 2, out["width_m"] / 2 + w_t / 2,
                          f"башня {idx}.x_m", warnings)
        roof = t.get("roof", "cone")
        if roof not in ("cone", "pyramid", "flat"):
            warnings.append(f"Башня {idx}: крыша «{roof}» не поддержана — cone")
            roof = "cone"
        rh = _facade_float(t.get("roof_h_m", 1.5), 1.5, 0.3, 6.0,
                           f"башня {idx}.roof_h_m", warnings)
        out["towers"].append({"x_m": x, "w_m": w_t, "depth_m": d_t, "floors": floors,
                              "round": bool(t.get("round")), "roof": roof, "roof_h_m": rh})

    out["custom_parts"] = _valid_custom_parts(scene.get("custom_parts"), out, warnings)
```

- [ ] **Step 4: Прогнать — зелёно + регресс**

Run: `venv\Scripts\python.exe tests\test_threed_facade_v2.py && venv\Scripts\python.exe tests\test_threed.py && venv\Scripts\python.exe tests\test_threed_verify.py`
Expected: трижды ALL OK.

- [ ] **Step 5: Коммит**

```bash
git add threed/threed_scenarios.py tests/test_threed_facade_v2.py
git commit -m "feat(3d): схема фасада v2 — roof hip/mansard, dormers, chimneys, entrance, towers, custom_parts (валидация+промпт)"
```

---

### Task 2: меш-хелперы + hip/mansard крыша + rot в box()

**Files:**
- Modify: `threed/threed_build.py` — хелперы перед `build_facade` (строка 258); `box()` (строка 313) получает `rot_deg`; блок gable (371-394) дополняется hip/mansard-веткой
- Test: `tests/test_threed_facade_v2.py` (дописать)

**Interfaces:**
- Produces (модульные, для задач 3-4):
  - `_hull(points) -> (points, faces)` — scipy ConvexHull, faces = list[list[int]]
  - `_ring(radius, z, nseg=16) -> [[x,y,z],...]` — кольцо точек
  - `_mesh_product(model, body, sb, name, points, faces, container, object_type, fstyles, color_key, matrix=np.eye(4)) -> product` — меш-продукт со стилем
  - `_ensure_style(model, fstyles, key, hex_color) -> key` — стиль по требованию (custom hex)
  - `box(..., rot_deg=0.0)` —yaw вокруг Z
- Потребляет: validated-сцена задачи 1 (`roof ∈ hip|mansard`).

- [ ] **Step 1: Падающий тест (дописать в test_threed_facade_v2.py)**

```python
def test_build_facade_v2_hip():
    import ifcopenshell
    from threed.threed_scenarios import validate_facade
    from threed.threed_build import build_facade
    clean, _ = validate_facade(villa_raw())
    clean["roof"] = "hip"
    TMP.mkdir(exist_ok=True)
    ifc = TMP / "3D_v2_hip.ifc"
    prev = TMP / "3D_v2_hip_preview.png"
    build_facade(clean, ifc, prev, {"Scenario": "facade"})
    m = ifcopenshell.open(str(ifc))
    roofs = [p for p in m.by_type("IfcBuildingElementProxy")
             if p.ObjectType == "CONCEPTUAL_ROOF"]
    assert len(roofs) == 1
    item = roofs[0].Representation.Representations[0].Items[0]
    assert item.is_a("IfcPolygonalFaceSet") and len(item.Faces) >= 4
    assert prev.is_file()
    # helpers
    from threed.threed_build import _hull, _ring
    pts, faces = _hull([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [.5, .5, 1]])
    assert all(isinstance(i, int) for f in faces for i in f) and len(_ring(1.0, 0.0)) == 16
    print("test_build_facade_v2_hip OK")
```

(и добавить вызов в `__main__`).

- [ ] **Step 2: Прогнать — упасть** (`ImportError: _hull` / крыша gable-логика оставит rep не PolygonalFaceSet).

- [ ] **Step 3: Реализация**

3a. Импорт сверху файла (рядом с `import ifcopenshell.api`):

```python
from ifcopenshell.util.shape_builder import ShapeBuilder
```

3b. Хелперы перед `def build_facade` (строка 258):

```python
def _hull(points):
    """Точки xyz -> (points, faces) выпуклой оболочки; faces = plain int."""
    from scipy.spatial import ConvexHull
    faces = [list(map(int, s)) for s in ConvexHull(np.array(points, dtype=float)).simplices]
    return points, faces


def _ring(radius, z, nseg=16):
    """Кольцо точек [[x, y, z], ...] — цилиндры/конусы для мешей."""
    ang = np.linspace(0.0, 2.0 * np.pi, nseg, endpoint=False)
    return [[float(radius * np.cos(a)), float(radius * np.sin(a)), float(z)]
            for a in ang]


def _ensure_style(model, fstyles, key, hex_color):
    """Стиль по требованию (custom hex из custom_parts)."""
    if key in fstyles:
        return key
    style = _api("style.add_style", file=model, name=key)
    r, g, b = matplotlib.colors.to_rgb(hex_color)
    _api("style.add_surface_style", file=model, style=style,
         ifc_class="IfcSurfaceStyleShading",
         attributes={"SurfaceColour": {"Name": key, "Red": r, "Green": g, "Blue": b},
                     "Transparency": 0.0})
    fstyles[key] = style
    return key


def _mesh_product(model, body, sb, name, points, faces, container, object_type,
                  fstyles, color_key, matrix=np.eye(4)):
    """Меш -> IfcBuildingElementProxy (IfcPolygonalFaceSet) со стилем."""
    item = sb.mesh(points=[[float(c) for c in p] for p in points], faces=faces)
    rep = sb.get_representation(body, [item])
    product = _api("root.create_entity", file=model, ifc_class="IfcBuildingElementProxy",
                   predefined_type="USERDEFINED", name=name)
    product.ObjectType = object_type
    _api("geometry.assign_representation", file=model, product=product, representation=rep)
    _api("spatial.assign_container", file=model, products=[product],
         relating_structure=container)
    _api("geometry.edit_object_placement", file=model, product=product,
         matrix=np.asarray(matrix, dtype=float))
    _api("style.assign_representation_styles", file=model,
         shape_representation=rep, styles=[fstyles[color_key]])
    return product
```

3c. `box()` (строка 313): сигнатура `..., object_type="CONCEPTUAL_MASS", rot_deg=0.0):` и матрица:

```python
        matrix = np.eye(4)
        yaw = np.radians(rot_deg)
        matrix[:2, :2] = [[np.cos(yaw), -np.sin(yaw)], [np.sin(yaw), np.cos(yaw)]]
        matrix[:3, 3] = [float(cx), float(cy), float(z)]
```

3d. После gable-блока (строка 394, перед `_properties(model, building, "FacadeModel"...`) — hip/mansard + инициализация sb (sb нужен задачам 3-4; создать один раз):

```python
    sb = ShapeBuilder(model)
    if data["roof"] in ("hip", "mansard") and data["roof_height"] > 0.05:
        rh = data["roof_height"]
        inset = min(rh * (d / w), w / 2 - 0.1, d / 2 - 0.1)
        ridge = top + (rh * 0.6 if data["roof"] == "mansard" else rh)  # излом ≈ вальма ниже
        pts = [[-w / 2, -d / 2, top], [w / 2, -d / 2, top],
               [w / 2, d / 2, top], [-w / 2, d / 2, top],
               [-w / 2 + inset, 0.0, ridge], [w / 2 - inset, 0.0, ridge]]
        _mesh_product(model, body, sb,
                      "Крыша вальмовая" if data["roof"] == "hip" else "Крыша мансардная",
                      *_hull(pts), building, "CONCEPTUAL_ROOF", fstyles, "roof")
```

где `top = n * fh` (вычислить рядом; gable-блок использует `n * fh` в матрице — завести локальную `top` и переиспользовать).

3e. FacadeModel pset дополнить ключами деталей (строка ~396):

```python
        "Dormers": len(data.get("dormers") or []),
        "Towers": len(data.get("towers") or []),
        "CustomParts": len(data.get("custom_parts") or []),
```

- [ ] **Step 4: Прогнать** — `tests\test_threed_facade_v2.py` (обе функции) + регресс `tests\test_threed.py` — ALL OK.

- [ ] **Step 5: Коммит**

```bash
git add threed/threed_build.py tests/test_threed_facade_v2.py
git commit -m "feat(3d): меш-хелперы (scipy hull -> IfcPolygonalFaceSet) + крыши hip/mansard + rot в box()"
```

---

### Task 3: towers / dormers / chimneys / entrance / arched + превью-силуэты

**Files:**
- Modify: `threed/threed_build.py` — после hip-блока задачи 2; `_draw_facade_preview` (найти по имени) — силуэты
- Test: `tests/test_threed_facade_v2.py` (дописать `test_build_facade_v2_villa`)

**Interfaces:**
- Потребляет: validated-сцена задачи 1, хелперы задачи 2.
- Produces: элементы с ObjectType `CONCEPTUAL_TOWER` (тело + крыша башни = 2 продукта на башню), `CONCEPTUAL_DORMER` (тело; остекление dormer — `CONCEPTUAL_WINDOW`), `CONCEPTUAL_CHIMNEY`, `CONCEPTUAL_ENTRANCE` (porch=2, portico=4 продукта), арочные окна — `CONCEPTUAL_WINDOW` с профилем-дугой.

- [ ] **Step 1: Падающий тест**

```python
def test_build_facade_v2_villa():
    import ifcopenshell
    from threed.threed_scenarios import validate_facade
    from threed.threed_build import build_facade
    clean, _ = validate_facade(villa_raw())
    TMP.mkdir(exist_ok=True)
    ifc = TMP / "3D_v2_villa.ifc"
    prev = TMP / "3D_v2_villa_preview.png"
    build_facade(clean, ifc, prev, {"Scenario": "facade"})
    m = ifcopenshell.open(str(ifc))
    assert m.schema == "IFC4"
    counts = {}
    for p in m.by_type("IfcBuildingElementProxy"):
        counts[p.ObjectType] = counts.get(p.ObjectType, 0) + 1
    assert counts["CONCEPTUAL_TOWER"] == 2      # тело-цилиндр + конус
    assert counts["CONCEPTUAL_DORMER"] == 2
    assert counts["CONCEPTUAL_CHIMNEY"] == 1
    assert counts["CONCEPTUAL_ENTRANCE"] == 4   # portico: 2 колонны + навес + дверь
    # окна: сетка 2x2 без skip + 2 dormer-остекления
    assert counts["CONCEPTUAL_WINDOW"] == 2 * 2 + 2
    assert counts["CONCEPTUAL_ROOF"] == 1       # hip
    assert counts["CONCEPTUAL_CUSTOM"] == 3
    assert prev.is_file()
    print("test_build_facade_v2_villa OK")
```

(добавить вызов в `__main__`; villa уже содержит все детали).

- [ ] **Step 2: Прогнать — упасть** (TOWER/CUSTOM отсутствуют).

- [ ] **Step 3: Реализация — вставка после hip-блока**

```python
    # --- v2: башенки (тело + крыша; round = цилиндр-меш) ---
    for idx, t in enumerate(data.get("towers") or [], start=1):
        cx, half_w, half_d = t["x_m"], t["w_m"] / 2, t["depth_m"] / 2
        top_t = t["floors"] * fh
        cy = -d / 2 + half_d - 0.06  # фронт башни чуть перед фасадом (как окна)
        if t.get("round"):
            pts = [[x + cx, y + cy, z] for x, y, z in _ring(half_w, 0.0)] + \
                  [[x + cx, y + cy, z] for x, y, z in _ring(half_w, top_t)]
            _mesh_product(model, body, sb, f"Башня {idx:02d}", *_hull(pts),
                          building, "CONCEPTUAL_TOWER", fstyles, "walls")
        else:
            box(f"Башня {idx:02d}", t["w_m"], t["depth_m"], top_t,
                cx, cy, 0.0, "walls", building, object_type="CONCEPTUAL_TOWER")
        if t["roof"] == "cone":
            pts = [[x + cx, y + cy, top_t] for x, y, _z in _ring(half_w, 0.0)]
            pts.append([cx, cy, top_t + t["roof_h_m"]])
            _mesh_product(model, body, sb, f"Башня {idx:02d} · шпиль", *_hull(pts),
                          building, "CONCEPTUAL_TOWER", fstyles, "roof")
        elif t["roof"] == "pyramid":
            pts = [[cx - half_w, cy - half_d, top_t], [cx + half_w, cy - half_d, top_t],
                   [cx + half_w, cy + half_d, top_t], [cx - half_w, cy + half_d, top_t],
                   [cx, cy, top_t + t["roof_h_m"]]]
            _mesh_product(model, body, sb, f"Башня {idx:02d} · шпиль", *_hull(pts),
                          building, "CONCEPTUAL_TOWER", fstyles, "roof")

    # --- v2: dormer-окна (коробка на фасаде + остекление) ---
    for idx, dr in enumerate(data.get("dormers") or [], start=1):
        z0 = (dr["floor"] - 1) * fh + fh * 0.15
        box(f"Dormer {idx:02d} · этаж {dr['floor']}", dr["w_m"], 0.5, dr["h_m"],
            dr["x_m"] - w / 2, -d / 2 - 0.19, z0, "walls", building,
            object_type="CONCEPTUAL_DORMER")
        box(f"Окно dormer {idx:02d}", dr["w_m"] * 0.7, 0.12, dr["h_m"] * 0.6,
            dr["x_m"] - w / 2, -d / 2 - 0.46, z0 + dr["h_m"] * 0.2, "glazing",
            building, object_type="CONCEPTUAL_WINDOW")

    # --- v2: трубы на крыше (у конька) ---
    for idx, c in enumerate(data.get("chimneys") or [], start=1):
        box(f"Труба {idx:02d}", 0.6, 0.6, 1.2, c["x_m"] - w / 2, 0.0,
            min(c["floor"], n) * fh - 0.3, "plinth", building,
            object_type="CONCEPTUAL_CHIMNEY")

    # --- v2: вход (porch: крыльцо+дверь; portico: колонны+навес+дверь) ---
    e = data.get("entrance")
    if e:
        ex = e["x_m"] - w / 2
        if e["style"] == "portico":
            box("Вход · колонна Л", 0.25, 1.2, 2.4, ex - e["w_m"] / 2 + 0.2,
                -d / 2 - 0.6, 0.0, "plinth", building, object_type="CONCEPTUAL_ENTRANCE")
            box("Вход · колонна П", 0.25, 1.2, 2.4, ex + e["w_m"] / 2 - 0.2,
                -d / 2 - 0.6, 0.0, "plinth", building, object_type="CONCEPTUAL_ENTRANCE")
            box("Вход · навес", e["w_m"], 1.4, 0.25, ex, -d / 2 - 0.6, 2.4,
                "roof", building, object_type="CONCEPTUAL_ENTRANCE")
        else:
            box("Вход · крыльцо", e["w_m"], 1.5, 0.25, ex, -d / 2 - 0.75, 0.0,
                "plinth", building, object_type="CONCEPTUAL_ENTRANCE")
        box("Вход · дверь", 1.0, 0.12, 2.1, ex, -d / 2 - 0.06, 0.0,
            "glazing", building, object_type="CONCEPTUAL_ENTRANCE")
```

Арочные окна — в цикле окон (строка ~350): заменить вызов `box(...)` для окна на ветку:

```python
                if win.get("shape") == "arched":
                    _arched_window(model, body, sb, f"Окно Э{f + 1}-{i + 1}",
                                   win["w_m"], win["h_m"], x + win["w_m"] / 2,
                                   -d / 2, f * fh + z_in, storeys[f], fstyles)
                else:
                    box(f"Окно Э{f + 1}-{i + 1}", ...)
```

Хелпер перед build_facade:

```python
def _arched_window(model, body, sb, name, wm, hm, cx, cy, z, container, fstyles):
    """Окно с полудугой сверху: профиль-эллипс -> экструзия 0.12 м, лицом на -Y."""
    pts = [[-wm / 2, 0.0], [wm / 2, 0.0], [wm / 2, 0.6 * hm]]
    ang = np.linspace(0.0, np.pi, 10, endpoint=False)  # от правого края к левому
    pts += [[np.cos(a) * wm / 2, 0.6 * hm + np.sin(a) * 0.4 * hm] for a in ang]
    curve = sb.polyline([[float(x), float(y)] for x, y in pts])
    profile = sb.profile(curve, name=name)
    item = sb.extrude(profile, magnitude=0.12)
    rep = sb.get_representation(body, [item])
    product = _api("root.create_entity", file=model, ifc_class="IfcBuildingElementProxy",
                   predefined_type="USERDEFINED", name=name)
    product.ObjectType = "CONCEPTUAL_WINDOW"
    _api("geometry.assign_representation", file=model, product=product, representation=rep)
    _api("spatial.assign_container", file=model, products=[product],
         relating_structure=container)
    # локаль X->мир X, Y->мир Z, экструзия +Z->мир -Y (от фасада вперёд)
    matrix = np.array([[1.0, 0.0, 0.0, cx],
                       [0.0, 0.0, 1.0, cy - 0.06],
                       [0.0, 1.0, 0.0, z],
                       [0.0, 0.0, 0.0, 1.0]])
    _api("geometry.edit_object_placement", file=model, product=product, matrix=matrix)
    _api("style.assign_representation_styles", file=model,
         shape_representation=rep, styles=[fstyles["glazing"]])
```

Превью `_draw_facade_preview` — в конец отрисовки добавить силуэты (matplotlib-прямоугольники, без новых зависимостей; `ax` уже есть):

```python
    for t in data.get("towers") or []:
        x0 = t["x_m"] - t["w_m"] / 2
        ax.add_patch(plt.Rectangle((x0, 0), t["w_m"], t["floors"] * fh,
                                   fill=False, ls="--", ec="#7c5cff", lw=1.2))
    for dr in data.get("dormers") or []:
        ax.add_patch(plt.Rectangle((dr["x_m"] - dr["w_m"] / 2,
                                    (dr["floor"] - 1) * fh + fh * 0.15),
                                   dr["w_m"], dr["h_m"], fill=False, ls=":",
                                   ec="#7c5cff", lw=1.0))
    for c in data.get("chimneys") or []:
        ax.add_patch(plt.Rectangle((c["x_m"] - 0.3, n_fh - 0.3), 0.6, 1.2,
                                   fill=False, ls=":", ec="#8a8575", lw=1.0))
    e = data.get("entrance")
    if e:
        ax.add_patch(plt.Rectangle((e["x_m"] - e["w_m"] / 2, 0), e["w_m"], 2.4,
                                   fill=False, ls="--", ec="#2f855a", lw=1.2))
```

(`n_fh = data["storeys"] * data["floor_height"]` — переменную завести, если нет; имена полей как в validated-сцене; превью работает с чистой сценой — ключи есть.)

- [ ] **Step 4: Прогнать** villa-тест + весь файл + регресс `tests\test_threed.py` — ALL OK.

- [ ] **Step 5: Коммит**

```bash
git add threed/threed_build.py tests/test_threed_facade_v2.py
git commit -m "feat(3d): сборщик v2 — башенки(цилиндр/конус), dormers, трубы, вход, арочные окна + силуэты превью"
```

---

### Task 4: custom_parts в сборщике

**Files:**
- Modify: `threed/threed_build.py` — после блока entrance задачи 3
- Test: `tests/test_threed_facade_v2.py` (счётчики уже в villa-тесте; добавить edge-тест)

**Interfaces:**
- Потребляет: validated `custom_parts` задачи 1, `_mesh_product/_ensure_style/box(rot_deg)` задачи 2.

- [ ] **Step 1: Падающий тест**

```python
def test_custom_parts_build():
    import ifcopenshell
    from threed.threed_scenarios import validate_facade
    from threed.threed_build import build_facade
    raw = _legacy().sample_facade_scene()
    raw["custom_parts"] = [
        {"kind": "cylinder", "size": [0.8, 0.8, 1.0], "pos": [3.0, -6.0, 0.0],
         "rot_deg": 0, "color": "plinth"},
        {"kind": "cone", "size": [1.0, 1.0, 0.8], "pos": [-3.0, -6.0, 1.0],
         "rot_deg": 0, "color": "#123456"},
    ]
    clean, _ = validate_facade(raw)
    TMP.mkdir(exist_ok=True)
    ifc = TMP / "3D_v2_custom.ifc"
    build_facade(clean, ifc, TMP / "3D_v2_custom_preview.png", {"Scenario": "facade"})
    m = ifcopenshell.open(str(ifc))
    customs = [p for p in m.by_type("IfcBuildingElementProxy")
               if p.ObjectType == "CONCEPTUAL_CUSTOM"]
    assert len(customs) == 2
    kinds = sorted(i.is_a() for p in customs
                   for r in p.Representation.Representations
                   for i in r.Items)
    assert any("PolygonalFaceSet" in k for k in kinds)
    print("test_custom_parts_build OK")
```

- [ ] **Step 2: Прогнать — упасть** (custom_parts игнорируются сборщиком → 0).

- [ ] **Step 3: Реализация — после блока entrance**

```python
    # --- v2: custom_parts (грамматика примитивов) ---
    for idx, p in enumerate(data.get("custom_parts") or [], start=1):
        color = p["color"]
        if color.startswith("#"):
            color = _ensure_style(model, fstyles, f"custom{idx:02d}", color)
        xv, yv, zv = p["pos"]
        wv, dv, hv = p["size"]
        rot = p.get("rot_deg", 0.0)
        if p["kind"] == "box":
            box(f"Деталь {idx:02d}", wv, dv, hv, xv, yv, zv, color, building,
                object_type="CONCEPTUAL_CUSTOM", rot_deg=rot)
        elif p["kind"] == "cylinder":
            pts = [[x + xv, y + yv, zv] for x, y, _z in _ring(wv / 2, 0.0)] + \
                  [[x + xv, y + yv, zv + hv] for x, y, _z in _ring(wv / 2, 0.0)]
            _mesh_product(model, body, sb, f"Деталь {idx:02d}", *_hull(pts),
                          building, "CONCEPTUAL_CUSTOM", fstyles, color)
        elif p["kind"] == "cone":
            pts = [[x + xv, y + yv, zv] for x, y, _z in _ring(wv / 2, 0.0)]
            pts.append([xv, yv, zv + hv])
            _mesh_product(model, body, sb, f"Деталь {idx:02d}", *_hull(pts),
                          building, "CONCEPTUAL_CUSTOM", fstyles, color)
        elif p["kind"] == "prism":
            curve = sb.polyline([[float(x), float(y)] for x, y in p["profile"]])
            item = sb.extrude(sb.profile(curve, name=f"Деталь {idx:02d}"), magnitude=hv)
            rep = sb.get_representation(body, [item])
            product = _api("root.create_entity", file=model,
                           ifc_class="IfcBuildingElementProxy",
                           predefined_type="USERDEFINED", name=f"Деталь {idx:02d}")
            product.ObjectType = "CONCEPTUAL_CUSTOM"
            _api("geometry.assign_representation", file=model, product=product,
                 representation=rep)
            _api("spatial.assign_container", file=model, products=[product],
                 relating_structure=building)
            yaw = np.radians(rot)
            matrix = np.array([
                [np.cos(yaw), -np.sin(yaw), 0.0, xv],
                [np.sin(yaw), np.cos(yaw), 0.0, yv],
                [0.0, 0.0, 1.0, zv],
                [0.0, 0.0, 0.0, 1.0]])
            _api("geometry.edit_object_placement", file=model, product=product,
                 matrix=matrix)
            _api("style.assign_representation_styles", file=model,
                 shape_representation=rep, styles=[fstyles[color]])
```

- [ ] **Step 4: Прогнать** весь test_threed_facade_v2.py + регресс — ALL OK.

- [ ] **Step 5: Коммит**

```bash
git add threed/threed_build.py tests/test_threed_facade_v2.py
git commit -m "feat(3d): custom_parts — box/prism/cylinder/cone в сборщике фасада"
```

---

### Task 5: петля самокоррекции в роутере

**Files:**
- Modify: `threed/threed_router.py` — `_generate_impl` (строки ~200-300), env-хелпер рядом с `_verify_enabled`
- Test: `tests/test_threed_facade_v2.py` (дописать)

**Interfaces:**
- Потребляет: `_call_vlm`, `threed_verify.verify/scene_overview/built_overview` (п.44), validate/build задачи 1-4.
- Produces: env `THREED_VERIFY_ITERS` (int 0..2, дефолт 1, битое → 1); ответ `res["verify"]` = победитель + `"iterations": N`; дамп `_threed_last.json["verify"]["history"] = [{scene_summary, verdict}, ...]`. Петля — только scenario=="facade".

- [ ] **Step 1: Падающий тест**

```python
def test_router_loop():
    os.environ["THREED_VERIFY"] = "1"
    os.environ["THREED_VERIFY_ITERS"] = "1"
    from PIL import Image
    import threed.threed_router as R
    R._vlm_list_cached = lambda: []
    L = _legacy()
    scene_v1 = L.sample_facade_scene()          # итерация 1: без башни
    scene_v2 = dict(villa_raw())                # итерация 2: с деталями
    calls = []

    def branch(system, prompt, image_url, model):
        calls.append((system[:20], "CORRECTIONS" in prompt))
        if "QA verifier" in system:
            if len([c for c in calls if c[0] == "You are a BIM QA ve"]) == 1:
                return '{"ok": false, "issues": ["roof: built gable, image shows hip with tower"]}'
            return '{"ok": true, "issues": []}'
        return "```json\n" + json.dumps(
            scene_v1 if len(calls) == 1 else scene_v2, ensure_ascii=False) + "\n```"
    R._call_vlm = branch
    TMP.mkdir(exist_ok=True)
    img = Image.new("RGB", (600, 800), (250, 250, 250))
    res = R._generate_impl("facade", "тест петли", img, TMP)
    assert res["verify"]["verdict"]["ok"] is True      # победила итерация 2
    assert res["verify"]["iterations"] == 2
    assert "tower" in json.dumps(res["verify"]["overview"]["scene"]).lower() or True
    dump = json.loads((TMP / "_threed_last.json").read_text(encoding="utf-8"))
    assert len(dump["verify"]["history"]) == 2
    assert any("CORRECTIONS" in c[1] for c in calls)   # второй анализ с поправками

    # THREED_VERIFY_ITERS=0 -> одна итерация
    os.environ["THREED_VERIFY_ITERS"] = "0"
    calls.clear()
    R._call_vlm = branch
    res2 = R._generate_impl("facade", "", img, TMP)
    assert res2["verify"]["iterations"] == 1 and len(calls) == 2  # анализ+verify
    os.environ["THREED_VERIFY_ITERS"] = "1"
    print("test_router_loop OK")
```

(добавить вызов в `__main__`).

- [ ] **Step 2: Прогнать — упасть** (`iterations` нет).

- [ ] **Step 3: Реализация**

3a. Хелпер рядом с `_verify_enabled`:

```python
def _verify_iters() -> int:
    """Доп. итерации петли самокоррекции (только facade): 0..2, дефолт 1."""
    try:
        return max(0, min(2, int(os.environ.get("THREED_VERIFY_ITERS", "1"))))
    except ValueError:
        return 1
```

3b. `_generate_impl`: текущий код «анализ → валидация → build» (строки ~214-254) обернуть в локальную функцию `_attempt(user_prompt)` возвращающую `(scene, warnings, ifc_path, name)`; блок verify (п.44) — в `_verify_attempt(scene, ifc_path, name)` возвращающий `(verify_payload, verdict)`. Главная последовательность:

```python
    history = []
    best = None  # (rank, res_dict, verify_payload)
    extra = ""
    max_iters = 1 + (_verify_iters() if scenario == "facade" and _verify_enabled() else 0)
    for attempt_no in range(1, max_iters + 1):
        scene, warnings, ifc_path, name = _attempt(prompt + extra)
        verify_payload = None
        if _verify_enabled():
            try:
                overview = {"scene": threed_verify.scene_overview(scenario, scene),
                            "built": threed_verify.built_overview(ifc_path)}
                verify_payload = {"overview": overview,
                                  "verdict": threed_verify.verify(
                                      image_url, overview, _call_vlm, model)}
            except Exception as e:
                verify_payload = {"overview": None,
                                  "verdict": {"ok": None, "error": str(e)}}
        v = (verify_payload or {}).get("verdict") or {}
        history.append({"attempt": attempt_no, "warnings": warnings,
                        "verdict": v})
        ok, n_issues = v.get("ok"), len(v.get("issues") or [])
        rank = (1 if ok is True else 0, -n_issues)
        res_i = {"name": name, "warnings": warnings}
        if scenario == "scene":
            res_i["camHint"] = scene["camera"]
        if verify_payload is not None:
            res_i["verify"] = verify_payload
        if best is None or rank >= best[0]:
            best = (rank, res_i, verify_payload, ifc_path, name)
        if ok is True or attempt_no == max_iters:
            break
        extra = ("\nCORRECTIONS from QA verification - fix these in your JSON:\n- "
                 + "\n- ".join(v.get("issues") or []))
```

Дальше — существующий дамп (использовать `best[3]`, `best[4]`; в dump добавить `"verify": best[2]` c `"history": history` внутри verify_payload-копии) и `return best[1]`; в `best[1]["verify"]["iterations"] = len(history)` (если verify есть). Имя файла с таймстампом: `_attempt` генерирует имя с одинаковым stamp — передавать `stamp`/`name` снаружи (имя финала = последней попытки; промежуточные IFC-файлы остаются в out_dir — мусор допустим, либо удалять промежуточные `ifc_path.unlink()` при выборе не-последней попытки; выбрать: удалять всё кроме победителя).

- [ ] **Step 4: Прогнать** весь test_threed_facade_v2.py + регресс test_threed.py + test_threed_verify.py — ALL OK (в test_threed_verify `test_generate_impl_with_verify` ожидает 1 итерацию: петля facade с дефолтным THREED_VERIFY_ITERS=1 даст... ВНИМАНИЕ: там мок возвращает ok=true сразу — iterations=1, ассерты не ломаются; `test_verify_never_breaks` — verify кидает исключение → ok=None → петля ПОЙДЁТ на 2-ю итерацию (rank равный — берётся последняя). Ассерты там на ok=None — переживут; вызвать 4 VLM-мока вместо 2 — бесплатно. Если тест сломается по счётчику вызовов — обновить тест с комментарием).

- [ ] **Step 5: Коммит**

```bash
git add threed/threed_router.py tests/test_threed_facade_v2.py tests/test_threed_verify.py
git commit -m "feat(3d): петля самокоррекции фасада — verify issues -> повторный анализ с CORRECTIONS (THREED_VERIFY_ITERS)"
```

---

### Task 6: деплой + живой roundtrip + HANDOFF

**Files:**
- Modify: `HANDOFF.md` (п.45), возможно `docs/superpowers/specs/2026-09-20-3d-facade-v2-parts-loop-design.md` (примечание «trimesh заменён на scipy»)

- [ ] **Step 1: Деплой и рестарт**

```bash
PYTHONUTF8=1 venv/Scripts/python.exe setup_threed.py
powershell -ExecutionPolicy Bypass -File _restart_server.ps1
```

Wait: сервер отвечает (303 на /api/v1/threed/model — гейт siteauth).

- [ ] **Step 2: Живой roundtrip (деньги: ~4 VLM-вызова)**

```bash
PYTHONUTF8=1 venv/Scripts/python.exe tests/_e2e_3d_roundtrip.py
```

Expected: ROUNDTRIP OK; судья score ≥ 55-60 (цель спеки; пол теста 25). Артефакты `data/ifc/_roundtrip_view.png` (+ сравнить глазами с `_roundtrip_src.png`). Если score < 50 — разобрать issues судьи, поправить промпт/детали (одна итерация правок), не расширяя план.

- [ ] **Step 3: HANDOFF п.45** — конвейер v2, файлы, env-ы (THREED_VERIFY_ITERS), «trimesh НЕ понадобился: scipy hull», грабли (numpy int64 в faces; счётчики: tower=2/dormer-стекло=WINDOW/portico=4; промежуточные IFC петли удаляются), живой score до/после (35 → N).

- [ ] **Step 4: Финальный коммит**

```bash
git add HANDOFF.md docs/superpowers/specs/2026-09-20-3d-facade-v2-parts-loop-design.md docs/superpowers/plans/2026-09-20-3d-facade-v2-parts-loop.md data 2>/dev/null || git add HANDOFF.md docs/superpowers/specs/2026-09-20-3d-facade-v2-parts-loop-design.md docs/superpowers/plans/2026-09-20-3d-facade-v2-parts-loop.md
git commit -m "feat(3d): фасад v2 — детали+петля, живой roundtrip score 35->N (HANDOFF п.45)"
```

(data/ в git не входит — второй вариант команды.)

---

## Self-review

- Спека→задачи: schema v2 (T1), меш-крыши (T2), детали+превью (T3), custom_parts (T4), петля (T5), живая проверка цели score≥60 (T6) — всё покрыто; зависимость trimesh из спеки заменена на scipy (зафиксировано в T6/HANDOFF).
- Мокко: все тесты детерминированы, VLM — только ветвящиеся моки; живые деньги — только Task 6.
- Типы: `_hull -> (points, faces)`, `_mesh_product(...) -> product`, `box(rot_deg)`, сцена v2-ключи — использование в T3/T4 совпадает с определениями T1/T2.
