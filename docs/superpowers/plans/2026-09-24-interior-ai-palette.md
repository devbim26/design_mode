# Различимая палитра интерьера + режим «AI-палитра» во вьювере — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** стены интерьера перестают сливаться: в IFC цвет стены кодирует тип (наружная/перегородка) и ориентацию, во вьювере появляется режим «AI-палитра» с плоской покраской граней по нормалям и автокопированием легенды в промт.

**Architecture:** два уровня. (1) Сборщик `build_interior` красит каждую стену стилем из `INTERIOR_WALL_PALETTE` (тон ext/int × 4 сектора ориентации), двери — один стиль `Door`, окна — `Window` с Transparency 0.55; легенда едет в pset и превью. (2) `ifcviewer.html` получает кнопку «🎨»: обход мешей `model.object`, подмена материала на MeshBasicMaterial + onBeforeCompile (цвет по геометрической нормали грани через dFdx/dFdy в мировых координатах); меши-«оболочка» опознаются по hex материала из палитры сборщика (наружные — тёмный вариант), прозрачные (окна) и мебель/двери не трогаются; чужие модели без совпадений красятся целиком светлым. Классификация НЕ использует внутренности @thatopen — только three.js поверх `model.object`.

**Tech Stack:** Python (ifcopenshell API высокого уровня, как в текущем `threed_build.py`), matplotlib (превью), three.js r182 из `thatopen.mjs` (MeshBasicMaterial, onBeforeCompile), plain-assert тесты репозитория.

**Спека:** `docs/superpowers/specs/2026-09-24-interior-ai-palette-design.md` (обязательна к прочтению).

## Global Constraints

- Ветка `interior`; коммиты в стиле истории (`feat(threed): …`, по-русски, с номером пункта HANDOFF — здесь «п.54»).
- Тесты: `PYTHONUTF8=1 venv/Scripts/python.exe tests/<имя>.py` из корня репозитория (plain asserts, печать OK).
- НИКОГДА не править `venv/Lib/site-packages/...` руками — только setup-скриптами из корня.
- JS-бандлы приложения НЕ трогаются (риска «белого экрана» нет); меняются только `threed/*.py` (деплой `setup_threed.py`) и `ifc/ifcviewer.html` (деплой `setup_ifcviewer.py`).
- После правки module-скрипта вьювера — `node --check` (допустимы только ошибки исполнения, не синтаксиса).
- Рестарт сервера только `powershell -ExecutionPolicy Bypass -File launch/_restart_server.ps1`.
- Секреты (`.env`, `companies/*`) не коммитить.
- Точные цвета из спеки (hex, верхний регистр): стены ext `#C2765B #C9924F #A98F55 #B58383`, int `#E8C9B8 #E9D9B8 #D6DCC3 #D9D0DC`, дверь `#7A4E35`, окно `#A8D4EA` (Transparency 0.55), slab `#d9d4c8`; палитра вьювера: `#F0A35C #E8D260 #9EC78A #9CC8E0 #F2F2EE #838A93`, тёмный множитель 0.62.

---

### Task 1: Сборщик — палитра стен, двери/окна, pset-легенда, превью

**Files:**
- Modify: `threed/threed_build.py` (INTERIOR_DEFAULT_COLORS ~735, стили ~825, стены ~903-917, проёмы ~919-947, pset ~963, превью ~993-1062)
- Test: `tests/test_threed.py` (новая функция + вызов в `__main__`)

**Interfaces:**
- Consumes: `build_interior(scene, ifc_path, preview_path, meta)`, `validate_interior` (не меняются), `_px_to_m(data, x, y)`.
- Produces: `wall_palette_key(data, wall) -> ("ext"|"int", "X"|"D45"|"Y"|"D135")`; `INTERIOR_WALL_PALETTE: dict[(kind, sector)] -> hex`; `INTERIOR_DEFAULT_COLORS` с ключами `door`/`window` (без `wall`/`opening`); pset `InteriorModel.ColorLegend`. Task 2 использует эти же hex-значения в `AI_SHELL_HEXES`/`AI_EXT_HEXES`.

- [ ] **Step 1: Написать падающий тест**

В `tests/test_threed.py` после `test_build_interior` добавить (функция `sample_interior_scene` уже есть; стены 1/3 идут по X, 2/4 по Y — наружные, 5 по Y — перегородка):

```python
def test_interior_wall_palette():
    import ifcopenshell
    from ifcopenshell.util.element import get_psets
    from threed.threed_build import (build_interior, INTERIOR_WALL_PALETTE,
                                     wall_palette_key, INTERIOR_COLOR_LEGEND)

    scene = sample_interior_scene()
    # сектор в МЕТРАХ плана (Y-флип учтён), ось двунаправленная -> 4 корзины
    assert wall_palette_key(scene, scene["walls"][0]) == ("ext", "X")   # [2,2]->[38,2]
    assert wall_palette_key(scene, scene["walls"][1]) == ("ext", "Y")   # [38,2]->[38,28]
    assert wall_palette_key(scene, scene["walls"][4]) == ("int", "Y")   # перегородка
    diag = dict(scene)
    diag["walls"] = [{"points_px": [[0, 0], [10, 10]], "thickness_m": 0.2,
                      "exterior": False}]
    assert wall_palette_key(diag, diag["walls"][0]) == ("int", "D45")

    TMP.mkdir(exist_ok=True)
    ifc = TMP / "3D_interior_palette.ifc"
    prev = TMP / "3D_interior_palette_preview.png"
    build_interior(scene, ifc, prev, {"Scenario": "interior", "Prompt": "тест",
                                      "Model": "test/model", "Source": "3D Design"})
    assert ifc.is_file() and prev.is_file()

    m = ifcopenshell.open(str(ifc))

    def style_name(product):
        item = product.Representation.Representations[0].Items[0]
        return item.StyledByItem[0].Styles[0].Name

    walls = m.by_type("IfcWall")
    assert len(walls) == 5
    names = sorted(w.Name for w in walls)
    assert any("наружная В-З" in n for n in names), names
    assert any("перегородка С-Ю" in n for n in names), names
    assert not any("нар." in n for n in names), "старый суффикс «нар.» должен уйти"
    # каждой стене — свой стиль по типу×ориентации
    assert {style_name(w) for w in walls} == {"WallExtX", "WallExtY", "WallIntY"}

    # двери — один стиль, окна — голубые полупрозрачные
    proxies = m.by_type("IfcBuildingElementProxy")
    doors = [p for p in proxies if p.ObjectType == "CONCEPTUAL_DOOR"]
    wins = [p for p in proxies if p.ObjectType == "CONCEPTUAL_WINDOW"]
    assert len(doors) == 2 and len(wins) == 1
    assert {style_name(p) for p in doors} == {"Door"}
    assert {style_name(p) for p in wins} == {"Window"}
    shading = [s for s in m.by_type("IfcSurfaceStyleShading")
               if s.SurfaceColour.Name == "window"][0]
    assert abs(shading.Transparency - 0.55) < 1e-6, "окно должно быть прозрачным"
    col = shading.SurfaceColour
    assert abs(col.Red - 0xA8 / 255) < 0.02 and abs(col.Blue - 0xEA / 255) < 0.02 \
        and abs(col.Green - 0xD4 / 255) < 0.02, "окно должно быть голубым #A8D4EA"

    # цвет WallExtX = терракота #C2765B; одноимённые сектора ext/int различаются
    def surf_rgb(style_name_):
        st = [s for s in m.by_type("IfcSurfaceStyle") if s.Name == style_name_][0]
        c = st.Styles[0].SurfaceColour
        return (c.Red, c.Green, c.Blue)
    import matplotlib.colors as _mc
    for name, hexc in (("WallExtX", "#C2765B"), ("WallIntX", "#E8C9B8")):
        want = _mc.to_rgb(hexc)
        got = surf_rgb(name)
        assert all(abs(a - b) < 0.02 for a, b in zip(want, got)), (name, got)
    assert len(INTERIOR_WALL_PALETTE) == 8

    # легенда едет с файлом
    pset = get_psets(m.by_type("IfcBuilding")[0]).get("InteriorModel", {})
    assert INTERIOR_COLOR_LEGEND[:40] in (pset.get("ColorLegend") or ""), pset
    print("test_interior_wall_palette OK")
```

И в `if __name__ == "__main__":` того же файла добавить `test_interior_wall_palette()` с печатью `print("OK test_interior_wall_palette")` по образцу соседних.

- [ ] **Step 2: Прогнать — убедиться, что падает**

```bash
cd "C:\Users\Lenovo\Desktop\проект SOFT_2\Дизайн\InvokeAI\InvokeAI" && PYTHONUTF8=1 venv/Scripts/python.exe tests/test_threed.py
```

Ожидание: `ImportError: cannot import name 'wall_palette_key'` (или падение на первом же ассерте). Остальные тесты файла могут падать тоже (сборщик ещё не правлен) — это нормально для этого шага.

- [ ] **Step 3: Реализовать в threed/threed_build.py**

3a. Заменить `INTERIOR_DEFAULT_COLORS` (строки ~735-740) и добавить палитру стен:

```python
INTERIOR_DEFAULT_COLORS = {
    "slab": "#d9d4c8", "door": "#7A4E35", "window": "#A8D4EA", "room": "#e6ecf2",
    "bed": "#8fa3bf", "sofa": "#7f9b8e", "table": "#c9a227", "chair": "#d4ac9e",
    "wardrobe": "#a58d6f", "kitchen": "#9aa3ad", "bath": "#bfd8e6",
    "toilet": "#e0e4e8", "sink": "#d6e0e8", "lamp": "#f0d68a", "other": "#b8bcc2",
}

# Палитра стен интерьера: тон = наружная/перегородка, оттенок = ориентация
# (4 сектора по 45°, ось двунаправленная). Смежные перпендикулярные стены
# всегда в разных секторах -> всегда разного цвета.
INTERIOR_WALL_PALETTE = {
    ("ext", "X"): "#C2765B", ("ext", "D45"): "#C9924F",
    ("ext", "Y"): "#A98F55", ("ext", "D135"): "#B58383",
    ("int", "X"): "#E8C9B8", ("int", "D45"): "#E9D9B8",
    ("int", "Y"): "#D6DCC3", ("int", "D135"): "#D9D0DC",
}
WALL_SECTOR_LABELS = {"X": "В-З", "D45": "45°", "Y": "С-Ю", "D135": "135°"}
INTERIOR_COLOR_LEGEND = (
    "Стены: наружные — терракота В-З, охра 45°, хаки С-Ю, пыльная роза 135°; "
    "перегородки — пастельные аналоги; двери коричневые; окна голубые "
    "полупрозрачные. Цвет кодирует тип и ориентацию, не материал."
)


def wall_palette_key(data, wall):
    """Ключ стиля стены: (ext|int, сектор). Сектор считается по углу сегмента
    в метрах плана (Y-флип учтён); 180° = та же ось, поэтому 4 корзины."""
    (x1, y1), (x2, y2) = (_px_to_m(data, *wall["points_px"][0]),
                          _px_to_m(data, *wall["points_px"][1]))
    ang = float(np.degrees(np.arctan2(y2 - y1, x2 - x1))) % 180.0
    sector = ("X", "D45", "Y", "D135")[int(round(ang / 45.0)) % 4]
    return ("ext" if wall.get("exterior") else "int"), sector
```

(`wall_palette_key` размещается после `_outline_point_at`, перед `build_interior` — `_px_to_m` уже определён выше.)

3b. В `build_interior` цикл создания стилей (~825-833) — после существующего цикла по `colors` добавить стены и прозрачность окон:

```python
    fstyles = {}
    for key, color in colors.items():
        r, g, b = matplotlib.colors.to_rgb(color)
        sname = {"door": "Door", "window": "Window"}.get(
            key, f"Interior{key.capitalize()}")
        style = _api("style.add_style", file=model, name=sname)
        _api("style.add_surface_style", file=model, style=style,
             ifc_class="IfcSurfaceStyleShading",
             attributes={"SurfaceColour": {"Name": key, "Red": r, "Green": g, "Blue": b},
                         "Transparency": 0.55 if key == "window" else 0.0})
        fstyles[key] = style
    for (kind, sector), color in INTERIOR_WALL_PALETTE.items():
        r, g, b = matplotlib.colors.to_rgb(color)
        style = _api("style.add_style", file=model, name=f"Wall{kind.capitalize()}{sector}")
        _api("style.add_surface_style", file=model, style=style,
             ifc_class="IfcSurfaceStyleShading",
             attributes={"SurfaceColour": {"Name": f"wall-{kind}-{sector}",
                                                "Red": r, "Green": g, "Blue": b},
                         "Transparency": 0.0})
        fstyles[(kind, sector)] = style
```

3c. Цикл стен (~905-917) — имя и стиль по ключу (вместо `ext = " нар." …` и `rbox(f"Стена {idx:02d}{ext}", …, "wall", …)`):

```python
    for idx, wall in enumerate(data["walls"], start=1):
        p1 = _px_to_m(data, *wall["points_px"][0])
        p2 = _px_to_m(data, *wall["points_px"][1])
        dx, dy = p2[0] - p1[0], p2[1] - p1[1]
        length = float(np.hypot(dx, dy))
        wall_geo.append((p1, p2, length))
        if length < 0.05:
            continue
        ang = np.degrees(np.arctan2(dy, dx))
        kind, sector = wall_palette_key(data, wall)
        rbox(f"Стена {idx:02d} {'наружная' if kind == 'ext' else 'перегородка'} "
             f"{WALL_SECTOR_LABELS[sector]}",
             length, wall["thickness_m"], wh,
             (p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2, 0.0, ang,
             (kind, sector), storey, "IfcWall", "CONCEPTUAL_WALL", predefined="USERDEFINED")
```

3d. Проёмы (~945-947): `"opening"` заменить на тип проёма:

```python
        rbox(name, op["width_m"], thickness + 0.06, op["height_m"], cx, cy,
             op["sill_m"], ang, "door" if op["kind"] == "door" else "window",
             storey, "IfcBuildingElementProxy", otype, predefined="USERDEFINED")
```

3e. Pset `InteriorModel` (~963-968): добавить строку легенды:

```python
    _properties(model, building, "InteriorModel", {
        "WallHeight": wh, "ScaleMPerPx": scale,
        "Walls": len(data["walls"]), "Openings": len(data["openings"]),
        "Rooms": len(data["rooms"]), "Furniture": len(data["furniture"]),
        "ApproximateGeometry": True, "Notes": ASSUMPTION_INTERIOR,
        "ColorLegend": INTERIOR_COLOR_LEGEND,
    })
```

3f. Превью `_draw_interior_preview`: в цикле стен (~1001-1004) `facecolor=data["colors"]["wall"]` → `facecolor=INTERIOR_WALL_PALETTE[wall_palette_key(data, wall)]`; в цикле проёмов (~1026-1028) `facecolor=data["colors"]["opening"]` → `facecolor=data["colors"]["door" if op["kind"] == "door" else "window"]`. Перед `fig.tight_layout()` (~1059) добавить легенду с плашками:

```python
    handles = [PlotPolygon([[0, 0], [1, 0], [1, 1], [0, 1]], facecolor=c,
                           edgecolor="#263747", linewidth=0.5)
               for c in INTERIOR_WALL_PALETTE.values()]
    labels = [f"{'нар.' if k == 'ext' else 'перег.'} {WALL_SECTOR_LABELS[s]}"
              for k, s in INTERIOR_WALL_PALETTE]
    fig.legend(handles, labels, loc="lower center", ncol=4, fontsize=7,
               frameon=False, title="Палитра стен (тип × ориентация)")
```

- [ ] **Step 4: Прогнать тесты — проходят**

```bash
cd "C:\Users\Lenovo\Desktop\проект SOFT_2\Дизайн\InvokeAI\InvokeAI" && PYTHONUTF8=1 venv/Scripts/python.exe tests/test_threed.py
```

Ожидание: все функции печатают OK, в конце «ВСЕ ТЕСТЫ OK» (или эквивалент файла). Если `item.StyledByItem` пуст — проверить, что стили навешаны на representation item (сборщик уже делает `geometry.assign_representation(styles=[...])`, как было с `"wall"`).

- [ ] **Step 5: Деплой сборщика и рестарт**

```bash
cd "C:\Users\Lenovo\Desktop\проект SOFT_2\Дизайн\InvokeAI\InvokeAI" && PYTHONUTF8=1 venv/Scripts/python.exe setup_threed.py && powershell -ExecutionPolicy Bypass -File launch/_restart_server.ps1
```

Ожидание: «Файлы threed развернуты» + сервер перезапущен (проверка: `curl -s http://127.0.0.1:9090/api/v1/threed/…` не нужен — роутер статичен; достаточно отсутствия ошибок скрипта).

- [ ] **Step 6: Коммит**

```bash
cd "C:\Users\Lenovo\Desktop\проект SOFT_2\Дизайн\InvokeAI\InvokeAI" && git add threed/threed_build.py tests/test_threed.py && git commit -m "feat(threed): палитра стен интерьера по типу×ориентации, голубые окна-полупрозрачные, двери одним цветом (п.54)"
```

---

### Task 2: Вьювер — режим «AI-палитра» + легенда в буфер

**Files:**
- Modify: `ifc/ifcviewer.html` (CSS ~91, тулбар ~276, `__ifc` ~607-635, слушатель камеры ~411, `loadIfc` ~494, `copyContextToClipboard` ~687-702, новый блок после ~702)
- Test: `tests/test_ifc_sections.py` (две новые функции + вызовы в `__main__`)

**Interfaces:**
- Consumes: hex-палитра Task 1 (`AI_SHELL_HEXES` = 8 стен + `#D9D4C8`; `AI_EXT_HEXES` = 4 наружных), `model.object` (three.js), `embedToast`, `$`, `model` (let), `MeshBasicMaterial`/`Color` (уже импортированы из thatopen.mjs, строка 362).
- Produces: `window.__ifc.palette.{enable,disable,state}` (`state = {on: bool, meshes: number}`); localStorage-ключ `devbim:ifc:aiPalette`; константа `AI_PALETTE_LEGEND` (текст легенды — см. код ниже).

- [ ] **Step 1: Падающие markup/логика-тесты**

В `tests/test_ifc_sections.py` перед `if __name__ == "__main__":` добавить:

```python
def test_ai_palette() -> None:
    s = SRC.read_text(encoding="utf-8")
    assert 'id="btn-palette"' in s, "нет кнопки AI-палитры в тулбаре"
    assert "#toolbar button.active" in s, "нет стиля активной кнопки тулбара"
    js = module_script(s)
    assert 'posX: "#F0A35C"' in js, "нет палитры шести корзин"
    assert "AI_SHELL_HEXES" in js and "AI_EXT_HEXES" in js, "нет hex-наборов оболочки"
    assert "dFdx(vAIWorld)" in js and "dFdy(vAIWorld)" in js, \
        "нет покраски по геометрической нормали грани"
    assert 'localStorage.getItem("devbim:ifc:aiPalette")' in js, "состояние не переживает F5"
    assert "aiPaletteState.on ? AI_PALETTE_LEGEND" in js, "легенда не копируется при снимке"
    assert "if (aiPaletteState.on) aiApply();" in js, "палитра не переживает загрузку модели"
    assert "if (aiPaletteState.on) aiEnsure();" in js, "нет самопроверки подмены при LOD"
    assert "palette: {" in js, "нет отладочного __ifc.palette"


def test_module_syntax() -> None:
    import subprocess
    js = module_script(SRC.read_text(encoding="utf-8"))
    p = BASE / "tests" / "_threed_tmp" / "ifc_module.mjs"
    p.parent.mkdir(exist_ok=True)
    p.write_text(js, encoding="utf-8")
    r = subprocess.run(["node", "--check", str(p)], capture_output=True, text=True)
    assert r.returncode == 0, f"синтаксис module-скрипта: {r.stderr[:400]}"
```

В `__main__` того же файла добавить `test_ai_palette()` / `test_module_syntax()` с печатью по образцу.

- [ ] **Step 2: Прогнать — падают**

```bash
cd "C:\Users\Lenovo\Desktop\проект SOFT_2\Дизайн\InvokeAI\InvokeAI" && PYTHONUTF8=1 venv/Scripts/python.exe tests/test_ifc_sections.py
```

Ожидание: `AssertionError: нет кнопки AI-палитры в тулбаре`; `test_deployed` может падать до деплоя — это нормально, деплой в Step 5.

- [ ] **Step 3: Реализация в ifc/ifcviewer.html**

3a. CSS (после строки `#toolbar button{padding:4px 10px; font-size:12px; font-weight:500}` ~91):

```css
  #toolbar button.active{background:#38BDF8;border-color:#38BDF8;color:#08222e}
```

3b. Кнопка в тулбаре (после `btn-camera`, строка ~276):

```html
      <button id="btn-palette" class="ghost" title="AI-палитра: плоские цвета по нормалям граней (стороны света + вверх/вниз) — снимок для ИИ, где внутренний/наружный угол однозначен; легенда копируется при снимке">🎨</button>
```

3c. В `window.__ifc` (объект ~607-635) добавить строку после `capture:`:

```js
  palette: {
    enable: () => aiSetEnabled(true), disable: () => aiSetEnabled(false),
    get state() { return { ...aiPaletteState }; },
  },
```

3d. Слушатель камеры (строка ~411) — доучёт возврата подмены, если библиотека пересоздаёт меши:

```js
world.camera.controls.addEventListener("update", () => { fragments.core.update(); if (aiPaletteState.on) aiEnsure(); });
```

3e. В `loadIfc` после `fragments.core.update(true);` (строка ~494):

```js
  if (aiPaletteState.on) aiApply();   // AI-палитра переживает загрузку модели
```

3f. `copyContextToClipboard` (строки ~687-689) — дописывать легенду к контексту:

```js
function copyContextToClipboard() {
  const s = [$("person-context").value, aiPaletteState.on ? AI_PALETTE_LEGEND : ""]
    .filter(Boolean).join("\n");
  if (!s) return;
```

(остальное тело без изменений.)

3g. Движок — новым блоком сразу ПОСЛЕ закрывающей `}` функции `copyContextToClipboard` (~строка 702, перед `function updatePromptContext`):

```js
// --- AI-палитра: плоские цвета по нормалям граней (снимки под ИИ-рендер) ---
const AI_PALETTE = { posX: "#F0A35C", negX: "#E8D260", posY: "#9EC78A",
                     negY: "#9CC8E0", posZ: "#F2F2EE", negZ: "#838A93" };
const AI_DARK = 0.62;              // тёмный вариант корзины — наружные стены
// материалы «оболочки» из сборщика интерьеров (hex): совпадение -> красить.
// Наружные стены (AI_EXT_HEXES) — тёмным, перегородки/пол — светлым.
// Совпадений нет (чужая модель) -> красим все непрозрачные меши светлым.
const AI_EXT_HEXES = new Set(["#C2765B", "#C9924F", "#A98F55", "#B58383"]);
const AI_SHELL_HEXES = new Set([...AI_EXT_HEXES,
  "#E8C9B8", "#E9D9B8", "#D6DCC3", "#D9D0DC", "#D9D4C8"]);
const AI_PALETTE_LEGEND =
  "AI-палитра снимка: оранжевый — грань смотрит на восток (+X), жёлтый — на запад (−X), " +
  "зелёный — на север (+Y), голубой — на юг (−Y), белый — вверх, серый — вниз; " +
  "тёмные оттенки — наружные стены, светлые — перегородки и пол. Это служебный код " +
  "ориентации граней, не материалы: перерисуй все поверхности реальными материалами " +
  "с референсов, сохрани геометрию и направления граней.";

const aiPaletteState = { on: false, meshes: 0 };

function aiMaterial(dark) {
  // MeshBasicMaterial + инъекция: цвет = корзина доминирующей оси ГЕОМЕТРИЧЕСКОЙ
  // нормали грани в мировых координатах (dFdx/dFdy) — работает на любой геометрии,
  // инстансинг и клиппинг-плоскости обрабатывает сам three.
  const mat = new MeshBasicMaterial({ color: 0xffffff });
  const cols = Object.values(AI_PALETTE)
    .map((h) => new Color(h).multiplyScalar(dark ? AI_DARK : 1.0));
  mat.onBeforeCompile = (shader) => {
    shader.uniforms.uAICols = { value: cols };
    shader.vertexShader = "varying vec3 vAIWorld;\n" + shader.vertexShader.replace(
      "#include <project_vertex>",
      `#include <project_vertex>
      { vec4 aiwp = vec4(transformed, 1.0);
        #ifdef USE_INSTANCING
          aiwp = instanceMatrix * aiwp;
        #endif
        vAIWorld = (modelMatrix * aiwp).xyz; }`);
    shader.fragmentShader = "varying vec3 vAIWorld;\nuniform vec3 uAICols[6];\n" +
      shader.fragmentShader.replace(
        "#include <color_fragment>",
        `#include <color_fragment>
        { vec3 ain = normalize(cross(dFdx(vAIWorld), dFdy(vAIWorld)));
          vec3 aia = abs(ain); vec3 aic;
          if (aia.x >= aia.y && aia.x >= aia.z) aic = ain.x > 0.0 ? uAICols[0] : uAICols[1];
          else if (aia.y >= aia.z) aic = ain.y > 0.0 ? uAICols[2] : uAICols[3];
          else aic = ain.z > 0.0 ? uAICols[4] : uAICols[5];
          diffuseColor.rgb = aic; }`);
  };
  return mat;
}

const aiMatLight = aiMaterial(false);
const aiMatDark = aiMaterial(true);

function aiFirstMat(o) {
  return Array.isArray(o.material) ? o.material[0] : o.material;
}

function aiApply() {
  if (!model) return;
  aiRestore();
  let shellSeen = false;
  model.object.traverse((o) => {
    if (!o.isMesh) return;
    const m = aiFirstMat(o);
    if (!m) return;
    if (m.transparent || m.opacity < 1) return;   // стекло/окна — как есть
    const hex = m.color ? "#" + m.color.getHexString().toUpperCase() : null;
    if (!hex || !AI_SHELL_HEXES.has(hex)) return;
    shellSeen = true;
    o.userData.aiOriginal = o.material;
    o.material = AI_EXT_HEXES.has(hex) ? aiMatDark : aiMatLight;
    aiPaletteState.meshes++;
  });
  if (!shellSeen) {
    // чужая модель без палитры DevBIM — красим все непрозрачные меши светлым
    model.object.traverse((o) => {
      if (!o.isMesh || o.userData.aiOriginal) return;
      const m = aiFirstMat(o);
      if (!m || m.transparent || m.opacity < 1) return;
      o.userData.aiOriginal = o.material;
      o.material = aiMatLight;
      aiPaletteState.meshes++;
    });
  }
  // сечения (клиппинг) действуют и на подменённые материалы: та же ссылка
  // на плоскости, что у оригинала
  model.object.traverse((o) => {
    if (!o.isMesh || !o.userData.aiOriginal) return;
    const src = Array.isArray(o.userData.aiOriginal) ? o.userData.aiOriginal[0]
                                                     : o.userData.aiOriginal;
    if (src && src.clippingPlanes) o.material.clippingPlanes = src.clippingPlanes;
  });
}

function aiRestore() {
  if (!model) return;
  model.object.traverse((o) => {
    if (o.isMesh && o.userData.aiOriginal) {
      o.material = o.userData.aiOriginal;
      delete o.userData.aiOriginal;
    }
  });
  aiPaletteState.meshes = 0;
}

function aiEnsure() {
  // если библиотека пересоздала меши (LOD) — подмену наводим заново
  if (!model) return;
  let ok = true;
  model.object.traverse((o) => { if (o.isMesh && !o.userData.aiOriginal) ok = false; });
  if (!ok) aiApply();
}

function aiSetEnabled(on) {
  aiPaletteState.on = !!on;
  localStorage.setItem("devbim:ifc:aiPalette", on ? "1" : "0");
  const b = $("btn-palette");
  b.classList.toggle("active", aiPaletteState.on);
  if (aiPaletteState.on) aiApply(); else aiRestore();
}

$("btn-palette").addEventListener("click", () => aiSetEnabled(!aiPaletteState.on));
aiSetEnabled(localStorage.getItem("devbim:ifc:aiPalette") === "1");
```

Пояснение для реализатора: `aiSetEnabled` в конце модуля исполняется при старте — `model` ещё `null`, `aiApply` благополучно выходит по гварду; вызовы из `loadIfc`/`__ifc`/кнопки случаются позже. `aiPaletteState` используется в слушателе камеры (объявленном выше по файлу) — безопасно: слушатель срабатывает только после полной инициализации модуля.

- [ ] **Step 4: Прогнать тесты вьювера**

```bash
cd "C:\Users\Lenovo\Desktop\проект SOFT_2\Дизайн\InvokeAI\InvokeAI" && PYTHONUTF8=1 venv/Scripts/python.exe tests/test_ifc_sections.py
```

Ожидание: все OK, включая новые `test_ai_palette`, `test_module_syntax` и `test_deployed` (после Step 5; до него test_deployed падает «не развернут» — сначала прогнать новые, затем деплой и полный повтор).

- [ ] **Step 5: Деплой вьювера**

```bash
cd "C:\Users\Lenovo\Desktop\проект SOFT_2\Дизайн\InvokeAI\InvokeAI" && PYTHONUTF8=1 venv/Scripts/python.exe setup_ifcviewer.py
```

Затем повторить команду Step 4 — все тесты, включая `test_deployed`, зелёные.

- [ ] **Step 6: Коммит**

```bash
cd "C:\Users\Lenovo\Desktop\проект SOFT_2\Дизайн\InvokeAI\InvokeAI" && git add ifc/ifcviewer.html tests/test_ifc_sections.py && git commit -m "feat(ifcviewer): режим AI-палитры — плоские цвета граней по нормалям + легенда в буфер при снимке (п.54)"
```

---

### Task 3: Живая E2E-проверка (Playwright, ОСНОВНАЯ сессия — браузерные инструменты не делегируются сабагентам)

**Files:**
- Использует: `tests/_threed_tmp/3D_interior_palette.ifc` (артефакт Task 1; интерьерных моделей в `data/ifc/` нет — только фасады)
- Создаёт: `docs/3d-ai-palette-off.png`, `docs/3d-ai-palette-on.png`, `docs/3d-ai-palette-section.png`

**Interfaces:**
- Consumes: сервер на `http://127.0.0.1:9090` (гейт сайта: пароль из `.env` `SITE_PASSWORD`), вкладка IFC (`/ifcviewer.html`), `window.__ifc.palette`.

- [ ] **Step 1: Открыть вьювер и загрузить модель**

Если `tests/_threed_tmp/3D_interior_palette.ifc` нет — собрать (грабля п.40 HANDOFF: фокус-запуск из каталога tests, иначе его затеняет site-packages/tests):
```bash
cd "C:\Users\Lenovo\Desktop\проект SOFT_2\Дизайн\InvokeAI\InvokeAI\tests" && PYTHONUTF8=1 ../venv/Scripts/python.exe -c "from test_threed import test_interior_wall_palette; test_interior_wall_palette()"
```
Браузером: `http://127.0.0.1:9090` → ввод пароля сайта → левая рейка, вкладка «IFC» → файловый ввод → выбрать `3D_interior_palette.ifc`. Ждать статус «Модель загружена».

- [ ] **Step 2: Снимок «до», включить палитру, снимок «после»**

`window.__ifc.palette.state` → `{on:false, meshes:0}`; скриншот `docs/3d-ai-palette-off.png`.
Включить кнопку «🎨» (или `__ifc.palette.enable()`); `state` → `on:true`, `meshes > 0`; скриншот `docs/3d-ai-palette-on.png`. Проверить глазами: соседние стены разных цветов, грани одной стены, смотрящие в разные стороны, различаются; окна остались голубыми и просвечивают; мебель/двери не перекрашены. Повертеть камеру (drag) — цвета не сбрасываются (проверка aiEnsure).

- [ ] **Step 3: Сечения и снимок в галерею**

`__ifc.addSection('h')` → скриншот `docs/3d-ai-palette-section.png` — сечение режет и в палитре (клиппинг не потерян). Выключить сечения («✕ сечения»/«Удалить все»). Кликнуть «💾 To Assets» → тост содержит «copied»/легенду (clipboard в headless недоступен для чтения — достаточно тоста и `state.on`). Выключить палитру — исходные цвета вернулись.

- [ ] **Step 4: Зафиксировать результат**

Ошибок консоли, связанных с вьювером (фильтр redux-persist-шума — он был до), быть не должно. Скриншоты остались в `docs/`. Коммита нет (скриншоты уйдут в коммит Task 4).

---

### Task 4: HANDOFF + финальный прогон + коммит

**Files:**
- Modify: `HANDOFF.md` (новый п.54 в «Что реализовано»)
- Коммит: скриншоты `docs/3d-ai-palette-*.png`

**Interfaces:**
- Consumes: всё выше; номера пунктов HANDOFF (последний — 53).

- [ ] **Step 1: Полный прогон тестов**

```bash
cd "C:\Users\Lenovo\Desktop\проект SOFT_2\Дизайн\InvokeAI\InvokeAI" && PYTHONUTF8=1 venv/Scripts/python.exe tests/test_threed.py && PYTHONUTF8=1 venv/Scripts/python.exe tests/test_ifc_sections.py
```

Ожидание: оба файла — все OK.

- [ ] **Step 2: Пункт в HANDOFF.md**

Добавить п.54 в конец раздела «Что реализовано» (перед «Ключевые технические детали»), в стиле соседних пунктов — кратко: суть (палитра ext/int × 4 сектора в build_interior, стиль WallExt*/WallInt*, двери Door, окна Window Transparency 0.55, ColorLegend в pset, легенда в превью), режим 🎨 во вьювере (MeshBasicMaterial+onBeforeCompile, нормаль dFdx/dFdy, hex-классификация мешей по палитре сборщика, окна/мебель не трогаем, чужие модели — сплошной светлый вариант, aiEnsure на LOD, клиппинг-плоскости копируются), легенда в буфер при снимке (дописывается к BIM-контексту), отладка `__ifc.palette`, тесты, скриншоты. Отметить грабли, найденные при реализации (если будут).

- [ ] **Step 3: Финальный коммит**

```bash
cd "C:\Users\Lenovo\Desktop\проект SOFT_2\Дизайн\InvokeAI\InvokeAI" && git add HANDOFF.md docs/3d-ai-palette-off.png docs/3d-ai-palette-on.png docs/3d-ai-palette-section.png && git commit -m "docs(threed): HANDOFF п.54 — различимая палитра интерьера и AI-палитра вьювера + скриншоты"
```

(Если E2E делал дополнительные скриншоты — добавить и их. Коммит `--only` не нужен: перечислены конкретные файлы, чужие изменения `imagerouter_router.py`/`tests/test_reference_types.py` в индекс не попадут.)
