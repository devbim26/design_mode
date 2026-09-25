# Tiered-конвейер 3D-генерации (п.56) — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Дешёвое извлечение → детерминированный контракт посадки кодом → ремонт
JSON при нарушениях → сборка → verify на дорогой модели → одна эскалационная
попытка при провале раунда. Петля verify/CORRECTIONS и рейтинг попыток не
меняются.

**Architecture:** Часть 1 — контракт в `threed_scenarios.validate_interior`
(возвращает 3-ю корзину `issues`); числа п.55 вынесены в общие константы,
сборщик их импортирует (последний рубеж остаётся). Части 2–3 — per-stage модели
(`THREED_ANALYSIS/REPAIR/VERIFY/ESCALATION_MODEL`, полный override `THREED_MODEL`
сохранён), text-only ремонт с гейтом (parse + validate, один повтор на sol),
эскалация одной попыткой после раунда. A/B-проба (часть 4 спеки) — ОТДЕЛЬНО,
после согласования пользователя; дефолт analysis остаётся astra.

**Tech Stack:** Python (FastAPI-роутер InvokeAI), ifcopenshell, requests;
тесты — plain asserts (`venv\Scripts\python.exe tests\<имя>.py`).

Спека: `docs/superpowers/specs/2026-09-24-threed-tiered-pipeline-design.md`.
HANDOFF: п.53 (промт-гварды), п.55 (проёмы), грабли п.45-3/п.46-1.

## Global Constraints

- Коммиты — ТОЛЬКО по команде пользователя (шаги commit в задачах отсутствуют).
- Не править `venv/.../site-packages` руками — только `setup_threed.py`.
- `PYTHONUTF8=1` в bat; тесты из корня: `venv\Scripts\python.exe tests\<имя>.py`.
- Дефолты стадий: analysis=`openai/gpt-6-astra`, repair=`openai/gpt-6-luna`,
  verify=`openai/gpt-6-astra`, escalation=`openai/gpt-6-astra`;
  ремонт-повтор=`openai/gpt-6-sol` (id сверены с `/v3/models` 24.09,
  тарифы luna $0.1/$0.5, sol $2/$10 совпадают со спекой).
- `THREED_MODEL` (env/file-store через PUT /api/v1/threed/model) — полный
  override всех стадий; PUT валидирует id по каталогу как раньше.
- Не задано ничего нового → поведение и стоимость сегодняшние (эскалация по
  дефолту выключена: analysis == escalation == astra).
- Прогресс-стадии фронта (`analysis|build|verify`, STAGE_KEYS в
  devbim_topright_buttons.js) НЕ расширяем: repair/escalation идут под
  «analysis»; новые теги — только в `_usage_stage` (cost-дампы).
- Спека пишет «validate_scene (interior)» — реализуем в `validate_interior`
  (интерьерный валидатор; уличная `validate_scene` проёмов не имеет).
- Деплой в venv (`setup_threed.py`) — ДО прогона test_threed.py: роутер дерева
  тянет VENV-копии threed-модулей (грабля п.45-3), смена сигнатуры
  validate_interior требует синхронного деплоя. Рестарт сервера — после тестов.

## Решённые дизайновые вопросы

1. **Сигнатура `validate_interior`** → `(scene, warnings, issues)`; остальные
   валидаторы не меняются. Роутер остальные сценарии трактует как `issues=[]`.
2. **Огрызок < 0.6 м**: перенос проёма на ближайшую стену ≥ 0.6 м в радиусе
   `OPENING_TRANSFER_MAX_M = 1.5` м от середины огрызка (warning «посажен»);
   подходящей стены нет → semantic issue «проём без стены-носителя рядом»,
   проём удаляется (сборщик его всё равно не держит — но теперь факт виден).
3. **Ширина/высота после клампа < 0.3** → удаление с warning (зеркало сборщика,
   раньше — молча). Проёмы `wall_idx:"outline"` не проверяются (нет носителя).
4. **«Комната не замкнута»**: покрытие контура комнаты стенами; точка контура
   «закрыта», если лежит в допуске `(thickness/2 + 0.15 м)` от оси какой-либо
   стены; шаг выборки 0.3 м; покрытие < 60% → issue.
5. **«Мебель вне комнат»**: центр вне всех полигонов комнат (при их отсутствии
   — вне outline; нет ни того, ни другого — проверка пропускается) → issue.
6. **Ремонт** — только interior и только при непустых semantic issues; вход
   чистая сцена + issues БЕЗ картинки; выход strict-JSON; гейт =
   `extract_json` + `validate_interior` (без исключения); провал → один повтор
   на sol; не помогло → issues едут в CORRECTIONS следующей итерации/эскалации.
   Сбой сети ремонта НЕ роняет попытку (warning, исходная сцена).
7. **Эскалация**: после раунда (verify включён, лучший вердикт ok=False или все
   ok=None) и analysis ≠ escalation → +1 попытка `_r{max_iters+1}` на
   эскалационной модели, CORRECTIONS = накопленные verify-issues + semantic
   issues контракта (пул с дедупом); verify попытки — как всегда на
   THREED_VERIFY_MODEL (судья независим от генератора). Пустой
   `THREED_ESCALATION_MODEL` → выключено. Победа по действующему рейтингу.
8. **Гейт повтора петли** расширяется: `ok is False` и (verify issues ИЛИ
   оставшиеся contract issues) → итерация с общим CORRECTIONS-блоком. Для
   plan/facade/scene (issues контракта всегда []) — поведение идентично сегодня.
9. **GET /model** дополнительно отдаёт `stages` (наблюдаемость); PUT не меняется.
10. Каталог при старте генерации валидирует 4 stage-модели (пустой каталог
    (тесты/оффлайн) → no-op, как сегодня). sol-повтор не валидируется заранее —
    его сбой глушится гейтом ремонта.

---

### Task 1: Часть 1 — контракт посадки (threed_scenarios.py + threed_build.py)

**Files:**
- Modify: `threed/threed_scenarios.py` (константы, хелперы, `validate_interior` → 3-tuple)
- Modify: `threed/threed_build.py` (импорт констант вместо литералов п.55)

**Interfaces:**
- Produces: `OPENING_MIN_HOST=0.6, OPENING_MARGIN=0.05, OPENING_MIN=0.3,
  OPENING_TRANSFER_MAX_M=1.5, ROOM_WALL_COVER_MIN=0.6` (module-level,
  threed_scenarios); `validate_interior(scene, img_w, img_h) ->
  (scene, warnings, issues)`; `_pt_seg_dist`, `_point_in_poly` (private).

- [ ] Константы после `INTERIOR_SCALE_MIN, INTERIOR_SCALE_MAX` (interior-блок):

```python
# --- контракт посадки проёмов (п.56; числа п.55 — сборщик импортирует их
# как последний рубеж) ---
OPENING_MIN_HOST = 0.6   # стена-носитель короче — огрызок, проём не держит
OPENING_MARGIN = 0.05    # поле от проёма до торца стены-носителя
OPENING_MIN = 0.3        # минимальный проём после клампов (меньше — мусор VLM)
OPENING_TRANSFER_MAX_M = 1.5  # дальность переноса проёма с огрызка, м
ROOM_WALL_COVER_MIN = 0.6     # минимум покрытия контура комнаты стенами
```

- [ ] Хелперы геометрии (module-private, px-пространство):

```python
def _pt_seg_dist(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    l2 = dx * dx + dy * dy
    if l2 <= 0:
        return ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / l2))
    return ((px - ax - t * dx) ** 2 + (py - ay - t * dy) ** 2) ** 0.5


def _point_in_poly(x, y, pts):
    inside = False
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            if x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
                inside = not inside
    return inside
```

- [ ] Посадочный проход в `validate_interior` — после существующих клампов
  величин (openings уже распарсены в `out["openings"]`), до финального
  `ValueError`. Нормализуемое — правим + warning «посажен/посажено»;
  семантическое — `issues`. Порядок внутри прохода: огрызок → перенос/issue;
  ширина; высота; центр. Update сигнатуры/docstring, `return out, warnings, issues`.

```python
def _seat_openings(out, warnings, issues):
    scale = out["metres_per_trace_pixel"]
    segs = [tuple(w["points_px"][0]) + tuple(w["points_px"][1])
            for w in out["walls"]]
    seated = []
    for i, op in enumerate(out["openings"], start=1):
        widx = op["wall_idx"]
        if widx == "outline":
            seated.append(op)
            continue
        x1, y1, x2, y2 = segs[widx]
        length_m = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5 * scale
        if length_m < OPENING_MIN_HOST:
            ax, ay = (x1 + x2) / 2, (y1 + y2) / 2
            best = None
            for j, (bx1, by1, bx2, by2) in enumerate(segs):
                if j == widx:
                    continue
                lm = ((bx2 - bx1) ** 2 + (by2 - by1) ** 2) ** 0.5 * scale
                if lm < OPENING_MIN_HOST:
                    continue
                d = _pt_seg_dist(ax, ay, bx1, by1, bx2, by2) * scale
                if best is None or d < best[0]:
                    best = (d, j)
            if best is None or best[0] > OPENING_TRANSFER_MAX_M:
                issues.append(f"Проём {i} ({op['kind']} {op['width_m']:g} м): "
                              f"стена-носитель {widx + 1} короче "
                              f"{OPENING_MIN_HOST:g} м, подходящей стены рядом "
                              f"нет — проём без стены-носителя")
                continue
            j = best[1]
            bx1, by1, bx2, by2 = segs[j]
            dx, dy = bx2 - bx1, by2 - by1
            l2 = dx * dx + dy * dy
            t = max(0.0, min(1.0, ((ax - bx1) * dx + (ay - by1) * dy) / l2))
            op["wall_idx"] = j
            op["x_px"] = t * (l2 ** 0.5)
            warnings.append(f"Проём {i}: стена-носитель {widx + 1} — огрызок "
                            f"{length_m:g} м — посажен на стену {j + 1}")
            x1, y1, x2, y2 = bx1, by1, bx2, by2
            length_m = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5 * scale
        if op["width_m"] > length_m - 2 * OPENING_MARGIN:
            op["width_m"] = length_m - 2 * OPENING_MARGIN
            warnings.append(f"Проём {i}: ширина срезана до {op['width_m']:g} м — "
                            f"посажено в стену {op['wall_idx'] + 1}")
        if op["width_m"] < OPENING_MIN:
            warnings.append(f"Проём {i}: ширина после посадки < {OPENING_MIN:g} м — "
                            f"удалён")
            continue
        h_max = out["wall_height"] - op["sill_m"] - OPENING_MARGIN
        if op["height_m"] > h_max:
            op["height_m"] = h_max
            warnings.append(f"Проём {i}: высота срезана до {h_max:g} м — "
                            f"посажено под потолок")
        if op["height_m"] < OPENING_MIN:
            warnings.append(f"Проём {i}: высота после посадки < {OPENING_MIN:g} м — "
                            f"удалён")
            continue
        t_m = op["x_px"] * scale
        lo = op["width_m"] / 2 + OPENING_MARGIN
        hi = length_m - op["width_m"] / 2 - OPENING_MARGIN
        if t_m < lo or t_m > hi:
            t_m = max(lo, min(hi, t_m))
            op["x_px"] = t_m / scale
            warnings.append(f"Проём {i}: центр вне сегмента — посажен на "
                            f"{t_m:g} м от начала стены {op['wall_idx'] + 1}")
        seated.append(op)
    out["openings"] = seated
```

- [ ] Семантические проверки (после `_seat_openings`):

```python
def _check_furniture_rooms(out, issues):
    polys = [r["points_px"] for r in out["rooms"]] or \
            ([out["outline"]] if out["outline"] else [])
    if not polys:
        return
    for i, item in enumerate(out["furniture"], start=1):
        if not any(_point_in_poly(item["x_px"], item["y_px"], p) for p in polys):
            issues.append(f"Мебель {i} ({item['type']}): вне комнат — "
                          f"переместить внутрь помещения")


def _check_rooms_closed(out, issues):
    scale = out["metres_per_trace_pixel"]
    segs = [(tuple(w["points_px"][0]), tuple(w["points_px"][1]), w["thickness_m"])
            for w in out["walls"]]
    step_px = max(1.0, 0.3 / scale)
    for room in out["rooms"]:
        pts = room["points_px"]
        total = covered = 0
        for k in range(len(pts)):
            (ax, ay), (bx, by) = pts[k], pts[(k + 1) % len(pts)]
            el = ((bx - ax) ** 2 + (by - ay) ** 2) ** 0.5
            n = max(2, int(el / step_px))
            for s in range(n):
                t = s / n
                px, py = ax + (bx - ax) * t, ay + (by - ay) * t
                total += 1
                for (x1, y1), (x2, y2), th in segs:
                    if _pt_seg_dist(px, py, x1, y1, x2, y2) <= (th / 2 + 0.15) / scale:
                        covered += 1
                        break
        if total and covered / total < ROOM_WALL_COVER_MIN:
            issues.append(f"Комната «{room['name']}»: контур закрыт стенами на "
                          f"{round(100 * covered / total)}% — комната не замкнута")
```

- [ ] `threed_build.py`: импорт констант (try venv / except дерево — паттерн
  threed_router) + замена литералов в `build_interior`: `0.6`→
  `OPENING_MIN_HOST`, `- 0.1`→`- 2 * OPENING_MARGIN`, `0.3`→`OPENING_MIN`
  (ширина и высота), `- 0.05`→`- OPENING_MARGIN` (высота), `width / 2 + 0.05`/
  `- width / 2 - 0.05`→`± OPENING_MARGIN` (кламп центра). Поведение п.55
  бит-в-бит (существующие точные ассерты `6.95` и др. остаются в силе).

- [ ] Обновить `tests/test_threed.py::test_validate_interior`: распаковка
  3-tuple; в out2-фикстуре ожидаются новые warnings («посажено») и issues
  (комната не замкнута) — ассерты на них. Добавить в test_threed.py
  `test_interior_seating_contract` (фикстуры кейсов п.55):
  - окно за торцом (стена 8 м, окно x_px=45 при scale 0.16) → посажено
    (x_px ≈ 43.4375 = 6.95/0.16), warning «посажен», issues == [];
  - дверь на огрызке 0.32 м + параллельная стена 5.76 м рядом → перенос
    (wall_idx сменён, warning «огрызок … посажен на стену»), issues == [];
  - огрызок БЕЗ подходящей стены → issues содержат «проём без
    стены-носителя», проём удалён из out["openings"];
  - мебель вне комнаты (стол в (30,15) при одной комнате Кухня) → issue
    «вне комнат»;
  - комната с одной стеной из четырёх → issue «не замкнута»;
  - happy path `sample_interior_scene()` → issues == [].
  Запуск: `venv\Scripts\python.exe tests\test_threed.py` → ALL OK
  (test_generate_impl_interior тоже проходит: контракт на сэмпле чист).

### Task 2: Части 2–3 — per-stage модели, ремонт, эскалация (threed_router.py)

**Files:**
- Modify: `threed/threed_router.py` (env-рульки, `_stage_model`, `_call_vlm`
  image optional, `_repair_scene`, `_generate_impl`: контракт в `_attempt`,
  `_run_attempt`-рефакторинг, эскалация, dump `stages`, GET /model `stages`)
- Modify: `threed/threed_scenarios.py` (+`SYSTEM_REPAIR`)

**Interfaces:**
- Consumes: Task 1 `validate_interior` 3-tuple, константы.
- Produces: `STAGES`, `STAGE_ENV`, `STAGE_DEFAULTS`, `DEFAULT_REPAIR_MODEL
  ="openai/gpt-6-luna"`, `REPAIR_RETRY_MODEL="openai/gpt-6-sol"`;
  `_stage_model(stage)->(model, source)` (source: file|env|env:stage|off|
  default); `_repair_scene(scene, issues, img_w, img_h)->(scene|None,
  warnings, issues)`; `_usage_stage` ∈ analysis|repair|verify|escalation.

- [ ] Константы + env-механика (после `DEFAULT_MODEL`):

```python
DEFAULT_REPAIR_MODEL = "openai/gpt-6-luna"
REPAIR_RETRY_MODEL = "openai/gpt-6-sol"
STAGES = ("analysis", "repair", "verify", "escalation")
STAGE_ENV = {"analysis": "THREED_ANALYSIS_MODEL", "repair": "THREED_REPAIR_MODEL",
             "verify": "THREED_VERIFY_MODEL", "escalation": "THREED_ESCALATION_MODEL"}
STAGE_DEFAULTS = {"analysis": DEFAULT_MODEL, "repair": DEFAULT_REPAIR_MODEL,
                  "verify": DEFAULT_MODEL, "escalation": DEFAULT_MODEL}
```

`_env_threed_var(name)` (os.environ → .env файлами, `None`=не задана,
`''`=пусто), `_env_threed_model()` сводится к ней, `_stage_model(stage)` —
см. дизайн-решение 7/Global Constraints (override глушит per-stage;
`''` эскалации → `("", "off")`).

- [ ] `_call_vlm(system, prompt, image_url, model)` — `image_url: str | None`;
  content без image-парты, когда None (ремонт text-only).

- [ ] `SYSTEM_REPAIR` в threed_scenarios.py (рядом с SYSTEM_INTERIOR):
  «You are a BIM data fixer. You get a parametric interior scene JSON that
  failed automated placement checks. Fix ONLY the listed issues by editing
  numbers (move furniture inside rooms, re-seat openings onto their host
  walls, add missing wall segments). Keep every other value EXACTLY as given.
  Reply with STRICT JSON ONLY - the full corrected scene, same schema, no
  markdown fences, no comments.»

- [ ] `_repair_scene` (модульный уровень роутера): цикл по
  `(repair_model, REPAIR_RETRY_MODEL)`; `_usage_stage[0]="repair"`;
  `_call_vlm(SYSTEM_REPAIR, prompt, None, model)`; гейт `extract_json` +
  `validate_interior` (ValueError → следующий); успех → `(fixed_scene,
  warnings + note, left)`; провал обоих → `(None, [note], issues)`.
  Вызов в `_attempt` обёрнут try/except — сбой ремонта не роняет попытку.

- [ ] `_generate_impl`:
  - `model, source = _stage_model("analysis")`; валидация всех 4 stage-моделей
    по каталогу (пустой каталог — no-op);
  - `_attempt(user_prompt, attempt_no, model_override=None, stage="analysis")`:
    модель попытки = override or analysis; meta["Model"] = модель попытки;
    interior → 3-tuple + ремонт; возвращает
    `(scene, warnings, ifc_path, preview_path, raw_head, contract_issues)`;
  - `_verify_attempt` — модель `_stage_model("verify")[0]`;
  - тело попытки вынесено в `_run_attempt(user_prompt, attempt_no, a_model,
    stage)` (nonlocal best; history + contract_issues + `_add_corr` пул;
    возвращает `(ok, issues, contract_issues)` или None при сбое попытки ≥ 2);
  - цикл раунда: гейт повтора `ok is False and (issues or contract_issues)`;
    CORRECTIONS-блок = verify issues + недублирующиеся contract issues;
  - эскалация после раунда: `_verify_enabled()` и `esc_model` непуст и
    `esc_model != model` и лучший ok не True → `_run_attempt(esc_prompt,
    max_iters + 1, esc_model, "escalation")` с CORRECTIONS из пула;
  - dump `["stages"] = {s: _stage_model(s)[0] for s in STAGES}`;
  - `GET /model` → + `"stages": {s: _stage_model(s) for s in STAGES}`.
  Регресс-инвариант: без новых env и без override план/фасад/сцена идут
  ровно как раньше (escalation off: analysis==escalation).

### Task 3: Тесты маршрутизации/ремонта/эскалации (tests/test_threed_tiered.py)

**Files:**
- Create: `tests/test_threed_tiered.py` (THREED_VERIFY=1 на импорте;
  изолятор `_router()` как в test_threed_facade_v2.py; env-рульки
  ставятся/снимаются try/finally)

- [ ] `test_stage_model_resolution`: дефолты (analysis/verify/escalation =
  astra, repair = luna, source="default"); `THREED_ANALYSIS_MODEL=x/y` →
  только analysis; `THREED_MODEL` env / file-store → все стадии на нём;
  `THREED_ESCALATION_MODEL=""` → `("", "off")`.
- [ ] `test_routing_analysis_repair_verify` (interior, мок пишет
  (маркер system, model)): сцена с мебелью вне комнаты; ремонт-ветка
  (`"data fixer" in system`) возвращает исправленный JSON → порядок
  моделей [astra, luna, astra]; у попытки contract_issues == []; happy-path
  сцена без issues → ремонт НЕ вызывается (дешёвый путь не платит).
- [ ] `test_repair_gate`: кривой JSON на luna → повтор на sol → валидный
  → сцена принята; оба кривые → issues остаются и едут в CORRECTIONS
  итерации 2 (analysis-промпт №2 содержит «вне комнат»).
- [ ] `test_escalation_single_attempt` (facade, THREED_ANALYSIS_MODEL=
  "fake/sol", escalation=astra, verify всё время ok=False+issue,
  THREED_VERIFY_ITERS=1): последовательность моделей
  [sol, astra, sol, astra, astra(escalation), astra(verify)]; победитель
  `_r3.ifc`; history 3 записи; промпт эскалации содержит issue итераций 1–2
  (пул); `_usage_stage`-теги в порядке анализа мока не проверить (мок не
  пишет usage) — вместо этого ассерт `dump["stages"]` и структуры history.
- [ ] `test_escalation_disabled_and_override`:
  - `THREED_ESCALATION_MODEL=""` → нет третьей попытки, файлов _r3 нет;
  - `THREED_MODEL="fake/one"` (+ per-stage рульки) → ВСЕ вызовы (вкл.
    ремонт и verify) на "fake/one", эскалации нет (analysis == escalation).
- [ ] Прогон: `venv\Scripts\python.exe tests\test_threed_tiered.py` → ALL OK.

### Task 4: Деплой, полный прогон, рестарт, HANDOFF

- [ ] `venv\Scripts\python.exe setup_threed.py` (идемпотентен) — ДО тестов
  test_threed.py (грабля п.45-3: роутер дерева тянет venv-копии сценариев,
  сигнатура validate_interior изменилась).
- [ ] Тесты: `tests\test_threed.py`, `tests\test_threed_verify.py`,
  `tests\test_threed_facade_v2.py`, `tests\test_threed_tiered.py` — ALL OK.
- [ ] Рестарт: `launch\_restart_server.ps1`; health-check:
  `GET /api/v1/threed/model` → 200, `stages` на месте; `GET /api/v1/ifc/list`.
- [ ] HANDOFF.md п.56 (по факту: что сделано, грабли, стоимость, откат).
  Коммит — только по команде пользователя.

## Self-Review

- Спека ч.1 → Task 1 (константы, 2 корзины, outline-исключение). ч.2 → Task 2
  (4 рульки, override, ремонт без картинки + гейт + sol-повтор, _usage_stage).
  ч.3 → Task 2 (эскалация одной попыткой, `_rN`, отключаемо, рейтинг не тронут).
  ч.4 — осознанно вне плана (после согласования, отдельная проба).
  «Проверка» спеки → Tasks 1/3 + Task 4 (регресс существующих).
- Типы/имена сверены: `OPENING_*` едины в scenarios/build; `_stage_model`
  используется в `_generate_impl`/`_verify_attempt`/`_repair_scene`/GET;
  `_run_attempt` возвращает `(ok, issues, contract_issues)|None`.
- Мок-тесты не требуют сети (каталог `[]`, key не нужен — `_call_vlm` мок).
