# 3D Design: сцена — мебель + люди с высотой + петля для всех сценариев

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** сценарий «Сцена» строит уличную/балконную мебель и людей на высоте (балкон/терраса/крыша), а петля самокоррекции verify работает для всех сценариев, не только фасада.

**Architecture:** расширяем JSON-схему SYSTEM_SCENE (context.furniture + z_m у people/furniture), валидатор нормирует новые поля с дефолтами по типу мебели, сборщик строит боксы CONCEPTUAL_FURNITURE и поднимает людей/мебель на z_m; scene_overview отдаёт верификатору счётчики мебели и «приподнятых» людей; роутер снимает ограничение петли «только facade».

**Tech Stack:** Python (FastAPI-роутер InvokeAI 6.2.0, ifcopenshell API, matplotlib-превью), plain-assert тесты.

**Контекст (почему):** живый кейс 20.09 — фото вида с балкона (женщина в кресле). Дамп `_threed_last.json`: VLM видит людей/мебель, но схема scene их не выражает (people без высоты, мебели нет) — verify выдал «Furniture: built none», петля для scene не запускалась.

## Global Constraints

- Не править `venv/.../site-packages` руками — только `setup_threed.py` (копирует threed/* as-is).
- Тесты: `venv\Scripts\python.exe tests\test_threed.py` (из корня, plain asserts, печать OK).
- Тесты без сети: `R._vlm_list_cached = lambda: []`, VLM мокается заменой `R._call_vlm`.
- Коммит-стиль репо: `feat(3d)/fix(3d)/docs(3d): …` на русском.
- Деплой после правок: `venv\Scripts\python.exe setup_threed.py` → рестарт `_restart_server.ps1`.

---

### Task 1: схема SYSTEM_SCENE + validate_scene — мебель и z_m

**Files:**
- Modify: `threed/threed_scenarios.py` (SYSTEM_SCENE ~738-781, validate_scene 784-941)
- Test: `tests/test_threed.py` (sample_scene_scene 614-646, test_validate_scene 649-672)

**Interfaces:**
- Produces: валидированная сцена scene с `context.people[i].z_m: float` и
  `context.furniture[i] = {"type": str∈FURNITURE_TYPES, "x_m","y_m","z_m","w_m","d_m","h_m","rot_deg": float}`.

- [ ] **Шаг 1: тест-сэмпл и ассерты (упадут)**

`sample_scene_scene()` — context заменить на (человек 1 на балконе главного: этаж 2, fh 3.1 → z_m 3.1, балкон x_m=1.5 от левого края 27 м → центр x=-12, y=0-(7.5+0.6)=-8.1):

```python
        "context": {
            "trees": [{"x_m": 8.0, "y_m": -12.0, "h_m": 7.0, "crown_d_m": 3.5},
                      {"x_m": "bad"}, {"x_m": 15.0, "y_m": -14.0, "h_m": 99,
                                       "crown_d_m": 3.0}],
            "cars": [{"x_m": -6.0, "y_m": -10.0, "rot_deg": 15}],
            "people": [{"x_m": -12.0, "y_m": -8.1, "z_m": 3.1}, {"x_m": 6.0, "y_m": -9.5}],
            "furniture": [
                {"type": "lounger", "x_m": -12.0, "y_m": -8.3, "z_m": 3.1,
                 "w_m": 1.8, "d_m": 0.7, "h_m": 0.8, "rot_deg": 0},
                {"type": "bench", "x_m": 10.0, "y_m": -10.0, "z_m": 0, "rot_deg": 30},
                {"type": "fountain"},
                {"x_m": "bad"},
            ],
        },
```

`test_validate_scene()` — после `people` добавить:

```python
    assert "furniture" in SYSTEM_SCENE and "z_m" in SYSTEM_SCENE
    assert out["context"]["people"][0]["z_m"] == 3.1
    furn = out["context"]["furniture"]
    assert len(furn) == 3                       # 'bad' выкинут
    assert furn[0]["type"] == "lounger" and furn[0]["z_m"] == 3.1
    assert furn[1]["w_m"] == 1.8 and furn[1]["d_m"] == 0.5 and furn[1]["h_m"] == 0.45
    assert furn[2]["type"] == "other"           # fountain -> other + warning
    assert any("fountain" in w for w in warn)
```

- [ ] **Шаг 2: прогнать** `venv\Scripts\python.exe tests\test_threed.py` → test_validate_scene FAIL (KeyError z_m / len(furn)!=3).

- [ ] **Шаг 3: реализация**

SYSTEM_SCENE, блок `"context"` заменить на:

```
 "context": {
   "trees": [{"x_m": <>, "y_m": <>, "h_m": <5-15>, "crown_d_m": <2-6>}],
   "cars": [{"x_m": <>, "y_m": <>, "rot_deg": <heading; 0 = along X>}],
   "people": [{"x_m": <>, "y_m": <>, "z_m": <base height above ground, m:
     0 = standing on the ground; on a balcony/terrace/roof = slab level,
     i.e. (floor-1) * floor_height of that building>}],
   "furniture": [{"type": "bench"|"chair"|"lounger"|"table"|"sofa"|"umbrella"|
       "planter"|"other", "x_m": <>, "y_m": <>, "z_m": <same as people>,
     "w_m": <width, m>, "d_m": <depth, m>, "h_m": <height, m>,
     "rot_deg": <0 = along X>}]
 }
```

Rules — добавить два правила перед «The USER PROMPT overrides…»:

```
- Street/yard/balcony furniture (benches, lounge chairs, tables, umbrellas,
  planters): list EACH visible item in context.furniture with realistic sizes
  (bench 1.8 x 0.5 x 0.45, chair 0.6 x 0.6 x 0.9, lounger 1.8 x 0.7 x 0.8,
  table 0.8 x 0.8 x 0.75, umbrella crown 2.0 x 2.0 x 2.2). Do NOT skip items
  on balconies/terraces.
- A person or furniture item ON a balcony/terrace/roof: keep x_m/y_m on that
  slab and set z_m to the slab level, e.g. floor 3 with floor_height 3.2 ->
  z_m = 6.4. Ground items: z_m = 0.
```

Модульный словарь перед validate_scene:

```python
FURNITURE_TYPES = {  # сцена: тип уличной мебели -> дефолты (w_m, d_m, h_m)
    "bench": (1.8, 0.5, 0.45), "chair": (0.6, 0.6, 0.9),
    "lounger": (1.8, 0.7, 0.8), "table": (0.8, 0.8, 0.75),
    "sofa": (2.0, 0.9, 0.8), "umbrella": (2.0, 2.0, 2.2),
    "planter": (0.5, 0.5, 0.5), "other": (0.8, 0.8, 0.8),
}
```

validate_scene: `ctx = {"trees": [], "cars": [], "people": [], "furniture": []}`;
в цикле people добавить `"z_m": _clamp(z, 0.0, 90.0)` (z из `it.get("z_m", 0.0)`, NaN→0, как x/y);
после people — парсинг furniture (лимит 40): тип из FURNITURE_TYPES иначе `other`+warning,
w/d/h через `_facade_float(..., дефолт из FURNITURE_TYPES, 0.1/0.1/0.05..8.0/8.0/3.5, "furniture.*", warnings)`,
x/y кламп ±150, z кламп 0..90, rot кламп ±180 (NaN→0).

- [ ] **Шаг 4: прогнать тесты** → test_validate_scene OK, остальные не тронуты.
- [ ] **Шаг 5:** `git add threed/threed_scenarios.py tests/test_threed.py && git commit -m "feat(3d): сцена — мебель и высота людей в схеме/валидаторе (п.46, задача 1)"`

### Task 2: build_scene + превью — CONCEPTUAL_FURNITURE и z

**Files:**
- Modify: `threed/threed_build.py` (SCENE_COLORS 1074, build_scene 1106-1278, _draw_scene_preview 1281+)
- Test: `tests/test_threed.py` (test_build_scene 675-724)

**Interfaces:**
- Consumes: сцена из Task 1 (`ctx["furniture"]`, `people[i]["z_m"]`).

- [ ] **Шаг 1: ассерты в test_build_scene** — после CONCEPTUAL_PERSON:

```python
    assert by_type.get("CONCEPTUAL_FURNITURE") == 3
    # человек 1 стоит на балконе главного: низ фигуры z = (2-1)*3.1
    pers = [p for p in proxies if p.ObjectType == "CONCEPTUAL_PERSON"]
    p1 = next(p for p in pers if (p.Name or "").startswith("Человек 1"))
    assert abs(get_local_placement(p1.ObjectPlacement)[2, 3] - 3.1) < 1e-6
    # ...в блоке SceneModel:
    assert sm.get("Furniture") == 3
```

(get_local_placement уже импортирован в тесте выше.)

- [ ] **Шаг 2: прогнать** → FAIL (0 != 3).

- [ ] **Шаг 3: реализация**

SCENE_COLORS + `"furniture": "#a4703f",`.

build_scene:
- человек: `boxx(f"Человек {p_idx}", 0.5, 0.3, 1.7, per["x_m"], per["y_m"], per.get("z_m", 0.0), "person", "CONCEPTUAL_PERSON")`
- после людей:

```python
    for f_idx, fu in enumerate(ctx.get("furniture", []), start=1):
        boxx(f"Мебель {f_idx} · {fu['type']}", fu["w_m"], fu["d_m"], fu["h_m"],
             fu["x_m"], fu["y_m"], fu.get("z_m", 0.0), "furniture",
             "CONCEPTUAL_FURNITURE", rot=fu.get("rot_deg", 0.0))
```

- земля: `all_xy` — к перечню контекста добавить `+ ctx.get("furniture", [])`;
- SceneModel-псет: `"Furniture": len(ctx.get("furniture", [])),` после Cars.

_draw_scene_preview — после машин, перед людьми:

```python
    for fu in ctx.get("furniture", []):
        rot = fu.get("rot_deg", 0.0) or 0.0
        tr = matplotlib.transforms.Affine2D().rotate_deg_around(
            fu["x_m"], fu["y_m"], rot) + ax.transData
        rect = Rectangle((fu["x_m"] - fu["w_m"] / 2, fu["y_m"] - fu["d_m"] / 2),
                         fu["w_m"], fu["d_m"], facecolor="#a4703f",
                         edgecolor="#5e3d1f", alpha=.9)
        rect.set_transform(tr)
        ax.add_patch(rect)
```

- [ ] **Шаг 4: прогнать тесты** → OK.
- [ ] **Шаг 5:** `git commit -m "feat(3d): сцена — сборка мебели и людей на высоте + превью (п.46, задача 2)"`

### Task 3: verify — мебель и «приподнятые» люди в обзоре сцены

**Files:**
- Modify: `threed/threed_verify.py` (SYSTEM_VERIFY 23-42, scene_overview 86-96)
- Test: `tests/test_threed.py` (новый `test_scene_overview_furniture`, вызов в `__main__`)

**Interfaces:**
- Consumes: валидированная сцена Task 1. Produces: scene_overview("scene")["context"]["furniture"] = {type: count}, ["people_elevated"] = int.

- [ ] **Шаг 1: тест (упадёт)**

```python
def test_scene_overview_furniture():
    from threed.threed_scenarios import validate_scene
    from threed.threed_verify import scene_overview
    clean, _ = validate_scene(sample_scene_scene())
    ov = scene_overview("scene", clean)
    assert ov["context"]["furniture"] == {"lounger": 1, "bench": 1, "other": 1}
    assert ov["context"]["people"] == 2 and ov["context"]["people_elevated"] == 1
    print("test_scene_overview_furniture OK")
```

- [ ] **Шаг 2: прогнать** → FAIL (KeyError furniture).

- [ ] **Шаг 3: реализация**

scene_overview, ветка scene — контекст:

```python
        kinds = {}
        for item in (scene.get("context") or {}).get("furniture") or []:
            kinds[item.get("type", "other")] = kinds.get(item.get("type", "other"), 0) + 1
        people = (scene.get("context") or {}).get("people") or []
        ...
            "context": {"trees": len((scene.get("context") or {}).get("trees") or []),
                        "cars": len((scene.get("context") or {}).get("cars") or []),
                        "people": len(people),
                        "people_elevated": sum(
                            1 for p in people if float(p.get("z_m") or 0.0) > 0.05),
                        "furniture": kinds},
```

SYSTEM_VERIFY, правило ok=true: `(trees/cars/people)` → `(trees/cars/people/furniture)`.

- [ ] **Шаг 4: тесты** → OK.
- [ ] **Шаг 5:** `git commit -m "feat(3d): verify сцены видит мебель и людей на высоте (п.46, задача 3)"`

### Task 4: роутер — петля самокоррекции для всех сценариев

**Files:**
- Modify: `threed/threed_router.py` (docstring 118-123, 216-219, комментарий 288-294, строка max_iters 298)
- Test: `tests/test_threed.py` (новый `test_generate_impl_scene_loop`, вызов в `__main__`)

- [ ] **Шаг 1: тест (упадёт: сейчас 1 анализ вместо 2)**

```python
def test_generate_impl_scene_loop():
    """Петля самокоррекции работает и для сцены: ok=False+issues ->
    повторный анализ с CORRECTIONS -> ok=True побеждает (файл _r2)."""
    import threed.threed_router as R
    import threed.threed_verify as V
    from PIL import Image
    R._vlm_list_cached = lambda: []
    scene = sample_scene_scene()
    calls = {"scene": 0, "verify": 0, "saw_corrections": False}
    def call(system, prompt, image_url, model):
        if system.strip().startswith("You are a BIM QA verifier"):
            calls["verify"] += 1
            return json.dumps(
                {"ok": False, "issues": ["Furniture: built none, image shows a balcony lounger."]}
                if calls["verify"] == 1 else {"ok": True, "issues": []})
        calls["scene"] += 1
        if calls["scene"] == 2:
            calls["saw_corrections"] = "CORRECTIONS" in prompt
        return json.dumps(scene, ensure_ascii=False)
    R._call_vlm = call
    TMP.mkdir(exist_ok=True)
    img = Image.new("RGB", (691, 647), (250, 250, 250))
    res = R._generate_impl("scene", "тест петли", img, TMP)
    assert calls["scene"] == 2 and calls["verify"] == 2 and calls["saw_corrections"]
    assert res["name"].endswith("_r2.ifc")
    assert res["verify"]["verdict"]["ok"] is True and res["verify"]["iterations"] == 2
    print("test_generate_impl_scene_loop OK")
```

- [ ] **Шаг 2: прогнать** → FAIL (calls["scene"] == 1).

- [ ] **Шаг 3: реализация**

- `max_iters = 1 + (_verify_iters() if _verify_enabled() else 0)` (убрать `scenario == "facade" and`);
- комментарий блока петли и docstring `_generate_impl`: «петля самокоррекции — все сценарии»;
- docstring `_verify_iters`: «доп. итерации петли самокоррекции (все сценарии): 0..2, дефолт 1».

- [ ] **Шаг 4: все тесты** → OK (существующие scene/facade-тесты: verify-мок вернёт ok=None → гейт не сработает).
- [ ] **Шаг 5:** `git commit -m "feat(3d): петля самокоррекции для всех сценариев, не только фасада (п.46, задача 4)"`

### Task 5: деплой + живой прогон по фото пользователя + HANDOFF

**Files:**
- Modify: `HANDOFF.md` (новый п.46)
- Deploy: `setup_threed.py`, рестарт `_restart_server.ps1`

- [ ] **Шаг 1:** `venv\Scripts\python.exe setup_threed.py` → «Файлы threed развернуты».
- [ ] **Шаг 2:** живой прогон: `_generate_impl("scene", "сделай точно по фото", img)` на фото вида с балкона (кэш-копия), затем разбор `data/ifc/_threed_last.json`: в history/scene_summary — furniture counts, people/people_elevated; имя победителя. Успех = мебель построена (built CONCEPTUAL_FURNITURE > 0) или, при игноре VLM, понятное усиление правила промпта.
- [ ] **Шаг 3:** рестарт сервера `_restart_server.ps1`, smoke: GET /api/v1/threed/model (с cookie devbim_auth из CREDENTIALS базовой компании) отвечает 200.
- [ ] **Шаг 4:** HANDOFF п.46 (кратко: что/файлы/тесты/грабли) + `git commit -m "docs(3d): п.46 — сцена: мебель, люди на высоте, петля всех сценариев"`.
