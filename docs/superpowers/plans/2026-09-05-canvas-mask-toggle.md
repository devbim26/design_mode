# Тумблер «Маска / Слой» на холсте — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Плавающая пилюля «Маска / Слой» на холсте InvokeAI, показывающая и переключающая слой, которым рисует кисть (inpaint-маска ↔ растровый слой).

**Architecture:** Мост в App-бандле (одна строка: `window.__devbimCanvasBridge={getManager:()=>ru.get()}` перед якорем `const cue=u.memo(`) + отдельный скрипт-виджет `devbim-mask-toggle.js`, деплоимый в `dist/` и подключаемый в `index.html`. Виджет читает redux-стор канваса через `manager.stateApi.store` (подписка + тик 500 мс), выделяет слои диспатчем `canvas/entitySelected`, создаёт — через `stateApi.addInpaintMask/addRasterLayer`.

**Tech Stack:** Python-патчер `setup_imagerouter.py` (проектные паттерны идемпотентных патчей), чистый ES5-JS без зависимостей, тесты plain-asserts, `node --check`/`node -e import` для проверки бандлов.

**Спека:** `docs/superpowers/specs/2026-09-05-canvas-mask-toggle-design.md`

## Global Constraints

- Репо: `C:\Users\Lenovo\Desktop\проект SOFT_2\Дизайн\InvokeAI\InvokeAI`, ветка `feature/ifc-viewer`. Секреты (`.env`, `companies/*`, `companies.json`) не коммитить.
- Файлы в `venv/.../site-packages` править ТОЛЬКО через `setup_imagerouter.py`; все патчи идемпотентны (повторный запуск — «пропуск»), бэкапы `*.imagerouter-bak` / `index.html.masktoggle-bak` создаются один раз.
- После любого патча JS-бандла обязательна проверка: `node -e "import('file:///...App-*.js').catch(e=>console.log(e.message))"` — допустима ТОЛЬКО рантайм-ошибка (`document is not defined`), не SyntaxError.
- Якорь `const cue=u.memo(` должен оставаться в бандле после патча (его использует `setup_ifcviewer.py`).
- Команды python — из корня проекта: `venv/Scripts/python.exe ...` (Git Bash) с `PYTHONUTF8=1` для запусков сервера (тесты не трогают yaml — можно без).
- Сервер перезапускать только `_restart_server.ps1` (WMI, отсоединённо).

---

### Task 1: Виджет-тумблер `imagerouter/devbim_mask_toggle.js`

**Files:**
- Create: `imagerouter/devbim_mask_toggle.js`

**Interfaces:**
- Consumes: `window.__devbimCanvasBridge.getManager()` (мост из Task 3), `window.__devbimGetTab()` (уже существует, патч админ-гейта), redux-действие `{type:"canvas/entitySelected",payload:{entityIdentifier:{id,type}}}`, методы `stateApi.addInpaintMask({isSelected:true})` / `stateApi.addRasterLayer({isSelected:true})`, состояние `state.canvas.{selectedEntityIdentifier,inpaintMasks.entities,rasterLayers.entities}`.
- Produces: DOM `div#devbim-mask-toggle` с двумя кнопками; файл-источник для `deploy_mask_toggle()` (Task 2).

- [ ] **Step 1: Создать файл `imagerouter/devbim_mask_toggle.js` с полным кодом**

```js
// DevBIM — тумблер «Маска / Слой» на холсте InvokeAI.
// Показывает, каким слоем рисует кисть, и переключает слой одним кликом.
// Деплой: setup_imagerouter.py → dist/devbim-mask-toggle.js (+script в index.html).
// Мост: window.__devbimCanvasBridge.getManager() — патч App-бандла.
(function () {
  "use strict";

  var TICK_MS = 500;
  var ID = "devbim-mask-toggle";
  var STYLE = [
    "#" + ID + "{position:fixed;bottom:96px;left:50%;transform:translateX(-50%);",
    "z-index:1400;display:none;align-items:center;gap:2px;padding:4px;",
    "border-radius:999px;background:#0B0C0E;border:1px solid rgba(255,255,255,.08);",
    "box-shadow:0 4px 16px rgba(0,0,0,.4)}",
    "#" + ID + " button{display:flex;align-items:center;gap:6px;padding:6px 14px;",
    "border:0;border-radius:999px;background:transparent;color:rgba(255,255,255,.72);",
    "font-size:13px;line-height:1;cursor:pointer;font-family:inherit}",
    "#" + ID + " button:hover{background:rgba(255,255,255,.06);color:#fff}",
    "#" + ID + " button.active{background:rgba(56,189,248,.16);color:#38BDF8}",
    "#" + ID + " svg{width:14px;height:14px;flex:none}"
  ].join("");
  var ICON_MASK =
    '<svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="6.2" ' +
    'fill="none" stroke="currentColor" stroke-width="1.4"/><path ' +
    'd="M4.5 11.5 11 5M6.5 12.8 12.8 6.5" fill="none" stroke="currentColor" ' +
    'stroke-width="1.2"/></svg>';
  var ICON_LAYER =
    '<svg viewBox="0 0 16 16" aria-hidden="true"><rect x="3.5" y="3.5" width="9" ' +
    'height="9" rx="1.5" fill="none" stroke="currentColor" stroke-width="1.4"/></svg>';

  var root = null, btnMask = null, btnLayer = null;
  var subscribedStore = null, unsubscribe = null;

  function manager() {
    var b = window.__devbimCanvasBridge;
    if (!b) return null;
    try {
      var m = b.getManager();
      return m && m.stateApi && m.stateApi.store ? m : null;
    } catch (e) {
      return null;
    }
  }

  function render() {
    if (root) return;
    var st = document.createElement("style");
    st.textContent = STYLE;
    document.head.appendChild(st);
    root = document.createElement("div");
    root.id = ID;
    btnMask = document.createElement("button");
    btnMask.type = "button";
    btnMask.title = "Рисовать маской для правки (полосатая кисть)";
    btnMask.innerHTML = ICON_MASK + "<span>Маска</span>";
    btnMask.onclick = function () { activate("inpaint_mask"); };
    btnLayer = document.createElement("button");
    btnLayer.type = "button";
    btnLayer.title = "Рисовать цветом по картинке";
    btnLayer.innerHTML = ICON_LAYER + "<span>Слой</span>";
    btnLayer.onclick = function () { activate("raster_layer"); };
    root.appendChild(btnMask);
    root.appendChild(btnLayer);
    document.body.appendChild(root);
  }

  function activate(type) {
    var m = manager();
    if (!m) return;
    var store = m.stateApi.store;
    var cs = store.getState().canvas;
    var list = type === "inpaint_mask" ? cs.inpaintMasks.entities : cs.rasterLayers.entities;
    if (list.length > 0) {
      var last = list[list.length - 1];
      store.dispatch({
        type: "canvas/entitySelected",
        payload: { entityIdentifier: { id: last.id, type: type } }
      });
    } else if (type === "inpaint_mask") {
      m.stateApi.addInpaintMask({ isSelected: true });
    } else {
      m.stateApi.addRasterLayer({ isSelected: true });
    }
    sync();
  }

  function sync() {
    var m = manager();
    var tab = window.__devbimGetTab ? window.__devbimGetTab() : null;
    if (!m || tab !== "canvas") {
      if (root) root.style.display = "none";
      return;
    }
    if (!root) return;
    var sel = m.stateApi.store.getState().canvas.selectedEntityIdentifier;
    var t = sel && sel.type;
    btnMask.classList.toggle("active", t === "inpaint_mask");
    btnLayer.classList.toggle("active", t === "raster_layer");
    root.style.display = "flex";
  }

  function ensureSubscribed(m) {
    var store = m.stateApi.store;
    if (subscribedStore === store) return;
    if (unsubscribe) { try { unsubscribe(); } catch (e) {} }
    subscribedStore = store;
    unsubscribe = store.subscribe(sync);
  }

  function tick() {
    var m = manager();
    if (!m) {
      if (root) root.style.display = "none";
      return;
    }
    render();
    ensureSubscribed(m);
    sync();
  }

  function start() { setInterval(tick, TICK_MS); tick(); }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
})();
```

- [ ] **Step 2: Проверить синтаксис**

Run: `node --check "imagerouter/devbim_mask_toggle.js"`
Expected: пустой вывод, код возврата 0.

- [ ] **Step 3: Commit**

```bash
git add imagerouter/devbim_mask_toggle.js
git commit -m "feat(canvas): виджет-тумблер Маска/Слой (исходник)"
```

---

### Task 2: `deploy_mask_toggle()` — деплой виджета в dist + index.html

**Files:**
- Create: `tests/test_mask_toggle.py`
- Modify: `setup_imagerouter.py` (константы после строки `ADMIN_JS_DST = DIST / "devbim-admin.js"` (стр. 53) и новая функция после `deploy_files()` (стр. 83-90))

**Interfaces:**
- Consumes: `imagerouter/devbim_mask_toggle.js` (Task 1); константы `BASE`, `SRC`, `DIST` модуля.
- Produces: `deploy_mask_toggle(dist: Path | None = None) -> bool` — копирует источник в `<dist>/devbim-mask-toggle.js`, вставляет `<script src="/devbim-mask-toggle.js" defer></script>` перед `</head>`; идемпотентна; тесты вызывают её с временной папкой.

- [ ] **Step 1: Написать падающий тест `tests/test_mask_toggle.py`**

```python
# -*- coding: utf-8 -*-
"""Тесты тумблера «Маска/Слой»: деплой идемпотентен, синтаксис JS валиден.

Запуск: venv\\Scripts\\python.exe tests\\test_mask_toggle.py
"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import setup_imagerouter as sir


def test_deploy_idempotent():
    with tempfile.TemporaryDirectory() as td:
        dist = Path(td)
        (dist / "index.html").write_text(
            "<html><head><title>t</title></head><body></body></html>",
            encoding="utf-8",
        )
        sir.deploy_mask_toggle(dist)
        changed_again = sir.deploy_mask_toggle(dist)
        s = (dist / "index.html").read_text(encoding="utf-8")
        assert s.count('src="/devbim-mask-toggle.js"') == 1, s
        assert "<script" in s and "</head>" in s
        assert (dist / "devbim-mask-toggle.js").exists()
        assert not changed_again, "повторный деплой не должен менять index.html"
    print("OK: деплой идемпотентен")


def test_widget_js_syntax():
    node = shutil.which("node")
    if not node:
        print("SKIP: node не найден")
        return
    r = subprocess.run(
        [node, "--check", str(sir.SRC / "devbim_mask_toggle.js")],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    print("OK: node --check devbim_mask_toggle.js")


if __name__ == "__main__":
    test_deploy_idempotent()
    test_widget_js_syntax()
```

- [ ] **Step 2: Запустить тест, убедиться в падении**

Run: `venv/Scripts/python.exe tests/test_mask_toggle.py`
Expected: `AttributeError: module 'setup_imagerouter' has no attribute 'deploy_mask_toggle'`

- [ ] **Step 3: Добавить константы (после `ADMIN_JS_DST = ...` в setup_imagerouter.py)**

```python
MASK_TOGGLE_SRC = SRC / "devbim_mask_toggle.js"
MASK_TOGGLE_NAME = "devbim-mask-toggle.js"
```

- [ ] **Step 4: Добавить функцию (после `deploy_files()`, перед `ensure_env_file()`)**

```python
def deploy_mask_toggle(dist: Path | None = None) -> bool:
    """Деплой тумблера «Маска/Слой»: копия в dist/ + script в index.html."""
    dist = dist or DIST
    dst = dist / MASK_TOGGLE_NAME
    index = dist / "index.html"
    if not MASK_TOGGLE_SRC.exists():
        print("ОШИБКА: нет источника", MASK_TOGGLE_SRC)
        sys.exit(1)
    if not index.exists():
        print("ОШИБКА: нет index.html в", dist)
        sys.exit(1)
    shutil.copy2(MASK_TOGGLE_SRC, dst)
    s = index.read_text(encoding="utf-8")
    if MASK_TOGGLE_NAME in s:
        print("index.html уже подключает", MASK_TOGGLE_NAME + ", пропуск")
        print("Тумблер развернут:", dst)
        return False
    if "</head>" not in s:
        print("ОШИБКА: в index.html нет </head>")
        sys.exit(1)
    bak = index.with_suffix(".html.masktoggle-bak")
    if not bak.exists():
        shutil.copy2(index, bak)
    tag = f'  <script src="/{MASK_TOGGLE_NAME}" defer></script>\n</head>'
    index.write_text(s.replace("</head>", tag, 1), encoding="utf-8")
    print("index.html подключает", MASK_TOGGLE_NAME + f" (бэкап: {bak.name})")
    print("Тумблер развернут:", dst)
    return True
```

- [ ] **Step 5: Запустить тест, убедиться в прохождении**

Run: `venv/Scripts/python.exe tests/test_mask_toggle.py`
Expected:
```
OK: деплой идемпотентен
OK: node --check devbim_mask_toggle.js
```

- [ ] **Step 6: Commit**

```bash
git add tests/test_mask_toggle.py setup_imagerouter.py
git commit -m "feat(canvas): deploy_mask_toggle — деплой тумблера в dist и index.html"
```

---

### Task 3: `patch_canvas_bridge()` — мост в App-бандле

**Files:**
- Modify: `tests/test_mask_toggle.py` (добавить тест моста)
- Modify: `setup_imagerouter.py` (константы + функция после `patch_canvas_control_layer()`, стр. 270-296)

**Interfaces:**
- Consumes: якорь `const cue=u.memo(` (тот же, что у `setup_ifcviewer.py::JS_APPCONTENT_ANCHOR`); модульная переменная бандла `ru` (стор менеджера канваса, `ru=De(null)`).
- Produces: `patch_canvas_bridge(bundle: Path | None = None) -> bool`; в бандле — `window.__devbimCanvasBridge={getManager:()=>ru.get()};` перед якорем; потребляет виджет из Task 1.

- [ ] **Step 1: Дописать падающий тест в `tests/test_mask_toggle.py`**

Добавить функцию и вызов (перед `if __name__ == "__main__":` внести её в список вызовов):

```python
def test_bridge_patch_idempotent():
    with tempfile.TemporaryDirectory() as td:
        b = Path(td) / "App-fake.js"
        b.write_text(
            'const q=1;const cue=u.memo((e=>e));export{cue};,ru=De(null)',
            encoding="utf-8",
        )
        assert sir.patch_canvas_bridge(b) is True
        assert sir.patch_canvas_bridge(b) is False  # повторный запуск — пропуск
        s2 = b.read_text(encoding="utf-8")
        assert s2.count("__devbimCanvasBridge") == 1, s2
        assert s2.count("const cue=u.memo(") == 1, s2
        assert s2.index("window.__devbimCanvasBridge") < s2.index("const cue=u.memo(")
        assert (Path(td) / "App-fake.js.imagerouter-bak").exists()
    print("OK: патч моста идемпотентен, якорь сохранён")
```

и в `__main__`-блоке:

```python
if __name__ == "__main__":
    test_deploy_idempotent()
    test_widget_js_syntax()
    test_bridge_patch_idempotent()
```

- [ ] **Step 2: Запустить тест, убедиться в падении**

Run: `venv/Scripts/python.exe tests/test_mask_toggle.py`
Expected: `AttributeError: module 'setup_imagerouter' has no attribute 'patch_canvas_bridge'`

- [ ] **Step 3: Добавить константы и функцию в `setup_imagerouter.py`**

Константы (рядом с `MASK_TOGGLE_*` из Task 2):

```python
# Якорь тот же, что у setup_ifcviewer.py (JS_APPCONTENT_ANCHOR): вставка
# префиксом, якорь сохраняется для IFC-патча при любом порядке запуска.
JS_CANVAS_BRIDGE_ANCHOR = "const cue=u.memo("
JS_CANVAS_BRIDGE = "window.__devbimCanvasBridge={getManager:()=>ru.get()};"
```

Функция (после `patch_canvas_control_layer()`):

```python
def patch_canvas_bridge(bundle: Path | None = None) -> bool:
    """Мост менеджера канваса для тумблера «Маска/Слой» (devbim_mask_toggle.js)."""
    if bundle is None:
        targets = [
            f for f in DIST.glob("assets/*.js")
            if 'displayName="TabContent"' in f.read_text(encoding="utf-8")
        ]
        if len(targets) != 1:
            print(f"ОШИБКА: App-бандл (TabContent) найден {len(targets)} раз (ожидался 1)")
            sys.exit(1)
        bundle = targets[0]
    s = bundle.read_text(encoding="utf-8")
    if "__devbimCanvasBridge" in s:
        print("Мост канваса уже установлен, пропуск")
        return False
    if s.count(JS_CANVAS_BRIDGE_ANCHOR) != 1:
        print(f"ОШИБКА: якорь моста найден {s.count(JS_CANVAS_BRIDGE_ANCHOR)} раз (ожидался 1)")
        sys.exit(1)
    if ",ru=" not in s:
        print("ОШИБКА: в бандле нет ru (стор менеджера) — структура изменилась")
        sys.exit(1)
    bak = bundle.with_suffix(bundle.suffix + ".imagerouter-bak")
    if not bak.exists():
        shutil.copy2(bundle, bak)
    s = s.replace(JS_CANVAS_BRIDGE_ANCHOR, JS_CANVAS_BRIDGE + JS_CANVAS_BRIDGE_ANCHOR, 1)
    bundle.write_text(s, encoding="utf-8")
    print(f"Мост канваса установлен: {bundle.name} (бэкап: {bak.name})")
    return True
```

- [ ] **Step 4: Запустить тест, убедиться в прохождении**

Run: `venv/Scripts/python.exe tests/test_mask_toggle.py`
Expected:
```
OK: деплой идемпотентен
OK: node --check devbim_mask_toggle.js
OK: патч моста идемпотентен, якорь сохранён
```

- [ ] **Step 5: Commit**

```bash
git add tests/test_mask_toggle.py setup_imagerouter.py
git commit -m "feat(canvas): patch_canvas_bridge — мост менеджера канваса в App-бандле"
```

---

### Task 4: Интеграция в `main()`, прогон на реальном venv, проверки

**Files:**
- Modify: `setup_imagerouter.py:517-535` (`main()`)

**Interfaces:**
- Consumes: `deploy_mask_toggle()` (Task 2), `patch_canvas_bridge()` (Task 3), `MASK_TOGGLE_SRC`.
- Produces: рабочий деплой в `venv/.../dist/`; мост в реальном App-бандле.

- [ ] **Step 1: Включить новые шаги в `main()`**

В проверке предусловий (строка с `for p in (...)`) добавить `MASK_TOGGLE_SRC` в кортеж:

```python
    for p in (SRC / "imagerouter_router.py", SRC / "imagerouter.html", SRC / "devbim_admin.js",
              MASK_TOGGLE_SRC, DIST, API_APP.parent):
```

После `deploy_files()` добавить:

```python
    deploy_mask_toggle()
```

После `patch_canvas_control_layer()` добавить:

```python
    patch_canvas_bridge()
```

- [ ] **Step 2: Прогнать setup на реальном venv**

Run (из корня проекта): `venv/Scripts/python.exe setup_imagerouter.py`
Expected: среди строк вывода:
```
index.html подключает devbim-mask-toggle.js (бэкап: index.html.masktoggle-bak)
Тумблер развернут: ...dist\devbim-mask-toggle.js
...
Мост канваса установлен: App-B3eY4dpl.js (бэкап: App-B3eY4dpl.js.imagerouter-bak)
```
Остальные патчи — «уже пропатчен, пропуск» (идемпотентность). Никаких «ОШИБКА».

- [ ] **Step 3: Проверить, что App-бандл не сломан**

Run:
```bash
node -e "import('file:///C:/Users/Lenovo/Desktop/%D0%BF%D1%80%D0%BE%D0%B5%D0%BA%D1%82%20SOFT_2/%D0%94%D0%B8%D0%B7%D0%B0%D0%B9%D0%BD/InvokeAI/InvokeAI/venv/Lib/site-packages/invokeai/frontend/web/dist/assets/App-B3eY4dpl.js').catch(e=>console.log(e.message))"
```
Expected: только `document is not defined` (или подобная рантайм-ошибка), НЕ SyntaxError / Unexpected token.

- [ ] **Step 4: Проверить файлы дистрибутива**

```bash
grep -c "devbim-mask-toggle.js" venv/Lib/site-packages/invokeai/frontend/web/dist/index.html   # → 1
grep -c "__devbimCanvasBridge" venv/Lib/site-packages/invokeai/frontend/web/dist/assets/App-B3eY4dpl.js  # → 1
node --check venv/Lib/site-packages/invokeai/frontend/web/dist/devbim-mask-toggle.js  # без вывода
```

- [ ] **Step 5: Перезапустить сервер**

Run: `powershell -NoProfile -ExecutionPolicy Bypass -File _restart_server.ps1`
Expected: сервер поднялся (лог `ir_server.log`, порт 9090 отвечает).

- [ ] **Step 6: Ручная UI-проверка пользователем (контрольная точка)**

Попросить пользователя открыть `http://127.0.0.1:9090`, вкладка Canvas:
1. Видна пилюля «Маска / Слой» по центру над нижней панелью.
2. Клик «Маска» — подсветилась, кисть рисует полосатой маской; клик «Слой» — кисть рисует цветом.
3. Кнопка «На холст» в IFC-панели — подсветка сама переключается на «Маска».
4. Клик по слою в панели слоёв — подсветка тумблера следует.
5. Вкладка Generate — пилюля скрыта; возврат на Canvas — снова видна.
6. F5 — подсветка соответствует сохранённому выделению.

- [ ] **Step 7: Commit**

```bash
git add setup_imagerouter.py
git commit -m "feat(canvas): тумблер Маска/Слой включён в setup_imagerouter (main)"
```

---

### Task 5: Документация — HANDOFF.md и README.md

**Files:**
- Modify: `HANDOFF.md` (новый п. 16 в «Что реализовано» + строка в «Проверка после изменений»)
- Modify: `README.md` (подраздел перед `### Диагностика` раздела ImageRouter, стр. 332)

**Interfaces:**
- Consumes: фактические результаты Tasks 1-4.
- Produces: документация для следующих сессий (правило AGENTS.md: HANDOFF читать первым).

- [ ] **Step 1: Добавить п. 16 в HANDOFF.md (после п. 15, перед «Ключевые технические детали»)**

```markdown
16. **Тумблер «Маска / Слой» на холсте** (05.09, поздний вечер). Пилюля
    над нижней панелью холста: подсвечивает слой, которым рисует кисть
    (Маска = inpaint_mask, полосатая кисть; Слой = raster_layer, цвет), и
    переключает его одним кликом. Реализация: мост в App-бандле
    `window.__devbimCanvasBridge={getManager:()=>ru.get()}` (вставка перед
    якорем `const cue=u.memo(` — тот же якорь, что у IFC-патча; вставка
    префиксом, якорь сохраняется) + виджет `imagerouter/devbim_mask_toggle.js`
    → `dist/devbim-mask-toggle.js` + script в index.html. Всё — в
    `setup_imagerouter.py`: `patch_canvas_bridge()` (бандл ищется по
    `displayName="TabContent"`), `deploy_mask_toggle()` (бэкап
    `index.html.masktoggle-bak`). Виджет: тик 500 мс ждёт мост и
    `__devbimGetTab()`, показывается только на вкладке canvas;
    подсветка — через `store.subscribe` (store = `manager.stateApi.store`),
    состояние `state.canvas.selectedEntityIdentifier.type`; клик: слой есть
    → `dispatch({type:"canvas/entitySelected",payload:{entityIdentifier:{id,type}}})`
    (самый свежий слой = последний в `entities`), нет →
    `stateApi.addInpaintMask({isSelected:true})` / `addRasterLayer`. Тесты:
    `tests/test_mask_toggle.py`. Правка вида/позиции — правкой
    `imagerouter/devbim_mask_toggle.js` + повторный `setup_imagerouter.py`
    (как баннер). Откат: `*.imagerouter-bak`, `index.html.masktoggle-bak`,
    удалить `dist/devbim-mask-toggle.js`.
```

- [ ] **Step 2: Добавить строку в чек-лист «Проверка после изменений» в HANDOFF.md**

В блок кода после строки `.\venv\Scripts\python.exe .\setup_ifcviewer.py          # вкладка IFC (идемпотентно)` добавить:

```powershell
.\venv\Scripts\python.exe .\tests\test_mask_toggle.py     # тумблер Маска/Слой
```

- [ ] **Step 3: Добавить подраздел в README.md перед `### Диагностика` (раздел ImageRouter)**

```markdown
### Тумблер «Маска / Слой» на холсте

Над нижней панелью холста плавает пилюля с двумя кнопками:
- **Маска** — кисть рисует полосатой маской (зона для правки/inpaint);
- **Слой** — кисть рисует обычным цветом по картинке.

Подсветка показывает, чем рисует кисть прямо сейчас; клик переключает слой
(если слоя нет — создаётся). Полезно после кнопки «На холст» из IFC-вьювера:
она сама выделяет слой маски, и без индикации это неочевидно. Конкретный
слой по-прежнему можно выбрать в панели слоёв справа.

Реализация: `imagerouter/devbim_mask_toggle.js` (деплой
`setup_imagerouter.py` → `dist/devbim-mask-toggle.js`) + однострочный мост в
App-бандле (`patch_canvas_bridge`). Правка вида — правка JS-файла с
повторным запуском `setup_imagerouter.py`. Откат: восстановить
`*.imagerouter-bak` и `index.html.masktoggle-bak`, удалить
`dist/devbim-mask-toggle.js`.
```

- [ ] **Step 4: Commit**

```bash
git add HANDOFF.md README.md
git commit -m "docs: тумблер Маска/Слой на холсте (HANDOFF п.16, README)"
```

---

## Самопроверка плана (выполнена при написании)

- Покрытие спеки: мост (Task 3), виджет + data flow (Task 1), деплой + index.html (Task 2), интеграция + проверки + ручной чек-лист спеки (Task 4), документация (Task 5), крайние случаи — в коде виджета (скрытие без менеджера/не на canvas; выбор последнего слоя). Out-of-scope спеки в план не входят.
- Placeholder'ов нет: каждый шаг содержит полный код/команды/ожидаемый вывод.
- Имена согласованы: `deploy_mask_toggle(dist)`, `patch_canvas_bridge(bundle)`, `MASK_TOGGLE_SRC`, `MASK_TOGGLE_NAME`, `JS_CANVAS_BRIDGE(_ANCHOR)` используются одинаково во всех задачах.
