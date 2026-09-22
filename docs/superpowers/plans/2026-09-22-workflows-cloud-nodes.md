# Workflows: облачные ноды Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Вкладка Workflows работает на четырёх облачных нодах (Generate / Edit / Ask AI / Upscale) через реальную очередь InvokeAI, библиотека нод ограничена белым списком (~24 типа), стоковые шаблоны заменены пятью облачными.

**Architecture:** Новые инвокации в `devbim_cloud_nodes.py` (деплой в `invokeai/app/invocations/`, паттерн Prompt Enhancer п.22) ходят в API облака из `invoke()`, выполняются реальной очередью (перехват enqueue_batch их не ловит — их поля `model` строки, не ModelField) и сами сохраняют результаты в галерею. Белый список — штатный `nodesAllowlist` в config-slice index-бандла. Шаблоны — замена папки `default_workflows/` (сидинг `_sync_default_workflows` при старте, паттерн пресетов стилей).

**Tech Stack:** Python 3.11 (venv, invokeai 6.2.0), pydantic v2 (динамические `Literal`), requests, правки минифицированных JS-бандлов, plain-assert тесты, Playwright E2E.

**Спека:** `docs/superpowers/specs/2026-09-22-workflows-cloud-nodes-design.md`. Ветка: `workflows` (текущая).

## Отклонения от спеки (обоснованы разведкой этого плана)

1. **`iterate` и `collect` в 6.2 ЕСТЬ** — спека ошиблась («НЕТ нод Collect/Iterate»). Оба типа зарегистрированы декораторами в `app/services/shared/graph.py:258,279` и присутствуют в живом `/openapi.json` (проверено 22.09). Без `iterate` шаблон «Generate and Upscale» невозможен: движок ставит выход-коллекцию в одиночный вход как есть (`_prepare_inputs` → setattr), и pydantic падает `NodeInputError`. → **`iterate` + `collect` добавлены в allowlist (итого 24 типа)**, шаблон 5 идёт через `iterate`.
2. **Нодам generate/edit добавлено одиночное поле `prompt: str` (кроме `prompts: list[str]`).** В 6.2 нельзя соединить одиночный выход со входом-коллекцией: серверная проверка рёбер такое допускает (`from_type in get_args(to_type)`), но подготовка узла падает (`NodeInputError`, см. graph.py:1111-1116, комментарий у класса ошибки). Шаблоны спеки №1 («String Primitive → Generate») и №4 («Ask AI → prompts → Generate») требуют именно одиночную связь. Двойное поле покрывает все источники: одиночный промт (String/Ask AI), батч (Dynamic Prompt/String Collection) и ввод руками.
3. **Note-ноды в шаблонах заменены** полем `notes` воркфлоу (панель Details — паттерн стокового «Face Detailer… See Note in Details») и `label` нод: ни в одном из 14 стоковых JSON и 14 записей живой БД нет Note-ноды, формат фронтендовской zod-схемы нечем верифицировать локально; серверная валидация узлы не проверяет. Риск «воркфлоу не открывается» исключаем.
4. **`devbim_upscale` тоже сохраняет результат в галерею** (в спеке явно сказано только про generate/edit) — консистентность UX: результат виден в галерее без Save-ноды.
5. **Эхо-проверка (`_is_echo`) НЕ применяется к `devbim_edit`** — список моделей админский и дополнительно фильтруется по входу-image из каталога (как у облачного апскейла, п.27).
6. **(при исполнении, Задача 1) `_image_input_ok` = `"image" in inputs` без `or not inputs`** — образец плана противоречил его же тесту (пустой `input_modalities: []` = text-only обязан отсекаться у edit); фикс выровнен с семантикой `_supports_image_input` роутера (imagerouter.py:1033).

## Global Constraints

- НЕ править `venv/.../site-packages` руками — только через `setup_imagerouter.py` (все правки — в исходниках `imagerouter/` + setup-функции).
- Запрещён `from __future__ import annotations` в модулях инвокций (валит старт сервера, грабля п.22 HANDOFF).
- Все патчи идемпотентны; бэкапы: бандлы `*.imagerouter-bak`, шаблоны `<имя>.json.orig`.
- После каждого патча JS-бандла — node-import чек: `node -e "import('file:///…').catch(e=>console.log(e.message))"`, допустима только рантайм-ошибка (не SyntaxError).
- Сервер перезапускать только `_restart_server.ps1` (WMI, отсоединённо). После setup + рестарта пользовательская вкладка браузера обязана перезагрузиться (F5).
- Интерфейс нод — английский, провайдер (ImageRouter) не упоминается (п.48): «Generation service…», «cloud model».
- Секреты в git не входят (`.env`, `companies/*`, `companies.json`).
- Тесты: `PYTHONUTF8=1 venv/Scripts/python.exe tests/<имя>.py` из корня проекта (plain asserts, печать OK).
- `use_cache=False` у всех четырёх нод; таймаут API 300 с; ключ/URL/хелперы — лениво из задеплоенного роутера (единый источник `.env`).
- Коммиты — на ветке `workflows`, сообщения по-русски в стиле `feat(workflows): …`.

## Разведка-факты (для исполнителя, проверено 22.09)

- Якорь allowlist: `nodesAllowlist:void 0,nodesDenylist:void 0` — ровно 1 вхождение в `venv/Lib/site-packages/invokeai/frontend/web/dist/assets/index-BFW2ubNY.js`.
- Каталог живого openapi: все 22 типа из таблицы спеки присутствуют + `iterate`/`collect`; версии нод для шаблонов: `string` 1.0.1, `string_collection` 1.0.2, `dynamic_prompt` 1.0.1, `image` 1.0.2, `image_collection` 1.0.1, `iterate` 1.1.0, `collect` 1.0.0, `save_image` 1.2.2.
- Файлы выбора админа: `<INVOKEAI_ROOT>/data/imagerouter_main_models.json` (в проекте — `data/data/…`, сейчас 16 моделей) и `…/imagerouter_upscale.json`; `DEFAULT_UPSCALE_MODELS` есть в роутере, `DEFAULT_MAIN_MODELS` — НЕТ (добавляем, Задача 4).
- `_sync_default_workflows` (workflow_records_sqlite.py:338) на старте: валидирует JSON (`id` обязан начинаться с `default_`, `meta.category = "default"`), обновляет изменённые, добавляет новые, **удаляет из БД default-воркфлои, которых нет в папке** — стоковые дочистятся сами.
- Серверная валидация шаблона мягкая (`nodes: list[dict]`), строгая — на фронтенде; формат узла брать со стоковых файлов (id/type/position/data{id,version,nodePack,label,notes,type,inputs,isOpen,isIntermediate,useCache}).
- `context.images.save(image=pil, metadata=MetadataField(root={...}))` — штатный паттерн (image.py:69), GENERAL-категория → галерея; метаданные воркфлоу очереди прикладываются автоматически.
- Формат JSON-edits с референсами (п.26): `{"model", "prompt", "image": [data-URL,…], "size"?, "output_format"}` — исходник первым (PNG), референсы JPEG 1024/q85.
- Апскейл-хелперы роутера: `_pick_upscale_size(mid, w, h, scale)` (сетка 64, кап 2048/явные размеры модели) и `_upscale_prompt(scale=None, creativity=None, structure=None, size_label=None)` (серверный EN-промпт).
- Перехват enqueue_batch игнорирует графы наших нод: `_extract_ir_info` ищет ModelField-ключи `imagerouter/…` и spandrel-узлы; строковое поле `model` не матчится.
- Логин для API/E2E: `POST /auth/login` form-data `password=<SITE_PASSWORD из .env>` → кука `devbim_auth`.

---

### Task 1: Модуль нод — ядро: списки моделей, слой API, хелперы

**Files:**
- Create: `imagerouter/devbim_cloud_nodes.py`
- Test: `tests/test_cloud_nodes.py`

**Interfaces:**
- Consumes: задеплоенный роутер `invokeai.app.api.routers.imagerouter` (`_load_key`, `_fetch_ir_models`, `_ir_model_by_id`, `GENERATIONS_URL`, `EDITS_URL`, `DEFAULT_UPSCALE_MODELS`; `DEFAULT_MAIN_MODELS` появится в Задаче 4).
- Produces (для Задач 2–3): `GENERATE_MODELS/EDIT_MODELS/UPSCALE_MODELS: list[str]`, `GenerateModel/EditModel/UpscaleModel/OutputFormat` (Literal-типы), `_api() -> (key, router_module)`, `_post_images(url, body, key) -> list[dict]`, `_prompt_batch(prompt, prompts) -> list[str]`, `_snap_side(v) -> int`, `_save(context, pil, metadata) -> ImageDTO`, константы `MAX_PROMPTS=10`, `MAX_REFERENCES=4`, `MAX_VLM_IMAGES=4`, `REFERENCE_NOTE`, `SYSTEM_ASK`, `DEFAULT_MAIN_FALLBACK`, `DEFAULT_UPSCALE_FALLBACK`.

- [ ] **Step 1: Write the failing test**

Создать `tests/test_cloud_nodes.py`:

```python
# -*- coding: utf-8 -*-
"""Тесты облачных нод Workflows (devbim_cloud_nodes.py): списки моделей из
файлов администратора, слой API, кап 10, snap64, EN-тексты ошибок.
Инвокции (тела запросов) — в тестах ниже по ходу задач (test_generate/edit/
upscale/vlm). Патч бандла и шаблоны — в тестах задач 5-6 этого же файла.

Запуск: PYTHONUTF8=1 venv/Scripts/python.exe tests/test_cloud_nodes.py
"""
import importlib.util
import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_NODES = None


def _prime_catalog(catalog):
    """Прогреть кэш каталога задеплоенного роутера ДО импорта модуля нод —
    убирает живой HTTP на старте импорта (_model_choices('edit') фильтрует
    по каталогу)."""
    from invokeai.app.api.routers import imagerouter as ir
    ir._ir_models_cache["ts"] = 1e12  # «никогда не протухнет»
    ir._ir_models_cache["items"] = catalog


def nodes():
    global _NODES
    if _NODES is None:
        _prime_catalog([
            {"id": "x/edit-model", "architecture": {"input_modalities": ["image"]}},
            {"id": "x/text-model", "architecture": {"input_modalities": []}},
        ])
        spec = importlib.util.spec_from_file_location(
            "devbim_cloud_nodes", ROOT / "imagerouter" / "devbim_cloud_nodes.py")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod  # регистрация для pydantic-резолва классов
        spec.loader.exec_module(mod)
        _NODES = mod
    return _NODES


def test_model_choices_from_admin_file():
    mod = nodes()
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        # x/text-model есть в прогретом каталоге (нет входа-image) — edit
        # должен его отсечь; посторонние id остаются (нет в каталоге ->
        # не фильтруем, офлайн-старт не ломает дропдаун)
        (d / "imagerouter_main_models.json").write_text(
            json.dumps({"models": ["b/m2", "a/m1", "x/text-model", "b/m2", 7]}), encoding="utf-8")
        (d / "imagerouter_upscale.json").write_text(
            json.dumps({"models": ["u/m9"]}), encoding="utf-8")
        assert mod._model_choices("generate", dirs=[d]) == ["b/m2", "a/m1", "x/text-model"]
        assert mod._model_choices("edit", dirs=[d]) == ["b/m2", "a/m1"]
        assert mod._model_choices("upscale", dirs=[d]) == ["u/m9"]
    print("OK: списки моделей — файл админа, порядок, дубли, фильтр edit")


def test_model_choices_fallbacks():
    mod = nodes()
    with tempfile.TemporaryDirectory() as td:
        got = mod._model_choices("upscale", dirs=[Path(td)])
    # файла нет -> дефолт задеплоенного роутера (DEFAULT_UPSCALE_MODELS,
    # идентичен фолбэку — контроль синхронности в test_router_defaults_sync)
    assert got == list(mod.DEFAULT_UPSCALE_FALLBACK), got
    print("OK: файла нет — дефолты роутера/фолбэки")


def test_prompt_batch():
    mod = nodes()
    assert mod._prompt_batch("house", []) == ["house"]
    assert mod._prompt_batch("", [" a ", "", "roof"]) == ["a", "roof"]
    assert mod._prompt_batch("house", ["house", "roof"]) == ["house", "roof"]  # без дублей
    try:
        mod._prompt_batch("  ", [])
        raise AssertionError("пустой батч должен падать")
    except ValueError as e:
        assert str(e) == "Enter a prompt", str(e)
    try:
        mod._prompt_batch("", [f"p{i}" for i in range(11)])
        raise AssertionError("кап 10 должен падать")
    except ValueError as e:
        assert str(e) == "Batch limited to 10 images per run", str(e)
    print("OK: батч промтов — склейка, дубли, кап 10, EN-ошибки")


def test_snap_side():
    mod = nodes()
    assert mod._snap_side(1024) == 1024
    assert mod._snap_side(1000) == 1024      # (1000+31)//64*64
    assert mod._snap_side(500) == 512
    assert mod._snap_side(333) == 320
    assert mod._snap_side(10) == 128         # нижний кап
    assert mod._snap_side(9999) == 2048      # верхний кап
    print("OK: snap64 + диапазон 128..2048")


def test_post_images_errors():
    mod = nodes()

    class Resp:
        def __init__(self, status, data):
            self.status_code, self._data = status, data
        def json(self):
            if self._data is None:
                raise ValueError("no json")
            return self._data

    saved_requests = mod.requests

    def run(resp):
        mod.requests = SimpleNamespace(post=lambda *a, **k: resp)
        return mod._post_images("http://x", {}, "k")

    try:
        # HTTP 502 с error.message
        try:
            run(Resp(502, {"error": {"message": "boom"}}))
            raise AssertionError("должен упасть")
        except ValueError as e:
            assert str(e) == "Generation failed: boom", str(e)
        # HTTP 200 с error (грабля шлюза из п.26)
        try:
            run(Resp(200, {"error": {"message": "silent fail"}}))
            raise AssertionError("должен упасть")
        except ValueError as e:
            assert str(e) == "Generation failed: silent fail", str(e)
        # HTTP 200 со строкной ошибкой
        try:
            run(Resp(200, {"error": "quota exceeded"}))
            raise AssertionError("должен упасть")
        except ValueError as e:
            assert str(e) == "Generation failed: quota exceeded", str(e)
        # пустой data[]
        try:
            run(Resp(200, {"data": []}))
            raise AssertionError("должен упасть")
        except ValueError as e:
            assert "returned no images" in str(e), str(e)
        # успех
        assert run(Resp(200, {"data": [{"b64_json": "eHg="}]})) == [{"b64_json": "eHg="}]
    finally:
        mod.requests = saved_requests
    print("OK: _post_images — ошибки апстрима в EN, HTTP 200 c error, пустой ответ")


def test_api_no_key():
    mod = nodes()
    from invokeai.app.api.routers import imagerouter as ir
    saved = ir._load_key
    ir._load_key = lambda: None
    try:
        mod._api()
        raise AssertionError("должен упасть без ключа")
    except ValueError as e:
        assert str(e) == ("Generation service is not configured: no API key. "
                          "Please contact your administrator."), str(e)
    finally:
        ir._load_key = saved
    print("OK: нет ключа — EN-ошибка про администратора")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONUTF8=1 venv/Scripts/python.exe tests/test_cloud_nodes.py`
Expected: FAIL — `FileNotFoundError` (нет `imagerouter/devbim_cloud_nodes.py`).

- [ ] **Step 3: Write minimal implementation**

Создать `imagerouter/devbim_cloud_nodes.py`:

```python
# -*- coding: utf-8 -*-
"""DevBIM cloud nodes: облачные инвокации для вкладки Workflows.

Четыре ноды — Generate Image / Edit Image / Ask AI / Upscale Image — ходят
в API облачной генерации из invoke() и выполняются РЕАЛЬНОЙ очередью
InvokeAI: перехват enqueue_batch (посредник Canvas) их не ловит, поля model
у них строки, а не ModelField. Результаты сохраняются в галерею самими
нодами (Save-нода не обязательна). Ключ, URL и хелперы читаются лениво из
задеплоенного роутера invokeai.app.api.routers.imagerouter — единый
источник (.env).

Дропдауны моделей строятся на ИМПОРТЕ модуля (старт сервера) из файлов
выбора администратора; смена списка подхватывается перезапуском сервера
(openapi-схема строится на старте). Запуск ноды с устаревшей моделью падает
валидацией Literal на enqueue — тост со списком допустимых значений.

Деплой: setup_imagerouter.py копирует файл в
invokeai/app/invocations/devbim_cloud_nodes.py (паттерн Prompt Enhancer).
"""
# ВНИМАНИЕ: НЕ добавлять `from __future__ import annotations` — PEP 563
# валит старт сервера (грабля п.22: output_annotation разбирается без eval_str).
import json
import os
import re
from pathlib import Path
from typing import Any, Literal, Optional

import requests
from invokeai.app.invocations.baseinvocation import BaseInvocation, invocation
from invokeai.app.invocations.fields import ImageField, InputField, MetadataField
from invokeai.app.invocations.primitives import ImageCollectionOutput, ImageOutput, StringOutput
from invokeai.app.services.shared.invocation_context import InvocationContext

API_TIMEOUT_S = 300   # таймаут облачного запроса (как TIMEOUT_GENERATE роутера)
MAX_PROMPTS = 10      # кап батча промтов на один запуск ноды
MAX_REFERENCES = 4    # референсов у Edit (лишние молча срезаются)
MAX_VLM_IMAGES = 4    # картинок у Ask AI (лишние молча срезаются)
MIN_SIDE = 128        # диапазон стороны кадра после снапа к 64
MAX_SIDE = 2048
MAX_TOKENS = 1500     # reasoning-модели тратят лимит до начала ответа (п.22)
TEMPERATURE = 0.7
JPEG_QUALITY = 85

# Фолбэки, если задеплоенный роутер недоимортируем на старте (сервер обязан
# подниматься всегда). Актуальные дефолты — в imagerouter_router.py; тест
# test_router_defaults_sync ниже держит их согласованными.
DEFAULT_MAIN_FALLBACK = ["google/nano-banana-2", "openai/gpt-image-2", "qwen/qwen-image"]
DEFAULT_UPSCALE_FALLBACK = [
    "philz1337x/clarity-2x",
    "jingyunliang/swinir-2x",
    "stabilityai/latent-2x",
    "prunaai/P-Image-Upscale",
    "csslc/ccsr-2x",
]

SYSTEM_ASK = (
    "You are a helpful assistant for architects and architectural visualizers. "
    "Look at the attached image(s) and answer the user's question concisely in English."
)

REFERENCE_NOTE = (
    "\n\nImage 1 is the source image to edit. The following images are references "
    "(weight 0.5): follow their style, materials and content."
)


# --- файлы выбора администратора (читаются на ИМПОРТЕ — старт сервера) ---

def _candidate_dirs() -> list[Path]:
    """Каталоги поиска файлов выбора админа. Роутер хранит выбор в
    <INVOKEAI_ROOT>/data; конфиг на импорте может быть ещё не поднят,
    поэтому env и cwd-фолбэки."""
    out: list[Path] = []
    try:
        from invokeai.app.services.config.config_default import get_config
        out.append(Path(get_config().root_path) / "data")
    except Exception:  # noqa: BLE001
        pass
    env_root = os.environ.get("INVOKEAI_ROOT")
    if env_root:
        out.append(Path(env_root) / "data")
    cwd = Path.cwd()
    out += [cwd / "data" / "data", cwd / "data", cwd]
    return out


def _read_admin_ids(filename: str, dirs: Optional[list[Path]] = None) -> list[str]:
    """Список id из файла выбора (порядок админа, без дублей и мусора)."""
    for d in (dirs if dirs is not None else _candidate_dirs()):
        try:
            ids = json.loads((d / filename).read_text(encoding="utf-8")).get("models")
        except Exception:  # noqa: BLE001
            continue
        if isinstance(ids, list):
            out: list[str] = []
            for i in ids:
                if isinstance(i, str) and i and i not in out:
                    out.append(i)
            return out
    return []


def _router_default(name: str, fallback: list[str]) -> list[str]:
    """Дефолтный список из задеплоенного роутера; недоимпорт — локальный."""
    try:
        from invokeai.app.api.routers import imagerouter as _ir
        val = list(getattr(_ir, name))
        return val or fallback
    except Exception:  # noqa: BLE001
        return fallback


def _image_input_ok(mid: str) -> bool:
    """Есть ли у модели вход-image (каталог роутера). Каталог недоступен или
    модели в нём нет — считаем, что есть: лучше лишняя модель в дропдауне,
    чем пустой список при офлайн-старте сервера."""
    try:
        from invokeai.app.api.routers import imagerouter as _ir
        m = _ir._ir_model_by_id(mid)
    except Exception:  # noqa: BLE001
        return True
    if m is None:
        return True
    inputs = ((m.get("architecture") or {}).get("input_modalities")) or []
    return "image" in inputs


def _model_choices(kind: str, dirs: Optional[list[Path]] = None) -> list[str]:
    """Список id для дропдауна ноды: файл выбора админа; нет файла — дефолт
    роутера (DEFAULT_*). kind: generate | edit | upscale; edit фильтруется
    по входу-image из каталога (каталог офлайн — без фильтра)."""
    if kind == "upscale":
        return _read_admin_ids("imagerouter_upscale.json", dirs) or _router_default(
            "DEFAULT_UPSCALE_MODELS", DEFAULT_UPSCALE_FALLBACK
        )
    ids = _read_admin_ids("imagerouter_main_models.json", dirs) or _router_default(
        "DEFAULT_MAIN_MODELS", DEFAULT_MAIN_FALLBACK
    )
    if kind == "edit":
        filtered = [m for m in ids if _image_input_ok(m)]
        if filtered:
            ids = filtered
    return ids


GENERATE_MODELS = _model_choices("generate")
EDIT_MODELS = _model_choices("edit")
UPSCALE_MODELS = _model_choices("upscale")
GenerateModel = Literal[tuple(GENERATE_MODELS)]
EditModel = Literal[tuple(EDIT_MODELS)]
UpscaleModel = Literal[tuple(UPSCALE_MODELS)]
OutputFormat = Literal["png", "jpeg", "webp"]


# --- общий слой API (лениво из роутера: единый источник ключа и URL) ---

def _api() -> tuple[str, Any]:
    """(key, модуль роутера). Ключа нет — ValueError с EN-текстом."""
    from invokeai.app.api.routers import imagerouter as ir
    key = ir._load_key()
    if not key:
        raise ValueError(
            "Generation service is not configured: no API key. "
            "Please contact your administrator."
        )
    return key, ir


def _post_images(url: str, body: dict, key: str) -> list[dict]:
    """POST generations/edits (JSON-тело). Ошибки апстрима — в том числе
    HTTP 200 с {"error": ...} (грабля шлюза, п.26) — ValueError с EN-текстом."""
    resp = requests.post(
        url, headers={"Authorization": f"Bearer {key}"}, json=body, timeout=API_TIMEOUT_S
    )
    try:
        data = resp.json()
    except ValueError:
        data = None
    err = data.get("error") if isinstance(data, dict) else None
    if resp.status_code >= 400 or err:
        msg = err.get("message") if isinstance(err, dict) else (
            err if isinstance(err, str) else None)
        msg = msg or (data.get("detail") if isinstance(data, dict) else None)
        raise ValueError(f"Generation failed: {msg or f'HTTP {resp.status_code}'}")
    items = data.get("data") if isinstance(data, dict) else None
    if not isinstance(items, list) or not items:
        raise ValueError("Generation failed: the generation service returned no images")
    return items


def _prompt_batch(prompt: str, prompts: Optional[list[str]]) -> list[str]:
    """Эффективный батч: элементы коллекции + одиночный промт (без дублей).
    Пусто — ошибка; больше MAX_PROMPTS — ошибка «Batch limited…»."""
    out = [p.strip() for p in (prompts or []) if isinstance(p, str) and p.strip()]
    single = (prompt or "").strip()
    if single and single not in out:
        out.append(single)
    if not out:
        raise ValueError("Enter a prompt")
    if len(out) > MAX_PROMPTS:
        raise ValueError(f"Batch limited to {MAX_PROMPTS} images per run")
    return out


def _snap_side(v: int) -> int:
    """Сторона кадра: сетка 64 (округление вверх), диапазон 128..2048."""
    snapped = (int(v) + 31) // 64 * 64
    return max(MIN_SIDE, min(MAX_SIDE, snapped))


def _save(context: InvocationContext, pil: Any, metadata: dict) -> Any:
    """Сохранить картинку в галерею (GENERAL); метаданные — провенанс ноды."""
    dto = context.images.save(image=pil, metadata=MetadataField(root=metadata))
    print(f"[cloud-node] saved {dto.image_name}", flush=True)
    return dto
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONUTF8=1 venv/Scripts/python.exe tests/test_cloud_nodes.py`
Expected: 6× `OK: …`, выход без traceback.

- [ ] **Step 5: Commit**

```bash
git add imagerouter/devbim_cloud_nodes.py tests/test_cloud_nodes.py
git commit -m "feat(workflows): ядро облачных нод — списки моделей админа, слой API, snap64 (п.1)"
```

---

### Task 2: Ноды Generate Image и Edit Image

**Files:**
- Modify: `imagerouter/devbim_cloud_nodes.py` (дописать в конец)
- Test: `tests/test_cloud_nodes.py` (дописать)

**Interfaces:**
- Consumes: всё из Task 1; роутер: `GENERATIONS_URL`, `EDITS_URL`, `_item_to_pil(item) -> PIL|None`, `_pil_to_durl(pil, fmt="PNG", max_side=0, quality=92) -> str`.
- Produces: инвокации `devbim_generate` (выход `ImageCollectionOutput.collection: list[ImageField]`) и `devbim_edit` (то же); поля для шаблонов Задачи 6: `prompt`, `prompts`, `model`, `width`, `height`, `output_format`, `image`, `references`.

- [ ] **Step 1: Write the failing test**

Дописать в `tests/test_cloud_nodes.py`:

```python
# --- фикстурыinvoke: фейковый роутер/requests/context (задачи 2-3) ---

import io

from PIL import Image


def _fake_ir():
    def durl(img, fmt="PNG", max_side=0, quality=92):
        buf = io.BytesIO()
        img.save(buf, format=fmt)
        import base64
        mime = "png" if fmt == "PNG" else "jpeg"
        return f"data:image/{mime};base64," + base64.b64encode(buf.getvalue()).decode()
    def item_to_pil(item):
        return Image.new("RGB", (8, 8)) if item.get("ok") else None
    return SimpleNamespace(
        GENERATIONS_URL="http://x/generations",
        EDITS_URL="http://x/edits",
        CHAT_COMPLETIONS_URL="http://x/chat",
        _item_to_pil=item_to_pil,
        _pil_to_durl=durl,
        _pick_upscale_size=lambda mid, w, h, s: (
            f"{max(64, (int(w * s) + 31) // 64 * 64)}x{max(64, (int(h * s) + 31) // 64 * 64)}"),
        _upscale_prompt=lambda scale=None, creativity=None, structure=None, size_label=None: (
            f"Upscale to {size_label} resolution." if size_label
            else f"Upscale to approximately {int(round(scale or 2))}x higher resolution."),
        _enhancer_model=lambda: "zai/glm-5.3-flash",
    )


class _Capture:
    def __init__(self, responses):
        self.calls = []
        self.responses = responses
    def post(self, url, headers=None, json=None, timeout=None, **kw):
        self.calls.append({"url": url, "headers": headers, "json": json})
        return self.responses.pop(0)


def _fake_context(saved):
    def get_pil(name, mode=None):
        return Image.new("RGBA", (500, 333), (200, 30, 30, 255))
    def save(image=None, board_id=None, image_category=None, metadata=None):
        dto = SimpleNamespace(image_name=f"img_{len(saved)}.png", width=image.width, height=image.height)
        saved.append((dto, image))
        return dto
    return SimpleNamespace(images=SimpleNamespace(get_pil=get_pil, save=save))


def test_generate_node():
    mod = nodes()
    fake_ir = _fake_ir()
    saved = []
    resp = SimpleNamespace(status_code=200, json=lambda: {"data": [{"ok": True}]})
    mod_requests, saved_api = mod.requests, mod._api
    mod.requests, mod._api = _Capture([resp]), (lambda: ("KEY", fake_ir))
    try:
        node = mod.GenerateImageInvocation(
            prompt="red house", model=mod.GENERATE_MODELS[0], width=1000, height=1000)
        out = node.invoke(_fake_context(saved))
        assert [f.image_name for f in out.collection] == ["img_0.png"]
        body = mod.requests.calls[-1]["json"]
        assert body == {"model": mod.GENERATE_MODELS[0], "prompt": "red house",
                        "size": "1024x1024", "output_format": "png"}, body
        assert mod.requests.calls[-1]["url"] == "http://x/generations"
        assert mod.requests.calls[-1]["headers"] == {"Authorization": "Bearer KEY"}
        # метаданные сохранения
        assert saved[0][1].size == (8, 8)
    finally:
        mod.requests, mod._api = mod_requests, saved_api
    print("OK: devbim_generate — тело generations, size snap64, сохранение в галерею")


def test_generate_node_batch():
    mod = nodes()
    fake_ir = _fake_ir()
    saved = []
    resps = [SimpleNamespace(status_code=200, json=lambda: {"data": [{"ok": True}]}) for _ in range(2)]
    mod_requests, saved_api = mod.requests, mod._api
    mod.requests, mod._api = _Capture(resps), (lambda: ("KEY", fake_ir))
    try:
        node = mod.GenerateImageInvocation(
            prompts=["a", "b"], model=mod.GENERATE_MODELS[0])
        out = node.invoke(_fake_context(saved))
        assert len(out.collection) == 2
        prompts = [c["json"]["prompt"] for c in mod.requests.calls]
        assert prompts == ["a", "b"], prompts
    finally:
        mod.requests, mod._api = mod_requests, saved_api
    print("OK: devbim_generate — батч промтов последовательными вызовами")


def test_edit_node():
    mod = nodes()
    fake_ir = _fake_ir()
    saved = []
    resp = SimpleNamespace(status_code=200, json=lambda: {"data": [{"ok": True}]})
    mod_requests, saved_api = mod.requests, mod._api
    mod.requests, mod._api = _Capture([resp]), (lambda: ("KEY", fake_ir))
    try:
        node = mod.EditImageInvocation(
            image={"image_name": "src.png"},
            references=[{"image_name": "r1.png"}, {"image_name": "r2.png"}],
            prompt="repaint", model=mod.EDIT_MODELS[0])
        out = node.invoke(_fake_context(saved))
        assert len(out.collection) == 1
        body = mod.requests.calls[-1]["json"]
        assert mod.requests.calls[-1]["url"] == "http://x/edits"
        assert body["prompt"].startswith("repaint")
        assert mod.REFERENCE_NOTE in body["prompt"]        # блок референсов дописан
        assert body["size"] == "512x320", body["size"]     # исходник 500x333 -> snap64
        assert len(body["image"]) == 3                     # исходник + 2 референса
        assert body["image"][0].startswith("data:image/png")   # исходник PNG
        assert body["image"][1].startswith("data:image/jpeg")  # референсы JPEG
        assert body["model"] == mod.EDIT_MODELS[0]
        assert body["output_format"] == "png"
    finally:
        mod.requests, mod._api = mod_requests, saved_api
    print("OK: devbim_edit — JSON-edits, референсы, размер от исходника")


def test_edit_node_explicit_size_no_refs():
    mod = nodes()
    fake_ir = _fake_ir()
    saved = []
    resp = SimpleNamespace(status_code=200, json=lambda: {"data": [{"ok": True}]})
    mod_requests, saved_api = mod.requests, mod._api
    mod.requests, mod._api = _Capture([resp]), (lambda: ("KEY", fake_ir))
    try:
        node = mod.EditImageInvocation(
            image={"image_name": "src.png"}, prompt="p",
            model=mod.EDIT_MODELS[0], width=1536, height=1024)
        node.invoke(_fake_context(saved))
        body = mod.requests.calls[-1]["json"]
        assert body["size"] == "1536x1024"
        assert len(body["image"]) == 1                     # только исходник
        assert mod.REFERENCE_NOTE not in body["prompt"]    # без блока референсов
    finally:
        mod.requests, mod._api = mod_requests, saved_api
    print("OK: devbim_edit — явный размер, без референсов")


def test_generate_node_fail_en():
    mod = nodes()
    fake_ir = _fake_ir()
    saved = []
    resp = SimpleNamespace(status_code=200, json=lambda: {"error": {"message": "quota"}})
    mod_requests, saved_api = mod.requests, mod._api
    mod.requests, mod._api = _Capture([resp]), (lambda: ("KEY", fake_ir))
    try:
        node = mod.GenerateImageInvocation(prompt="x", model=mod.GENERATE_MODELS[0])
        try:
            node.invoke(_fake_context(saved))
            raise AssertionError("должен упасть")
        except ValueError as e:
            assert str(e) == "Generation failed: quota", str(e)
    finally:
        mod.requests, mod._api = mod_requests, saved_api
    print("OK: ошибка апстрима — ValueError EN (тост очереди)")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONUTF8=1 venv/Scripts/python.exe tests/test_cloud_nodes.py`
Expected: FAIL — `AttributeError: module 'devbim_cloud_nodes' has no attribute 'GenerateImageInvocation'`.

- [ ] **Step 3: Write implementation**

Дописать в конец `imagerouter/devbim_cloud_nodes.py`:

```python
# --- инвокации ---

@invocation(
    "devbim_generate",
    title="Generate Image",
    tags=["cloud", "image", "devbim"],
    category="cloud",
    version="1.0.0",
    use_cache=False,
)
class GenerateImageInvocation(BaseInvocation):
    """Generates images from text prompts using a cloud model (batch up to 10)."""

    prompt: str = InputField(
        default="", description="Prompt (type here or connect a String / Ask AI output)"
    )
    prompts: list[str] = InputField(
        default=[], description="Batch prompts (connect Dynamic Prompt or String Collection)"
    )
    model: GenerateModel = InputField(default=GENERATE_MODELS[0], description="Cloud model")
    width: int = InputField(default=1024, ge=64, le=4096, description="Width (snapped to a 64 grid, 128-2048)")
    height: int = InputField(default=1024, ge=64, le=4096, description="Height (snapped to a 64 grid, 128-2048)")
    output_format: OutputFormat = InputField(default="png", description="Output file format")

    def invoke(self, context: InvocationContext) -> ImageCollectionOutput:
        key, ir = _api()
        batch = _prompt_batch(self.prompt, self.prompts)
        w, h = _snap_side(self.width), _snap_side(self.height)
        print(f"[cloud-node] generate: model={self.model} prompts={len(batch)} size={w}x{h}", flush=True)
        fields: list[ImageField] = []
        for p in batch:
            body = {
                "model": self.model,
                "prompt": p,
                "size": f"{w}x{h}",
                "output_format": self.output_format,
            }
            for item in _post_images(ir.GENERATIONS_URL, body, key):
                pil = ir._item_to_pil(item)
                if pil is None:
                    continue
                dto = _save(context, pil, {
                    "generation_mode": "cloud-generate",
                    "cloud_model": self.model,
                    "positive_prompt": p,
                    "width": w,
                    "height": h,
                })
                fields.append(ImageField(image_name=dto.image_name))
        if not fields:
            raise ValueError("Generation failed: the generation service returned no images")
        return ImageCollectionOutput(collection=fields)


@invocation(
    "devbim_edit",
    title="Edit Image",
    tags=["cloud", "image", "editing", "devbim"],
    category="cloud",
    version="1.0.0",
    use_cache=False,
)
class EditImageInvocation(BaseInvocation):
    """Edits an image with optional references using a cloud model (batch up to 10)."""

    image: ImageField = InputField(description="Source image to edit")
    references: list[ImageField] = InputField(default=[], description="Reference images (up to 4)")
    prompt: str = InputField(default="", description="Prompt (type here or connect a String / Ask AI output)")
    prompts: list[str] = InputField(default=[], description="Batch prompts")
    model: EditModel = InputField(default=EDIT_MODELS[0], description="Cloud editing model")
    width: int = InputField(default=0, ge=0, le=4096, description="Output width; 0 = size of the source")
    height: int = InputField(default=0, ge=0, le=4096, description="Output height; 0 = size of the source")
    output_format: OutputFormat = InputField(default="png", description="Output file format")

    def invoke(self, context: InvocationContext) -> ImageCollectionOutput:
        key, ir = _api()
        batch = _prompt_batch(self.prompt, self.prompts)
        src = context.images.get_pil(self.image.image_name)
        refs_pil = [context.images.get_pil(f.image_name)
                    for f in (self.references or [])[:MAX_REFERENCES]]
        if self.width > 0 and self.height > 0:
            w, h = _snap_side(self.width), _snap_side(self.height)
        else:
            w, h = _snap_side(src.width), _snap_side(src.height)
        # JSON-массив image[]: исходник первым (PNG, паттерн п.26),
        # референсы дальше (JPEG 1024/q85, паттерн п.26/47)
        images = [ir._pil_to_durl(src)] + [
            ir._pil_to_durl(r, "JPEG", 1024, JPEG_QUALITY) for r in refs_pil
        ]
        note = REFERENCE_NOTE if refs_pil else ""
        print(
            f"[cloud-node] edit: model={self.model} prompts={len(batch)} "
            f"refs={len(refs_pil)} size={w}x{h}",
            flush=True,
        )
        fields: list[ImageField] = []
        for p in batch:
            body = {
                "model": self.model,
                "prompt": p + note,
                "image": images,
                "size": f"{w}x{h}",
                "output_format": self.output_format,
            }
            for item in _post_images(ir.EDITS_URL, body, key):
                pil = ir._item_to_pil(item)
                if pil is None:
                    continue
                dto = _save(context, pil, {
                    "generation_mode": "cloud-edit",
                    "cloud_model": self.model,
                    "positive_prompt": p,
                    "width": w,
                    "height": h,
                    "source_image": self.image.image_name,
                    "ref_images": [f.image_name for f in (self.references or [])[:MAX_REFERENCES]],
                })
                fields.append(ImageField(image_name=dto.image_name))
        if not fields:
            raise ValueError("Generation failed: the generation service returned no images")
        return ImageCollectionOutput(collection=fields)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONUTF8=1 venv/Scripts/python.exe tests/test_cloud_nodes.py`
Expected: все `OK`, включая 5 новых.

- [ ] **Step 5: Commit**

```bash
git add imagerouter/devbim_cloud_nodes.py tests/test_cloud_nodes.py
git commit -m "feat(workflows): ноды Generate Image и Edit Image — generations/edits JSON, референсы (п.2)"
```

---

### Task 3: Ноды Ask AI и Upscale Image

**Files:**
- Modify: `imagerouter/devbim_cloud_nodes.py` (дописать в конец)
- Test: `tests/test_cloud_nodes.py` (дописать)

**Interfaces:**
- Consumes: Task 1–2; `prepare_image(pil) -> str` из задеплоенного `invokeai.app.invocations.devbim_prompt_enhancer` (JPEG data-URL, даунскейл 1024); роутер `CHAT_COMPLETIONS_URL`, `_enhancer_model()`, `_pick_upscale_size`, `_upscale_prompt`.
- Produces: `devbim_vlm` → `StringOutput(value)` (одиночная строка — подключается к `prompt` нод generate/edit и к строковым нодам); `devbim_upscale` → `ImageOutput(image,width,height)` (одиночная картинка — вход `image` дальше по цепочке, в т.ч. через `iterate`); поля `images`+`question` / `image`+`model`+`mode` для шаблонов.

- [ ] **Step 1: Write the failing test**

Дописать в `tests/test_cloud_nodes.py`:

```python
def test_vlm_node():
    mod = nodes()
    fake_ir = _fake_ir()
    saved = []
    resp = SimpleNamespace(status_code=200, json=lambda: {
        "choices": [{"message": {"content": "  It is a brick school.  "}}]})
    mod_requests, saved_api = mod.requests, mod._api
    mod.requests, mod._api = _Capture([resp]), (lambda: ("KEY", fake_ir))
    try:
        node = mod.AskAIInvocation(
            images=[{"image_name": f"i{k}.png"} for k in range(6)],
            question="what is it?")
        out = node.invoke(_fake_context(saved))
        assert out.value == "It is a brick school."          # только strip, без санитайзинга
        body = mod.requests.calls[-1]["json"]
        assert body["model"] == "zai/glm-5.3-flash"
        assert body["max_tokens"] == 1500
        parts = body["messages"][1]["content"]
        assert parts[0] == {"type": "text", "text": "what is it?"}
        assert len([p for p in parts if p["type"] == "image_url"]) == 4  # кап 4, срезаны молча
    finally:
        mod.requests, mod._api = mod_requests, saved_api
    print("OK: devbim_vlm — chat/completions, кап 4, ответ без санитайзинга")


def test_vlm_node_empty():
    mod = nodes()
    node = mod.AskAIInvocation(images=[], question="  ")
    try:
        node.invoke(_fake_context([]))
        raise AssertionError("должен упасть")
    except ValueError as e:
        assert str(e) == "Attach an image or enter a question", str(e)
    print("OK: devbim_vlm — пустые входы")


def test_vlm_node_default_question():
    mod = nodes()
    fake_ir = _fake_ir()
    resp = SimpleNamespace(status_code=200, json=lambda: {
        "choices": [{"message": {"content": "desc"}}]})
    mod_requests, saved_api = mod.requests, mod._api
    mod.requests, mod._api = _Capture([resp]), (lambda: ("KEY", fake_ir))
    try:
        node = mod.AskAIInvocation(images=[{"image_name": "i.png"}], question="")
        node.invoke(_fake_context([]))
        parts = mod.requests.calls[-1]["json"]["messages"][1]["content"]
        assert parts[0]["text"] == "Describe these images in detail."
    finally:
        mod.requests, mod._api = mod_requests, saved_api
    print("OK: devbim_vlm — дефолтный вопрос без текста")


def test_upscale_node_modes():
    mod = nodes()
    fake_ir = _fake_ir()
    saved = []
    saved_requests, saved_api = mod.requests, mod._api

    def run(mode):
        resp = SimpleNamespace(status_code=200, json=lambda: {"data": [{"ok": True}]})
        cap = _Capture([resp])
        mod.requests = cap
        node = mod.UpscaleImageInvocation(
            image={"image_name": "src.png"}, model=mod.UPSCALE_MODELS[0], mode=mode)
        out = node.invoke(_fake_context(saved))
        return out, cap.calls[-1]["json"]

    mod._api = lambda: ("KEY", fake_ir)
    try:
        out, body = run("2x")                     # исходник 500x333 -> 2x -> 1000x666 -> snap64
        assert body["size"] == "1024x640", body["size"]
        assert "2x higher resolution" in body["prompt"]
        assert body["image"][0].startswith("data:image/png")
        assert body["output_format"] == "png"
        assert out.image.image_name == saved[-1][0].image_name
        assert (out.width, out.height) == (8, 8)

        _, body = run("1536x1024")                # явный размер
        assert body["size"] == "1536x1024"
        assert "1536×1024 resolution" in body["prompt"]

        try:
            run("x3")
            raise AssertionError("должен упасть")
        except ValueError as e:
            assert str(e).startswith("Invalid upscale mode 'x3'"), str(e)
    finally:
        mod.requests, mod._api = saved_requests, saved_api
    print("OK: devbim_upscale — режимы 2x/WxH, серверный промпт, EN-ошибка режима")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONUTF8=1 venv/Scripts/python.exe tests/test_cloud_nodes.py`
Expected: FAIL — `no attribute 'AskAIInvocation'`.

- [ ] **Step 3: Write implementation**

Дописать в конец `imagerouter/devbim_cloud_nodes.py`:

```python
@invocation(
    "devbim_vlm",
    title="Ask AI",
    tags=["cloud", "vlm", "devbim"],
    category="cloud",
    version="1.0.0",
    use_cache=False,
)
class AskAIInvocation(BaseInvocation):
    """Asks a vision-language model about up to 4 images."""

    images: list[ImageField] = InputField(default=[], description="Images to analyze (up to 4)")
    question: str = InputField(default="", description="Question about the images")

    def invoke(self, context: InvocationContext) -> StringOutput:
        key, ir = _api()
        # переиспользуем подготовку картинок Prompt Enhancer (JPEG 1024/q85)
        from invokeai.app.invocations.devbim_prompt_enhancer import prepare_image
        picked = (self.images or [])[:MAX_VLM_IMAGES]
        q = (self.question or "").strip()
        if not q and not picked:
            raise ValueError("Attach an image or enter a question")
        urls = [prepare_image(context.images.get_pil(f.image_name)) for f in picked]
        parts: list[dict] = [{"type": "text", "text": q or "Describe these images in detail."}]
        parts += [{"type": "image_url", "image_url": {"url": u}} for u in urls]
        body = {
            "model": ir._enhancer_model(),
            "messages": [
                {"role": "system", "content": SYSTEM_ASK},
                {"role": "user", "content": parts},
            ],
            "max_tokens": MAX_TOKENS,
            "temperature": TEMPERATURE,
        }
        print(f"[cloud-node] vlm: model={body['model']} images={len(urls)}", flush=True)
        resp = requests.post(
            ir.CHAT_COMPLETIONS_URL,
            headers={"Authorization": f"Bearer {key}"},
            json=body,
            timeout=API_TIMEOUT_S,
        )
        try:
            data = resp.json()
        except ValueError:
            data = None
        err = data.get("error") if isinstance(data, dict) else None
        if resp.status_code >= 400 or (isinstance(err, dict) and err.get("message")):
            msg = err.get("message") if isinstance(err, dict) else (
                err if isinstance(err, str) else None)
            raise ValueError(f"Generation failed: {msg or f'HTTP {resp.status_code}'}")
        choices = data.get("choices") if isinstance(data, dict) else None
        content = ""
        if choices:
            content = ((choices[0].get("message") or {}).get("content")) or ""
        # ответ произвольный — без санитайзинга промта, только пробелы
        text = (content or "").strip()
        if not text:
            raise ValueError("The assistant model returned an empty response. Please try again.")
        return StringOutput(value=text)


_UPSCALE_FACTOR_RE = re.compile(r"^(\d+(?:\.\d+)?)x$", re.IGNORECASE)
_UPSCALE_SIZE_RE = re.compile(r"^(\d{2,4})x(\d{2,4})$", re.IGNORECASE)


def _upscale_request(mid: str, mode: str, src_pil: Any, ir: Any) -> dict:
    """Тело edits-запроса апскейла. Режим «2x»/«4x» — множитель, размер через
    _pick_upscale_size роутера (явные размеры модели, сетка 64, кап 2048);
    «1536x1024» — явный размер (сетка 64, 128..2048). Промпт серверный
    (_upscale_prompt) — у ноды поля промпта нет. Проверка эха не применяется
    (п.27: честный апскейл после нормализации размера почти совпадает со входом)."""
    mode = (mode or "").strip()
    m = _UPSCALE_FACTOR_RE.match(mode)
    scale = None
    size = None
    size_label = None
    if m:
        scale = float(m.group(1))
        size = ir._pick_upscale_size(mid, src_pil.width, src_pil.height, scale)
    else:
        s = _UPSCALE_SIZE_RE.match(mode)
        if not s:
            raise ValueError(
                f"Invalid upscale mode '{mode}'. Use a multiplier like '2x' or '4x', "
                "or an explicit size like '1536x1024'."
            )
        w, h = _snap_side(int(s.group(1))), _snap_side(int(s.group(2)))
        size, size_label = f"{w}x{h}", f"{w}×{h}"
    prompt = ir._upscale_prompt(None if size_label else scale, None, None, size_label)
    body: dict = {
        "model": mid,
        "prompt": prompt,
        "image": [ir._pil_to_durl(src_pil)],
        "output_format": "png",
    }
    if size:
        body["size"] = size
    return body


@invocation(
    "devbim_upscale",
    title="Upscale Image",
    tags=["cloud", "upscale", "devbim"],
    category="cloud",
    version="1.0.0",
    use_cache=False,
)
class UpscaleImageInvocation(BaseInvocation):
    """Upscales an image with a cloud model: '2x', '4x' or an explicit size like '1536x1024'."""

    image: ImageField = InputField(description="Image to upscale")
    model: UpscaleModel = InputField(default=UPSCALE_MODELS[0], description="Cloud upscaling model")
    mode: str = InputField(
        default="2x",
        description="Upscale mode: a multiplier ('2x', '4x') or a size ('1536x1024')",
    )

    def invoke(self, context: InvocationContext) -> ImageOutput:
        key, ir = _api()
        src = context.images.get_pil(self.image.image_name)
        body = _upscale_request(self.model, self.mode, src, ir)
        print(f"[cloud-node] upscale: model={self.model} mode={self.mode}", flush=True)
        item = _post_images(ir.EDITS_URL, body, key)[0]
        pil = ir._item_to_pil(item)
        if pil is None:
            raise ValueError("Generation failed: the generation service returned no images")
        dto = _save(context, pil, {
            "generation_mode": "cloud-upscale",
            "cloud_model": self.model,
            "upscale_mode": self.mode,
            "source_image": self.image.image_name,
        })
        return ImageOutput(
            image=ImageField(image_name=dto.image_name), width=dto.width, height=dto.height
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONUTF8=1 venv/Scripts/python.exe tests/test_cloud_nodes.py`
Expected: все `OK`.

- [ ] **Step 5: Commit**

```bash
git add imagerouter/devbim_cloud_nodes.py tests/test_cloud_nodes.py
git commit -m "feat(workflows): ноды Ask AI (VLM) и Upscale Image (2x/4x/WxH) (п.3)"
```

---

### Task 4: Роутер DEFAULT_MAIN_MODELS + деплой модуля в setup_imagerouter.py

**Files:**
- Modify: `imagerouter/imagerouter_router.py` (после `DEFAULT_UPSCALE_MODELS`, ~строка 207)
- Modify: `setup_imagerouter.py` (константы после `PE_DST` ~строка 90; функции после `deploy_prompt_enhancer()` ~строка 1274; `main()` ~строка 1896)
- Test: `tests/test_cloud_nodes.py` (дописать)

**Interfaces:**
- Consumes: `devbim_cloud_nodes.py` (Task 1–3).
- Produces: `DEFAULT_MAIN_MODELS: list[str]` в роутере (читается `_router_default` нод); `deploy_cloud_nodes() -> bool` в setup; `CN_SRC`, `CN_DST` константы.

- [ ] **Step 1: Write the failing test**

Дописать в `tests/test_cloud_nodes.py`:

```python
def _load_setup():
    spec = importlib.util.spec_from_file_location("setup_imagerouter", ROOT / "setup_imagerouter.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_router_defaults_sync():
    """Фолбэки модуля нод = дефолты задеплоенного роутера (DRY-контроль)."""
    mod = nodes()
    from invokeai.app.api.routers import imagerouter as ir
    assert list(ir.DEFAULT_UPSCALE_MODELS) == mod.DEFAULT_UPSCALE_FALLBACK
    assert list(ir.DEFAULT_MAIN_MODELS) == mod.DEFAULT_MAIN_FALLBACK
    print("OK: дефолты роутера и фолбэки нод синхронны")


def test_deploy_cloud_nodes():
    setup = _load_setup()
    import shutil as _sh
    import tempfile as _tf
    with _tf.TemporaryDirectory() as td:
        dst = Path(td) / "devbim_cloud_nodes.py"
        saved = setup.CN_DST
        setup.CN_DST = dst
        try:
            assert setup.deploy_cloud_nodes() is True    # первый запуск — копия
            assert dst.read_text(encoding="utf-8") == setup.CN_SRC.read_text(encoding="utf-8")
            assert setup.deploy_cloud_nodes() is False   # повтор — идемпотентно
        finally:
            setup.CN_DST = saved
    print("OK: deploy_cloud_nodes идемпотентен")


def test_setup_main_calls_deploy():
    import inspect
    setup = _load_setup()
    src = inspect.getsource(setup.main)
    assert "deploy_cloud_nodes()" in src
    print("OK: main() вызывает deploy_cloud_nodes")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONUTF8=1 venv/Scripts/python.exe tests/test_cloud_nodes.py`
Expected: FAIL — `AttributeError: ... no attribute 'DEFAULT_MAIN_MODELS'` (в test_router_defaults_sync).

- [ ] **Step 3: Implement**

(а) В `imagerouter/imagerouter_router.py` после блока `DEFAULT_UPSCALE_MODELS = [...]` (строки 201–207) добавить:

```python
# Дефолт основных моделей для облачных нод Workflows
# (devbim_cloud_nodes.py): файла выбора админа нет — дропдауны нод получают
# этот список (для Canvas/Upscaling действует СВОЯ логика: нет файла —
# весь каталог). Проверенные генерация+правка модели.
DEFAULT_MAIN_MODELS = [
    "google/nano-banana-2",
    "openai/gpt-image-2",
    "qwen/qwen-image",
]
```

(б) В `setup_imagerouter.py` после строки `PE_DST = …` (строка 90) добавить:

```python
CN_SRC = SRC / "devbim_cloud_nodes.py"
CN_DST = SP / "invokeai" / "app" / "invocations" / "devbim_cloud_nodes.py"
```

(в) После функции `deploy_prompt_enhancer()` (~строка 1274) добавить:

```python
def deploy_cloud_nodes() -> bool:
    """Копирует модуль облачных нод Workflows в пакет invokeai (паттерн
    Prompt Enhancer: пакет подхватывает новые *.py сам)."""
    if not CN_SRC.exists():
        print("ОШИБКА: нет источника", CN_SRC)
        sys.exit(1)
    if CN_DST.exists() and CN_DST.read_text(encoding="utf-8") == CN_SRC.read_text(encoding="utf-8"):
        print("Модуль облачных нод уже развернут, пропуск")
        return False
    CN_DST.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(CN_SRC, CN_DST)
    print("Модуль облачных нод развернут:", CN_DST)
    return True
```

(г) В `main()` (строка 1864): в проверку существования в кортеже первого цикла добавить `CN_SRC` (после `PE_SRC`), и после `deploy_prompt_enhancer()` (строка 1896) добавить строку `deploy_cloud_nodes()`:

```python
    for p in (SRC / "imagerouter_router.py", SRC / "imagerouter.html", SRC / "devbim_admin.js",
              MASK_TOGGLE_SRC, CUT_TOOL_SRC, TEXT_TOOL_SRC, TOPRIGHT_SRC, MODEL_INFO_SRC,
              PE_SRC, CN_SRC, DIST, API_APP.parent):
```
и
```python
    deploy_prompt_enhancer()
    deploy_cloud_nodes()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONUTF8=1 venv/Scripts/python.exe tests/test_cloud_nodes.py`
Expected: FAIL у `test_router_defaults_sync` — задеплоенный в venv роутер ещё СТАРЫЙ (без `DEFAULT_MAIN_MODELS`), пока setup не перезаписал. Это нормально для юнит-теста против исходников, но тест читает venv-копию. Запустить деплой роутера:

Run: `PYTHONUTF8=1 venv/Scripts/python.exe setup_imagerouter.py`
Expected: обычный вывод setup (все патчи идемпотентны), среди строк «Модуль облачных нод развернут: …». Затем повторить тест — все `OK`.

- [ ] **Step 5: Commit**

```bash
git add imagerouter/imagerouter_router.py setup_imagerouter.py tests/test_cloud_nodes.py
git commit -m "feat(workflows): DEFAULT_MAIN_MODELS в роутере + деплой devbim_cloud_nodes (п.4)"
```

---

### Task 5: Белый список нод — patch_nodes_allowlist (index-бандл)

**Files:**
- Modify: `setup_imagerouter.py` (константы + функция + `main()`)
- Test: `tests/test_cloud_nodes.py` (дописать)

**Interfaces:**
- Consumes: якорь `nodesAllowlist:void 0,nodesDenylist:void 0` в index-бандле (ровно 1 вхождение, проверено).
- Produces: `patch_nodes_allowlist(bundle: Path | None = None) -> bool`; allowlist из 24 типов (константа `JS_ALLOWLIST_TYPES` — её же читает тест шаблонов Задачи 6).

- [ ] **Step 1: Write the failing test**

Дописать в `tests/test_cloud_nodes.py`:

```python
def test_allowlist_types():
    setup = _load_setup()
    assert len(setup.JS_ALLOWLIST_TYPES) == 24
    for t in ("devbim_generate", "devbim_edit", "devbim_vlm", "devbim_upscale",
              "claude_expand_prompt", "claude_analyze_image",
              "iterate", "collect", "save_image", "dynamic_prompt"):
        assert t in setup.JS_ALLOWLIST_TYPES, t
    for gone in ("denoise_latents", "compel", "sdxl_model_loader", "l2i", "esrgan"):
        assert gone not in setup.JS_ALLOWLIST_TYPES, gone
    print("OK: белый список — 24 типа, локальной диффузии нет")


def test_allowlist_patch_synthetic():
    setup = _load_setup()
    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / "index-test.js"
        f.write_text('x={nodesAllowlist:void 0,nodesDenylist:void 0,y:1}', encoding="utf-8")
        assert setup.patch_nodes_allowlist(bundle=f) is True
        s = f.read_text(encoding="utf-8")
        assert 'nodesAllowlist:["devbim_generate"' in s
        assert ',"iterate",' in s and ',"save_image"],nodesDenylist:void 0' in s
        assert s.startswith("x={") and s.endswith("y:1}")   # точечная замена
        assert setup.patch_nodes_allowlist(bundle=f) is False  # идемпотентно
    print("OK: allowlist-патч на синтетике, идемпотентность")


def test_allowlist_anchor_in_live_bundle():
    setup = _load_setup()
    found = 0
    for f in (setup.DIST / "assets").glob("index-*.js"):
        s = f.read_text(encoding="utf-8")
        if setup.JS_ALLOW_MARKER in s:
            found += 1          # уже пропатчено (деплой прошёл)
        else:
            found += 1 if s.count(setup.JS_ALLOW_OLD) == 1 else 0
    assert found == 1, f"index-бандл с config-slice: {found}"
    print("OK: якорь/маркер allowlist в живом бандле — ровно один файл")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONUTF8=1 venv/Scripts/python.exe tests/test_cloud_nodes.py`
Expected: FAIL — `AttributeError: … 'JS_ALLOWLIST_TYPES'`.

- [ ] **Step 3: Implement**

В `setup_imagerouter.py`:

(а) В шапку к импортам добавить `json` (если его нет): строка `import re` → 
```python
import json
import re
```

(б) После констант `CN_SRC/CN_DST` добавить:

```python
# --- Белый список нод вкладки Workflows (штатный nodesAllowlist config-slice,
# index-бандл). Механизм allow/denylist — родной для InvokeAI, в OSS ничем не
# наполняется; фильтрация действует на меню Add Node, поиск и cmdk редактора.
# Билдеры графов Generate/Canvas/Upscaling шаблонов не читают — их не трогает.
# iterate/collect в 6.2 ЕСТЬ (зарегистрированы в app/services/shared/graph.py,
# вопреки разведке спеки) — iterate нужен шаблону «Generate and Upscale».
JS_ALLOWLIST_TYPES = [
    "devbim_generate", "devbim_edit", "devbim_vlm", "devbim_upscale",
    "claude_expand_prompt", "claude_analyze_image",
    "string", "string_collection", "dynamic_prompt",
    "string_join", "string_join_three", "string_replace",
    "image", "image_collection", "collect", "iterate",
    "img_crop", "img_resize", "img_scale",
    "integer", "float", "rand_int", "range",
    "save_image",
]
JS_ALLOW_OLD = "nodesAllowlist:void 0,nodesDenylist:void 0"
JS_ALLOW_NEW = (
    "nodesAllowlist:" + json.dumps(JS_ALLOWLIST_TYPES, separators=(",", ":"))
    + ",nodesDenylist:void 0"
)
JS_ALLOW_MARKER = 'nodesAllowlist:["devbim_generate"'
```

(в) Добавить функцию сразу после `deploy_cloud_nodes()` (порядок объявления в модуле не важен, вызовы расставляет `main()`):

```python
def patch_nodes_allowlist(bundle: Path | None = None) -> bool:
    """Белый список нод Workflows в config-slice index-бандла: меню Add Node,
    поиск и cmdk показывают только облачные и вспомогательные ноды. Списки
    моделей внутри нод НЕ зависят от этого патча (это openapi-схема)."""
    if bundle is None:
        targets = []
        for f in DIST.glob("assets/index-*.js"):
            s = f.read_text(encoding="utf-8")
            if JS_ALLOW_OLD in s or JS_ALLOW_MARKER in s:
                targets.append(f)
        if len(targets) != 1:
            print(f"ОШИБКА: index-бандл с config-slice найден {len(targets)} раз (ожидался 1)")
            sys.exit(1)
        bundle = targets[0]
    s = bundle.read_text(encoding="utf-8")
    if JS_ALLOW_MARKER in s:
        print("Белый список нод уже установлен, пропуск")
        return False
    n = s.count(JS_ALLOW_OLD)
    if n != 1:
        print(f"ОШИБКА: якорь nodesAllowlist найден {n} раз — структура изменилась")
        sys.exit(1)
    s = s.replace(JS_ALLOW_OLD, JS_ALLOW_NEW, 1)
    bak = bundle.with_suffix(bundle.suffix + ".imagerouter-bak")
    if not bak.exists():
        shutil.copy2(bundle, bak)
    bundle.write_text(s, encoding="utf-8")
    print(f"Белый список нод Workflows установлен ({len(JS_ALLOWLIST_TYPES)} типов): "
          f"{bundle.name} (бэкап: {bak.name})")
    return True
```

(г) В `main()` после `patch_tab_guard()` и до `patch_index_html()` добавить `patch_nodes_allowlist()`.

- [ ] **Step 4: Run tests**

Run: `PYTHONUTF8=1 venv/Scripts/python.exe tests/test_cloud_nodes.py`
Expected: все `OK` (живой бандл ещё не пропатчен — якорь найден 1 раз).

- [ ] **Step 5: Apply patch to live bundle + node-import check**

Run: `PYTHONUTF8=1 venv/Scripts/python.exe setup_imagerouter.py`
Expected: среди вывода — «Белый список нод Workflows установлен (24 типов)…».

Проверка синтаксиса бандла (рутинная грабля HANDOFF — одна лишняя скобка ломает весь бандл; из корня проекта):

```bash
node -e "const{pathToFileURL}=require('url');const fs=require('fs');const d='venv/Lib/site-packages/invokeai/frontend/web/dist/assets';const f=fs.readdirSync(d).find(n=>/^index-.*\.js$/.test(n));import(pathToFileURL(d+'/'+f).href).catch(e=>console.log(e.message))"
```
Expected: только рантайм-ошибка вида `document is not defined` / `window is not defined`. **SyntaxError / Unexpected token — стоп, откат по `index-*.js.imagerouter-bak` и разбор.**

- [ ] **Step 6: Commit**

```bash
git add setup_imagerouter.py tests/test_cloud_nodes.py
git commit -m "feat(workflows): patch_nodes_allowlist — 24 типа в config-slice index-бандла (п.5)"
```

---

### Task 6: Облачные шаблоны default_workflows + деплой

**Files:**
- Create: `imagerouter/cloud_workflows/default_cloud_text_to_image.json`
- Create: `imagerouter/cloud_workflows/default_cloud_facade_variants.json`
- Create: `imagerouter/cloud_workflows/default_cloud_edit_with_references.json`
- Create: `imagerouter/cloud_workflows/default_cloud_analyze_and_recreate.json`
- Create: `imagerouter/cloud_workflows/default_cloud_generate_and_upscale.json`
- Modify: `setup_imagerouter.py` (константы + `deploy_cloud_workflows()` + `main()`)
- Test: `tests/test_cloud_nodes.py` (дописать)

**Interfaces:**
- Consumes: типы нод и поля из Задач 2–3; `JS_ALLOWLIST_TYPES` из Задачи 5 (тест проверяет, что все ноды шаблонов — из белого списка); версии нод из openapi (см. «Разведка-факты»).
- Produces: `WF_SRC`, `WF_DST` константы; `deploy_cloud_workflows(dst: Path | None = None) -> bool`; 5 валидных шаблонов (id `default_*`, `meta.category="default"`, `meta.version="3.0.0"`).

Общие правила JSON: формат узла — со стоковых файлов: `{"id", "type": "invocation", "position", "data": {id, version, nodePack: "invokeai", label, notes: "", type, inputs, isOpen, isIntermediate: false, useCache}}`; inputs: `{"имя": {"name", "label": "", ["value": …]}}` (без `value` — берётся дефолт схемы; **поле `model` БЕЗ value** — дефолт Literal = первый элемент выбора админа, на момент создания шаблона неизвестен); рёбра: `{"id": "reactflow__edge-<src><handle>-<dst><handle>", "type": "default", "source", "target", "sourceHandle", "targetHandle"}`.

- [ ] **Step 1: Write the failing test**

Дописать в `tests/test_cloud_nodes.py`:

```python
ALLOWED_EXTRA = {"note"}  # Note-нод в v1 нет, но валидатор допускает любые типы

def test_templates_valid():
    setup = _load_setup()
    from invokeai.app.services.workflow_records.workflow_records_common import WorkflowValidator
    files = sorted((ROOT / "imagerouter" / "cloud_workflows").glob("*.json"))
    assert len(files) == 5, files
    allowed = set(setup.JS_ALLOWLIST_TYPES) | ALLOWED_EXTRA
    for f in files:
        wf = WorkflowValidator.validate_json(f.read_bytes())  # формат сервера
        assert wf.id.startswith("default_"), f.name
        assert wf.meta.category.value == "default"
        ids = {n["id"] for n in wf.nodes}
        types = set()
        for n in wf.nodes:
            assert n["id"] == n["data"]["id"], f.name
            types.add(n["data"]["type"])
            assert n["data"]["type"] in allowed, (f.name, n["data"]["type"])
        for e in wf.edges:
            assert e["source"] in ids and e["target"] in ids, (f.name, e["id"])
            # хендл назначения — вход ноды (или item у collect)
            tgt = next(n for n in wf.nodes if n["id"] == e["target"])
            assert e["targetHandle"] in set(tgt["data"]["inputs"]), (f.name, e)
        assert "devbim_" in " ".join(types) or "dynamic_prompt" in types, f.name
    print("OK: 5 шаблонов валидны (WorkflowValidator), ноды из белого списка")


def test_deploy_cloud_workflows():
    setup = _load_setup()
    with tempfile.TemporaryDirectory() as td:
        dst = Path(td) / "default_workflows"
        dst.mkdir()
        stock = dst / "Text to Image - SD1.5.json"
        stock.write_text('{"id": "default_x", "name": "s"}', encoding="utf-8")
        assert setup.deploy_cloud_workflows(dst=dst) is True
        names = {p.name for p in dst.glob("*.json")}
        assert len(names) == 5 and "Text to Image - SD1.5.json" not in names
        assert (dst / "Text to Image - SD1.5.json.orig").exists()   # сток в бэкапе
        assert setup.deploy_cloud_workflows(dst=dst) is False      # идемпотентно
        # «переустановка пакета» вернула стоковый файл — деплой снова убирает
        stock.write_text('{"id": "default_x", "name": "s"}', encoding="utf-8")
        assert setup.deploy_cloud_workflows(dst=dst) is False      # наши не менялись
        assert not stock.exists()
    print("OK: deploy_cloud_workflows — сток в .orig, идемпотентность")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONUTF8=1 venv/Scripts/python.exe tests/test_cloud_nodes.py`
Expected: FAIL — `FileNotFoundError` (нет каталога `cloud_workflows`).

- [ ] **Step 3: Create the 5 template files**

`imagerouter/cloud_workflows/default_cloud_text_to_image.json`:

```json
{
  "id": "default_cloud_text_to_image",
  "name": "Cloud — Text to Image",
  "author": "DevBIM",
  "description": "Generate an image from a text prompt using a cloud model.",
  "version": "1.0.0",
  "contact": "support@devbim.com",
  "tags": "cloud, text to image",
  "notes": "Type a prompt in the Prompt node and press Invoke. The result is saved to the gallery automatically - no Save Image node needed. Batch: connect a Dynamic Prompt node to the Prompts input (up to 10 per run).",
  "exposedFields": [
    {"nodeId": "c1000000-0000-4000-8000-000000000001", "fieldName": "value"}
  ],
  "meta": {"version": "3.0.0", "category": "default"},
  "nodes": [
    {
      "id": "c1000000-0000-4000-8000-000000000001",
      "type": "invocation",
      "position": {"x": 0, "y": 200},
      "data": {
        "id": "c1000000-0000-4000-8000-000000000001",
        "version": "1.0.1",
        "nodePack": "invokeai",
        "label": "Prompt",
        "notes": "",
        "type": "string",
        "inputs": {
          "value": {"name": "value", "label": "", "value": "Modern minimalist house, concrete and glass, warm evening light, photorealistic architectural render"}
        },
        "isOpen": true,
        "isIntermediate": false,
        "useCache": true
      }
    },
    {
      "id": "c1000000-0000-4000-8000-000000000002",
      "type": "invocation",
      "position": {"x": 600, "y": 175},
      "data": {
        "id": "c1000000-0000-4000-8000-000000000002",
        "version": "1.0.0",
        "nodePack": "invokeai",
        "label": "",
        "notes": "",
        "type": "devbim_generate",
        "inputs": {
          "prompt": {"name": "prompt", "label": ""},
          "prompts": {"name": "prompts", "label": ""},
          "model": {"name": "model", "label": ""},
          "width": {"name": "width", "label": "", "value": 1024},
          "height": {"name": "height", "label": "", "value": 1024},
          "output_format": {"name": "output_format", "label": ""}
        },
        "isOpen": true,
        "isIntermediate": false,
        "useCache": false
      }
    }
  ],
  "edges": [
    {
      "id": "reactflow__edge-c1000000-0000-4000-8000-000000000001value-c1000000-0000-4000-8000-000000000002prompt",
      "type": "default",
      "source": "c1000000-0000-4000-8000-000000000001",
      "target": "c1000000-0000-4000-8000-000000000002",
      "sourceHandle": "value",
      "targetHandle": "prompt"
    }
  ]
}
```

`imagerouter/cloud_workflows/default_cloud_facade_variants.json`:

```json
{
  "id": "default_cloud_facade_variants",
  "name": "Cloud — Facade Variants",
  "author": "DevBIM",
  "description": "Explore facade variants with Dynamic Prompt and a cloud model.",
  "version": "1.0.0",
  "contact": "support@devbim.com",
  "tags": "cloud, dynamic prompt, facade",
  "notes": "Dynamic Prompt expands {a|b} alternatives into a batch of prompts (max 10 per run): each variant is generated separately. Edit the prompt text and Max Prompts, then press Invoke. Results are saved to the gallery automatically.",
  "exposedFields": [
    {"nodeId": "c2000000-0000-4000-8000-000000000001", "fieldName": "prompt"},
    {"nodeId": "c2000000-0000-4000-8000-000000000001", "fieldName": "max_prompts"}
  ],
  "meta": {"version": "3.0.0", "category": "default"},
  "nodes": [
    {
      "id": "c2000000-0000-4000-8000-000000000001",
      "type": "invocation",
      "position": {"x": 0, "y": 200},
      "data": {
        "id": "c2000000-0000-4000-8000-000000000001",
        "version": "1.0.1",
        "nodePack": "invokeai",
        "label": "Facade options",
        "notes": "",
        "type": "dynamic_prompt",
        "inputs": {
          "prompt": {"name": "prompt", "label": "", "value": "{modern|classical} apartment facade, {brick|plaster} walls, golden hour, photorealistic architectural render"},
          "max_prompts": {"name": "max_prompts", "label": "", "value": 4},
          "combinatorial": {"name": "combinatorial", "label": "", "value": false}
        },
        "isOpen": true,
        "isIntermediate": false,
        "useCache": true
      }
    },
    {
      "id": "c2000000-0000-4000-8000-000000000002",
      "type": "invocation",
      "position": {"x": 600, "y": 175},
      "data": {
        "id": "c2000000-0000-4000-8000-000000000002",
        "version": "1.0.0",
        "nodePack": "invokeai",
        "label": "",
        "notes": "",
        "type": "devbim_generate",
        "inputs": {
          "prompt": {"name": "prompt", "label": ""},
          "prompts": {"name": "prompts", "label": ""},
          "model": {"name": "model", "label": ""},
          "width": {"name": "width", "label": "", "value": 1024},
          "height": {"name": "height", "label": "", "value": 1024},
          "output_format": {"name": "output_format", "label": ""}
        },
        "isOpen": true,
        "isIntermediate": false,
        "useCache": false
      }
    }
  ],
  "edges": [
    {
      "id": "reactflow__edge-c2000000-0000-4000-8000-000000000001collection-c2000000-0000-4000-8000-000000000002prompts",
      "type": "default",
      "source": "c2000000-0000-4000-8000-000000000001",
      "target": "c2000000-0000-4000-8000-000000000002",
      "sourceHandle": "collection",
      "targetHandle": "prompts"
    }
  ]
}
```

`imagerouter/cloud_workflows/default_cloud_edit_with_references.json`:

```json
{
  "id": "default_cloud_edit_with_references",
  "name": "Cloud — Edit with References",
  "author": "DevBIM",
  "description": "Edit an image following the style and materials of reference images.",
  "version": "1.0.0",
  "contact": "support@devbim.com",
  "tags": "cloud, editing, references",
  "notes": "Pick the source image in the Source node, add up to 4 references to the References collection, edit the prompt, then press Invoke. The first image sent to the model is the source; the rest are references (weight 0.5). Results are saved to the gallery automatically. Width/Height 0 = keep the source size.",
  "exposedFields": [],
  "meta": {"version": "3.0.0", "category": "default"},
  "nodes": [
    {
      "id": "c3000000-0000-4000-8000-000000000001",
      "type": "invocation",
      "position": {"x": 0, "y": 100},
      "data": {
        "id": "c3000000-0000-4000-8000-000000000001",
        "version": "1.0.2",
        "nodePack": "invokeai",
        "label": "Source",
        "notes": "",
        "type": "image",
        "inputs": {
          "image": {"name": "image", "label": ""}
        },
        "isOpen": true,
        "isIntermediate": false,
        "useCache": true
      }
    },
    {
      "id": "c3000000-0000-4000-8000-000000000002",
      "type": "invocation",
      "position": {"x": 0, "y": 350},
      "data": {
        "id": "c3000000-0000-4000-8000-000000000002",
        "version": "1.0.1",
        "nodePack": "invokeai",
        "label": "References",
        "notes": "",
        "type": "image_collection",
        "inputs": {
          "collection": {"name": "collection", "label": ""}
        },
        "isOpen": true,
        "isIntermediate": false,
        "useCache": true
      }
    },
    {
      "id": "c3000000-0000-4000-8000-000000000003",
      "type": "invocation",
      "position": {"x": 600, "y": 200},
      "data": {
        "id": "c3000000-0000-4000-8000-000000000003",
        "version": "1.0.0",
        "nodePack": "invokeai",
        "label": "",
        "notes": "",
        "type": "devbim_edit",
        "inputs": {
          "image": {"name": "image", "label": ""},
          "references": {"name": "references", "label": ""},
          "prompt": {"name": "prompt", "label": "", "value": "Repaint the facade using the materials and style of the reference images"},
          "prompts": {"name": "prompts", "label": ""},
          "model": {"name": "model", "label": ""},
          "width": {"name": "width", "label": "", "value": 0},
          "height": {"name": "height", "label": "", "value": 0},
          "output_format": {"name": "output_format", "label": ""}
        },
        "isOpen": true,
        "isIntermediate": false,
        "useCache": false
      }
    }
  ],
  "edges": [
    {
      "id": "reactflow__edge-c3000000-0000-4000-8000-000000000001image-c3000000-0000-4000-8000-000000000003image",
      "type": "default",
      "source": "c3000000-0000-4000-8000-000000000001",
      "target": "c3000000-0000-4000-8000-000000000003",
      "sourceHandle": "image",
      "targetHandle": "image"
    },
    {
      "id": "reactflow__edge-c3000000-0000-4000-8000-000000000002collection-c3000000-0000-4000-8000-000000000003references",
      "type": "default",
      "source": "c3000000-0000-4000-8000-000000000002",
      "target": "c3000000-0000-4000-8000-000000000003",
      "sourceHandle": "collection",
      "targetHandle": "references"
    }
  ]
}
```

`imagerouter/cloud_workflows/default_cloud_analyze_and_recreate.json`:

```json
{
  "id": "default_cloud_analyze_and_recreate",
  "name": "Cloud — Analyze and Recreate",
  "author": "DevBIM",
  "description": "Ask AI describes a photo as a prompt, then a cloud model recreates it.",
  "version": "1.0.0",
  "contact": "support@devbim.com",
  "tags": "cloud, vlm, analyze",
  "notes": "Add the building photo to the Building photo collection, adjust the question if needed, then press Invoke. Ask AI writes a detailed English prompt from the photo; Generate Image uses it directly. Results are saved to the gallery automatically.",
  "exposedFields": [
    {"nodeId": "c4000000-0000-4000-8000-000000000002", "fieldName": "question"}
  ],
  "meta": {"version": "3.0.0", "category": "default"},
  "nodes": [
    {
      "id": "c4000000-0000-4000-8000-000000000001",
      "type": "invocation",
      "position": {"x": 0, "y": 200},
      "data": {
        "id": "c4000000-0000-4000-8000-000000000001",
        "version": "1.0.1",
        "nodePack": "invokeai",
        "label": "Building photo",
        "notes": "",
        "type": "image_collection",
        "inputs": {
          "collection": {"name": "collection", "label": ""}
        },
        "isOpen": true,
        "isIntermediate": false,
        "useCache": true
      }
    },
    {
      "id": "c4000000-0000-4000-8000-000000000002",
      "type": "invocation",
      "position": {"x": 500, "y": 175},
      "data": {
        "id": "c4000000-0000-4000-8000-000000000002",
        "version": "1.0.0",
        "nodePack": "invokeai",
        "label": "",
        "notes": "",
        "type": "devbim_vlm",
        "inputs": {
          "images": {"name": "images", "label": ""},
          "question": {"name": "question", "label": "", "value": "Describe this building as a detailed prompt for an image generator"}
        },
        "isOpen": true,
        "isIntermediate": false,
        "useCache": false
      }
    },
    {
      "id": "c4000000-0000-4000-8000-000000000003",
      "type": "invocation",
      "position": {"x": 1000, "y": 175},
      "data": {
        "id": "c4000000-0000-4000-8000-000000000003",
        "version": "1.0.0",
        "nodePack": "invokeai",
        "label": "",
        "notes": "",
        "type": "devbim_generate",
        "inputs": {
          "prompt": {"name": "prompt", "label": ""},
          "prompts": {"name": "prompts", "label": ""},
          "model": {"name": "model", "label": ""},
          "width": {"name": "width", "label": "", "value": 1024},
          "height": {"name": "height", "label": "", "value": 1024},
          "output_format": {"name": "output_format", "label": ""}
        },
        "isOpen": true,
        "isIntermediate": false,
        "useCache": false
      }
    }
  ],
  "edges": [
    {
      "id": "reactflow__edge-c4000000-0000-4000-8000-000000000001collection-c4000000-0000-4000-8000-000000000002images",
      "type": "default",
      "source": "c4000000-0000-4000-8000-000000000001",
      "target": "c4000000-0000-4000-8000-000000000002",
      "sourceHandle": "collection",
      "targetHandle": "images"
    },
    {
      "id": "reactflow__edge-c4000000-0000-4000-8000-000000000002value-c4000000-0000-4000-8000-000000000003prompt",
      "type": "default",
      "source": "c4000000-0000-4000-8000-000000000002",
      "target": "c4000000-0000-4000-8000-000000000003",
      "sourceHandle": "value",
      "targetHandle": "prompt"
    }
  ]
}
```

`imagerouter/cloud_workflows/default_cloud_generate_and_upscale.json`:

```json
{
  "id": "default_cloud_generate_and_upscale",
  "name": "Cloud — Generate and Upscale",
  "author": "DevBIM",
  "description": "Generate an image and upscale every result 2x with cloud models.",
  "version": "1.0.0",
  "contact": "support@devbim.com",
  "tags": "cloud, upscale",
  "notes": "Iterate runs Upscale Image once per generated image. Mode accepts a multiplier ('2x', '4x') or an explicit size ('1536x1024'); factual size depends on the upscaling model. Results are saved to the gallery automatically.",
  "exposedFields": [
    {"nodeId": "c5000000-0000-4000-8000-000000000001", "fieldName": "value"}
  ],
  "meta": {"version": "3.0.0", "category": "default"},
  "nodes": [
    {
      "id": "c5000000-0000-4000-8000-000000000001",
      "type": "invocation",
      "position": {"x": 0, "y": 200},
      "data": {
        "id": "c5000000-0000-4000-8000-000000000001",
        "version": "1.0.1",
        "nodePack": "invokeai",
        "label": "Prompt",
        "notes": "",
        "type": "string",
        "inputs": {
          "value": {"name": "value", "label": "", "value": "Elegant brick townhouse, detailed facade, soft daylight, photorealistic architectural render"}
        },
        "isOpen": true,
        "isIntermediate": false,
        "useCache": true
      }
    },
    {
      "id": "c5000000-0000-4000-8000-000000000002",
      "type": "invocation",
      "position": {"x": 450, "y": 175},
      "data": {
        "id": "c5000000-0000-4000-8000-000000000002",
        "version": "1.0.0",
        "nodePack": "invokeai",
        "label": "",
        "notes": "",
        "type": "devbim_generate",
        "inputs": {
          "prompt": {"name": "prompt", "label": ""},
          "prompts": {"name": "prompts", "label": ""},
          "model": {"name": "model", "label": ""},
          "width": {"name": "width", "label": "", "value": 1024},
          "height": {"name": "height", "label": "", "value": 1024},
          "output_format": {"name": "output_format", "label": ""}
        },
        "isOpen": true,
        "isIntermediate": false,
        "useCache": false
      }
    },
    {
      "id": "c5000000-0000-4000-8000-000000000003",
      "type": "invocation",
      "position": {"x": 900, "y": 175},
      "data": {
        "id": "c5000000-0000-4000-8000-000000000003",
        "version": "1.1.0",
        "nodePack": "invokeai",
        "label": "Each result",
        "notes": "",
        "type": "iterate",
        "inputs": {
          "collection": {"name": "collection", "label": ""}
        },
        "isOpen": false,
        "isIntermediate": true,
        "useCache": false
      }
    },
    {
      "id": "c5000000-0000-4000-8000-000000000004",
      "type": "invocation",
      "position": {"x": 1300, "y": 175},
      "data": {
        "id": "c5000000-0000-4000-8000-000000000004",
        "version": "1.0.0",
        "nodePack": "invokeai",
        "label": "",
        "notes": "",
        "type": "devbim_upscale",
        "inputs": {
          "image": {"name": "image", "label": ""},
          "model": {"name": "model", "label": ""},
          "mode": {"name": "mode", "label": "", "value": "2x"}
        },
        "isOpen": true,
        "isIntermediate": false,
        "useCache": false
      }
    }
  ],
  "edges": [
    {
      "id": "reactflow__edge-c5000000-0000-4000-8000-000000000001value-c5000000-0000-4000-8000-000000000002prompt",
      "type": "default",
      "source": "c5000000-0000-4000-8000-000000000001",
      "target": "c5000000-0000-4000-8000-000000000002",
      "sourceHandle": "value",
      "targetHandle": "prompt"
    },
    {
      "id": "reactflow__edge-c5000000-0000-4000-8000-000000000002collection-c5000000-0000-4000-8000-000000000003collection",
      "type": "default",
      "source": "c5000000-0000-4000-8000-000000000002",
      "target": "c5000000-0000-4000-8000-000000000003",
      "sourceHandle": "collection",
      "targetHandle": "collection"
    },
    {
      "id": "reactflow__edge-c5000000-0000-4000-8000-000000000003item-c5000000-0000-4000-8000-000000000004image",
      "type": "default",
      "source": "c5000000-0000-4000-8000-000000000003",
      "target": "c5000000-0000-4000-8000-000000000004",
      "sourceHandle": "item",
      "targetHandle": "image"
    }
  ]
}
```

- [ ] **Step 4: Add deploy function + wiring to setup_imagerouter.py**

После `CN_SRC/CN_DST` добавить:

```python
WF_SRC = SRC / "cloud_workflows"
WF_DST = SP / "invokeai" / "app" / "services" / "workflow_records" / "default_workflows"
```

После `deploy_cloud_nodes()` добавить:

```python
def deploy_cloud_workflows(dst: Path | None = None) -> bool:
    """Заменяет стоковые default_workflows облачными шаблонами (Workflows).
    Стоковые JSON сохраняются как <имя>.json.orig (один раз) и удаляются;
    устаревшие default-воркфлои из БД удаляет серверный _sync_default_workflows
    при старте («Deleting obsolete default workflow»), новые — добавляет/обновляет."""
    dst = dst or WF_DST
    ours = {p.name for p in WF_SRC.glob("*.json")}
    if not ours:
        print("ОШИБКА: нет шаблонов в", WF_SRC)
        sys.exit(1)
    dst.mkdir(parents=True, exist_ok=True)
    for f in sorted(dst.glob("*.json")):
        if f.name in ours:
            continue
        orig = f.with_suffix(f.suffix + ".orig")
        if not orig.exists():
            shutil.copy2(f, orig)
        f.unlink()
        print(f"Стоковый шаблон убран (бэкап {orig.name}):", f.name)
    changed = False
    for src in sorted(WF_SRC.glob("*.json")):
        d = dst / src.name
        if d.exists() and d.read_text(encoding="utf-8") == src.read_text(encoding="utf-8"):
            continue
        shutil.copy2(src, d)
        print("Шаблон развернут:", src.name)
        changed = True
    return changed
```

В `main()`: в проверку существования добавить `WF_SRC`; после `deploy_cloud_nodes()` добавить `deploy_cloud_workflows()`:

```python
              PE_SRC, CN_SRC, WF_SRC, DIST, API_APP.parent):
```
```python
    deploy_prompt_enhancer()
    deploy_cloud_nodes()
    deploy_cloud_workflows()
```

- [ ] **Step 5: Run tests**

Run: `PYTHONUTF8=1 venv/Scripts/python.exe tests/test_cloud_nodes.py`
Expected: все `OK`, включая два новых.

- [ ] **Step 6: Commit**

```bash
git add imagerouter/cloud_workflows setup_imagerouter.py tests/test_cloud_nodes.py
git commit -m "feat(workflows): 5 облачных шаблонов + deploy_cloud_workflows (замена default_workflows)"
```

---

### Task 7: Подсказка в админ-UI + документация

**Files:**
- Modify: `imagerouter/imagerouter.html:156-161` (секция «Генерация и правка») и `imagerouter/imagerouter.html:175-179` (секция «Апскейлинг»)
- Modify: `HANDOFF.md` (новый пункт)
- Modify: `README.md` (раздел Workflows)

**Interfaces:** — (тексты; деплой imagerouter.html — штатный `deploy_files()` setup-скрипта).

- [ ] **Step 1: Add hint lines**

В `imagerouter/imagerouter.html` в подсказку секции `#mainsec` (после «…обновить страницу (F5).») добавить предложение:

```
      Списки моделей в нодах вкладки Workflows обновляются после
      перезапуска сервера.
```
(в тот же `<div class="hint">`, перед `</div>`).

В секции `#upsec` (после «После сохранения — F5 у пользователей.») — то же предложение.

- [ ] **Step 2: README section**

В `README.md` после раздела про апскейлинг (или соседние вкладки) добавить раздел:

```markdown
## Workflows — облачные ноды

Вкладка Workflows работает на облачных нодах: **Generate Image** (промт/батч
до 10 → галерея), **Edit Image** (исходник + до 4 референсов), **Ask AI**
(вопрос по картинкам VLM), **Upscale Image** («2x»/«4x»/«1536x1024»).
Результаты сохраняются в галерею автоматически. Ноды выполняются реальной
очередью: отмена работает между нодами (текущий API-вызов завершается,
результат отбрасывается).

Белый список нод (меню Add Node / поиск / cmdk) — 24 типа: облачные ноды,
Enhance/Analyze, примитивы, iterate/collect, кадрирование/ресайз, числа,
Save Image. Списки моделей в дропдаунах нод = выбор администратора
(«Менеджер моделей»); смена списка требует перезапуска сервера.

Библиотека шаблонов: 5 облачных (Text to Image, Facade Variants,
Edit with References, Analyze and Recreate, Generate and Upscale).
Стоковые локальные шаблоны заменены; ранее сохранённые пользовательские
workflow с локальными нодами открываются с «missing template» (ожидаемо).

Реализация: `imagerouter/devbim_cloud_nodes.py` (деплой
`setup_imagerouter.py`, узлы `devbim_*`), allowlist — `patch_nodes_allowlist`
(index-бандл), шаблоны — `imagerouter/cloud_workflows/` →
`default_workflows/` в пакете. Тесты: `tests/test_cloud_nodes.py`.
Откат: `index-*.js.imagerouter-bak`, `default_workflows/*.orig`, удалить
`invokeai/app/invocations/devbim_cloud_nodes.py`, перезапустить setup и сервер.
```

- [ ] **Step 3: HANDOFF entry**

В `HANDOFF.md` в раздел «Что реализовано» добавить пункт 49 (по образцу соседних: суть, механика, грабли):

```markdown
49. **Workflows: облачные ноды + белый список + облачные шаблоны** (22.09;
    спека/план `docs/superpowers/specs|plans/2026-09-22-workflows-cloud-nodes*`).
    Четыре инвокации в `imagerouter/devbim_cloud_nodes.py` (деплой
    `deploy_cloud_nodes` в setup_imagerouter.py, паттерн п.22):
    `devbim_generate`/`devbim_edit` (батч до 10 промтов, поле prompt
    одиночное + prompts коллекция — одиночный выход ко входу-коллекции в
    6.2 НЕ подключается, NodeInputError), `devbim_vlm` (Ask AI, до 4 картинок,
    модель PROMPT_ENHANCER_MODEL), `devbim_upscale` (режим 2x/4x/WxH,
    хелперы _pick_upscale_size/_upscale_prompt роутера). Выполняются
    РЕАЛЬНОЙ очередью (перехват enqueue_batch их не видит: model — строка),
    результаты сами падают в галерею (context.images.save, GENERAL).
    Дропдауны моделей — Literal с tuple(...) на ИМПОРТЕ модуля из файлов
    выбора админа (data/imagerouter_main_models.json — edit фильтруется по
    входу-image каталога; imagerouter_upscale.json); файла нет —
    DEFAULT_MAIN_MODELS/DEFAULT_UPSCALE_MODELS роутера; смена списка —
    рестарт сервера. Allowlist: `patch_nodes_allowlist` (config-slice
    index-бандла, 24 типа — включая iterate/collect: вопреки разведке спеки
    они в 6.2 ЕСТЬ, graph.py:258/279; iterate обязателен для цепочки
    collection→single). Шаблоны: 5 JSON в `imagerouter/cloud_workflows/`,
    `deploy_cloud_workflows` убирает стоковые (бэкап *.orig), БД дочищает
    _sync_default_workflows на старте. ГРАБЛИ: (а) field label/notes
    воркфлоу вместо Note-нод — формат Note-ноды фронтендовской zod не
    верифицировать локально; (б) якорь nodesAllowlist ровно один в
    index-бандле — проверять node-import; (в) пустой список админа у нод
    даёт дефолты (Literal не бывает пустым); (г) модель-значение в шаблонах
    НЕ задаётся (value опущен) — дефолт Literal = первый элемент списка
    админа, при открытии шаблона подбирается автоматически. Тесты:
    tests/test_cloud_nodes.py; E2E tests/_e2e_cloud_nodes.py.
```

- [ ] **Step 4: Commit**

```bash
git add imagerouter/imagerouter.html README.md HANDOFF.md
git commit -m "docs(workflows): подсказки админ-UI о рестарте + README + HANDOFF п.49 (п.7)"
```

---

### Task 8: Полный деплой, рестарт, живые проверки (E2E + регрессия)

**Files:**
- Create: `tests/_e2e_cloud_nodes.py`
- Deploy: запуск `setup_imagerouter.py` + `_restart_server.ps1`

**Interfaces:**
- Consumes: всё выше; живой сервер 9090; `SITE_PASSWORD` из `.env`; кука `devbim_auth`; дамп `data/_ir_last_graph.json` (регрессия перехвата).
- Produces: подтверждённая работа вкладки; скриншоты `docs/workflows-cloud-*.png`.

- [ ] **Step 1: Full deploy + restart**

```bash
PYTHONUTF8=1 venv/Scripts/python.exe setup_imagerouter.py
powershell -ExecutionPolicy Bypass -File _restart_server.ps1
```
Expected: setup проходит без «ОШИБКА»; сервер поднимается (лог `ir_server.log`, ждать ~40–60 с). В логе при старте — строки синка воркфлоу (debug-уровень может быть скрыт — не обязательно).

- [ ] **Step 2: API smoke (до браузера)**

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:9090/auth/login
```
Expected: 200 (форма) / 303 — сервер жив. Далее Step 3 сам прогоняет API-проверки с логином.

- [ ] **Step 3: Write E2E script**

Создать `tests/_e2e_cloud_nodes.py`:

```python
# -*- coding: utf-8 -*-
"""E2E облачных нод Workflows (22.09): регистрация нод в openapi, allowlist
меню Add Node, открытие шаблона Facade Variants, ЖИВАЯ генерация через
реальную очередь (~$0.01), регрессия перехвата канваса (репост последнего
дампа графа) и чистота консоли.
Запуск (сервер на 9090, после setup + рестарта):
  PYTHONUTF8=1 venv/Scripts/python.exe tests/_e2e_cloud_nodes.py
"""
import json
import re
import sys
import time
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs"
BASE = "http://127.0.0.1:9090"

pw = (re.search(r"^SITE_PASSWORD=(.+)$", (ROOT / ".env").read_text(encoding="utf-8"),
                re.M) or [None, ""])[1].strip().strip('"')
s = requests.Session()
r = s.post(f"{BASE}/auth/login", data={"password": pw}, allow_redirects=False, timeout=15)
assert r.status_code in (302, 303), r.status_code
COOKIE = s.cookies.get("devbim_auth")
assert COOKIE

# --- 1. ноды зарегистрированы: openapi содержит devbim_* ---
oa = s.get(f"{BASE}/openapi.json", timeout=30).json()
schemas = oa.get("components", {}).get("schemas", {})
types = set()
for sch in schemas.values():
    t = (sch.get("properties") or {}).get("type", {})
    c = t.get("const") or (t.get("enum") or [None])[0]
    if c:
        types.add(c)
for t in ("devbim_generate", "devbim_edit", "devbim_vlm", "devbim_upscale"):
    assert t in types, f"нет ноды {t} в openapi — сервер перезапущен без деплоя?"
print("OK: openapi содержит devbim_*")

# --- 2. регрессия инъекции моделей (перехват не сломан allowlist-патчем) ---
models = s.get(f"{BASE}/api/v2/models/", timeout=60).json()
keys = {m.get("key") for m in models.get("models", [])}
assert any(str(k).startswith("imagerouter/") for k in keys), "инъекция моделей исчезла"
print("OK: /api/v2/models содержит imagerouter-модели (регрессия инъекции)")

# --- 3. ЖИВАЯ генерация облачной нодой через РЕАЛЬНУЮ очередь (~$0.01) ---
gen_graph = {
    "batch": {
        "origin": "workflows",
        "destination": "workflows",
        "runs": 1,
        "graph": {
            "id": "e2e-cloud-gen",
            "nodes": {
                "gen": {
                    "id": "gen",
                    "type": "devbim_generate",
                    "prompt": "small test house, simple sketch, white background",
                }
            },
            "edges": {},
        },
    },
    "prepend": False,
}
r = s.post(f"{BASE}/api/v1/queue/default/enqueue_batch", json=gen_graph, timeout=30)
assert r.status_code == 202, (r.status_code, r.text[:300])
item_ids = r.json().get("item_ids") or []
assert item_ids, r.text[:300]
deadline = time.time() + 360
done = False
while time.time() < deadline:
    items = s.get(f"{BASE}/api/v1/queue/default/list?limit=1&offset=0", timeout=15).json().get("items", [])
    if items and items[0].get("status") in ("completed", "failed", "canceled"):
        assert items[0]["status"] == "completed", f"очередь: {items[0]['status']} {items[0].get('error')}"
        done = True
        break
    time.sleep(3)
assert done, "генерация не завершилась за 6 минут"
lst = s.get(f"{BASE}/api/v1/images/?offset=0&limit=1&order=desc", timeout=15).json()
name = lst.get("images", [{}])[0].get("image_name")
assert name, "в галерее нет новой картинки"
meta = s.post(f"{BASE}/api/v1/images/images_by_names", json={"image_names": [name]}, timeout=15).json()
mode = ((meta[0].get("metadata") or {}).get("generation_mode"))
assert mode == "cloud-generate", f"метаданные: {mode!r} (ожидалось cloud-generate)"
print("OK: живая генерация devbim_generate через реальную очередь, результат в галерее")

# --- 4. регрессия перехвата канваса: репост последнего дампа графа (~$0.01-0.07) ---
dump = ROOT / "data" / "_ir_last_graph.json"
if dump.exists():
    batch = json.loads(dump.read_text(encoding="utf-8"))
    if isinstance(batch, dict) and "batch" in batch:
        r = s.post(f"{BASE}/api/v1/queue/default/enqueue_batch", json=batch, timeout=120)
        assert r.status_code == 202, (r.status_code, r.text[:300])
        print("OK: канвас-граф принят перехватом (регрессия посредника)")
    else:
        print("SKIP: дампа-графа нет (структура)")
else:
    print("SKIP: data/_ir_last_graph.json отсутствует — регрессию снять вручную с холста")

# --- 5. браузер: allowlist в меню Add Node + шаблон Facade Variants ---
with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(
        str(ROOT / "tests" / "_pw_e2e_fresh"), channel="chrome", headless=True,
        viewport={"width": 1600, "height": 900})
    ctx.add_cookies([{"name": "devbim_auth", "value": COOKIE, "url": BASE}])
    page = ctx.new_page()
    errors = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.goto(BASE + "/", wait_until="domcontentloaded")
    page.wait_for_selector(".positive-prompt-textarea", timeout=60000)
    time.sleep(2)

    # вкладка Workflows (левая рейка, EN-локаль)
    wf = page.get_by_role("button", name=re.compile("workflows", re.I))
    if not wf.count():
        wf = page.get_by_text("Workflows", exact=False)
    wf.first.click(timeout=15000)
    time.sleep(3)
    page.screenshot(path=str(OUT / "workflows-cloud-tab.png"))

    # меню Add Node: только разрешённые ноды
    add = page.get_by_role("button", name=re.compile("add node", re.I))
    if not add.count():
        add = page.get_by_text("Add Node", exact=False)
    add.first.click(timeout=15000)
    time.sleep(1)
    body = page.locator("body").inner_text()
    assert "Generate Image" in body or "Devbim" in body or "devbim" in body.lower(), \
        "меню Add Node не показывает облачные ноды (см. workflows-cloud-addnode.png)"
    for gone in ("Denoise Latents", "Compel Prompt", "Model Loader"):
        assert gone not in body, f"запрещённая нода в меню: {gone}"
    page.keyboard.press("Escape")
    page.screenshot(path=str(OUT / "workflows-cloud-addnode.png"))
    print("OK: Add Node — облачные ноды есть, локальной диффузии нет")

    # библиотека: открыть шаблон Facade Variants
    lib = page.get_by_text("Facade Variants", exact=False)
    assert lib.count(), "шаблон Facade Variants не найден в библиотеке (см. скриншот вкладки)"
    lib.first.click(timeout=15000)
    time.sleep(3)
    assert page.locator(".react-flow__node").count() >= 2, "узлы шаблона не отрисованы"
    page.screenshot(path=str(OUT / "workflows-cloud-template.png"))
    print("OK: шаблон Facade Variants открылся, узлы на холсте")

    real_errors = [e for e in errors if "favicon" not in e.lower()]
    assert not real_errors, f"ошибки консоли: {real_errors[:3]}"
    ctx.close()

print("E2E OK — все проверки пройдены")
```

ПРИМЕЧАНИЕ К СКРИПТУ (для исполнителя): селекторы вкладки/меню написаны по EN-локали (интерфейс проекта английский, п.48). Если элемент не найден — сделать `page.screenshot()` + `page.locator("body").inner_text()` и уточнить селектор по факту (меню Add Node в редакторе воркфлоу открывается кнопкой «+» на холсте или правым кликом). Если у очереди другой формат ответа `/list` (нет `status` у элемента) — свериться с `GET /api/v1/queue/default/status` (`queue.total === 0` и `completed > 0`) и поправить поллинг; это UI-зонд, а не юнит-тест.

- [ ] **Step 4: Run E2E**

Run: `PYTHONUTF8=1 venv/Scripts/python.exe tests/_e2e_cloud_nodes.py`
Expected: последовательные `OK:` и финальное `E2E OK`. Стоимость: ~$0.01–0.09 (генерация + возможный репост канвас-графа). При падении селекторов — приложить скриншоты из `docs/workflows-cloud-*.png` и поправить (это UI-зонд, не юнит-тест).

- [ ] **Step 5: Ручной чек-лист (кратко, по спеке)**

- F5 в браузере → вкладка Workflows: библиотека содержит 5 шаблонов «Cloud — …», стоковых нет.
- Открыть «Cloud — Generate and Upscale» → Invoke с дефолтным промптом (1 картинка): нода Generate подсвечивается при выполнении, результат ×2 в галерее, консоль чистая.
- Смена модели в дропдауне ноды = список «Менеджера моделей» (первая — дефолт).

- [ ] **Step 6: Commit**

```bash
git add tests/_e2e_cloud_nodes.py
git commit -m "test(workflows): E2E облачных нод — openapi, allowlist, шаблон, живая генерация, регрессия (п.8)"
```

---

## Откат (из спеки)

1. Восстановить `venv/.../dist/assets/index-*.js.imagerouter-bak` → `index-*.js`.
2. В `default_workflows/`: удалить наши 5 JSON, переименовать `*.json.orig` → `*.json`.
3. Удалить `invokeai/app/invocations/devbim_cloud_nodes.py`.
4. `PYTHONUTF8=1 venv/Scripts/python.exe setup_imagerouter.py` (патчи идемпотентны) + `_restart_server.ps1`.
5. F5 в браузере.

## Самопроверка плана (выполнена при составлении)

- **Покрытие спеки:** компонент 1 (модуль нод) → Задачи 1–3 (таблица нод: все поля/выходы совпадают + добавлен `prompt` — см. отклонение 2); компонент 2 (allowlist) → Задача 5 (24 типа вместо ~22 — отклонение 1); компонент 3 (шаблоны) → Задача 6 (5 штук, сидинг подтверждён кодом `workflow_records_sqlite.py:338-406`); «Выполнение и ошибки» → реальные поля/лимиты в Задачах 1–3 + E2E Задачи 8; «Риски/регрессии» → E2E п.2/4 (инъекция + перехват), node-import чек в Задаче 5; «Тесты» → `tests/test_cloud_nodes.py` покрывает все пункты юнит-уровня, E2E — живые; «Откат» — выше.
- **Плейсхолдеры:** отсутствуют (все шаги содержат полный код; E2E-скрипт — рабочий, с пометкой про возможную подстройку UI-селекторов).
- **Консистентность имён:** `_model_choices`/`_read_admin_ids`/`_api`/`_post_images`/`_prompt_batch`/`_snap_side`/`_save`/`_upscale_request` — одинаковы в тестах и реализации; фейк `_upscale_prompt` в тестах воспроизводит подстроки реального промпта роутера, на который настроены assert'ы; `JS_ALLOWLIST_TYPES`/`JS_ALLOW_OLD`/`JS_ALLOW_MARKER` — одинаковы в Задачах 5–6; `CN_SRC/CN_DST/WF_SRC/WF_DST` — в Задачах 4/6 и тестах; `DEFAULT_MAIN_MODELS` (роутер) ↔ `DEFAULT_MAIN_FALLBACK` (модуль) связаны тестом синхронности.
- **Арифметика проверена:** edit 500×333 → snap64 → 512×320; upscale 2x от 500×333 → 1000×666 → snap64 → 1024×640.
