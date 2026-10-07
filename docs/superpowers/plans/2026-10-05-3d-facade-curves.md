# Криволинейные фасады + окружение (facade v2) — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** сценарий `facade` строит гнутые здания (волна/наклон силуэта, taper, дуга плана, скруглённые торцы) и окружение (деревья, люди, фоновые дома) по опциональным блокам `curve`/`context`.

**Architecture:** параметрический контракт в `SYSTEM_FACADE` (числа, не полигоны) → `_facade_curve`/`_facade_context` в валидаторе → геометрия в `build_facade` (контур плана `_facade_footprint` экструзией произвольного профиля — механизм уже используется `box()`/призмами; крыша-полоса мешем с явными гранями — волна невыпуклая, `_hull` нельзя) → превью/оверлей/overview дорисовывают кривую и окружение.

**Tech Stack:** Python (venv), ifcopenshell API (`profile.add_arbitrary_profile`, `geometry.add_profile_representation`, ShapeBuilder-меши), matplotlib-превью, PIL-оверлей. Тесты — plain asserts в `tests/test_threed.py`.

**Спека:** `docs/superpowers/specs/2026-10-05-3d-facade-curves-design.md`

## Global Constraints

- Рабочее дерево содержит ЧУЖОЙ WIP (furniture-parts: `threed_build.py` и др. изменены) — **коммитов в сессии НЕ делаем**; шаг «Commit» из шаблона заменён на «чекпоинт: тесты зелёные». Финальный коммит — вручную после ревью.
- Всё в UTF-8; запуск тестов: `venv\Scripts\python.exe tests\test_threed.py` (из корня), печать `ALL OK`.
- Деплой бэкенда: `venv\Scripts\python.exe setup_threed.py` + рестарт `powershell -NoProfile -ExecutionPolicy Bypass -File launch\_restart_server.ps1`.
- Обратная совместимость: сцена без `curve`/`context` обязана давать байт-в-байт прежнее поведение сборщика (существующие тесты без правок).
- Поправка к спеке (уточнение по ходу): поле кроны дерева — `crown_d_m` (диаметр, как в схеме `scene`), а не `r_m`; `storeys` у фоновых домов не используем (только `h_m`); фоновый дом с y перед зданием — не дроп, а сброс y за фасад (d/2+6) + warning (спека обновлена).
- Ансамбль: curve-поля в `compare_scenes` НЕ добавляем осознанно — прогон B (grounding/text) кривых не извлекает, спор по ним невозможен («отсутствие поля у B ≠ спор» выполняется автоматически); строка спеки про compare — тавтология, реализация = ничего не менять.
- Шаги «Run» для отдельных тестов: файл тестов один, гоним целиком `venv\Scripts\python.exe tests\test_threed.py`; «FAIL» проверяем по AssertionError с именем теста в трейсе.

---

### Task 1: Контракт и валидация `curve`

**Files:**
- Modify: `threed/threed_scenarios.py` (SYSTEM_FACADE ~153-203; validate_facade — вставка после FIT-блока ~353, перед skip-блоком)
- Test: `tests/test_threed.py` (внутрь `test_validate_facade`)

**Interfaces:**
- Produces: `validate_facade` возвращает сцену с полем `curve: dict | None`; ключи: `silhouette` ("wave"|"slope_up"|"slope_down"|None), `amplitude_m` float, `wavelength_m` float, `taper_pct` int, `plan_bend_m` float, `end_left`/`end_right` ("flat"|"round"). None — кривых нет. Побочно: при round-торцах матрица `windows.skip` помечает колонки за пределами прямого участка.

- [ ] **Step 1: failing-тест**

В `test_validate_facade` после блока про cols-клампы добавить:

```python
    # curve (v2): гнутое здание — разбор/клампы/дефолты
    base = {"storeys": 2, "width_m": 40.0, "depth_m": 12.0}
    out, warn = validate_facade(dict(base, roof="gable", curve={
        "silhouette": "wave", "amplitude_m": 1.2, "wavelength_m": 9.0,
        "taper_pct": 15, "plan_bend_m": 3.0,
        "end_left": "round", "end_right": "round"}))
    assert out["curve"]["silhouette"] == "wave"
    assert abs(out["curve"]["amplitude_m"] - 1.2) < 1e-9
    assert abs(out["curve"]["wavelength_m"] - 9.0) < 1e-9
    assert out["curve"]["taper_pct"] == 15
    assert abs(out["curve"]["plan_bend_m"] - 3.0) < 1e-9
    assert out["curve"]["end_left"] == "round" and out["curve"]["end_right"] == "round"
    # волна+gable -> приоритет кривой, крыша выключена
    assert out["roof"] == "flat" and any("силуэт" in w for w in warn)
    # клампы: amplitude 0.3-3, wavelength <= width/1.5, taper 0-40, bend <= w/4
    out, warn = validate_facade(dict(base, curve={
        "silhouette": "wave", "amplitude_m": 9.0, "wavelength_m": 60.0,
        "taper_pct": 90, "plan_bend_m": 50.0}))
    assert out["curve"]["amplitude_m"] == 3.0
    assert out["curve"]["wavelength_m"] == 40.0 / 1.5
    assert out["curve"]["taper_pct"] == 40
    assert abs(out["curve"]["plan_bend_m"] - 10.0) < 1e-9   # w/4 = 10
    assert any("amplitude_m" in w for w in warn) and any("taper_pct" in w for w in warn)
    # мусорные энумы -> дефолты; пустой блок -> None (ветка сборки не включается)
    out, warn = validate_facade(dict(base, curve={
        "silhouette": "banana", "end_left": "circle", "end_right": "circle"}))
    assert out["curve"] is None and any("silhouette" in w for w in warn)
    out, warn = validate_facade(dict(base))
    assert "curve" not in out or out.get("curve") is None
    # skip за скруглёнными торцами: у широкого фасада крайние колонки гасятся
    out, warn = validate_facade(dict(base, windows={
        "cols": 20, "w_m": 1.5, "h_m": 2.5}, curve={"end_left": "round",
                                                    "end_right": "round"}))
    assert out["windows"]["skip"][0][0] is True and out["windows"]["skip"][0][-1] is True
    assert any("торц" in w for w in warn)
```

- [ ] **Step 2: Run** — `venv\Scripts\python.exe tests\test_threed.py` → FAIL, `KeyError: 'curve'` / `None is not True`.

- [ ] **Step 3: реализация**

3a. SYSTEM_FACADE: в схему после строки `"roof_height": …` вставить

```
 "curve": <optional, curved buildings; omit for a flat rectangular box>: {
   "silhouette": "wave" | "slope_up" | "slope_down" | null,
   "amplitude_m": <0.3-3.0, wave height / slope rise>,
   "wavelength_m": <4.0-40.0, wave only>,
   "taper_pct": <0-40, plan narrowing toward the top>,
   "plan_bend_m": <-15..15, arc in plan: + bulges toward the camera>,
   "end_left": "flat" | "round", "end_right": "flat" | "round"
 },
```

В Rules заменить строку
`- Curved/wavy roofs and rounded building ends: the parametric box cannot bend - approximate the silhouette with custom_parts prisms (6-16 segments along the facade, color "roof" or "glazing").`
на
`- Curved buildings: estimate the roof-line wave (amplitude/wavelength), linear height rise/fall along the facade, plan bend and rounded ends from the photo into "curve"; keep "roof": "flat" then.`

3b. Новая функция перед `validate_facade`:

```python
def _facade_curve(raw, out, warnings):
    """Опц. блок curve (гнутое здание) -> dict | None. None = прямые формы,
    ветка кривой в сборке не включается. Не гейт: любой мусор -> дефолт."""
    if not isinstance(raw, dict):
        if raw:
            warnings.append("curve: не объект — изгибы выключены")
        return None
    sil = raw.get("silhouette")
    if sil not in ("wave", "slope_up", "slope_down", None):
        warnings.append(f"curve.silhouette «{sil}» не поддержан — силуэта нет")
        sil = None
    amp = _facade_float(raw.get("amplitude_m", 1.0), 1.0, 0.3, 3.0,
                        "curve.amplitude_m", warnings)
    wl_def = max(4.0, min(12.0, out["width_m"] / 2))
    wl = _facade_float(raw.get("wavelength_m", wl_def), wl_def, 4.0,
                       max(4.0, out["width_m"] / 1.5), "curve.wavelength_m", warnings)
    taper = int(_facade_float(raw.get("taper_pct", 0), 0, 0, 40,
                              "curve.taper_pct", warnings))
    bend = _facade_float(raw.get("plan_bend_m", 0), 0, -15.0, 15.0,
                         "curve.plan_bend_m", warnings)
    bend_cap = out["width_m"] / 4
    if abs(bend) > bend_cap:
        warnings.append(f"curve.plan_bend_m: {bend:g} вне ±w/4 — кламп до "
                        f"{max(-bend_cap, min(bend_cap, bend)):g}")
        bend = max(-bend_cap, min(bend_cap, bend))
    ends = {}
    for k in ("end_left", "end_right"):
        v = raw.get(k, "flat")
        if v not in ("flat", "round"):
            warnings.append(f"curve.{k} «{v}» не поддержан — flat")
            v = "flat"
        ends[k] = v
    if sil is None and taper == 0 and abs(bend) < 0.05 \
            and ends == {"end_left": "flat", "end_right": "flat"}:
        return None
    return {"silhouette": sil,
            "amplitude_m": amp if sil else 0.0,
            "wavelength_m": wl if sil == "wave" else 0.0,
            "taper_pct": taper, "plan_bend_m": bend, **ends}
```

3c. В `validate_facade` после FIT-блока (после `win["h_m"] = fit_h`-клампа, перед комментарием `# skip -> строго rows×cols…`) вставить разбор curve + правило gable:

```python
    curve = _facade_curve(scene.get("curve"), out, warnings)
    if curve and curve["silhouette"] and out["roof"] != "flat":
        warnings.append(f"roof {out['roof']} заменён силуэтом "
                        f"«{curve['silhouette']}» (приоритет curve)")
        out["roof"] = "flat"
    if curve:
        out["curve"] = curve
```

3d. Сразу ПОСЛЕ нормализации skip (после `win["skip"] = skip` не трогаем; после `out["windows"] = win` на самом деле удобнее до `out["windows"]`) — вставить гашение крайних колонок за круглыми торцами, работая по уже собранному `skip`:

после блока `raw_skip`-нормализации (строки `skip[j][i] = bool(...)`) и до `shape = src.get(...)` вставить:

```python
    if curve and ("round" in (curve["end_left"], curve["end_right"])):
        inset = 0.3 * out["depth_m"]          # 0.6 * d/2 с каждой стороны
        usable = out["width_m"] - 2 * win["margin_x_m"]
        gap = (usable - win["cols"] * win["w_m"]) / max(win["cols"] - 1, 1) \
            if win["cols"] > 1 else 0.0
        hidden = 0
        for i in range(win["cols"]):
            cx = win["margin_x_m"] + win["w_m"] / 2 + i * (win["w_m"] + gap)
            if (curve["end_left"] == "round" and cx < inset) or \
                    (curve["end_right"] == "round" and cx > out["width_m"] - inset):
                for j in range(win["rows"]):
                    if not skip[j][i]:
                        skip[j][i] = True
                        hidden += 1
        if hidden:
            warnings.append(f"скруглённый торец: {hidden} окон скрыты (skip)")
```

- [ ] **Step 4: Run** — `venv\Scripts\python.exe tests\test_threed.py` → PASS (`ALL OK`).
- [ ] **Step 5: Чекпоинт** — тесты зелёные; коммитов нет (см. Global Constraints).

---

### Task 2: Контракт и валидация `context`

**Files:**
- Modify: `threed/threed_scenarios.py` (SYSTEM_FACADE — блок в схему + правило; `_facade_context` перед `validate_facade`; вызов в конце `validate_facade`, перед `src_colors`)
- Test: `tests/test_threed.py` (новая `test_validate_facade_context` + регистрация в `__main__`-списке рядом с `test_validate_facade()`)

**Interfaces:**
- Produces: `out["context"] = {"trees": [...], "people": [...], "background_buildings": [...]}` или отсутствие ключа. Элементы trees: `{x_m, y_m, h_m, crown_d_m}` (x — от ЛЕВОЙ кромки фасада, y: 0 = линия фасада, + за зданием); people: `{x_m, y_m, h_m}`; background_buildings: `{x_m, y_m, w_m, d_m, h_m, color}` (color — hex или None).

- [ ] **Step 1: failing-тест**

```python
def test_validate_facade_context():
    from threed.threed_scenarios import validate_facade
    base = {"storeys": 2, "width_m": 40.0, "depth_m": 12.0}
    # без context ключа нет; мусор -> предупреждение
    out, warn = validate_facade(dict(base))
    assert "context" not in out
    out, warn = validate_facade(dict(base, context="мусор"))
    assert "context" not in out and any("context" in w for w in warn)
    out, warn = validate_facade(dict(base, context={
        "trees": [{"x_m": 5, "y_m": 20, "h_m": 8, "crown_d_m": 4},
                  {"x_m": 7, "y_m": 25, "h_m": 99, "crown_d_m": 0.2},
                  "не объект"] * 15,
        "people": [{"x_m": 10, "y_m": -5, "h_m": 1.8}],
        "background_buildings": [
            {"x_m": 20, "y_m": 30, "w_m": 25, "d_m": 15, "h_m": 30,
             "color": "#9aa3ad"},
            {"x_m": 30, "y_m": 2, "w_m": 20, "d_m": 10, "h_m": 20},
            {"x_m": 35, "y_m": 40, "w_m": 999, "d_m": 10, "h_m": 20}]}))
    ctx = out["context"]
    # 45 элементов на входе -> лимит 40; из валидных второй с клампами
    assert len(ctx["trees"]) == 40 and len(ctx["people"]) == 1
    assert any("больше 40" in w for w in warn)
    tr = ctx["trees"][1]
    assert tr["h_m"] == 20.0 and tr["crown_d_m"] == 1.0   # клампы 2-20 / 1-8
    assert ctx["people"][0]["h_m"] == 1.8
    # второй фоновый дом: y=2 < d/2+3=9 -> дроп с warning; третий: w-кламп 60
    assert len(ctx["background_buildings"]) == 2
    assert any("перед зданием" in w for w in warn)
    assert ctx["background_buildings"][1]["w_m"] == 60.0
    assert ctx["background_buildings"][0]["color"] == "#9aa3ad"
    print("test_validate_facade_context OK")
```

- [ ] **Step 2: Run** → FAIL: `KeyError: 'context'`.

- [ ] **Step 3: реализация**

3a. SYSTEM_FACADE, в схему после блока `curve`:

```
 "context": <optional surroundings; omit for a clean elevation/drawing>: {
   "trees": [{"x_m" <from facade LEFT edge>, "y_m" <0 = facade line, + behind>,
              "h_m": 2-20, "crown_d_m": 1-8}],
   "people": [{"x_m", "y_m", "h_m": 1.4-2.0}],
   "background_buildings": [{"x_m", "y_m" <behind the building>, "w_m",
     "d_m", "h_m", "color": "#rrggbb"}]
 },
```

В Rules добавить:
`- Report visible surroundings in "context" (roadside trees, people, background blocks); the model must match the photo environment.`

3b. Функция перед `validate_facade`:

```python
def _facade_context(raw, out, warnings):
    """Опц. блок context (окружение фасада): деревья/люди/фоновые дома.
    Рамка: x от левой кромки фасада, y: 0 = линия фасада, + за зданием."""
    if not isinstance(raw, dict):
        if raw:
            warnings.append("context: не объект — окружение пропущено")
        return None
    w, d = out["width_m"], out["depth_m"]
    ctx = {"trees": [], "people": [], "background_buildings": []}
    trees = raw.get("trees")
    if not isinstance(trees, list):
        if trees:
            warnings.append("context.trees: не список — пропущены")
        trees = []
    if len(trees) > 40:
        warnings.append("context.trees: больше 40 — лишние отброшены")
    for idx, tr in enumerate(trees[:40], start=1):
        if not isinstance(tr, dict):
            warnings.append(f"Дерево {idx}: не объект — пропущено")
            continue
        try:
            x = float(tr.get("x_m", w / 2)); y = float(tr.get("y_m", 10.0))
        except (TypeError, ValueError):
            warnings.append(f"Дерево {idx}: координаты не числа — пропущено")
            continue
        h = _facade_float(tr.get("h_m", 6.0), 6.0, 2.0, 20.0,
                          f"дерево {idx}.h_m", warnings)
        cr = _facade_float(tr.get("crown_d_m", 3.0), 3.0, 1.0, 8.0,
                           f"дерево {idx}.crown_d_m", warnings)
        ctx["trees"].append({"x_m": max(-10.0, min(w + 10.0, x)),
                             "y_m": max(-30.0, min(60.0, y)),
                             "h_m": h, "crown_d_m": cr})
    people = raw.get("people")
    if not isinstance(people, list):
        if people:
            warnings.append("context.people: не список — пропущены")
        people = []
    if len(people) > 20:
        warnings.append("context.people: больше 20 — лишние отброшены")
    for idx, per in enumerate(people[:20], start=1):
        if not isinstance(per, dict):
            warnings.append(f"Человек {idx}: не объект — пропущен")
            continue
        try:
            x = float(per.get("x_m", w / 2)); y = float(per.get("y_m", -3.0))
        except (TypeError, ValueError):
            continue
        h = _facade_float(per.get("h_m", 1.7), 1.7, 1.4, 2.0,
                          f"человек {idx}.h_m", warnings)
        ctx["people"].append({"x_m": max(-10.0, min(w + 10.0, x)),
                              "y_m": max(-30.0, min(60.0, y)), "h_m": h})
    bgs = raw.get("background_buildings")
    if not isinstance(bgs, list):
        if bgs:
            warnings.append("context.background_buildings: не список — пропущены")
        bgs = []
    if len(bgs) > 8:
        warnings.append("context.background_buildings: больше 8 — лишние отброшены")
    for idx, bb in enumerate(bgs[:8], start=1):
        if not isinstance(bb, dict):
            warnings.append(f"Фоновый дом {idx}: не объект — пропущен")
            continue
        try:
            x = float(bb.get("x_m", w / 2)); y = float(bb.get("y_m", 25.0))
            bw = float(bb.get("w_m", 20.0)); bd = float(bb.get("d_m", 12.0))
            bh = float(bb.get("h_m", 15.0))
        except (TypeError, ValueError):
            warnings.append(f"Фоновый дом {idx}: размеры не числа — пропущен")
            continue
        if y <= d / 2 + 3:
            warnings.append(f"Фоновый дом {idx}: перед зданием (y={y:g}) — сброс за фасад")
            y = d / 2 + 6.0
        color = bb.get("color")
        if not _is_hex(color):
            if color:
                warnings.append(f"Фоновый дом {idx}.color: не hex — дефолт")
            color = "#c3c9cf"
        ctx["background_buildings"].append({
            "x_m": max(-10.0, min(w + 10.0, x)), "y_m": min(60.0, y),
            "w_m": max(4.0, min(60.0, bw)), "d_m": max(4.0, min(30.0, bd)),
            "h_m": max(3.0, min(60.0, bh)), "color": color})
    return ctx
```

3c. В `validate_facade` перед `src_colors = scene.get("colors")`:

```python
    ctx = _facade_context(scene.get("context"), out, warnings)
    if ctx is not None:
        out["context"] = ctx
```

3d. `tests/test_threed.py`: добавить `test_validate_facade_context()` в список вызовов внизу файла рядом с `test_validate_facade()`.

- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Чекпоинт** — тесты зелёные.

---

### Task 3: Геометрия кривых в `build_facade`

**Files:**
- Modify: `threed/threed_build.py`: модульные хелперы `_facade_ztop`, `_facade_footprint`, `_facade_front_at`, `_curve_roof_band` (перед `build_facade`); внутри `build_facade` — ветка кривой (стены-полигон `poly_walls`, крыша-полоса, окна по кривой, цоколь-полигон, pset-поля)
- Test: `tests/test_threed.py` — новая `test_build_facade_curve`

**Interfaces:**
- Consumes: `scene["curve"]` из Task 1 (ключи выше).
- Produces:
  - `_facade_ztop(curve, w, H)` → `[(x, z), …]` (25 точек, x от −w/2 до w/2) или `None`;
  - `_facade_footprint(w, d, bend, end_l, end_r, scale=1.0)` → `[[x, y], …]` (центр-фрейм, CCW);
  - `_facade_front_at(curve, w, d, x)` → `(y, rot_deg)`;
  - IFC: при curve стены этажа — `CONCEPTUAL_STOREY` с профилем >4 точек; крыша-полоса — `CONCEPTUAL_ROOF` с именем `Крыша-полоса`; pset `FacadeModel` получает `Curve`-строку.

- [ ] **Step 1: failing-тест**

```python
def test_build_facade_curve(tmp_path=None):
    import ifcopenshell
    from threed.threed_scenarios import validate_facade
    from threed.threed_build import build_facade, _facade_footprint, _facade_ztop
    out = Path(tmp_path or tempfile.mkdtemp())
    scene, warn = validate_facade({
        "storeys": 1, "width_m": 40.0, "depth_m": 12.0,
        "windows": {"rows": 2, "cols": 16, "w_m": 1.6, "h_m": 2.2},
        "curve": {"silhouette": "wave", "amplitude_m": 1.2, "wavelength_m": 10.0,
                  "plan_bend_m": 3.0, "end_left": "round"}})
    ifc, prev = out / "wave.ifc", out / "wave_preview.png"
    build_facade(scene, ifc, prev, {})
    assert ifc.is_file() and prev.is_file()
    m = ifcopenshell.open(str(ifc))
    names = [p.Name for p in m.by_type("IfcBuildingElementProxy")]
    assert any("Крыша-полоса" in (nm or "") for nm in names)
    # стены-полигон: профиль этажа > 4 точек (парабола), окна гнутой посадки
    profs = m.by_type("IfcArbitraryClosedProfileDef")
    storey_prof_pts = 0
    for p in profs:
        if "Стены" in (p.ProfileName or ""):
            # OuterCurve — IfcPolyline; точек на 1 больше сегментов
            storey_prof_pts = len(p.OuterCurve.Points)
    assert storey_prof_pts > 4
    # хелперы: волна выше прямой в пике, контур с круглым торцем шире w
    ztop = _facade_ztop(scene["curve"], 40.0, 5.0)
    assert max(z for _, z in ztop) > 5.0 and min(z for _, z in ztop) < 5.0
    fp = _facade_footprint(40.0, 12.0, 0.0, "flat", "round")
    assert max(x for x, _ in fp) > 20.0            # полукруг за x=w/2
    fp_flat = _facade_footprint(40.0, 12.0, 0.0, "flat", "flat")
    assert abs(max(x for x, _ in fp_flat) - 20.0) < 1e-9
    # дуга: y фронта в центре больше (ближе к камере), на краях = -d/2
    from threed.threed_build import _facade_front_at
    y_mid, rot_mid = _facade_front_at(scene["curve"], 40.0, 12.0, 0.0)
    y_edge, rot_edge = _facade_front_at(scene["curve"], 40.0, 12.0, 19.0)
    assert y_mid > -6.0 and abs(rot_mid) < 1e-9
    assert abs(y_edge - (-6.0 + 3.0 * (1 - (2 * 19.0 / 40.0) ** 2))) < 1e-9
    assert abs(rot_edge) > 0.0
    # taper: этаж 2 уже этажа 1 (клампы гарантируют различие профилей)
    scene2, _ = validate_facade({
        "storeys": 3, "width_m": 30.0, "depth_m": 10.0,
        "curve": {"taper_pct": 40}})
    ifc2 = out / "taper.ifc"
    build_facade(scene2, ifc2, out / "taper_preview.png", {})
    m2 = ifcopenshell.open(str(ifc2))
    widths = []
    for p in m2.by_type("IfcArbitraryClosedProfileDef"):
        if "Стены" in (p.ProfileName or ""):
            widths.append(max(pt.Coordinates[0] for pt in p.OuterCurve.Points)
                          - min(pt.Coordinates[0] for pt in p.OuterCurve.Points))
    assert len(widths) == 3 and widths[0] > widths[-1]
    print("test_build_facade_curve OK")
```

Вверху тест-файла уже есть `from pathlib import Path`; если нет `import tempfile` — добавить в функцию `import tempfile`.

- [ ] **Step 2: Run** → FAIL: `ImportError: cannot import name '_facade_footprint'`.

- [ ] **Step 3: реализация**

3a. Модульные хелперы перед `build_facade` (после `_facade_grid`):

```python
def _facade_ztop(curve, w, H):
    """Линия верха фасада (центр-фрейм): [(x, z), …] или None — прямая."""
    if not curve or not curve.get("silhouette"):
        return None
    n = 24
    xs = [-w / 2 + w * i / n for i in range(n + 1)]
    sil, a = curve["silhouette"], curve["amplitude_m"]
    if sil == "wave":
        lam = curve["wavelength_m"]
        return [(x, H + a * math.sin(2 * math.pi * (x + w / 2) / lam)) for x in xs]
    pts = [(x, H - a + 2 * a * (x + w / 2) / w) for x in xs]
    return list(reversed(pts)) if sil == "slope_down" else pts


def _facade_footprint(w, d, bend=0.0, end_l="flat", end_r="flat", scale=1.0):
    """Контур плана фасада (центр-фрейм, CCW): параболы фронт/тыл (дуга),
    плоские/полукруглые торцы (10 сегментов); scale — taper-этаж."""
    w, d = w * scale, d * scale
    n = 16
    r = d / 2

    def par(x):
        return bend * (1 - (2 * x / w) ** 2)

    pts = [[-w / 2 + w * i / n, -d / 2 + par(-w / 2 + w * i / n)]
           for i in range(n + 1)]
    if end_r == "round":
        pts += [[w / 2 + r * math.cos(t), r * math.sin(t)]
                for t in (math.pi * (k / 10 - 0.5) for k in range(1, 10))]
    else:
        pts.append([w / 2, d / 2])
    pts += [[w / 2 - w * i / n, d / 2 + par(w / 2 - w * i / n)]
            for i in range(1, n + 1)]
    if end_l == "round":
        pts += [[-w / 2 - r * math.cos(t), -r * math.sin(t)]
                for t in (math.pi * (k / 10 - 0.5) for k in range(1, 10))]
    else:
        pts.append([-w / 2, -d / 2])
    return pts


def _facade_front_at(curve, w, d, x):
    """Посадка окна на фронтальную грань: (y, rot_deg). Без дуги — (-d/2, 0)."""
    if not curve or abs(curve.get("plan_bend_m", 0.0)) < 0.05:
        return -d / 2, 0.0
    bend = curve["plan_bend_m"]
    y = -d / 2 + bend * (1 - (2 * x / w) ** 2)
    dydx = bend * (-8 * x / w ** 2)
    return y, math.degrees(math.atan(dydx))
```

`math` в `threed_build.py` уже импортирован (проверить: `import math` в шапке; если нет — добавить).

3b. В `build_facade` после `w, d, fh, n = …` / `sb = ShapeBuilder(model)`:

```python
    curve = data.get("curve")
    ztop = _facade_ztop(curve, w, n * fh) if curve else None

    def poly_walls(name, pts_xy, bh, z, container, otype="CONCEPTUAL_STOREY",
                   color_key="walls"):
        """Этаж-стены экструзией произвольного контура (кривой план/taper)."""
        product = _api("root.create_entity", file=model,
                       ifc_class="IfcBuildingElementProxy",
                       predefined_type="USERDEFINED", name=name)
        product.ObjectType = otype
        profile = _api("profile.add_arbitrary_profile", file=model,
                       profile=[[float(x), float(y)] for x, y in pts_xy], name=name)
        rep = _api("geometry.add_profile_representation", file=model, context=body,
                   profile=profile, depth=bh, cardinal_point=None)
        _api("geometry.assign_representation", file=model, product=product,
             representation=rep)
        _api("spatial.assign_container", file=model, products=[product],
             relating_structure=container)
        matrix = np.eye(4)
        matrix[2, 3] = z
        _api("geometry.edit_object_placement", file=model, product=product,
             matrix=matrix)
        _api("style.assign_representation_styles", file=model,
              shape_representation=rep, styles=[fstyles[color_key]])
        return product

    def footprint_of(scale=1.0, pad=0.0):
        if not curve:
            return None
        return _facade_footprint(w + 2 * pad, d + 2 * pad,
                                 curve.get("plan_bend_m", 0.0),
                                 curve.get("end_left", "flat"),
                                 curve.get("end_right", "flat"), scale)
```

3c. Цикл этажей — ветка кривой (заменить в `for f in range(n):` строку `box(f"Стены · этаж …`):

```python
    for f in range(n):
        fp = None
        if curve:
            sc = 1.0 - (curve.get("taper_pct", 0) / 100.0) * (f + 0.5) / n
            fp = footprint_of(sc)
        if fp is not None:
            poly_walls(f"Стены · этаж {f + 1}", fp, fh, f * fh, storeys[f])
        else:
            box(f"Стены · этаж {f + 1}", w, d, fh, 0.0, 0.0, f * fh, "walls",
                storeys[f], object_type="CONCEPTUAL_STOREY")
```

3d. Окна по кривой (в теле цикла окон заменить ветку rect-окна; arched оставляем как есть — на кривой дуги v1 не тянем):

```python
                else:
                    wx = x + win["w_m"] / 2
                    wy, wrot = _facade_front_at(curve, w, d, wx) if curve \
                        else (-d / 2, 0.0)
                    box(f"Окно Э{f + 1}-{i + 1}", win["w_m"], 0.12, win["h_m"],
                        wx, wy, f * fh + z_in, "glazing", storeys[f],
                        object_type="CONCEPTUAL_WINDOW", rot_deg=wrot)
```

3e. Цоколь и крыша-полоса. Цоколь — после цикла этажей заменить `box("Цоколь", w + 0.2, …)`:

```python
    fp_plinth = footprint_of(1.0, pad=0.1) if curve else None
    if fp_plinth is not None:
        poly_walls("Цоколь", fp_plinth, 0.6, 0.0, building,
                   otype="CONCEPTUAL_PLINTH", color_key="plinth")
    else:
        box("Цоколь", w + 0.2, d + 0.2, 0.6, 0.0, 0.0, 0.0, "plinth", building,
            object_type="CONCEPTUAL_PLINTH")
```

(поэтому `poly_walls` сразу объявляем с параметрами `otype="CONCEPTUAL_STOREY"`, `color_key="walls"` и в 3c вызов не меняется).

Крыша-полоса — после блока `hip/mansard`:

```python
    if ztop:
        th = 0.5
        pts, faces = [], []
        for x, z in ztop:
            pts.extend([[x, -d / 2, z], [x, d / 2, z],
                        [x, -d / 2, z - th], [x, d / 2, z - th]])
        for i in range(len(ztop) - 1):
            j = i * 4

            def q(a, b, c, dd):
                faces.extend([[a, b, c], [a, c, dd]])

            q(j, j + 4, j + 5, j + 1)      # верхняя лента
            q(j + 2, j + 3, j + 7, j + 6)  # нижняя
            q(j, j + 2, j + 6, j + 4)      # фронт-юбка
            q(j + 1, j + 5, j + 7, j + 3)  # тыл-юбка
        q(0, 1, 3, 2)
        last = (len(ztop) - 1) * 4
        q(last, last + 2, last + 3, last + 1)
        _mesh_product(model, body, sb, "Крыша-полоса", pts, faces, building,
                      "CONCEPTUAL_ROOF", fstyles, "roof")
```

3f. pset `FacadeModel` — добавить строку 曲ной (в `_properties(model, building, "FacadeModel", {…})`):

```python
        "Curve": (json.dumps(curve, ensure_ascii=False) if curve else ""),
```

`json` в `threed_build.py` импортирован? Проверить шапку; если нет — `import json` сверху.

- [ ] **Step 4: Run** → PASS (в т.ч. ВСЕ старые фасад-тесты — обратная совместимость).
- [ ] **Step 5: Чекпоинт** — тесты зелёные.

---

### Task 4: Окружение в сборке (общие хелперы facade/scene)

**Files:**
- Modify: `threed/threed_build.py`: модульные `_ctx_tree`/`_ctx_person` (рядом с `_facade_grid`); в `build_scene` блок context-циклов деревьев/людей заменяется вызовами хелперов; в `build_facade` — блок окружения после custom_parts
- Test: `tests/test_threed.py` — новая `test_build_facade_context`

**Interfaces:**
- Consumes: `scene["context"]` из Task 2.
- Produces: `_ctx_tree(mk, idx, tr)` / `_ctx_person(mk, idx, per)`; колбэк `mk(name, bw, bd, bh, cx, cy, z, color_key, object_type, rot_deg=0.0)` (сигнатура = `boxx` из `build_scene`). Фасадные IFC: `CONCEPTUAL_TREE` ×2 на дерево, `CONCEPTUAL_PERSON`, `CONCEPTUAL_MASS` (фоновые дома, имя `Фоновый дом NN`); цвета через `_ensure_style`.

- [ ] **Step 1: failing-тест**

```python
def test_build_facade_context():
    import ifcopenshell
    from threed.threed_scenarios import validate_facade
    from threed.threed_build import build_facade
    out = Path(tempfile.mkdtemp())
    scene, _ = validate_facade({
        "storeys": 2, "width_m": 40.0, "depth_m": 12.0,
        "context": {"trees": [{"x_m": 5, "y_m": 15, "h_m": 8, "crown_d_m": 4}],
                    "people": [{"x_m": 20, "y_m": -4, "h_m": 1.75}],
                    "background_buildings": [
                        {"x_m": 10, "y_m": 30, "w_m": 25, "d_m": 15, "h_m": 30}]}})
    ifc = out / "ctx.ifc"
    build_facade(scene, ifc, out / "ctx_preview.png", {})
    m = ifcopenshell.open(str(ifc))
    ot = [p.ObjectType for p in m.by_type("IfcBuildingElementProxy")]
    assert ot.count("CONCEPTUAL_TREE") == 2          # ствол + крона
    assert ot.count("CONCEPTUAL_PERSON") == 1
    assert ot.count("CONCEPTUAL_MASS") == 1
    assert any((p.Name or "").startswith("Фоновый дом")
               for p in m.by_type("IfcBuildingElementProxy"))
    print("test_build_facade_context OK")
```

- [ ] **Step 2: Run** → FAIL: `assert 0 == 2`.

- [ ] **Step 3: реализация**

3a. Модульные хелперы (перед `build_facade`):

```python
def _ctx_tree(mk, idx, tr):
    """Дерево-прокси (ствол+крона) через колбэк mk — общий для facade/scene."""
    h, crown = float(tr["h_m"]), float(tr.get("crown_d_m", 3.0))
    mk(f"Дерево {idx} · ствол", 0.3, 0.3, h * 0.4, tr["x_m"], tr["y_m"], 0.0,
       "trunk", "CONCEPTUAL_TREE")
    mk(f"Дерево {idx} · крона", crown, crown, h * 0.6, tr["x_m"], tr["y_m"],
       h * 0.4, "tree", "CONCEPTUAL_TREE")


def _ctx_person(mk, idx, per):
    """Человек-прокси через колбэк mk — общий для facade/scene."""
    mk(f"Человек {idx}", 0.5, 0.3, 1.7, per["x_m"], per["y_m"],
       per.get("z_m", 0.0), "person", "CONCEPTUAL_PERSON")
```

3b. `build_scene`: заменить два цикла (`for t_idx, tr in enumerate(ctx.get("trees"…)` и `for p_idx, per in enumerate(ctx.get("people"…)`) на:

```python
    for t_idx, tr in enumerate(ctx.get("trees", []), start=1):
        _ctx_tree(boxx, t_idx, tr)
    for p_idx, per in enumerate(ctx.get("people", []), start=1):
        _ctx_person(boxx, p_idx, per)
```

(поведение идентично; `boxx` имеет сигнатуру колбэка — cars/furniture не трогаем.)

3c. `build_facade` — блок после custom_parts, до `_properties(model, building, "FacadeModel"…)`:

```python
    # --- v2: окружение (context: деревья/люди/фоновые дома) ---
    ctx = data.get("context")
    if ctx:
        _ensure_style(model, fstyles, "trunk", "#8a6b4f")
        _ensure_style(model, fstyles, "tree", "#5d8a4a")
        _ensure_style(model, fstyles, "person", "#d4a373")

        def ctx_mk(name, bw, bd, bh, cx, cy, z, color_key, otype, rot_deg=0.0):
            # x контекста — от левой кромки фасада; y: 0 = линия фасада
            box(name, bw, bd, bh, cx - w / 2, cy - d / 2, z, color_key, building,
                object_type=otype, rot_deg=rot_deg)

        for t_idx, tr in enumerate(ctx.get("trees") or [], start=1):
            _ctx_tree(ctx_mk, t_idx, tr)
        for p_idx, per in enumerate(ctx.get("people") or [], start=1):
            _ctx_person(ctx_mk, p_idx, per)
        for b_idx, bb in enumerate(ctx.get("background_buildings") or [], start=1):
            hex_c = bb.get("color") if str(bb.get("color", "")).startswith("#") else None
            ck = _ensure_style(model, fstyles, f"bgb{b_idx:02d}",
                               hex_c or "#c3c9cf")
            ctx_mk(f"Фоновый дом {b_idx:02d}", bb["w_m"], bb["d_m"], bb["h_m"],
                   bb["x_m"], bb["y_m"], 0.0, ck, "CONCEPTUAL_MASS")
```

3d. pset `FacadeModel` дополнить: `"Context": (f"trees {len((ctx or {}).get('trees') or [])}, people …"` — аккуратно: переменная `ctx` определена выше pset; строка:

```python
        "ContextTrees": len((data.get("context") or {}).get("trees") or []),
        "ContextPeople": len((data.get("context") or {}).get("people") or []),
        "ContextBg": len((data.get("context") or {}).get("background_buildings") or []),
```

- [ ] **Step 4: Run** → PASS (scene-тесты обязаны остаться зелёными — это и есть проверка рефактора).
- [ ] **Step 5: Чекпоинт** — тесты зелёные.

---

### Task 5: Превью, verify-overview и оверлей

**Files:**
- Modify: `threed/threed_build.py` (`_draw_facade_preview` — кривой силуэт + глифы окружения + титул)
- Modify: `threed/threed_verify.py` (`scene_overview` facade-ветка — `curve`/`context`; `render_overlay` facade-ветка — полилиния верха)
- Test: `tests/test_threed.py` — новая `test_facade_curve_preview_overlay`

**Interfaces:**
- Consumes: `_facade_ztop`/`_facade_footprint` из Task 3, `scene["curve"]`/`scene["context"]`.
- Produces: `scene_overview("facade", scene)["curve"]` и `["context"]`; оверлей с кривым верхом.

- [ ] **Step 1: failing-тест**

```python
def test_facade_curve_preview_overlay():
    from PIL import Image
    from threed.threed_scenarios import validate_facade
    from threed.threed_build import build_facade
    from threed.threed_verify import scene_overview, render_overlay
    out = Path(tempfile.mkdtemp())
    scene, _ = validate_facade({
        "storeys": 1, "width_m": 40.0, "depth_m": 12.0,
        "windows": {"rows": 2, "cols": 18, "w_m": 1.6, "h_m": 2.0},
        "curve": {"silhouette": "wave", "amplitude_m": 1.5, "wavelength_m": 12.0,
                  "plan_bend_m": 3.0, "end_left": "round"},
        "context": {"trees": [{"x_m": 5, "y_m": 15, "h_m": 8, "crown_d_m": 4}]}})
    build_facade(scene, out / "pv.ifc", out / "pv.png", {})
    assert (out / "pv.png").is_file()
    ov = scene_overview("facade", scene)
    assert ov["curve"]["silhouette"] == "wave"
    assert abs(ov["curve"]["plan_bend_m"] - 3.0) < 1e-9
    assert ov["context"]["trees"] == 1
    im = render_overlay("facade", scene, Image.new("RGB", (800, 600), "white"))
    assert im.size == (800, 600)
    # без curve — прежний прямой оверлей, overview без ключа curve
    scene_flat, _ = validate_facade({"storeys": 2, "width_m": 20.0})
    ov2 = scene_overview("facade", scene_flat)
    assert "curve" not in ov2 and "context" not in ov2
    render_overlay("facade", scene_flat, Image.new("RGB", (800, 600), "white"))
    print("test_facade_curve_preview_overlay OK")
```

- [ ] **Step 2: Run** → FAIL: `KeyError: 'curve'`.

- [ ] **Step 3: реализация**

3a. `threed_verify.py`, `scene_overview` facade-ветка — после `out["windows"]["skipped_cells"] = …`:

```python
    if isinstance(scene.get("curve"), dict):
        out["curve"] = {k: scene["curve"].get(k) for k in (
            "silhouette", "amplitude_m", "wavelength_m", "taper_pct",
            "plan_bend_m", "end_left", "end_right")}
    if isinstance(scene.get("context"), dict):
        ctx = scene["context"]
        out["context"] = {"trees": len(ctx.get("trees") or []),
                          "people": len(ctx.get("people") or []),
                          "background_buildings":
                              len(ctx.get("background_buildings") or [])}
```

3b. `render_overlay` facade-ветка — после `d.rectangle([x1, y1, x2, y2], …)`:

```python
        curve = scene.get("curve")
        if isinstance(curve, dict) and curve.get("silhouette"):
            # дубль формулы ztop из threed_build (лёгкий модуль без импорта)
            w_m_, st_ = w_m, st * fh
            sx = (x2 - x1) / w_m_
            a = float(curve.get("amplitude_m") or 1.0)
            line = []
            for k in range(25):
                xm = w_m_ * k / 24
                if curve["silhouette"] == "wave":
                    z = st_ + a * math.sin(2 * math.pi * xm
                                           / float(curve.get("wavelength_m") or 12))
                else:
                    z = st_ - a + 2 * a * xm / w_m_
                    if curve["silhouette"] == "slope_down":
                        z = st_ + a - 2 * a * xm / w_m_
                line.append((x1 + xm * sx, y2 - z * sx))
            d.line(line, fill=OVERLAY_COLOR, width=3)
```

3c. `_draw_facade_preview` — силуэт по ztop (заменить первый PlotPolygon стен):

```python
    curve = data.get("curve")
    ztop = _facade_ztop(curve, w, H) if curve else None
    if ztop:
        ax.add_patch(PlotPolygon(
            [[x, 0] for x, _ in ztop] + [[x, z] for x, z in reversed(ztop)],
            facecolor=colors["walls"], edgecolor="#263747", linewidth=1.2))
        top = max(top, max(z for _, z in ztop))
    else:
        ax.add_patch(PlotPolygon([[-w / 2, 0], [w / 2, 0], [w / 2, H], [-w / 2, H]],
                                 facecolor=colors["walls"], edgecolor="#263747",
                                 linewidth=1.2))
```

(переменная `top` сейчас создаётся ниже как `top = H` — перенести инициализацию `top = H` выше силуэта, а старое присваивание удалить.)

Глифы окружения — перед `ax.set_xlim(...)`:

```python
    ctx = data.get("context") or {}
    for t in ctx.get("trees") or []:
        tx = t["x_m"] - w / 2
        ax.add_patch(plt.Circle((tx, t["h_m"] / 2), t["crown_d_m"] / 2,
                                fill=False, ec="#5d8a4a", lw=1.0, alpha=.7))
        top = max(top, t["h_m"])
    for per in ctx.get("people") or []:
        px = per["x_m"] - w / 2
        ax.plot([px], [-0.9], marker="o", ms=3, color="#d4a373")
    for bb in ctx.get("background_buildings") or []:
        bx0 = bb["x_m"] - w / 2 - bb["w_m"] / 2
        ax.add_patch(plt.Rectangle((bx0, 0), bb["w_m"], bb["h_m"],
                                   fill=False, ls=":", ec="#9aa3ad", lw=.8))
        top = max(top, bb["h_m"])
```

Титул — расширить (после `dp = data["depth_m"]`):

```python
    cnote = ""
    if curve:
        bits = []
        if curve.get("silhouette"):
            bits.append(f"силуэт {curve['silhouette']} ±{curve['amplitude_m']:g} м")
        if curve.get("taper_pct"):
            bits.append(f"тейпер {curve['taper_pct']}%")
        if abs(curve.get("plan_bend_m", 0)) > 0.05:
            bits.append(f"дуга {curve['plan_bend_m']:g} м")
        if "round" in (curve.get("end_left"), curve.get("end_right")):
            bits.append("круглые торцы")
        cnote = ", " + ", ".join(bits)
    nctx = sum(len(ctx.get(k) or []) for k in
               ("trees", "people", "background_buildings"))
    if nctx:
        cnote += f", окружение {nctx}"
    ax.set_title(f"3D Design — фасад: {n} эт. × {fh:g} м, {w:g}×{dp:g} м, "
                 f"крыша {data['roof']}{cnote}", fontsize=13)
```

(старый `ax.set_title(…)` заменить на этот блок целиком.)

- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Чекпоинт** — тесты зелёные.

---

### Task 6: Роутерный смок + деплой + HANDOFF

**Files:**
- Modify: `tests/test_threed.py` — `test_generate_impl_facade_curve` (по образцу `test_generate_impl_interior3d`: мок `threed_router._vlm_counted`)
- Modify: `HANDOFF.md` — новый пункт п.64
- Deploy: `setup_threed.py` + рестарт

**Interfaces:**
- Consumes: всё выше; роутер не меняется (facade давно в `SCENARIOS`).

- [ ] **Step 1: failing-тест** — по образцу существующего interior3d-мока: подменяем `threed_router._vlm_counted` → возвращаем JSON-строку сцены фасада с `curve`+`context`, зовём `_generate_impl("facade", "", PIL-картинка 64×64, out_dir=tmp)`; ассерты: `res["name"].startswith("3D_facade")`, IFC-файл существует. (Точный образец — смотреть `test_generate_impl_interior3d` в `tests/test_threed.py`; отличается только сценарием и телом сцены.)

```python
def test_generate_impl_facade_curve():
    from PIL import Image
    import threed.threed_router as R
    scene = {"storeys": 1, "floor_height": 4.0, "width_m": 40.0, "depth_m": 12.0,
             "roof": "flat",
             "windows": {"rows": 2, "cols": 18, "w_m": 1.6, "h_m": 2.2},
             "curve": {"silhouette": "wave", "amplitude_m": 1.2,
                       "wavelength_m": 10.0, "plan_bend_m": 3.0,
                       "end_left": "round"},
             "context": {"trees": [{"x_m": 5, "y_m": 15, "h_m": 8,
                                    "crown_d_m": 4}]},
             "colors": {"walls": "#d9dde3", "roof": "#b9c1cb",
                        "plinth": "#92989f"}}
    calls = {"n": 0}

    def fake_vlm(system, prompt, image_url, model):
        calls["n"] += 1
        return json.dumps(scene, ensure_ascii=False)

    orig = R._vlm_counted
    R._vlm_counted = fake_vlm
    try:
        out = Path(tempfile.mkdtemp())
        img = Image.new("RGB", (64, 64), (120, 140, 160))
        res = R._generate_impl("facade", "", img, out_dir=out)
    finally:
        R._vlm_counted = orig
    assert res["name"].startswith("3D_facade")
    assert (out / res["name"]).is_file()
    assert calls["n"] >= 1
    print("test_generate_impl_facade_curve OK")
```

(`import json` в тест-файле есть; `_generate_impl` вызовет и verify-этап — мок вернёт ту же сцену-строку на промпт судьи, вердикт будет ok=None — генерацию это не роняет.)

- [ ] **Step 2: Run** → FAIL (verify-этап упадёт молча — если генерация всё же прошла, ассерт падает на curve-элементах; добиваемся PASS после правок Task 3-5 — фактически этот тест зелёный уже после Task 5, здесь он регрессионный).

- [ ] **Step 3: деплой**

```
venv\Scripts\python.exe tests\test_threed.py          # ALL OK
venv\Scripts\python.exe setup_threed.py
powershell -NoProfile -ExecutionPolicy Bypass -File launch\_restart_server.ps1
curl -s -o NUL -w "%{http_code}" http://127.0.0.1:9090/api/v1/threed/model   # 303 (siteauth) = сервер жив
```

- [ ] **Step 4: HANDOFF** — новый пункт: «64. 3D Design: криволинейные фасады + окружение (curve/context)» — кратко: контракт, валидация, геометрия (футпринт-экструзия, крыша-полоса мешем — волна невыпуклая, hull нельзя), общий контекст-хелпер facade/scene, превью/оверлей/overview, тесты, деплой; ссылка на спеку и план.

- [ ] **Step 5: живая проверка** — пользователь: 3D Design → Facade → фото павильона → Generate; в дампе `data/ifc/_threed_last.json` — `scenario=facade`, `image.sha1` = свежая картинка, scene_summary с curve/context; превью с волной и деревьями; вьювер — гнутый силуэт.
