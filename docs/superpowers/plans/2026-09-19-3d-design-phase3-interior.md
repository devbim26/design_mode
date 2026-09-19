# 3D Design — фаза 3 «Интерьер»: план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Сценарий «Интерьер» в 3D Design: 2D-план квартиры → VLM-сцена → IFC4
(плита, стены-сегменты, проёмы, IfcSpace-комнаты с именами, IfcFurnishingElement-
мебель) + чертёж-превью в метрах; плитка «Интерьер» в модалке активна.

**Architecture:** Те же три слоя, что в фазах 1–2: `threed_scenarios.py`
(SYSTEM_INTERIOR + validate_interior; ЕДИНОЕ ПРАВИЛО КООРДИНАТ — позиции в
ПИКСЕЛЯХ, размеры/высоты в МЕТРАХ), `threed_build.py` (build_interior +
_draw_interior_preview), `threed_router.py` (ветвление scenario=="interior"),
виджет `imagerouter/devbim_topright_buttons.js` (плитка + placeholder).
Деплой — существующий setup_threed.py (идемпотентен, менять не нужно).

**Tech Stack:** ifcopenshell 0.8.5 (`_api`/`_properties` паттерны фаз 1–2),
shapely (контур/центроид), matplotlib Agg (превью), numpy (матрицы поворота),
PIL (подготовка картинки на сервере), plain asserts-тесты.

## Global Constraints

- Не править `venv/.../site-packages` руками — только через `setup_threed.py`
  (после правок `threed/*` запускать его ПЕРЕД тестами роутера: тесты
  импортируют venv-копии модулей).
- Тесты: plain asserts + `print OK` (НЕ pytest). Запуск:
  `PYTHONUTF8=1 ./venv/Scripts/python.exe tests/test_threed.py`.
- IFC4; координаты: пиксели → метры через `metres_per_trace_pixel`,
  Y-флип `(trace_height − y) * scale` (y=0 — верх картинки); Z — вверх.
- Концепт-прокси: ObjectType `CONCEPTUAL_*`; реальные классы по спеке:
  IfcSlab (пол), IfcWall (стены), IfcSpace (комнаты, имена с плана!),
  IfcFurnishingElement (мебель, ObjectType `FURNITURE_<TYPE>`).
- УРОК ФАЗЫ 2: элементы НЕ рисовать заподлицо с другими гранями —
  проёмы делаются СКВОЗЬ стену с выступом 0.03 м с каждой стороны
  (толщина проёма = толщина стены + 0.06), иначе невидимы в рендере.
- Не коммитить: `.env`, `companies*`, ключи; в индексе может лежать чужой
  WIP (design_code/*, model-manager) — коммитить ТОЛЬКО через явный pathspec,
  никогда `git add -A` / `git add .` / `-a`.
- Сервер перезапускать только `_restart_server.ps1`; порт открывается
  25–80 с — поллить, не ждать фикс. 40 с.
- Живые VLM-генерации ~$0.05–0.15 каждая: на фазу — РОВНО ОДНА живая
  генерация интерьера (smoke в Task 5 ИЛИ E2E в Task 6; выбрать одно место).
- RU/EN тексты виджета: чистые кавычки в TEXTS, экранирование
  (`replace(/"/g,'&quot;')`) ТОЛЬКО в точке интерполяции innerHTML.

## Спека (источник: docs/superpowers/specs/2026-09-18-3d-design-ifc-generation-design.md, раздел «Сценарий „Интерьер“»)

Схема сцены: `metres_per_trace_pixel` (опоры: дверной проём 0,9–1 м, кровать
2×1,6 м, унитаз 0,4 м; размерная линия точнее), `wall_height` (дефолт 2,7),
`outline [[x,y],…]`, `walls [{points_px, thickness_m, exterior}]`,
`openings [{wall_idx|"outline", x_px (вдоль стены), width_m, height_m,
sill_m, kind: door|window}]`, `rooms [{name, type, points_px}]`,
`furniture [{type: bed|sofa|table|chair|wardrobe|kitchen|bath|toilet|sink|
lamp|other, x_px, y_px, w_m, d_m, h_m, rot_deg}]`. Пользовательский цикл
после сборки (человек, вид от глаз, снимок, референсы) уже работает —
НЕ входит в фазу.

## File Structure

- `threed/threed_build.py` — добавить: `ASSUMPTION_INTERIOR`,
  `INTERIOR_DEFAULT_COLORS`, `FURNITURE_RU`, `_rot_z`, `_px_to_m`,
  `build_interior`, `_draw_interior_preview` (одна ответственность:
  сборка IFC интерьера + чертёж-превью; рядом с build_facade).
- `threed/threed_scenarios.py` — добавить: `SYSTEM_INTERIOR`,
  `ROOM_TYPES`, `FURNITURE_TYPES`, `validate_interior` (валидация+дефолты).
- `threed/threed_router.py` — `SCENARIOS += "interior"`, ветвление
  промпт/валидатор/сборщик (3 ветки вместо 2).
- `imagerouter/devbim_topright_buttons.js` — плитка «Интерьер» активна,
  `promptPhInterior` RU/EN, выбор placeholder по 3 сценариям, убрать `soon3d`.
- `tests/test_threed.py` — `test_build_interior`, `test_validate_interior`,
  `test_generate_impl_interior`, дополнить `test_widget_3d_modal`.
- `HANDOFF.md` (СЛЕДУЮЩИЙ свободный номер — проверить по файлу на момент
  исполнения; чужая параллельная сессия занимает п.39, ожидается п.40),
  `README.md`, спека-статус.
- E2E-скрипты и синтетика — `.superpowers/sdd/` (в git НЕ входят);
  скриншоты — `docs/3d-design-interior-{modal,result}.png`.

---

### Task 1: Сборщик build_interior + чертёж-превью

**Files:**
- Modify: `threed/threed_build.py` (добавить блок после `_draw_facade_preview`)
- Test: `tests/test_threed.py` (добавить `test_build_interior` + `sample_interior_scene`)

**Interfaces:**
- Consumes: `_api`, `_properties`, `_write_header` (уже в файле);
  паттерн `box()` из build_facade НЕ переиспользуется напрямую (нужен
  поворот) — пишем свой `rbox` внутри `build_interior`.
- Produces: `build_interior(scene: dict, ifc_path: Path, preview_path: Path,
  meta: dict) -> Path` — scene = вывод `validate_interior` (Task 2):
  `{"trace_width", "trace_height", "metres_per_trace_pixel", "wall_height",
  "outline": [[x,y],…], "walls": [{"points_px", "thickness_m", "exterior"}],
  "openings": [{"wall_idx"|"outline", "x_px", "width_m", "height_m",
  "sill_m", "kind"}], "rooms": [{"name", "type", "points_px"}],
  "furniture": [{"type", "x_px", "y_px", "w_m", "d_m", "h_m", "rot_deg"}]}`.
  Вызывается роутером в Task 3 как
  `threed_build.build_interior(scene, ifc_path, preview_path, meta)`
  (БЕЗ аргумента-картинки, как build_facade).

- [ ] **Step 1: Тест-фикстура и падающий тест**

В `tests/test_threed.py` после `sample_facade_scene()`:

```python
def sample_interior_scene():
    """Интерьер: прямоугольник 40×30 px-контур (scale 0.25 м/px -> 10×7.5 м),
    внутренняя стена с дверью, окно на контуре, 2 комнаты, кровать 90°."""
    return {
        "trace_width": 40, "trace_height": 30, "metres_per_trace_pixel": 0.25,
        "wall_height": 2.7,
        "outline": [[2, 2], [38, 2], [38, 28], [2, 28]],
        "walls": [
            {"points_px": [[2, 2], [38, 2]], "thickness_m": 0.4, "exterior": True},
            {"points_px": [[38, 2], [38, 28]], "thickness_m": 0.4, "exterior": True},
            {"points_px": [[38, 28], [2, 28]], "thickness_m": 0.4, "exterior": True},
            {"points_px": [[2, 28], [2, 2]], "thickness_m": 0.4, "exterior": True},
            {"points_px": [[20, 2], [20, 28]], "thickness_m": 0.15, "exterior": False},
        ],
        "openings": [
            {"wall_idx": 0, "x_px": 6, "width_m": 0.9, "height_m": 2.1,
             "sill_m": 0.0, "kind": "door"},
            {"wall_idx": 1, "x_px": 12, "width_m": 1.4, "height_m": 1.5,
             "sill_m": 0.9, "kind": "window"},
            {"wall_idx": "outline", "x_px": 4, "width_m": 0.9, "height_m": 2.1,
             "sill_m": 0.0, "kind": "door"},
        ],
        "rooms": [
            {"name": "Кухня", "type": "kitchen",
             "points_px": [[2, 2], [20, 2], [20, 28], [2, 28]]},
            {"name": "Спальня", "type": "bedroom",
             "points_px": [[20, 2], [38, 2], [38, 28], [20, 28]]},
        ],
        "furniture": [
            {"type": "bed", "x_px": 10, "y_px": 20, "w_m": 2.0, "d_m": 1.6,
             "h_m": 0.5, "rot_deg": 90},
            {"type": "table", "x_px": 29, "y_px": 20, "w_m": 1.2, "d_m": 0.8,
             "h_m": 0.75, "rot_deg": 0},
        ],
    }


def test_build_interior():
    import ifcopenshell
    from ifcopenshell.util.element import get_psets
    from ifcopenshell.util.placement import get_local_placement
    from threed.threed_build import build_interior

    TMP.mkdir(exist_ok=True)
    ifc = TMP / "3D_interior_test.ifc"
    prev = TMP / "3D_interior_test_preview.png"
    path = build_interior(sample_interior_scene(), ifc, prev,
                          {"Scenario": "interior", "Prompt": "тест",
                           "Model": "test/model", "Source": "3D Design"})
    assert path == ifc and ifc.is_file() and prev.is_file()

    m = ifcopenshell.open(str(ifc))
    assert m.schema == "IFC4"
    gids = [r.GlobalId for r in m.by_type("IfcRoot")]
    assert len(gids) == len(set(gids)), "GlobalId не уникальны"
    assert len(m.by_type("IfcSlab")) == 1                    # плита пола
    assert len(m.by_type("IfcWall")) == 5                    # 5 сегментов
    assert len(m.by_type("IfcSpace")) == 2                   # комнаты
    space_names = sorted(s.Name for s in m.by_type("IfcSpace"))
    assert space_names == ["Кухня", "Спальня"]               # имена с плана
    # все IfcSpace в одном сторе
    assert len(m.by_type("IfcBuildingStorey")) == 1
    proxies = [p for p in m.by_type("IfcBuildingElementProxy")]
    kinds = {}
    for p in proxies:
        kinds[p.ObjectType] = kinds.get(p.ObjectType, 0) + 1
    assert kinds.get("CONCEPTUAL_DOOR") == 2                 # 2 двери
    assert kinds.get("CONCEPTUAL_WINDOW") == 1               # окно
    furn = m.by_type("IfcFurnishingElement")
    assert len(furn) == 2
    ftypes = sorted(f.ObjectType for f in furn)
    assert ftypes == ["FURNITURE_BED", "FURNITURE_TABLE"]
    # кровать повёрнута на 90° (в сборке Rz(-90) из-за Y-флипа):
    # mat = [[0,1,0],[-1,0,0],…] -> mat[0,0]≈0, mat[1,0]≈-1
    bed = [f for f in furn if f.ObjectType == "FURNITURE_BED"][0]
    mat = get_local_placement(bed.ObjectPlacement)
    assert abs(mat[0, 0] - 0.0) < 1e-6 and abs(mat[1, 0] - (-1.0)) < 1e-6, \
        "кровать должна быть повёрнута Rz(-90)"
    # pset DevBIM у проекта + InteriorModel у здания
    assert get_psets(m.by_type("IfcProject")[0]).get("DevBIM", {}).get("Scenario") \
        == "interior"
    fm = get_psets(m.by_type("IfcBuilding")[0]).get("InteriorModel", {})
    assert fm.get("WallHeight") == 2.7 and fm.get("Rooms") == 2 \
        and fm.get("Furniture") == 2
    print("test_build_interior OK")
```

- [ ] **Step 2: Запустить тест — должен упасть**

```bash
PYTHONUTF8=1 ./venv/Scripts/python.exe -c "import tests.test_threed as t; t.test_build_interior()"
```
Ожидание: `ImportError: cannot import name 'build_interior'`.

- [ ] **Step 3: Реализация — добавить в threed/threed_build.py (в конец файла)**

```python
# ===================== Фаза 3: сценарий «Интерьер» =====================

ASSUMPTION_INTERIOR = (
    "Концептуальная модель квартиры по растровому плану (3D Design). Стены, проёмы "
    "и мебель — оценочные блоки по обводке плана; размеры по опорным объектам или "
    "размерным линиям. Не использовать как обмерную или рабочую документацию."
)

INTERIOR_DEFAULT_COLORS = {
    "slab": "#d9d4c8", "wall": "#c8b89a", "opening": "#202830", "room": "#e6ecf2",
    "bed": "#8fa3bf", "sofa": "#7f9b8e", "table": "#c9a227", "chair": "#d4ac9e",
    "wardrobe": "#a58d6f", "kitchen": "#9aa3ad", "bath": "#bfd8e6",
    "toilet": "#e0e4e8", "sink": "#d6e0e8", "lamp": "#f0d68a", "other": "#b8bcc2",
}

FURNITURE_RU = {
    "bed": "Кровать", "sofa": "Диван", "table": "Стол", "chair": "Стул",
    "wardrobe": "Шкаф", "kitchen": "Кухня", "bath": "Ванна", "toilet": "Унитаз",
    "sink": "Раковина", "lamp": "Лампа", "other": "Предмет",
}


def _rot_z(deg):
    a = np.radians(float(deg))
    c, s = np.cos(a), np.sin(a)
    return np.array([[c, -s, 0.0, 0.0], [s, c, 0.0, 0.0],
                     [0.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.0, 1.0]])


def _px_to_m(data, x, y):
    """Пиксели картинки -> метры плана (Y-флип: y=0 — верх картинки)."""
    s = data["metres_per_trace_pixel"]
    return float(x) * s, (data["trace_height"] - float(y)) * s


def _outline_point_at(data, dist_px):
    """Точка на контуре outline на расстоянии dist_px вдоль периметра от 1-й
    точки + направление сегмента (градусы). None = контура нет."""
    pts_m = [_px_to_m(data, x, y) for x, y in data["outline"]]
    segs = []
    total = 0.0
    for i in range(len(pts_m)):
        a, b = pts_m[i], pts_m[(i + 1) % len(pts_m)]
        ln = float(np.hypot(b[0] - a[0], b[1] - a[1])) / data["metres_per_trace_pixel"]
        segs.append((a, b, ln))  # ln в пикселях исходника
        total += ln
    t = max(0.0, min(float(dist_px), total))
    acc = 0.0
    for a, b, ln in segs:
        if ln <= 0:
            continue
        if acc + ln >= t or (a, b, ln) is segs[-1]:
            frac = (t - acc) / ln
            x = a[0] + (b[0] - a[0]) * frac
            y = a[1] + (b[1] - a[1]) * frac
            ang = np.degrees(np.arctan2(b[1] - a[1], b[0] - a[0]))
            return x, y, ang, ln
        acc += ln
    return None


def build_interior(scene, ifc_path, preview_path, meta):
    """Сцена интерьера (validate_interior) -> IFC4 + чертёж-превью."""
    data = dict(scene)
    colors = dict(INTERIOR_DEFAULT_COLORS)
    data["colors"] = colors  # сборщик не красит по VLM-цветам — палитра типов
    scale = data["metres_per_trace_pixel"]
    wh = data["wall_height"]

    model = _api("project.create_file", version="IFC4")
    project = _api("root.create_entity", file=model, ifc_class="IfcProject",
                   name=data.get("project_name", "3D Design — интерьер"))
    project.Description = ASSUMPTION_INTERIOR
    units = [_api("unit.add_si_unit", file=model, unit_type=t)
             for t in ("LENGTHUNIT", "AREAUNIT", "VOLUMEUNIT")]
    _api("unit.assign_unit", file=model, units=units)
    context = _api("context.add_context", file=model, context_type="Model")
    body = _api("context.add_context", file=model, context_type="Model",
                context_identifier="Body", target_view="MODEL_VIEW", parent=context)
    site = _api("root.create_entity", file=model, ifc_class="IfcSite", name="Участок")
    _api("aggregate.assign_object", file=model, products=[site], relating_object=project)
    _api("geometry.edit_object_placement", file=model, product=site, matrix=np.eye(4))
    building = _api("root.create_entity", file=model, ifc_class="IfcBuilding",
                    name=data.get("building_name", "Квартира по плану"))
    building.Description = ASSUMPTION_INTERIOR
    _api("aggregate.assign_object", file=model, products=[building],
         relating_object=site)
    _api("geometry.edit_object_placement", file=model, product=building, matrix=np.eye(4))
    storey = _api("root.create_entity", file=model, ifc_class="IfcBuildingStorey",
                  name="Этаж 01")
    storey.Elevation = 0.0
    _api("aggregate.assign_object", file=model, products=[storey], relating_object=building)
    _api("geometry.edit_object_placement", file=model, product=storey, matrix=np.eye(4))
    _properties(model, project, "DevBIM", {
        "Source": meta.get("Source", "3D Design"), "Scenario": "interior",
        "Prompt": (meta.get("Prompt") or "")[:1024], "Model": meta.get("Model", ""),
        "ApproximateGeometry": True, "Notes": ASSUMPTION_INTERIOR,
    })
    fstyles = {}
    for key, color in colors.items():
        r, g, b = matplotlib.colors.to_rgb(color)
        style = _api("style.add_style", file=model, name=f"Interior{key.capitalize()}")
        _api("style.add_surface_style", file=model, style=style,
             ifc_class="IfcSurfaceStyleShading",
             attributes={"SurfaceColour": {"Name": key, "Red": r, "Green": g, "Blue": b},
                         "Transparency": 0.0})
        fstyles[key] = style

    def rbox(name, bw, bd, bh, cx, cy, z, rot_deg, color_key, container,
             ifc_class, object_type, predefined=None):
        """Прямоугольный блок с поворотом вокруг Z: профиль bw×bd, выдавливание
        bh вверх от z. rot_deg — против часовой в метрах плана."""
        kwargs = dict(file=model, ifc_class=ifc_class, name=name)
        if predefined is not None:
            kwargs["predefined_type"] = predefined
        product = _api("root.create_entity", **kwargs)
        if object_type is not None:
            product.ObjectType = object_type
        pts = [[-bw / 2, -bd / 2], [bw / 2, -bd / 2], [bw / 2, bd / 2], [-bw / 2, bd / 2]]
        profile = _api("profile.add_arbitrary_profile", file=model, profile=pts, name=name)
        representation = _api("geometry.add_profile_representation", file=model,
                              context=body, profile=profile, depth=bh, cardinal_point=None)
        _api("geometry.assign_representation", file=model, product=product,
             representation=representation)
        _api("spatial.assign_container", file=model, products=[product],
             relating_structure=container)
        matrix = _rot_z(rot_deg)
        matrix[0, 3], matrix[1, 3], matrix[2, 3] = float(cx), float(cy), float(z)
        _api("geometry.edit_object_placement", file=model, product=product, matrix=matrix)
        _api("style.assign_representation_styles", file=model,
             shape_representation=representation, styles=[fstyles[color_key]])
        return product

    def poly(name, points_px, depth, z, color_key, container, ifc_class,
             object_type, predefined=None):
        """Полигон px -> профиль относительно центроида, выдавливание depth от z."""
        kwargs = dict(file=model, ifc_class=ifc_class, name=name)
        if predefined is not None:
            kwargs["predefined_type"] = predefined
        product = _api("root.create_entity", **kwargs)
        if object_type is not None:
            product.ObjectType = object_type
        pts_m = [_px_to_m(data, x, y) for x, y in points_px]
        polygon = orient(Polygon(pts_m), sign=1.0)
        if not polygon.is_valid or polygon.area <= 0:
            raise ValueError(f"Некорректный контур: {name}")
        xy = np.array(polygon.exterior.coords, dtype=float)
        origin = np.array(polygon.centroid.coords[0])
        profile = _api("profile.add_arbitrary_profile", file=model,
                       profile=(xy - origin).tolist(), name=name)
        representation = _api("geometry.add_profile_representation", file=model,
                              context=body, profile=profile, depth=depth,
                              cardinal_point=None)
        _api("geometry.assign_representation", file=model, product=product,
             representation=representation)
        _api("spatial.assign_container", file=model, products=[product],
             relating_structure=container)
        matrix = np.eye(4)
        matrix[:3, 3] = [float(origin[0]), float(origin[1]), float(z)]
        _api("geometry.edit_object_placement", file=model, product=product, matrix=matrix)
        _api("style.assign_representation_styles", file=model,
             shape_representation=representation, styles=[fstyles[color_key]])
        return product

    # --- плита пола: outline, толщина 0.1 м, верх на z=0
    if data["outline"]:
        poly("Пол", data["outline"], 0.1, -0.1, "slab", storey,
             "IfcSlab", "CONCEPTUAL_FLOOR", predefined="FLOOR")

    # --- стены: сегменты -> повёрнутые боксы
    wall_geo = []  # (p1_m, p2_m, length_m, angle_deg) для проёмов
    for idx, wall in enumerate(data["walls"], start=1):
        p1 = _px_to_m(data, *wall["points_px"][0])
        p2 = _px_to_m(data, *wall["points_px"][1])
        dx, dy = p2[0] - p1[0], p2[1] - p1[1]
        length = float(np.hypot(dx, dy))
        wall_geo.append((p1, p2, length))
        if length < 0.05:
            continue
        ang = np.degrees(np.arctan2(dy, dx))
        ext = " нар." if wall.get("exterior") else ""
        rbox(f"Стена {idx:02d}{ext}", length, wall["thickness_m"], wh,
             (p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2, 0.0, ang,
             "wall", storey, "IfcWall", "CONCEPTUAL_WALL", predefined="USERDEFINED")

    # --- проёмы: сквозь стену с выступом 0.03 м (урок фазы 2: заподлицо
    #     совпадающие грани не рендерятся и не кликаются)
    n_doors = n_windows = 0
    for op in data["openings"]:
        widx = op["wall_idx"]
        if widx == "outline":
            hit = _outline_point_at(data, op["x_px"]) if data["outline"] else None
            if hit is None:
                continue
            cx, cy, ang, len_px = hit
            thickness = 0.4
        else:
            p1, p2, length = wall_geo[widx]
            if length < 0.05:  # вырожденный сегмент (пропущен стеной)
                continue
            thickness = data["walls"][widx]["thickness_m"]
            t = max(0.0, min(op["x_px"] * scale, length))
            ux, uy = (p2[0] - p1[0]) / length, (p2[1] - p1[1]) / length
            cx, cy = p1[0] + ux * t, p1[1] + uy * t
            ang = np.degrees(np.arctan2(p2[1] - p1[1], p2[0] - p1[0]))
        if op["kind"] == "door":
            n_doors += 1
            name, otype = f"Дверь {n_doors}", "CONCEPTUAL_DOOR"
        else:
            n_windows += 1
            name, otype = f"Окно {n_windows}", "CONCEPTUAL_WINDOW"
        rbox(name, op["width_m"], thickness + 0.06, op["height_m"], cx, cy,
             op["sill_m"], ang, "opening", storey,
             "IfcBuildingElementProxy", otype, predefined="USERDEFINED")

    # --- комнаты: IfcSpace с именами с плана + pset Room
    for room in data["rooms"]:
        space = poly(room["name"], room["points_px"], 0.02, 0.005, "room",
                     storey, "IfcSpace", "CONCEPTUAL_ROOM", predefined="SPACE")
        _properties(model, space, "Room", {"Type": room.get("type", "other")})

    # --- мебель: IfcFurnishingElement, цвет/имя по типу, поворот
    for idx, item in enumerate(data["furniture"], start=1):
        cx, cy = _px_to_m(data, item["x_px"], item["y_px"])
        ftype = item["type"] if item["type"] in FURNITURE_RU else "other"
        rbox(f"{FURNITURE_RU[ftype]} {idx:02d}", item["w_m"], item["d_m"],
             item["h_m"], cx, cy, 0.0, -item["rot_deg"],  # Y-флип инвертирует угол
             ftype, storey, "IfcFurnishingElement", f"FURNITURE_{ftype.upper()}")

    _properties(model, building, "InteriorModel", {
        "WallHeight": wh, "ScaleMPerPx": scale,
        "Walls": len(data["walls"]), "Openings": len(data["openings"]),
        "Rooms": len(data["rooms"]), "Furniture": len(data["furniture"]),
        "ApproximateGeometry": True, "Notes": ASSUMPTION_INTERIOR,
    })

    _write_header(model, ifc_path)
    ifc_path.parent.mkdir(parents=True, exist_ok=True)
    model.write(str(ifc_path))
    _draw_interior_preview(data, preview_path)
    return ifc_path


def _draw_interior_preview(data, preview_path):
    """Чертёж плана в метрах: контур, стены, проёмы, подписи комнат, мебель."""
    scale = data["metres_per_trace_pixel"]
    wh = data["wall_height"]

    def rect_corners(cx, cy, bw, bd, deg):
        a = np.radians(deg)
        c, s = np.cos(a), np.sin(a)
        loc = [(-bw / 2, -bd / 2), (bw / 2, -bd / 2), (bw / 2, bd / 2), (-bw / 2, bd / 2)]
        return [(cx + x * c - y * s, cy + x * s + y * c) for x, y in loc]

    fig, ax = plt.subplots(figsize=(12, 8), facecolor="white")
    if data["outline"]:
        pts = [_px_to_m(data, x, y) for x, y in data["outline"]]
        ax.add_patch(PlotPolygon(pts + [pts[0]], facecolor="#efece5",
                                 edgecolor="#263747", linewidth=1.0))
    for idx, wall in enumerate(data["walls"], start=1):
        p1 = _px_to_m(data, *wall["points_px"][0])
        p2 = _px_to_m(data, *wall["points_px"][1])
        length = float(np.hypot(p2[0] - p1[0], p2[1] - p1[1]))
        if length < 0.05:
            continue
        ang = np.degrees(np.arctan2(p2[1] - p1[1], p2[0] - p1[0]))
        t = wall["thickness_m"]
        ax.add_patch(PlotPolygon(rect_corners((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2,
                                              length, t, ang),
                                 facecolor=data["colors"]["wall"], edgecolor="#263747",
                                 linewidth=0.8))
    for op in data["openings"]:
        widx = op["wall_idx"]
        if widx == "outline":
            hit = _outline_point_at(data, op["x_px"]) if data["outline"] else None
            if hit is None:
                continue
            cx, cy, ang, _ = hit
            thickness = 0.4
        else:
            if not (isinstance(widx, int) and 0 <= widx < len(data["walls"])):
                continue
            p1, p2, length = (_px_to_m(data, *data["walls"][widx]["points_px"][0]),
                              _px_to_m(data, *data["walls"][widx]["points_px"][1]), 0.0)
            length = float(np.hypot(p2[0] - p1[0], p2[1] - p1[1]))
            if length < 0.05:
                continue
            thickness = data["walls"][widx]["thickness_m"]
            t = max(0.0, min(op["x_px"] * scale, length))
            ux, uy = ((p2[0] - p1[0]) / length, (p2[1] - p1[1]) / length) if length else (0, 0)
            cx, cy = p1[0] + ux * t, p1[1] + uy * t
            ang = np.degrees(np.arctan2(p2[1] - p1[1], p2[0] - p1[0]))
        ax.add_patch(PlotPolygon(rect_corners(cx, cy, op["width_m"], thickness + 0.06, ang),
                                 facecolor=data["colors"]["opening"], edgecolor="white",
                                 linewidth=0.6))
    for room in data["rooms"]:
        pts = [_px_to_m(data, x, y) for x, y in room["points_px"]]
        centroid = Polygon(pts).centroid
        ax.text(centroid.x, centroid.y, room["name"], ha="center", va="center",
                fontsize=10, color="#15232e")
    for item in data["furniture"]:
        cx, cy = _px_to_m(data, item["x_px"], item["y_px"])
        ftype = item["type"] if item["type"] in FURNITURE_RU else "other"
        ax.add_patch(PlotPolygon(rect_corners(cx, cy, item["w_m"], item["d_m"],
                                              -item["rot_deg"]),
                                 facecolor=data["colors"][ftype], edgecolor="#263747",
                                 linewidth=0.7, alpha=.9))
        ax.text(cx, cy, FURNITURE_RU[ftype][:1], ha="center", va="center",
                fontsize=7, color="#15232e")
    xs, ys = [], []
    for x, y in (data["outline"] or []):
        mx, my = _px_to_m(data, x, y)
        xs.append(mx); ys.append(my)
    for w in data["walls"]:
        for x, y in w["points_px"]:
            mx, my = _px_to_m(data, x, y)
            xs.append(mx); ys.append(my)
    if xs:
        pad = 0.5
        ax.set_xlim(min(xs) - pad, max(xs) + pad)
        ax.set_ylim(min(ys) - pad, max(ys) + pad)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title(f"3D Design — интерьер: стены {wh:g} м, масштаб {scale:g} м/px",
                 fontsize=13)
    fig.tight_layout()
    preview_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(preview_path, dpi=160, facecolor="white")
    plt.close(fig)
```

Примечания к коду (исполнителю): `_rot_z`, `_px_to_m`, `_outline_point_at`
— модульные (используются и превью). `orient`/`Polygon` уже импортированы
вверху файла. IfcFurnishingElement создаётся БЕЗ predefined_type (в IFC4 у
него нет PredefinedType). Отрицательный угол мебели (`-item["rot_deg"]`) —
Y-флип картинки инвертирует направление вращения.

- [ ] **Step 4: Прогнать тест**

```bash
PYTHONUTF8=1 ./venv/Scripts/python.exe -c "import tests.test_threed as t; t.test_build_interior()"
```
Ожидание: `test_build_interior OK`.

- [ ] **Step 5: Полный прогон (тесты импортируют venv-копии — сперва деплой)**

```bash
PYTHONUTF8=1 ./venv/Scripts/python.exe setup_threed.py
PYTHONUTF8=1 ./venv/Scripts/python.exe tests/test_threed.py
```
Ожидание: все строки `OK` + `ALL OK` (пока 13 функций).

- [ ] **Step 6: Коммит**

```bash
git add -- threed/threed_build.py tests/test_threed.py
git commit -m "feat(3d): сборщик IFC4 интерьера (плита, стены-сегменты с поворотом, проёмы сквозь стену, IfcSpace-комнаты с именами, IfcFurnishingElement-мебель) + чертёж-превью" -- threed/threed_build.py tests/test_threed.py
```

---

### Task 2: SYSTEM_INTERIOR + validate_interior

**Files:**
- Modify: `threed/threed_scenarios.py` (блок «Фаза 3» в конец)
- Test: `tests/test_threed.py` (`test_validate_interior`)

**Interfaces:**
- Consumes: `extract_json` (существует), `_clamp`, `_valid_points`
  (существуют), паттерн `_facade_float` (обобщаем в `_num`).
- Produces: `SYSTEM_INTERIOR: str`;
  `validate_interior(scene: dict, img_w: int, img_h: int) -> (dict, warnings)`;
  `ROOM_TYPES`, `FURNITURE_TYPES` (множества; FURNITURE_RU в threed_build
  использует те же ключи). Выход — точно схема из Interfaces Task 1.

- [ ] **Step 1: Падающий тест**

В `tests/test_threed.py`:

```python
def test_validate_interior():
    from threed.threed_scenarios import validate_interior, SYSTEM_INTERIOR
    assert "furniture" in SYSTEM_INTERIOR and "wall_height" in SYSTEM_INTERIOR

    scene = sample_interior_scene()
    out, warn = validate_interior(scene, 40, 30)
    assert out["trace_width"] == 40 and out["trace_height"] == 30
    assert out["wall_height"] == 2.7 and len(out["walls"]) == 5
    assert len(out["openings"]) == 3 and out["openings"][0]["kind"] == "door"
    assert [r["name"] for r in out["rooms"]] == ["Кухня", "Спальня"]
    assert out["furniture"][0]["type"] == "bed"
    assert warn == []

    # не-dict / пустая сцена -> ValueError
    for bad in (None, [], {}, {"rooms": []}):
        try:
            validate_interior(bad, 100, 100)
            raise AssertionError("ожидалась ошибка для " + repr(bad))
        except ValueError:
            pass

    # дефолты: масштаб/высота/толщина; мусорные поля выбрасываются
    out2, warn2 = validate_interior({"outline": [[0, 0], [99, 0], [99, 99], [0, 99]],
                                     "walls": [
                                         {"points_px": [[0, 0], [99, 0]],
                                          "thickness_m": "мусор", "exterior": True},
                                         {"points_px": [[0, 0]], "thickness_m": 0.1},
                                         {"points_px": [[0, 0], [1, 0]],
                                          "thickness_m": 99.0}],
                                     "openings": [
                                         {"wall_idx": 7, "x_px": 5, "width_m": 1.0,
                                          "height_m": 2.0, "sill_m": 0, "kind": "door"},
                                         {"wall_idx": 0, "x_px": 50, "width_m": 1.0,
                                          "height_m": 2.0, "sill_m": 0, "kind": "window"}],
                                     "rooms": [{"name": 123, "type": "sauna",
                                                "points_px": [[1, 1], [9, 1], [9, 9], [1, 9]]}],
                                     "furniture": [
                                         {"type": "spaceship", "x_px": 5, "y_px": 5,
                                          "w_m": 2.0, "d_m": 2.0, "h_m": 1.0,
                                          "rot_deg": 900}]},
                                    100, 100)
    assert abs(out2["metres_per_trace_pixel"] - 0.01) < 1e-9   # дефолт
    assert out2["wall_height"] == 2.7
    assert len(out2["walls"]) == 2                              # нулевая длина выброшена
    assert out2["walls"][0]["thickness_m"] == 0.15              # мусор -> дефолт
    assert out2["walls"][1]["thickness_m"] == 0.6               # кламп сверху
    assert len(out2["openings"]) == 1                           # wall_idx 7 выброшен
    assert out2["rooms"][0]["name"] == "Комната 1"              # не-строка -> дефолт
    assert out2["rooms"][0]["type"] == "other"                  # sauna -> other
    assert out2["furniture"][0]["type"] == "other"              # spaceship -> other
    assert out2["furniture"][0]["rot_deg"] == 180.0             # кламп 900 -> 180
    assert any("walls" in w for w in warn2) or warn2
    print("test_validate_interior OK")
```

- [ ] **Step 2: Запуск — должен упасть**

```bash
PYTHONUTF8=1 ./venv/Scripts/python.exe -c "import tests.test_threed as t; t.test_validate_interior()"
```
Ожидание: `ImportError: cannot import name 'validate_interior'`.

- [ ] **Step 3: Реализация — в конец threed/threed_scenarios.py**

```python
# ===================== Фаза 3: сценарий «Интерьер» =====================

SYSTEM_INTERIOR = """You are a BIM interior analyst. Look at the attached 2D FLOOR PLAN
(apartment / room drawing, PDF page fragment or screenshot; NOT a photo of a finished
interior). Trace the plan into a parametric model. Reply with STRICT JSON ONLY - no
markdown fences, no comments, no extra keys.

Schema (positions in PIXELS of the image, sizes/heights in METERS):
{
 "metres_per_trace_pixel": <float: meters per image pixel. Estimate from anchors:
   door opening 0.9-1 m, bed 2.0 x 1.6 m, toilet 0.4 m, or printed dimension lines
   (they are exact). Typical flat plan ~0.005-0.02.>,
 "wall_height": <float m, floor-to-ceiling, default 2.7>,
 "outline": [[x, y], ...outer boundary pixels, y=0 at the TOP of the image],
 "walls": [
   {"points_px": [[x1, y1], [x2, y2]], "thickness_m": <float m, interior 0.1-0.2,
     exterior 0.3-0.5>, "exterior": <bool>}
 ],
 "openings": [
   {"wall_idx": <int index into walls> | "outline", "x_px": <position ALONG the wall
     from its first point, image pixels>, "width_m": 0.9, "height_m": 2.1,
     "sill_m": <0.0 for doors, ~0.9 for windows>, "kind": "door" | "window"}
 ],
 "rooms": [
   {"name": "<label read from the plan, e.g. Kitchen; Room N if unlabeled>",
    "type": "living|bedroom|kitchen|bath|wc|hall|wardrobe|balcony|other",
    "points_px": [[x, y], ...]}
 ],
 "furniture": [
   {"type": "bed|sofa|table|chair|wardrobe|kitchen|bath|toilet|sink|lamp|other",
    "x_px": <center x>, "y_px": <center y>, "w_m": <width>, "d_m": <depth>,
    "h_m": <height>, "rot_deg": <rotation around center, 0 = as drawn>}
 ]
}

Rules:
- y=0 is the TOP of the image; pixel coordinates only for positions/along-wall
  distances; all sizes, heights and thicknesses are meters.
- List every wall segment with its drawn thickness; exterior walls form the outline.
- Rooms MUST use the label text read on the plan when present.
- Furniture: one entry per item, placed as drawn (position + rotation).
- The USER PROMPT overrides your guesses (scale, wall height) wherever it states them.
"""

ROOM_TYPES = {"living", "bedroom", "kitchen", "bath", "wc", "hall",
              "wardrobe", "balcony", "other"}
FURNITURE_TYPES = {"bed", "sofa", "table", "chair", "wardrobe", "kitchen",
                   "bath", "toilet", "sink", "lamp", "other"}
INTERIOR_SCALE_DEFAULT = 0.01
INTERIOR_SCALE_MIN, INTERIOR_SCALE_MAX = 0.001, 0.1


def _num(value, default, lo, hi, field, warnings):
    """float с NaN-гвардом и клампом (паттерн _facade_float, обобщено)."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        warnings.append(f"{field}: неверное значение — дефолт {default}")
        return default
    if v != v:  # NaN
        warnings.append(f"{field}: NaN — дефолт {default}")
        return default
    if v < lo or v > hi:
        clamped = max(lo, min(hi, v))
        warnings.append(f"{field}: {v:g} вне [{lo}, {hi}] — кламп до {clamped:g}")
        return clamped
    return v


def _px_point(value, w, h):
    """Одна точка [x, y] -> [x, y] клампнутая | None."""
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    try:
        x, y = float(value[0]), float(value[1])
    except (TypeError, ValueError):
        return None
    if x != x or y != y:
        return None
    return [_clamp(x, 0, w), _clamp(y, 0, h)]


def validate_interior(scene, img_w, img_h):
    """Сцена интерьера от VLM -> (чистая сцена, warnings). ValueError — не план."""
    if not isinstance(scene, dict):
        raise ValueError("Сцена не является JSON-объектом")
    warnings = []
    out = {"trace_width": int(img_w), "trace_height": int(img_h),
           "metres_per_trace_pixel": INTERIOR_SCALE_DEFAULT, "wall_height": 2.7,
           "outline": [], "walls": [], "openings": [], "rooms": [], "furniture": []}
    scale = _num(scene.get("metres_per_trace_pixel"), INTERIOR_SCALE_DEFAULT,
                 INTERIOR_SCALE_MIN, INTERIOR_SCALE_MAX, "metres_per_trace_pixel",
                 warnings)
    out["metres_per_trace_pixel"] = scale
    out["wall_height"] = _num(scene.get("wall_height"), 2.7, 2.0, 4.0,
                              "wall_height", warnings)
    if not (scene.get("outline") or scene.get("walls")):
        raise ValueError("Не удалось распознать план помещения")

    outline = _valid_points(scene.get("outline"), img_w, img_h)
    if outline is None:
        warnings.append("outline: битый контур — стены по segments")
    else:
        out["outline"] = outline

    raw_walls = scene.get("walls")
    if not isinstance(raw_walls, list):
        warnings.append("walls: не список — пропущены")
        raw_walls = []
    for idx, wall in enumerate(raw_walls, start=1):
        if not isinstance(wall, dict):
            warnings.append(f"Стена {idx}: не объект — пропущена")
            continue
        pts = wall.get("points_px")
        if not isinstance(pts, list) or len(pts) != 2:
            warnings.append(f"Стена {idx}: нужен ровно 2 точки — пропущена")
            continue
        p1 = _px_point(pts[0], img_w, img_h)
        p2 = _px_point(pts[1], img_w, img_h)
        if p1 is None or p2 is None:
            warnings.append(f"Стена {idx}: битые координаты — пропущена")
            continue
        if abs(p2[0] - p1[0]) + abs(p2[1] - p1[1]) < 1.0:
            warnings.append(f"Стена {idx}: нулевая длина — пропущена")
            continue
        out["walls"].append({
            "points_px": [p1, p2],
            "thickness_m": _num(wall.get("thickness_m", 0.15), 0.15, 0.05, 0.6,
                                f"Стена {idx}.thickness_m", warnings),
            "exterior": bool(wall.get("exterior")),
        })

    raw_ops = scene.get("openings")
    if not isinstance(raw_ops, list):
        if raw_ops:
            warnings.append("openings: не список — пропущены")
        raw_ops = []
    for idx, op in enumerate(raw_ops, start=1):
        if not isinstance(op, dict):
            warnings.append(f"Проём {idx}: не объект — пропущен")
            continue
        widx = op.get("wall_idx")
        if widx != "outline" and not (isinstance(widx, int) and 0 <= widx < len(out["walls"])):
            warnings.append(f"Проём {idx}: wall_idx {widx} не указывает на стену — пропущен")
            continue
        if widx == "outline" and not out["outline"]:
            warnings.append(f"Проём {idx}: нет outline — пропущен")
            continue
        kind = op.get("kind")
        if kind not in ("door", "window"):
            warnings.append(f"Проём {idx}: kind {kind} не поддержан — пропущен")
            continue
        h_default = 2.1 if kind == "door" else 1.5
        out["openings"].append({
            "wall_idx": widx,
            "x_px": _num(op.get("x_px", 0), 0, 0, 100000, f"Проём {idx}.x_px", warnings),
            "width_m": _num(op.get("width_m", 0.9), 0.9, 0.4, 4.0,
                            f"Проём {idx}.width_m", warnings),
            "height_m": _num(op.get("height_m", h_default), h_default, 0.5, 3.0,
                             f"Проём {idx}.height_m", warnings),
            "sill_m": _num(op.get("sill_m", 0.0 if kind == "door" else 0.9),
                           0.0, 0.0, 2.0, f"Проём {idx}.sill_m", warnings),
            "kind": kind,
        })

    raw_rooms = scene.get("rooms")
    if not isinstance(raw_rooms, list):
        if raw_rooms:
            warnings.append("rooms: не список — пропущены")
        raw_rooms = []
    for idx, room in enumerate(raw_rooms, start=1):
        if not isinstance(room, dict):
            warnings.append(f"Комната {idx}: не объект — пропущена")
            continue
        points = _valid_points(room.get("points_px"), img_w, img_h)
        if points is None:
            warnings.append(f"Комната {idx}: битый контур — пропущена")
            continue
        name = room.get("name")
        name = str(name).strip()[:24] if isinstance(name, str) and name.strip() \
            else f"Комната {idx}"
        rtype = room.get("type")
        if rtype not in ROOM_TYPES:
            warnings.append(f"Комната {name}: тип {rtype} не поддержан — other")
            rtype = "other"
        out["rooms"].append({"name": name, "type": rtype, "points_px": points})

    raw_furn = scene.get("furniture")
    if not isinstance(raw_furn, list):
        if raw_furn:
            warnings.append("furniture: не список — пропущены")
        raw_furn = []
    for idx, item in enumerate(raw_furn, start=1):
        if not isinstance(item, dict):
            warnings.append(f"Мебель {idx}: не объект — пропущена")
            continue
        p = _px_point([item.get("x_px"), item.get("y_px")], img_w, img_h)
        if p is None:
            warnings.append(f"Мебель {idx}: битая позиция — пропущена")
            continue
        ftype = item.get("type")
        if ftype not in FURNITURE_TYPES:
            warnings.append(f"Мебель {idx}: тип {ftype} не поддержан — other")
            ftype = "other"
        out["furniture"].append({
            "type": ftype, "x_px": p[0], "y_px": p[1],
            "w_m": _num(item.get("w_m", 0.6), 0.6, 0.1, 6.0,
                        f"Мебель {idx}.w_m", warnings),
            "d_m": _num(item.get("d_m", 0.6), 0.6, 0.1, 6.0,
                        f"Мебель {idx}.d_m", warnings),
            "h_m": _num(item.get("h_m", 0.5), 0.5, 0.05, 3.0,
                        f"Мебель {idx}.h_m", warnings),
            "rot_deg": _num(item.get("rot_deg", 0), 0, -180.0, 180.0,
                            f"Мебель {idx}.rot_deg", warnings),
        })

    if not out["walls"] and not out["rooms"] and not out["furniture"]:
        raise ValueError("На картинке не найдено объектов для 3D-модели")
    return out, warnings
```

- [ ] **Step 4: Прогнать тест (деплой не нужен — прямой импорт)**

```bash
PYTHONUTF8=1 ./venv/Scripts/python.exe -c "import tests.test_threed as t; t.test_validate_interior()"
```
Ожидание: `test_validate_interior OK`. Если ассерт `warn == []` на чистой
сцене падает — валидатор что-то чинит в валидных данных: это баг валидатора,
не теста.

- [ ] **Step 5: Полный прогон + коммит**

```bash
PYTHONUTF8=1 ./venv/Scripts/python.exe setup_threed.py
PYTHONUTF8=1 ./venv/Scripts/python.exe tests/test_threed.py
git add -- threed/threed_scenarios.py tests/test_threed.py
git commit -m "feat(3d): промпт и валидация сценария интерьер (план квартиры: пиксели+метры, клампы, типы комнат/мебели, имена комнат с плана)" -- threed/threed_scenarios.py tests/test_threed.py
```

---

### Task 3: Роутер — сценарий interior

**Files:**
- Modify: `threed/threed_router.py`
- Test: `tests/test_threed.py` (`test_generate_impl_interior`)

**Interfaces:**
- Consumes: `SYSTEM_INTERIOR`, `validate_interior` (Task 2);
  `build_interior` (Task 1); существующие `_call_vlm`, `_load_model_choice`,
  `_validate_model_in_list`.
- Produces: `SCENARIOS = {"plan", "facade", "interior"}`;
  `_generate_impl("interior", …)` возвращает `{"name": "3D_interior_<stamp>.ifc",
  "warnings": [...]}`. Виджет (Task 4) шлёт scenario="interior".

- [ ] **Step 1: Падающий тест**

В `tests/test_threed.py` (рядом с `test_generate_impl_facade`):

```python
def test_generate_impl_interior(monkeypatch=None):
    """Роутер: сценарий interior (мок VLM) -> 3D_interior_*.ifc."""
    import threed.threed_router as R
    R._vlm_list_cached = lambda: []  # каталог не запрашиваем: тесты без сети
    scene = sample_interior_scene()
    R._call_vlm = _mock_vlm_ok("```json\n" + json.dumps(scene, ensure_ascii=False) + "\n```")
    TMP.mkdir(exist_ok=True)
    from PIL import Image
    img = Image.new("RGB", (40, 30), (250, 250, 248))
    res = R._generate_impl("interior", "тест", img, TMP)
    assert res["name"].startswith("3D_interior_") and res["name"].endswith(".ifc")
    assert (TMP / res["name"]).is_file()
    assert (TMP / (Path(res["name"]).stem + "_preview.png")).is_file()
    assert res["warnings"] == []
    # docstring/ошибка для неизвестного сценария больше не называет интерьер
    # «в разработке»
    try:
        R._generate_impl("attic", "", img, TMP)
        raise AssertionError("ожидалась ошибка")
    except ValueError as e:
        assert "plan, facade, interior" in str(e)
    print("test_generate_impl_interior OK")
```

- [ ] **Step 2: Запуск — должен упасть**

```bash
PYTHONUTF8=1 ./venv/Scripts/python.exe -c "import tests.test_threed as t; t.test_generate_impl_interior()"
```
Ожидание: `ValueError: Сценарий «interior» в разработке`.

- [ ] **Step 3: Правки threed/threed_router.py (4 места)**

1) Константа (строка с `SCENARIOS = {"plan", "facade"}`):

```python
SCENARIOS = {"plan", "facade", "interior"}
```

2) Гейт-ошибка в `_generate_impl`:

```python
        raise ValueError(f"Сценарий «{scenario}» в разработке (доступны: plan, facade, interior)")
```

3) Выбор system-промпта в retry-петле (заменить ветку if/else на цепочку):

```python
        system = (threed_scenarios.SYSTEM_INTERIOR if scenario == "interior"
                  else threed_scenarios.SYSTEM_FACADE if scenario == "facade"
                  else threed_scenarios.SYSTEM_GENPLAN)
```

4) Валидация+сборка (заменить оба ветвления):

```python
    if scenario == "interior":
        scene, warnings = threed_scenarios.validate_interior(
            scene, image.width, image.height)
    elif scenario == "facade":
        scene, warnings = threed_scenarios.validate_facade(scene)
    else:
        scene, warnings = threed_scenarios.validate_genplan(
            scene, image.width, image.height)
```

и

```python
    if scenario == "interior":
        threed_build.build_interior(scene, ifc_path, preview_path, meta)
    elif scenario == "facade":
        threed_build.build_facade(scene, ifc_path, preview_path, meta)
    else:
        threed_build.build_genplan(scene, image, ifc_path, preview_path, meta)
```

Также обновить docstring роутера: `{scenario: plan|facade|interior, …}`.

- [ ] **Step 4: Деплой + тесты**

```bash
PYTHONUTF8=1 ./venv/Scripts/python.exe setup_threed.py
PYTHONUTF8=1 ./venv/Scripts/python.exe tests/test_threed.py
```
Ожидание: `test_generate_impl_interior OK`, `ALL OK`.

- [ ] **Step 5: Коммит**

```bash
git add -- threed/threed_router.py tests/test_threed.py
git commit -m "feat(3d): роутер принимает сценарий interior (промпт/валидатор/сборщик)" -- threed/threed_router.py tests/test_threed.py
```

---

### Task 4: Виджет — плитка «Интерьер» активна + placeholder

**Files:**
- Modify: `imagerouter/devbim_topright_buttons.js`
- Test: `tests/test_threed.py` (`test_widget_3d_modal` — дополнить)

**Interfaces:**
- Consumes: TEXTS-паттерн, `t()`, плитки `data-s`, `#devbim-3d-prompt`
  (все существуют).
- Produces: POST `/api/v1/threed/generate` с `scenario: "interior"`
  (штатный run3D уже читает `S3.scenario` с плитки — меняется только разметка
  плиток и placeholder).

- [ ] **Step 1: Дополнить тест-ассерты в test_widget_3d_modal**

В `test_widget_3d_modal` после существующих ассертов добавить:

```python
    # фаза 3: плитка интерьера активна, placeholder по 3 сценариям
    assert '<button class="devbim-3d-tile" data-s="interior"><span>🛋</span>' in src
    assert 'data-s="interior" disabled' not in src
    assert "promptPhInterior" in src and "soon3d" not in src
    # RU/EN тексты placeholder-ов интерьера
    assert "promptPhInterior: 'Уточнения:" in src
    # переключение placeholder-а через карту сценариев
    assert "var ph = {plan: t().promptPhPlan" in src
```

- [ ] **Step 2: Запуск — упадёт на новом ассерте**

```bash
PYTHONUTF8=1 ./venv/Scripts/python.exe -c "import tests.test_threed as t; t.test_widget_3d_modal()"
```
Ожидание: AssertionError про `data-s="interior"`.

- [ ] **Step 3: Правки devbim_topright_buttons.js**

1) TEXTS.ru — удалить строку `soon3d: …`, после `promptPhFacade:` добавить:

```javascript
      promptPhInterior: 'Уточнения: «высота стен 2.8, масштаб 0.01 м/px, стены по чертежу»',
```

TEXTS.en — удалить `soon3d: …`, добавить:

```javascript
      promptPhInterior: 'Hints: "wall height 2.8, scale 0.01 m/px, walls as drawn"',
```

2) Плитка интерьера (заменить строку с `data-s="interior" disabled …`):

```javascript
      '<button class="devbim-3d-tile" data-s="interior"><span>🛋</span>' + t().interior + '</button>' +
```

3) Обработчик плиток — переключение placeholder по карте сценариев
(заменить существующее `var ta = … ? t().promptPhFacade : t().promptPhPlan;`):

```javascript
      var ta = document.getElementById('devbim-3d-prompt');
      if (ta) {
        var ph = {plan: t().promptPhPlan, facade: t().promptPhFacade,
                  interior: t().promptPhInterior};
        ta.placeholder = ph[b.getAttribute('data-s')] || t().promptPhPlan;
      }
```

4) Шапка-комментарий файла: заменить упоминание заглушки интерьера на
«сценарии: генплан, фасад, интерьер — все активны (фазы 1–3)».

- [ ] **Step 4: Проверки + полный прогон**

```bash
node --check imagerouter/devbim_topright_buttons.js
PYTHONUTF8=1 ./venv/Scripts/python.exe setup_imagerouter.py
PYTHONUTF8=1 ./venv/Scripts/python.exe tests/test_threed.py
```
Ожидание: тишина от node, «Роутер развернут…»/«уже развернут» от сетапа
(виджет деплоится setup_imagerouter.py), `ALL OK`.

- [ ] **Step 5: Коммит**

```bash
git add -- imagerouter/devbim_topright_buttons.js tests/test_threed.py
git commit -m "feat(3d): плитка «Интерьер» активна + placeholder промта по 3 сценариям (RU/EN)" -- imagerouter/devbim_topright_buttons.js tests/test_threed.py
```

---

### Task 5: Деплой + рестарт + живой smoke

**Files:** — (без коммитов; артефакты в data/ifc/)

- [ ] **Step 1: Синтетический план квартиры** `.superpowers/sdd/e2e_plan.png`
(PIL, 800×600, белый фон): наружный прямоугольник стен (толстые линии),
внутренняя стена, разрыв-дверь, тёмный прямоугольник окна, подписи
«КУХНЯ»/«СПАЛЬНЯ» (PIL ImageFont default), кровать/стол прямоугольниками.
Образец — генератор `.superpowers/sdd/e2e_facade.png` из фазы 2.

- [ ] **Step 2: Деплой + рестарт**

```bash
PYTHONUTF8=1 ./venv/Scripts/python.exe setup_threed.py
powershell -ExecutionPolicy Bypass -File _restart_server.ps1
# поллить порт до 200 на /auth/login (25-80 с)
```

- [ ] **Step 3: ЖИВОЙ smoke (единственная живая генерация фазы)**

Login-cookie + POST (образец — smoke фазы 2): body
`{"scenario": "interior", "prompt": "высота стен 2.7, дверь на кухню, окно в спальне",
"image": "data:image/png;base64,…"}` → ожидание 200, ответ
`{"name": "3D_interior_<stamp>.ifc", "warnings": [...]}`;
проверить файлы `data/ifc/3D_interior_*.ifc` + `_preview.png` + дамп
`data/ifc/_threed_last.json`; ifcopenshell-проверка: есть IfcSpace с русским
именем, IfcFurnishingElement, IfcWall; warnings прочитать и зафиксировать.

- [ ] **Step 4: Ledger** — записать результат smoke в
`.superpowers/sdd/progress.md` (файл «## 2026-09-19 3D Design Phase 3»
продолжить).

---

### Task 6: E2E браузер + скриншоты (main-agent-only)

**Files:** скриншоты `docs/3d-design-interior-{modal,result}.png` (коммит),
скрипты `.superpowers/sdd/e2e_interior_step*.py` (без коммита).

- [ ] **Step 1:** Методика — скрипты фазы 2 (`.superpowers/sdd/e2e_facade_step1.py`
и step3): `pip`-playwright уже в venv, `launch_persistent_context(channel="chrome",
headless=True)`, СВЕЖИЙ профиль `.superpowers/sdd/browser-profile-i3` (галерея
чистая — выбор после Upload гарантированно наш).
- [ ] **Step 2:** Чек-лист: (1) модалка: все 3 плитки активны; (2) клик «Интерьер» →
placeholder интерьерный RU, «Фасад»/«Генплан» → свои; (3) Upload
`e2e_plan.png` → бейдж «Галерея», превью data:; (4) скриншот
`docs/3d-design-interior-modal.png` (плитка «Интерьер» подсвечена);
(5) промт «высота стен 2.7, дверь, окно» → Generate → ≤150 с → модалка
закрыта, тост «Модель создана: 3D_interior_….ifc»; (6) вкладка IFC: чип
`#stat-model` = имя, дерево загружено; (7) обход листьев дерева: клик —
props показывает IfcSpace «Кухня» (имя!), CONCEPTUAL_DOOR/WINDOW,
FURNITURE_BED/TABLE (props-панель ЧИСТИТЬ между кликами — грабля фазы 2);
(8) 📸 To Canvas → растровый слой на холсте; (9) консоль: только стоковый
redux-persist шум; (10) скриншот `docs/3d-design-interior-result.png`.
- [ ] **Step 3:** Известные ограничения (не баги): canvas-picking групп
@thatopen (п.38 HANDOFF — элементы выбираются деревом); пустой select
сервер-моделей — by design.
- [ ] **Step 4:** Коммит скриншотов строго по pathspec:
`git add -- docs/3d-design-interior-modal.png docs/3d-design-interior-result.png`
+ commit + запись в ledger.

---

### Task 7: Документация + финальный коммит фазы

**Files:**
- Modify: `HANDOFF.md` (СЛЕДУЮЩИЙ свободный номер — проверить по файлу;
  чужая сессия занимает п.39, ожидается п.40; вставлять после последнего),
  `README.md` (раздел «3D Design» — сценарий «Интерьер», указатель HANDOFF
  «п. 37–38» → «п. 37–40» по факту), спека-статус.

- [ ] **Step 1: HANDOFF п.40** (по образцу п.38): конвейер интерьера
  (SYSTEM_INTERIOR, правило пиксели+метры, validate_interior, build_interior:
  плита IfcSlab/стены IfcWall-сегменты с поворотом/проёмы сквозь стену
  +0.06/IfcSpace с именами/pset Room/IfcFurnishingElement с FURNITURE_*,
  палитра типов, поворот −rot_deg из-за Y-флипа, превью-чертёж в метрах),
  роутер-ветвление, плитка виджета, артефакты, грабли живого прогона.
- [ ] **Step 2: README** — подраздел «Сценарий «Интерьер» (фаза 3)» после
  фасада: вход — 2D-план (не фото!), цикл план→3D→человек→снимок→референсы,
  комнаты-имена, мебель-типы, концепт-дисклеймер.
- [ ] **Step 3: Спека** — статус-блок: «Фаза 3 (интерьер) реализована 19.09
  (ветка 3d) — см. HANDOFF п.40».
- [ ] **Step 4: Прогон + коммит**

```bash
PYTHONUTF8=1 ./venv/Scripts/python.exe tests/test_threed.py
PYTHONUTF8=1 ./venv/Scripts/python.exe tests/test_designcode.py
git add -- HANDOFF.md README.md docs/superpowers/specs/2026-09-18-3d-design-ifc-generation-design.md
git commit -m "docs: 3D Design фаза 3 (интерьер) — HANDOFF п.40, README, спека" -- HANDOFF.md README.md docs/superpowers/specs/2026-09-18-3d-design-ifc-generation-design.md
```

ВНИМАНИЕ (грабля сессии): в HANDOFF может лежать незакоммиченный чужой п.39
(model-manager) — коммитить свой пункт ЧЕРЕЗ git-пламбинг
(`git show HEAD:HANDOFF.md` → вставка своего пункта → `git hash-object -w
--stdin` → `git update-index --cacheinfo` → `git commit` БЕЗ pathspec, чужие
файлы в индексе сперва `git restore --staged`, после — вернуть стейджинг),
либо дождаться коммита чужой сессии. Ни в каком случае не коммитить чужой
незакоммиченный блок.

---

## Самопроверка (выполнена при написании плана)

- Спека-интерьер покрыта: вход 2D-план (SYSTEM_INTERIOR явно «NOT a photo»),
  ЕДИНОЕ правило координат (validate+build), опоры масштаба (промпт), схема
  целиком (outline/walls/openings/rooms/furniture), сборка по спеке (плита,
  стены-боксы, проёмы, IfcSpace с именами, IfcFurnishingElement с ObjectType,
  палитра, поворот placement-ом), «обозначение объектов» = имена комнат+типы
  мебели+цвет+штатный BIM-контекст (п.25/26 уже работают), превью.
- Отступления от спеки (зафиксированы): проёмы НЕ заподлицо, а сквозь стену
  с выступом 0.03 м (урок фазы 2 — иначе невидимы); превью — чертёж в метрах,
  не оверлей на исходник (соглашение фаз 1–2).
- Ошибки спеки: не-JSON → ретрай+422 (штатно), пустая сцена → ValueError
  в validate_interior (422), сборщик → 422 (штатный except роутера).
- Типы согласованы: `build_interior(scene, ifc_path, preview_path, meta)`
  (Task 1) = вызов в Task 3; `validate_interior(scene, img_w, img_h)` (Task 2)
  = вызов в Task 3; FURNITURE_RU/INTERIOR_DEFAULT_COLORS ключи совпадают с
  FURNITURE_TYPES; имена для виджета promptPhInterior одинаковы в Task 4.
- Мелочи учтены: IfcFurnishingElement без predefined_type (нет в IFC4);
  Y-флип инвертирует угол поворота мебели (−rot_deg); номер HANDOFF
  определяется по факту (чужой п.39).
