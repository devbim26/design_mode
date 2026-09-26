# Двухканальный ансамбль извлечения геометрии image→IFC (п.60) — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Два независимых извлечения (A: параметрический JSON на astra; B:
grounding-боксы в пикселях на модели из зонда) → детерминированное сравнение →
слияние с LLM-реферти по спорам (≤1 вызов) → регуляризация по теме (чистый код,
гейт по agree_rate) → существующие контракт/сборка/verify (судья получает
оригинал + оверлей геометрии). Цель: median judge-score фасада 43 → ≥51.

**Architecture:** «VLM выбирает семантику, код считает геометрию». Три новых
чистых модуля `threed/threed_ground.py` (прогон B + конвертеры боксы→сцена),
`threed/threed_ensemble.py` (compare/merge/referee), `threed/threed_regular.py`
(снапы/ритм/симметрия); интеграция — в `_attempt` роутера ПОСЛЕ валидации A и
ДО контракта/сборки. Сбой любой части ансамбля — warning + работа с A
(текущее качество — нижняя граница). `THREED_ENSEMBLE=0` — откат в один клик.

**Tech Stack:** Python 3.11 (venv InvokeAI), ifcopenshell, shapely 2.1.2,
PIL 12.3.0, numpy — всё уже в venv, НОВЫХ зависимостей нет. Тесты — plain
asserts: `venv\Scripts\python.exe tests\<имя>.py` (печать OK/ALL OK).

Спека: `docs/superpowers/specs/2026-09-26-threed-geometry-ensemble-design.md`.
HANDOFF: пп.44–58; грабли: **п.45-3 / п.58(а)** (тесты роутера тянут
VENV-копии threed-модулей → деплой ДО тестов, изолятор `_router()`),
п.46-1 (`THREED_VERIFY=0` на импорте в test_threed.py), п.55 (константы
проёмов — общий импорт), п.22(а) (никаких future-annotations в задеплоенных
модулях).

## Global Constraints

- **Коммиты — ТОЛЬКО по команде пользователя.** Исключения, прямо
  требуемые спекой з.7: коммит харнесса и baseline-результатов в Task 1
  (без baseline-коммита Δ не измерим — стохастика VLM ±5–15).
- **ГРАБЛЯ п.45-3/п.58(а) — изоляция venv-копий**: тесты роутера, запущенные
  из дерева, импортируют задеплоенные копии из
  `venv/.../invokeai/app/api/routers/`. Правила:
  1. Каждый НОВЫЙ модуль добавляется в план копирования `setup_threed.py`
     В ТОЙ ЖЕ задаче, которая его создаёт.
  2. Перед запуском тестов, импортирующих роутер (`test_threed*.py`,
     зонды, E2E) — `venv\Scripts\python.exe setup_threed.py`.
  3. Новые роутерные тесты используют изолятор `_router()` (связывает модули
     дерева в роутер дерева — см. Task 4/8; паттерн `tests/test_threed_tiered.py:34`).
  4. Тесты чистых модулей (`test_threed_ground/ensemble/regular.py`)
     импортируют `from threed import threed_ground` напрямую — эти модули
     НЕ импортируют `invokeai.*` и от venv не зависят.
- `PYTHONUTF8=1` в bat; тесты из корня проекта: `venv\Scripts\python.exe tests\<имя>.py`.
- Существующие наборы (test_threed.py 20 + test_threed_facade_v2.py 10 +
  test_threed_tiered.py 5 + test_threed_verify.py 9 = 44 функции, п.46) НЕ
  ломаются. Минимальные правки существующих файлов: на импорте
  `os.environ["THREED_ENSEMBLE"] = "0"` (Task 8, шаг 6) — иначе моки
  `_call_vlm` ломаются лишним вызовом прогона B.
- Внутри `threed/*.py` ЗАПРЕЩЁН `from __future__ import annotations`
  (задеплоенные модули; грабля п.22(а)). Аннотации — нативные (`str | None`),
  Python 3.11.
- `threed_ground`/`threed_ensemble`/`threed_regular` — чистые: stdlib/
  shapely/PIL + соседи `threed_scenarios`/`threed_regular` через
  try/except `invokeai...|threed...` (паттерн `threed_build.py:23-29`).
  Импорт из дерева (`from threed import threed_ground`) обязан работать
  БЕЗ venv — никаких прочих `invokeai.*` и никакого `from threed import
  ...` вне except-ветки (в venv пакета `threed` нет — грабля п.45-3).
- Константы проёмов п.55 (`OPENING_MIN_HOST/OPENING_MARGIN/OPENING_MIN`) —
  ТОЛЬКО импорт из `threed_scenarios` (тесты п.55 assert'ят точные значения).
- Каталог моделей: id сверены с `/v3/models` 24.09 (astra/luna/sol);
  шлюз ImageRouter отдаёт ошибки и с HTTP 200 — статусу не верить.
- Прогресс-стадии фронта (`analysis|build|verify`, STAGE_KEYS) НЕ расширяем:
  прогон B и реферти идут под «analysis»; новый тег `ensemble` — только в
  `_usage_stage` (cost-дампы). JS-бандлы не патчим → node-проверка не нужна.
- Сервер перезапускать только `launch\_restart_server.ps1`; API за гейтом —
  кука `devbim_auth` (POST /auth/login с SITE_PASSWORD из .env).
- Бюджет ImageRouter: зонд ≤ $0.30; baseline 9 прогонов ≈ $1.9; ensemble
  A/B 9 прогонов ≈ $2.3 (Task 10). `:free`-модели НЕ использовать
  (3 запроса/сутки, грабля п.19).
- Сцена сценария `scene` (улица) — ансамблем НЕ покрывается (боксы улицы
  спекой не определены): `THREED_ENSEMBLE=1` на неё не действует.

## Решённые дизайновые вопросы (отклонения от буквы спеки — осознанные)

1. **Сцены B проходят ТЕ ЖЕ валидаторы** (`validate_facade/genplan/interior`),
   что и A: сравнение идёт по стабильным клампнутым полям, конвертер не
   дублирует клампы.
2. **Фасадный B голосует полем `entrance` (0/1)**, а не `doors[]`: схема
   фасада (п.44-45) списка дверей не хранит — только `entrance` (0/1) и
   балконы. Боксы дверей садятся в `entrance` (самая нижняя дверь).
   Count-семантика «doors Δ≥1» сохранена как «вход есть/нет».
3. **МНК-масштаб план — внутри конвертера B** (`lsq_scale`), а не в
   регуляризации: якоря (стойло парковки 2.5×5, спортплощадка 17×34) живут в
   пиксельных боксах payload B, в слитой сцене их уже нет. Функция одна,
   тестится отдельно.
4. **Снап углов**: план — к k·90° при отклонении <15°, прочие рёбра не
   трогаем (эркер 67.5° остаётся); интерьер — к ближайшему k·45° только при
   отклонении <15° (67.5° не задевает: до 90° и 45° ровно по 22.5°).
5. **Оверлей фасада**: сцена фасада метрическая (без пикселей) → пиксельный
   якорь = бокс `building` из прогона B (grounding-режим); без B
   (text-fallback) — пропорциональный фит (80% ширины, по центру): судья
   видит ритм сетки, позиции — только в grounding-режиме.
6. **Рефери разрешает споры фасада точечно** (поле → значение), план/интерьер
   — на уровне КОМПОНЕНТА (спор о секциях/комнатах решается большинством
   голосов полей компонента: берём `sections`/комнаты целиком из A или B) —
   иначе пришлось бы телепортировать отдельные числа между структурами.
7. **Рефери-модель не глушится полным override** `THREED_MODEL` (спека з.3:
   «отдельное значение, не luna»): env `THREED_REFEREE_MODEL` → всегда
   дефолт `openai/gpt-6-sol`. Text-fallback B — на ремонт-модели (luna; при
   override — на override-модели, как обычные стадии).
8. **Бюджет попытки**: счётчик `_attempt_calls` инкрементится в самом
   `_call_vlm`, сбрасывается в начале `_run_attempt` (эскалация — своя
   попытка, свой бюджет, спека з.8). Проверка ПЕРЕД необязательными
   вызовами (B, реферти, ремонт, verify); порядок analysis→B→рефери→ремонт→
   verify защищает ядро: при исчерпании пропускается verify (ok=None),
   а не анализ.
9. **agree_rate** = agreed / (agreed + disputed) по числу сравниваемых полей
   темы (facade 7 полей, plan 5, interior 5 — см. Task 5).
10. **Baseline-набор картинок**: 3 темы × 1 картинка × ≥3 прогона = 9
    (бюджет ≈ $1.9 на пайплайн). Спека писала «3 картинки × 3 темы × 3»
    (27) — при появлении у пользователя ещё реальных картинок харнесс
    принимает их флагом `--image`, прогоняется дополнительно; синтетика
    plan/interior + реальный фасад покрывают все конвертеры уже сейчас.

## Файловая структура

| Файл | Статус | Ответственность |
|---|---|---|
| `threed/threed_ground.py` | NEW (Task 2,4,9) | SYSTEM_GROUND_*, `_compute_iou`, `normalize_boxes`, `lsq_scale`, `run_ground_pass`, `run_text_pass`, `facade_pixel_hint`, конвертеры `*_boxes_to_scene` |
| `threed/threed_ensemble.py` | NEW (Task 5,9) | `DISPUTE_RULES`, `compare_scenes`, `merge_scenes`, `SYSTEM_REFEREE`, `_get/_set` |
| `threed/threed_regular.py` | NEW (Task 6,9) | `REGULAR_GATE=0.7`, `regularize`, `snap`, `rdp`, `orthogonalize`, per-theme |
| `threed/threed_router.py` | MODIFY (Task 8) | env-хелперы, `_ensemble_pass`, бюджет, тег ensemble, оверлей в verify, дамп |
| `threed/threed_verify.py` | MODIFY (Task 7) | `render_overlay`, `verify(..., overlay_url=None)` |
| `threed/threed_build.py` | MODIFY (Task 8) | `EnsembleAgreement` в pset DevBIM (4 билдера) |
| `setup_threed.py` | MODIFY (Task 2 первый, затем 4/5/6) | план копирования +3 файла |
| `data/probe/_make_gt_images.py` | NEW (Task 1) | синтетические plan/interior картинки + авто-GT |
| `tests/_e2e_3d_roundtrip.py` | MODIFY (Task 1) | `--runs/--label/--save/--scenario/--image`, медианы |
| `data/probe/_gt_mark.py` | NEW (Task 2) | tkinter-маркер боксов фасада |
| `data/probe/_threed_ground_gt.json` | NEW (Task 2) | GT фасада (ручная разметка) |
| `data/probe/_threed_ground_gt_synthetic.json` | NEW (Task 1, auto) | GT plan/interior (точно из генератора) |
| `data/probe/_probe_threed_ground.py` | NEW (Task 3) | зонд grounding-моделей |
| `data/probe/_probe_threed_ground_results.json` | NEW (Task 3, live) | таблица зонда + winner |
| `tests/test_threed_ground.py` | NEW (Task 2,4,9) | IoU/конвертеры/кластеризация |
| `tests/test_threed_ab.py` | NEW (Task 1) | чистые хелперы A/B-харнесса |
| `tests/test_threed_ensemble.py` | NEW (Task 5,8) | compare/merge/реферти + интеграция в роутер |
| `tests/test_threed_regular.py` | NEW (Task 6,9) | снапы/ритм/симметрия/RDP |
| `tests/test_threed_verify.py` | MODIFY (Task 7) | +оверлей-тесты |
| `data/probe/_ab_baseline.json` | NEW (Task 1, ветка baseline-3d) | baseline-метрики |

---

### Task 1: A/B-харнесс + входные картинки тем + baseline-ветка (з.7, пререквизит)

Baseline обязателен ДО задач 2+ (спека: Δ не измерим без него, стохастика
VLM ±5–15). Харнесс — расширение живого `tests/_e2e_3d_roundtrip.py`; чистые
функции вынесены для TDD.

**Files:**
- Modify: `tests/_e2e_3d_roundtrip.py`
- Create: `tests/test_threed_ab.py`, `data/probe/_make_gt_images.py`
- Auto-generated (не в git руками): `data/probe/gt_plan_synthetic.png`,
  `data/probe/gt_interior_synthetic.png`,
  `data/probe/_threed_ground_gt_synthetic.json`

**Interfaces:**
- Produces: `_median(vals) -> float`, `_summarize(runs) -> dict` в
  `_e2e_3d_roundtrip.py` (переиспользуются Task 10);
  `data/probe/_make_gt_images.py::main()` — пишет 2 PNG + авто-GT JSON
  (детерминированно; координаты ниже — источник GT Task 2/3);
  картинки: фасад `data/probe/vlm_test_house.png` (есть, 455×534),
  план `gt_plan_synthetic.png`, интерьер `gt_interior_synthetic.png`.

- [ ] **Шаг 1: тест чистых хелперов (файл целиком)**

`tests/test_threed_ab.py`:

```python
# -*- coding: utf-8 -*-
"""Чистые хелперы A/B-харнесса _e2e_3d_roundtrip.py (медианы/сводка).
Живого VLM тут нет — харнесс-скрипт импортируется через importlib
(он не .py-модуль тестов, а скрипт с main())."""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _harness():
    spec = importlib.util.spec_from_file_location(
        "_threed_ab_harness", ROOT / "tests" / "_e2e_3d_roundtrip.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_median():
    H = _harness()
    assert H._median([3, 1, 2]) == 2
    assert H._median([4, 1, 2, 3]) == 2.5
    assert H._median([5]) == 5
    assert H._median([]) is None
    print("test_median OK")


def test_summarize():
    H = _harness()
    runs = [{"score": 40, "cost_usd": 0.2, "structural_ok": True,
             "agree_rate": None, "contract_issues": 2},
            {"score": 50, "cost_usd": 0.3, "structural_ok": False,
             "agree_rate": None, "contract_issues": 4},
            {"score": 45, "cost_usd": 0.25, "structural_ok": True,
             "agree_rate": None, "contract_issues": 0}]
    s = H._summarize(runs)
    assert s["median_score"] == 45, s
    assert abs(s["median_cost_usd"] - 0.25) < 1e-9
    assert s["structural_clean_rate"] == round(2 / 3, 3), s
    assert s["median_contract_issues"] == 2
    assert s["agree_rate"] is None  # baseline без ансамбля
    runs2 = runs + [{"score": 60, "cost_usd": 0.4, "structural_ok": True,
                     "agree_rate": 0.85, "contract_issues": 0}]
    s2 = H._summarize(runs2)
    assert s2["agree_rate"] == 0.85
    print("test_summarize OK")


if __name__ == "__main__":
    test_median()
    test_summarize()
    print("ALL OK")
```

- [ ] **Шаг 2: запуск — ожидается FAIL**

Run: `venv\Scripts\python.exe tests\test_threed_ab.py`
Expected: FAIL — `AttributeError: ... has no attribute '_median'` (хелперов ещё нет).

- [ ] **Шаг 3: хелперы + CLI в `_e2e_3d_roundtrip.py`**

После `SYSTEM_JUDGE = """..."""` (строка ~59) добавить:

```python
def _median(vals):
    """Медиана списка чисел; None для пустого (A/B-сводки, спека з.7)."""
    v = sorted(x for x in vals if x is not None)
    n = len(v)
    if not n:
        return None
    return v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2


def _summarize(runs):
    """N прогонов одной конфигурации -> медианы/доли для таблицы приёмки
    (спека, раздел 11). Прогон = dict из main()-цикла."""
    scores = [r.get("score") for r in runs]
    costs = [r.get("cost_usd") for r in runs]
    agrees = [r.get("agree_rate") for r in runs if r.get("agree_rate") is not None]
    ci = [r.get("contract_issues") for r in runs]
    st = [bool(r.get("structural_ok")) for r in runs]
    return {"n": len(runs),
            "median_score": _median(scores),
            "median_cost_usd": _median(costs),
            "structural_clean_rate": (round(sum(st) / len(st), 3)
                                      if st else None),
            "median_contract_issues": _median(ci),
            "agree_rate": (round(sum(agrees) / len(agrees), 3)
                           if agrees else None)}
```

`main()` переходит на серию: заменить сигнатуру и цикл (текущий блок
`if ifc_arg: ... else: res = _generate(...)` и хвост печати) на:

```python
def main() -> None:
    args = sys.argv[1:]
    ifc_arg = args[args.index("--ifc") + 1] if "--ifc" in args else None
    runs_n = int(args[args.index("--runs") + 1]) if "--runs" in args else 1
    label = args[args.index("--label") + 1] if "--label" in args else "adhoc"
    save = Path(args[args.index("--save") + 1]) if "--save" in args else None
    scenario = args[args.index("--scenario") + 1] if "--scenario" in args else "facade"
    img_arg = args[args.index("--image") + 1] if "--image" in args else None
    src_img = Path(img_arg) if img_arg else DEFAULT_IMG
    src = ROOT / "data" / "ifc" / "_roundtrip_src.png"
    Image.open(src_img).convert("RGB").save(src)

    runs = []
    for i in range(runs_n if not ifc_arg else 1):
        if ifc_arg:
            res = {"name": ifc_arg, "camHint": None, "verify": None}
        else:
            res = _generate(scenario, "ab harness run", src_img)
        # contract_issues/agree_rate живут в дампе сервера (history только
        # там; Semaphore(1) = дамп соответствует этому прогону)
        dump = {}
        try:
            dump = json.loads(
                (ROOT / "data" / "ifc" / "_threed_last.json")
                .read_text(encoding="utf-8"))
        except Exception:
            pass
        hist = (dump.get("verify") or {}).get("history") or []
        render = _viewer_render(res["name"], res.get("camHint"))
        view_path = ROOT / "data" / "ifc" / "_roundtrip_view.png"
        render.convert("RGB").save(view_path)
        frac = _content_fraction(render)
        assert frac > MIN_CONTENT_FRACTION, "рендер вьювера пуст"
        verdict = _judge(src, view_path)
        ens = res.get("ensemble") or dump.get("ensemble") or {}
        usage = res.get("usage") or {}
        runs.append({"name": res["name"], "score": int(verdict["score"]),
                     "match": bool(verdict["match"]),
                     "content_fraction": round(frac, 4),
                     "cost_usd": usage.get("cost_usd"),
                     "structural_ok": ((res.get("structural") or {})
                                       .get("ok")),
                     "contract_issues": (len(hist[-1].get("contract_issues")
                                             or []) if hist else 0),
                     "agree_rate": ens.get("agree_rate")})
        print(f"run {i + 1}/{runs_n}: score={verdict['score']} "
              f"cost={usage.get('cost_usd')}")

    summary = _summarize(runs)
    print(f"[{label}] {scenario} {src_img.name}: median score "
          f"{summary['median_score']}, cost {summary['median_cost_usd']}")
    if save:
        save.parent.mkdir(parents=True, exist_ok=True)
        save.write_text(json.dumps(
            {"label": label, "scenario": scenario, "image": str(src_img),
             "runs": runs, "summary": summary},
            ensure_ascii=False, indent=1), encoding="utf-8")
        print("сохранено:", save)
```

- [ ] **Шаг 4: тест хелперов — PASS**

Run: `venv\Scripts\python.exe tests\test_threed_ab.py`
Expected: `ALL OK`.

- [ ] **Шаг 5: генератор синтетических картинок plan/interior (файл целиком)**

`data/probe/_make_gt_images.py` (детерминированный; эти же координаты —
GT-боксы Task 2/эталон зонда Task 3; масштабы: план 0.25 м/px, интерьер
0.01 м/px):

```python
# -*- coding: utf-8 -*-
"""Синтетические GT-картинки тем plan/interior (спека п.60 з.1a).

Рисует детерминированно и пишет авто-GT (боксы = нарисованные
прямоугольники, без ручной разметки). Фасад GT — ручной (_gt_mark.py).

  gt_plan_synthetic.png      1024x768, 0.25 м/px: 3 корпуса + спортплощадка
                            (17x34 м -> 68x136 px) + стойло парковки
                            (2.5x5 м -> 10x20 px) как якоря масштаба.
  gt_interior_synthetic.png   900x700, 0.01 м/px: 3 комнаты, 2 двери, 1 окно.

Запуск: venv\\Scripts\\python.exe data\\probe\\_make_gt_images.py
"""
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "probe"

PLAN_BOXES = {  # (x1, y1, x2, y2), подписи этажности рисуются рядом
    "buildings": [
        ((120, 120, 420, 320), "Residential", 5),
        ((520, 120, 888, 296), "School", 3),
        ((160, 470, 360, 660), "Kindergarten", 2),
    ],
    "sport": (440, 420, 508, 556),      # 68x136 px = 17x34 м
    "parking": (700, 470, 710, 490),    # 10x20 px = 2.5x5 м
}
INTERIOR_BOXES = {
    "rooms": [
        ((60, 60, 460, 350), "Living"),
        ((60, 350, 460, 640), "Bedroom"),
        ((460, 60, 840, 640), "Kitchen"),
    ],
    "doors": [(455, 190, 465, 280), (160, 345, 250, 355)],  # 0.9-0.1 м
    "windows": [(835, 200, 845, 320)],                      # 1.2 м
}


def draw_plan() -> dict:
    im = Image.new("RGB", (1024, 768), "white")
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, 1023, 767], outline=(200, 200, 200), width=2)
    entries = []
    for (box, use, floors) in PLAN_BOXES["buildings"]:
        d.rectangle(list(box), outline="black", width=3)
        d.text((box[0] + 6, box[1] + 6), f"{use} {floors} fl", fill="black")
        entries.append({"label": "building", "box": list(box),
                        "meta": {"use": use, "floors": floors}})
    x1, y1, x2, y2 = PLAN_BOXES["sport"]
    d.rectangle([x1, y1, x2, y2], outline=(70, 120, 60), width=3)
    d.text((x1 + 4, y1 + 4), "SPORT", fill=(70, 120, 60))
    entries.append({"label": "sport", "box": [x1, y1, x2, y2]})
    x1, y1, x2, y2 = PLAN_BOXES["parking"]
    d.rectangle([x1, y1, x2, y2], outline=(60, 60, 60), width=2)
    d.text((x1 - 4, y2 + 4), "P", fill=(60, 60, 60))
    entries.append({"label": "parking", "box": [x1, y1, x2, y2]})
    im.save(OUT / "gt_plan_synthetic.png")
    return {"image": "gt_plan_synthetic.png", "scenario": "plan",
            "metres_per_pixel": 0.25, "boxes": entries}


def draw_interior() -> dict:
    im = Image.new("RGB", (900, 700), "white")
    d = ImageDraw.Draw(im)
    entries = []
    for (box, name) in INTERIOR_BOXES["rooms"]:
        d.rectangle(list(box), outline="black", width=8)  # 8 px = 0.08 м
        d.text((box[0] + 12, box[1] + 12), name, fill="black")
        entries.append({"label": "room", "box": list(box), "meta": {"name": name}})
    for box in INTERIOR_BOXES["doors"] + INTERIOR_BOXES["windows"]:
        d.rectangle(list(box), fill="white", outline="black", width=2)
    for box in INTERIOR_BOXES["doors"]:
        entries.append({"label": "door", "box": list(box)})
    for box in INTERIOR_BOXES["windows"]:
        entries.append({"label": "window", "box": list(box)})
    im.save(OUT / "gt_interior_synthetic.png")
    return {"image": "gt_interior_synthetic.png", "scenario": "interior",
            "metres_per_pixel": 0.01, "boxes": entries}


def main() -> None:
    gt = [draw_plan(), draw_interior()]
    (OUT / "_threed_ground_gt_synthetic.json").write_text(
        json.dumps(gt, ensure_ascii=False, indent=1), encoding="utf-8")
    print("OK:", ", ".join(e["image"] for e in gt),
          "+ _threed_ground_gt_synthetic.json")


if __name__ == "__main__":
    main()
```

- [ ] **Шаг 6: генерация + проверка артефактов**

Run: `venv\Scripts\python.exe data\probe\_make_gt_images.py`
Expected: `OK: gt_plan_synthetic.png, gt_interior_synthetic.png + _threed_ground_gt_synthetic.json`.
Проверка: 3 бокса building + sport + parking в plan-записи; 3 room + 2 door + 1 window в interior-записи:
`venv\Scripts\python.exe -c "import json;d=json.load(open('data/probe/_threed_ground_gt_synthetic.json',encoding='utf-8'));print([[b['label'] for b in e['boxes']] for e in d])"`.

- [ ] **Шаг 7 (LIVE-1): baseline-ветка и прогон**

Живой VLM (~$1.9, сервер поднят, ключ в .env). Baseline = СЕГОДНЯШНИЙ
конвейер (кода ансамбля ещё нет). СНАЧАЛА фиксируем харнесс на рабочей
ветке (иначе checkout унесёт файлы из дерева), ПОТОМ ветка baseline:

```bash
git add tests/_e2e_3d_roundtrip.py tests/test_threed_ab.py data/probe/_make_gt_images.py data/probe/gt_plan_synthetic.png data/probe/gt_interior_synthetic.png data/probe/_threed_ground_gt_synthetic.json
git commit -m "test(threed): A/B-харнесс + синтетические GT-картинки тем plan/interior (п.60 з.7)"
git branch baseline-3d
git checkout baseline-3d
```

Последовательно (каждая команда = 3 генерации; фасад ~$0.75, план ~$0.36,
интерьер ~$0.60):

```bash
venv\Scripts\python.exe tests\_e2e_3d_roundtrip.py --runs 3 --label baseline --scenario facade --image data\probe\vlm_test_house.png --save data\probe\_ab_baseline.json
venv\Scripts\python.exe tests\_e2e_3d_roundtrip.py --runs 3 --label baseline --scenario plan --image data\probe\gt_plan_synthetic.png --save data\probe\_ab_baseline_plan.json
venv\Scripts\python.exe tests\_e2e_3d_roundtrip.py --runs 3 --label baseline --scenario interior --image data\probe\gt_interior_synthetic.png --save data\probe\_ab_baseline_interior.json
```

- [ ] **Шаг 8 (LIVE-2): baseline-коммит и возврат**

Собрать три JSON в один `_ab_baseline.json` (merge вручную: ключи
facade/plan/interior с их summary) — фиксация baseline по спеке. Затем:

```bash
git add data/probe/_ab_baseline*.json
git commit -m "test(threed): baseline A/B-метрики пайплайна до ансамбля (п.60 з.7, ветка baseline-3d)"
git checkout 3d_analysys
```

Task 10 сравнивает с baseline через
`git show baseline-3d:data/probe/_ab_baseline.json` (и `_plan`/`_interior`).

---

### Task 2: GT-разметка фасада + `_compute_iou` + первый деплой нового модуля (з.1a)

Гейт спеки: разметка фасада с sanity `_compute_iou ≥ 0.9`. Здесь появляется
`threed/threed_ground.py` (скелет: IoU + нормализация + GT-валидатор;
конвертеры — Task 4/9) и первый шаг изоляции venv: модуль сразу в плане
копирования `setup_threed.py`.

**Files:**
- Create: `threed/threed_ground.py`, `data/probe/_gt_mark.py`,
  `data/probe/_threed_ground_gt.json` (руками через маркер)
- Modify: `setup_threed.py:34-37` (план копирования)
- Test: `tests/test_threed_ground.py`

**Interfaces:**
- Produces: `threed_ground._compute_iou(a, b) -> float` (a/b = dict или
  список `[x1, y1, x2, y2]`); `threed_ground.normalize_boxes(payload, img_w,
  img_h) -> (boxes, meta, warnings)` (используется зондом Task 3 и
  конвертерами Task 4/9; формат боксов `{"label","x1","y1","x2","y2"}` —
  `box`/`x1..y2` принимаются на входе, на выходе всегда плоские ключи);
  `threed_ground.GROUND_LABELS`; `threed_ground.validate_gt(entries) ->
  (ok, errors)`.

- [ ] **Шаг 1: failing-тест (файл целиком)**

`tests/test_threed_ground.py`:

```python
# -*- coding: utf-8 -*-
"""Прогон B: GT-инфраструктура + IoU (Task 2), конвертеры (Task 4, 9).
Модуль чистый (без invokeai.*) — импорт из дерева, venv не нужен."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from threed import threed_ground as G  # noqa: E402


def test_compute_iou():
    # identical -> 1.0; disjoint -> 0.0; перекрытие 50% площади
    b = [0, 0, 10, 10]
    assert G._compute_iou(b, [0, 0, 10, 10]) == 1.0
    assert G._compute_iou(b, [20, 20, 30, 30]) == 0.0
    # [0,0,10,10] и [0,0,10,20]: пересечение 100, union 200 -> 0.5
    assert abs(G._compute_iou(b, [0, 0, 10, 20]) - 0.5) < 1e-9
    # dict-форма (GT-файл) и list-форма смешиваются
    assert G._compute_iou({"x1": 0, "y1": 0, "x2": 10, "y2": 10},
                          [0, 0, 10, 10]) == 1.0
    # вырожденные -> 0.0, не исключение
    assert G._compute_iou([0, 0, 0, 0], b) == 0.0
    print("test_compute_iou OK")


def test_normalize_boxes():
    payload = {"boxes": [
        {"label": "window", "x1": 10, "y1": 20, "x2": 60, "y2": 90},
        {"label": "hack", "x1": 0, "y1": 0, "x2": 5, "y2": 5},   # чужой label
        {"label": "door", "box": [100, 100, 140, 220]},          # форма "box"
        {"label": "window", "x1": 790, "y1": 590, "x2": 900, "y2": 700},  # кламп
        {"label": "window", "x1": 50, "y1": 50, "x2": 50, "y2": 50},      # вырожденный
    ], "meta": {"floors": 3}}
    boxes, meta, wns = G.normalize_boxes(payload, 800, 600)
    labels = [b["label"] for b in boxes]
    assert labels == ["window", "door", "window"], labels
    assert all(set(b) == {"label", "x1", "y1", "x2", "y2"} for b in boxes)
    d = next(b for b in boxes if b["label"] == "door")
    assert (d["x1"], d["y1"], d["x2"], d["y2"]) == (100, 100, 140, 220)
    w = next(b for b in boxes if b["x1"] == 790)
    assert (w["x2"], w["y2"]) == (800, 600), "кламп к границе картинки"
    assert meta == {"floors": 3}
    assert len(wns) == 3, wns  # чужой label + вырожденный + кламп
    print("test_normalize_boxes OK")


def test_validate_gt():
    ok, errors = G.validate_gt([
        {"image": "a.png", "scenario": "facade", "boxes": [
            {"label": "window", "x1": 1, "y1": 1, "x2": 2, "y2": 2}] * 8
            + [{"label": "door", "x1": 1, "y1": 1, "x2": 2, "y2": 2},
               {"label": "building", "x1": 0, "y1": 0, "x2": 9, "y2": 9}]},
        {"image": "b.png", "scenario": "plan", "boxes": [
            {"label": "building", "x1": 1, "y1": 1, "x2": 2, "y2": 2}] * 3},
        {"image": "c.png", "scenario": "interior", "boxes": [
            {"label": "room", "x1": 1, "y1": 1, "x2": 2, "y2": 2}] * 3
            + [{"label": "door", "x1": 1, "y1": 1, "x2": 2, "y2": 2}] * 2},
    ])
    assert ok, errors
    # фасад < 8 окон -> ошибка
    ok2, errors2 = G.validate_gt([
        {"image": "a.png", "scenario": "facade", "boxes": [
            {"label": "window", "x1": 1, "y1": 1, "x2": 2, "y2": 2}] * 7}])
    assert not ok2 and any("facade" in e for e in errors2), errors2
    print("test_validate_gt OK")


if __name__ == "__main__":
    test_compute_iou()
    test_normalize_boxes()
    test_validate_gt()
    print("ALL OK")
```

- [ ] **Шаг 2: запуск — FAIL**

Run: `venv\Scripts\python.exe tests\test_threed_ground.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'threed.threed_ground'`.

- [ ] **Шаг 3: скелет `threed/threed_ground.py` (верх модуля целиком)**

```python
# -*- coding: utf-8 -*-
"""Прогон B — grounding-извлечение (спека п.60, з.2): VLM отдаёт боксы в
ПИКСЕЛЯХ исходной картинки + минимальный текстовый блок; геометрию считает
код (конвертеры ниже по модулю). Модуль ЧИСТЫЙ: без invokeai.*, тянется
тестами из дерева (грабля п.45-3 не касается)."""

try:  # в venv threed_scenarios лежит рядом; в дереве — пакет threed
    from invokeai.app.api.routers import threed_scenarios
except ImportError:
    from threed import threed_scenarios

# какие метки принимает каждая тема (чужие — мусор, дроп с warning)
GROUND_LABELS = {
    "facade": {"window", "door", "building"},
    "plan": {"building", "parking", "sport"},
    "interior": {"room", "door", "window"},
}

# якоря метрических размеров (скилл tools/image-to-ifc): м
ANCHOR_PARKING = (2.5, 5.0)    # стойло: короткая/длинная сторона
ANCHOR_SPORT = (17.0, 34.0)    # спортплощадка 16-18 x 32-36 -> медианы
ANCHOR_DOOR_H = 2.1            # высота входной двери, м
ANCHOR_DOOR_W = 0.9            # ширина двери интерьера, м
ANCHOR_WINDOW_H = 1.5          # высота окна фасада, м
ANCHOR_STOREY = 3.0            # этаж, м


def _box_xyxy(b):
    """GT/pred бокс (dict x1..y2 | dict box[4] | list[4]) -> (x1,y1,x2,y2)|None."""
    if isinstance(b, dict):
        raw = b.get("box")
        if isinstance(raw, (list, tuple)) and len(raw) == 4:
            vals = raw
        else:
            vals = (b.get("x1"), b.get("y1"), b.get("x2"), b.get("y2"))
    elif isinstance(b, (list, tuple)) and len(b) == 4:
        vals = b
    else:
        return None
    try:
        x1, y1, x2, y2 = (float(v) for v in vals)
    except (TypeError, ValueError):
        return None
    if x1 == x2 or y1 == y2:  # вырожденный
        return None
    return x1, y1, max(x1, x2), max(y1, y2)


def _compute_iou(pred, gt) -> float:
    """IoU двух боксов (строки спеки з.1a: sanity разметки; з.1b: метрика
    зонда). Формы: dict/list, координаты любые — сам нормализует."""
    a, b = _box_xyxy(pred), _box_xyxy(gt)
    if not a or not b:
        return 0.0
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    union = ((a[2] - a[0]) * (a[3] - a[1])
             + (b[2] - b[0]) * (b[3] - b[1]) - inter)
    return inter / union if union > 0 else 0.0


def normalize_boxes(payload, img_w, img_h, scenario="facade"):
    """Сырой payload B (или GT-запись) -> (boxes, meta, warnings): плоские
    ключи, кламп к границе, дроп чужих label/вырожденных. Валидные GT-записи
    проходят без единого warning."""
    warnings = []
    if not isinstance(payload, dict):
        return [], {}, ["grounding: ответ не объект"]
    raw = payload.get("boxes")
    if not isinstance(raw, list):
        return [], {}, ["grounding: нет массива boxes"]
    allowed = GROUND_LABELS[scenario]
    boxes = []
    for i, b in enumerate(raw, start=1):
        label = b.get("label") if isinstance(b, dict) else None
        if label not in allowed:
            warnings.append(f"бокс {i}: label {label!r} не в {sorted(allowed)} — дроп")
            continue
        xy = _box_xyxy(b)
        if xy is None:
            warnings.append(f"бокс {i} ({label}): битые координаты — дроп")
            continue
        x1, y1, x2, y2 = xy
        cx2, cy2 = min(x2, float(img_w)), min(y2, float(img_h))
        if (x1, y1, x2, y2) != (max(0.0, x1), max(0.0, y1), cx2, cy2):
            warnings.append(f"бокс {i} ({label}): кламп к границе картинки")
        x1, y1, x2, y2 = max(0.0, x1), max(0.0, y1), cx2, cy2
        if x2 - x1 < 1.0 or y2 - y1 < 1.0:
            warnings.append(f"бокс {i} ({label}): меньше 1 px после клампа — дроп")
            continue
        boxes.append({"label": label, "x1": x1, "y1": y1, "x2": x2, "y2": y2})
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    return boxes, dict(meta), warnings


def validate_gt(entries):
    """GT-файл -> (ok, errors). Минимумы спеки з.1a: фасад >=8 окон +
    дверь + контур; план >=3 корпуса; интерьер >=3 комнаты + 2 двери."""
    errors = []
    seen = {"facade": [], "plan": [], "interior": []}
    for e in entries if isinstance(entries, list) else []:
        sc = e.get("scenario")
        if sc not in seen:
            errors.append(f"запись {e.get('image')}: сценарий {sc!r} не в темах")
            continue
        boxes, _, wns = normalize_boxes(e, 10 ** 6, 10 ** 6, scenario=sc)
        if wns:
            errors.append(f"{e.get('image')}: битые GT-боксы ({wns[:2]})")
        seen[sc].append((e.get("image"), [b["label"] for b in boxes]))
    for img, labels in seen["facade"]:
        if labels.count("window") < 8:
            errors.append(f"{img}: facade окон {labels.count('window')} < 8")
        if "door" not in labels or "building" not in labels:
            errors.append(f"{img}: facade нужны door и building")
    for img, labels in seen["plan"]:
        if labels.count("building") < 3:
            errors.append(f"{img}: plan корпусов {labels.count('building')} < 3")
    for img, labels in seen["interior"]:
        if labels.count("room") < 3 or labels.count("door") < 2:
            errors.append(f"{img}: interior нужно >=3 room и >=2 door")
    if not any(seen["facade"]) or not any(seen["plan"]) or not any(seen["interior"]):
        errors.append("нужна хотя бы одна запись каждой темы (facade/plan/interior)")
    return not errors, errors
```

- [ ] **Шаг 4: тест — PASS**

Run: `venv\Scripts\python.exe tests\test_threed_ground.py`
Expected: `ALL OK`.

- [ ] **Шаг 5: деплой-изоляция — `setup_threed.py` узнаёт новый модуль**

`setup_threed.py:34-37`, план копирования (файлы появятся задачами 4–6,
деплой копирует то, что есть — поэтому сразу финальный список):

```python
    plan = [(SRC / "threed_router.py", routers / "threed.py"),
            (SRC / "threed_scenarios.py", routers / "threed_scenarios.py"),
            (SRC / "threed_build.py", routers / "threed_build.py"),
            (SRC / "threed_verify.py", routers / "threed_verify.py"),
            (SRC / "threed_ground.py", routers / "threed_ground.py"),
            (SRC / "threed_ensemble.py", routers / "threed_ensemble.py"),
            (SRC / "threed_regular.py", routers / "threed_regular.py")]
```

И защитить отсутствие ещё не созданных файлов (функция `deploy_files`,
строки выше плана):

```python
    plan = [(src, dst) for src, dst in plan if src.is_file()]
```

Run: `venv\Scripts\python.exe setup_threed.py`
Expected: `Роутер развернут: threed_ground.py` (+ возможно «уже развернуты,
пропуск» для прежних четырёх — копии не совпали из-за нового файла, это
нормально: развернутся все).

- [ ] **Шаг 6: ручная разметка фасада — tkinter-маркер (файл целиком)**

`data/probe/_gt_mark.py`:

```python
# -*- coding: utf-8 -*-
"""Ручная разметка GT-боксов фасада (спека з.1a). Клик-drag рисует бокс,
кнопка/клавиша переключает метку, S сохраняет JSON. Координаты — пиксели
КАРТИНКИ (канвас 1:1, скролл не нужен: vlm_test_house.png 455x534).

Запуск: venv\\Scripts\\python.exe data\\probe\\_gt_mark.py [картка] [сценарий]
"""
import json
import sys
import tkinter as tk
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LABELS = ["window", "door", "building"]

img_path = Path(sys.argv[1]) if len(sys.argv) > 1 else \
    ROOT / "data" / "probe" / "vlm_test_house.png"
scenario = sys.argv[2] if len(sys.argv) > 2 else "facade"
out_path = ROOT / "data" / "probe" / "_threed_ground_gt.json"

import tkinter.filedialog  # noqa: E402,F401
from PIL import Image, ImageTk  # noqa: E402

boxes = []
if out_path.is_file():  # дозагрузка прошлой разметки этой же картинки
    for e in json.loads(out_path.read_text(encoding="utf-8")):
        if e.get("image") == img_path.name:
            boxes = e.get("boxes", [])

root = tk.Tk()
root.title(f"GT mark: {img_path.name} [{scenario}]")
img = Image.open(img_path).convert("RGB")
tkimg = ImageTk.PhotoImage(img)
cv = tk.Canvas(root, width=img.width, height=img.height)
cv.pack()
cv.create_image(0, 0, anchor="nw", image=tkimg)
cur = {"label": tk.StringVar(value=LABELS[0]), "start": None, "rect": None}


def redraw():
    cv.delete("all")
    cv.create_image(0, 0, anchor="nw", image=tkimg)
    for b in boxes:
        x1, y1, x2, y2 = b["x1"], b["y1"], b["x2"], b["y2"]
        cv.create_rectangle(x1, y1, x2, y2, outline="#ff3b30", width=2)
        cv.create_text(x1, max(0, y1 - 8), text=b["label"], fill="#ff3b30")


def press(ev):
    cur["start"] = (ev.x, ev.y)


def drag(ev):
    if cur["rect"]:
        cv.delete(cur["rect"])
    cur["rect"] = cv.create_rectangle(cur["start"][0], cur["start"][1],
                                      ev.x, ev.y, outline="#00a8ff", width=2)


def release(ev):
    if cur["start"]:
        x1, y1 = cur["start"]
        boxes.append({"label": cur["label"].get(),
                      "x1": min(x1, ev.x), "y1": min(y1, ev.y),
                      "x2": max(x1, ev.x), "y2": max(y1, ev.y)})
    cur["start"], cur["rect"] = None, None
    redraw()


def save(_ev=None):
    entries = []
    if out_path.is_file():  # другие картинки сохраняем
        entries = [e for e in json.loads(out_path.read_text(encoding="utf-8"))
                   if e.get("image") != img_path.name]
    entries.append({"image": img_path.name, "scenario": scenario,
                    "boxes": boxes})
    out_path.write_text(json.dumps(entries, indent=1), encoding="utf-8")
    print("saved", len(boxes), "boxes ->", out_path)


def undo(_ev=None):
    if boxes:
        boxes.pop()
        redraw()


def cycle_label(_ev=None):
    i = LABELS.index(cur["label"].get())
    cur["label"].set(LABELS[(i + 1) % len(LABELS)])


bar = tk.Frame(root)
bar.pack()
tk.Label(bar, textvariable=cur["label"], fg="#00a8ff").pack(side="left")
tk.Button(bar, text="Label (L)", command=cycle_label).pack(side="left")
tk.Button(bar, text="Undo (U)", command=undo).pack(side="left")
tk.Button(bar, text="Save (S)", command=save).pack(side="left")
cv.bind("<Button-1>", press)
cv.bind("<B1-Motion>", drag)
cv.bind("<ButtonRelease-1>", release)
root.bind("s", save)
root.bind("u", undo)
root.bind("l", cycle_label)
redraw()
root.mainloop()
```

- [ ] **Шаг 7 (ручной): разметка `vlm_test_house.png`**

Run: `venv\Scripts\python.exe data\probe\_gt_mark.py`
Разметить: ≥8 окон (label `window`), входную дверь (`door`), один общий
контур главного объёма (`building`). Закрыть окно после «Save». ГРАБЛЯ:
кнопка Save обязательна (закрытие окна не сохраняет).

- [ ] **Шаг 8: гейт разметки (sanity спеки ≥0.9 + минимумы)**

```bash
venv\Scripts\python.exe -c "import json,sys;sys.path.insert(0,'.');from threed import threed_ground as G;gt=json.load(open('data/probe/_threed_ground_gt.json',encoding='utf-8'))+json.load(open('data/probe/_threed_ground_gt_synthetic.json',encoding='utf-8'));print(G.validate_gt(gt));[print(e['image'],len(e['boxes'])) for e in gt]"
```

Expected: `(True, [])`. IoU-sanity (джиттер ±5% стороны — «боксы, нарисованные
для теста», IoU ≥ 0.9):

```bash
venv\Scripts\python.exe -c "import json,sys;sys.path.insert(0,'.');from threed import threed_ground as G;gt=json.load(open('data/probe/_threed_ground_gt.json',encoding='utf-8'));ws=[b for e in gt for b in e['boxes'] if b['label']=='window'];import random;random.seed(1);j=[{'x1':b['x1']+0.02*(b['x2']-b['x1']),'y1':b['y1']-0.03*(b['y2']-b['y1']),'x2':b['x2']-0.02*(b['x2']-b['x1']),'y2':b['y2']+0.03*(b['y2']-b['y1'])} for b in ws];m=min(G._compute_iou(p,g) for p,g in zip(j,ws));print('min jitter IoU',round(m,3));assert m>=0.9"
```

Expected: `min jitter IoU ≥ 0.9` без AssertionError.

---

### Task 3: Зонд grounding-моделей — ГЕЙТ модели B (з.1b)

Метрики зонда — чистые функции (TDD); сам прогон живой (≤$0.30). Паттерн —
`data/probe/_vlm_probe.py` (импорт venv-копий роутера: перед запуском
`setup_threed.py` — Task 2 шаг 5 уже развернул модуль).

**Files:**
- Create: `data/probe/_probe_threed_ground.py`
- Test: `tests/test_threed_ground.py` (+2 функции)
- Auto (live): `data/probe/_probe_threed_ground_results.json`

**Interfaces:**
- Consumes: `threed_ground._compute_iou`, `normalize_boxes`, GT-файлы Task 2.
- Produces: `threed_ground.probe_metrics(pred_boxes, gt_boxes) -> dict`
  (mean/median IoU, recall, precision); `threed_ground.probe_candidates(
  vlm_ids) -> list[str]`; `threed_ground.pick_model(results) -> (model,
  mode)` — mode `"grounding"|"text"` (fallback спеки: best mean IoU < 0.5
  или json-valid < 0.5 → text).

- [ ] **Шаг 1: failing-тесты — дописать в `tests/test_threed_ground.py`**

Перед блоком `if __name__ == "__main__":` добавить:

```python
def test_probe_metrics():
    gt = [{"x1": 0, "y1": 0, "x2": 10, "y2": 10},
          {"x1": 20, "y1": 20, "x2": 30, "y2": 30}]
    perfect = [dict(b) for b in gt]
    m = G.probe_metrics(perfect, gt)
    assert m["iou_mean"] == 1.0 and m["iou_median"] == 1.0
    assert m["recall"] == 1.0 and m["precision"] == 1.0
    # один точный pred + один мусор: recall 0.5, precision 0.5
    m2 = G.probe_metrics([gt[0], {"x1": 90, "y1": 90, "x2": 99, "y2": 99}], gt)
    assert m2["recall"] == 0.5 and m2["precision"] == 0.5
    # пустые pred: нули, не исключение
    m3 = G.probe_metrics([], gt)
    assert m3["iou_mean"] == 0.0 and m3["recall"] == 0.0
    print("test_probe_metrics OK")


def test_pick_model():
    good = {"model": "qwen/vl-x", "iou_mean": 0.62, "json_valid": 0.9,
            "results": []}
    assert G.pick_model([good]) == ("qwen/vl-x", "grounding")
    bad = {"model": "openai/gpt-6-sol", "iou_mean": 0.3, "json_valid": 0.9,
           "results": []}
    assert G.pick_model([bad]) == ("", "text"), "IoU<0.5 -> text fallback"
    nojson = {"model": "m", "iou_mean": 0.9, "json_valid": 0.4, "results": []}
    assert G.pick_model([nojson]) == ("", "text")
    assert G.pick_model([]) == ("", "text")
    # лучший по mean IoU среди прошедших гейт
    both = [good, {"model": "m2", "iou_mean": 0.7, "json_valid": 1.0,
                   "results": []}]
    assert G.pick_model(both)[0] == "m2"
    print("test_pick_model OK")
```

и в раннер:
```python
    test_probe_metrics()
    test_pick_model()
```

- [ ] **Шаг 2: запуск — FAIL**

Run: `venv\Scripts\python.exe tests\test_threed_ground.py`
Expected: FAIL — `AttributeError: module 'threed.threed_ground' has no attribute 'probe_metrics'`.

- [ ] **Шаг 3: реализация — дописать в `threed/threed_ground.py`**

```python
# ===================== зонд (з.1b): метрики и выбор модели =====================

def probe_metrics(pred_boxes, gt_boxes, iou_thresh=0.5):
    """pred/gt списки боксов -> {iou_mean, iou_median, recall, precision}.
    Сопоставление жадное по лучшему IoU (один pred закрывает один gt)."""
    pairs = []
    for g in gt_boxes:
        best_iou, best_j = 0.0, -1
        for j, p in enumerate(pred_boxes):
            iou = _compute_iou(p, g)
            if iou > best_iou:
                best_iou, best_j = iou, j
        pairs.append((best_iou, best_j))
    ious = [iou for iou, _ in pairs]
    matched = [j for iou, j in pairs if iou >= iou_thresh and j >= 0]
    used, hits = set(), 0
    for j in matched:  # один pred не закрывает два gt
        if j not in used:
            used.add(j)
            hits += 1
    return {"iou_mean": round(sum(ious) / len(ious), 4) if ious else 0.0,
            "iou_median": round(sorted(ious)[len(ious) // 2], 4) if ious else 0.0,
            "recall": round(hits / len(gt_boxes), 4) if gt_boxes else 0.0,
            "precision": round(hits / len(pred_boxes), 4) if pred_boxes else 0.0}


def probe_candidates(vlm_ids):
    """Каталог id -> кандидаты зонда: qwen-vl семейство + sol; контроль —
    astra (модель анализа A). Порядок стабилен."""
    ids = list(vlm_ids)
    qwen = sorted(i for i in ids if "qwen" in i.lower() and "vl" in i.lower())
    out = []
    if qwen:
        out.append(qwen[0])  # первый qwen-vl каталога (обычно базовый)
    for m in ("openai/gpt-6-sol", "openai/gpt-6-astra"):
        if m in ids:
            out.append(m)
    return out


def pick_model(results):
    """Таблица зонда -> (model, mode). Гейт спеки з.1b: best mean IoU >= 0.5
    И json_valid >= 0.5, иначе text-fallback ("" — модель выберет роутер)."""
    ok = [r for r in results
          if r.get("iou_mean", 0) >= 0.5 and r.get("json_valid", 0) >= 0.5]
    if not ok:
        return "", "text"
    best = max(ok, key=lambda r: r["iou_mean"])
    return best["model"], "grounding"
```

- [ ] **Шаг 4: тест — PASS**

Run: `venv\Scripts\python.exe tests\test_threed_ground.py`
Expected: `ALL OK` (5 функций).

- [ ] **Шаг 5: скрипт зонда (файл целиком)**

`data/probe/_probe_threed_ground.py`:

```python
# -*- coding: utf-8 -*-
"""Зонд grounding-способности VLM каталога ImageRouter (спека п.60 з.1b).

Кандидаты x GT-картинки (Task 1/2): строгий JSON боксов -> IoU/recall/
precision/json-valid. Выход: data/probe/_probe_threed_ground_results.json
(таблица + winner/mode). Бюджет ~$0.10-0.30.

Запуск (сервер не нужен, ключ в .env):
    venv\\Scripts\\python.exe data\\probe\\_probe_threed_ground.py
"""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from invokeai.app.api.routers.threed import (  # noqa: E402  (venv-копии)
    _call_vlm, _prepare_png, _to_dataurl, _vlm_list_cached)
from invokeai.app.api.routers import threed_scenarios  # noqa: E402
from threed import threed_ground as G  # noqa: E402  (дерево — источник правды)

PROBE = ROOT / "data" / "probe"
GT_FILES = [PROBE / "_threed_ground_gt.json",
            PROBE / "_threed_ground_gt_synthetic.json"]
RESULTS = PROBE / "_probe_threed_ground_results.json"

SYSTEM_GROUND = {  # черновик промптов (финальные — Task 4 в threed_ground)
    "facade": G.SYSTEM_GROUND_FACADE, "plan": G.SYSTEM_GROUND_PLAN,
    "interior": G.SYSTEM_GROUND_INTERIOR}


def load_gt():
    entries = []
    for p in GT_FILES:
        if p.is_file():
            entries += json.loads(p.read_text(encoding="utf-8"))
    return entries


def run_one(model, entry, image):
    t0 = time.time()
    try:
        raw = _call_vlm(SYSTEM_GROUND[entry["scenario"]],
                        "Detect all objects. STRICT JSON only.",
                        _to_dataurl(image), model)
        payload = threed_scenarios.extract_json(raw)
    except Exception as e:
        return {"ok": False, "error": str(e)[:120], "secs": round(time.time() - t0, 1)}
    if payload is None:
        return {"ok": False, "error": "not json", "secs": round(time.time() - t0, 1)}
    pred, _, _ = G.normalize_boxes(payload, image.width, image.height,
                                   scenario=entry["scenario"])
    gt, _, _ = G.normalize_boxes(entry, image.width, image.height,
                                 scenario=entry["scenario"])
    return {"ok": True, "secs": round(time.time() - t0, 1),
            **G.probe_metrics(pred, gt)}


def main() -> None:
    from PIL import Image
    gt = load_gt()
    assert gt, "нет GT — сначала Task 1/2"
    cands = G.probe_candidates([m["id"] for m in _vlm_list_cached()])
    print("кандидаты:", cands)
    table = []
    for model in cands:
        rows = []
        for entry in gt:
            img = Image.open(PROBE / entry["image"]).convert("RGB")
            r = run_one(model, entry, img)
            rows.append({"image": entry["image"], **r})
            print(f"  {model} x {entry['image']}: {r}")
        ok_rows = [r for r in rows if r.get("ok")]
        table.append({
            "model": model,
            "iou_mean": (round(sum(r["iou_mean"] for r in ok_rows) / len(ok_rows), 4)
                         if ok_rows else 0.0),
            "recall": (round(sum(r["recall"] for r in ok_rows) / len(ok_rows), 4)
                       if ok_rows else 0.0),
            "json_valid": round(len(ok_rows) / len(rows), 4),
            "rows": rows})
        print(f"{model}: mean IoU {table[-1]['iou_mean']}, "
              f"json_valid {table[-1]['json_valid']}")
    winner, mode = G.pick_model(table)
    out = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "winner": winner,
           "mode": mode, "table": table}
    RESULTS.write_text(json.dumps(out, ensure_ascii=False, indent=1),
                       encoding="utf-8")
    print(f"WINNER: {winner or '(text fallback)'} mode={mode} -> {RESULTS}")


if __name__ == "__main__":
    main()
```

ГРАБЛЯ: зонд импортирует `G.SYSTEM_GROUND_*` — их ещё нет. Поэтому Шаг 5
СОДЕРЖИТ финальные версии промптов (Task 4 их не меняет) — дописать в
`threed/threed_ground.py`:

```python
# ===================== промпты прогона B (з.2) =====================

SYSTEM_GROUND_FACADE = """You are a facade grounding model. Look at the attached
image of a building facade (photo/render/elevation). Detect objects and output
their boxes in ABSOLUTE IMAGE PIXELS. Reply with STRICT JSON ONLY - no markdown
fences, no comments, no extra keys:
{"boxes": [{"label": "window" | "door" | "building",
            "x1": <int>, "y1": <int>, "x2": <int>, "y2": <int>}, ...],
 "meta": {"floors": <int storeys>, "roof": "flat"|"gable"|"hip"|"mansard"}}

Rules:
- "building" = exactly ONE box tightly around the whole main facade volume.
- One box per visible window (a pane group counts as one window); include
  dormer windows in the roof.
- One box per ground-floor entrance door.
- x1 < x2, y1 < y2; coordinates of the ATTACHED image, y axis down.
- Count storeys carefully; meta carries no descriptions.
"""

SYSTEM_GROUND_PLAN = """You are a site-plan grounding model. Look at the attached
top-down master plan / aerial scheme. Detect objects and output their boxes in
ABSOLUTE IMAGE PIXELS. Reply with STRICT JSON ONLY:
{"boxes": [{"label": "building" | "parking" | "sport",
            "x1": <int>, "y1": <int>, "x2": <int>, "y2": <int>}, ...],
 "meta": {"sections": [{"use": "Residential"|"School"|"Kindergarten",
                        "floors": <int>}, ...], "scale_hint": <float m/px>}}

Rules:
- One "building" box per building volume (same order as meta.sections).
- "parking" = ONE single parking stall box; "sport" = one sport ground box
  (they anchor the metric scale).
- x1 < x2, y1 < y2; coordinates of the ATTACHED image, y axis down.
"""

SYSTEM_GROUND_INTERIOR = """You are a floor-plan grounding model. Look at the
attached 2D floor plan drawing. Detect objects and output their boxes in
ABSOLUTE IMAGE PIXELS. Reply with STRICT JSON ONLY:
{"boxes": [{"label": "room" | "door" | "window",
            "x1": <int>, "y1": <int>, "x2": <int>, "y2": <int>}, ...],
 "meta": {"scale_hint": <float m/px>, "wall_height": 2.7}}

Rules:
- One "room" box per enclosed room (inner surface of its walls).
- "door"/"window" = the opening gap on a wall (small elongated box).
- x1 < x2, y1 < y2; coordinates of the ATTACHED image, y axis down.
"""
```

- [ ] **Шаг 6 (LIVE): прогон зонда (~$0.10–0.30)**

```bash
venv\Scripts\python.exe setup_threed.py
venv\Scripts\python.exe data\probe\_probe_threed_ground.py
```

Expected: таблица по каждому кандидату; итог `WINNER: <id> mode=grounding`
или `mode=text` (fallback). Результаты смотреть в
`data/probe/_probe_threed_ground_results.json`.

- [ ] **Шаг 7: констаты в спеку**

В `docs/superpowers/specs/2026-09-26-threed-geometry-ensemble-design.md`
раздел 5 (з.1b) дописать короткий абзац: победитель, mean IoU/recall/
json_valid кандидатов, принятый mode. Значение winner вносить в
`threed_router.py` Task 8 (константа `DEFAULT_ENSEMBLE_MODEL`); при
`mode=text` константа остаётся `""`.

---

### Task 4: Прогон B фасада — промпты + конвертер боксы→сцена (з.2, фасад)

Фасад первым (узкое место доказано, п.45). Конвертер — чистая функция на
синтетических боксах; кластеризация окон по строкам/столбцам; масштаб из
якоря двери → этажа → окна.

**Files:**
- Modify: `threed/threed_ground.py` (конвертер + рантайм-обёртки)
- Test: `tests/test_threed_ground.py` (+2 функции)

**Interfaces:**
- Consumes: `normalize_boxes` (Task 2), `threed_scenarios.validate_facade`.
- Produces:
  - `facade_boxes_to_scene(payload, img_w, img_h) -> (scene, warnings)` —
    raw-сцена под `validate_facade` (только голосующие поля: `storeys`,
    `floor_height`, `width_m`, `depth_m`, `roof`, `windows{rows,cols,w_m,
    h_m,margin_x_m,margin_y_m,skip,shape}`, `entrance`; towers/dormers/
    chimneys/custom_parts НЕ выдаёт — A остаётся единственным источником);
  - `facade_pixel_hint(payload, img_w, img_h) -> (x1,y1,x2,y2) | None` —
    пиксельный bbox здания (оверлей Task 7);
  - `run_ground_pass(scenario, image_url, model, call_vlm) -> (payload,
    warnings)` — вызов VLM по SYSTEM_GROUND_* + extract_json;
  - `run_text_pass(scenario, user_prompt, image_url, model, call_vlm) ->
    (raw_scene, warnings)` — text-fallback B (спека з.1b): тот же
    параметрический промпт, другая модель.

- [ ] **Шаг 1: failing-тесты — дописать в `tests/test_threed_ground.py`**

```python
def _synth_facade_payload():
    """800x600: контур (100,50)-(700,590) = 600x540 px; окна 3 строки x 4
    столбца (w=60,h=80), дверь 60x120 px (якорь 2.1 м -> scale 0.0175)."""
    boxes = [{"label": "building", "x1": 100, "y1": 50, "x2": 700, "y2": 590}]
    for j in range(3):    # строки: y центры 130 / 300 / 470
        for i in range(4):  # столбцы: x центры 190 / 330 / 470 / 610
            cx, cy = 190 + i * 140, 130 + j * 170
            boxes.append({"label": "window", "x1": cx - 30, "y1": cy - 40,
                          "x2": cx + 30, "y2": cy + 40})
    boxes.append({"label": "door", "x1": 370, "y1": 470, "x2": 430, "y2": 590})
    return {"boxes": boxes, "meta": {"floors": 3, "roof": "gable"}}


def test_facade_boxes_to_scene():
    scene, wns = G.facade_boxes_to_scene(_synth_facade_payload(), 800, 600)
    assert not wns, wns
    assert scene["storeys"] == 3 and scene["roof"] == "gable"
    # дверь 120 px * (2.1/120) = масштаб 0.0175; ширина 600 px -> 10.5 м
    assert abs(scene["width_m"] - 10.5) < 0.15, scene["width_m"]
    assert abs(scene["floor_height"] - 540 * 0.0175 / 3) < 0.15
    w = scene["windows"]
    assert (w["rows"], w["cols"]) == (3, 4)
    assert abs(w["w_m"] - 60 * 0.0175) < 0.1 and abs(w["h_m"] - 80 * 0.0175) < 0.1
    assert not any(any(row) for row in w["skip"]), "все окна остеклены"
    e = scene["entrance"]
    assert e and abs(e["x_m"] - (400 - 100) * 0.0175) < 0.1  # центр 400 px
    # сцена проходит штатный валидатор (сравнение идёт по клампнутым полям)
    from threed import threed_scenarios
    fixed, warns = threed_scenarios.validate_facade(dict(scene))
    assert fixed["storeys"] == 3 and fixed["windows"]["rows"] == 3
    print("test_facade_boxes_to_scene OK")


def test_facade_converter_edges():
    # нет окон -> пустая сцена + warning (B выпадает, работаем с A)
    bad = {"boxes": [{"label": "building", "x1": 0, "y1": 0,
                      "x2": 100, "y2": 100}], "meta": {}}
    scene, wns = G.facade_boxes_to_scene(bad, 800, 600)
    assert scene == {} and any("окон" in w for w in wns)
    # пропуск окна: клетка сетки без бокса -> skip=True (строка j=2: cy=470)
    p = _synth_facade_payload()
    p["boxes"] = [b for b in p["boxes"]
                  if not (b["label"] == "window" and b["x1"] == 160
                          and b["y1"] == 430)]  # (3-я строка, 1-й столбец)
    scene2, _ = G.facade_boxes_to_scene(p, 800, 600)
    assert scene2["windows"]["skip"][2][0] is True
    # пиксельный хинт
    hint = G.facade_pixel_hint(_synth_facade_payload(), 800, 600)
    assert hint == (100, 50, 700, 590)
    print("test_facade_converter_edges OK")
```

Раннер: `+ test_facade_boxes_to_scene()` / `+ test_facade_converter_edges()`.

- [ ] **Шаг 2: запуск — FAIL**

Run: `venv\Scripts\python.exe tests\test_threed_ground.py`
Expected: FAIL — `AttributeError: ... no attribute 'facade_boxes_to_scene'`.

- [ ] **Шаг 3: реализация — дописать в `threed/threed_ground.py`**

```python
# ===================== конвертеры боксы -> сцена (з.2) =====================

def _clusters(values, gap):
    """Значения -> список групп индексов: соседние ближе gap в одну группу
    (кластеризация строк/столбцов окон по центрам)."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    groups, last = [], None
    for i in order:
        if last is None or values[i] - values[last] > gap:
            groups.append([i])
        else:
            groups[-1].append(i)
        last = i
    return groups


def _med(vals):
    import statistics
    return statistics.median(vals) if vals else 0.0


def facade_boxes_to_scene(payload, img_w, img_h):
    """Боксы фасада -> raw-сцена validate_facade (только голосующие поля).
    Геометрию считает код: сетка = кластеры центров окон, масштаб = якорь
    двери (2.1 м) -> этажа (3.0 м) -> окна (1.5 м)."""
    boxes, meta, warnings = normalize_boxes(payload, img_w, img_h, "facade")
    wins = [b for b in boxes if b["label"] == "window"]
    doors = [b for b in boxes if b["label"] == "door"]
    bld = next((b for b in boxes if b["label"] == "building"), None)
    if not wins or bld is None:
        return {}, ["facade B: нет боксов окон/контура — сцена B пустая"]
    med_w = _med([b["x2"] - b["x1"] for b in wins])
    med_h = _med([b["y2"] - b["y1"] for b in wins])
    rows_g = _clusters([(b["y1"] + b["y2"]) / 2 for b in wins], 0.6 * med_h)
    cols_g = _clusters([(b["x1"] + b["x2"]) / 2 for b in wins], 0.6 * med_w)
    rows, cols = len(rows_g), len(cols_g)
    row_of, col_of = {}, {}
    for gi, grp in enumerate(rows_g):
        for i in grp:
            row_of[i] = gi
    for gi, grp in enumerate(cols_g):
        for i in grp:
            col_of[i] = gi
    skip = [[True] * cols for _ in range(rows)]
    for i in range(len(wins)):
        skip[row_of[i]][col_of[i]] = False
    try:
        floors = int(meta.get("floors") or 0)
    except (TypeError, ValueError):
        floors = 0
    floors = max(1, min(30, floors or max(rows, 1)))
    b_w, b_h = bld["x2"] - bld["x1"], bld["y2"] - bld["y1"]
    scale = None
    if doors:
        dh = _med([b["y2"] - b["y1"] for b in doors])
        if dh > 2:
            scale = ANCHOR_DOOR_H / dh
    if not scale and b_h > 2:
        scale = (floors * ANCHOR_STOREY) / b_h
    if not scale and med_h > 2:
        scale = ANCHOR_WINDOW_H / med_h
    leftmost = min(b["x1"] for b in wins)
    topmost = min(b["y1"] for b in wins)
    entrance = None
    if doors:
        d0 = min(doors, key=lambda b: b["y2"])  # самая нижняя дверь
        entrance = {"x_m": round(((d0["x1"] + d0["x2"]) / 2 - bld["x1"]) * scale, 2),
                    "w_m": round((d0["x2"] - d0["x1"]) * scale, 2),
                    "style": "porch"}
    roof = meta.get("roof")
    scene = {"storeys": floors,
             "floor_height": round(b_h * scale / floors, 2),
             "width_m": round(b_w * scale, 2), "depth_m": 12.0,
             "roof": roof if roof in ("flat", "gable", "hip", "mansard") else "flat",
             "roof_height": 2.5,
             "windows": {"rows": rows, "cols": cols,
                         "w_m": round(med_w * scale, 2),
                         "h_m": round(med_h * scale, 2),
                         "margin_x_m": round(max((leftmost - bld["x1"]) * scale, 0.05), 2),
                         "margin_y_m": round(max((topmost - bld["y1"]) * scale, 0.05), 2),
                         "skip": skip, "shape": "rect"},
             "entrance": entrance}
    return scene, warnings


def facade_pixel_hint(payload, img_w, img_h):
    """Бокс building -> (x1, y1, x2, y2) пикселей (якорь оверлея фасада)."""
    boxes, _, _ = normalize_boxes(payload, img_w, img_h, "facade")
    b = next((x for x in boxes if x["label"] == "building"), None)
    return (b["x1"], b["y1"], b["x2"], b["y2"]) if b else None


# ===================== рантайм прогона B (вызов VLM) =====================

def run_ground_pass(scenario, image_url, model, call_vlm):
    """Grounding-вызов: SYSTEM_GROUND_* -> strict JSON боксов. (payload |
    None, warnings); None = невалидный ответ (вызывающий работает с A).
    call_vlm передаётся роутером (модуль чистый, invokeai.* не трогает)."""
    system = {"facade": SYSTEM_GROUND_FACADE, "plan": SYSTEM_GROUND_PLAN,
              "interior": SYSTEM_GROUND_INTERIOR}[scenario]
    raw = call_vlm(system, "Detect all objects. STRICT JSON only.",
                   image_url, model)
    payload = threed_scenarios.extract_json(raw)
    if payload is None:
        return None, [f"grounding B: ответ не JSON ({raw[:80]!r})"]
    return payload, []


def run_text_pass(scenario, user_prompt, image_url, model, call_vlm):
    """Text-fallback B (зонд провалился): тот же параметрический промпт, что
    у A, но ДРУГАЯ модель — двухканальность ловит галлюцинации и без
    grounding. Возвращает (raw_scene | None, warnings)."""
    system = {"facade": threed_scenarios.SYSTEM_FACADE,
              "plan": threed_scenarios.SYSTEM_GENPLAN,
              "interior": threed_scenarios.SYSTEM_INTERIOR}[scenario]
    raw = call_vlm(system, user_prompt, image_url, model)
    scene = threed_scenarios.extract_json(raw)
    if scene is None:
        return None, [f"text B: ответ не JSON ({raw[:80]!r})"]
    return scene, []
```

- [ ] **Шаг 4: тест — PASS + деплой**

```bash
venv\Scripts\python.exe tests\test_threed_ground.py     # ALL OK (7 функций)
venv\Scripts\python.exe setup_threed.py                 # грабля п.45-3
```

---

### Task 5: `threed_ensemble.py` — compare + merge + реферти (з.3, фасад)

Сравнение детерминированное; спорное — один реферти-вызов (картинка + оба
варианта ТОЛЬКО спорных полей); сбой/неуверенность → вариант A + warning.

**Files:**
- Create: `threed/threed_ensemble.py`
- Modify: `setup_threed.py` — уже содержит файл (Task 2 шаг 5)
- Test: `tests/test_threed_ensemble.py` (чистая часть)

**Interfaces:**
- Consumes: валидированные сцены A и B (`validate_facade/genplan/interior`).
- Produces:
  - `compare_scenes(scenario, A, B) -> {"agreed": [field...], "disputed":
    {field: (a_repr, b_repr)}, "metrics": {...}, "agree_rate": float}` —
    фасад 7 полей: `storeys`(Δ≥1), `width_m`(Δ>15%), `floor_height`(Δ>10%),
    `windows.rows`/`windows.cols`(Δ≥1), `windows.skip`(Δ≥2 клеток),
    `entrance`(0/1, Δ≥1);
  - `merge_scenes(scenario, A, B, cmp, referee=None) -> (scene, confidence,
    warnings)`; `referee: callable(list[str]) -> {"choices": {field:
    "A"|"B"}} | None`; согласованные числа — среднее (float-поля
    `width_m`/`floor_height`), ints/`skip`/`entrance` — из A; спорные — по
    вердикту реферти, иначе A + warning; base = deepcopy(A);
  - `confidence = {"agree_rate", "disputed_fields", "referee_used"}`;
  - `SYSTEM_REFEREE` — промпт арбитра;
  - `_get(scene, "windows.rows")` / `_set(scene, "windows.rows", v)`.

- [ ] **Шаг 1: failing-тест (файл целиком, чистая часть)**

`tests/test_threed_ensemble.py`:

```python
# -*- coding: utf-8 -*-
"""Ансамбль: compare/merge/реферти (Task 5) + интеграция в роутер (Task 8).
Часть функций — чистые (этот файл, без venv); роутерные — через изолятор."""
import copy
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from threed import threed_ensemble as E  # noqa: E402


def _facade(storeys=5, width=20.0, fh=3.0, rows=2, cols=4, skip=None,
            entrance=True):
    return {"storeys": storeys, "floor_height": fh, "width_m": width,
            "depth_m": 12.0, "roof": "flat", "roof_height": 2.5,
            "windows": {"rows": rows, "cols": cols, "w_m": 1.5, "h_m": 1.5,
                        "margin_x_m": 1.0, "margin_y_m": 0.8,
                        "skip": skip if skip is not None else
                        [[False] * cols for _ in range(rows)],
                        "shape": "rect"},
            "entrance": ({"x_m": 10.0, "w_m": 2.0, "style": "porch"}
                         if entrance else None),
            "balconies": [], "dormers": [], "chimneys": [], "towers": [],
            "custom_parts": [], "colors": {"walls": "#c8b89a"}}


def test_compare_full_agreement():
    A, B = _facade(), _facade(width=20.5)  # Δwidth 2.5% < 15%
    cmp = E.compare_scenes("facade", A, B)
    assert cmp["disputed"] == {}, cmp["disputed"]
    assert cmp["agree_rate"] == 1.0
    assert set(cmp["agreed"]) == {"storeys", "width_m", "floor_height",
                                  "windows.rows", "windows.cols",
                                  "windows.skip", "entrance"}
    print("test_compare_full_agreement OK")


def test_compare_disputes():
    A = _facade()
    B = _facade(storeys=3, width=30.0, fh=3.6, rows=1, entrance=False)
    cmp = E.compare_scenes("facade", A, B)
    # skip спорит из-за формы (rows differ -> матрицы разного размера)
    assert set(cmp["disputed"]) == {"storeys", "width_m", "floor_height",
                                    "windows.rows", "windows.skip",
                                    "entrance"}, cmp["disputed"]
    assert cmp["agree_rate"] == round(1 / 7, 3)  # согласован только cols
    assert abs(cmp["metrics"]["width_m_pct"] - 10 / 30) < 1e-3  # /max(a,b)
    print("test_compare_disputes OK")


def test_skip_dispute_two_cells():
    A = _facade()
    B = _facade()
    B["windows"]["skip"] = [[True, True, False, False], [False] * 4]
    cmp = E.compare_scenes("facade", A, B)
    assert "windows.skip" in cmp["disputed"], "Δ=2 клетки -> спор"
    B2 = _facade()
    B2["windows"]["skip"] = [[True, False, False, False], [False] * 4]
    cmp2 = E.compare_scenes("facade", A, B2)
    assert "windows.skip" not in cmp2["disputed"], "Δ=1 клетка — согласовано"
    print("test_skip_dispute_two_cells OK")


def test_merge_average_and_referee():
    A, B = _facade(width=20.0), _facade(width=21.0)  # Δ5% — согласовано
    cmp = E.compare_scenes("facade", A, B)
    scene, conf, wns = E.merge_scenes("facade", A, B, cmp)
    assert abs(scene["width_m"] - 20.5) < 1e-9, "согласованный float — среднее"
    assert conf["agree_rate"] == 1.0 and conf["referee_used"] is False
    assert not wns

    # спор: реферти выбирает B по storeys, молчит по width_m
    A2, B2 = _facade(storeys=5), _facade(storeys=3, width=40.0)
    cmp2 = E.compare_scenes("facade", A2, B2)
    assert set(cmp2["disputed"]) == {"storeys", "width_m"}
    calls = []

    def referee(fields):
        calls.append(fields)
        return {"choices": {"storeys": "B"}}

    scene2, conf2, wns2 = E.merge_scenes("facade", A2, B2, cmp2, referee=referee)
    assert calls and calls[0] == ["storeys", "width_m"], "спорные поля по алфавиту"
    assert scene2["storeys"] == 3, "выбор B применён"
    assert scene2["width_m"] == 20.0, "реферти молчит -> вариант A"
    assert conf2["referee_used"] is True
    assert any("width_m" in w for w in wns2), "неспособный реферти -> A + warning"

    # реферти выбрал B по ОБОИМ полям -> оба из B
    scene2b, _, _ = E.merge_scenes(
        "facade", A2, B2, cmp2,
        referee=lambda f: {"choices": {"storeys": "B", "width_m": "B"}})
    assert scene2b["storeys"] == 3 and scene2b["width_m"] == 40.0

    # сбой реферти (None) -> всё A, генерация не падает
    scene3, conf3, wns3 = E.merge_scenes(
        "facade", A2, B2, cmp2, referee=lambda f: None)
    assert scene3["storeys"] == 5 and scene3["width_m"] == 20.0
    assert conf3["referee_used"] is False and wns3
    # входы не мутируются
    assert A2["storeys"] == 5 and B2["width_m"] == 40.0
    print("test_merge_average_and_referee OK")


def test_referee_prompt_shape():
    assert "A" in E.SYSTEM_REFEREE and "B" in E.SYSTEM_REFEREE
    s = {"windows": {"rows": 2}}
    assert E._get(s, "windows.rows") == 2
    E._set(s, "windows.rows", 3)
    assert s["windows"]["rows"] == 3
    print("test_referee_prompt_shape OK")


if __name__ == "__main__":
    test_compare_full_agreement()
    test_compare_disputes()
    test_skip_dispute_two_cells()
    test_merge_average_and_referee()
    test_referee_prompt_shape()
    print("ALL OK")
```

- [ ] **Шаг 2: запуск — FAIL**

Run: `venv\Scripts\python.exe tests\test_threed_ensemble.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'threed.threed_ensemble'`.

- [ ] **Шаг 3: реализация (файл целиком)**

`threed/threed_ensemble.py`:

```python
# -*- coding: utf-8 -*-
"""Ансамбль двух извлечений (спека п.60, з.3): детерминированное сравнение
валидированных сцен A и B; слияние согласованного (float — среднее);
спорное — ОДИН реферти-вызов (картинка + оба варианта спорных полей);
сбой/неуверенность реферти -> вариант A + warning. Модуль чистый.

Сравнение фасада (7 полей, пороги спеки): storeys d>=1; width_m d>15%;
floor_height d>10%; windows.rows / windows.cols — несовпадение;
windows.skip — d>=2 клеток; entrance — 0/1 (d>=1)."""

import copy

SYSTEM_REFEREE = """You are a geometry referee. The attached image was analyzed
by two independent extraction passes (A and B); they disagree on a few fields.
For EACH field pick the value that better matches the image. Reply with STRICT
JSON ONLY - no fences, no extra keys:
{"choices": {"<field>": "A" | "B", ...}}

Rules:
- Judge ONLY the listed fields; do not invent new ones.
- If unsure, pick "A" (the primary pass).
"""


def _get(obj, path):
    for k in path.split("."):
        if not isinstance(obj, dict) or k not in obj:
            return None
        obj = obj[k]
    return obj


def _set(obj, path, val):
    keys = path.split(".")
    for k in keys[:-1]:
        obj = obj.setdefault(k, {})
    obj[keys[-1]] = val


def _pct(a, b):
    return abs(a - b) / max(abs(a), abs(b), 1e-9)


def _skip_diff(a, b):
    if not isinstance(a, list) or not isinstance(b, list):
        return 99
    flat_a = [c for row in a for c in row]
    flat_b = [c for row in b for c in row]
    if len(flat_a) != len(flat_b):
        return 99
    return sum(1 for x, y in zip(flat_a, flat_b) if bool(x) != bool(y))


# фасад: (поле, путь|getter, вид сравнения, порог)
_FACADE_FIELDS = (
    ("storeys", "storeys", "int", 1),
    ("width_m", "width_m", "pct", 0.15),
    ("floor_height", "floor_height", "pct", 0.10),
    ("windows.rows", "windows.rows", "int", 1),
    ("windows.cols", "windows.cols", "int", 1),
    ("windows.skip", "windows.skip", "skip", 2),
    ("entrance", "entrance", "flag", 1),
)


def compare_scenes(scenario, A, B):
    """Валидированные A/B -> {agreed, disputed, metrics, agree_rate}.
    plan/interior — Task 9 (до него сравнение этих тем = полное согласие
    по нулевому набору полей, ensemble их не включает)."""
    if scenario == "facade":
        return _compare_facade(A, B)
    return {"agreed": [], "disputed": {}, "metrics": {},
            "agree_rate": 1.0}


def _compare_facade(A, B):
    agreed, disputed, metrics = [], {}, {}
    for field, path, kind, thresh in _FACADE_FIELDS:
        a, b = _get(A, path), _get(B, path)
        if kind == "flag":
            a_n, b_n = 1 if a else 0, 1 if b else 0
            diff = abs(a_n - b_n)
            metrics[field] = (a_n, b_n)
            if diff >= thresh:
                disputed[field] = (a_n, b_n)
            else:
                agreed.append(field)
            continue
        if a is None or b is None:
            metrics[field] = {"a": a, "b": b}
            agreed.append(field)  # нет значения у B — не спор, A прав
            continue
        if kind == "int":
            diff = abs(float(a) - float(b))
        elif kind == "skip":
            diff = _skip_diff(a, b)
        else:
            diff = _pct(float(a), float(b))
            metrics[path.replace(".", "_") + "_pct"] = round(diff, 4)
        if diff > thresh:
            disputed[field] = (a, b)
        else:
            agreed.append(field)
    total = len(agreed) + len(disputed)
    return {"agreed": agreed, "disputed": disputed, "metrics": metrics,
            "agree_rate": round(len(agreed) / total, 3) if total else 1.0}


def merge_scenes(scenario, A, B, cmp, referee=None):
    """Слияние: base = deepcopy(A); согласованные float — среднее; спорные —
    по вердикту реферти (referee(list_fields) -> {"choices": ...} | None),
    неспособный/молчащий реферти -> A + warning. Возвращает (scene,
    confidence, warnings). План/интерьер (Task 9) — компонентное слияние,
    до него проходят base=A."""
    scene = copy.deepcopy(A)
    warnings = []
    disputed = cmp.get("disputed") or {}
    choices = {}
    if disputed and referee is not None:
        try:
            verdict = referee(sorted(disputed))
        except Exception as e:  # сеть/бюджет — не роняем слияние
            verdict = None
            warnings.append(f"ансамбль: реферти сбой ({e}) — спорные из A")
        if isinstance(verdict, dict):
            raw = verdict.get("choices")
            if isinstance(raw, dict):
                choices = {k: v for k, v in raw.items()
                           if k in disputed and v in ("A", "B")}
    # фасад: согласованные float осредняем, спорные точкично
    if scenario == "facade":
        for f in ("width_m", "floor_height"):
            if f in cmp.get("agreed", []):
                a, b = _get(scene, f), _get(B, f)
                if isinstance(a, (int, float)) and isinstance(b, (int, float)):
                    _set(scene, f, round((a + b) / 2, 3))
        for f, (a, b) in disputed.items():
            pick = choices.get(f)
            if pick == "B" and b is not None:
                _set(scene, f, copy.deepcopy(b))
            elif f not in choices:
                warnings.append(f"ансамбль: спор {f} не решён — вариант A")
    confidence = {"agree_rate": cmp.get("agree_rate", 1.0),
                  "disputed_fields": sorted(disputed),
                  "referee_used": bool(choices)}
    return scene, confidence, warnings
```

- [ ] **Шаг 4: тест — PASS + деплой**

```bash
venv\Scripts\python.exe tests\test_threed_ensemble.py   # ALL OK (5 функций)
venv\Scripts\python.exe setup_threed.py                 # грабля п.45-3
```

---

### Task 6: `threed_regular.py` — регуляризация фасада (з.4)

Чистый код, бесплатно. Гейт: `agree_rate ≥ 0.7` — иначе warning «regularization
skipped: low ensemble agreement» (не ломаем VLM-интент: пристройки, эркеры).

**Files:**
- Create: `threed/threed_regular.py`
- Test: `tests/test_threed_regular.py`

**Interfaces:**
- Produces:
  - `REGULAR_GATE = 0.7`;
  - `regularize(scenario, scene, confidence, warnings) -> scene` — гейт +
    диспетчер (`scene`-сценарий и низкий agree_rate → без изменений);
  - `snap(v, step=0.05) -> float`; `rdp(points, eps=2.0) -> points`;
    `orthogonalize(points, tol_deg=15.0, step_deg=90.0) -> points`
    (используются планом/интерьером в Task 9);
  - `regularize_facade(scene) -> scene` — снап `floor_height`/оконных
    размеров к 0.05 м; симметрия skip-строк (|Δлевой/правой половины| ≤ 10%
    → зеркалим худшую половину на лучшую).

- [ ] **Шаг 1: failing-тест (файл целиком)**

`tests/test_threed_regular.py`:

```python
# -*- coding: utf-8 -*-
"""Регуляризация по темам (з.4): гейт agree_rate, снапы, симметрия,
RDP/ортогонализация (plan/interior — Task 9)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from threed import threed_regular as RG  # noqa: E402


def _facade(skip):
    return {"storeys": 5, "floor_height": 3.02, "width_m": 20.0,
            "windows": {"rows": 2, "cols": 4, "w_m": 1.52, "h_m": 1.48,
                        "margin_x_m": 1.03, "margin_y_m": 0.81,
                        "skip": skip, "shape": "rect"}}


def test_gate():
    conf = {"agree_rate": 0.7}
    wn = []
    RG.regularize("facade", _facade([[False] * 4] * 2), conf, wn)
    assert not any("skipped" in w for w in wn)
    conf2 = {"agree_rate": 0.69}
    RG.regularize("facade", _facade([[False] * 4] * 2), conf2, wn)
    assert any("regularization skipped: low ensemble agreement" in w
               for w in wn), wn
    # scene-сценарий не регуляризуется вообще
    wn2 = []
    RG.regularize("scene", {"camera": {}}, {"agree_rate": 1.0}, wn2)
    assert not wn2
    print("test_gate OK")


def test_snaps():
    s = RG.regularize_facade(_facade([[False] * 4] * 2))
    assert s["floor_height"] == 3.0
    assert s["windows"]["w_m"] == 1.5 and s["windows"]["h_m"] == 1.5
    assert s["windows"]["margin_x_m"] == 1.05 and s["margin_y_m"] == 0.8
    print("test_snaps OK")


def test_symmetry_mirror():
    # правило: в строке с |L-R|/max <= 10% (L/R = окна в половинах) половина
    # с МЕНЬШИМ числом окон зеркалится на большую; перевес > 10% ("намеренная
    # асимметрия") и нечётный средний столбец — не трогаются
    # [0,1,1,1]: L=1, R=2, перевес 0.5 -> не трогаем
    s = RG.regularize_facade(_facade([[False, True, True, True]]))
    assert s["windows"]["skip"] == [[False, True, True, True]], "не трогаем"
    # [0,1,1,0]: L=1, R=1, уже симметрична -> без изменений
    s2 = RG.regularize_facade(_facade([[False, True, True, False]]))
    assert s2["windows"]["skip"] == [[False, True, True, False]]
    # [1,1,1,0]: L=2, R=1, перевес 0.5 -> не трогаем
    s3 = RG.regularize_facade(_facade([[True, True, True, False]]))
    assert s3["windows"]["skip"] == [[True, True, True, False]]
    # [0,1,0,1]: L=1, R=1 (в допуске), половины [0,1]/[0,1] разные ->
    # правая зеркалится на левую -> [0,1,1,0]
    s4 = RG.regularize_facade(_facade([[False, True, False, True]]))
    assert s4["windows"]["skip"] == [[False, True, True, False]], s4
    # [0,1,1,0]: L=1, R=1, половины уже зеркальны -> без изменений
    s5 = RG.regularize_facade(_facade([[False, True, True, False]]))
    assert s5["windows"]["skip"] == [[False, True, True, False]]
    print("test_symmetry_mirror OK")


def test_rdp_orthogonalize():
    # RDP: коллинеарная точка выбрасывается
    pts = [[0, 0], [5, 0], [10, 0], [10, 10]]
    assert RG.rdp(pts, eps=0.5) == [[0, 0], [10, 0], [10, 10]]
    # ортогонализация: ребро 88° снапится к 90°, эркер 67.5° не трогается
    nearly = [[0, 0], [100, 0], [100, -3], [100, 100]]  # ребро ~88.3°
    fixed = RG.orthogonalize(nearly, tol_deg=15.0, step_deg=90.0)
    assert fixed[2] == [100, 0], fixed  # снап к горизонтальному ребру
    bay = [[0, 0], [38, 0], [52, -16], [66, 0], [104, 0], [104, 50],
           [0, 50]]  # рёбра эркера ~66-68°
    same = RG.orthogonalize(bay, tol_deg=15.0, step_deg=90.0)
    assert same == bay, "эркер вне допуска 15° — не трогаем"
    print("test_rdp_orthogonalize OK")


if __name__ == "__main__":
    test_gate()
    test_snaps()
    test_symmetry_mirror()
    test_rdp_orthogonalize()
    print("ALL OK")
```

- [ ] **Шаг 2: запуск — FAIL**

Run: `venv\Scripts\python.exe tests\test_threed_regular.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'threed.threed_regular'`.

- [ ] **Шаг 3: реализация (файл целиком)**

`threed/threed_regular.py`:

```python
# -*- coding: utf-8 -*-
"""Регуляризация по темам (спека п.60, з.4) — чистый код, без VLM.
Гейт agree_rate >= REGULAR_GATE (низкое согласие = VLM-интент нестандартен:
пристройки/эркеры/намеренная асимметрия — не ломаем). Применяется к
сцене-победителю ПОСЛЕ merge, ДО контракта/сборки. Модуль чистый."""

import math

REGULAR_GATE = 0.7


def snap(v, step=0.05):
    """Число к сетке step (0.05 м — BIM-шаг размеров)."""
    return round(round(float(v) / step) * step, 4)


def rdp(points, eps=2.0):
    """Ramer-Douglas-Peucker упрощение полигона (px), замкнуто не
    обрабатываем — вход строителю точки подряд."""
    if len(points) < 3:
        return [list(p) for p in points]
    x1, y1 = points[0]
    x2, y2 = points[-1]
    best, idx = 0.0, -1
    for i, (px, py) in enumerate(points[1:-1], start=1):
        dx, dy = x2 - x1, y2 - y1
        L = math.hypot(dx, dy)
        d = (abs(dx * (y1 - py) - dy * (x1 - px)) / L) if L else \
            math.hypot(px - x1, py - y1)
        if d > best:
            best, idx = d, i
    if best <= eps:
        return [list(points[0]), list(points[-1])]
    return (rdp(points[:idx + 1], eps)[:-1]
            + rdp(points[idx:], eps))


def _snap_angle(a_deg, tol_deg, step_deg):
    """Угол к ближайшему кратному step_deg, если в допуске; иначе как был."""
    k = round(a_deg / step_deg)
    d = abs(a_deg - k * step_deg)
    return k * step_deg if d < tol_deg else a_deg


def orthogonalize(points, tol_deg=15.0, step_deg=90.0):
    """Контур: снап рёбер к k*step_deg в допуске (план 90°, интерьер 45°);
    эркер 67.5° при step 90/45 остаётся (до осей 22.5° > 15°). Точки
    пересчитываются накопленным проходом, замыкание контура сохраняется."""
    if len(points) < 3:
        return [list(p) for p in points]
    pts = [list(map(float, p)) for p in points]
    out = [pts[0]]
    ang = 0.0  # накопленное направление (0 = +x)
    for i in range(1, len(pts)):
        dx, dy = pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]
        edge = math.degrees(math.atan2(dy, dx))
        rel = (edge - ang + 180.0) % 180.0  # направление ребра к текущей базе
        snapped = _snap_angle(rel, tol_deg, step_deg)
        ang += snapped
        L = math.hypot(dx, dy)
        a = math.radians(ang)
        out.append([out[-1][0] + L * math.cos(a),
                    out[-1][1] + L * math.sin(a)])
    # замкнуть в первую точку (полигон): добираем остаточное смещение
    # распределённо не делаем — строитель сам замыкает; возвращаем как есть
    return [[round(p[0], 1), round(p[1], 1)] for p in out]


def regularize(scenario, scene, confidence, warnings):
    """Гейт + диспетчер. Возвращает ТУ ЖЕ сцену (in-place правки полей)."""
    rate = (confidence or {}).get("agree_rate")
    if scenario not in ("facade", "plan", "interior"):
        return scene
    if rate is None or rate < REGULAR_GATE:
        warnings.append("regularization skipped: low ensemble agreement")
        return scene
    if scenario == "facade":
        return regularize_facade(scene)
    return scene  # plan/interior — Task 9


def regularize_facade(scene):
    """Снап размеров к 0.05 м + симметрия сетки окон в зеркальных секциях."""
    if isinstance(scene.get("floor_height"), (int, float)):
        scene["floor_height"] = snap(scene["floor_height"])
    win = scene.get("windows") or {}
    for k in ("w_m", "h_m", "margin_x_m", "margin_y_m"):
        if isinstance(win.get(k), (int, float)):
            win[k] = snap(win[k])
    skip = win.get("skip")
    if isinstance(skip, list) and skip:
        cols = max(len(r) for r in skip)
        half = cols // 2
        if half >= 1:
            for row in skip:
                if len(row) != cols:
                    continue  # клампнуто валидатором, на всякий случай
                left = sum(1 for c in row[:half] if not c)   # окон слева
                right = sum(1 for c in row[cols - half:] if not c)
                if max(left, right) == 0 or \
                        abs(left - right) / max(left, right) > 0.1:
                    continue  # асимметрия намеренная (порог 10%, спека з.4)
                if left >= right:  # худшая (меньше окон) половина — правая
                    for i in range(half):
                        row[cols - 1 - i] = row[i]
                else:
                    for i in range(half):
                        row[i] = row[cols - 1 - i]
                # средний столбец (cols нечётное) не трогаем
    return scene
```

- [ ] **Шаг 4: тест — PASS + деплой**

```bash
venv\Scripts\python.exe tests\test_threed_regular.py    # ALL OK (4 функции)
venv\Scripts\python.exe setup_threed.py                 # грабля п.45-3
```

ПРИМЕЧАНИЕ к тесту `test_symmetry_mirror`: правило зеркалирования — «при
равном числе окон в половинах (≤10%) половина с МЕНЬШИМ числом окон
зеркалится на большую»; строки с перевесом >10% не трогаются. Нечётный
`cols` — средняя колонка не участвует.

---

### Task 7: Визуальный verify — оверлей геометрии на картинку (з.5)

Судья получает МАССИВ из двух dataURL (оригинал + оверлей) в одном
запросе → issues становятся геометрическими. Инвариант: verify не роняет
генерацию.

**Files:**
- Modify: `threed/threed_verify.py`, `threed/threed_router.py` (только
  `_call_vlm` — список картинок)
- Test: `tests/test_threed_verify.py` (+3 функции)

**Interfaces:**
- Produces:
  - `threed_verify.render_overlay(scenario, scene, image, pixel_hint=None)
    -> PIL.Image` — рисует контур+сетку окон (facade), полигоны секций
    (plan), стены/проёмы (interior) поверх КОПИИ исходной картинки;
  - `threed_verify.facade_grid_boxes(scene, pixel_hint, img_w, img_h) ->
    list[[x1,y1,x2,y2]]` — пиксельные боксы окон сетки (та же математика,
    что рисует оверлей фасада; без pixel_hint — фитовое размещение);
    метрика приёмки «IoU оверлея по GT» (Task 10) = `probe_metrics(
    facade_grid_boxes(...), gt_windows)`;
  - `threed_verify.verify(image_url, overview, call_vlm, model,
    overlay_url=None)` — обратная совместимость: без overlay_url поведение
    прежнее (существующие тесты не меняются);
  - `threed_router._call_vlm(system, prompt, image_url, model)`: `image_url`
    дополнительно принимает `list[str]` — все dataURL уходят в один запрос.

- [ ] **Шаг 1: failing-тесты — дописать в `tests/test_threed_verify.py`**

Вставить ПЕРЕД существующими функциями (или после — файл на импорте
`os.environ` не трогает; блок `if __name__` расширить):

```python
def test_render_overlay_facade():
    import sys as _sys
    from pathlib import Path as _P
    _sys.path.insert(0, str(_P(__file__).resolve().parents[1]))
    from threed import threed_verify as V
    from PIL import Image
    scene = {"storeys": 2, "width_m": 10.0, "floor_height": 3.0,
             "windows": {"rows": 2, "cols": 4, "w_m": 1.5, "h_m": 1.5,
                         "margin_x_m": 1.0, "margin_y_m": 0.5,
                         "skip": [[False] * 4, [True] + [False] * 3],
                         "shape": "rect"}}
    im = Image.new("RGB", (800, 600), "white")
    ov = V.render_overlay("facade", scene, im, pixel_hint=(100, 50, 700, 590))
    assert ov.size == (800, 600)
    assert ov.getpixel((0, 0)) == (255, 255, 255), "копия, не исходник"
    px = ov.load()
    assert any(px[x, 50] != (255, 255, 255) for x in range(100, 701)), \
        "контур по верхней грани хинта"
    # без хинта — фит по центру, тоже рисует
    ov2 = V.render_overlay("facade", scene, im)
    assert ov2.size == (800, 600)
    # боксы сетки — та же геометрия, что на оверлее (метрика IoU з.7)
    boxes = V.facade_grid_boxes(scene, (100, 50, 700, 590), 800, 600)
    assert len(boxes) == 2 * 4 - 1, "8 окон - 1 skip"  # rows*cols - skip
    assert all(b[0] >= 100 and b[2] <= 700 for b in boxes)
    # skip-клетки (2-я строка, 1-я колонка) среди боксов нет
    xs = {round(b[0]) for b in boxes}
    assert len(xs) == 4, "4 столбца"
    print("test_render_overlay_facade OK")


def test_render_overlay_plan_interior():
    import sys as _sys
    from pathlib import Path as _P
    _sys.path.insert(0, str(_P(__file__).resolve().parents[1]))
    from threed import threed_verify as V
    from PIL import Image
    plan = {"sections": [{"id": "A", "points_px":
                          [[100, 100], [400, 100], [400, 300], [100, 300]]}]}
    ov = V.render_overlay("plan", plan, Image.new("RGB", (500, 400), "white"))
    assert ov.getpixel((250, 100)) != (255, 255, 255), "верхнее ребро полигона"
    interior = {"walls": [{"points_px": [[60, 60], [460, 60]]}],
                "openings": [{"wall_idx": 0, "x_px": 100, "kind": "door"}]}
    ov2 = V.render_overlay("interior", interior,
                           Image.new("RGB", (500, 400), "white"))
    assert ov2.getpixel((300, 60)) != (255, 255, 255), "стена по горизонтали"
    print("test_render_overlay_plan_interior OK")


def test_verify_two_images():
    import sys as _sys
    from pathlib import Path as _P
    _sys.path.insert(0, str(_P(__file__).resolve().parents[1]))
    from threed import threed_verify as V
    seen = {}

    def call_vlm(system, prompt, image_url, model):
        seen["system"], seen["prompt"] = system, prompt
        seen["images"] = image_url
        return '{"ok": true, "issues": []}'

    v = V.verify("data:image/png;base64,AAA", {"scene": {}, "built": {}},
                 call_vlm, "m", overlay_url="data:image/png;base64,BBB")
    assert v["ok"] is True
    assert seen["images"] == ["data:image/png;base64,AAA",
                              "data:image/png;base64,BBB"], seen["images"]
    assert "ALIGNMENT" in seen["prompt"]
    # без оверлея — прежнее поведение (одна картинка)
    V.verify("data:image/png;base64,AAA", {"scene": {}, "built": {}},
             call_vlm, "m")
    assert seen["images"] == "data:image/png;base64,AAA"
    print("test_verify_two_images OK")
```

Раннер: добавить 3 вызова перед `print("ALL OK")`.

- [ ] **Шаг 2: запуск — FAIL**

Run: `venv\Scripts\python.exe tests\test_threed_verify.py`
Expected: FAIL — `AttributeError: module ... has no attribute 'render_overlay'` в первой новой функции (преждевременный STOP допустим: упадёт раньше раннера; проверить, что СТАРЫЕ функции не упали — запуск без раннера:
`venv\Scripts\python.exe -c "import sys;sys.path.insert(0,'.');import tests.test_threed_verify as t;t.test_scene_overview();print('old ok')"`
Expected: `old ok` — старые тесты живы).

- [ ] **Шаг 3: реализация — дописать в `threed/threed_verify.py`**

После `structural_report` (перед `_normalize_verdict`):

```python
# ===================== оверлей извлечённой геометрии (п.60, з.5) =====================

OVERLAY_COLOR = (255, 59, 48)   # красный DevBIM-оверлей
OVERLAY_DOOR_COLOR = (0, 122, 255)


def facade_grid_boxes(scene, pixel_hint, img_w, img_h):
    """Пиксельные боксы окон сетки фасада (метрика «IoU оверлея по GT» з.7
    и геометрия оверлея — один источник). pixel_hint=None -> фитовое
    размещение (80% ширины, по центру), как в render_overlay."""
    st = max(1, int(scene.get("storeys") or 1))
    w_m = max(0.1, float(scene.get("width_m") or 10))
    fh = float(scene.get("floor_height") or 3)
    if pixel_hint:
        x1, y1, x2, y2 = pixel_hint
    else:
        bw = int(img_w * 0.8)
        bh = int(min(img_h * 0.9, bw * (st * fh) / w_m))
        x1, y1 = (img_w - bw) // 2, (img_h - bh) // 2
        x2, y2 = x1 + bw, y1 + bh
    win = scene.get("windows") or {}
    rows = max(1, int(win.get("rows") or 1))
    cols = max(1, int(win.get("cols") or 1))
    sx = (x2 - x1) / w_m  # px на метр по фасаду
    mx = float(win.get("margin_x_m") or 0) * sx
    ww = min(float(win.get("w_m") or 1.5) * sx, (x2 - x1) / cols)
    wh = min(float(win.get("h_m") or 1.5) * sx, (y2 - y1) / st)
    span = (x2 - x1) - 2 * mx - ww
    step = span / max(cols - 1, 1) if cols > 1 else 0
    skip = win.get("skip") or []
    storey_h = (y2 - y1) / st
    boxes = []
    for j in range(rows):
        cy = y1 + j * storey_h + (storey_h - wh) / 2
        for i in range(cols):
            if j < len(skip) and i < len(skip[j]) and skip[j][i]:
                continue
            cx = x1 + mx + i * step
            boxes.append([cx, cy, cx + ww, cy + wh])
    return boxes


def render_overlay(scenario, scene, image, pixel_hint=None):
    """Сцена-победитель ДО сборки поверх исходной картинки (PIL, паттерн
    draw_overlay скилла tools/image-to-ifc). Ловит ошибки АНАЛИЗА (сборку
    проверяет structural_report п.58). facade: сцена метрическая — пиксельный
    якорь = бокс building прогона B (pixel_hint), без него пропорциональный
    фит. Возвращает НОВУЮ картинку (копию)."""
    from PIL import ImageDraw
    im = image.convert("RGB").copy()
    d = ImageDraw.Draw(im)
    if scenario == "facade":
        st = max(1, int(scene.get("storeys") or 1))
        w_m = max(0.1, float(scene.get("width_m") or 10))
        fh = float(scene.get("floor_height") or 3)
        if pixel_hint:
            x1, y1, x2, y2 = pixel_hint
        else:
            bw = int(im.width * 0.8)
            bh = int(min(im.height * 0.9, bw * (st * fh) / w_m))
            x1, y1 = (im.width - bw) // 2, (im.height - bh) // 2
            x2, y2 = x1 + bw, y1 + bh
        d.rectangle([x1, y1, x2, y2], outline=OVERLAY_COLOR, width=3)
        for b in facade_grid_boxes(scene, pixel_hint, im.width, im.height):
            d.rectangle(b, outline=OVERLAY_COLOR, width=2)
    elif scenario == "plan":
        for sec in scene.get("sections") or []:
            pts = [tuple(p) for p in sec.get("points_px") or []]
            if len(pts) >= 3:
                d.line(pts + [pts[0]], fill=OVERLAY_COLOR, width=3)
    elif scenario == "interior":
        walls = scene.get("walls") or []
        for wall in walls:
            (ax, ay), (bx, by) = wall["points_px"]
            d.line([(ax, ay), (bx, by)], fill=OVERLAY_COLOR, width=3)
        for op in scene.get("openings") or []:
            widx = op.get("wall_idx")
            if not isinstance(widx, int) or not (0 <= widx < len(walls)):
                continue
            (ax, ay), (bx, by) = walls[widx]["points_px"]
            L = math.hypot(bx - ax, by - ay)
            t = min(max(float(op.get("x_px") or 0) / max(L, 1.0), 0.0), 1.0)
            cx, cy = ax + (bx - ax) * t, ay + (by - ay) * t
            r = 6
            d.ellipse([cx - r, cy - r, cx + r, cy + r],
                      outline=OVERLAY_DOOR_COLOR, width=2)
    return im
```

`import math` добавить к импортам файла (верх `threed_verify.py`, рядом с
`json`).

`verify()` — заменить тело промпта/вызова (сигнатура расширяется):

```python
def verify(image_url, overview, call_vlm, model, overlay_url=None):
    """Второй VLM-запрос: картинка (+опционально оверлей з.5) + обзор ->
    вердикт. Отказоустойчиво."""
    prompt = ("An earlier pass analyzed the attached image and built a parametric "
              "3D model. Verify it.\n\n(A) final scene specification:\n"
              + json.dumps(overview.get("scene"), ensure_ascii=False)
              + "\n\n(B) elements actually created in the IFC file:\n"
              + json.dumps(overview.get("built"), ensure_ascii=False)
              + "\n\nCompare (A) and (B) against the image. Reply with STRICT "
                "JSON ONLY: {\"ok\": true|false, \"issues\": [...]}")
    structural = [str(s) for s in (overview.get("structural") or [])
                  if str(s).strip()][:MAX_ISSUES]
    if structural:  # п.58: машинные дефекты сборки — факт, а не догадка VLM
        prompt += ("\n\n(C) machine-detected IFC build defects (deterministic "
                   "ground truth, not guesses — report them as issues):\n- "
                   + "\n- ".join(structural))
    if overlay_url:
        prompt += ("\n\nImage 1 = the source. Image 2 = the SAME source with the "
                   "extracted geometry overlaid in red (contours, window grid, "
                   "walls; blue dots = openings). Check ALIGNMENT of the red "
                   "overlay with the source: shifted grids, wrong counts, "
                   "misplaced contours are issues.")
    images = [image_url, overlay_url] if overlay_url else image_url
    try:
        raw = call_vlm(SYSTEM_VERIFY, prompt, images, model)
    except Exception as e:  # сеть/ключ/таймаут — верификация не роняет генерацию
        return {"ok": None, "error": f"VLM verify error: {e}"}
    return _normalize_verdict(threed_scenarios.extract_json(raw), raw)
```

(изменения против текущего `verify` — только: сигнатура `overlay_url=None`,
блок про ALIGNMENT в промпте и `images`-список в вызове; хвост сохранён
дословно).

`threed_router._call_vlm` — строка `content.append({"type": "image_url", ...})`
заменяется на список-толерантную версию:

```python
    content = [{"type": "text", "text": prompt or "No user prompt; analyze the image."}]
    urls = image_url if isinstance(image_url, list) else ([image_url] if image_url else [])
    for u in urls:
        content.append({"type": "image_url", "image_url": {"url": u}})
```

- [ ] **Шаг 4: тесты — PASS + деплой**

```bash
venv\Scripts\python.exe tests\test_threed_verify.py    # ALL OK (9 старых + 3 новых)
venv\Scripts\python.exe setup_threed.py                # грабля п.45-3/п.58а
```

---

### Task 8: Интеграция в роутер + env + бюджет вызовов + pset + деплой (з.6)

Ядро задачи. Порядок стадий попытки: analysis A → B → compare/merge
(реферти ≤1) → регуляризация (гейт) → контракт/ремонт (interior) → сборка →
verify (оригинал + оверлей). Сбой B — warning, работа с A.

**Files:**
- Modify: `threed/threed_router.py`, `threed/threed_build.py`,
  `tests/test_threed.py`, `tests/test_threed_facade_v2.py`,
  `tests/test_threed_tiered.py`, `tests/test_threed_verify.py`
  (по одной строке `THREED_ENSEMBLE=0` на импорте)
- Test: `tests/test_threed_ensemble.py` (роутерная часть, изолятор)

**Interfaces:**
- Consumes: `threed_ground.run_ground_pass/run_text_pass/
  facade_boxes_to_scene/facade_pixel_hint`, `threed_ensemble.compare_scenes/
  merge_scenes/SYSTEM_REFEREE`, `threed_regular.REGULAR_GATE/regularize`,
  `threed_verify.render_overlay`.
- Produces:
  - env: `THREED_ENSEMBLE` (0/1, дефолт 1), `THREED_ENSEMBLE_MODEL`
    (дефолт — константа `DEFAULT_ENSEMBLE_MODEL` из зонда Task 3; `""` →
    text-fallback на ремонт-модели), `THREED_REFEREE_MODEL` (дефолт
    `openai/gpt-6-sol`, override-стадией НЕ глушится),
    `THREED_MAX_CALLS_PER_ATTEMPT` (дефолт 6);
  - `_ensemble_enabled()/_ensemble_b_model()/_referee_model()/_max_calls()`;
  - `_attempt_calls` (module-level `[0]`, инкремент в `_call_vlm`, сброс в
    `_run_attempt`); `_budget_left() -> bool`;
  - `_generate_impl` → `res["ensemble"] = {"mode", "b_model",
    "agree_rate", "disputed_fields", "pixel_hint"}` (победитель),
    history-записи + то же, dump `_threed_last.json["ensemble"]`, тег
    `ensemble` в `_usage_stage`;
  - `meta["EnsembleAgreement"]` → pset `DevBIM` (4 билдера);
  - `_verify_attempt(scene, ifc_path, structural, ensemble_info)`.

- [ ] **Шаг 1: роутерные failing-тесты — дописать в `tests/test_threed_ensemble.py`**

Изолятор + `_Env` (грабля п.45-3/п.58а — расширенная версия из
`tests/test_threed_tiered.py:34`, 4 новых env-ключа):

```python
TMP = ROOT / "tests" / "_threed_tmp"

_ENS_ENV_KEYS = ("THREED_ENSEMBLE", "THREED_ENSEMBLE_MODEL",
                 "THREED_REFEREE_MODEL", "THREED_MAX_CALLS_PER_ATTEMPT")


class _Env:
    """THREED*-рульки на блок: ensemble-ключи + собственные kwargs снимает/
    ставит, на выходе восстанавливает ВСЁ, что трогал (паттерн
    test_threed_tiered._Env, расширен на ensemble-рульки)."""

    def __init__(self, **kw):
        self.kw, self.saved = kw, {}

    def __enter__(self):
        for k in dict.fromkeys((*_ENS_ENV_KEYS, *self.kw)):
            self.saved[k] = os.environ.get(k)
            os.environ.pop(k, None)
        for k, v in self.kw.items():
            os.environ[k] = v
        return self

    def __exit__(self, *a):
        for k, v in self.saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _router():
    """Роутер дерева с модулями дерева: threed_router импортирует
    build/scenarios/verify/ground/ensemble/regular из venv, где копии
    деплоя могут отставать (грабля п.45-3 / п.58а)."""
    import threed.threed_router as R
    from threed import (threed_build, threed_scenarios, threed_verify,
                        threed_ground, threed_ensemble, threed_regular)
    R.threed_build, R.threed_scenarios, R.threed_verify = (
        threed_build, threed_scenarios, threed_verify)
    R.threed_ground, R.threed_ensemble, R.threed_regular = (
        threed_ground, threed_ensemble, threed_regular)
    return R


def _facade_json():
    return json.dumps(_facade(), ensure_ascii=False)


def test_router_ensemble_happy_path():
    """Порядок стадий: analysis -> B(grounding) -> merge (полное согласие) ->
    verify(2 картинки). Тег ensemble в usage, дамп, pset EnsembleAgreement.
    Геометрия B подобрана под A ( порог согласия): дверь 84px -> масштаб
    0.025; контур 780x550 px -> 19.5м x этаж 2.75 (дельты 2.5%/8.3% < порогов);
    2 строки x 4 столбца окон; нижняя дверь -> entrance."""
    R = _router()
    from PIL import Image
    img = Image.new("RGB", (800, 600), "white")
    calls = []

    def fake_vlm(system, prompt, image_url, model):
        calls.append({"system": system, "images": image_url, "model": model,
                      "stage": R._usage_stage[0]})
        if "facade grounding model" in system:
            boxes = [{"label": "building", "x1": 10, "y1": 40,
                      "x2": 790, "y2": 590},
                     {"label": "door", "x1": 370, "y1": 506,
                      "x2": 430, "y2": 590}]
            for cy in (180, 420):          # 2 строки (зазор 240 > 0.6*80)
                for cx in (190, 370, 550, 730):  # 4 столбца (зазор 180)
                    boxes.append({"label": "window", "x1": cx - 30,
                                  "y1": cy - 40, "x2": cx + 30,
                                  "y2": cy + 40})
            return json.dumps({"boxes": boxes,
                               "meta": {"floors": 5, "roof": "flat"}},
                              ensure_ascii=False)
        if "QA verifier" in system:
            assert isinstance(image_url, list) and len(image_url) == 2, \
                "verify: [оригинал, оверлей] (з.5)"
            return '{"ok": true, "issues": []}'
        return _facade_json()

    R._call_vlm = fake_vlm
    with _Env(THREED_ENSEMBLE="1", THREED_ENSEMBLE_MODEL="fake/qwen",
              THREED_VERIFY="1", THREED_VERIFY_ITERS="0",
              THREED_MODEL="fake/one"):
        res = R._generate_impl("facade", "t", img, TMP)
    stages = [c["stage"] for c in calls]
    assert stages[0] == "analysis" and "ensemble" in stages, stages
    assert calls[1]["model"] == "fake/qwen", "прогон B на ENSEMBLE-модели"
    dump = json.loads((TMP / "_threed_last.json").read_text(encoding="utf-8"))
    ens = dump["ensemble"]
    assert ens["mode"] == "grounding" and ens["agree_rate"] == 1.0, ens
    assert res["ensemble"]["agree_rate"] == 1.0
    # pset EnsembleAgreement в IFC победителя
    import ifcopenshell
    model = ifcopenshell.open(str(TMP / res["name"]))
    rels = [r for r in model.by_type("IfcRelDefinesByProperties")
            if r.RelatingPropertyDefinition.Name == "DevBIM"]
    props = {}
    for q in rels[0].RelatingPropertyDefinition.HasProperties:
        props[q.Name] = getattr(q.NominalValue, "wrappedValue", None)
    assert "EnsembleAgreement" in props and props["EnsembleAgreement"], props
    # usage: моки заменяют _call_vlm целиком -> usage пуст (учёт живых вызовов
    # в _record_usage); проверяем тег косвенно — stages выше уже содержит
    # "ensemble" в момент вызова B
    print("test_router_ensemble_happy_path OK")


def test_router_b_failure_falls_back():
    """Сбой прогона B (не JSON) — warning, генерация на A."""
    R = _router()
    from PIL import Image
    img = Image.new("RGB", (64, 64), "white")

    def fake_vlm(system, prompt, image_url, model):
        if "grounding" in system:
            return "I cannot answer in JSON, sorry"
        if "QA verifier" in system:
            return '{"ok": true, "issues": []}'
        return _facade_json()

    R._call_vlm = fake_vlm
    with _Env(THREED_ENSEMBLE="1", THREED_ENSEMBLE_MODEL="fake/qwen",
              THREED_VERIFY="1", THREED_VERIFY_ITERS="0",
              THREED_MODEL="fake/one"):
        res = R._generate_impl("facade", "t", img, TMP)
    assert any("B" in w for w in res["warnings"]), res["warnings"]
    assert (res.get("ensemble") or {}).get("agree_rate") is None
    print("test_router_b_failure_falls_back OK")


def test_router_ensemble_disabled():
    """THREED_ENSEMBLE=0 — ровно один analysis-вызов, поведение до п.60."""
    R = _router()
    from PIL import Image
    img = Image.new("RGB", (64, 64), "white")
    seen = []

    def fake_vlm(system, prompt, image_url, model):
        seen.append(system[:20])
        if "QA verifier" in system:
            return '{"ok": true, "issues": []}'
        return _facade_json()

    R._call_vlm = fake_vlm
    with _Env(THREED_ENSEMBLE="0", THREED_VERIFY="1",
              THREED_VERIFY_ITERS="0", THREED_MODEL="fake/one"):
        R._generate_impl("facade", "t", img, TMP)
    assert len(seen) == 2, seen  # analysis + verify, без B
    print("test_router_ensemble_disabled OK")


def test_router_budget_and_referee():
    """Бюджет THREED_MAX_CALLS_PER_ATTEMPT=3: analysis(1) + B(1) + реферти(1)
    исчерпали -> verify пропущен (ok=None), генерация жива. Рефери вызывается
    РОВНО один раз; мусорный ответ реферти -> вариант A + warning."""
    R = _router()
    from PIL import Image
    img = Image.new("RGB", (64, 64), "white")
    b_calls, r_calls = [], []

    def fake_vlm(system, prompt, image_url, model):
        if "facade grounding model" in system:
            b_calls.append(1)
            # B: этажей 2 против A=5 -> споры storeys/rows/cols/skip/width/
            # entrance (floor_height совпадёт 3.0)
            return json.dumps({"boxes": [
                {"label": "building", "x1": 0, "y1": 0, "x2": 60, "y2": 60},
                {"label": "window", "x1": 10, "y1": 10, "x2": 30, "y2": 30}],
                "meta": {"floors": 2}}, ensure_ascii=False)
        if "geometry referee" in system:
            r_calls.append(prompt)
            return "garbage not json"
        if "QA verifier" in system:
            return '{"ok": true, "issues": []}'
        return _facade_json()

    R._call_vlm = fake_vlm
    with _Env(THREED_ENSEMBLE="1", THREED_ENSEMBLE_MODEL="fake/qwen",
              THREED_MAX_CALLS_PER_ATTEMPT="3", THREED_VERIFY="1",
              THREED_VERIFY_ITERS="0", THREED_MODEL="fake/one"):
        res = R._generate_impl("facade", "t", img, TMP)
    assert len(b_calls) == 1
    assert len(r_calls) == 1, "реферти <=1 вызова на попытку"
    v = res["verify"]["verdict"]
    assert v["ok"] is None, "verify за бюджетом -> ok=None (не крах)"
    assert res["ensemble"]["agree_rate"] < 1.0
    dump = json.loads((TMP / "_threed_last.json").read_text(encoding="utf-8"))
    assert dump["ensemble"]["disputed_fields"], dump["ensemble"]
    print("test_router_budget_and_referee OK")
```

Раннер файла дополнить 4 вызовами (чистые — уже там).

- [ ] **Шаг 2: запуск — FAIL**

```bash
venv\Scripts\python.exe tests\test_threed_ensemble.py
```
Expected: FAIL на `test_router_ensemble_happy_path` — у роутера нет
`DEFAULT_ENSEMBLE_MODEL`/`_ensemble_enabled` (AttributeError) или B-вызова.

- [ ] **Шаг 3: правки `threed/threed_router.py`**

3а. Импорт-блок (строки 37-40) — добавить три модуля:

```python
try:  # задеплоено в venv
    from invokeai.app.api.routers import (
        threed_build, threed_scenarios, threed_verify,
        threed_ground, threed_ensemble, threed_regular)
except ImportError:  # дерево проекта (тесты)
    from threed import (
        threed_build, threed_scenarios, threed_verify,
        threed_ground, threed_ensemble, threed_regular)
```

3б. Константы и env-хелперы — после `_verify_iters()` (~строка 183):

```python
# --- двухканальный ансамбль (п.60): прогон B + compare/merge + реферти ---
DEFAULT_ENSEMBLE_MODEL = ""  # winner зонда з.1b (Task 3 шаг 7); "" -> text-B
REFEREE_MODEL_DEFAULT = REPAIR_RETRY_MODEL  # sol — ярус выше luna-ремонта


def _ensemble_enabled() -> bool:
    """Двухканальный режим (темы facade/plan/interior): .env THREED_ENSEMBLE=
    0/false/no/off выключает; дефолт ВКЛ (спека з.6)."""
    v = _env_threed_var("THREED_ENSEMBLE")
    return (v if v is not None else "1").strip().lower() not in (
        "0", "false", "no", "off")


def _ensemble_b_model() -> str:
    """Модель прогона B: env THREED_ENSEMBLE_MODEL -> константа зонда.
    "" -> text-fallback на ремонт-модели (спека з.1b)."""
    v = _env_threed_var("THREED_ENSEMBLE_MODEL")
    if v:
        return v
    return DEFAULT_ENSEMBLE_MODEL


def _referee_model() -> str:
    """Модель арбитра споров. ВАЖНО: полным override THREED_MODEL НЕ глушится
    (спека з.3 «отдельное значение, не luna») — судья споров всегда выше
    ярусом, иначе эхо-камера."""
    return _env_threed_var("THREED_REFEREE_MODEL") or REFEREE_MODEL_DEFAULT


def _max_calls() -> int:
    """Лимит VLM-вызовов на ОДНУ попытку (analysis+B+repair+referee+verify;
    спека з.6; эскалация — своя попытка, свой бюджет)."""
    try:
        return max(2, min(20, int(_env_threed_var("THREED_MAX_CALLS_PER_ATTEMPT")
                                  or 6)))
    except ValueError:
        return 6


_attempt_calls = [0]  # счётчик вызовов текущей попытки (сброс в _run_attempt)


def _budget_left() -> bool:
    return _attempt_calls[0] < _max_calls()
```

3в. `_call_vlm` — счётчик бюджета. Первой строкой тела (сразу после
докстринга, перед `from invokeai.app.api.routers.imagerouter import ...`):

```python
    _attempt_calls[0] += 1  # бюджет попытки (п.60 з.6): считаем всё
```

3г. `_generate_impl` — константа пиксельного хинта и функция ансамбля.
Вставить ПЕРЕД `def _attempt(...)`:

```python
    ens_hint = [None]  # пиксельный bbox здания из B (якорь оверлея фасада)

    def _ensemble_pass(user_prompt, scene):
        """Двухканальный режим (п.60): B (grounding|text) -> compare ->
        merge (реферти по спорам, <=1 вызов) -> регуляризация по гейту.
        ЛЮБОЙ сбой — warning + исходная A (не хуже текущего поведения)."""
        if not _ensemble_enabled():
            return scene, None, []
        wns = []
        b_model = _ensemble_b_model()
        info = {"mode": "grounding" if b_model else "text",
                "b_model": b_model or _stage_model("repair")[0],
                "agree_rate": None, "disputed_fields": [], "pixel_hint": None}
        if not _budget_left():
            wns.append("ансамбль: прогон B пропущен — лимит VLM-вызовов попытки")
            return scene, None, wns
        try:
            _usage_stage[0] = "ensemble"
            if b_model:
                payload, b_wns = threed_ground.run_ground_pass(
                    scenario, image_url, b_model, _call_vlm)
                wns += b_wns
                if payload is None:
                    return scene, None, wns
                raw_b = threed_ground.CONVERTERS[scenario](
                    payload, image.width, image.height)[0]
                if scenario == "facade":  # якорь оверлея — бокс building
                    ens_hint[0] = threed_ground.facade_pixel_hint(
                        payload, image.width, image.height)
                    info["pixel_hint"] = ens_hint[0]
            else:
                raw_b, b_wns = threed_ground.run_text_pass(
                    scenario, user_prompt, image_url, info["b_model"], _call_vlm)
                wns += b_wns
                if raw_b is None:
                    return scene, None, wns
            if not raw_b:
                wns.append("ансамбль: сцена B пуста — работаем с A")
                return scene, None, wns
            try:
                if scenario == "facade":
                    b_scene, _ = threed_scenarios.validate_facade(dict(raw_b))
                elif scenario == "plan":
                    b_scene, _ = threed_scenarios.validate_genplan(
                        dict(raw_b), image.width, image.height)
                else:
                    b_scene, _, _ = threed_scenarios.validate_interior(
                        dict(raw_b), image.width, image.height)
            except ValueError as e:
                wns.append(f"ансамбль: сцена B невалидна ({e}) — работаем с A")
                return scene, None, wns
            cmp = threed_ensemble.compare_scenes(scenario, scene, b_scene)

            def referee(fields):
                body = {f: {"A": cmp["disputed"][f][0],
                            "B": cmp["disputed"][f][1]} for f in fields}
                raw = _call_vlm(
                    threed_ensemble.SYSTEM_REFEREE,
                    "Image = the source the fields were extracted from.\n"
                    "Disputed fields of two independent extractions:\n"
                    + json.dumps(body, ensure_ascii=False)
                    + "\nFor EACH field pick the value better matching the "
                      "image. STRICT JSON only.", image_url, _referee_model())
                return threed_scenarios.extract_json(raw)

            _usage_stage[0] = "ensemble"
            scene, confidence, m_wns = threed_ensemble.merge_scenes(
                scenario, scene, b_scene, cmp,
                referee=referee if cmp["disputed"] and _budget_left() else None)
            wns += m_wns
            if cmp["disputed"] and not _budget_left():
                wns.append("ансамбль: реферти за бюджетом — спорные из A")
            info["agree_rate"] = confidence["agree_rate"]
            info["disputed_fields"] = confidence["disputed_fields"]
            if confidence["agree_rate"] >= threed_regular.REGULAR_GATE:
                scene = threed_regular.regularize(scenario, scene,
                                                  confidence, wns)
            else:
                wns.append("regularization skipped: low ensemble agreement")
        except Exception as e:
            wns.append(f"ансамбль: сбой прогона B ({e}) — работаем с A")
            return scene, None, wns
        return scene, confidence, wns
```

3д. В `_attempt` — вызов ансамбля ПОСЛЕ валидаторов, ДО контракта/сборки.
Заменить блок валидации (строки 435-455) на:

```python
        contract_issues = []
        if scenario == "interior":
            scene, warnings, contract_issues = threed_scenarios.validate_interior(
                scene, image.width, image.height)
        elif scenario == "scene":
            scene, warnings = threed_scenarios.validate_scene(scene)
        elif scenario == "facade":
            scene, warnings = threed_scenarios.validate_facade(scene)
        else:
            scene, warnings = threed_scenarios.validate_genplan(
                scene, image.width, image.height)
        ensemble_info = None
        if scenario in ("facade", "plan", "interior"):
            scene, ensemble_info, ens_wns = _ensemble_pass(user_prompt, scene)
            warnings += ens_wns
            if scenario == "interior" and ensemble_info:
                # merge мог заменить комнаты/стены — перепосадить проёмы
                # константами п.55 (общий импорт, не дублировать)
                threed_scenarios._seat_openings(scene, warnings, contract_issues)
        if scenario == "interior" and contract_issues:
            try:  # ремонт ПОСЛЕ merge (порядок стадий спеки з.6)
                if not _budget_left():
                    raise ValueError("лимит VLM-вызовов попытки")
                fixed, rep_wns, contract_issues = _repair_scene(
                    scene, contract_issues, image.width, image.height)
            except Exception as e:  # сеть/ключ/бюджет — ремонт не роняет попытку
                rep_wns = [f"контракт: ремонт не удался ({e})"]
            else:
                if fixed is not None:
                    scene = fixed
            warnings = list(warnings) + rep_wns
```

И `meta` (строки 460-461) дополнить:

```python
        meta = {"Scenario": scenario, "Prompt": prompt, "Model": a_model,
                "Source": "3D Design"}
        if ensemble_info and ensemble_info.get("agree_rate") is not None:
            meta["EnsembleAgreement"] = json.dumps(
                {"agree_rate": ensemble_info["agree_rate"],
                 "disputed_fields": ensemble_info["disputed_fields"],
                 "mode": ensemble_info["mode"]}, ensure_ascii=False)
```

Возврат `_attempt` не меняется (`ensemble_info` уходит через замыкание —
см. 3е).

3е. `_verify_attempt` — оверлей + бюджет. Заменить целиком:

```python
    def _verify_attempt(scene, ifc_path, structural, ensemble_info=None):
        """... (прежний докстринг) + оверлей з.5: судья получает
        [оригинал, оверлей сцены-победителя ДО сборки]."""
        if not _budget_left():
            raise ValueError("verify: лимит VLM-вызовов попытки")
        _usage_stage[0] = "verify"
        overlay_url = None
        try:
            ov = threed_verify.render_overlay(
                scenario, scene, image, pixel_hint=ens_hint[0])
            overlay_url = _to_dataurl(ov)
        except Exception:
            pass  # оверлей не критичен: судья увидит хотя бы оригинал
        overview = {"scene": threed_verify.scene_overview(scenario, scene),
                    "built": threed_verify.built_overview(ifc_path),
                    "structural": (structural or {}).get("issues") or []}
        return {"overview": overview, "ensemble": ensemble_info,
                "verdict": threed_verify.verify(
                    image_url, overview, _call_vlm, stage_models["verify"],
                    overlay_url=overlay_url)}
```

3ж. `_run_attempt` — сброс бюджета, ensemble в history/res. Первой строкой
тела: `_attempt_calls[0] = 0`. Вызов verify (строка 541):
`verify_payload = _verify_attempt(scene, ifc_path, structural, ensemble_info)`
— `ensemble_info` берётся из замыкания `_attempt` (после его возврата
значение уже выставлено; присвоить в `_run_attempt` перед вызовом:
`ensemble_info = None` — недостижимо, поэтому проще: `_attempt` возвращает
его 7-м элементом). ИТОГО: возврат `_attempt` (строка 472) становится:

```python
        return scene, warnings, ifc_path, preview_path, raw_head, \
            contract_issues, ensemble_info
```

распаковка в `_run_attempt` (строка 512):

```python
            scene, warnings, ifc_path, preview_path, raw_head, c_issues, \
                ens_info = _attempt(user_prompt, attempt_no,
                                    model_override=a_model, stage=stage)
```

history-запись (строка 547) дополнить `"ensemble": ens_info,`;
`res_i` (строка 559) дополнить `("ensemble": ens_info)` при не-None:

```python
        res_i = {"name": ifc_path.name, "warnings": warnings,
                 "structural": structural}
        if ens_info is not None:
            res_i["ensemble"] = ens_info
```

Сбойная ветка `attempt failed` (строка 521) — без изменений.

3з. Dump (строка 635-641) — ключ победителя:

```python
    dump = {"ts": datetime.now().isoformat(), "scenario": scenario, "prompt": prompt,
            "model": model, "warnings": res["warnings"], "name": ifc_path.name,
            "stages": stage_models,
            "ensemble": res.get("ensemble"),
            "image": {"bytes": img_bytes, "sha1": img_sha1,
                      "w": image.width, "h": image.height},
            "vlm_head": raw_head, "usage": usage_sum, "verify": dump_verify,
            "structural": res.get("structural")}
```

3и. `CONVERTERS` — дописать в `threed/threed_ground.py` (фасад уже есть;
plan/interior появятся в Task 9, до того — заглушки, чтобы роутер не падал):

```python
# конвертеры по темам (plan/interior — Task 9); роутер зовёт через словарь
CONVERTERS = {"facade": facade_boxes_to_scene}
```

(Task 9 заменит строку на полную карту.)

- [ ] **Шаг 4: `EnsembleAgreement` в pset — `threed/threed_build.py`**

В четырёх местах pset `DevBIM` (`build_genplan` ~стр. 82, `build_facade`
~стр. 374, `build_interior` ~стр. 856, `build_scene` ~стр. 1234 — искать
`_properties(model, project, "DevBIM"`) добавить ключ в словарь значений:

```python
        "EnsembleAgreement": (meta.get("EnsembleAgreement") or ""),
```

- [ ] **Шаг 5: ретро-тесты — одна строка на файл (грабля «моки ломаются B-вызовом»)**

В `tests/test_threed.py` (рядом с `os.environ["THREED_VERIFY"] = "0"`,
строка 14), `tests/test_threed_facade_v2.py`, `tests/test_threed_tiered.py`,
`tests/test_threed_verify.py` (в шапку после вставки sys.path) добавить:

```python
os.environ["THREED_ENSEMBLE"] = "0"  # ретро-тесты: без прогона B (п.60)
```

В `test_threed_tiered.py` `_Env` НЕ расширяется (ключ ставится на импорте
и живёт до конца процесса; изоляция новых рулек — в
`tests/test_threed_ensemble.py:_Env`).

- [ ] **Шаг 6: деплой + прогон всех threed-тестов**

```bash
venv\Scripts\python.exe setup_threed.py
venv\Scripts\python.exe tests\test_threed_ground.py
venv\Scripts\python.exe tests\test_threed_ensemble.py
venv\Scripts\python.exe tests\test_threed_regular.py
venv\Scripts\python.exe tests\test_threed.py
venv\Scripts\python.exe tests\test_threed_facade_v2.py
venv\Scripts\python.exe tests\test_threed_tiered.py
venv\Scripts\python.exe tests\test_threed_verify.py
```

Expected: каждый файл печатает `ALL OK` (ground 7, ensemble 9, regular 4,
verify 12, ретро — прежние 20/10/5).

- [ ] **Шаг 7: деплой-проверка вживую (рестарт + health-check + 1 генерация ~$0.3)**

JS-бандлы задачей не трогаются, но спека з.6 требует контрольную проверку
парсинга после деплоя (AGENTS.md-бойплейт; имя бандла — актуальный
`index-*.js`, как в HANDOFF):

```bash
node -e "import('file:///C:/Users/Lenovo/Desktop/проект SOFT_2/Дизайн/InvokeAI/InvokeAI/venv/Lib/site-packages/invokeai/frontend/web/dist/assets/index-BFW2ubNY.js').catch(e=>console.log(e.message))"
```
Expected: только `document is not defined` (НЕ SyntaxError).

```powershell
launch\_restart_server.ps1
```

Health-check (гейт-кука — паттерн п.56):
```bash
venv\Scripts\python.exe -c "import requests,re;pw=re.search(r'^SITE_PASSWORD=(.+)$',open('.env',encoding='utf-8').read(),re.M).group(1).strip();s=requests.Session();s.post('http://127.0.0.1:9090/auth/login',data={'password':pw},allow_redirects=False);r=s.get('http://127.0.0.1:9090/api/v1/threed/model');print(r.status_code,r.json().get('stages'))"
```
Expected: `200 {...}`. Затем одна живая генерация фасада
(`tests\_e2e_3d_roundtrip.py --runs 1 --label smoke ...`), в дампе
`data/ifc/_threed_last.json` — ключ `ensemble` (mode/agree_rate), в
`ir_server.log` — тег `ensemble` у второго вызова. При `mode=text` без
зонда — это ожидаемо (DEFAULT_ENSEMBLE_MODEL="" до Task 3 шага 7, если
Task 3 выполнялся раньше — реальный winner).

- [ ] **Шаг 8: константа зонда**

Если Task 3 уже прогнан: вписать winner в `DEFAULT_ENSEMBLE_MODEL`
(`threed/threed_router.py`) и перезапустить шаг 6 (деплой+тесты). Если
зонд дал `mode=text` — константа остаётся `""` (text-fallback).

---

### Task 9: Портирование на plan + interior — конвертеры, споры, регуляризация (з.2–4)

Механика та же, различия — в полях сравнения и регуляризации (ортогональный
снап, RDP, пересечения футпринтов, замыкание комнат, толщины стен, снап 45°).

**Files:**
- Modify: `threed/threed_ground.py` (`plan_boxes_to_scene`,
  `interior_boxes_to_scene`, `lsq_scale`, полная карта `CONVERTERS`),
  `threed/threed_ensemble.py` (compare/merge plan+interior),
  `threed/threed_regular.py` (`regularize_plan/interior`)
- Test: `tests/test_threed_ground.py` (+2), `tests/test_threed_ensemble.py`
  (+2), `tests/test_threed_regular.py` (+2)

**Interfaces:**
- Produces:
  - `threed_ground.lsq_scale(pairs) -> float` — МНК по якорям
    (спека з.4: «МНК по всем якорям сразу»; пары (px, m));
  - `threed_ground.plan_boxes_to_scene(payload, img_w, img_h) ->
    (scene, warnings)` — raw под `validate_genplan`: секции из ортогона-
    лизированных боксов + `use/floors` из `meta.sections` (по порядку),
    Ground-контекст на всю картинку, масштаб = МНК по parking/sport;
  - `threed_ground.interior_boxes_to_scene(payload, img_w, img_h) ->
    (scene, warnings)` — raw под `validate_interior`: outline = union
    комнат (shapely), стены = рёбра комнат (дедуп общих, внешние 0.35 /
    внутренние 0.12 м), проёмы привязаны к ближайшей стене с `x_px` вдоль;
  - `CONVERTERS = {"facade": ..., "plan": ..., "interior": ...}`;
  - ensemble: plan-поля `sections_count`(Δ≥1), `footprint_iou`(<0.6,
    min по matched парам), `floors`(Δ≥1 max), `width_m`(Δ>20%, крупнейшая
    секция), `scale`(Δ>15%); interior-поля `rooms_count`(Δ≥1),
    `walls_len`(Δ>15%), `doors_count`/`windows_count`(Δ≥1), `rooms.wh`
    (Δ>15% max по matched комнатам); merge plan/interior — компонентный:
    спор о секциях → `sections` целиком из A|B (большинство голосов полей
    компонента), `scale` → точечно; спор интерьера → `rooms+walls+outline`
    и `openings` двумя компонентами;
  - regular: `regularize_plan` (ортоснап <15°, RDP при >8 вершинах,
    снятие пересечений футпринтов shapely-difference), `regularize_interior`
    (снап рёбер стен к k·45° в допуске 15°, замыкание комнат buffer(0),
    толщины: наружные clamp 0.3–0.4 → 0.35, перегородки 0.1–0.15 → 0.12).

- [ ] **Шаг 1: failing-тесты конвертеров — в `tests/test_threed_ground.py`**

```python
def test_lsq_scale():
    # синтетика плана: 0.25 м/px; якорь спорт 68px/34м + стойло 10px/2.5м
    s = G.lsq_scale([(68, 17.0), (136, 34.0), (10, 2.5)])
    assert abs(s - 0.25) < 0.01, s
    assert G.lsq_scale([]) == 0.0
    print("test_lsq_scale OK")


def test_plan_and_interior_converters():
    # план из генератора Task 1: 3 корпуса + sport + parking
    import json as _json
    gt = _json.loads((ROOT / "data" / "probe" /
                      "_threed_ground_gt_synthetic.json").read_text(encoding="utf-8"))
    plan_entry = next(e for e in gt if e["scenario"] == "plan")
    payload = {"boxes": [{"label": "building", "x1": b["box"][0],
                          "y1": b["box"][1], "x2": b["box"][2],
                          "y2": b["box"][3]} for b in plan_entry["boxes"]
                         if b["label"] == "building"]
               + [{"label": "sport", "x1": 440, "y1": 420,
                   "x2": 508, "y2": 556},
                  {"label": "parking", "x1": 700, "y1": 470,
                   "x2": 710, "y2": 490}],
               "meta": {"sections": [
                   {"use": "Residential", "floors": 5},
                   {"use": "School", "floors": 3},
                   {"use": "Kindergarten", "floors": 2}]}}
    scene, wns = G.plan_boxes_to_scene(payload, 1024, 768)
    assert len(scene["sections"]) == 3 and not wns, wns
    assert abs(scene["metres_per_trace_pixel"] - 0.25) < 0.02, \
        scene["metres_per_trace_pixel"]  # МНК по двум якорям
    assert scene["sections"][1]["use"] == "School"
    assert scene["context"][0]["kind"] == "Ground"
    from threed import threed_scenarios
    fixed, _ = threed_scenarios.validate_genplan(dict(scene), 1024, 768)
    assert len(fixed["sections"]) == 3

    # интерьер: 3 комнаты генератора Task 1 (0.01 м/px)
    payload2 = {"boxes": [
        {"label": "room", "x1": 60, "y1": 60, "x2": 460, "y2": 350},
        {"label": "room", "x1": 60, "y1": 350, "x2": 460, "y2": 640},
        {"label": "room", "x1": 460, "y1": 60, "x2": 840, "y2": 640},
        {"label": "door", "x1": 455, "y1": 190, "x2": 465, "y2": 280},
        {"label": "door", "x1": 160, "y1": 345, "x2": 250, "y2": 355},
        {"label": "window", "x1": 835, "y1": 200, "x2": 845, "y2": 320}],
        "meta": {"scale_hint": 0.01}}
    scene2, wns2 = G.interior_boxes_to_scene(payload2, 900, 700)
    assert len(scene2["rooms"]) == 3
    assert scene2["outline"], "union комнат -> outline"
    assert abs(scene2["metres_per_trace_pixel"] - 0.01) < 0.002, \
        "якорь: длинная сторона двери 90 px = 0.9 м"
    # 12 рёбер комнат - 3 поглощённых (право Living, право Bedroom в левом
    # ребре Kitchen; верх Bedroom в низе Living) = 9 стен; внутренние 2
    # (ребро x=460 между Living/Bedroom и Kitchen; ребро y=350)
    assert len(scene2["walls"]) == 9, scene2["walls"]
    assert sum(1 for w in scene2["walls"] if w["exterior"]) == 7
    assert len(scene2["openings"]) == 3
    assert all(isinstance(o["wall_idx"], int) for o in scene2["openings"])
    f2, w2, i2 = threed_scenarios.validate_interior(dict(scene2), 900, 700)
    assert len(f2["rooms"]) == 3
    print("test_plan_and_interior_converters OK")
```

Раннер: + `test_lsq_scale()`, `+ test_plan_and_interior_converters()`.

- [ ] **Шаг 2: реализация конвертеров — в `threed/threed_ground.py`**

ГРАБЛЯ (п.45-3): в venv нет пакета `threed` — шапку модуля (Task 2 шаг 3)
дополнить вторым try/except-импортом (цикла нет: regular не импортирует
ground):

```python
try:  # ортогонализация рёбер — общий хелпер regular (venv | дерево)
    from invokeai.app.api.routers import threed_regular
except ImportError:
    from threed import threed_regular
```

Конвертеры:

```python
def lsq_scale(pairs):
    """МНК-масштаб по якорям (px, м): scale = sum(px*m)/sum(px*px).
    0.0 = якорей нет (вызывающий берёт scale_hint/дефолт)."""
    if not pairs:
        return 0.0
    sx = sum(px * m for px, m in pairs)
    sxx = sum(px * px for px, m in pairs)
    return sx / sxx if sxx > 0 else 0.0


def _scale_from_anchors(boxes, hint, lo=0.05, hi=10.0):
    """Масштаб плана: parking (2.5x5) + sport (17x34) якоря -> МНК; иначе
    hint; иначе дефолт генплана."""
    anchors = []
    for b in boxes:
        w, h = b["x2"] - b["x1"], b["y2"] - b["y1"]
        if b["label"] == "parking":
            anchors += [(min(w, h), ANCHOR_PARKING[0]), (max(w, h), ANCHOR_PARKING[1])]
        elif b["label"] == "sport":
            anchors += [(min(w, h), ANCHOR_SPORT[0]), (max(w, h), ANCHOR_SPORT[1])]
    scale = lsq_scale(anchors)
    if not (lo <= scale <= hi):
        try:
            scale = float(hint or 0) or threed_scenarios.DEFAULT_SCALE
        except (TypeError, ValueError):
            scale = threed_scenarios.DEFAULT_SCALE
    return scale


def plan_boxes_to_scene(payload, img_w, img_h):
    """Боксы генплана -> raw-сцена validate_genplan. Ортогонализация контуров
    — в regularize_plan (з.4); тут прямоугольники боксов как есть.
    threed_regular импортирован в шапке модуля (try/except venv|дерево)."""
    boxes, meta, warnings = normalize_boxes(payload, img_w, img_h, "plan")
    blds = [b for b in boxes if b["label"] == "building"]
    if not blds:
        return {}, ["plan B: нет боксов зданий — сцена B пустая"]
    scale = _scale_from_anchors(boxes, meta.get("scale_hint"))
    sections_meta = meta.get("sections") if isinstance(
        meta.get("sections"), list) else []
    sections = []
    for i, b in enumerate(blds):
        m = sections_meta[i] if i < len(sections_meta) and isinstance(
            sections_meta[i], dict) else {}
        use = m.get("use")
        if use not in ("Residential", "School", "Kindergarten"):
            use = "Residential"
        try:
            floors = int(m.get("floors") or 5)
        except (TypeError, ValueError):
            floors = 5
        pts = threed_regular.orthogonalize(
            [[b["x1"], b["y1"]], [b["x2"], b["y1"]],
             [b["x2"], b["y2"]], [b["x1"], b["y2"]]])
        sections.append({"id": f"B{i + 1}", "building": f"B{i + 1}",
                         "use": use, "floors": max(1, min(30, floors)),
                         "points_px": pts, "partial": False})
    scene = {"trace_width": int(img_w), "trace_height": int(img_h),
             "metres_per_trace_pixel": round(scale, 4),
             "residential_storey_height": 3.1, "public_storey_height": 3.3,
             "sections": sections,
             "context": [{"kind": "Ground", "z": -0.45, "depth": 0.35,
                          "points_px": [[0, 0], [img_w, 0],
                                        [img_w, img_h], [0, img_h]]}]}
    return scene, warnings


def _collinear_contained(a, b):
    """Отрезок a содержится в коллинеарном b (допуск 1 px)."""
    (ax1, ay1), (ax2, ay2) = a
    (bx1, by1), (bx2, by2) = b
    cross = (ax2 - ax1) * (by2 - by1) - (ay2 - ay1) * (bx2 - bx1)
    if abs(cross) > 1e-6 * (1 + abs(bx2 - bx1) + abs(by2 - by1)):
        return False

    def within(px, py):
        return (min(bx1, bx2) - 1 <= px <= max(bx1, bx2) + 1
                and min(by1, by2) - 1 <= py <= max(by1, by2) + 1)

    return within(ax1, ay1) and within(ax2, ay2)


def interior_boxes_to_scene(payload, img_w, img_h):
    """Боксы плана этажа -> raw-сцена validate_interior: outline = union
    комнат, стены = рёбра комнат (общие/поглощённые рёбра схлопываются,
    выжившее ребро между комнатами = внутренняя стена), проёмы к ближайшей
    стене. Толщины: все 0.35 (наружная), общие рёбра помечаются interior;
    нормализация толщин — regularize_interior (з.4)."""
    import math as _math
    from shapely.geometry import Polygon
    boxes, meta, warnings = normalize_boxes(payload, img_w, img_h, "interior")
    rooms = [b for b in boxes if b["label"] == "room"]
    ops = [b for b in boxes if b["label"] in ("door", "window")]
    if not rooms:
        return {}, ["interior B: нет боксов комнат — сцена B пустая"]
    # якорь двери: ДЛИННАЯ сторона бокса = ширина проёма 0.9 м (короткая —
    # толщина стены, не масштаб)
    door_ws = [max(b["x2"] - b["x1"], b["y2"] - b["y1"]) for b in ops
               if b["label"] == "door"]
    scale = ANCHOR_DOOR_W / _med(door_ws) if door_ws else 0.0
    try:
        hint = float(meta.get("scale_hint") or 0)
    except (TypeError, ValueError):
        hint = 0.0
    if not (0.001 <= scale <= 0.5):
        scale = hint or 0.01
    # outline: union прямоугольников комнат
    uni = None
    for r in rooms:
        p = Polygon([(r["x1"], r["y1"]), (r["x2"], r["y1"]),
                     (r["x2"], r["y2"]), (r["x1"], r["y2"])])
        uni = p if uni is None else uni.union(p)
    outline = [[round(x), round(y)] for x, y in
               list(uni.exterior.coords)[:-1]] if uni and uni.is_valid else []

    def edges(r):
        x1, y1, x2, y2 = r["x1"], r["y1"], r["x2"], r["y2"]
        return [[(x1, y1), (x2, y1)], [(x2, y1), (x2, y2)],
                [(x2, y2), (x1, y2)], [(x1, y2), (x1, y1)]]

    # стены: рёбра по убыванию длины; ребро, содержащееся в уже принятом
    # коллинеарном, НЕ добавляется, а помечает то внутренним (граница комнат)
    edges_all = [e for r in rooms for e in edges(r)]
    edges_all.sort(key=lambda e: -_math.hypot(e[1][0] - e[0][0],
                                              e[1][1] - e[0][1]))
    walls = []
    for e in edges_all:
        hit = False
        for w in walls:
            if _collinear_contained(e, w["points_px"]):
                w["exterior"] = False
                hit = True
        if not hit:
            walls.append({"points_px": [list(e[0]), list(e[1])],
                          "thickness_m": 0.35, "exterior": True})

    openings = []
    for b in ops:
        cx, cy = (b["x1"] + b["x2"]) / 2, (b["y1"] + b["y2"]) / 2
        best, best_d = None, 1e18
        for wi, wl in enumerate(walls):
            (ax, ay), (bx2, by2) = wl["points_px"]
            dx, dy = bx2 - ax, by2 - ay
            L2 = dx * dx + dy * dy or 1.0
            t = max(0.0, min(1.0, ((cx - ax) * dx + (cy - ay) * dy) / L2))
            px, py = ax + t * dx, ay + t * dy
            d = (cx - px) ** 2 + (cy - py) ** 2
            if d < best_d:
                best, best_d = (wi, t), d
        if best is None:
            continue
        wi, t = best
        (ax, ay), (bx2, by2) = walls[wi]["points_px"]
        L = _math.hypot(bx2 - ax, by2 - ay)
        openings.append({
            "wall_idx": wi,
            "x_px": round(t * L, 1),
            "width_m": round(max(b["x2"] - b["x1"], b["y2"] - b["y1"]) * scale, 2),
            "height_m": 2.1 if b["label"] == "door" else 1.5,
            "sill_m": 0.0 if b["label"] == "door" else 0.9,
            "kind": b["label"]})
    scene = {"trace_width": int(img_w), "trace_height": int(img_h),
             "metres_per_trace_pixel": round(scale, 4), "wall_height": 2.7,
             "outline": outline, "walls": walls, "openings": openings,
             "rooms": [{"name": f"Room {i + 1}", "type": "other",
                        "points_px": [[r["x1"], r["y1"]], [r["x2"], r["y1"]],
                                      [r["x2"], r["y2"]], [r["x1"], r["y2"]]]}
                       for i, r in enumerate(rooms)],
             "furniture": []}
    return scene, warnings


# конвертеры по темам (роутер зовёт через словарь)
CONVERTERS = {"facade": facade_boxes_to_scene,
              "plan": plan_boxes_to_scene,
              "interior": interior_boxes_to_scene}
```

(заготовку `CONVERTERS` из Task 8 шаг 3и заменить этой картой).

- [ ] **Шаг 3: failing-тесты ensemble plan/interior — в `tests/test_threed_ensemble.py`**

```python
def _plan_scene(n=3, floors=(5, 3, 2), scale=0.25):
    def poly(i):
        x = 100 + i * 250
        return [[x, 100], [x + 200, 100], [x + 200, 300], [x, 300]]
    return {"trace_width": 1024, "trace_height": 768,
            "metres_per_trace_pixel": scale,
            "residential_storey_height": 3.1, "public_storey_height": 3.3,
            "sections": [{"id": f"B{i}", "building": f"B{i}",
                          "use": "Residential", "floors": floors[i],
                          "points_px": poly(i), "partial": False}
                         for i in range(n)],
            "context": [{"kind": "Ground", "z": -0.45, "depth": 0.35,
                         "points_px": [[0, 0], [1024, 0], [1024, 768],
                                       [0, 768]]}]}


def test_compare_plan():
    A = _plan_scene()
    B = _plan_scene(floors=(5, 3, 5))          # спор floors (Δ=3 у 3-й)
    cmp = E.compare_scenes("plan", A, B)
    assert cmp["disputed"] == {"floors": (2, 5)}, cmp["disputed"]
    B2 = _plan_scene(n=2)                      # спор числа секций
    cmp2 = E.compare_scenes("plan", A, B2)
    assert "sections_count" in cmp2["disputed"]
    # IoU футпринтов: B сдвинул первую секцию на 150 px (>40% ширины)
    B3 = _plan_scene()
    B3["sections"][0]["points_px"] = [[400, 100], [600, 100],
                                      [600, 300], [400, 300]]
    cmp3 = E.compare_scenes("plan", A, B3)
    assert "footprint_iou" in cmp3["disputed"], cmp3["disputed"]
    print("test_compare_plan OK")


def test_merge_plan_component():
    A, B = _plan_scene(), _plan_scene(floors=(5, 3, 5))
    cmp = E.compare_scenes("plan", A, B)
    # реферти выбирает B по floors -> секции ЦЕЛИКОМ из B (компонентно)
    scene, conf, wns = E.merge_scenes(
        "plan", A, B, cmp, referee=lambda f: {"choices": {"floors": "B"}})
    assert scene["sections"][2]["floors"] == 5
    assert scene["metres_per_trace_pixel"] == 0.25  # scale не спорили
    # большинство за A -> секции A
    scene2, _, _ = E.merge_scenes(
        "plan", A, B, cmp, referee=lambda f: {"choices": {}})
    assert scene2["sections"][2]["floors"] == 2
    print("test_merge_plan_component OK")


def _interior_scene(rooms=3, doors=2, windows=1):
    walls = [[(60, 60), (460, 60)], [(460, 60), (460, 640)],
             [(460, 640), (60, 640)], [(60, 640), (60, 60)],
             [(60, 350), (460, 350)]]
    return {"trace_width": 900, "trace_height": 700,
            "metres_per_trace_pixel": 0.01, "wall_height": 2.7,
            "outline": [[60, 60], [460, 60], [460, 640], [60, 640]],
            "walls": [{"points_px": list(w), "thickness_m": 0.35,
                       "exterior": True} for w in walls],
            "openings": ([{"wall_idx": 1, "x_px": 130.0, "width_m": 0.9,
                           "height_m": 2.1, "sill_m": 0.0, "kind": "door"}]
                         * doors
                         + [{"wall_idx": 2, "x_px": 140.0, "width_m": 1.2,
                             "height_m": 1.5, "sill_m": 0.9,
                             "kind": "window"}] * windows),
            "rooms": [{"name": f"R{i}", "type": "other",
                       "points_px": [[60, 60], [300, 60], [300, 350],
                                     [60, 350]]} for i in range(rooms)],
            "furniture": []}


def test_compare_interior():
    A = _interior_scene()
    B = _interior_scene(doors=4)
    cmp = E.compare_scenes("interior", A, B)
    assert cmp["disputed"] == {"doors_count": (2, 4)}, cmp["disputed"]
    B2 = _interior_scene(rooms=5)
    assert "rooms_count" in E.compare_scenes("interior", A, B2)["disputed"]
    print("test_compare_interior OK")
```

Раннер: + 3 функции (итого 12).

- [ ] **Шаг 4: реализация compare/merge plan+interior — в `threed/threed_ensemble.py`**

Заменить «заглушку» `compare_scenes` и дополнить `merge_scenes`:

```python
def _poly_iou(pa, pb):
    """IoU полигонов px (shapely); 0.0 при невалидных."""
    try:
        from shapely.geometry import Polygon
        a, b = Polygon(pa), Polygon(pb)
        if not a.is_valid or not b.is_valid or a.area + b.area <= 0:
            return 0.0
        return a.intersection(b).area / a.union(b).area
    except Exception:
        return 0.0


def _match_sections(A, B):
    """Секции A/B -> список (i, j, iou) жадно по лучшему IoU."""
    out = []
    used = set()
    for i, sa in enumerate(A["sections"]):
        best, bj = 0.0, -1
        for j, sb in enumerate(B["sections"]):
            if j in used:
                continue
            iou = _poly_iou(sa["points_px"], sb["points_px"])
            if iou > best:
                best, bj = iou, j
        if bj >= 0:
            used.add(bj)
            out.append((i, bj, best))
    return out


def _compare_plan(A, B):
    agreed, disputed, metrics = [], {}, {}
    matched = _match_sections(A, B)
    iou_by_a = {i: iou for i, j, iou in matched}
    # несопоставленная секция A = IoU 0 (спор футпринта), не «согласие»
    min_iou = min((iou_by_a.get(i, 0.0)
                   for i in range(len(A["sections"]))), default=0.0)
    metrics["footprint_iou"] = round(min_iou, 4)
    if min_iou < 0.6:
        disputed["footprint_iou"] = (round(min_iou, 3), round(min_iou, 3))
    else:
        agreed.append("footprint_iou")
    na, nb = len(A["sections"]), len(B["sections"])
    metrics["sections_count"] = (na, nb)
    if abs(na - nb) >= 1:
        disputed["sections_count"] = (na, nb)
    else:
        agreed.append("sections_count")
    pairs = [(A["sections"][i]["floors"], B["sections"][j]["floors"])
             for i, j, _ in matched]
    dfloors = max((abs(a - b) for a, b in pairs), default=0)
    metrics["floors"] = dfloors
    if dfloors >= 1:
        disputed["floors"] = max(pairs, key=lambda p: abs(p[0] - p[1]))
    else:
        agreed.append("floors")
    wa = max(_bbox_wh(s["points_px"])[0] for s in A["sections"]) * \
        A["metres_per_trace_pixel"]
    wb = max(_bbox_wh(s["points_px"])[0] for s in B["sections"]) * \
        B["metres_per_trace_pixel"]
    metrics["width_m"] = (round(wa, 2), round(wb, 2))
    if _pct(wa, wb) > 0.20:
        disputed["width_m"] = (round(wa, 2), round(wb, 2))
    else:
        agreed.append("width_m")
    sa, sb = A["metres_per_trace_pixel"], B["metres_per_trace_pixel"]
    metrics["scale_pct"] = round(_pct(sa, sb), 4)
    if _pct(sa, sb) > 0.15:
        disputed["scale"] = (sa, sb)
    else:
        agreed.append("scale")
    total = len(agreed) + len(disputed)
    return {"agreed": agreed, "disputed": disputed, "metrics": metrics,
            "agree_rate": round(len(agreed) / total, 3) if total else 1.0}


def _bbox_wh(points):
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return max(xs) - min(xs), max(ys) - min(ys)


def _walls_len(s):
    import math
    return sum(math.hypot(w["points_px"][1][0] - w["points_px"][0][0],
                          w["points_px"][1][1] - w["points_px"][0][1])
               for w in s["walls"])


def _compare_interior(A, B):
    agreed, disputed, metrics = [], {}, {}
    la, lb = _walls_len(A), _walls_len(B)
    metrics["walls_len"] = (round(la), round(lb))
    if _pct(la, lb) > 0.15:
        disputed["walls_len"] = (round(la), round(lb))
    else:
        agreed.append("walls_len")
    for name, kind in (("rooms_count", "rooms"), ("doors_count", None),
                       ("windows_count", None)):
        if kind:
            va, vb = len(A[kind]), len(B[kind])
        else:
            k = "door" if "doors" in name else "window"
            va = sum(1 for o in A["openings"] if o["kind"] == k)
            vb = sum(1 for o in B["openings"] if o["kind"] == k)
        metrics[name] = (va, vb)
        if abs(va - vb) >= 1:
            disputed[name] = (va, vb)
        else:
            agreed.append(name)
    # rooms.wh: max Δ% габарита по matching-у комнат (близкие центры)
    worst = 0.0
    for ra in A["rooms"]:
        wa, ha = _bbox_wh(ra["points_px"])
        for rb in B["rooms"]:
            wb, hb = _bbox_wh(rb["points_px"])
            if abs(_cx(ra) - _cx(rb)) < 50 and abs(_cy(ra) - _cy(rb)) < 50:
                worst = max(worst, _pct(wa, wb), _pct(ha, hb))
    metrics["rooms_wh_pct"] = round(worst, 4)
    (disputed if worst > 0.15 else agreed).append("rooms.wh")
    total = len(agreed) + len(disputed)
    return {"agreed": agreed, "disputed": disputed, "metrics": metrics,
            "agree_rate": round(len(agreed) / total, 3) if total else 1.0}


def _cx(room):
    return sum(p[0] for p in room["points_px"]) / len(room["points_px"])


def _cy(room):
    return sum(p[1] for p in room["points_px"]) / len(room["points_px"])
```

`compare_scenes` — диспетчер:

```python
def compare_scenes(scenario, A, B):
    if scenario == "facade":
        return _compare_facade(A, B)
    if scenario == "plan":
        return _compare_plan(A, B)
    if scenario == "interior":
        return _compare_interior(A, B)
    return {"agreed": [], "disputed": {}, "metrics": {}, "agree_rate": 1.0}
```

(модуль: `import math` в шапку).

`merge_scenes` — после фасадного блока добавить компонентные ветки:

```python
    elif scenario == "plan":
        votes = [choices.get(f) for f in
                 ("sections_count", "footprint_iou", "floors", "width_m")]
        if votes.count("B") > votes.count("A"):
            scene["sections"] = copy.deepcopy(B["sections"])
        elif disputed:
            warnings.append("ансамбль: спор секций не решён — вариант A")
        if choices.get("scale") == "B":
            scene["metres_per_trace_pixel"] = B["metres_per_trace_pixel"]
    elif scenario == "interior":
        votes = [choices.get(f) for f in
                 ("rooms_count", "walls_len", "rooms.wh")]
        if votes.count("B") > votes.count("A"):
            for k in ("rooms", "walls", "outline"):
                scene[k] = copy.deepcopy(B[k])
        elif any(f in disputed for f in ("rooms_count", "walls_len",
                                         "rooms.wh")):
            warnings.append("ансамбль: спор комнат/стен не решён — вариант A")
        votes2 = [choices.get(f) for f in ("doors_count", "windows_count")]
        if votes2.count("B") > votes2.count("A"):
            scene["openings"] = copy.deepcopy(B["openings"])
```

- [ ] **Шаг 5: failing-тесты regular plan/interior — в `tests/test_threed_regular.py`**

```python
def test_regularize_plan():
    scene = {"metres_per_trace_pixel": 0.25,
             "sections": [
                 # верхнее ребро с дрожью 1 px (угол ~0.7° < 15° -> снап к 0°)
                 {"id": "A", "floors": 5, "points_px": [
                     [100, 100], [350, 100], [420, 100], [500, 101],
                     [500, 300], [100, 300]]},
                 # 10 вершин с коллинеарным шумом на верхней грани -> RDP
                 {"id": "C", "floors": 2, "points_px": [
                     [600, 100], [650, 101], [700, 100], [750, 99],
                     [800, 100], [800, 300], [750, 300], [700, 300],
                     [650, 300], [600, 300]]},
                 {"id": "B", "floors": 3, "points_px": [
                     [200, 200], [420, 200], [420, 380], [200, 380]]},
             ]}
    s = RG.regularize("plan", scene, {"agree_rate": 0.9}, [])
    pts = s["sections"][0]["points_px"]
    # дрожавшее ребро стало горизонтальным (все y верхней грани ~100)
    top = pts[:4]
    assert max(abs(p[1] - 100) for p in top) < 1.0, top
    # RDP упростил 10-вершинный контур (коллинеарный шум снят)
    assert len(s["sections"][1]["points_px"]) <= 6, \
        s["sections"][1]["points_px"]
    # пересечение футпринтов снято: B минус A/C (порядок обхода секций)
    from shapely.geometry import Polygon
    polys = [Polygon(sec["points_px"]) for sec in s["sections"]]
    for i in range(len(polys)):
        for j in range(i + 1, len(polys)):
            assert polys[i].intersection(polys[j]).area <= 1.0, \
                f"секции {i} и {j} пересекаются"
    print("test_regularize_plan OK")


def test_regularize_interior():
    scene = {"walls": [  # стена ~50° -> снап к 45° (tan=1); горизонтальная
                          # перегородка не трогается
                       {"points_px": [[0, 0], [100, 119]], "thickness_m": 0.2,
                        "exterior": True},
                      {"points_px": [[0, 0], [200, 0]], "thickness_m": 0.2,
                       "exterior": False}],
             "rooms": [{"name": "R", "type": "other",
                        "points_px": [[0, 0], [100, 0], [100, 100],
                                      [50, 150], [0, 100]]}],
             "openings": []}
    s = RG.regularize("interior", scene, {"agree_rate": 0.9}, [])
    w = s["walls"][0]
    dx = w["points_px"][1][0] - w["points_px"][0][0]
    dy = w["points_px"][1][1] - w["points_px"][0][1]
    assert abs(dy / dx - 1.0) < 0.02, "50° -> 45° (tan=1)"
    # толщины: кламп в диапазоны спеки (наружная -> 0.3..0.4, перегородка
    # -> 0.1..0.15), а не только замена «близких»
    assert 0.3 <= s["walls"][0]["thickness_m"] <= 0.4
    assert 0.1 <= s["walls"][1]["thickness_m"] <= 0.15
    # комната остаётся валидным полигоном после buffer(0)
    from shapely.geometry import Polygon
    p = Polygon(s["rooms"][0]["points_px"])
    assert p.is_valid or p.buffer(0).is_valid
    print("test_regularize_interior OK")
```

Раннер: + 2 функции (итого 6).

- [ ] **Шаг 6: реализация — в `threed/threed_regular.py`**

```python
def regularize_plan(scene):
    """Ортоснап рёбер (<15°), RDP при >8 вершинах, снятие взаимных
    пересечений футпринтов (поздние минус ранние, порядок секций A)."""
    for sec in scene.get("sections") or []:
        pts = sec.get("points_px") or []
        if len(pts) >= 3:
            pts = orthogonalize(pts, tol_deg=15.0, step_deg=90.0)
            if len(pts) > 8:
                pts = rdp(pts, eps=2.0)
            sec["points_px"] = pts
    # пересечения: секция i+1 обрезается о секцию i (shapely difference)
    try:
        from shapely.geometry import Polygon
        polys = []
        for sec in scene.get("sections") or []:
            p = Polygon(sec["points_px"])
            for q in polys:
                p = p.difference(q)
            if not p.is_empty and p.area > 1.0:
                if p.geom_type == "Polygon":
                    sec["points_px"] = [[round(x), round(y)]
                                        for x, y in p.exterior.coords[:-1]]
                    polys.append(Polygon(sec["points_px"]))
                else:  # развалилось на куски — берём крупнейший
                    biggest = max(p.geoms, key=lambda g: g.area)
                    sec["points_px"] = [[round(x), round(y)]
                                        for x, y in biggest.exterior.coords[:-1]]
                    polys.append(Polygon(sec["points_px"]))
    except Exception:
        pass  # shapely недоступен/контур битый — регуляризация не роняет
    return scene


def regularize_interior(scene):
    """Снап рёбер стен к k*45° в допуске 15° (прямой угол и 45° — типовые;
    эркер 67.5° не задевается: до 90° и 45° по 22.5°), кламп толщин в
    диапазоны спеки (наружные 0.3-0.4, перегородки 0.1-0.15), замыкание
    комнат buffer(0)."""
    for wall in scene.get("walls") or []:
        pts = wall.get("points_px")
        if pts and len(pts) == 2:
            ang = math.degrees(math.atan2(pts[1][1] - pts[0][1],
                                          pts[1][0] - pts[0][0]))
            sn = _snap_angle(ang, 15.0, 45.0)
            if sn != ang:
                L = math.hypot(pts[1][0] - pts[0][0], pts[1][1] - pts[0][1])
                a = math.radians(sn)
                pts[1] = [pts[0][0] + L * math.cos(a),
                          pts[0][1] + L * math.sin(a)]
        t = wall.get("thickness_m")
        if isinstance(t, (int, float)):
            if wall.get("exterior"):
                wall["thickness_m"] = min(max(float(t), 0.3), 0.4)
            else:
                wall["thickness_m"] = min(max(float(t), 0.1), 0.15)
    for room in scene.get("rooms") or []:
        pts = room.get("points_px")
        if pts and len(pts) >= 3:
            try:
                from shapely.geometry import Polygon
                p = Polygon(pts).buffer(0)
                if not p.is_empty and p.geom_type == "Polygon":
                    room["points_px"] = [[round(x), round(y)]
                                         for x, y in p.exterior.coords[:-1]]
            except Exception:
                pass
    return scene
```

Диспетчер `regularize` — заменить хвост:

```python
    if scenario == "facade":
        return regularize_facade(scene)
    if scenario == "plan":
        return regularize_plan(scene)
    if scenario == "interior":
        return regularize_interior(scene)
    return scene
```

- [ ] **Шаг 7: прогон + деплой**

```bash
venv\Scripts\python.exe tests\test_threed_ground.py      # 9 функций
venv\Scripts\python.exe tests\test_threed_ensemble.py    # 12 функций
venv\Scripts\python.exe tests\test_threed_regular.py     # 6 функций
venv\Scripts\python.exe setup_threed.py                  # грабля п.45-3
venv\Scripts\python.exe tests\test_threed.py
venv\Scripts\python.exe tests\test_threed_facade_v2.py
venv\Scripts\python.exe tests\test_threed_tiered.py
venv\Scripts\python.exe tests\test_threed_verify.py
```

Expected: все `ALL OK`.

- [ ] **Шаг 8 (LIVE, опционально по бюджету ~$0.35): смоук plan+interior**

```bash
venv\Scripts\python.exe tests\_e2e_3d_roundtrip.py --runs 1 --label ens-smoke --scenario plan --image data\probe\gt_plan_synthetic.png --save data\probe\_ens_smoke_plan.json
venv\Scripts\python.exe tests\_e2e_3d_roundtrip.py --runs 1 --label ens-smoke --scenario interior --image data\probe\gt_interior_synthetic.png --save data\probe\_ens_smoke_interior.json
```

В дампах `data/ifc/_threed_last.json` — `ensemble.mode=grounding`,
`agree_rate` число. Рестарт сервера перед смоуком:
`launch\_restart_server.ps1`.

---

### Task 10: A/B-приёмка E2E + тюнинг + HANDOFF п.60 (з.7)

**Files:**
- Modify: `HANDOFF.md` (п.60)
- Auto: `data/probe/_ab_ensemble*.json` (live)

**Interfaces:**
- Consumes: харнесс Task 1 (`--runs/--label/--save`), baseline из ветки
  `baseline-3d`, таблица приёмки спеки (раздел 11).

- [ ] **Шаг 1 (LIVE, ~$2.3): ensemble-прогоны (сервер с Task 8/9 деплоем)**

```bash
launch\_restart_server.ps1
venv\Scripts\python.exe tests\_e2e_3d_roundtrip.py --runs 3 --label ensemble --scenario facade --image data\probe\vlm_test_house.png --save data\probe\_ab_ensemble.json
venv\Scripts\python.exe tests\_e2e_3d_roundtrip.py --runs 3 --label ensemble --scenario plan --image data\probe\gt_plan_synthetic.png --save data\probe\_ab_ensemble_plan.json
venv\Scripts\python.exe tests\_e2e_3d_roundtrip.py --runs 3 --label ensemble --scenario interior --image data\probe\gt_interior_synthetic.png --save data\probe\_ab_ensemble_interior.json
```

- [ ] **Шаг 2: сравнение с baseline и целями спеки**

Baseline достаётся из ветки:
`git show baseline-3d:data/probe/_ab_baseline.json` (и `_plan`/`_interior`).
Сводка по целям (раздел 11 спеки):

| Метрика | Цель | Где смотреть |
|---|---|---|
| median judge-score facade | ≥ 51 (baseline 43) | `summary.median_score` |
| median judge-score plan/interior | ≥ baseline + 5 | то же |
| agree_rate facade / прочие | ≥ 0.7 / ≥ 0.6 | `summary.agree_rate` |
| structural clean rate | ≥ baseline | `summary.structural_clean_rate` |
| median contract_issues | −30% | `summary.median_contract_issues` |
| median cost_usd | ≤ 2× baseline | `summary.median_cost_usd` |

Дополнительно (после фасадной серии шага 1 — дамп последнего прогона
остаётся в `data/ifc/_threed_last.json`): IoU оверлея по GT, цель mean
IoU ≥ 0.6 (позиционно — только в grounding-режиме; без pixel_hint метрика
фитовая, фиксируется как fact без порога):

```bash
venv\Scripts\python.exe -c "import json,sys;sys.path.insert(0,'.');from threed import threed_ground as G,threed_verify as V;d=json.load(open('data/ifc/_threed_last.json',encoding='utf-8'));assert d['scenario']=='facade','фасад должен быть последним прогоном серии';ov=d['verify']['overview']['scene'];scene={'storeys':ov.get('storeys'),'width_m':ov.get('width_m'),'floor_height':ov.get('floor_height'),'windows':ov.get('windows')};hint=(d.get('ensemble') or {}).get('pixel_hint');gt=json.load(open('data/probe/_threed_ground_gt.json',encoding='utf-8'));wins=[b for e in gt for b in e['boxes'] if b['label']=='window'];boxes=V.facade_grid_boxes(scene,hint,d['image']['w'],d['image']['h']);m=G.probe_metrics(boxes,wins);print('overlay-vs-GT:',m);assert hint is None or m['iou_mean']>=0.6,m"
```

(`pixel_hint` попадает в дамп `ensemble` из Task 8 шаг 3г: `info` несёт
`"pixel_hint": None` и заполняется при grounding-прогоне фасада.)

- [ ] **Шаг 3 (условный): тюнинг при недоборе — НЕ откат архитектуры**

Порядок спеки (раздел 11): (1) поднять пороги споров з.3 (меньше реферти);
(2) снизить гейт регуляризации (`REGULAR_GATE` ниже 0.7); (3) сменить
`THREED_ENSEMBLE_MODEL` (кандидат-2 зонда); (4) последним —
`THREED_ENSEMBLE=0` для проблемной темы. После каждого шага — повторный
прогон шага 1 (только проблемная тема, 3 прогона).

- [ ] **Шаг 4: HANDOFF.md п.60**

Дописать пункт 60 в стиле соседних (что реализовано / конвейер / env /
грабли / стоимость / тесты / откат):

- конвейер: A → B (grounding|text) → compare → merge (реферти ≤1) →
  регуляризация (гейт 0.7) → контракт → сборка → verify [оригинал+оверлей]
  → петля/эскалация;
- env: THREED_ENSEMBLE / _MODEL / REFEREE_MODEL / MAX_CALLS_PER_ATTEMPT
  (+ дефолты и winner зонда);
- грабли: (а) изолятор `_router()` в новых тестах обязателен (п.45-3/п.58а),
  деплой до venv-тестов; (б) ретро-тесты гасят THREED_ENSEMBLE=0 на импорте;
  (в) реферти НЕ глушится THREED_MODEL; (г) verify при исчерпании бюджета
  молчит (ok=None) — это не сбой сети; (д) зонд/эталоны: GT фасада ручной,
  plan/interior — генератор `_make_gt_images.py` (перегенерация =
  детерминированные боксы);
- стоимость: таблица з.8 спеки + фактические medians из A/B;
- метрики A/B: baseline vs ensemble по всем строкам таблицы шага 2;
- откат: THREED_ENSEMBLE=0 (один клик, поведение до п.60), файлы
  threed_ground/ensemble/regular остаются деплоенными (не мешают).

- [ ] **Шаг 5: финальный полный прогон тестов**

```bash
venv\Scripts\python.exe setup_threed.py
venv\Scripts\python.exe tests\test_threed_ground.py
venv\Scripts\python.exe tests\test_threed_ensemble.py
venv\Scripts\python.exe tests\test_threed_regular.py
venv\Scripts\python.exe tests\test_threed_verify.py
venv\Scripts\python.exe tests\test_threed.py
venv\Scripts\python.exe tests\test_threed_facade_v2.py
venv\Scripts\python.exe tests\test_threed_tiered.py
venv\Scripts\python.exe tests\test_threed_ab.py
launch\_restart_server.ps1
```

Expected: 9 × `ALL OK`; сервер поднят (проверка health-check из Task 8
шаг 7).

---

## Self-Review

1. **Покрытие спеки**: з.0 — спека существует (Task 3 шаг 7 дополняет
   констаты зонда); з.1a — Task 2 (GT + IoU + гейт ≥0.9 + минимумы);
   з.1b — Task 3 (метрики, зонд, fallback `pick_model`); з.2 — Task 4
   (фасад) + Task 9 (plan/interior); з.3 — Task 5 (фасад) + Task 9
   (plan/interior, компонентное слияние — «Решённые вопросы» №6); з.4 —
   Task 6 (фасад) + Task 9 (plan/interior; МНК в конвертере — №3); з.5 —
   Task 7 (две картинки судье, `render_overlay`/`facade_grid_boxes`); з.6 —
   Task 8 (env, бюджет, тег ensemble, деплой, pset, dump, node-чек); з.7 —
   Task 1 (baseline ДО задач 2+) + Task 10 (A/B, пороги, тюнинг, HANDOFF).
   Пороги споров (Δ≥1 / 15% / 10% / 20% / IoU 0.6 / skip 2), гейты
   (agree 0.7 / IoU 0.5 / json 0.5), лимиты (≤1 реферти, 6 вызовов) —
   перенесены дословно.
2. **Плейсхолдеры**: код во всех шагах полный; ручная разметка фасада
   (Task 2 шаг 7) и live-прогоны — по природе ручные/платные, оба снабжены
   процедурой и гейтом проверки.
3. **Консистентность имён**: `run_ground_pass/run_text_pass/
   facade_boxes_to_scene/plan_boxes_to_scene/interior_boxes_to_scene/
   facade_pixel_hint/CONVERTERS/lsq_scale/probe_metrics/probe_candidates/
   pick_model/_compute_iou/normalize_boxes/validate_gt` (ground) →
   `compare_scenes/merge_scenes/SYSTEM_REFEREE/_get/_set` (ensemble) →
   `REGULAR_GATE/regularize/snap/rdp/orthogonalize` (regular) →
   `render_overlay/facade_grid_boxes/verify(..., overlay_url)` (verify) →
   `_ensemble_enabled/_ensemble_b_model/_referee_model/_max_calls/
   _budget_left/_attempt_calls/DEFAULT_ENSEMBLE_MODEL/REFEREE_MODEL_DEFAULT`
   (router). Сверено по всем тестам задач 4–9.
4. **Проверенные при ревью и исправленные места** (важно исполнителю):
   - фикстура happy-path (Task 8): геометрия B подобрана под пороги A
     (дверь 84 px → масштаб 0.025; контур 780×550 → 19.5 м × этаж 2.75 —
     дельты 2.5%/8.3% меньше порогов 15%/10%; 2 строки × 4 столбца);
   - `THREED_MAX_CALLS_PER_ATTEMPT=3` в тесте бюджета (analysis+B+реферти
     исчерпывают, verify пропускается) — при 2 реферти не вызывается вовсе;
   - skip-матрицы разной формы (rows differ) = спор `_skip_diff=99`, а не
     согласие (Task 5 тест);
   - `_compare_plan`: `disputed` — dict (первая версия делала `.append()`);
     несопоставленная секция даёт footprint IoU 0;
   - интерьер B: якорь двери — ДЛИННАЯ сторона бокса (короткая = толщина
     стены); стены — поглощение коллинеарных рёбер (9 стен / 7 наружных на
     фикстуре), не точный key-дедуп;
   - `plan_boxes_to_scene` зовёт `threed_regular` через try/except-импорт
     в шапке (в venv нет пакета `threed` — иначе ImportError в деплое);
   - толщины стен — кламп в диапазоны 0.3–0.4/0.1–0.15 (не точечная
     замена «близких»);
   - `_Env` тестов восстанавливает ВСЕ тронутые ключи (включая собственные
     kwargs THREED_VERIFY/THREED_MODEL).
5. **Изоляторы venv (требование пользователя)**: Global Constraints +
   Task 2 шаг 5 (список setup_threed.py + фильтр существующих) +
   расширенный `_router()` (Task 8) + правило «деплой ДО venv-тестов»
   повторено в каждом прогоне задач 2–9.
