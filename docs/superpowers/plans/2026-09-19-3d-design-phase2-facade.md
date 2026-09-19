# 3D Design — фаза 2 (сценарий «Фасад») Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Плитка «Фасад» в модалке 3D Design становится активной: фото/рендер фасада или чертёж фасада → VLM (та же модель-аналитик) → JSON-сцена ВСЯ В МЕТРАХ (этажи, окна сеткой с пропусками, балконы, крыша, цвета) → сборщик `build_facade` пишет IFC4 (поэтажные объёмы, тёмные «стеклопакеты» заподлицо с фасадом, плиты-балконы, цоколь, двускатная призма) + превью-чертёж фасада → автозагрузка во вкладке IFC (штатная из фазы 1).

**Architecture:** Расширение конвейера фазы 1 без изменений его контрактов: `threed_scenarios` (+`SYSTEM_FACADE`, +`validate_facade` — метрическая схема, клампы/дефолты/warnings), `threed_build` (+`build_facade` — бокс-тома по этажам + сетка окон + балконы/цоколь/крыша, pset `FacadeModel`), `threed_router` (SCENARIOS + ветвление системы/валидатора/сборщика), виджет (плитка фасада активна, placeholder промта по сценарию). Деплой — существующий `setup_threed.py` (копирует файлы as-is) + `setup_imagerouter.py` (виджет).

**Tech Stack:** Python 3.11 (venv InvokeAI), ifcopenshell + shapely + matplotlib + numpy (уже стоят), FastAPI; JS — правка существующего виджета.

## Global Constraints

- Windows, Git Bash; python — всегда `./venv/Scripts/python.exe` из корня проекта
  `C:\Users\Lenovo\Desktop\проект SOFT_2\Дизайн\InvokeAI\InvokeAI` (ветка `3d`).
- Тесты — plain asserts + печать OK (НЕ pytest): `venv\Scripts\python.exe tests\test_threed.py`.
- В `venv/Lib/site-packages` руками не править — только через setup-скрипты (все идемпотентны).
- Коммитить нельзя: `.env`, `companies.json`, `companies/*`. В индексе застейджен чужой WIP
  (`design_code/design_code_viewer.html`, `tests/test_designcode.py`) — коммитить ТОЧЕЧНО через
  `git add <файлы задачи> && git commit <файлы задачи> -m ...` (pathspec), никогда `git add -A`/`.`/`-a`.
- Схема фасада — ВСЯ В МЕТРАХ (никаких пиксельных координат; у фасада нет привязанных
  к картинке полигонов, сетка окон описывается параметрически) — спека, раздел «Сценарий Фасад».
- VLM: тот же конвейер, что в фазе 1 (max_tokens 8000, temperature 0.2, PNG ≤1536, 1 ретрай).
- Модель-аналитик/модальности/менеджер — НЕ меняем (фаза 1 работает).
- Файлы генерации: `3D_facade_<ГГГГММДД-ЧЧММСС>.ifc` + `<имя>_preview.png` в `root_path/ifc`;
  дамп `root_path/ifc/_threed_last.json` — как в фазе 1.
- Сервер перезапускать только `_restart_server.ps1`; после деплоя JS пользователю нужен F5.
- Живые запросы к Astra ~$0.05–0.15 за генерацию: smoke (Task 5) один раз + E2E (Task 6) один раз.
- УРОК ФАЗЫ 1 (обязателен к учёту): статика и node --check не ловят рантайм-имена и форму
  redux-стейта — каждый шаг, читающий чужие структуры, обязан проверять их вживую или
  копировать эталонный паттерн дословно.

## File Structure

```
threed/threed_scenarios.py   — ДОБАВИТЬ: SYSTEM_FACADE, validate_facade (правка существующего)
threed/threed_build.py       — ДОБАВИТЬ: ASSUMPTION_FACADE, FACADE_DEFAULT_COLORS,
                                build_facade, _draw_facade_preview, _write_header (правка)
threed/threed_router.py      — ДОБАВИТЬ: "facade" в SCENARIOS, ветвление (правка)
imagerouter/devbim_topright_buttons.js — плитка фасада активна, placeholder по сценарию (правка)
tests/test_threed.py         — +4 тест-функции, правка __main__ и test_widget_3d_modal
setup_threed.py, setup_imagerouter.py, ifc/ifcviewer.html — БЕЗ ИЗМЕНЕНИЙ (деплой as-is)
```

---

### Task 1: Сборщик фасада `build_facade` (`threed/threed_build.py`)

**Files:**
- Modify: `threed/threed_build.py` (дописать в конец модуля; существующий код genplan НЕ трогать)
- Test: `tests/test_threed.py` (дополнить)

**Interfaces:**
- Produces: `build_facplan` — ВНИМАНИЕ, имя именно `build_facade(scene: dict, ifc_path: Path,
  preview_path: Path, meta: dict) -> Path`. Сцена — dict метрической схемы (см. тест):
  `storeys, floor_height, width_m, depth_m, roof ("flat"|"gable"), roof_height, windows
  {rows, cols, w_m, h_m, margin_x_m, margin_y_m, skip[][]}, balconies [{floor, x_m, w_m, d_m}],
  colors {walls, roof, plinth}` (validate_facade из Task 2 гарантирует клампы). `meta` —
  `{Scenario, Prompt, Model, Source}` для pset `DevBIM` у IfcProject (как в genplan).
  Пишет `ifc_path` (IFC4) и `preview_path` (PNG-чертёж фасада), возвращает `ifc_path`.
- Также produces (module-level): `_write_header(model, ifc_path)` — общая шапка STEP-файла
  (используется только build_facade; build_genplan не трогаем), `_draw_facade_preview(data, preview_path)`.

- [ ] **Step 1: Failing-тест** — добавить в `tests/test_threed.py` после `sample_scene()` (до
  `test_build_genplan`):

```python
def sample_facade_scene():
    """Фасад: 5 эт. × 3.0 м, 24×12 м, двускатная крыша 2.5 м, окна 1 ряд по 4
    (второе пропущено на всех этажах), балконы на 2 и 3 этаже."""
    return {
        "storeys": 5, "floor_height": 3.0, "width_m": 24.0, "depth_m": 12.0,
        "roof": "gable", "roof_height": 2.5,
        "windows": {"rows": 1, "cols": 4, "w_m": 1.5, "h_m": 1.5,
                    "margin_x_m": 1.0, "margin_y_m": 0.7,
                    "skip": [[False, True, False, False]]},
        "balconies": [{"floor": 2, "x_m": 4.0, "w_m": 3.0, "d_m": 1.2},
                      {"floor": 3, "x_m": 4.0, "w_m": 3.0, "d_m": 1.2}],
        "colors": {"walls": "#d9c7a7", "roof": "#52616b", "plinth": "#8d8d8d"},
    }


def test_build_facade():
    import ifcopenshell
    from threed.threed_build import build_facade

    TMP.mkdir(exist_ok=True)
    ifc = TMP / "3D_facade_test.ifc"
    prev = TMP / "3D_facade_test_preview.png"
    path = build_facade(sample_facade_scene(), ifc, prev,
                        {"Scenario": "facade", "Prompt": "тест", "Model": "test/model",
                         "Source": "3D Design"})
    assert path == ifc and ifc.is_file() and prev.is_file()

    m = ifcopenshell.open(str(ifc))
    assert m.schema == "IFC4"
    gids = [r.GlobalId for r in m.by_type("IfcRoot")]
    assert len(gids) == len(set(gids)), "GlobalId не уникальны"
    assert len(m.by_type("IfcBuilding")) == 1
    assert len(m.by_type("IfcBuildingStorey")) == 5
    proxies = m.by_type("IfcBuildingElementProxy")
    by_type = {}
    for p in proxies:
        by_type[p.ObjectType] = by_type.get(p.ObjectType, 0) + 1
    assert by_type.get("CONCEPTUAL_STOREY") == 5            # поэтажные тома
    assert by_type.get("CONCEPTUAL_WINDOW") == 3 * 5        # 4 минус skip, на этаж
    assert by_type.get("CONCEPTUAL_BALCONY") == 2
    assert by_type.get("CONCEPTUAL_PLINTH") == 1
    assert by_type.get("CONCEPTUAL_ROOF") == 1              # двускатная призма
    # этажи на своих отметках
    elev = sorted(s.Elevation for s in m.by_type("IfcBuildingStorey"))
    assert elev == [0.0, 3.0, 6.0, 9.0, 12.0]
    # объём первого этажа: 24 × 12 × 3 = 864 м³
    from ifcopenshell.util.element import get_psets
    storey1 = [p for p in proxies if p.ObjectType == "CONCEPTUAL_STOREY"][0]
    qto = get_psets(storey1).get("Qto_BuildingElementProxyQuantities", {})
    assert abs(qto.get("NetVolume", 0) - 24 * 12 * 3.0) < 1.0
    # pset DevBIM у проекта + FacadeModel у здания
    assert get_psets(m.by_type("IfcProject")[0]).get("DevBIM", {}).get("Scenario") == "facade"
    b = m.by_type("IfcBuilding")[0]
    fm = get_psets(b).get("FacadeModel", {})
    assert fm.get("Storeys") == 5 and fm.get("WindowsTotal") == 15
    print("test_build_facade OK")
```

- [ ] **Step 2: Запустить — упасть**

Run: `./venv/Scripts/python.exe tests/test_threed.py`
Expected: `ImportError: cannot import name 'build_facade'` (RED).

- [ ] **Step 3: Написать код — добавить в конец `threed/threed_build.py`**

```python
# ===================== Фаза 2: сценарий «Фасад» =====================

ASSUMPTION_FACADE = (
    "Концептуальная модель по изображению фасада (3D Design). Перспектива принята "
    "за ортогональную, глубина здания и толщины оценочные. Окна и балконы — схематичные "
    "объёмы. Не использовать как обмерную или рабочую документацию."
)

FACADE_DEFAULT_COLORS = {
    "walls": "#c8b89a", "roof": "#52616b", "plinth": "#8d8d8d",
    "glazing": "#202830", "balcony": "#9aa3ad",
}


def _write_header(model, ifc_path):
    """Шапка STEP-файла (как у genplan; вынесено для build_facade)."""
    model.header.file_name.name = ifc_path.name
    model.header.file_name.author = ("3D Design",)
    model.header.file_name.organization = ("DevBIM",)
    model.header.file_name.preprocessor_version = f"IfcOpenShell {ifcopenshell.version}"
    model.header.file_name.originating_system = "DevBIM 3D Design (VLM scene -> IFC)"
    model.header.file_name.authorization = "Approximate model; not construction documentation"


def _facade_grid(data):
    """Левые края окон по X (метры, от -w/2) и по Z внутри этажа; одинаково для всех этажей."""
    win, w, fh = data["windows"], data["width_m"], data["floor_height"]
    usable_w = w - 2 * win["margin_x_m"]
    gap_x = (usable_w - win["cols"] * win["w_m"]) / (win["cols"] - 1) \
        if win["cols"] > 1 else 0.0
    xs = [-w / 2 + win["margin_x_m"] + i * (win["w_m"] + max(gap_x, 0.0))
          for i in range(win["cols"])]
    usable_h = fh - 2 * win["margin_y_m"]
    gap_y = (usable_h - win["rows"] * win["h_m"]) / (win["rows"] - 1) \
        if win["rows"] > 1 else 0.0
    zs = [win["margin_y_m"] + j * (win["h_m"] + max(gap_y, 0.0))
          for j in range(win["rows"])]
    return xs, zs


def _window_skip(data):
    """skip[j][i] (True = окна нет); нормализован validate_facade до rows×cols."""
    return data["windows"].get("skip") or []


def build_facade(scene, ifc_path, preview_path, meta):
    """Сцена-метрики фасада -> IFC4 + PNG-чертёж фасада. Возвращает ifc_path."""
    data = dict(scene)
    data.setdefault("storeys", 5)
    data.setdefault("floor_height", 3.0)
    data.setdefault("width_m", 18.0)
    data.setdefault("depth_m", 12.0)
    data.setdefault("roof", "flat")
    data.setdefault("roof_height", 2.5)
    data.setdefault("windows", {})
    data.setdefault("balconies", [])
    win = {"rows": 1, "cols": 3, "w_m": 1.5, "h_m": 1.5,
           "margin_x_m": 1.0, "margin_y_m": 0.8}
    win.update({k: v for k, v in (data["windows"] or {}).items() if k != "skip"})
    win["skip"] = (data["windows"] or {}).get("skip") or []
    data["windows"] = win
    colors = dict(FACADE_DEFAULT_COLORS)
    colors.update({k: v for k, v in (scene.get("colors") or {}).items() if k in colors})

    model = _api("project.create_file", version="IFC4")
    project = _api("root.create_entity", file=model, ifc_class="IfcProject",
                   name=data.get("project_name", "3D Design — фасад"))
    project.Description = ASSUMPTION_FACADE
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
        "Source": meta.get("Source", "3D Design"), "Scenario": meta.get("Scenario", "facade"),
        "Prompt": (meta.get("Prompt") or "")[:1024], "Model": meta.get("Model", ""),
        "ApproximateGeometry": True, "Notes": ASSUMPTION_FACADE,
    })
    building = _api("root.create_entity", file=model, ifc_class="IfcBuilding",
                    name=data.get("building_name", "Здание по фасаду"))
    building.Description = ASSUMPTION_FACADE
    _api("aggregate.assign_object", file=model, products=[building], relating_object=site)
    _api("geometry.edit_object_placement", file=model, product=building, matrix=np.eye(4))

    fstyles = {}
    for key, color in colors.items():
        r, g, b = matplotlib.colors.to_rgb(color)
        style = _api("style.add_style", file=model, name=f"Facade{key.capitalize()}")
        _api("style.add_surface_style", file=model, style=style,
             ifc_class="IfcSurfaceStyleShading",
             attributes={"SurfaceColour": {"Name": key, "Red": r, "Green": g, "Blue": b},
                         "Transparency": 0.0})
        fstyles[key] = style

    w, d, fh, n = data["width_m"], data["depth_m"], data["floor_height"], data["storeys"]

    def box(name, bw, bd, bh, cx, cy, z, color_key, container,
            object_type="CONCEPTUAL_MASS"):
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
        matrix[:3, 3] = [float(cx), float(cy), float(z)]
        _api("geometry.edit_object_placement", file=model, product=product, matrix=matrix)
        _api("style.assign_representation_styles", file=model,
             shape_representation=representation, styles=[fstyles[color_key]])
        return product

    storeys = []
    for f in range(n):
        storey = _api("root.create_entity", file=model, ifc_class="IfcBuildingStorey",
                      name=f"Этаж {f + 1:02d}")
        storey.Elevation = f * fh
        _api("aggregate.assign_object", file=model, products=[storey], relating_object=building)
        matrix = np.eye(4)
        matrix[2, 3] = storey.Elevation
        _api("geometry.edit_object_placement", file=model, product=storey, matrix=matrix)
        storeys.append(storey)

    windows_total = 0
    xs, zs = _facade_grid(data)
    skip = _window_skip(data)
    for f in range(n):
        box(f"Стены · этаж {f + 1}", w, d, fh, 0.0, 0.0, f * fh, "walls", storeys[f],
            object_type="CONCEPTUAL_STOREY")
        for j, z_in in enumerate(zs):
            for i, x in enumerate(xs):
                if j < len(skip) and i < len(skip[j]) and skip[j][i]:
                    continue
                box(f"Окно Э{f + 1}-{i + 1}", win["w_m"], 0.12, win["h_m"],
                    x + win["w_m"] / 2, d / 2 - 0.06, f * fh + z_in, "glazing",
                    storeys[f], object_type="CONCEPTUAL_WINDOW")
                windows_total += 1
    for b_idx, bal in enumerate(data["balconies"], start=1):
        box(f"Балкон {b_idx} · этаж {bal['floor']}", bal["w_m"], bal["d_m"], 0.18,
            bal["x_m"], d / 2 + bal["d_m"] / 2, bal["floor"] * fh - 0.18, "balcony",
            storeys[bal["floor"] - 1], object_type="CONCEPTUAL_BALCONY")
    box("Цоколь", w + 0.2, d + 0.2, 0.6, 0.0, 0.0, 0.0, "plinth", building,
        object_type="CONCEPTUAL_PLINTH")
    if data["roof"] == "gable" and data["roof_height"] > 0.05:
        gable = _api("root.create_entity", file=model, ifc_class="IfcBuildingElementProxy",
                     predefined_type="USERDEFINED", name="Крыша двускатная")
        gable.ObjectType = "CONCEPTUAL_ROOF"
        pts = [[-w / 2, 0.0], [w / 2, 0.0], [0.0, data["roof_height"]]]
        profile = _api("profile.add_arbitrary_profile", file=model, profile=pts,
                       name="Крыша двускатная")
        representation = _api("geometry.add_profile_representation", file=model, context=body,
                              profile=profile, depth=d, cardinal_point=None)
        _api("geometry.assign_representation", file=model, product=gable,
             representation=representation)
        _api("spatial.assign_container", file=model, products=[gable],
             relating_structure=building)
        # локальная X -> мировая X; локальная Y (высота профиля) -> мировая Z;
        # выдавливание (+Z локали) -> -Y (от лицевой грани вглубь), origin на грани
        matrix = np.array([
            [1.0, 0.0, 0.0, 0.0],
            [0.0, 0.0, -1.0, d / 2],
            [0.0, 1.0, 0.0, n * fh],
            [0.0, 0.0, 0.0, 1.0],
        ])
        _api("geometry.edit_object_placement", file=model, product=gable, matrix=matrix)
        _api("style.assign_representation_styles", file=model,
             shape_representation=representation, styles=[fstyles["roof"]])

    _properties(model, building, "FacadeModel", {
        "Storeys": n, "FloorHeight": fh, "WidthM": w, "DepthM": d,
        "Roof": data["roof"], "RoofHeight": data["roof_height"] if data["roof"] == "gable" else 0.0,
        "WindowsTotal": windows_total, "BalconiesCount": len(data["balconies"]),
        "OrthoAssumption": True, "DepthAssumed": True,
        "Source": "3D Design", "Notes": ASSUMPTION_FACADE,
    })
    for f in range(n):
        qto = _api("pset.add_qto", file=model,
                   product=[p for p in model.by_type("IfcBuildingElementProxy")
                            if p.ObjectType == "CONCEPTUAL_STOREY"][f],
                   name="Qto_BuildingElementProxyQuantities")
        _api("pset.edit_qto", file=model, qto=qto, properties={
            "NetVolume": float(w * d * fh)})

    _write_header(model, ifc_path)
    ifc_path.parent.mkdir(parents=True, exist_ok=True)
    model.write(str(ifc_path))
    _draw_facade_preview(data, preview_path)
    return ifc_path


def _draw_facade_preview(data, preview_path):
    """Чертёж фасада (метры): стены, цоколь, сетка окон, балконы, крыша."""
    colors = dict(FACADE_DEFAULT_COLORS)
    colors.update({k: v for k, v in (data.get("colors") or {}).items() if k in colors})
    w, fh, n = data["width_m"], data["floor_height"], data["storeys"]
    H = n * fh
    fig, ax = plt.subplots(figsize=(12, 7), facecolor="white")
    ax.add_patch(PlotPolygon([[-w / 2, 0], [w / 2, 0], [w / 2, H], [-w / 2, H]],
                             facecolor=colors["walls"], edgecolor="#263747", linewidth=1.2))
    ax.add_patch(PlotPolygon([[-w / 2 - 0.1, 0], [w / 2 + 0.1, 0],
                              [w / 2 + 0.1, 0.6], [-w / 2 - 0.1, 0.6]],
                             facecolor=colors["plinth"], edgecolor="#263747", linewidth=1.0))
    xs, zs = _facade_grid(data)
    skip = _window_skip(data)
    win = data["windows"]
    for j, z_in in enumerate(zs):
        for i, x in enumerate(xs):
            if j < len(skip) and i < len(skip[j]) and skip[j][i]:
                continue
            for f in range(n):
                ax.add_patch(PlotPolygon(
                    [[x, f * fh + z_in], [x + win["w_m"], f * fh + z_in],
                     [x + win["w_m"], f * fh + z_in + win["h_m"]],
                     [x, f * fh + z_in + win["h_m"]]],
                    facecolor=colors["glazing"], edgecolor="white", linewidth=0.7))
    for b_idx, bal in enumerate(data["balconies"], start=1):
        ax.add_patch(PlotPolygon(
            [[bal["x_m"] - bal["w_m"] / 2, bal["floor"] * fh - 1.0],
             [bal["x_m"] + bal["w_m"] / 2, bal["floor"] * fh - 1.0],
             [bal["x_m"] + bal["w_m"] / 2, bal["floor"] * fh],
             [bal["x_m"] - bal["w_m"] / 2, bal["floor"] * fh]],
            facecolor="none", edgecolor=colors["balcony"], hatch="////", linewidth=1.2))
        ax.text(bal["x_m"], bal["floor"] * fh - 0.5, f"Б{b_idx}", ha="center", va="center",
                fontsize=7, color="#15232e")
    top = H
    if data["roof"] == "gable":
        ax.add_patch(PlotPolygon([[-w / 2, H], [w / 2, H], [0, H + data["roof_height"]]],
                                 facecolor=colors["roof"], edgecolor="#263747", alpha=.9))
        top = H + data["roof_height"]
    for f in range(1, n):
        ax.plot([-w / 2, w / 2], [f * fh, f * fh], color="#263747", linewidth=.5,
                linestyle="--", alpha=.5)
    for i, x in enumerate(xs):
        ax.text(x + win["w_m"] / 2, -0.9, f"О{i + 1}", ha="center", va="center",
                fontsize=7, color="#15232e")
    ax.set_xlim(-w / 2 - 1.5, w / 2 + 1.5)
    ax.set_ylim(-1.5, top + 1.0)
    ax.set_aspect("equal")
    ax.axis("off")
    dp = data["depth_m"]
    ax.set_title(f"3D Design — фасад: {n} эт. × {fh:g} м, {w:g}×{dp:g} м, "
                 f"крыша {data['roof']}", fontsize=13)
    fig.tight_layout()
    preview_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(preview_path, dpi=160, facecolor="white")
    plt.close(fig)
```

- [ ] **Step 4: Запустить тест — PASS**

Run: `./venv/Scripts/python.exe tests/test_threed.py`
Expected: `test_build_facade OK` + прежние OK + `ALL OK`.
Затем открыть глазами превью `tests/_threed_tmp/3D_facade_test_preview.png` (Read) —
стены/цоколь/15 тёмных окон/2 штрихованных балкона/треугольник крыши на месте.

- [ ] **Step 5: Commit**

```bash
git add threed/threed_build.py tests/test_threed.py
git commit threed/threed_build.py tests/test_threed.py -m "feat(3d): сборщик IFC4 фасада (тома-этажи, окна-сетка с skip, балконы, цоколь, двускатная крыша) + чертёж-превью"
```

---

### Task 2: Сценарий «Фасад»: системный промпт + `validate_facade` (`threed/threed_scenarios.py`)

**Files:**
- Modify: `threed/threed_scenarios.py` (дописать в конец; существующее не трогать)
- Test: `tests/test_threed.py` (дополнить)

**Interfaces:**
- Produces: `SYSTEM_FACADE: str`; `validate_facade(scene: dict) -> tuple[dict, list[str]]`
  (БЕЗ размеров картинки — схема вся в метрах); ValueError, если сцена не dict или не
  похожа на фасад (нет ни storeys, ни width_m, ни windows, ни floor_height).
  Выходная сцена — ровно те ключи, что читает `build_facade` (Task 1), с клампами:
  storeys 1..30 (дефолт 5), floor_height 2.0..6.0 (3.0), width_m 3..200 (18.0),
  depth_m 3..60 (12.0), roof ∈ {flat, gable} (flat), roof_height 0.5..8.0 (2.5),
  windows rows 1..4 (1), cols 1..10 (3), w_m 0.3..5.0 (1.5), h_m 0.3..4.0 (1.5),
  margin_x_m 0.05..5.0 (1.0), margin_y_m 0.05..3.0 (0.8), skip нормализован до rows×cols
  (bool), balcony floor 1..storeys (иначе выкинуть), x_m 0..width_m, w_m 0.5..width_m,
  d_m 0.3..5.0 (невалидные выкидывать с warning), colors — hex `#rrggbb` иначе дефолт
  с warning; FIT: если 2·margin_x + cols·w_m > width_m → w_m сжать до
  (width_m − 2·margin_x)/cols с warning; аналогично h_m по floor_height.

- [ ] **Step 1: Failing-тест** — добавить в `tests/test_threed.py` перед `_mock_vlm_ok`:

```python
def test_validate_facade():
    from threed.threed_scenarios import validate_facade
    # валидная сцена проходит без изменений структуры
    out, warn = validate_facade(sample_facade_scene())
    assert out["storeys"] == 5 and out["windows"]["cols"] == 4
    assert out["windows"]["skip"] == [[False, True, False, False]]
    # дефолты на пустых полях
    out, warn = validate_facade({"storeys": 3})
    assert out["floor_height"] == 3.0 and out["windows"]["cols"] == 3
    assert out["depth_m"] == 12.0 and out["roof"] == "flat"
    # клампы
    out, warn = validate_facade({"storeys": 99, "floor_height": 9.0, "width_m": 500.0})
    assert out["storeys"] == 30 and out["floor_height"] == 6.0 and out["width_m"] == 200.0
    # крыша вне белого списка -> flat + warning
    out, warn = validate_facade({"storeys": 2, "roof": "hip", "roof_height": 1.0})
    assert out["roof"] == "flat" and any("hip" in w for w in warn)
    # FIT: окна не влезают по ширине -> w_m сжат
    s = {"storeys": 2, "width_m": 10.0,
         "windows": {"rows": 1, "cols": 4, "w_m": 3.0, "h_m": 1.5,
                     "margin_x_m": 1.0, "margin_y_m": 0.5}}
    out, warn = validate_facade(s)
    assert abs(out["windows"]["w_m"] - (10.0 - 2.0) / 4) < 1e-9
    assert any("w_m" in w for w in warn)
    # skip неправильной формы -> all False + warning
    s = sample_facade_scene()
    s["windows"]["skip"] = [[True], [True, False]]
    out, warn = validate_facade(s)
    assert out["windows"]["skip"] == [[False] * 4]
    assert any("skip" in w for w in warn)
    # балкон с этажем вне диапазона выкидывается
    s = sample_facade_scene()
    s["balconies"] = [{"floor": 9, "x_m": 4, "w_m": 3, "d_m": 1},
                      {"floor": 1, "x_m": 40, "w_m": 3, "d_m": 1}]
    out, warn = validate_facade(s)
    assert len(out["balconies"]) == 0 and len(warn) >= 2
    # цвет не hex -> дефолт + warning
    s = sample_facade_scene()
    s["colors"] = {"walls": "red"}
    out, warn = validate_facade(s)
    assert out["colors"]["walls"] == "#c8b89a" and any("walls" in w for w in warn)
    # не dict / пустышка -> ValueError
    for bad in ([1, 2], {"prompt": "x"}, None):
        try:
            validate_facade(bad)
            raise AssertionError("ожидалась ошибка")
        except ValueError:
            pass
    print("test_validate_facade OK")
```

- [ ] **Step 2: Запустить — упасть (`cannot import name 'validate_facade'`)**

Run: `./venv/Scripts/python.exe tests/test_threed.py`

- [ ] **Step 3: Написать код — добавить в конец `threed/threed_scenarios.py`**

```python
# ===================== Фаза 2: сценарий «Фасад» =====================

SYSTEM_FACADE = """You are a BIM facade analyst. Look at the attached image: a PHOTO or
RENDER of a building facade, OR an elevation DRAWING (possibly with dimension lines).
Estimate the facade as a parametric metric model. Reply with STRICT JSON ONLY - no
markdown fences, no comments, no extra keys.

Schema (ALL VALUES ARE METERS - no pixel coordinates):
{
 "storeys": <int 1-30, number of storeys>,
 "floor_height": <float m, storey height, 2.5-4 typical>,
 "width_m": <float m, facade width>,
 "depth_m": <float m, building depth - NOT visible from the facade; use 12 or the
   USER PROMPT if it states one>,
 "roof": "flat" | "gable",
 "roof_height": <float m, ridge height above the eave, only for gable>,
 "windows": {
   "rows": <int 1-4, window rows per storey>,
   "cols": <int 1-10, windows per row>,
   "w_m": <float m, window width>, "h_m": <float m, window height>,
   "margin_x_m": <float m, side margin>, "margin_y_m": <float m, margin inside a storey>,
   "skip": <rows x cols boolean matrix, true = NO window there (e.g. stair shaft,
     blind panels); all-false if every cell is glazed>
 },
 "balconies": [{"floor": <int 1-based>, "x_m": <center position from facade LEFT edge,
   m>, "w_m": <width>, "d_m": <projection depth>}],
 "colors": {"walls": "#rrggbb", "roof": "#rrggbb", "plinth": "#rrggbb"}
}

Rules:
- SCALE: if the image has dimension lines - use them (they are exact). Otherwise use
  anchors: storey ~3 m, window ~1.5 x 1.5 m, entrance door ~2.1 m, balcony ~3 x 1.2 m.
- Count storeys and window columns CAREFULLY; one window row per storey is typical.
- Perspective in photos: treat the facade as flat (orthographic).
- The USER PROMPT overrides your guesses (storeys, depth, roof, colors) wherever it
  states them.
"""


def _facade_float(value, default, lo, hi, field, warnings):
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


def _is_hex(value):
    import re as _re
    return isinstance(value, str) and _re.fullmatch(r"#[0-9a-fA-F]{6}", value) is not None


def validate_facade(scene):
    """Сцена фасада от VLM -> (чистая сцена, warnings). ValueError — не фасад."""
    if not isinstance(scene, dict) or not any(
            k in scene for k in ("storeys", "width_m", "windows", "floor_height")):
        raise ValueError("Не удалось распознать фасад на картинке")
    warnings = []
    out = {}
    out["storeys"] = int(_facade_float(scene.get("storeys", 5), 5, 1, 30, "storeys", warnings))
    out["floor_height"] = _facade_float(scene.get("floor_height", 3.0), 3.0, 2.0, 6.0,
                                        "floor_height", warnings)
    out["width_m"] = _facade_float(scene.get("width_m", 18.0), 18.0, 3.0, 200.0,
                                   "width_m", warnings)
    out["depth_m"] = _facade_float(scene.get("depth_m", 12.0), 12.0, 3.0, 60.0,
                                   "depth_m", warnings)
    roof = scene.get("roof", "flat")
    if roof not in ("flat", "gable"):
        warnings.append(f"roof: «{roof}» не поддержан — flat")
        roof = "flat"
    out["roof"] = roof
    out["roof_height"] = _facade_float(scene.get("roof_height", 2.5), 2.5, 0.5, 8.0,
                                       "roof_height", warnings)

    src = scene.get("windows") or {}
    win = {}
    win["rows"] = int(_facade_float(src.get("rows", 1), 1, 1, 4, "windows.rows", warnings))
    win["cols"] = int(_facade_float(src.get("cols", 3), 3, 1, 10, "windows.cols", warnings))
    win["margin_x_m"] = _facade_float(src.get("margin_x_m", 1.0), 1.0, 0.05, 5.0,
                                      "windows.margin_x_m", warnings)
    win["margin_y_m"] = _facade_float(src.get("margin_y_m", 0.8), 0.8, 0.05, 3.0,
                                      "windows.margin_y_m", warnings)
    win["w_m"] = _facade_float(src.get("w_m", 1.5), 1.5, 0.3, 5.0, "windows.w_m", warnings)
    win["h_m"] = _facade_float(src.get("h_m", 1.5), 1.5, 0.3, 4.0, "windows.h_m", warnings)
    # FIT: сетка обязана влезать в фасад/этаж
    fit_w = (out["width_m"] - 2 * win["margin_x_m"]) / win["cols"]
    if win["w_m"] > fit_w:
        warnings.append(f"windows.w_m: {win['w_m']:g} не влезает — сжат до {fit_w:g}")
        win["w_m"] = fit_w
    fit_h = (out["floor_height"] - 2 * win["margin_y_m"]) / win["rows"]
    if win["h_m"] > fit_h:
        warnings.append(f"windows.h_m: {win['h_m']:g} не влезает — сжат до {fit_h:g}")
        win["h_m"] = fit_h
    # skip -> строго rows×cols из bool
    raw_skip = src.get("skip")
    skip = [[False] * win["cols"] for _ in range(win["rows"])]
    if raw_skip is not None:
        ok = isinstance(raw_skip, list) and len(raw_skip) == win["rows"] and all(
            isinstance(r, list) and len(r) == win["cols"] for r in raw_skip)
        if ok:
            for j in range(win["rows"]):
                for i in range(win["cols"]):
                    skip[j][i] = bool(raw_skip[j][i])
        else:
            warnings.append("windows.skip: неверная форма — все окна считаются остеклёнными")
    win["skip"] = skip
    out["windows"] = win

    out["balconies"] = []
    for idx, bal in enumerate(scene.get("balconies") or [], start=1):
        if not isinstance(bal, dict):
            warnings.append(f"Балкон {idx}: не объект — пропущен")
            continue
        try:
            floor = int(bal.get("floor", 0))
        except (TypeError, ValueError):
            floor = 0
        if floor < 1 or floor > out["storeys"]:
            warnings.append(f"Балкон {idx}: этаж {floor} вне 1..{out['storeys']} — пропущен")
            continue
        x = _facade_float(bal.get("x_m", out["width_m"] / 2), out["width_m"] / 2,
                          0.0, out["width_m"], f"Балкон {idx}.x_m", warnings)
        w_b = _facade_float(bal.get("w_m", 3.0), 3.0, 0.5, out["width_m"],
                            f"Балкон {idx}.w_m", warnings)
        d_b = _facade_float(bal.get("d_m", 1.2), 1.2, 0.3, 5.0,
                            f"Балкон {idx}.d_m", warnings)
        if w_b <= 0 or d_b <= 0:
            warnings.append(f"Балкон {idx}: нулевые размеры — пропущен")
            continue
        out["balconies"].append({"floor": floor, "x_m": x, "w_m": w_b, "d_m": d_b})

    src_colors = scene.get("colors") or {}
    out["colors"] = {}
    for key, default in (("walls", "#c8b89a"), ("roof", "#52616b"), ("plinth", "#8d8d8d")):
        value = src_colors.get(key)
        if _is_hex(value):
            out["colors"][key] = value
        else:
            warnings.append(f"colors.{key}: не hex — дефолт {default}")
            out["colors"][key] = default
    return out, warnings
```

- [ ] **Step 4: Тест зелёный**

Run: `./venv/Scripts/python.exe tests/test_threed.py`
Expected: `test_validate_facade OK` + все прежние + `ALL OK`.

- [ ] **Step 5: Commit**

```bash
git add threed/threed_scenarios.py tests/test_threed.py
git commit threed/threed_scenarios.py tests/test_threed.py -m "feat(3d): промпт и валидация сценария фасад (метрическая схема, клампы, FIT-сетка окон, skip-матрица)"
```

---

### Task 3: Роутер — сценарий `facade` в `_generate_impl` (`threed/threed_router.py`)

**Files:**
- Modify: `threed/threed_router.py`
- Test: `tests/test_threed.py` (дополнить)

**Interfaces:**
- Consumes: `threed_scenarios.SYSTEM_FACADE/validate_facade` (Task 2),
  `threed_build.build_facade` (Task 1).
- Produces: `SCENARIOS = {"plan", "facade"}`; `_generate_impl("facade", prompt, image,
  out_dir)` → `{name: "3D_facade_….ifc", warnings}` (тот же контракт, что у plan).

- [ ] **Step 1: Failing-тест** — добавить в `tests/test_threed.py` после `test_generate_impl`:

```python
def test_generate_impl_facade():
    from PIL import Image
    import threed.threed_router as R
    R._vlm_list_cached = lambda: []  # тесты без сети (фаза 1)

    assert "facade" in R.SCENARIOS and "interior" not in R.SCENARIOS
    scene = sample_facade_scene()
    R._call_vlm = _mock_vlm_ok("```json\n" + json.dumps(scene, ensure_ascii=False) + "\n```")
    TMP.mkdir(exist_ok=True)
    img = Image.new("RGB", (600, 800), (250, 250, 250))
    res = R._generate_impl("facade", "тест фасада", img, TMP)
    assert res["name"].startswith("3D_facade_") and res["name"].endswith(".ifc")
    assert (TMP / res["name"]).is_file()
    assert (TMP / (Path(res["name"]).stem + "_preview.png")).is_file()
    assert (TMP / "_threed_last.json").is_file()
    # интерьер всё ещё фаза 3
    try:
        R._generate_impl("interior", "", img, TMP)
        raise AssertionError("ожидалась ошибка")
    except ValueError as e:
        assert "разработке" in str(e)
    print("test_generate_impl_facade OK")
```

- [ ] **Step 2: Запустить — упасть (`assert "facade" in R.SCENARIOS` — AssertionError)**

Run: `./venv/Scripts/python.exe tests/test_threed.py`

- [ ] **Step 3: Правки `threed/threed_router.py`** (точные замены)

3а. Строку (≈39):
```python
SCENARIOS = {"plan"}  # facade/interior — фазы 2-3
```
заменить на:
```python
SCENARIOS = {"plan", "facade"}  # interior — фаза 3
```

3б. Строку (≈203):
```python
        raise ValueError(f"Сценарий «{scenario}» в разработке (доступен: plan)")
```
заменить на:
```python
        raise ValueError(f"Сценарий «{scenario}» в разработке (доступны: plan, facade)")
```

3в. Вызов VLM (≈214) — системный промпт по сценарию. Было:
```python
        raw = _call_vlm(threed_scenarios.SYSTEM_GENPLAN,
```
стало:
```python
        system = (threed_scenarios.SYSTEM_FACADE if scenario == "facade"
                  else threed_scenarios.SYSTEM_GENPLAN)
        raw = _call_vlm(system,
```

3г. Валидация (≈225). Было:
```python
    scene, warnings = threed_scenarios.validate_genplan(scene, image.width, image.height)
```
стало:
```python
    if scenario == "facade":
        scene, warnings = threed_scenarios.validate_facade(scene)
    else:
        scene, warnings = threed_scenarios.validate_genplan(scene, image.width, image.height)
```

3д. Сборка (≈231). Было:
```python
    threed_build.build_genplan(
        scene, image, ifc_path, preview_path,
        {"Scenario": scenario, "Prompt": prompt, "Model": model, "Source": "3D Design"})
```
стало:
```python
    meta = {"Scenario": scenario, "Prompt": prompt, "Model": model, "Source": "3D Design"}
    if scenario == "facade":
        threed_build.build_facade(scene, ifc_path, preview_path, meta)
    else:
        threed_build.build_genplan(scene, image, ifc_path, preview_path, meta)
```

3е. Docstring модуля (строка 5) — после `-> {name, warnings}` дописать упоминание
сценариев: заменить строку
```python
    POST /api/v1/threed/generate  {scenario, prompt, image}  -> {name, warnings}
```
на
```python
    POST /api/v1/threed/generate  {scenario: plan|facade, prompt, image} -> {name, warnings}
```

- [ ] **Step 4: Тест зелёный**

Run: `./venv/Scripts/python.exe tests/test_threed.py`
Expected: `test_generate_impl_facade OK` + все прежние + `ALL OK`.

- [ ] **Step 5: Commit**

```bash
git add threed/threed_router.py tests/test_threed.py
git commit threed/threed_router.py tests/test_threed.py -m "feat(3d): роутер принимает сценарий facade (ветвление промпт/валидатор/сборщик)"
```

---

### Task 4: Виджет — плитка «Фасад» активна, placeholder по сценарию (`imagerouter/devbim_topright_buttons.js`)

**Files:**
- Modify: `imagerouter/devbim_topright_buttons.js`
- Test: `tests/test_threed.py` (дополнить `test_widget_3d_modal`)

**Interfaces:**
- Produces: плитка `data-s="facade"` без `disabled`; `TEXTS.*.promptPhPlan` /
  `promptPhFacade` (старый `promptPh` удалён); клик по плитке меняет placeholder
  textarea; interior остаётся заглушкой (`soon3d` = «фаза 3»).

- [ ] **Step 1: Дописать failing-ассерты в `test_widget_3d_modal`** (после существующих,
  до `print(...)`):

```python
    # фаза 2: плитка фасада активна, placeholder зависит от сценария
    facade_tile = '<button class="devbim-3d-tile" data-s="facade">'
    assert facade_tile + "<span>\U0001F3E2</span>" in src, \
        "плитка фасада должна быть активна (без disabled/title)"
    assert 'data-s="facade" disabled' not in src
    assert 'data-s="interior" disabled' in src
    for key in ("promptPhPlan", "promptPhFacade"):
        assert key + ":" in src, key
    assert "promptPh:" not in src and "t().promptPh +" not in src
    assert "promptPhFacade" in src.split('data-s="facade"')[1], \
        "клик по плитке фасада подставляет promptPhFacade"
```

- [ ] **Step 2: Запустить — упасть (маркер promptPhPlan отсутствует)**

Run: `./venv/Scripts/python.exe tests/test_threed.py`

- [ ] **Step 3: Правки виджета** (точные замены)

3а. `TEXTS.ru` — заменить строку
```js
      pickScenario: 'Что генерируем?', promptPh: 'Уточнения: «жилой 5 этажей, школа 3, масштаб 0.5 м/px»',
```
на
```js
      pickScenario: 'Что генерируем?',
      promptPhPlan: 'Уточнения: «жилой 5 этажей, школа 3, масштаб 0.5 м/px»',
      promptPhFacade: 'Уточнения: «5 этажей, двускатная крыша, окна 4 в ряд, балконы со 2 этажа, глубина 14 м»',
```
и строку
```js
      soon3d: 'Фасад и интерьер — в разработке (фаза 2–3)',
```
на
```js
      soon3d: 'Интерьер — в разработке (фаза 3)',
```

3б. `TEXTS.en` — заменить строку
```js
      pickScenario: 'What to generate?', promptPh: 'Hints: &quot;residential 5 floors, school 3, scale 0.5 m/px&quot;',
```
на
```js
      pickScenario: 'What to generate?',
      promptPhPlan: 'Hints: &quot;residential 5 floors, school 3, scale 0.5 m/px&quot;',
      promptPhFacade: 'Hints: &quot;5 storeys, gable roof, 4 windows per row, balconies from floor 2, depth 14 m&quot;',
```
и строку
```js
      soon3d: 'Facade & Interior — coming soon (phase 2-3)',
```
на
```js
      soon3d: 'Interior — coming soon (phase 3)',
```

3в. В `open3D()` — плитка фасада. Было:
```js
      '<button class="devbim-3d-tile" data-s="facade" disabled title="' + t().soon3d + '"><span>🏢</span>' + t().facade + '</button>' +
```
стало:
```js
      '<button class="devbim-3d-tile" data-s="facade"><span>🏢</span>' + t().facade + '</button>' +
```

3г. В `open3D()` — начальный placeholder. Было:
```js
      '<textarea id="devbim-3d-prompt" rows="3" placeholder="' + t().promptPh + '"></textarea>' +
```
стало:
```js
      '<textarea id="devbim-3d-prompt" rows="3" placeholder="' + t().promptPhPlan + '"></textarea>' +
```

3д. В обработчике плиток (после `b.classList.add('on');` добавить строку):
```js
        var ta = document.getElementById('devbim-3d-prompt');
        if (ta) ta.placeholder = b.getAttribute('data-s') === 'facade'
          ? t().promptPhFacade : t().promptPhPlan;
```
(полный блок обработчика после правки:
```js
    ov.querySelectorAll('.devbim-3d-tile').forEach(function (b) {
      b.addEventListener('click', function () {
        S3.scenario = b.getAttribute('data-s');
        ov.querySelectorAll('.devbim-3d-tile').forEach(function (x) { x.classList.remove('on'); });
        b.classList.add('on');
        var ta = document.getElementById('devbim-3d-prompt');
        if (ta) ta.placeholder = b.getAttribute('data-s') === 'facade'
          ? t().promptPhFacade : t().promptPhPlan;
      });
    });
```
)

3е. Шапка-комментарий файла (строки 11–13) — заменить
```js
 * «3D Design» открывает модалку генерации 3D
 * (сценарий/источник/промт -> POST /api/v1/threed/generate -> вкладка IFC;
 * фасад/интерьер — заглушки внутри модалки, фаза 2–3).
```
на
```js
 * «3D Design» открывает модалку генерации 3D
 * (сценарий/источник/промт -> POST /api/v1/threed/generate -> вкладка IFC;
 * сценарии: генплан и фасад, интерьер — заглушка, фаза 3).
```

- [ ] **Step 4: Проверки и деплой**

```bash
node --check imagerouter/devbim_topright_buttons.js
./venv/Scripts/python.exe tests/test_threed.py     # все OK + ALL OK
./venv/Scripts/python.exe setup_imagerouter.py     # редеплой виджета (static, F5)
```

- [ ] **Step 5: Commit**

```bash
git add imagerouter/devbim_topright_buttons.js tests/test_threed.py
git commit imagerouter/devbim_topright_buttons.js tests/test_threed.py -m "feat(3d): плитка «Фасад» активна + placeholder промта по сценарию (RU/EN)"
```

---

### Task 5: Деплой + рестарт + живой smoke фасада

**Files:** изменений в git нет (кроме правок по итогам — тогда pathspec-коммит с пояснением).

- [ ] **Step 1: Развернуть и перезапустить**

```bash
./venv/Scripts/python.exe setup_threed.py        # перекопирует 3 модуля роутера
./venv/Scripts/python.exe setup_imagerouter.py   # виджет (если Task 4 не деплоил)
powershell -ExecutionPolicy Bypass -File _restart_server.ps1
```

- [ ] **Step 2: Проверить API (~40 с после старта; siteauth — cookie devbim_auth, см. HANDOFF п.17/37)**

```bash
curl -s -b "devbim_auth=<cookie>" http://127.0.0.1:9090/api/v1/threed/model | head -c 200
```
Expected: `{"model":"openai/gpt-6-astra",...}` (как в фазе 1).

- [ ] **Step 3: Живой smoke фасада (ОДИН раз, ~$0.05–0.15)** — синтетический чертёж-фасад:

```bash
./venv/Scripts/python.exe -c "
import base64, io, json, urllib.request
from PIL import Image, ImageDraw
img = Image.new('RGB', (600, 800), (255, 255, 255))
d = ImageDraw.Draw(img)
d.rectangle([50, 100, 550, 700], fill=(210, 190, 160), outline=(60, 60, 60))  # стены 5 эт.
for f in range(5):
    for c in range(4):
        d.rectangle([90 + c * 110, 140 + f * 110, 160 + c * 110, 230 + f * 110],
                    fill=(35, 40, 48))
d.polygon([(50, 100), (550, 100), (300, 20)], fill=(90, 100, 110))            # двускатная
buf = io.BytesIO(); img.save(buf, format='PNG')
body = json.dumps({'scenario': 'facade', 'prompt': '5 storeys, gable roof, 4 windows per row',
                   'image': 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode()}).encode()
req = urllib.request.Request('http://127.0.0.1:9090/api/v1/threed/generate', data=body,
                             headers={'Content-Type': 'application/json'})
print(urllib.request.urlopen(req, timeout=300).read().decode())
"
```
(siteauth: если включён — предварительно войти POST /auth/login (см. HANDOFF п.17) и
приложить cookie, как делали в фазе 1.)
Expected: `{"name":"3D_facade_….ifc","warnings":[…]}`. Затем: файл и `_preview.png` в
`data/ifc/`, дамп `data/ifc/_threed_last.json` (`"scenario": "facade"`); превью открыть
глазами (Read) — 5 рядов × 4 окна, треугольник крыши.

---

### Task 6: E2E (браузер, живой сервер)

**Files:** — чек-лист + скриншоты `docs/3d-design-facade-{modal,result}.png`.

- [ ] **Step 1: Чек-лист** (после F5; вход по паролю сайта):

1. Открыть модалку «3D Design»: плитка «Фасад» АКТИВНА (кликабельна), «Интерьер»
   disabled с подсказкой «в разработке (фаза 3)».
2. Клик «Фасад»: плитка подсвечена, placeholder textarea сменился на фасадный
   (RU: «5 этажей, двускатная крыша…»); клик «Генплан» — вернулся прежний.
3. Загрузить фото/чертёж фасада в галерею (Upload) → выбрать → модалка: превью с
   бейджем «Галерея».
4. Промт «5 этажей, двускатная крыша, окна 4 в ряд, балконы со 2 этажа» → Generate →
   таймер; ответ ≤2 мин → модалка закрылась, тост «Модель создана: 3D_facade_….ifc»,
   приложение на вкладке IFC, модель загружена (3D-вид), имя в селекторе шапки.
5. Клик по окну в 3D — свойства: ObjectType CONCEPTUAL_WINDOW, имя «Окно Э…-…»;
   клик по стене — CONCEPTUAL_STOREY; дерево: 1 здание, 5 этажей.
6. 📸 To Canvas → снимок на холсте (штатный цикл).
7. Консоль браузера — без новых ошибок (стоковый redux-remember шум допустим).
8. Ошибки: PUT no/such и пустой источник уже покрыты фазой 1 — не повторять.

- [ ] **Step 2: Скриншоты**

`docs/3d-design-facade-modal.png` (модалка: плитка Фасад активна + фасадный
placeholder + превью источника), `docs/3d-design-facade-result.png` (вкладка IFC с
моделью фасада). Коммит:

```bash
git add docs/3d-design-facade-modal.png docs/3d-design-facade-result.png
git commit docs/3d-design-facade-modal.png docs/3d-design-facade-result.png -m "docs(3d): E2E-скриншоты сценария фасад"
```

---

### Task 7: Документация + финальный коммит

**Files:**
- Modify: `HANDOFF.md` (п.38), `README.md` (раздел «3D Design»), `AGENTS.md` (порядок
  setup — БЕЗ изменений, setup_threed уже указан; проверить и не дублировать),
  `docs/superpowers/specs/2026-09-18-3d-design-ifc-generation-design.md` (пометка
  «фаза 2 реализована»).

- [ ] **Step 1: HANDOFF.md — п.38** по образцу п.37: что добавлено (SYSTEM_FACADE,
  validate_facade с FIT-сеткой и skip-матрицей, build_facade: тома-этажи
  CONCEPTUAL_STOREY, окна CONCEPTUAL_WINDOW заподлицо с лицевой гранью (y = depth/2,
  толщина 0.12), балконы-плиты CONCEPTUAL_BALCONY, цоколь, двускатная призма
  CONCEPTUAL_ROOF с матрицей поворота (локальная Y→Z, выдавливание → −Y), превью —
  чертёж фасада в метрах), роутер-ветвление, плитка виджета + placeholder по сценарию,
  стоимость, грабли (все live-уроки фазы 2, если появятся; walrus в f-строке
  заголовка превью, если оставлен).
- [ ] **Step 2: README.md** — раздел «3D Design» дополнить сценарием «Фасад»: вход —
  фото/рендер/чертёж; масштаб по размерным линиям или опорам; результат — концепт
  (перспектива принята за орто, глубина по умолчанию 12 м); интерьер — фаза 3.
- [ ] **Step 3: Спека** — статус-блок в начале дополнить: «Фаза 2 (фасад) реализована
  19.09 (ветка 3d) — см. HANDOFF п.38».
- [ ] **Step 4: Полный прогон и коммит**

```bash
./venv/Scripts/python.exe tests/test_threed.py
./venv/Scripts/python.exe tests/test_designcode.py
git add HANDOFF.md README.md docs/superpowers/specs/2026-09-18-3d-design-ifc-generation-design.md
git commit HANDOFF.md README.md docs/superpowers/specs/2026-09-18-3d-design-ifc-generation-design.md -m "docs: 3D Design фаза 2 (фасад) — HANDOFF п.38, README, спека"
```

---

## Самопроверка (выполнена при написании плана)

- Спека-фаза-2 покрыта: вход фото/рендер ИЛИ чертёж (промпт T2), масштаб по
  размерным линиям/опорам (промпт T2), метрическая схема (T2), сборка бокс/призма/
  поэтажность/окна-сетка с skip/балконы-плиты (T1), цвета (T1/T2), допущения в
  свойствах OrthoAssumption/DepthAssumed (T1), конвейер/модалка (T3/T4), деплой и
  проверки (T5/T6), docs (T7).
- Отступлений от спеки нет; превью — чертёж фасада (2D, метры), 3D-вид даёт вьювер
  (соглашение фазы 1).
- Типы согласованы: `validate_facade(scene) -> (dict, [str])` без размеров картинки;
  `build_facade(scene, ifc_path, preview_path, meta) -> Path`; ветвление роутера
  передаёт `meta` словарём.
- План фазы 3 (интерьер-план) — отдельный документ после фазы 2.
