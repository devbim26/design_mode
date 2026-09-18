# 3D Design — фаза 1 (обвязка + сценарий «Генплан») Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Кнопка «3D Design» открывает модалку (сценарий + промт + превью источника), сервер через VLM ImageRouter (по умолчанию `openai/gpt-6-astra`) строит JSON-сцену «Генплан» по картинке, детерминированный сборщик на ifcopenshell пишет валидный IFC4 в `data/ifc/`, модель автозагружается во вкладке IFC.

**Architecture:** Виджет `devbim_topright_buttons.js` (DOM-модалка, бандлы не трогаем) → `POST /api/v1/threed/generate` → роутер `threed.py` (FastAPI, per-company root) → `call_vlm`-паттерн prompt_enhancer (ключ/модель лениво из imagerouter-роутера/.env/файла менеджера) → `threed_scenarios.validate_genplan` (клампы/дефолты/выкидывание битого) → `threed_build.build_genplan` (адаптация проверенного `build_model.py` скилла image-to-ifc) → IFC + превью → `devbim:ifc:lastModel` + `__devbimSwitchTab('ifc')` → автозагрузка (малый патч ifcviewer.html).

**Tech Stack:** Python 3.11 (venv InvokeAI), FastAPI, ifcopenshell + shapely + matplotlib + Pillow, requests; JS — vanilla-виджет в духе devbim_admin.js/cut_tool.

## Global Constraints

- Windows, Git Bash; python — всегда `./venv/Scripts/python.exe` из корня проекта
  `C:\Users\Lenovo\Desktop\проект SOFT_2\Дизайн\InvokeAI\InvokeAI`.
- Тесты — plain asserts + печать OK (НЕ pytest): `venv\Scripts\python.exe tests\test_threed.py`.
- В `venv/Lib/site-packages` руками не править — только через setup-скрипты; все setup идемпотентны, бэкапы `*.threed-bak`.
- Коммитить нельзя: `.env`, `companies.json`, `companies/*`. В индексе застейджен чужой WIP
  (HANDOFF.md, design_code_viewer.html, test_designcode.py) — коммитить точечно через
  `git commit <путь> -m ...` (pathspec), как в этой ветке уже делали.
- Сценарии латиницей в именах файлов: `plan` (фаза 1), `facade`/`interior` — фазы 2–3.
- Координаты сцен: позиции — ПИКСЕЛИ картинки (trace_width/height = размеры ПОСЛЕ даунскейла
  до ≤1536), размеры/высоты — метры.
- VLM: max_tokens 8000 (reasoning-модели!), temperature 0.2, картинка — PNG ≤1536 px на белом фоне.
- Модель-аналитик: файл `data/imagerouter_threed_model.json` → `.env THREED_MODEL` →
  дефолт `openai/gpt-6-astra`. Валидация по каталогу: `input_modalities` содержит image,
  `output_modalities` содержит text.
- Сервер перезапускать только `_restart_server.ps1`; после деплоя JS пользователю нужен F5.
- Живые запросы к Astra стоят ~$0.05–0.15 за генерацию — в тестах по умолчанию мок, живой smoke один раз (Task 9).

## File Structure

```
threed/
  threed_router.py      — FastAPI-роутер: POST /v1/threed/generate, GET/PUT /v1/threed/model
  threed_scenarios.py   — системные промпты, extract_json, validate_genplan
  threed_build.py       — сборка IFC4 (генплан) + превью-обводка (адаптация скилла)
setup_threed.py         — деплой 3 файлов в venv/.../routers/ + патч api_app.py
imagerouter/devbim_topright_buttons.js  — модалка 3D (правка существующего виджета)
imagerouter/imagerouter.html            — админ-секция «3D-генерация» (правка)
ifc/ifcviewer.html      — автозагрузка lastModel на полной вкладке (правка)
tests/test_threed.py    — все тесты фазы (plain asserts)
```

Деплой-имена: `threed/threed_router.py` → `routers/threed.py`; `threed_scenarios.py` и
`threed_build.py` → `routers/` под теми же именами. Роутер импортирует их с фолбэком
(try: `from invokeai.app.api.routers import ...` / except: `from threed import ...`),
чтобы работал и в venv, и из дерева проекта в тестах.

---

### Task 1: Зависимости + сборщик генплана (`threed/threed_build.py`)

**Files:**
- Create: `threed/threed_build.py`
- Test: `tests/test_threed.py`

**Interfaces:**
- Produces: `build_genplan(scene: dict, image: PIL.Image.Image, ifc_path: Path, preview_path: Path, meta: dict) -> Path`
  — scene = dict схемы footprints (см. тест), meta = `{Scenario, Prompt, Model, Source}` для pset `DevBIM`
  у IfcProject. Пишет `ifc_path` (IFC4) и `preview_path` (PNG: обводки+этажность поверх картинки).

- [ ] **Step 1: Установить зависимости в общий venv**

```bash
./venv/Scripts/python.exe -m pip install ifcopenshell shapely
./venv/Scripts/python.exe -c "import ifcopenshell, shapely; print('OK', ifcopenshell.version)"
```
Expected: `OK 0.8.x` (или новее). Колёса cp311 для Windows существуют.

- [ ] **Step 2: Написать failing-тест (сборка + проверки IFC)**

`tests/test_threed.py` (создать; функции сцен/роутера добавятся позже — файл расширяется по задачам):

```python
# -*- coding: utf-8 -*-
"""3D Design: тесты фазы 1 (сборщик, сценарий, роутер, статика виджета)."""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TMP = ROOT / "tests" / "_threed_tmp"


def sample_scene():
    """Генплан 800x600: жилой 5 эт. (прямоуг.), школа 3 эт., земля."""
    return {
        "trace_width": 800, "trace_height": 600,
        "metres_per_trace_pixel": 0.25,
        "residential_storey_height": 3.1, "public_storey_height": 3.3,
        "sections": [
            {"id": "Ж-1", "building": "Ж-1", "use": "Residential", "floors": 5,
             "points_px": [[100, 100], [500, 100], [500, 300], [100, 300]]},
            {"id": "Ш-1", "building": "Ш-1", "use": "School", "floors": 3,
             "points_px": [[100, 400], [300, 400], [300, 550], [100, 550]]},
        ],
        "context": [
            {"kind": "Ground", "z": -0.45, "depth": 0.35,
             "points_px": [[0, 0], [800, 0], [800, 600], [0, 600]]},
        ],
    }


def test_build_genplan():
    import ifcopenshell
    from PIL import Image
    from threed.threed_build import build_genplan

    TMP.mkdir(exist_ok=True)
    img = Image.new("RGB", (800, 600), (245, 245, 240))
    ifc = TMP / "3D_plan_test.ifc"
    prev = TMP / "3D_plan_test_preview.png"
    path = build_genplan(sample_scene(), img, ifc, prev,
                         {"Scenario": "plan", "Prompt": "тест", "Model": "test/model",
                          "Source": "3D Design"})
    assert path == ifc and ifc.is_file() and prev.is_file()

    m = ifcopenshell.open(str(ifc))
    assert m.schema == "IFC4"
    gids = [r.GlobalId for r in m.by_type("IfcRoot")]
    assert len(gids) == len(set(gids)), "GlobalId не уникальны"
    assert len(m.by_type("IfcBuilding")) == 2          # Ж-1 и Ш-1
    assert len(m.by_type("IfcBuildingStorey")) == 5 + 3
    assert len(m.by_type("IfcBuildingElementProxy")) == 5 + 3
    assert len(m.by_type("IfcGeographicElement")) == 1  # Ground
    # объём первой секции: 400x200 px * 0.25 = 100x50 м -> 5000 м2 * 3.1
    from ifcopenshell.util.element import get_psets
    p = m.by_type("IfcBuildingElementProxy")[0]
    qto = get_psets(p).get("Qto_BuildingElementProxyQuantities", {})
    assert abs(qto.get("NetVolume", 0) - 5000 * 3.1) < 1.0
    # pset DevBIM у проекта
    proj = m.by_type("IfcProject")[0]
    assert get_psets(proj).get("DevBIM", {}).get("Scenario") == "plan"
    print("test_build_genplan OK")


if __name__ == "__main__":
    test_build_genplan()
    print("ALL OK")
```

- [ ] **Step 3: Запустить — должен упасть**

Run: `./venv/Scripts/python.exe tests/test_threed.py`
Expected: `ModuleNotFoundError: No module named 'threed'` (или `threed.threed_build`).

- [ ] **Step 4: Написать `threed/threed_build.py`** (адаптация `build_model.py` скилла
  image-to-ifc: вход — dict и PIL-картинка, без README/_3D-PNG/CLI; +pset DevBIM)

```python
# -*- coding: utf-8 -*-
"""Сборка IFC4 «Генплан» по сцене-JSON (адаптация build_model.py скилла image-to-ifc).

Вход: scene (схема footprints: sections/context, пиксели + метры), PIL-картинка
исходника (после даунскейла), пути IFC и превью. Выход: путь к IFC.
"""
from collections import defaultdict
from pathlib import Path

import ifcopenshell
import ifcopenshell.api
import matplotlib
matplotlib.use("Agg")
import matplotlib.colors
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as PlotPolygon
import numpy as np
from PIL import Image
from shapely.geometry import Polygon
from shapely.geometry.polygon import orient

COLORS = {
    "Residential5": "#ded3b8", "Residential6": "#b6c7d3",
    "School": "#d68967", "Kindergarten": "#e5bd57",
    "Ground": "#c9d4b7", "Road": "#acafb3", "Parking": "#929ba5",
    "Sport": "#87ab6b", "Court": "#719eb3", "Play": "#d4ac9e",
}
USE_NAMES = {"Residential": "Жилой корпус", "School": "Школа", "Kindergarten": "Детский сад"}

ASSUMPTION = (
    "Концептуальная обводка кровель по растровой схеме (3D Design). Размеры, этажность "
    "секций и высоты оценочные. Геопривязка и ориентация на север отсутствуют. Не "
    "использовать как обмерную или рабочую документацию."
)


def _api(operation, **kwargs):
    return ifcopenshell.api.run(operation, **kwargs)


def _properties(model, product, name, values):
    pset = _api("pset.add_pset", file=model, product=product, name=name)
    _api("pset.edit_pset", file=model, pset=pset, properties=values)


def _metric_polygon(data, points):
    scale = data["metres_per_trace_pixel"]
    height = data["trace_height"]
    polygon = Polygon([(x * scale, (height - y) * scale) for x, y in points])
    if not polygon.is_valid or polygon.area <= 0:
        raise ValueError(f"Некорректный контур: {points}")
    return orient(polygon, sign=1.0)


def build_genplan(scene, image, ifc_path, preview_path, meta):
    """scene: dict схемы; image: PIL (уже ≤1536 px, белый фон); meta: pset DevBIM."""
    data = dict(scene)  # не мутировать вход
    data.setdefault("project_name", "3D Design — генплан")
    data.setdefault("site_name", "Участок")
    model = _api("project.create_file", version="IFC4")
    project = _api("root.create_entity", file=model, ifc_class="IfcProject",
                   name=data.get("project_name"))
    project.Description = ASSUMPTION
    units = [_api("unit.add_si_unit", file=model, unit_type=t)
             for t in ("LENGTHUNIT", "AREAUNIT", "VOLUMEUNIT")]
    _api("unit.assign_unit", file=model, units=units)
    context = _api("context.add_context", file=model, context_type="Model")
    body = _api("context.add_context", file=model, context_type="Model",
                context_identifier="Body", target_view="MODEL_VIEW", parent=context)
    site = _api("root.create_entity", file=model, ifc_class="IfcSite", name=data.get("site_name"))
    _api("aggregate.assign_object", file=model, products=[site], relating_object=project)
    _api("geometry.edit_object_placement", file=model, product=site, matrix=np.eye(4))
    _properties(model, project, "DevBIM", {
        "Source": meta.get("Source", "3D Design"), "Scenario": meta.get("Scenario", "plan"),
        "Prompt": (meta.get("Prompt") or "")[:1024], "Model": meta.get("Model", ""),
        "ApproximateGeometry": True, "Notes": ASSUMPTION,
    })
    _properties(model, site, "SourceAndAssumptions", {
        "SourceImage": meta.get("SourceImage", "canvas/viewer"),
        "GeometryStatus": "CONCEPTUAL / APPROXIMATE",
        "MetresPerTracePixel": data["metres_per_trace_pixel"],
        "TraceWidth": data["trace_width"], "TraceHeight": data["trace_height"],
        "Georeferenced": False, "NorthKnown": False, "Notes": ASSUMPTION,
    })
    styles = {}
    for key, color in COLORS.items():
        r, g, b = matplotlib.colors.to_rgb(color)
        style = _api("style.add_style", file=model, name=key)
        _api("style.add_surface_style", file=model, style=style,
             ifc_class="IfcSurfaceStyleShading",
             attributes={"SurfaceColour": {"Name": key, "Red": r, "Green": g, "Blue": b},
                         "Transparency": 0.0})
        styles[key] = style

    def mass(name, polygon, z, depth, container, color_key,
             ifc_class="IfcBuildingElementProxy", object_type="CONCEPTUAL_MASS"):
        product = _api("root.create_entity", file=model, ifc_class=ifc_class,
                       predefined_type="USERDEFINED", name=name)
        product.ObjectType = object_type
        xy = np.array(polygon.exterior.coords, dtype=float)
        origin = np.array(polygon.centroid.coords[0])
        profile = _api("profile.add_arbitrary_profile", file=model,
                       profile=(xy - origin).tolist(), name=name)
        representation = _api("geometry.add_profile_representation", file=model, context=body,
                              profile=profile, depth=depth, cardinal_point=None)
        _api("geometry.assign_representation", file=model, product=product,
             representation=representation)
        _api("spatial.assign_container", file=model, products=[product],
             relating_structure=container)
        matrix = np.eye(4)
        matrix[:3, 3] = [float(origin[0]), float(origin[1]), float(z)]
        _api("geometry.edit_object_placement", file=model, product=product, matrix=matrix)
        _api("style.assign_representation_styles", file=model, shape_representation=representation,
             styles=[styles[color_key]])
        return product

    groups = defaultdict(list)
    for section in data["sections"]:
        groups[section["building"]].append(section)
    for building_id, sections in groups.items():
        use = sections[0].get("use", "Residential")
        public = use != "Residential"
        floor_height = data["public_storey_height" if public else "residential_storey_height"]
        floors = max(s["floors"] for s in sections)
        name = f"{USE_NAMES.get(use, use)} {building_id}"
        if any(s.get("partial") for s in sections):
            name += " (видимый фрагмент)"
        building = _api("root.create_entity", file=model, ifc_class="IfcBuilding", name=name)
        building.Description = ASSUMPTION
        _api("aggregate.assign_object", file=model, products=[building], relating_object=site)
        _api("geometry.edit_object_placement", file=model, product=building, matrix=np.eye(4))
        _properties(model, building, "SiteMassing", {
            "BuildingId": building_id, "Use": use, "ApproximateGeometry": True,
            "NumberOfStoreys": floors, "MaximumHeight": floors * floor_height,
            "StoreyHeight": floor_height, "Source": "3D Design", "Notes": ASSUMPTION,
        })
        storeys = []
        for floor in range(floors):
            storey = _api("root.create_entity", file=model, ifc_class="IfcBuildingStorey",
                          name=f"{building_id} — этаж {floor + 1:02d}")
            storey.Elevation = floor * floor_height
            _api("aggregate.assign_object", file=model, products=[storey], relating_object=building)
            matrix = np.eye(4)
            matrix[2, 3] = storey.Elevation
            _api("geometry.edit_object_placement", file=model, product=storey, matrix=matrix)
            storeys.append(storey)
        for section in sections:
            polygon = _metric_polygon(data, section["points_px"])
            color_key = use if public else f"Residential{section['floors']}"
            if color_key not in styles:  # этажность без своего цвета -> ближайший
                color_key = "Residential5" if section["floors"] < 6 else "Residential6"
            for floor in range(section["floors"]):
                z = floor * floor_height
                product = mass(f"{USE_NAMES.get(use, use)} {section['id']} / этаж {floor + 1}",
                               polygon, z, floor_height, storeys[floor], color_key)
                _properties(model, product, "MassingElement", {
                    "Section": section["id"], "Use": use, "Storey": floor + 1,
                    "SectionStoreys": section["floors"], "StoreyHeight": floor_height,
                    "BaseElevation": z, "FootprintArea": polygon.area,
                    "ApproximateGeometry": True,
                    "PartialAtImageBoundary": bool(section.get("partial", False)),
                })
                qto = _api("pset.add_qto", file=model, product=product,
                           name="Qto_BuildingElementProxyQuantities")
                _api("pset.edit_qto", file=model, qto=qto, properties={
                    "NetSurfaceArea": float(polygon.area),
                    "NetVolume": float(polygon.area * floor_height)})
    for item in data.get("context", []):
        product = mass(item.get("name", item["kind"]), _metric_polygon(data, item["points_px"]),
                       item.get("z", -0.45), item.get("depth", 0.35), site, item["kind"],
                       ifc_class="IfcGeographicElement", object_type="SITE_SURFACE")
        _properties(model, product, "SiteContext",
                    {"Use": item["kind"], "ApproximateGeometry": True})

    model.header.file_name.name = ifc_path.name
    model.header.file_name.author = ("3D Design",)
    model.header.file_name.organization = ("DevBIM",)
    model.header.file_name.preprocessor_version = f"IfcOpenShell {ifcopenshell.version}"
    model.header.file_name.originating_system = "DevBIM 3D Design (VLM scene -> IFC)"
    model.header.file_name.authorization = "Approximate model; not construction documentation"
    ifc_path.parent.mkdir(parents=True, exist_ok=True)
    model.write(str(ifc_path))
    _draw_overlay(data, image, preview_path)
    return ifc_path


def _draw_overlay(data, image, preview_path):
    """Обводки + этажность поверх исходной картинки (как _footprints.png скилла)."""
    fig, ax = plt.subplots(figsize=(18, 10.125), facecolor="white")
    ax.imshow(image, extent=(0, data["trace_width"], data["trace_height"], 0))
    for section in data["sections"]:
        use = section.get("use", "Residential")
        key = use if use != "Residential" else f"Residential{section['floors']}"
        if key not in COLORS:
            key = "Residential5"
        ax.add_patch(PlotPolygon(section["points_px"], facecolor=COLORS[key],
                                 edgecolor="#263747", alpha=.78, linewidth=1.1))
        pt = Polygon(section["points_px"]).representative_point()
        ax.text(pt.x, pt.y, f"{section['id']}\n{section['floors']} эт.", ha="center",
                va="center", fontsize=6.5, color="#15232e", fontweight="bold",
                bbox=dict(facecolor="white", alpha=.65, pad=1, edgecolor="none"))
    ax.set_xlim(0, data["trace_width"])
    ax.set_ylim(data["trace_height"], 0)
    ax.axis("off")
    ax.set_title("3D Design — обводка зданий и этажность (контуры и масштаб оценочные)",
                 fontsize=14)
    fig.tight_layout()
    preview_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(preview_path, dpi=160, facecolor="white")
    plt.close(fig)
```

- [ ] **Step 5: Запустить тест — PASS**

Run: `./venv/Scripts/python.exe tests/test_threed.py`
Expected: `test_build_genplan OK` / `ALL OK`.

- [ ] **Step 6: Commit**

```bash
git add threed/threed_build.py tests/test_threed.py
git commit threed/threed_build.py tests/test_threed.py -m "feat(3d): сборщик IFC4 генплана (адаптация build_model.py скилла) + тесты"
```

---

### Task 2: Сценарий «Генплан»: системный промпт + валидация (`threed/threed_scenarios.py`)

**Files:**
- Create: `threed/threed_scenarios.py`
- Test: `tests/test_threed.py` (дополнить)

**Interfaces:**
- Produces:
  - `SYSTEM_GENPLAN: str` — системный промпт;
  - `extract_json(text: str) -> dict | None` — из сырого ответа VLM;
  - `validate_genplan(scene: dict, img_w: int, img_h: int) -> tuple[dict, list[str]]` —
    возвращает (сцена с дефолтами/клампами, warnings[]); выбрасывает `ValueError` только если
    валидных секций не осталось (роутер превратит в 422).

- [ ] **Step 1: Дописать failing-тесты в `tests/test_threed.py`** (в конец, до `__main__`; в `__main__` добавить вызовы)

```python
def test_extract_json():
    from threed.threed_scenarios import extract_json
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('Вот ответ: {"a": [1,2]} конец.') == {"a": [1, 2]}
    assert extract_json("никакого json нет") is None
    print("test_extract_json OK")


def test_validate_genplan():
    from threed.threed_scenarios import validate_genplan
    # валидная сцена проходит, дефолты проставлены
    s = sample_scene()
    s.pop("residential_storey_height")
    out, warn = validate_genplan(s, 800, 600)
    assert out["residential_storey_height"] == 3.1
    assert len(out["sections"]) == 2
    # координаты за пределами картинки клампятся
    s = sample_scene()
    s["sections"][0]["points_px"] = [[-50, 100], [900, 100], [900, 300], [-50, 300]]
    out, warn = validate_genplan(s, 800, 600)
    xs = [p[0] for p in out["sections"][0]["points_px"]]
    assert min(xs) >= 0 and max(xs) <= 800
    # битая секция выкидывается с warning
    s = sample_scene()
    s["sections"][1]["points_px"] = [[1, 1]]  # мало точек
    out, warn = validate_genplan(s, 800, 600)
    assert len(out["sections"]) == 1 and any("Ш-1" in w for w in warn)
    # этажность клампится 1..30
    s = sample_scene()
    s["sections"][0]["floors"] = 99
    out, _ = validate_genplan(s, 800, 600)
    assert out["sections"][0]["floors"] == 30
    # неизвестный kind контекста выкидывается
    s = sample_scene()
    s["context"].append({"kind": "Beach", "z": 0, "depth": 0.1,
                         "points_px": [[0, 0], [10, 0], [10, 10], [0, 10]]})
    out, warn = validate_genplan(s, 800, 600)
    assert len(out["context"]) == 1 and any("Beach" in w for w in warn)
    print("test_validate_genplan OK")
```

- [ ] **Step 2: Запустить — упасть (`No module named 'threed.threed_scenarios'`)**

Run: `./venv/Scripts/python.exe tests/test_threed.py`

- [ ] **Step 3: Написать `threed/threed_scenarios.py`**

```python
# -*- coding: utf-8 -*-
"""Сценарии 3D Design: системные промпты, разбор JSON, валидация сцен.

Фаза 1 — «Генплан» (plan). Координаты позиций — ПИКСЕЛИ картинки,
размеры/высоты — метры (единое правило спеки).
"""

SYSTEM_GENPLAN = """You are a BIM site analyst. Look at the attached image (top-down
master plan / aerial / hand scheme). Trace building footprints and site context.
Reply with STRICT JSON ONLY - no markdown fences, no comments, no extra keys.

Schema:
{
 "metres_per_trace_pixel": <float: meters per image pixel. Estimate from anchors:
   sports ground 16-18 x 32-36 m, parking space 2.5 x 5 m, road width 6-10 m,
   or printed dimension labels. Typical scheme ~0.3-0.7.>,
 "residential_storey_height": 3.1,
 "public_storey_height": 3.3,
 "sections": [
   {"id": "<short unique id>", "building": "<group id; sections of one complex share it>",
    "use": "Residential|School|Kindergarten", "floors": <int 1-30>,
    "points_px": [[x, y], ...4-18 points, CLOCKWISE, image pixel coordinates,
      y=0 at the TOP of the image, buildings traced by ROOFS>,
    "partial": <true only if cut by the image edge>}
 ],
 "context": [
   {"kind": "Ground|Road|Parking|Sport|Court|Play", "z": <elevation, Ground=-0.45>,
    "depth": <thickness, Ground=0.35>, "points_px": [[x, y], ...]}
 ]
}

Rules:
- One section per building volume; split multi-part complexes into sections with the
  same "building".
- ALWAYS add one Ground context covering the whole image.
- The USER PROMPT overrides your guesses (floors, use, scale) wherever it states them.
- Positions are pixels of the ATTACHED image; only heights/thicknesses/scale are meters.
"""

DEFAULT_SCALE = 0.5
SCALE_MIN, SCALE_MAX = 0.05, 10.0
USE_WHITELIST = {"Residential", "School", "Kindergarten"}
KIND_WHITELIST = {"Ground", "Road", "Parking", "Sport", "Court", "Play"}


def extract_json(text):
    """Сырой ответ VLM -> dict | None (срез ```-заборов, первый {...} до последнего })."""
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.strip("`")
        if t[:4].lower() == "json":
            t = t[4:]
    start, end = t.find("{"), t.rfind("}")
    if start < 0 or end <= start:
        return None
    import json
    try:
        data = json.loads(t[start:end + 1])
        return data if isinstance(data, dict) else None
    except ValueError:
        return None


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def _valid_points(points, w, h):
    """Список точек -> (клампнутые точки | None). None = битый контур."""
    if not isinstance(points, list) or len(points) < 3 or len(points) > 32:
        return None
    fixed = []
    for p in points:
        if not isinstance(p, (list, tuple)) or len(p) != 2:
            return None
        try:
            x, y = float(p[0]), float(p[1])
        except (TypeError, ValueError):
            return None
        if not (x == x and y == y):  # NaN
            return None
        fixed.append([_clamp(x, 0, w), _clamp(y, 0, h)])
    return fixed


def validate_genplan(scene, img_w, img_h):
    """Сцена от VLM -> (чистая сцена, warnings). ValueError — не осталось секций."""
    warnings = []
    out = {
        "trace_width": int(img_w), "trace_height": int(img_h),
        "metres_per_trace_pixel": DEFAULT_SCALE,
        "residential_storey_height": 3.1, "public_storey_height": 3.3,
        "sections": [], "context": [],
    }
    if not isinstance(scene, dict):
        raise ValueError("Сцена не является JSON-объектом")
    try:
        scale = float(scene.get("metres_per_trace_pixel", DEFAULT_SCALE))
    except (TypeError, ValueError):
        scale = DEFAULT_SCALE
    if not (SCALE_MIN <= scale <= SCALE_MAX):
        warnings.append(f"Масштаб {scale} вне диапазона — принят {DEFAULT_SCALE} м/px")
        scale = DEFAULT_SCALE
    out["metres_per_trace_pixel"] = scale
    for key in ("residential_storey_height", "public_storey_height"):
        try:
            v = float(scene.get(key, out[key]))
            out[key] = _clamp(v, 2.0, 6.0)
        except (TypeError, ValueError):
            warnings.append(f"{key}: неверное значение — дефолт {out[key]}")

    for sec in scene.get("sections", []) or []:
        sid = str(sec.get("id", sec.get("building", "?")))[:24]
        points = _valid_points(sec.get("points_px", sec.get("points")), img_w, img_h)
        if points is None:
            warnings.append(f"Секция {sid}: битый контур — пропущена")
            continue
        use = sec.get("use", "Residential")
        if use not in USE_WHITELIST:
            warnings.append(f"Секция {sid}: тип {use} не поддержан — Residential")
            use = "Residential"
        try:
            floors = int(sec.get("floors", 5))
        except (TypeError, ValueError):
            floors = 5
        floors = _clamp(floors, 1, 30)
        out["sections"].append({
            "id": sid, "building": str(sec.get("building", sid))[:24], "use": use,
            "floors": floors, "points_px": points, "partial": bool(sec.get("partial")),
        })
    if not out["sections"]:
        raise ValueError("На картинке не найдено зданий для 3D-модели")

    for item in scene.get("context", []) or []:
        kind = item.get("kind")
        if kind not in KIND_WHITELIST:
            warnings.append(f"Контекст {kind}: неизвестный тип — пропущен")
            continue
        points = _valid_points(item.get("points_px", item.get("points")), img_w, img_h)
        if points is None:
            warnings.append(f"Контекст {kind}: битый контур — пропущен")
            continue
        try:
            z, depth = float(item.get("z", -0.45)), float(item.get("depth", 0.35))
        except (TypeError, ValueError):
            z, depth = -0.45, 0.35
        out["context"].append({"kind": kind, "z": z, "depth": depth, "points_px": points})
    return out, warnings
```

- [ ] **Step 4: Тест зелёный**

Run: `./venv/Scripts/python.exe tests/test_threed.py`
Expected: три `OK` + `ALL OK`.

- [ ] **Step 5: Commit**

```bash
git commit threed/threed_scenarios.py tests/test_threed.py -m "feat(3d): промпт и валидация сценария генплан (клампы, дефолты, warnings)"
```

---

### Task 3: Роутер threed (`threed/threed_router.py`) — generate + менеджер модели

**Files:**
- Create: `threed/threed_router.py`
- Test: `tests/test_threed.py` (дополнить)

**Interfaces:**
- Consumes: `threed_scenarios.SYSTEM_GENPLAN/extract_json/validate_genplan`,
  `threed_build.build_genplan`, `invokeai.app.api.routers.imagerouter._load_key` (лениво).
- Produces:
  - `POST /api/v1/threed/generate` body `{"scenario": "plan", "prompt": str, "image": dataURL}`
    → `200 {"name": "3D_plan_….ifc", "warnings": [...]}` | `422 {"detail": msg}`;
  - `GET /api/v1/threed/model` → `{"model", "source", "vlms": [{"id"}, ...]}`;
  - `PUT /api/v1/threed/model` body `{"model"}` → `{"ok": true}`;
  - тестируемые функции: `_generate_impl(scenario, prompt, image: PIL, out_dir: Path) -> dict`,
    `_load_model_choice() -> tuple[str, str]`, `_vlm_list_cached(fetch) -> list[dict]`.

- [ ] **Step 1: Дописать failing-тесты** (в `tests/test_threed.py`)

```python
def _mock_vlm_ok(text):
    def call(system, prompt, image_url, model):
        return text
    return call


def test_generate_impl(monkeypatch=None):
    """Роутерная логика без HTTP: мок VLM -> IFC в tmp-каталоге."""
    from PIL import Image
    import threed.threed_router as R

    scene = sample_scene()
    R._call_vlm = _mock_vlm_ok("```json\n" + json.dumps(scene, ensure_ascii=False) + "\n```")
    TMP.mkdir(exist_ok=True)
    img = Image.new("RGB", (800, 600), (245, 245, 240))
    res = R._generate_impl("plan", "тест", img, TMP)
    assert res["name"].startswith("3D_plan_") and res["name"].endswith(".ifc")
    assert (TMP / res["name"]).is_file()
    assert (TMP / (Path(res["name"]).stem + "_preview.png")).is_file()
    assert (TMP / "_threed_last.json").is_file()

    # ретрай: первый ответ мусор, второй валидный
    calls = {"n": 0}
    def flaky(system, prompt, image_url, model):
        calls["n"] += 1
        return "мусор без json" if calls["n"] == 1 else json.dumps(scene)
    R._call_vlm = flaky
    res2 = R._generate_impl("plan", "", img, TMP)
    assert res2["name"].startswith("3D_plan_") and calls["n"] == 2

    # два мусорных ответа -> ValueError
    R._call_vlm = _mock_vlm_ok("no json here")
    try:
        R._generate_impl("plan", "", img, TMP)
        raise AssertionError("ожидалась ошибка")
    except ValueError as e:
        assert "JSON" in str(e) or "сцену" in str(e)
    print("test_generate_impl OK")


def test_model_choice_and_put(monkeypatch=None):
    import threed.threed_router as R
    # дефолт без файла
    R._model_store_path = lambda: TMP / "missing_threed_model.json"
    assert R._load_model_choice() == ("openai/gpt-6-astra", "default")
    # PUT-валидация по списку VLM (мок каталога)
    R._vlm_list_cached = lambda: [{"id": "openai/gpt-6-astra"}, {"id": "x/vlm-2"}]
    p = TMP / "threed_model.json"
    R._model_store_path = lambda: p
    R._save_model_choice("x/vlm-2")
    assert R._load_model_choice() == ("x/vlm-2", "file")
    try:
        R._validate_model_in_list("no/such")
        raise AssertionError("ожидалась ошибка")
    except ValueError:
        pass
    print("test_model_choice_and_put OK")
```

и в `__main__` добавить `test_generate_impl()`, `test_model_choice_and_put()`.

- [ ] **Step 2: Запустить — упасть (`No module named 'threed.threed_router'`)**

- [ ] **Step 3: Написать `threed/threed_router.py`**

```python
# -*- coding: utf-8 -*-
"""3D Design: генерация IFC по картинке (VLM ImageRouter) + выбор модели в менеджере.

Монтируется под /api:
    POST /api/v1/threed/generate  {scenario, prompt, image}  -> {name, warnings}
    GET  /api/v1/threed/model     {model, source, vlms:[...]}
    PUT  /api/v1/threed/model     {model} -> {ok}

Модель-аналитик: data/imagerouter_threed_model.json -> .env THREED_MODEL ->
дефолт openai/gpt-6-astra. Список VLM — свой запрос к /v3/models с модальным
фильтром (существующий GET /imagerouter/models фильтрует output=image и VLM
не возвращает!). IFC пишется в root_path/ifc (список IFC-вьювера), диагностический
дамп — root_path/_threed_last.json.
Разворачивается в venv скриптом setup_threed.py.
"""
import base64
import io
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path

import requests
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

try:  # задеплоено в venv
    from invokeai.app.api.routers import threed_build, threed_scenarios
except ImportError:  # дерево проекта (тесты)
    from threed import threed_build, threed_scenarios

from invokeai.app.services.config.config_default import get_config

threed_router = APIRouter(prefix="/v1/threed", tags=["threed"])

DEFAULT_MODEL = "openai/gpt-6-astra"
SCENARIOS = {"plan"}  # facade/interior — фазы 2-3
CHAT_TIMEOUT_S = 180
VLM_LIST_CACHE_S = 600
MAX_SIDE = 1536
MAX_TOKENS = 8000  # reasoning-модели тратят лимит до начала ответа (грабля п.22)

_vlm_cache = {"ts": 0.0, "list": []}


class GenerateBody(BaseModel):
    scenario: str = Field(min_length=1, max_length=32)
    prompt: str = Field(default="", max_length=4000)
    image: str = Field(min_length=32, max_length=20_000_000)  # dataURL PNG


class ModelBody(BaseModel):
    model: str = Field(min_length=3, max_length=128)


# --- per-company корень (…/data) и файлы ---
def _data_dir() -> Path:
    return Path(get_config().root_path)


def _ifc_dir() -> Path:
    d = _data_dir() / "ifc"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _model_store_path() -> Path:
    return _data_dir() / "imagerouter_threed_model.json"


def _env_threed_model() -> str | None:
    v = os.environ.get("THREED_MODEL")
    if v and v.strip():
        return v.strip()
    # .env проекта/компании (как design_code), без кэширования
    for cand in (_data_dir().parent / ".env", Path.cwd() / ".env"):
        try:
            if not cand.is_file():
                continue
            for line in cand.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("THREED_MODEL=") and line.partition("=")[2].strip():
                    return line.partition("=")[2].strip().strip('"').strip("'")
        except Exception:
            continue
    return None


def _load_model_choice() -> tuple[str, str]:
    p = _model_store_path()
    if p.is_file():
        try:
            m = json.loads(p.read_text(encoding="utf-8")).get("model")
            if isinstance(m, str) and m.strip():
                return m.strip(), "file"
        except Exception:
            pass
    env = _env_threed_model()
    if env:
        return env, "env"
    return DEFAULT_MODEL, "default"


def _save_model_choice(model: str) -> None:
    _model_store_path().write_text(
        json.dumps({"model": model}, ensure_ascii=False, indent=1), encoding="utf-8")


def _vlm_list_cached() -> list[dict]:
    """VLM каталога (вход image, выход text), кэш VLM_LIST_CACHE_S."""
    now = time.time()
    if _vlm_cache["list"] and now - _vlm_cache["ts"] < VLM_LIST_CACHE_S:
        return _vlm_cache["list"]
    try:
        resp = requests.get(
            "https://api.imagerouter.io/v3/models",
            params={"input_modalities": "image", "output_modalities": "text",
                    "limit": 500},
            timeout=30)
        items = resp.json().get("data", []) if resp.status_code == 200 else []
    except Exception:
        items = []
    out = []
    for m in items:
        arch = m.get("architecture") or {}
        if "image" in (arch.get("input_modalities") or []) and \
                "text" in (arch.get("output_modalities") or []):
            out.append({"id": m.get("id", "")})
    _vlm_cache.update(ts=now, list=out)
    return out


def _validate_model_in_list(model: str) -> None:
    ids = [m["id"] for m in _vlm_list_cached()]
    if ids and model not in ids:
        raise ValueError(f"Модель {model} не VLM или отсутствует в каталоге")


# --- подготовка картинки и вызов VLM ---
def _prepare_png(dataurl: str):
    from PIL import Image
    raw = base64.b64decode(dataurl.split(",", 1)[-1])
    img = Image.open(io.BytesIO(raw)).convert("RGBA")
    if img.width > MAX_SIDE or img.height > MAX_SIDE:
        img.thumbnail((MAX_SIDE, MAX_SIDE))
    bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
    return Image.alpha_composite(bg, img).convert("RGB")


def _to_dataurl(pil) -> str:
    buf = io.BytesIO()
    pil.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def _call_vlm(system: str, prompt: str, image_url: str, model: str) -> str:
    """Запрос в ImageRouter chat completions (паттерн prompt_enhancer.call_vlm).
    Возвращает СЫРОЙ ответ (разбор JSON — на вызывающем)."""
    from invokeai.app.api.routers.imagerouter import CHAT_COMPLETIONS_URL, _load_key

    key = _load_key()
    if not key:
        raise ValueError("API-ключ ImageRouter не задан (.env: IMAGEROUTER_API_KEY)")
    content = [{"type": "text", "text": prompt or "No user prompt; analyze the image."},
               {"type": "image_url", "image_url": {"url": image_url}}]
    resp = requests.post(
        CHAT_COMPLETIONS_URL,
        headers={"Authorization": f"Bearer {key}"},
        json={"model": model,
              "messages": [{"role": "system", "content": system},
                           {"role": "user", "content": content}],
              "max_tokens": MAX_TOKENS, "temperature": 0.2},
        timeout=CHAT_TIMEOUT_S)
    try:
        data = resp.json()
    except ValueError:
        data = None
    msg = None
    if isinstance(data, dict):
        err = data.get("error")
        if isinstance(err, dict):
            msg = err.get("message")
        elif isinstance(err, str):
            msg = err
    if resp.status_code >= 400 or msg:
        raise ValueError(f"ImageRouter: {msg or f'HTTP {resp.status_code}'}")
    choices = data.get("choices") if isinstance(data, dict) else None
    text = ((choices[0].get("message") or {}).get("content") or "") if choices else ""
    if not text.strip():
        raise ValueError("VLM вернула пустой ответ (попробуйте другую модель в менеджере)")
    return text


def _generate_impl(scenario: str, prompt: str, image, out_dir: Path | None = None) -> dict:
    """Без HTTP: анализ -> сцена -> IFC + превью. Raises ValueError (роутер даст 422)."""
    if scenario not in SCENARIOS:
        raise ValueError(f"Сценарий «{scenario}» в разработке (доступен: plan)")
    model, source = _load_model_choice()
    try:
        _validate_model_in_list(model)
    except ValueError:
        raise ValueError(f"Модель 3D-анализа {model} недоступна (не VLM или нет в каталоге)")
    image_url = _to_dataurl(image)

    scene = None
    last_err = ""
    for attempt in (1, 2):  # один ретрай на невалидный JSON
        raw = _call_vlm(threed_scenarios.SYSTEM_GENPLAN,
                        prompt + ("\n(attempt 2: return ONLY the strict JSON)" if attempt == 2
                                  else ""),
                        image_url, model)
        scene = threed_scenarios.extract_json(raw)
        if scene is not None:
            break
        last_err = raw[:200]
    if scene is None:
        raise ValueError(f"Модель не смогла описать сцену (не JSON): {last_err}")

    scene, warnings = threed_scenarios.validate_genplan(scene, image.width, image.height)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    name = f"3D_{scenario}_{stamp}.ifc"
    out_dir = Path(out_dir) if out_dir else _ifc_dir()
    ifc_path = out_dir / name
    preview_path = out_dir / (Path(name).stem + "_preview.png")
    threed_build.build_genplan(
        scene, image, ifc_path, preview_path,
        {"Scenario": scenario, "Prompt": prompt, "Model": model, "Source": "3D Design"})
    dump = {"ts": datetime.now().isoformat(), "scenario": scenario, "prompt": prompt,
            "model": model, "warnings": warnings, "name": name}
    try:
        (out_dir / "_threed_last.json").write_text(
            json.dumps(dump, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        pass
    return {"name": name, "warnings": warnings}


@threed_router.post("/generate")
def generate(body: GenerateBody) -> dict:
    try:
        image = _prepare_png(body.image)
        return _generate_impl(body.scenario, body.prompt, image)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:  # сборщик/сеть — единый вид для модалки
        raise HTTPException(status_code=422, detail=f"3D-генерация не удалась: {e}")


@threed_router.get("/model")
def get_model() -> dict:
    model, source = _load_model_choice()
    return {"model": model, "source": source, "vlms": _vlm_list_cached()}


@threed_router.put("/model")
def put_model(body: ModelBody) -> dict:
    try:
        _validate_model_in_list(body.model)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    _save_model_choice(body.model)
    return {"ok": True}
```

- [ ] **Step 4: Тест зелёный**

Run: `./venv/Scripts/python.exe tests/test_threed.py`
Expected: все `OK` + `ALL OK`. (Проверка `_load_key` не выполняется — `_call_vlm` замокан.)

- [ ] **Step 5: Commit**

```bash
git commit threed/threed_router.py tests/test_threed.py -m "feat(3d): роутер threed — generate (VLM+ретрай+сборка) и выбор модели (валидация VLM-модальностей)"
```

---

### Task 4: Деплой `setup_threed.py`

**Files:**
- Create: `setup_threed.py`
- Test: `tests/test_threed.py` (дополнить)

**Interfaces:**
- Produces: `deploy_files(venv: Path) -> bool`, `patch_api_app(api_app: Path) -> bool` —
  пути инъекционируются (тесты на tmp-структуре). Копирует: `threed/threed_router.py` →
  `venv/.../routers/threed.py`; `threed_scenarios.py`/`threed_build.py` → `routers/` as-is.
  Патчит api_app.py: импорт `threed` после `design_code`, `include_router` после design_code.

- [ ] **Step 1: Дописать failing-тест** (в `tests/test_threed.py`)

```python
def test_setup_threed():
    import setup_threed as S
    TMP.mkdir(exist_ok=True)
    fake = TMP / "fakevenv"
    routers = fake / "Lib" / "site-packages" / "invokeai" / "app" / "api" / "routers"
    routers.mkdir(parents=True, exist_ok=True)
    (routers / "imagerouter.py").write_text("# existing", encoding="utf-8")
    api_app = fake / "Lib" / "site-packages" / "invokeai" / "app" / "api_app.py"
    api_app.write_text(
        "from invokeai.app.api.routers import (\n    pdf,\n    design_code,\n)\n"
        'app.include_router(pdf.pdf_router, prefix="/api")\n'
        'app.include_router(design_code.design_code_router, prefix="/api")\n',
        encoding="utf-8")
    S.deploy_files(fake)
    assert (routers / "threed.py").is_file()
    assert (routers / "threed_scenarios.py").is_file()
    assert (routers / "threed_build.py").is_file()
    changed = S.patch_api_app(api_app)
    s = api_app.read_text(encoding="utf-8")
    assert changed and "    threed,\n" in s
    assert 'app.include_router(threed.threed_router, prefix="/api")' in s
    # идемпотентность: второй прогон ничего не меняет
    assert S.patch_api_app(api_app) is False
    assert S.deploy_files(fake) is False
    print("test_setup_threed OK")
```

- [ ] **Step 2: Запустить — упасть (`No module named 'setup_threed'`)**

- [ ] **Step 3: Написать `setup_threed.py`** (паттерн setup_designcode.py; идемпотентен)

```python
# -*- coding: utf-8 -*-
"""3D Design: деплой роутера threed в venv InvokeAI 6.2.0.

  1. Копирует threed/threed_router.py -> venv/.../routers/threed.py,
     threed/threed_scenarios.py и threed/threed_build.py -> routers/ (as-is).
  2. Патчит api_app.py: импорт + include_router threed после design_code
     (бэкап *.threed-bak).

Идемпотентен. Запуск: venv\\Scripts\\python.exe setup_threed.py
Порядок после force-reinstall: rebrand → imagerouter → ifcviewer → pdfviewer →
designcode → threed → siteauth (гейт: imagerouter-роутер обязан существовать).
"""
import shutil
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
SRC = BASE / "threed"
API_APP_REL = Path("Lib") / "site-packages" / "invokeai" / "app" / "api_app.py"
ROUTERS_REL = Path("Lib") / "site-packages" / "invokeai" / "app" / "api" / "routers"

IMPORT_ANCHOR = "    design_code,\n"
IMPORT_NEW = "    design_code,\n    threed,\n"
ROUTER_ANCHOR = 'app.include_router(design_code.design_code_router, prefix="/api")\n'
ROUTER_NEW = (ROUTER_ANCHOR + 'app.include_router(threed.threed_router, prefix="/api")\n')


def deploy_files(venv: Path) -> bool:
    routers = venv / ROUTERS_REL
    if not (routers / "imagerouter.py").exists():
        print("ОШИБКА: нет imagerouter-роутера — сначала setup_imagerouter.py")
        sys.exit(1)
    plan = [(SRC / "threed_router.py", routers / "threed.py"),
            (SRC / "threed_scenarios.py", routers / "threed_scenarios.py"),
            (SRC / "threed_build.py", routers / "threed_build.py")]
    if all(dst.is_file() and dst.read_bytes() == src.read_bytes() for src, dst in plan):
        print("Файлы threed уже развернуты, пропуск")
        return False
    for src, dst in plan:
        shutil.copy2(src, dst)
        print("Роутер развернут:", dst.name)
    return True


def patch_api_app(api_app: Path) -> bool:
    s = api_app.read_text(encoding="utf-8")
    if "include_router(threed.threed_router" in s:
        print("api_app.py уже пропатчен, пропуск")
        return False
    if "include_router(design_code.design_code_router" not in s:
        print("ОШИБКА: api_app.py без design_code — сначала setup_designcode.py")
        sys.exit(1)
    bak = api_app.with_suffix(".py.threed-bak")
    if not bak.exists():
        shutil.copy2(api_app, bak)
    orig = s
    s = s.replace(IMPORT_ANCHOR, IMPORT_NEW, 1)
    s = s.replace(ROUTER_ANCHOR, ROUTER_NEW, 1)
    if s == orig:
        print("ОШИБКА: не найдены точки вставки в api_app.py")
        sys.exit(1)
    api_app.write_text(s, encoding="utf-8")
    print("api_app.py пропатчен (бэкап:", bak.name + ")")
    return True


def main() -> None:
    venv = BASE / "venv"
    api_app = venv / API_APP_REL
    if not api_app.exists():
        print("Не найден venv InvokeAI:", api_app)
        sys.exit(1)
    deploy_files(venv)
    patch_api_app(api_app)
    print("Готово. Перезапустите сервер (_restart_server.ps1).")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Тест зелёный**

Run: `./venv/Scripts/python.exe tests/test_threed.py` → `test_setup_threed OK`, `ALL OK`.

- [ ] **Step 5: Commit**

```bash
git commit setup_threed.py tests/test_threed.py -m "feat(3d): setup_threed — идемпотентный деплой роутера (тесты на tmp-venv)"
```

---

### Task 5: ifcviewer.html — автозагрузка lastModel на полной вкладке

**Files:**
- Modify: `ifc/ifcviewer.html` (после блока `if (EMBED) { … }`, строка ~1813)
- Test: `tests/test_threed.py` (статические проверки)

**Interfaces:**
- Produces: полная вкладка IFC при старте читает `devbim:ifc:lastModel` и слушает
  `storage` (тот же код, что embed-панель). Деплой — повторный `setup_ifcviewer.py`.

- [ ] **Step 1: Вставить после закрывающей `}` блока `if (EMBED) { … }` (сразу после
  строки с `if (last) loadServerModel(last).catch(console.error);` и `}`)**

```js
// Полная вкладка IFC: автозагрузка последней модели (3D-генерация кладёт
// devbim:ifc:lastModel и переключает сюда). iframe монтируется свежим —
// прочитает только что сгенерированную модель; кнопка «3D» на вкладке IFC
// скрыта, спорных перезаписей нет.
if (!EMBED) {
  window.addEventListener("storage", (e) => {
    if (e.key !== LAST_MODEL_KEY || !e.newValue) return;
    if (e.newValue === loadedModelName) return;
    loadServerModel(e.newValue).catch((err) => console.warn("sync:", err));
  });
  const lastTab = (() => { try { return localStorage.getItem(LAST_MODEL_KEY); } catch { return null; } })();
  if (lastTab && lastTab !== loadedModelName) loadServerModel(lastTab).catch(console.error);
}
```

- [ ] **Step 2: Failing-тест (статика + синтаксис)** — добавить в `tests/test_threed.py`:

```python
def test_ifcviewer_autoload():
    import re
    src = (ROOT / "ifc" / "ifcviewer.html").read_text(encoding="utf-8")
    m = re.search(r'<script type="module">(.*?)</script>', src, re.S)
    assert m, "module-скрипт не найден"
    chk = ROOT / "ifc" / "_chk.mjs"
    chk.write_text(m.group(1), encoding="utf-8")
    try:
        import subprocess
        r = subprocess.run(["node", "--check", str(chk)], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
    finally:
        chk.unlink(missing_ok=True)
    assert 'if (!EMBED) {' in m.group(1)
    assert m.group(1).count("loadServerModel(lastTab)") == 1
    print("test_ifcviewer_autoload OK")
```

(опечатка `chh := chk` недопустима — использовать просто `str(chk)`.)

- [ ] **Step 3: Проверить синтаксис и прогнать**

```bash
./venv/Scripts/python.exe tests/test_threed.py
```
Expected: все OK. Деплой: `./venv/Scripts/python.exe setup_ifcviewer.py` (копирует as-is).

- [ ] **Step 4: Commit**

```bash
git commit ifc/ifcviewer.html tests/test_threed.py -m "feat(3d): автозагрузка последней модели на полной вкладке IFC (для 3D-генерации)"
```

---

### Task 6: Виджет — модалка 3D (`imagerouter/devbim_topright_buttons.js`)

**Files:**
- Modify: `imagerouter/devbim_topright_buttons.js` (клик «3D Design» вместо тоста)
- Test: `tests/test_threed.py` (статические проверки)

**Interfaces:**
- Consumes: `POST /api/v1/threed/generate {scenario:'plan', prompt, image}`,
  `__devbimCanvasBridge.getManager()` (композит), `__devbimPEStore` (выбор галереи),
  `POST /api/v1/images/images_by_names`, `localStorage['devbim:ifc:lastModel']`,
  `window.__devbimSwitchTab('ifc')`.
- Produces: модалка `#devbim-3d-modal`; RU/EN через существующий `lang`.

- [ ] **Step 1: В `TEXTS` добавить ключи 3D и заменить обработчик кнопки**

В объекты `TEXTS.ru`/`TEXTS.en` добавить:

```js
      soon3d: 'Фасад и интерьер — в разработке (фаза 2–3)',
      srcCanvas: 'Холст', srcViewer: 'Галерея',
      noSource: 'Положите картинку на Холст или выберите в галерее/вьювере',
      generate: 'Сгенерировать 3D', generating: 'Анализ модели…',
      done: 'Модель создана:', plan: 'Генплан', facade: 'Фасад', interior: 'Интерьер',
      pickScenario: 'Что генерируем?', promptPh: 'Уточнения: «жилой 5 этажей, школа 3, масштаб 0.5 м/px»',
      netErr: 'Ошибка сети/сервера'
```
```js
      soon3d: 'Facade & Interior — coming soon (phase 2-3)',
      srcCanvas: 'Canvas', srcViewer: 'Gallery',
      noSource: 'Put an image on the Canvas or select one in the viewer',
      generate: 'Generate 3D', generating: 'Analyzing the model…',
      done: 'Model created:', plan: 'Master plan', facade: 'Facade', interior: 'Interior',
      pickScenario: 'What to generate?', promptPh: 'Hints: "residential 5 floors, school 3, scale 0.5 m/px"',
      netErr: 'Network/server error'
```

В `build()` заменить `td.addEventListener('click', function () { toast(t().soon); });` на
`td.addEventListener('click', function () { open3D(); });`.

- [ ] **Step 2: Добавить блок модалки в конец IIFE (перед `if (document.readyState…`)**

```js
  // ===================== 3D Design: модалка генерации =====================
  var S3 = { scenario: 'plan', image: null, source: '', busy: false, timer: null };

  function close3D() {
    var m = document.getElementById('devbim-3d-modal');
    if (m) m.remove();
    if (S3.timer) { clearInterval(S3.timer); S3.timer = null; }
    S3.busy = false;
  }

  // Композит холста (как в E2E п.30: stage.toCanvas). null = контента нет.
  function canvasComposite() {
    var b = window.__devbimCanvasBridge;
    var m = b && b.getManager && b.getManager();
    if (!m || !m.stage || !m.stage.konva || !m.stage.konva.stage) return null;
    var ents = null;
    try { ents = window.__devbimPEStore.getState().canvas.PRESENT.entities; } catch (e) {}
    var has = false;
    (ents || []).forEach(function (en) {
      if ((en.type === 'raster_layer' || en.type === 'control_layer') &&
          (en.objects || []).length) has = true;
    });
    if (!has) return null;
    var st = m.stage.konva.stage;
    return st.toCanvas({ x: 0, y: 0, width: st.width(), height: st.height(),
                         pixelRatio: 1 }).toDataURL('image/png');
  }

  // Выбранная во вьювере картинка (последняя из selection) -> dataURL.
  async function viewerImage() {
    var st = window.__devbimPEStore;
    if (!st) return null;
    var sel = (st.getState().gallery || {}).selection || [];
    var last = sel[sel.length - 1];
    if (!last) return null;
    var name = last.image_name || (typeof last === 'string' ? last : null);
    if (!name) return null;
    var r = await fetch('/api/v1/images/images_by_names', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ image_names: [name] }) });
    if (!r.ok) return null;
    var j = await r.json();
    var dto = (Array.isArray(j) ? j : (j.images || []))[0];
    if (!dto || !dto.image_url) return null;
    var ir = await fetch(dto.image_url);
    if (!ir.ok) return null;
    var blob = await ir.blob();
    return await new Promise(function (res) {
      var fr = new FileReader();
      fr.onload = function () { res(fr.result); };
      fr.readAsDataURL(blob);
    });
  }

  async function refresh3DSource() {
    var img = document.querySelector('#devbim-3d-modal .devbim-3d-src img');
    var badge = document.querySelector('#devbim-3d-modal .devbim-3d-badge');
    var hint = document.getElementById('devbim-3d-hint');
    if (img) img.src = '';
    S3.image = canvasComposite(); S3.source = t().srcCanvas;
    if (!S3.image) {
      try { S3.image = await viewerImage(); S3.source = t().srcViewer; } catch (e) {}
    }
    if (img) img.src = S3.image || '';
    if (badge) badge.textContent = S3.image ? S3.source : '—';
    if (hint) hint.style.display = S3.image ? 'none' : 'block';
  }

  function open3D() {
    close3D();
    var ov = document.createElement('div');
    ov.id = 'devbim-3d-modal';
    ov.innerHTML =
      '<div class="devbim-3d-card">' +
      '<div class="devbim-3d-head"><b>3D Design</b><button class="devbim-3d-x" aria-label="close">✕</button></div>' +
      '<div class="devbim-3d-tiles">' +
      '<button class="devbim-3d-tile" data-s="plan"><span>🗺</span>' + t().plan + '</button>' +
      '<button class="devbim-3d-tile" data-s="facade" disabled title="' + t().soon3d + '"><span>🏢</span>' + t().facade + '</button>' +
      '<button class="devbim-3d-tile" data-s="interior" disabled title="' + t().soon3d + '"><span>🛋</span>' + t().interior + '</button>' +
      '</div>' +
      '<div class="devbim-3d-src"><img alt=""><span class="devbim-3d-badge">—</span></div>' +
      '<div id="devbim-3d-hint" style="display:none">' + t().noSource + '</div>' +
      '<textarea id="devbim-3d-prompt" rows="3" placeholder="' + t().promptPh + '"></textarea>' +
      '<button id="devbim-3d-go">' + t().generate + '</button>' +
      '<div id="devbim-3d-status"></div>' +
      '</div>';
    document.body.appendChild(ov);
    ov.addEventListener('click', function (e) { if (e.target === ov) close3D(); });
    ov.querySelector('.devbim-3d-x').addEventListener('click', close3D);
    ov.querySelectorAll('.devbim-3d-tile').forEach(function (b) {
      b.addEventListener('click', function () {
        S3.scenario = b.getAttribute('data-s');
        ov.querySelectorAll('.devbim-3d-tile').forEach(function (x) { x.classList.remove('on'); });
        b.classList.add('on');
      });
    });
    ov.querySelector('.devbim-3d-tile').classList.add('on');
    document.getElementById('devbim-3d-go').addEventListener('click', run3D);
    document.addEventListener('keydown', function esc(e) {
      if (e.key === 'Escape') { close3D(); document.removeEventListener('keydown', esc); }
    });
    refresh3DSource();
  }

  async function run3D() {
    if (S3.busy || !S3.image) { if (!S3.image) toast(t().noSource); return; }
    var go = document.getElementById('devbim-3d-go');
    var stEl = document.getElementById('devbim-3d-status');
    S3.busy = true; go.disabled = true; go.textContent = t().generating;
    var t0 = Date.now();
    S3.timer = setInterval(function () {
      stEl.textContent = '⏳ ' + Math.round((Date.now() - t0) / 1000) + ' s';
    }, 500);
    try {
      var r = await fetch('/api/v1/threed/generate', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scenario: S3.scenario,
                               prompt: (document.getElementById('devbim-3d-prompt').value || '').trim(),
                               image: S3.image })
      });
      var j = null; try { j = await r.json(); } catch (e) {}
      if (!r.ok) throw new Error((j && (j.detail || j.message)) || ('HTTP ' + r.status));
      if (j.warnings && j.warnings.length) toast(j.warnings.join(' · '));
      try { localStorage.setItem('devbim:ifc:lastModel', j.name); } catch (e) {}
      close3D();
      if (window.__devbimSwitchTab) window.__devbimSwitchTab('ifc');
      toast(t().done + ' ' + j.name);
    } catch (e) {
      S3.busy = false; go.disabled = false; go.textContent = t().generate;
      if (S3.timer) { clearInterval(S3.timer); S3.timer = null; }
      stEl.textContent = (e && e.message) || t().netErr;
    }
  }
```

- [ ] **Step 3: Добавить CSS в строку `CSS` виджета**

```js
    '#devbim-3d-modal{position:fixed;inset:0;background:rgba(0,0,0,.55);z-index:3000;' +
    'display:flex;align-items:center;justify-content:center}' +
    '.devbim-3d-card{width:400px;max-width:92vw;background:#1d2126;color:#e8ebee;' +
    'border:1px solid #2b2f35;border-radius:8px;padding:14px;display:flex;flex-direction:column;gap:10px;' +
    "font:500 13px/1.4 Inter,'Segoe UI',system-ui,sans-serif}" +
    '.devbim-3d-head{display:flex;justify-content:space-between;align-items:center}' +
    '.devbim-3d-x{background:none;border:none;color:#9aa3ad;font-size:15px;cursor:pointer}' +
    '.devbim-3d-tiles{display:flex;gap:8px}' +
    '.devbim-3d-tile{flex:1;display:flex;flex-direction:column;align-items:center;gap:4px;' +
    'padding:8px 4px;border:1px solid #2b2f35;border-radius:6px;background:#22262c;color:#e8ebee;' +
    'cursor:pointer;font:600 12px/1.2 inherit}' +
    '.devbim-3d-tile.on{border-color:#A78BFA;background:#2a2438}' +
    '.devbim-3d-tile:disabled{opacity:.45;cursor:default}' +
    '.devbim-3d-src{position:relative;border:1px dashed #2b2f35;border-radius:6px;overflow:hidden;' +
    'height:150px;display:flex;align-items:center;justify-content:center;background:#14161a}' +
    '.devbim-3d-src img{max-width:100%;max-height:100%;object-fit:contain}' +
    '.devbim-3d-badge{position:absolute;top:6px;left:6px;background:#000a;color:#cfd6dd;' +
    'border-radius:4px;padding:2px 7px;font-size:11px}' +
    '#devbim-3d-hint{color:#f0b429;font-size:12px}' +
    '#devbim-3d-prompt{background:#14161a;color:#e8ebee;border:1px solid #2b2f35;' +
    'border-radius:6px;padding:8px;resize:vertical;font:inherit}' +
    '#devbim-3d-go{height:36px;border:none;border-radius:4px;background:#A78BFA;color:#0B0C0E;' +
    'font:600 13px/1 inherit;cursor:pointer}' +
    '#devbim-3d-go:disabled{opacity:.55;cursor:default}' +
    '#devbim-3d-status{min-height:16px;font-size:12px;color:#9aa3ad}'
```

- [ ] **Step 4: Статические тесты** (добавить в `tests/test_threed.py`):

```python
def test_widget_3d_modal():
    src = (ROOT / "imagerouter" / "devbim_topright_buttons.js").read_text(encoding="utf-8")
    import subprocess
    r = subprocess.run(["node", "--check",
                        str(ROOT / "imagerouter" / "devbim_topright_buttons.js")],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    for marker in ("/api/v1/threed/generate", "__devbimSwitchTab('ifc')",
                   "devbim:ifc:lastModel", "images_by_names", "open3D()"):
        assert marker in src, marker
    assert "toast(t().soon)" not in src.split("function build()")[1].split("function isYellow")[0]
    print("test_widget_3d_modal OK")
```

(последний ассерт: клик 3D больше не заглушка-тост — в блоке build() осталось только
`open3D()`; строка-заглушка удалена.)

- [ ] **Step 5: Прогнать тесты, деплой виджета**

```bash
./venv/Scripts/python.exe tests/test_threed.py
./venv/Scripts/python.exe setup_imagerouter.py   # deploy_topright_buttons скопирует виджет
```

- [ ] **Step 6: Commit**

```bash
git commit imagerouter/devbim_topright_buttons.js tests/test_threed.py -m "feat(3d): модалка 3D Design в виджете (сценарий/промт/источник, прогресс, переход в IFC)"
```

---

### Task 7: Админ-секция «3D» в imagerouter.html

**Files:**
- Modify: `imagerouter/imagerouter.html` (новая `<section>` после `#upsec`)
- Test: `tests/test_threed.py` (статика)

**Interfaces:**
- Consumes: `GET/PUT /api/v1/threed/model` (обычный fetch — это НЕ imagerouter-префикс!).
- Produces: селектор `#threed-model` + кнопка Save.

- [ ] **Step 1: Разметка — после `</section>` секции `#upsec` вставить**

```html
  <section id="threedsec">
    <h2>3D-генерация — модель аналитики</h2>
    <p class="hint">VLM, которая анализирует картинку и строит JSON-сцену для 3D
      (кнопка «3D Design»). Список — только модели с входом «изображение» и
      текстовым выходом. После смены — F5 не нужен (читается при генерации).</p>
    <div class="row">
      <select id="threed-model" style="min-width:280px"></select>
      <button id="threed-save">Сохранить</button>
    </div>
    <div id="threed-status" class="hint"></div>
  </section>
```

- [ ] **Step 2: JS — рядом с инициализацией других секций (в конец скрипта)**

```js
  // --- 3D-генерация: выбор VLM-аналитика (GET/PUT /api/v1/threed/model) ---
  (function () {
    var sel = $("threed-model"), st = $("threed-status");
    fetch("/api/v1/threed/model").then(function (r) { return r.json(); }).then(function (d) {
      sel.innerHTML = "";
      (d.vlms || []).forEach(function (m) {
        var o = document.createElement("option");
        o.value = m.id; o.textContent = m.id;
        sel.appendChild(o);
      });
      if (!(d.vlms || []).some(function (m) { return m.id === d.model; })) {
        var o = document.createElement("option");
        o.value = d.model; o.textContent = d.model + " (не в каталоге)";
        sel.appendChild(o);
      }
      sel.value = d.model;
      st.textContent = "Источник: " + (d.source === "file" ? "сохранённый выбор" :
        d.source === "env" ? ".env THREED_MODEL" : "по умолчанию");
    }).catch(function () { st.textContent = "Не удалось загрузить список VLM"; });
    $("threed-save").addEventListener("click", function () {
      st.textContent = "Сохранение…";
      fetch("/api/v1/threed/model", {
        method: "PUT", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ model: sel.value })
      }).then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }); })
        .then(function (res) {
          st.textContent = res.ok ? "Сохранено: " + sel.value :
            "Ошибка: " + (res.j.detail || "?");
        }).catch(function () { st.textContent = "Ошибка сети"; });
    });
  })();
```

- [ ] **Step 3: Статический тест + деплой**

```python
def test_admin_threed_section():
    src = (ROOT / "imagerouter" / "imagerouter.html").read_text(encoding="utf-8")
    assert 'id="threedsec"' in src
    assert "/api/v1/threed/model" in src
    assert 'id="threed-save"' in src
    print("test_admin_threed_section OK")
```
```bash
./venv/Scripts/python.exe tests/test_threed.py
./venv/Scripts/python.exe setup_imagerouter.py   # переразвернёт imagerouter.html
```

- [ ] **Step 4: Commit**

```bash
git commit imagerouter/imagerouter.html tests/test_threed.py -m "feat(3d): админ-секция выбора VLM-аналитика в менеджере"
```

---

### Task 8: Деплой + рестарт + проверка API

**Files:** изменений в git нет (кроме возможных правок по итогам).

- [ ] **Step 1: Применить всё и перезапустить сервер**

```bash
./venv/Scripts/python.exe setup_threed.py
./venv/Scripts/python.exe setup_ifcviewer.py
./venv/Scripts/python.exe setup_imagerouter.py
powershell -ExecutionPolicy Bypass -File _restart_server.ps1
```

- [ ] **Step 2: Проверить API (ждать ~40 с после старта)**

```bash
curl -s http://127.0.0.1:9090/api/v1/threed/model
```
Expected: `{"model":"openai/gpt-6-astra","source":"default","vlms":[…id……]}` — в списке
есть `openai/gpt-6-astra` (если каталог недоступен — `vlms:[]`, это не ошибка).

```bash
curl -s -X PUT http://127.0.0.1:9090/api/v1/threed/model -H "Content-Type: application/json" -d "{\"model\":\"no/such\"}"
```
Expected: `{"detail":"Модель no/such не VLM или отсутствует в каталоге"}` (HTTP 422).

- [ ] **Step 3: Живой smoke генерации (~$0.05–0.15)**

```bash
./venv/Scripts/python.exe -c "
import base64, io, json, urllib.request
from PIL import Image, ImageDraw
img = Image.new('RGB', (800, 600), (245, 245, 240))
d = ImageDraw.Draw(img)
d.rectangle([100, 100, 500, 300], fill=(180, 180, 175))   # большой корпус
d.rectangle([100, 400, 300, 550], fill=(200, 160, 120))   # школа поменьше
buf = io.BytesIO(); img.save(buf, format='PNG')
body = json.dumps({'scenario': 'plan', 'prompt': 'residential 5 floors, school 3 floors',
                   'image': 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode()}).encode()
req = urllib.request.Request('http://127.0.0.1:9090/api/v1/threed/generate', data=body,
                             headers={'Content-Type': 'application/json'})
print(urllib.request.urlopen(req, timeout=300).read().decode())
"
```
Expected: `{"name":"3D_plan_….ifc","warnings":[…]}`. Затем
`curl -s http://127.0.0.1:9090/api/v1/ifc/list` — модель в списке; файл и `_preview.png`
лежат в `data/ifc/`, дамп — `data/_threed_last.json`. Посмотреть превью глазами (Read):
обводки легли на прямоугольники.

---

### Task 9: E2E (Playwright, живой сервер)

**Files:** — чек-лист (браузерная проверка, как E2E п.34/35).

- [ ] **Step 1: Пройти чек-лист в браузере (после F5)**

1. Вкладка «Generate»: слева в ряду Generate — группа кнопок; клик «3D Design» → модалка
   (плитки Генплан активна, Фасад/Интерьер disabled с подсказкой «в разработке»).
2. Пустой источник: под превью подсказка «Положите картинку…», Generate кликабелен, но
   по клику — тост-подсказка (не запрос).
3. Положить генплан-картинку на «Холст» (или выбрать картинку в галерее) → открыть модалку →
   превью с бейджем «Холст»/«Галерея».
4. Ввести промт «жилой 5 этажей, школа 3 этажа» → Generate → таймер секунд; ответ ≤2 мин →
   модалка закрылась, тост «Модель создана: 3D_plan_….ifc», приложение на вкладке IFC,
   модель ЗАГРУЖЕНА (3D-вид виден), имя — в селекторе шапки вкладки.
5. Клик по зданию — панель свойств: pset DevBIM (Scenario=plan, Prompt, Model) и
   SiteMassing (этажи). «👤» → клик по земле → человек стоит (snapToGround на наш Ground);
   «Вид от глаз» — камера 1,7 м.
6. 📸 To Canvas → снимок на холсте (штатный цикл).
7. Ошибки: недоступный каталог (PUT no/such уже проверен curl-ом) — в модалке строка ошибки.
8. Консоль браузера — без ошибок (допустим только ожидаемый 404/422 при намеренных ошибках).

- [ ] **Step 2: Скриншоты в `docs/`**

`docs/3d-design-modal.png`, `docs/3d-design-ifc-result.png` (модалка с превью; вкладка IFC
с загруженной моделью + человек/снимок).

---

### Task 10: Документация + финальный коммит

**Files:**
- Modify: `HANDOFF.md` (п.37), `README.md` (раздел «3D Design»), `AGENTS.md` (порядок setup: `… → setup_designcode.py → setup_threed.py → …`), `docs/superpowers/specs/2026-09-18-3d-design-ifc-generation-design.md` (пометка «фаза 1 реализована», превью — только обводки-оверлей).

- [ ] **Step 1: HANDOFF.md — добавить п.37** по образцу соседних: что сделано (конвейер,
  файлы, грабли: image-only фильтр каталога, идемпотентность, F5), отладка
  (`data/_threed_last.json`, `window.__devbimPEStore`, `_threed_tmp`), тест
  `tests/test_threed.py`, порядок setup, стоимость прогона.
- [ ] **Step 2: README.md — раздел «3D Design»** (пользовательский: кнопка → модалка →
  сценарий → промт → модель в IFC-вьювере → человек/снимок/референсы — цикл из спеки).
- [ ] **Step 3: AGENTS.md — порядок setup-скриптов** добавить `setup_threed.py` после
  `setup_designcode.py`; перечислить `threed/` в «Где что».
- [ ] **Step 4: Полный прогон тестов и коммит**

```bash
./venv/Scripts/python.exe tests/test_threed.py
./venv/Scripts/python.exe tests/test_designcode.py
./venv/Scripts/python.exe tests/test_topright_buttons.py
git commit HANDOFF.md README.md AGENTS.md docs/superpowers/specs/2026-09-18-3d-design-ifc-generation-design.md -m "docs: 3D Design фаза 1 — HANDOFF п.37, README, AGENTS, спека"
```

---

## Самопроверка (выполнена при написании плана)

- Спека-фаза-1 покрыта: конвейер (T3, T6), менеджер (T3, T7), генплан-схема (T2),
  сборщик (T1), автозагрузка (T5), деплой (T4), проверка/E2E (T8, T9), docs (T10).
- Планы фаз 2 (фасад) и 3 (интерьер-план) — отдельные документы после фазы 1.
- Известное упрощение против спеки: превью — только обводки-оверлей (`_preview.png`),
  без matplotlib-3D-превью (3D-вид даёт вьювер); отражено в Task 10 (правка спеки).
