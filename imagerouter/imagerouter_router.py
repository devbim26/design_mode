# -*- coding: utf-8 -*-
"""
Интеграция ImageRouter (https://docs.imagerouter.io/) в DevBIM / InvokeAI.

Часть 1 — прокси-роутер (монтируется под /api):
    GET  /api/v1/imagerouter/status     — установлен ли ключ
    PUT  /api/v1/imagerouter/key        — сохранить и проверить ключ
    DELETE /api/v1/imagerouter/key      — удалить ключ
    GET  /api/v1/imagerouter/credits    — баланс (прокси /v1/credits)
    GET  /api/v1/imagerouter/models     — список моделей (прокси /v3/models)
    POST /api/v1/imagerouter/generate   — генерация (прокси /v1/openai/images/generations)
    POST /api/v1/imagerouter/admin-auth — проверка админского пароля (.env)
    GET  /api/v1/imagerouter/upscale-models — модели апскейлинга, доступные
                                             пользователям (выбор администратора)
    PUT  /api/v1/imagerouter/upscale-models — сохранить выбор
    GET  /api/v1/imagerouter/enhancer-model — модель улучшителя промтов
                                              (Prompt Assistant) + каталог VLM
    PUT  /api/v1/imagerouter/enhancer-model — сохранить выбор модели
    POST /api/v1/imagerouter/enhance-test   — проверка улучшителя в менеджере
                                              (промт + картинка -> улучшенный)
    GET  /api/v1/imagerouter/model-marks   — пометки моделей (звёзды 1–5,
                                             баннеры) и каталог баннеров
    PUT  /api/v1/imagerouter/model-marks   — сохранить пометки

Секреты читаются из .env в корне проекта (см. _load_env_file):
    IMAGEROUTER_API_KEY — ключ ImageRouter; имеет приоритет над ключом,
                          введённым через UI (data/imagerouter.json)
    ADMIN_PASSWORD      — админский пароль: открывает «Менеджер моделей»
                          (шестерёнка «Настройки» в меню)

Часть 2 — ImageRouterCanvasMiddleware: модели ImageRouter в основном интерфейсе:
    GET    /api/v2/models/               — к списку добавляются модели ImageRouter
                                            (появляются в выборе модели на Canvas),
                                            spandrel-фейки выбранных админом моделей
                                            апскейлинга и декоративный Tile ControlNet
                                            (вкладка Upscaling)
    POST   /api/v1/queue/{q}/enqueue_batch — если в графе выбрана модель ImageRouter,
                                            генерация выполняется через API, картинка
                                            сохраняется в галерею, клиенту отправляются
                                            штатные события batch_enqueued /
                                            invocation_complete / queue_item_status_changed;
                                            графы апскейлинга (spandrel-узлы) идут в
                                            /v1/openai/images/edits с серверным промптом
    GET/DELETE /api/v2/models/i/{key}    — чтение/запрет удаления для моделей ImageRouter

Ключ хранится на сервере (<INVOKEAI_ROOT>/imagerouter.json) и в браузер не отдаётся.
Разворачивается в venv скриптом setup_imagerouter.py.
"""
from __future__ import annotations

import asyncio
import base64
import binascii
import hmac
import io
import json
import os
import re
import threading
import time
import traceback
import uuid
from pathlib import Path
from typing import Any, Optional
from urllib.parse import unquote

import requests
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from invokeai.app.services.config.config_default import get_config

imagerouter_router = APIRouter(prefix="/v1/imagerouter", tags=["imagerouter"])

IR_BASE = "https://api.imagerouter.io"
AUTH_TEST_URL = f"{IR_BASE}/v1/auth/test"
CREDITS_URL = f"{IR_BASE}/v1/credits"
MODELS_URL = f"{IR_BASE}/v3/models"
GENERATIONS_URL = f"{IR_BASE}/v1/openai/images/generations"
EDITS_URL = f"{IR_BASE}/v1/openai/images/edits"
CHAT_COMPLETIONS_URL = f"{IR_BASE}/v1/openai/chat/completions"

# VLM для улучшения промтов (Prompt Enhancer); override — .env PROMPT_ENHANCER_MODEL
DEFAULT_ENHANCER_MODEL = "zai/glm-5.3-flash"

# Дописывается к промпту, когда модель не принимает параметр mask и зона
# правки подсвечивается прямо в картинке (см. _draw_mask_marker)
PROMPT_MARKER_NOTE = (
    "\n\nЗона для правки выделена пурпурной полупрозрачной заливкой и рамкой. "
    "Изменяй только эту зону, отметки из финального изображения убери."
)

# --- Типы референсов для архитектурного пайплайна (решение 21.09, спека
# docs/superpowers/specs/2026-09-21-reference-types-design.md) ---
# Тип выбран в селекторе «Тип референса» и хранится в поле method узла
# ip_adapter, вес — в weight того же узла (патч setup_imagerouter.py).
# По каждому референсу в промт дописывается его роль (мини-промт) и вес.
IR_REF_TYPES: dict[str, dict] = {
    "main": {
        "label": "основной референс",
        "weight": 1.0,
        "note": "основная картинка: определи по ней в первую очередь "
        "композицию, ракурс, стиль и содержание",
    },
    "extra": {
        "label": "дополнительный референс",
        "weight": 0.2,
        "note": "дополнительная картинка: уточняй по ней детали, материалы "
        "и освещение, не перебивая остальные изображения",
    },
    "view3d": {
        "label": "3D-ракурс",
        "weight": 2.0,
        "note": "схема сцены кадра: выстави всё строго как на схеме — "
        "ракурс, композицию, расположение и пропорции объектов; "
        "формы и цвета самой схемы не используй, это только схема",
    },
    "environment": {
        "label": "окружение",
        "weight": 0.5,
        "note": "окружение: возьми оттуда деревья, дорожки и благоустройство",
    },
    "people": {
        "label": "люди",
        "weight": 0.5,
        "note": "люди: добавь людей как на этой картинке — позы, одежда, масштаб",
    },
    "atmosphere": {
        "label": "атмосфера",
        "weight": 0.5,
        "note": "атмосфера: передай настроение картинки — освещение, "
        "время суток, погоду, цветовую гамму",
    },
    "interior": {
        "label": "предметы интерьера",
        "weight": 0.5,
        "note": "предметы интерьера: возьми мебель и предметы "
        "(стол, стул и т.п.) как на картинке",
    },
    "facade": {
        "label": "детали фасада",
        "weight": 0.5,
        "note": "детали фасада: оформление балконов, козырьков и фасадов "
        "целиком — как на этой картинке",
    },
    "masterplan": {
        "label": "генплан",
        "weight": 0.5,
        "note": "генплан: возьми только расположение зданий как на схеме",
    },
}

# Тип не задан или неизвестен (старые сессии с method full/style/…,
# референс добавлен Generate-фолбэком) — универсальная формулировка
IR_REF_FALLBACK = {
    "label": "референс (общий)",
    "note": "учитывай стиль и содержание этой картинки",
}


def _ref_weight(meta: dict) -> Optional[float]:
    """Вес референса: из узла ip_adapter; отсутствует/кривой — дефолт типа."""
    t = IR_REF_TYPES.get(meta.get("type"))
    w = meta.get("weight")
    if isinstance(w, (int, float)) and not isinstance(w, bool) and 0 <= float(w) <= 2:
        return round(float(w), 2)
    return t["weight"] if t else None


def _reference_prompt_block(ref_meta: list, has_init: bool) -> str:
    """Блок референсов, дописываемый к промту: роль и вес каждой картинки
    по её типу. Нумерация соответствует массиву image[] edits-запроса
    (исходник — изображение 1, референсы — дальше).

    Фикс 24.09 (жалоба «генерация не видит фото из канваса — результат
    похож на референс»): картинка с канваса в запросе ЕСТЬ, но короткая
    строка «исходник для редактирования» не удерживала модель — она
    перерисовывала сцену с референса (живой бокс: clay-рендер 3D + фото
    интерьера, gpt-image-2.5-flare). С исходником блок приказывает сохранить
    геометрию/ракурс изображения 1 и заканчивается гвардом «референсы не
    копировать целиком». Проба: data/probe/_probe_canvas_ref_edit.py."""
    lines: list[str] = []
    if has_init:
        lines.append(
            "Первое изображение — исходник для редактирования: сохрани его "
            "геометрию, ракурс, пропорции, расположение стен, проёмов и "
            "объектов СТРОГО без изменений — это основа сцены."
        )
        # живой прогон 24.09 (джапанди-рендер, docs/3d-ai-palette-japandi-v2.png):
        # без прямого приказа редактирующие модели клеят стекло на сплошную
        # стену — «наклейка» вместо проёма. Формулировка условная («если
        # есть») — безопасна для кадров без окон
        lines.append(
            "ВАЖНО, ОКНА: если в исходнике есть оконные проёмы — рисуй их "
            "сквозными: стекло стоит ВНУТРИ проёма с рамой, за ним видно "
            "соседнее помещение с обстановкой; не рисуй сплошную стену под "
            "стеклом и не клей стекло на плоскость стены."
        )
    first = 2 if has_init else 1
    for k, meta in enumerate(ref_meta):
        t = IR_REF_TYPES.get(meta.get("type")) or IR_REF_FALLBACK
        w = _ref_weight(meta)
        wt = f" (вес {w:g})" if w is not None else ""
        lines.append(f"Изображение {first + k} — {t['label']}{wt}: {t['note']}.")
    if has_init and ref_meta:
        lines.append(
            "Референсы не копируй целиком и не меняй ракурс сцены: "
            "композиция и геометрия — строго с первого изображения. "
            "Ничего не добавляй, не убирай и не перемещай."
        )
    return "\n\n" + "\n".join(lines)

TIMEOUT_SHORT = 30
TIMEOUT_GENERATE = 300

# Префикс ключей моделей ImageRouter в интерфейсе InvokeAI
IR_KEY_PREFIX = "imagerouter/"
# Отдельный префикс для моделей апскейлинга (вкладка Upscaling): одна и та же
# облачная модель может быть выбрана и главной (type=main), и моделью апскейла
# (type=spandrel_image_to_image), а GET /api/v2/models/i/{key} отдаёт один
# конфиг на ключ — ролям нужны разные ключи.
IR_UPSCALE_KEY_PREFIX = "imagerouter-upscale/"
# Модели представляются как main/diffusers/base=sdxl — единственная база, для которой
# фронтенд строит граф без обязательных субмоделей (T5/CLIP и т.п.); сам граф
# сервером не исполняется, а перехватывается мидлварью.
FAKE_BASE = "sdxl"
IR_MODELS_CACHE_TTL = 600.0
MAX_RUNS = 10

# --- Апскейлинг: выбор администратора (какие облачные модели видят пользователи) ---

# Файл выбора: <INVOKEAI_ROOT>/data/imagerouter_upscale.json (per-company, как
# imagerouter.json). Первый элемент списка — модель по умолчанию (клиент
# авто-выбирает первый spandrel-конфиг из /api/v2/models/). Файла нет —
# наследуется выбор «Генерация и правка» (модели апскейлинга = модели
# менеджера, решение 09.09); нет и его — дефолт ниже.
DEFAULT_UPSCALE_MODELS = [
    "philz1337x/clarity-2x",
    "jingyunliang/swinir-2x",
    "stabilityai/latent-2x",
    "prunaai/P-Image-Upscale",
    "csslc/ccsr-2x",
]

# Дефолт основных моделей для облачных нод Workflows
# (devbim_cloud_nodes.py): файла выбора админа нет — дропдауны нод получают
# этот список (для Canvas/Upscaling действует СВОЯ логика: нет файла —
# весь каталог). Проверенные генерация+правка модели.
DEFAULT_MAIN_MODELS = [
    "google/nano-banana-2",
    "openai/gpt-image-2",
    "qwen/qwen-image",
]


def _upscale_store_path() -> Path:
    return Path(get_config().root_path) / "data" / "imagerouter_upscale.json"


def _upscale_selection_source() -> tuple[list[str], str]:
    """(список id, источник) для моделей апскейлинга. Источники:
    «file» — сохранённый выбор администратора (пустой список = отключить
    апскейл); «main» — файла нет, наследуем выбор «Генерация и правка»
    (в апскейлинге те же модели, что пользователь видит в менеджере,
    решение 09.09); «default» — нет обоих файлов, дефолт из кода."""
    p = _upscale_store_path()
    try:
        ids = json.loads(p.read_text(encoding="utf-8")).get("models")
    except Exception:
        ids = None
    src = "file"
    if not isinstance(ids, list):
        main_ids = _load_main_selection()
        if main_ids is not None:
            ids, src = main_ids, "main"
        else:
            ids, src = list(DEFAULT_UPSCALE_MODELS), "default"
    out: list[str] = []
    for mid in ids:
        if isinstance(mid, str) and mid and mid not in out:
            out.append(mid)
    return out, src


def _load_upscale_selection() -> list[str]:
    return _upscale_selection_source()[0]


def _save_upscale_selection(models: list[str]) -> None:
    p = _upscale_store_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"models": models}, ensure_ascii=False, indent=1), encoding="utf-8")


# --- Основные модели (генерация/правка на холсте): выбор администратора ---
#
# Файл <INVOKEAI_ROOT>/data/imagerouter_main_models.json (per-company).
# Пока файла нет — доступны ВСЕ модели каталога (обратная совместимость);
# после первого сохранения — только выбранные, в порядке выбора (первая
# модель — по умолчанию у «свежих» пользователей, клиент авто-выбирает
# первый main-конфиг из /api/v2/models/).


def _main_store_path() -> Path:
    return Path(get_config().root_path) / "data" / "imagerouter_main_models.json"


def _load_main_selection() -> Optional[list[str]]:
    """None = файла нет (показываем всё); иначе — список id без дублей."""
    p = _main_store_path()
    try:
        ids = json.loads(p.read_text(encoding="utf-8")).get("models")
    except Exception:
        ids = None
    if not isinstance(ids, list):
        return None
    out: list[str] = []
    for mid in ids:
        if isinstance(mid, str) and mid and mid not in out:
            out.append(mid)
    return out


def _save_main_selection(models: list[str]) -> None:
    p = _main_store_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"models": models}, ensure_ascii=False, indent=1), encoding="utf-8")


def _selected_main_models() -> list[dict]:
    """Модели каталога для инъекции как main: выбор администратора в его
    порядке; без файла — весь каталог (в его порядке)."""
    all_models = _fetch_ir_models()
    sel = _load_main_selection()
    if sel is None:
        return all_models
    by_id = {m.get("id"): m for m in all_models}
    return [by_id[mid] for mid in sel if mid in by_id]


# --- Пометки моделей (звёзды 1–5 + мини-баннеры): настройки владельца ---
#
# Файл <INVOKEAI_ROOT>/data/imagerouter_model_marks.json (per-company):
#   {"badges": {ключ: {"label", "color", "title"}},
#    "marks": {model_id: {"stars": 0..5, "badges": [ключи]}}}
# Файла нет → действуют встроенные дефолты; файл есть → ТОЛЬКО он
# (первое сохранение в менеджере фиксирует снапшот, дальше владелец
# меняет сам). Звёзды — сила модели именно в ПРАВКЕ картинок; строка
# инъектируется полем usage_info (★-серия + метки баннеров) и рендерится
# пикером модели без патчей бандла; devbim-model-info.js раскрашивает.

_DEFAULT_BADGES: dict[str, dict] = {
    "edit": {"label": "EDIT", "color": "#2f855a", "title": "правка фото по описанию"},
    "bg": {"label": "BG CUT", "color": "#2b6cb0", "title": "вырезание фона"},
    "erase": {"label": "ERASE", "color": "#805ad5", "title": "удаление объектов"},
    "fast": {"label": "FAST", "color": "#c05621", "title": "быстрая генерация"},
}

# Дефолты 08.10: текущий выбор владельца + популярные редакторы каталога.
_DEFAULT_MARKS: dict[str, dict] = {
    "google/nano-banana-pro": {"stars": 5, "badges": ["edit"]},
    "google/nano-banana-2": {"stars": 4, "badges": ["edit"]},
    "google/nano-banana": {"stars": 3, "badges": ["edit"]},
    "google/nano-banana-2-lite": {"stars": 2, "badges": ["edit", "fast"]},
    "openai/gpt-image-2.5-sunburst": {"stars": 5, "badges": ["edit"]},
    "openai/gpt-image-2.5-flare": {"stars": 4, "badges": ["edit"]},
    "openai/gpt-image-1.5": {"stars": 4, "badges": ["edit"]},
    "openai/gpt-image-1": {"stars": 3, "badges": ["edit"]},
    "qwen/qwen-image-2512": {"stars": 4, "badges": ["edit"]},
    "bytedance/seedream-5.0-pro": {"stars": 4, "badges": ["edit"]},
    "bytedance/seedream-4.5": {"stars": 3, "badges": ["edit"]},
    "bytedance/seedream-4": {"stars": 3, "badges": ["edit"]},
    "microsoft/mai-image-2.5": {"stars": 4, "badges": ["edit"]},
    "xAI/grok-imagine-image-2": {"stars": 3, "badges": ["edit"]},
    "midjourney/midjourney": {"stars": 2, "badges": ["edit"]},
    "bria/remove-background": {"stars": 0, "badges": ["bg"]},
    "bria/erase-foreground": {"stars": 0, "badges": ["erase"]},
    "bria/blur-background": {"stars": 0, "badges": ["bg"]},
    "bria/enhance": {"stars": 3, "badges": ["edit"]},
    "black-forest-labs/flux-kontext-max": {"stars": 4, "badges": ["edit"]},
    "black-forest-labs/flux-kontext-pro": {"stars": 4, "badges": ["edit"]},
    "black-forest-labs/flux-kontext-dev": {"stars": 3, "badges": ["edit"]},
    "black-forest-labs/FLUX-1-schnell": {"stars": 1, "badges": ["fast"]},
    "fal/flux-2-dev-turbo": {"stars": 2, "badges": ["fast", "edit"]},
    "google/imagen-4-ultra": {"stars": 2, "badges": ["edit"]},
}


def _marks_store_path() -> Path:
    return Path(get_config().root_path) / "data" / "imagerouter_model_marks.json"


def _sanitize_badges_catalog(raw: Any) -> dict[str, dict]:
    """Каталог баннеров: ключ [a-z0-9_-]{1,24} → {label ≤24, #rrggbb, title}."""
    out: dict[str, dict] = {}
    if not isinstance(raw, dict):
        return out
    for key, val in raw.items():
        if not isinstance(key, str) or not re.fullmatch(r"[a-z0-9_-]{1,24}", key):
            continue
        if not isinstance(val, dict):
            continue
        label = str(val.get("label") or "").strip()
        if not label or len(label) > 24:
            continue
        color = str(val.get("color") or "").strip()
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
            color = "#4a5568"
        out[key] = {"label": label, "color": color, "title": str(val.get("title") or "").strip()}
    return out


def _sanitize_marks(raw: Any, badges: dict[str, dict]) -> dict[str, dict]:
    """Пометки: {model_id: {stars 0..5, badges только из каталога}};
    пустые записи (0 звёзд и без баннеров) отбрасываются."""
    out: dict[str, dict] = {}
    if not isinstance(raw, dict):
        return out
    for mid, val in raw.items():
        if not isinstance(mid, str) or not mid or len(mid) > 200:
            continue
        if not isinstance(val, dict):
            continue
        try:
            stars = int(val.get("stars") or 0)
        except (TypeError, ValueError):
            stars = 0
        stars = max(0, min(5, stars))
        kept: list[str] = []
        bl = val.get("badges")
        if isinstance(bl, list):
            for b in bl:
                if isinstance(b, str) and b in badges and b not in kept:
                    kept.append(b)
        if stars == 0 and not kept:
            continue
        out[mid] = {"stars": stars, "badges": kept}
    return out


def _load_marks() -> Optional[dict]:
    """None = файла нет (действуют дефолты); иначе — разобранный файл."""
    p = _marks_store_path()
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None
    badges = _sanitize_badges_catalog(raw.get("badges"))
    if not badges:
        badges = dict(_DEFAULT_BADGES)
    return {"badges": badges, "marks": _sanitize_marks(raw.get("marks"), badges)}


def _save_marks(badges: dict, marks: dict) -> None:
    p = _marks_store_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"badges": badges, "marks": marks}, ensure_ascii=False, indent=1), encoding="utf-8")


_marks_cache: dict[str, Any] = {"key": None, "data": None}


def _effective_marks() -> dict:
    """Действующие пометки: файл (если есть) или дефолты. Кэш по mtime —
    _ir_fake_config зовёт это на каждую модель каталога."""
    p = _marks_store_path()
    try:
        key: Any = (str(p), p.stat().st_mtime)
    except OSError:
        key = (str(p), None)
    if _marks_cache["key"] != key:
        loaded = _load_marks()
        _marks_cache["key"] = key
        _marks_cache["data"] = (
            {"badges": dict(_DEFAULT_BADGES), "marks": {k: dict(v) for k, v in _DEFAULT_MARKS.items()}}
            if loaded is None
            else loaded
        )
    return _marks_cache["data"]


def _marks_usage_info(m: dict) -> str:
    """Строка пометок модели для списка генерации: «★★★★☆ · EDIT · BG CUT»
    (usage_info в конфиге; пустая строка = без пометок)."""
    data = _effective_marks()
    mark = data["marks"].get(m.get("id") or "")
    if not mark:
        return ""
    parts: list[str] = []
    if mark["stars"] > 0:
        parts.append("★" * mark["stars"] + "☆" * (5 - mark["stars"]))
    parts += [data["badges"][b]["label"] for b in mark["badges"] if b in data["badges"]]
    return " · ".join(parts)


# --- Хранение ключа: .env (IMAGEROUTER_API_KEY) > data/imagerouter.json ---

def _load_env_file() -> None:
    """Читает .env проекта (KEY=VALUE) в os.environ, не переопределяя уже
    заданные переменные. Ищется в cwd (оба .bat запускаются из корня проекта),
    в INVOKEAI_ROOT и на уровень выше него."""
    candidates: list[Path] = []
    try:
        candidates.append(Path.cwd() / ".env")
    except Exception:  # noqa: BLE001
        pass
    try:
        root = Path(get_config().root_path)
        candidates += [root / ".env", root.parent / ".env"]
    except Exception:  # noqa: BLE001
        pass
    for p in candidates:
        try:
            if not p.is_file():
                continue
            for line in p.read_text(encoding="utf-8-sig").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                k, v = k.strip(), v.strip().strip('"').strip("'")
                if k and k not in os.environ:
                    os.environ[k] = v
            break
        except Exception:  # noqa: BLE001
            traceback.print_exc()


_ENV_LOADED = {"done": False}


def _ensure_env() -> None:
    if not _ENV_LOADED["done"]:
        _load_env_file()
        _ENV_LOADED["done"] = True


def _key_path() -> Path:
    return Path(get_config().root_path) / "imagerouter.json"


def _env_key() -> Optional[str]:
    _ensure_env()
    return (os.environ.get("IMAGEROUTER_API_KEY") or "").strip() or None


def _load_key() -> Optional[str]:
    # общий ключ, заданный в админ-панели (settings studio.sqlite) — приоритет
    # над .env: после переезда владельцу хватает браузера, чтобы сменить ключ
    try:
        key = (_studio_store().get_setting("imagerouter_api_key") or "").strip()
        if key:
            return key
    except Exception:  # noqa: BLE001 — БД недоступна: прежняя цепочка
        pass
    key = _env_key()
    if key:
        return key
    p = _key_path()
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8")).get("api_key") or None
    except Exception:
        return None


def _enhancer_model() -> str:
    return _load_enhancer_choice()[0]


# --- Модель улучшителя промтов: выбор администратора в менеджере моделей ---
# Цепочка (как THREED_MODEL): data/imagerouter_prompt_model.json ->
# .env PROMPT_ENHANCER_MODEL -> дефолт. Читается при КАЖДОМ вызове — смена
# модели в менеджере действует без перезапуска и без F5.

def _prompt_model_store_path() -> Path:
    return Path(get_config().root_path) / "data" / "imagerouter_prompt_model.json"


def _load_enhancer_choice() -> "tuple[str, str]":
    """(model, source): file — сохранённый выбор менеджера, env —
    PROMPT_ENHANCER_MODEL, default — DEFAULT_ENHANCER_MODEL."""
    try:
        m = json.loads(
            _prompt_model_store_path().read_text(encoding="utf-8")).get("model")
        if isinstance(m, str) and m.strip():
            return m.strip(), "file"
    except Exception:
        pass
    _ensure_env()
    env = (os.environ.get("PROMPT_ENHANCER_MODEL") or "").strip()
    if env:
        return env, "env"
    return DEFAULT_ENHANCER_MODEL, "default"


def _save_enhancer_choice(model: str) -> None:
    p = _prompt_model_store_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"model": model}, ensure_ascii=False, indent=1), encoding="utf-8")


# Каталог VLM (вход image, выход text) — СВОЙ запрос к /v3/models с
# модальными фильтрами: основной GET /models фильтрует output=image
# (генерация) и VLM не отдаёт (та же грабля, что у threed).
# /v3/models отвечает ГОЛЫМ списком; {"data":[…]} принимаем как запасной
# вариант. Кэш 10 минут.

VLM_CATALOG_TTL_S = 600
_vlm_catalog_cache: dict[str, Any] = {"ts": 0.0, "ids": []}


def _fetch_vlm_ids(force: bool = False) -> list[str]:
    now = time.time()
    if not force and _vlm_catalog_cache["ids"] and now - _vlm_catalog_cache["ts"] < VLM_CATALOG_TTL_S:
        return _vlm_catalog_cache["ids"]
    ids: list[str] = []
    try:
        resp = requests.get(
            MODELS_URL,
            params={"input_modalities": "image", "output_modalities": "text",
                    "limit": 500},
            timeout=TIMEOUT_SHORT,
        )
        data = resp.json() if resp.status_code == 200 else []
        items = data.get("data", []) if isinstance(data, dict) else \
            (data if isinstance(data, list) else [])
        for m in items:
            arch = m.get("architecture") or {}
            if "image" in (arch.get("input_modalities") or []) and \
                    "text" in (arch.get("output_modalities") or []):
                mid = m.get("id")
                if isinstance(mid, str) and mid:
                    ids.append(mid)
    except Exception:
        traceback.print_exc()
    if ids:
        _vlm_catalog_cache.update(ts=now, ids=ids)
    return _vlm_catalog_cache["ids"]


def _auth_headers(studio_user: "str | None" = None) -> dict[str, str]:
    key = effective_key(studio_user)
    if not key:
        if studio_user and studio_user != "admin-local":
            raise HTTPException(
                status_code=401,
                detail="Персональный токен ImageRouter не задан — обратитесь к администратору.")
        raise HTTPException(status_code=401, detail="API key is not configured")
    return {"Authorization": f"Bearer {key}"}


def _upstream_json(resp: requests.Response) -> Any:
    """Ответ апстрима -> dict; ошибки -> HTTPException с сообщением ImageRouter."""
    try:
        data = resp.json()
    except ValueError:
        data = None
    if resp.status_code >= 400:
        msg = None
        if isinstance(data, dict):
            err = data.get("error")
            if isinstance(err, dict):
                msg = err.get("message")
            elif isinstance(err, str):
                msg = err
            msg = msg or data.get("detail")
        raise HTTPException(status_code=resp.status_code, detail=msg or f"Generation service: HTTP {resp.status_code}")
    return data


def _api_error_message(data_out: Any) -> Optional[str]:
    """ImageRouter возвращает ошибки и с HTTP 200: {"error": {"message": ...}}."""
    err = data_out.get("error") if isinstance(data_out, dict) else None
    if isinstance(err, dict) and err.get("message"):
        return str(err["message"])
    return None


class KeyBody(BaseModel):
    api_key: str = Field(min_length=8)


class GenerateBody(BaseModel):
    model: str = Field(min_length=1)
    prompt: str = Field(min_length=1, max_length=20000)
    size: Optional[str] = None
    quality: Optional[str] = None
    output_format: Optional[str] = Field(default=None, pattern="^(webp|jpeg|png)$")


@imagerouter_router.get("/status")
def get_status(request: Request = None) -> dict:
    u = request.headers.get("x-studio-user") if request else None
    user_tok = _personal_token(u)
    key = user_tok or _load_key()
    return {
        "has_key": key is not None,
        "hint": f"...{key[-4:]}" if key else None,
        "key_source": "user" if user_tok else ("env" if _env_key() else ("file" if key else None)),
        "prompt_enhancer_model": _enhancer_model(),
    }


@imagerouter_router.put("/key")
def put_key(body: KeyBody) -> dict:
    # сначала проверяем ключ на стороне ImageRouter, потом сохраняем
    resp = requests.post(AUTH_TEST_URL, headers={"Authorization": f"Bearer {body.api_key.strip()}"}, timeout=TIMEOUT_SHORT)
    if resp.status_code != 200:
        _upstream_json(resp)  # -> HTTPException с сообщением
    _key_path().write_text(json.dumps({"api_key": body.api_key.strip()}), encoding="utf-8")
    return {"status": "valid"}


@imagerouter_router.delete("/key")
def delete_key() -> dict:
    p = _key_path()
    if p.exists():
        p.unlink()
    return {"status": "deleted"}


# --- Админский пароль (.env: ADMIN_PASSWORD) ---
# Открывает закрытые по умолчанию разделы UI: «Менеджер моделей» под
# шестерёнкой «Настройки» (окно пароля — devbim-admin.js во фронтенде).

class AdminAuthBody(BaseModel):
    password: str = Field(min_length=1, max_length=256)


def _admin_password() -> Optional[str]:
    _ensure_env()
    return (os.environ.get("ADMIN_PASSWORD") or "").strip() or None


@imagerouter_router.post("/admin-auth")
def admin_auth(body: AdminAuthBody) -> dict:
    pw = _admin_password()
    if pw is None:
        # пароль не настроен — защита отключена, UI не запрашивает пароль
        return {"ok": True, "protected": False}
    if hmac.compare_digest(body.password.encode("utf-8"), pw.encode("utf-8")):
        return {"ok": True, "protected": True}
    time.sleep(0.3)  # замедлить перебор
    raise HTTPException(status_code=401, detail="Wrong password")


@imagerouter_router.get("/admin-auth")
def admin_auth_status() -> dict:
    return {"protected": _admin_password() is not None}


@imagerouter_router.get("/credits")
def get_credits(request: Request = None) -> Any:
    u = request.headers.get("x-studio-user") if request else None
    resp = requests.get(CREDITS_URL, headers=_auth_headers(u), timeout=TIMEOUT_SHORT)
    return _upstream_json(resp)


@imagerouter_router.get("/models")
def list_models(
    search: Optional[str] = None,
    free: Optional[bool] = None,
    sort: str = "name",
    limit: int = 500,
) -> Any:
    params: dict[str, Any] = {"output_modalities": "image", "sort": sort, "limit": max(1, min(limit, 1000))}
    if search:
        params["name"] = search
    if free is not None:
        params["free"] = "true" if free else "false"
    headers = {"Authorization": f"Bearer {_load_key()}"} if _load_key() else {}
    resp = requests.get(MODELS_URL, params=params, headers=headers, timeout=TIMEOUT_SHORT)
    return _upstream_json(resp)


@imagerouter_router.post("/generate")
def generate(body: GenerateBody, request: Request = None) -> Any:
    payload: dict[str, Any] = {"model": body.model, "prompt": body.prompt}
    if body.size:
        payload["size"] = body.size
    if body.quality:
        payload["quality"] = body.quality
    if body.output_format:
        payload["output_format"] = body.output_format
    u = request.headers.get("x-studio-user") if request else None
    resp = requests.post(GENERATIONS_URL, headers=_auth_headers(u), json=payload, timeout=TIMEOUT_GENERATE)
    return _upstream_json(resp)


# --- Апскейлинг: модели, доступные пользователям (выбор администратора) ---


class UpscaleModelsBody(BaseModel):
    models: list[str] = Field(default_factory=list, max_length=100)


@imagerouter_router.get("/upscale-models")
def get_upscale_models() -> dict:
    """Текущий выбор + справочные данные из каталога (цена, вход-image).
    selection_source: file — сохранённый выбор; main — унаследован из
    «Генерация и правка» (файл выбора не создавался); default — дефолт
    из кода (нет обоих файлов)."""
    ids, src = _upscale_selection_source()
    items: list[dict] = []
    for mid in ids:
        m = _ir_model_by_id(mid)
        items.append(
            {
                "id": mid,
                "available": m is not None,
                "price": _avg_price(m) if m else None,
                "image_input": _supports_image_input(mid) if m else None,
            }
        )
    return {
        "models": items,
        "selection_source": src,
        "defaults_used": src == "default",
        "inherited_from_main": src == "main",
    }


@imagerouter_router.put("/upscale-models")
def put_upscale_models(body: UpscaleModelsBody) -> dict:
    """Сохранить выбор. Валидация: модель есть в каталоге и принимает
    изображение на вход (апскейл — это edits-запрос). Невалидные id
    отсеиваются и перечисляются в ответе."""
    catalog = {m.get("id"): m for m in _fetch_ir_models(force=True)}
    valid: list[str] = []
    skipped: list[str] = []
    for mid in body.models:
        m = catalog.get(mid)
        if m is None or not _supports_image_input(mid):
            skipped.append(mid)
        elif mid not in valid:
            valid.append(mid)
    _save_upscale_selection(valid)
    return {"models": valid, "skipped": skipped}


# --- Апскейлинг: режимы и форматы вывода для выбранных моделей ---

# output_format — глобальный параметр generations/edits API ImageRouter
# (docs.imagerouter.io): webp (дефолт шлюза), jpeg, png. В галерее храним
# без потерь, поэтому дефолт выбора — png.
IR_OUTPUT_FORMATS = ["png", "jpeg", "webp"]
IR_DEFAULT_OUTPUT_FORMAT = "png"


def _upscale_modes(m: dict) -> list[dict]:
    """Доступные режимы апскейла модели по каталогу: явные размеры
    parameters.size → режим на каждый размер; суффикс id «…-<n>x» →
    единственный честный множитель (модели -2x игнорируют больший scale);
    прочий custom → 2×/4× (size шлюзом honoring, кап стороны 2048)."""
    mid = str(m.get("id") or "")
    params = m.get("parameters") or {}
    sizes = [s for s in (params.get("size") or []) if isinstance(s, str) and s not in ("auto", "custom")]
    out: list[dict] = []
    if sizes:
        for s in sizes:
            try:
                a, b = s.lower().split("x")
                out.append({"id": s, "label": f"{int(a)}×{int(b)}", "size": f"{int(a)}x{int(b)}"})
            except ValueError:
                continue
        if out:
            return out
    mm = re.search(r"-(\d+)x$", mid.lower())
    if mm:
        n = max(1, min(int(mm.group(1)), 8))
        return [{"id": f"{n}x", "label": f"{n}×", "scale": n}]
    return [
        {"id": "2x", "label": "2×", "scale": 2},
        {"id": "4x", "label": "4×", "scale": 4},
    ]


def _upscale_mode_by_id(mid: str, mode_id: Optional[str]) -> Optional[dict]:
    """Найти режим модели по id (None — режим не задан/не найден)."""
    if not mode_id:
        return None
    m = _ir_model_by_id(mid)
    if m is None:
        return None
    for mo in _upscale_modes(m):
        if mo["id"] == mode_id:
            return mo
    return None


def _upscale_request_params(mid: str, info: dict, width: int, height: int) -> tuple:
    """(scale, size, size_label, format) для edits-запроса. Режим из селектора
    вкладки первичнее слайдерного scale: у моделей с явными размерами берём
    точный размер режима, у факторных — их честный множитель (-2x-модели
    игнорируют больший scale). Без режима — прежнее поведение (совместимость
    с quick-action). Формат валидируется по белому списку API."""
    scale = float(info.get("upscale_scale") or 2)
    mode_obj = _upscale_mode_by_id(mid, info.get("upscale_mode"))
    size: Optional[str] = None
    size_label: Optional[str] = None
    if mode_obj is not None and mode_obj.get("size"):
        size = str(mode_obj["size"])
        size_label = str(mode_obj.get("label") or size)
    elif mode_obj is not None and mode_obj.get("scale"):
        scale = float(mode_obj["scale"])
    size = size or _pick_upscale_size(mid, width, height, scale)
    fmt = str(info.get("upscale_format") or IR_DEFAULT_OUTPUT_FORMAT)
    if fmt not in IR_OUTPUT_FORMATS:
        fmt = IR_DEFAULT_OUTPUT_FORMAT
    return scale, size, size_label, fmt


@imagerouter_router.get("/upscale-options")
def get_upscale_options() -> dict:
    """Режимы и форматы вывода для моделей апскейлинга из выбора админа
    (тот же фильтр, что инъектирует spandrel-фейки, — списки совпадают
    с дропдауном «Модель увеличения» один-в-один)."""
    items: list[dict] = []
    for mid in _load_upscale_selection():
        m = _ir_model_by_id(mid)
        if m is None or not _supports_image_input(mid):
            continue
        items.append(
            {
                "id": mid,
                "name": mid.split("/")[-1],
                "modes": _upscale_modes(m),
                "formats": list(IR_OUTPUT_FORMATS),
                "default_format": IR_DEFAULT_OUTPUT_FORMAT,
            }
        )
    return {"models": items}


# --- Основные модели (генерация/правка): выбор администратора ---


class MainModelsBody(BaseModel):
    models: list[str] = Field(default_factory=list, max_length=1000)


@imagerouter_router.get("/main-models")
def get_main_models() -> dict:
    """Текущий выбор основных моделей. all_by_default=True — файла ещё нет,
    пользователям доступен весь каталог (список отдан для предзаполнения
    чекбоксов админ-UI)."""
    sel = _load_main_selection()
    if sel is None:
        ids = [m.get("id") for m in _fetch_ir_models() if m.get("id")]
        return {"models": ids, "all_by_default": True}
    items = []
    for mid in sel:
        m = _ir_model_by_id(mid)
        items.append({"id": mid, "available": m is not None, "image_input": _supports_image_input(mid) if m else None})
    return {"models": items, "all_by_default": False}


@imagerouter_router.put("/main-models")
def put_main_models(body: MainModelsBody) -> dict:
    """Сохранить выбор основных моделей (генерация и/или правка). Валидация:
    модель есть в каталоге (вход-image НЕ обязателен — чистая генерация
    тоже допустима). Пустой список разрешён (полное отключение генерации)."""
    catalog = {m.get("id") for m in _fetch_ir_models(force=True)}
    valid: list[str] = []
    skipped: list[str] = []
    for mid in body.models:
        if mid not in catalog:
            skipped.append(mid)
        elif mid not in valid:
            valid.append(mid)
    _save_main_selection(valid)
    return {"models": valid, "skipped": skipped}


# --- Улучшитель промтов: модель VLM и проверка в менеджере моделей ---


class EnhancerModelBody(BaseModel):
    model: str = Field(min_length=1, max_length=200)


class EnhanceTestBody(BaseModel):
    prompt: str = Field(default="", max_length=8000)
    image: Optional[str] = Field(default=None, max_length=14_000_000)  # dataURL


@imagerouter_router.get("/enhancer-model")
def get_enhancer_model() -> dict:
    """Модель улучшителя промтов (кнопка «Prompt Assistant») + каталог VLM
    для селектора менеджера (вход image, выход text)."""
    model, source = _load_enhancer_choice()
    return {"model": model, "source": source, "vlms": _fetch_vlm_ids()}


@imagerouter_router.put("/enhancer-model")
def put_enhancer_model(body: EnhancerModelBody) -> dict:
    """Сохранить выбор (валидация по каталогу VLM; каталог недоступен —
    сохраняем как есть, ошибка всплывёт при первом вызове)."""
    m = body.model.strip()
    ids = _fetch_vlm_ids(force=True)
    if ids and m not in ids:
        raise HTTPException(
            status_code=400,
            detail=f"{m} — не VLM (нужен вход image и выход text) или нет в каталоге")
    _save_enhancer_choice(m)
    return {"ok": True, "model": m}


@imagerouter_router.post("/enhance-test")
def enhance_test(body: EnhanceTestBody) -> dict:
    """Проверка улучшателя в менеджере: промт (+опциональная картинка) ->
    улучшенный промт ТЕМИ ЖЕ системным промтом, моделью и ключом, что у
    пользователей (глобальный ключ инстанса). Ленивый импорт модуля
    инвокций: тесты подменяют его в sys.modules, сервер берёт развёрнутый."""
    if not body.prompt.strip() and not body.image:
        raise HTTPException(status_code=400, detail="Введите промт или приложите картинку")
    try:
        from invokeai.app.invocations.devbim_prompt_enhancer import (
            SYSTEM_ENHANCE, call_vlm, prepare_image)
    except ImportError:
        raise HTTPException(
            status_code=503, detail="Модуль улучшителя не развёрнут (setup_imagerouter.py)")
    urls: list[str] = []
    if body.image:
        from PIL import Image
        try:
            raw = base64.b64decode(body.image.split(",", 1)[-1])
            urls = [prepare_image(Image.open(io.BytesIO(raw)))]
        except Exception:
            raise HTTPException(status_code=400, detail="Не удалось прочитать изображение")
    try:
        text = call_vlm(SYSTEM_ENHANCE, body.prompt, urls)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"prompt": text}


# --- Пометки моделей (звёзды/баннеры): эндпоинты менеджера ---


class ModelMarksBadgeBody(BaseModel):
    label: str = Field(min_length=1, max_length=24)
    color: str = "#4a5568"
    title: str = Field(default="", max_length=200)


class ModelMarksBody(BaseModel):
    badges: dict[str, ModelMarksBadgeBody] = Field(default_factory=dict)
    marks: dict[str, dict] = Field(default_factory=dict)


@imagerouter_router.get("/model-marks")
def get_model_marks() -> dict:
    """Действующие пометки (звёзды 1–5 + баннеры) и каталог баннеров.
    source: defaults — файл ещё не сохранялся, показаны встроенные дефолты."""
    loaded = _load_marks()
    if loaded is None:
        return {
            "badges": dict(_DEFAULT_BADGES),
            "marks": {k: dict(v) for k, v in _DEFAULT_MARKS.items()},
            "source": "defaults",
        }
    return {**loaded, "source": "file"}


@imagerouter_router.put("/model-marks")
def put_model_marks(body: ModelMarksBody) -> dict:
    """Сохранить пометки и каталог баннеров (менеджер моделей). Валидация —
    как при чтении файла: звёзды 0–5, баннеры только из каталога, пустые
    записи отбрасываются. Идентификаторы моделей НЕ проверяются по каталогу
    (модель может временно пропасть — пометка переживёт)."""
    badges = _sanitize_badges_catalog({k: v.model_dump() for k, v in body.badges.items()})
    if not badges:
        badges = dict(_DEFAULT_BADGES)
    marks = _sanitize_marks(body.marks, badges)
    _save_marks(badges, marks)
    return {"badges": badges, "marks": marks, "source": "file"}


# ============================================================================
# Интеграция в основной интерфейс (Canvas): модели ImageRouter в выборе модели
# ============================================================================

_ir_models_cache: dict[str, Any] = {"ts": 0.0, "items": []}


def _fetch_ir_models(force: bool = False) -> list[dict]:
    """Каталог ImageRouter (публичный), кэш на 10 минут."""
    now = time.time()
    if not force and _ir_models_cache["items"] and now - _ir_models_cache["ts"] < IR_MODELS_CACHE_TTL:
        return _ir_models_cache["items"]
    try:
        resp = requests.get(
            MODELS_URL,
            params={"output_modalities": "image", "limit": 500, "sort": "name"},
            timeout=TIMEOUT_SHORT,
        )
        data = resp.json()
        if resp.status_code == 200 and isinstance(data, list):
            _ir_models_cache["ts"] = now
            _ir_models_cache["items"] = data
    except Exception:
        traceback.print_exc()
    return _ir_models_cache["items"]


def _ir_model_by_id(mid: str) -> Optional[dict]:
    for m in _fetch_ir_models():
        if m.get("id") == mid:
            return m
    return None


def _avg_price(m: dict) -> Optional[float]:
    p = m.get("pricing") or {}
    v = p.get("average", p.get("min"))
    return v if isinstance(v, (int, float)) else None


def _ir_size_digest(m: dict) -> str:
    """Дайджест размеров модели из каталога (parameters.size):
    "up to 3K (3136×1344)" + "custom size" при custom. Пустая строка,
    если данных нет. Решение 19.09: сделать выбор модели информативнее
    (качество 1–4K, форматы). 21.09: текст английский — интерфейс
    пользователя на английском, провайдер не называем."""
    sizes = (m.get("parameters") or {}).get("size") or []
    max_side = 0
    max_pair: Optional[tuple[int, int]] = None
    custom = False
    for s in sizes:
        if not isinstance(s, str):
            continue
        if s == "custom":
            custom = True
            continue
        parts = s.lower().split("x")
        if len(parts) != 2:
            continue
        try:
            w, h = int(parts[0]), int(parts[1])
        except ValueError:
            continue
        if max(w, h) > max_side:
            max_side = max(w, h)
            max_pair = (w, h)
    if not max_side and not custom:
        return ""
    parts: list[str] = []
    if max_side and max_pair:
        parts.append(f"up to {max(1, round(max_side / 1024))}K ({max_pair[0]}×{max_pair[1]})")
    if custom:
        parts.append("custom size")
    return " · ".join(parts)


def _ir_fake_config(m: dict) -> dict:
    import hashlib

    mid = m.get("id", "")
    # Описание пользовательское (селектор модели + виджет описания):
    # английский, без названия провайдера (решение 21.09 — куда уходит
    # генерация, пользователю не показываем). Слово "editing" ОБЯЗАТЕЛЬНО:
    # на него опирается гейт Generate-фолбэка (п.22 HANDOFF, ищет
    # cfg.description.indexOf("editing")).
    desc = "Cloud image generation"
    inputs = ((m.get("architecture") or {}).get("input_modalities")) or []
    if "image" in inputs:
        desc += " · ✏️ editing"
    desc += " · formats PNG, JPEG, WebP"
    size_part = _ir_size_digest(m)
    if size_part:
        desc += " · " + size_part
    cfg = {
        "key": IR_KEY_PREFIX + mid,
        # hash обязателен (zod: min(1)) — стабильный псевдохеш от id
        "hash": hashlib.md5(mid.encode("utf-8")).hexdigest(),
        "path": f"imagerouter://{mid}",
        "file_size": 0,
        "name": mid.split("/")[-1],
        "type": "main",
        "format": "diffusers",
        "base": FAKE_BASE,
        "source": "https://imagerouter.io",
        "source_type": "url",
        "description": desc,
        "variant": "normal",
        "cover_image": None,
    }
    # Пометки владельца (звёзды/баннеры): серый суб-текст опции списка;
    # клиентский скрипт devbim-model-info.js раскрашивает их в чипы
    usage = _marks_usage_info(m)
    if usage:
        cfg["usage_info"] = usage
    return cfg


# Фейковая модель IP-Adapter для референсных изображений: локальных моделей
# нет, а без выбранной модели клиент выбрасывает референс из графа и пишет
# «Модель не выбрана». Референсы передаются в API как image[].
IPADAPTER_FAKE_ID = "ip-adapter-reference"
IPADAPTER_FAKE_KEY = IR_KEY_PREFIX + IPADAPTER_FAKE_ID


def _ir_ipadapter_fake() -> dict:
    import hashlib

    return {
        "key": IPADAPTER_FAKE_KEY,
        "hash": hashlib.md5(IPADAPTER_FAKE_ID.encode("utf-8")).hexdigest(),
        "path": f"imagerouter://{IPADAPTER_FAKE_ID}",
        "file_size": 0,
        "name": "Reference",
        "type": "ip_adapter",
        "format": "checkpoint",
        "base": FAKE_BASE,
        "source": "https://imagerouter.io",
        "source_type": "url",
        "description": "Reference images for cloud generation",
        "variant": "normal",
        "cover_image": None,
    }


# Фейковый tile-ControlNet для вкладки Upscaling: unified-апскейл требует
# «Tile ControlNet model for the chosen main model architecture» (base главных
# фейков — sdxl, имя обязано содержать «tile» — по нему клиент авто-выбирает).
# Локально граф не исполняется — узел в графе остаётся декорацией.
TILE_CONTROLNET_FAKE_ID = "tile-controlnet"
TILE_CONTROLNET_FAKE_KEY = IR_KEY_PREFIX + TILE_CONTROLNET_FAKE_ID


def _ir_tile_fake() -> dict:
    import hashlib

    return {
        "key": TILE_CONTROLNET_FAKE_KEY,
        "hash": hashlib.md5(("upscale:" + TILE_CONTROLNET_FAKE_ID).encode("utf-8")).hexdigest(),
        "path": f"imagerouter://{TILE_CONTROLNET_FAKE_ID}",
        "file_size": 0,
        "name": "Tile ControlNet",
        "type": "controlnet",
        "format": "checkpoint",
        "base": FAKE_BASE,
        "source": "https://imagerouter.io",
        "source_type": "url",
        "description": "Decorative model; upscaling runs in the cloud",
        "variant": "normal",
        "cover_image": None,
    }


def _ir_upscale_fake_config(m: dict) -> dict:
    """Выбранная админом модель как spandrel-конфиг (дропдаун «Upscale Model»
    вкладки Upscaling показывает все модели type=spandrel_image_to_image).
    Описание пользовательское: английский, без провайдера; цену не
    показываем (08.09)."""
    import hashlib

    mid = m.get("id", "")
    return {
        "key": IR_UPSCALE_KEY_PREFIX + mid,
        # hash отличаем от main-фейка той же модели (роль другая — ключ другой)
        "hash": hashlib.md5(("upscale:" + mid).encode("utf-8")).hexdigest(),
        "path": f"imagerouter-upscale://{mid}",
        "file_size": 0,
        "name": mid.split("/")[-1],
        "type": "spandrel_image_to_image",
        "format": "checkpoint",
        "base": "any",
        "source": "https://imagerouter.io",
        "source_type": "url",
        "description": "Cloud image upscaling",
        "variant": "normal",
        "cover_image": None,
    }


def _ir_upscale_configs() -> list[dict]:
    """Spandrel-фейки для моделей из выбора администратора (порядок списка =
    порядок выбора: первый — модель по умолчанию у пользователей). Модели без
    входа-image не инъектируются: апскейл — это edits-запрос (страховка от
    вручную отредактированного файла выбора)."""
    out: list[dict] = []
    for mid in _load_upscale_selection():
        m = _ir_model_by_id(mid)
        if m is not None and _supports_image_input(mid):
            out.append(_ir_upscale_fake_config(m))
    return out


def _ir_fake_configs() -> list[dict]:
    return (
        [_ir_fake_config(m) for m in _selected_main_models()]
        + [_ir_ipadapter_fake()]
        + _ir_upscale_configs()
        + [_ir_tile_fake()]
    )


def _add_ir_models(data: Any) -> None:
    """Дописывает модели ImageRouter в ответ /api/v2/models (без дублей)."""
    models = data.get("models") if isinstance(data, dict) else None
    if not isinstance(models, list):
        return
    existing = {m.get("key") for m in models if isinstance(m, dict)}
    for fake in _ir_fake_configs():
        if fake["key"] not in existing:
            models.append(fake)


def _pick_size(mid: str, width: int, height: int) -> Optional[str]:
    """Размер для API: точный, если разрешён моделью; иначе auto (None)."""
    m = _ir_model_by_id(mid) or {}
    params = (m.get("parameters") or {}).get("size") or []
    allowed = [s for s in params if isinstance(s, str) and s not in ("auto", "custom")]
    candidate = f"{int(width)}x{int(height)}"
    if not allowed:
        return candidate  # модель принимает произвольные размеры
    return candidate if candidate in allowed else None


def _snap64(x: int) -> int:
    return max(64, (int(x) + 31) // 64 * 64)


# наблюдаемый лимит шлюза для моделей с произвольным размером (кратно 64, 128..2048)
UPSCALE_SIDE_CAP = 2048


def _pick_upscale_size(mid: str, width: int, height: int, scale: float) -> Optional[str]:
    """Целевой размер апскейла: исходник × масштаб. Если у модели явный список
    размеров — ближайший, покрывающий цель (иначе максимальный); без списка —
    цель со снапом к 64 и капом стороны (size=auto → модель выберет сама)."""
    m = _ir_model_by_id(mid) or {}
    params = (m.get("parameters") or {}).get("size") or []
    allowed = [s for s in params if isinstance(s, str) and s not in ("auto", "custom")]
    target_w = _snap64(int(width) * int(scale))
    target_h = _snap64(int(height) * int(scale))
    if allowed:
        dims: list[tuple[int, int]] = []
        for s in allowed:
            try:
                a, b = s.lower().split("x")
                dims.append((int(a), int(b)))
            except ValueError:
                continue
        if dims:
            covering = [d for d in dims if d[0] >= target_w and d[1] >= target_h]
            chosen = min(covering, key=lambda d: d[0] * d[1]) if covering else max(dims, key=lambda d: d[0] * d[1])
            return f"{chosen[0]}x{chosen[1]}"
        return None
    target_w, target_h = min(target_w, UPSCALE_SIDE_CAP), min(target_h, UPSCALE_SIDE_CAP)
    if target_w < 128 or target_h < 128:
        return None
    return f"{target_w}x{target_h}"


def _upscale_prompt(
    scale: Optional[float] = None,
    creativity: Optional[float] = None,
    structure: Optional[float] = None,
    size_label: Optional[str] = None,
) -> str:
    """Серверный промпт для облачного апскейла (у вкладки поля промпта нет).
    Цель — множитель («2x») или явный размер («2048×2048» из режима модели).
    Регуляторы вкладки переводятся в мягкие пояснения: creativity — доля
    перерисовки (1 - denoising_start, слайдер 0 ≈ 0.5), structure — вес
    tile-ControlNet (0.3..0.625)."""
    target = f"{size_label} resolution" if size_label else f"approximately {int(round(scale or 2))}x higher resolution"
    p = (
        f"Upscale this image to {target}. "
        "Increase sharpness and refine fine details, textures and edges. "
        "Keep the composition, geometry, colors and content exactly the same. "
        "Do not add, remove or alter any objects."
    )
    if creativity is not None:
        if creativity >= 0.75:
            p += " You may creatively enhance fine details while keeping the overall structure recognizable."
        elif creativity <= 0.25:
            p += " Be strictly faithful: only increase resolution and sharpness, no artistic changes."
    if structure is not None and structure >= 0.55:
        p += " Preserve the exact structure, proportions and composition."
    return p


class _IRClientError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


# --- Видимость генерации в UI (полоска/статус очереди) ---
#
# Облачная генерация не проходит через реальную очередь InvokeAI (элемент в
# БД не ставится), поэтому фронтенд считает очередь пустой и стирает прогресс
# при любом обновлении стора (подписка: queue.in_progress === 0 -> очистить
# $lastProgressEvent). Чтобы полоска «Generating» и счётчик очереди жили:
#   1) держим счётчик выполняемых генераций и на его основе патчим ответ
#      GET /api/v1/queue/{q}/status (in_progress + N);
#   2) шлём события invocation_started / invocation_progress (алерт «Generating»)
#      и queue_item_status_changed(in_progress) (обновление бейджа очереди).

_INFLIGHT: dict[str, int] = {}
_INFLIGHT_LOCK = threading.Lock()

# интервал «пульса» invocation_progress, сек
PROGRESS_TICK = 2.0


def _inflight_count(queue_id: str) -> int:
    with _INFLIGHT_LOCK:
        return _INFLIGHT.get(queue_id, 0)


def _inflight_inc(queue_id: str) -> None:
    with _INFLIGHT_LOCK:
        _INFLIGHT[queue_id] = _INFLIGHT.get(queue_id, 0) + 1


def _inflight_dec(queue_id: str) -> None:
    with _INFLIGHT_LOCK:
        n = max(0, _INFLIGHT.get(queue_id, 0) - 1)
        if n:
            _INFLIGHT[queue_id] = n
        else:
            _INFLIGHT.pop(queue_id, None)


def _supports_image_input(mid: str) -> bool:
    m = _ir_model_by_id(mid) or {}
    inputs = ((m.get("architecture") or {}).get("input_modalities")) or []
    return "image" in inputs


def _is_echo(init_pil: Any, result_pil: Any) -> bool:
    """Модель вернула вход без правки (эхо): средняя пиксельная разница
    после нормализации размера почти нулевая. Так ведут себя модели, у
    которых в каталоге заявлен вход-картинка, но правку они не выполняют
    (замечено 20.08 на onomaai/illustrious-xl: две «генерации» побайтово
    совпадали со входом). Порог 3.0 отсекает шум перекодирования, реальные
    правки дают разницу на порядок больше."""
    import numpy as np

    a = init_pil.convert("RGB")
    b = result_pil.convert("RGB")
    if b.size != a.size:
        b = b.resize(a.size)
    return float(np.abs(np.asarray(a, np.int16) - np.asarray(b, np.int16)).mean()) <= 3.0


def _mask_edit_alpha(mask_pil: Any) -> Any:
    """Альфа-маска в OpenAI-семантике: 0 (прозрачное) = зона правки.

    Слой Inpaint Mask канваса — непрозрачный растр, выделение ЧЁРНОЕ на
    белом (create_gradient_mask ждёт 0 = править), поэтому носителем служит
    яркость без инверсии. Маска с прозрачным фоном — наоборот, выделение
    непрозрачно, инвертируем альфу.
    """
    alpha = mask_pil.convert("RGBA").getchannel("A")
    if alpha.getextrema()[0] >= 255:
        return mask_pil.convert("L")
    return alpha.point(lambda v: 255 - v)


def _draw_mask_marker(init_pil: Any, mask_pil: Any) -> Any:
    """Подсветка зоны правки для моделей без параметра mask (шлюз ImageRouter
    его не поддерживает): полупрозрачная пурпурная заливка + рамка."""
    from PIL import Image, ImageDraw

    base = init_pil.convert("RGBA")
    zone = _mask_edit_alpha(mask_pil).point(lambda v: 255 - v)  # 255 = править
    overlay = Image.new("RGBA", base.size, (255, 0, 255, 0))
    overlay.putalpha(zone.point(lambda v: 110 if v >= 128 else 0))
    marked = Image.alpha_composite(base, overlay)
    bbox = zone.point(lambda v: 255 if v >= 128 else 0).getbbox()
    if bbox:
        ImageDraw.Draw(marked).rectangle(bbox, outline=(255, 0, 255, 255), width=max(2, base.width // 400))
    return marked


def _resolve_edge_image(nodes: dict, edges: list, node_id: str, field: str, depth: int = 0) -> Optional[str]:
    """Имя картинки на входе поля field узла node_id.

    В 6.2 маску канвас подключает к create_gradient_mask.mask ребром от
    mask_combine (растр слоя Inpaint Mask лежит в его mask1) — inline-поля
    mask в графе может не быть вовсе. Идём по рёбрам вглубь.
    """
    if depth > 8:
        return None
    node = nodes.get(node_id) or {}
    v = node.get(field)
    if isinstance(v, dict) and isinstance(v.get("image_name"), str):
        return v["image_name"]
    for e in edges:
        d, s = e.get("destination") or {}, e.get("source") or {}
        if d.get("node_id") != node_id or d.get("field") != field:
            continue
        snode = nodes.get(s.get("node_id")) or {}
        # mask_combine(mask1, mask2): mask1 — выбор пользователя (слой-маска),
        # mask2 — альфа подложки (границы outpaint); нужен mask1
        fields = ("mask1", "mask2") if snode.get("type") == "mask_combine" else ("image", "mask")
        for f in fields:
            r = _resolve_edge_image(nodes, edges, s.get("node_id"), f, depth + 1)
            if r:
                return r
    return None


def _apply_edit_mask(original: Any, zone_full: Any, edited: Any, bbox: tuple) -> Any:
    """Результат модели оставляем только в зоне маски (с растушёвкой):
    вне маски картинка не меняется вовсе, даже если модель перерисовала всё."""
    from PIL import Image, ImageFilter

    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    edit = edited.convert("RGBA")
    if edit.size != (w, h):
        edit = edit.resize((w, h))
    canvas_edit = Image.new("RGBA", original.size, (0, 0, 0, 0))
    canvas_edit.paste(edit, (bbox[0], bbox[1]))
    feathered = zone_full.filter(ImageFilter.GaussianBlur(4))
    return Image.composite(canvas_edit, original.convert("RGBA"), feathered)


def _extract_ir_info(batch: dict) -> dict:
    """Из графа Canvas достаём модель, промпт, размер, доску и исходное
    изображение/маску (для режимов inpaint/outpaint/img2img).

    Графы апскейлинга (вкладка Upscaling и quick-action из контекстного меню
    картинки) распознаются по spandrel-узлу: is_upscale=True, модель апскейла
    в upscale_model_key (префикс imagerouter-upscale/), исходник в init_image,
    масштаб в upscale_scale. В графе вкладки есть и main-модель (sdxl_loader),
    в adhoc-графе quick-action main-модели нет вовсе — поэтому признак
    is_upscale первичнее model_key."""
    nodes = (batch.get("graph") or {}).get("nodes") or {}
    info: dict[str, Any] = {
        "model_key": None,
        "positive": "",
        "negative": "",
        "width": 0,
        "height": 0,
        "board_id": None,
        "mode": "txt2img",
        "init_image": None,
        "mask": None,
        "references": [],
        # тип (method) и вес (weight) каждого референса из его узла
        # ip_adapter — параллельно списку references (решение 21.09)
        "ref_details": [],
        "is_upscale": False,
        "upscale_model_key": None,
        "upscale_scale": None,
        # нормированные регуляторы вкладки: creativity = 1 - denoising_start
        # (больше = творческая свобода), structure = control_weight тайла
        "upscale_creativity": None,
        "upscale_structure": None,
        # выбор облачных селекторов вкладки: режим («2x»/«2048x2048») и
        # формат вывода — доп. поля spandrel-узла от патченого билдера
        "upscale_mode": None,
        "upscale_format": None,
    }
    for node in nodes.values():
        if not isinstance(node, dict):
            continue
        ntype = node.get("type")
        if ntype in ("spandrel_image_to_image", "spandrel_image_to_image_autoscale"):
            info["is_upscale"] = True
            um = node.get("image_to_image_model")
            if isinstance(um, dict) and str(um.get("key", "")).startswith(IR_UPSCALE_KEY_PREFIX):
                info["upscale_model_key"] = str(um["key"])
            v = node.get("image")
            if isinstance(v, dict) and isinstance(v.get("image_name"), str):
                info["init_image"] = v["image_name"]
            sc = node.get("scale")
            if isinstance(sc, (int, float)) and sc > 0:
                info["upscale_scale"] = float(sc)
            if info.get("upscale_mode") is None and isinstance(node.get("upscale_mode"), str) and node["upscale_mode"]:
                info["upscale_mode"] = node["upscale_mode"]
            if info.get("upscale_format") is None and isinstance(node.get("output_format"), str) and node["output_format"]:
                info["upscale_format"] = node["output_format"]
            continue
        if ntype == "tiled_multi_diffusion_denoise_latents":
            ds = node.get("denoising_start")
            if isinstance(ds, (int, float)):
                info["upscale_creativity"] = 1.0 - float(ds)
        elif ntype == "controlnet":
            # в графе ДВА controlnet-узла (двухстадийный контроль); вес
            # первого — это маппинг слайдера Structure, дальше не перезаписываем
            cw = node.get("control_weight")
            if info["upscale_structure"] is None and isinstance(cw, (int, float)):
                info["upscale_structure"] = float(cw)
        if ntype == "ip_adapter":
            # референсные изображения: image — словарь или список словарей;
            # их НЕ считаем исходником/маской. Тип референса (селектор
            # «Тип референса») и вес едут в полях method/weight узла
            v = node.get("image")
            method = node.get("method") if isinstance(node.get("method"), str) else None
            weight = node.get("weight") if isinstance(node.get("weight"), (int, float)) else None
            for it in (v if isinstance(v, list) else [v]):
                if isinstance(it, dict) and isinstance(it.get("image_name"), str):
                    info["references"].append(it["image_name"])
                    info["ref_details"].append(
                        {"image": it["image_name"], "type": method or None, "weight": weight}
                    )
            continue
        if ntype == "core_metadata":
            info["positive"] = node.get("positive_prompt") or info["positive"]
            info["negative"] = node.get("negative_prompt") or info["negative"]
            info["width"] = node.get("width") or info["width"]
            info["height"] = node.get("height") or info["height"]
            # generation_mode приходит с префиксом базы (sdxl_inpaint,
            # flux_img2img, cogview4_outpaint, ...) — убираем его
            gm = node.get("generation_mode")
            info["mode"] = gm.split("_")[-1] if gm else info["mode"]
        m = node.get("model")
        if isinstance(m, dict) and str(m.get("key", "")).startswith(IR_KEY_PREFIX):
            info["model_key"] = str(m["key"])
        # доска: у канваса поле board на save_image, у апскейла — на l2i
        board = node.get("board")
        if isinstance(board, dict) and board.get("board_id"):
            info["board_id"] = str(board["board_id"])
        # исходное изображение: create_gradient_mask.image / i2l.image / любой ImageField
        for fname in ("image", "mask"):
            v = node.get(fname)
            if isinstance(v, dict) and isinstance(v.get("image_name"), str):
                if fname == "image" and not info["init_image"]:
                    info["init_image"] = v["image_name"]
                elif fname == "mask" and not info["mask"]:
                    info["mask"] = v["image_name"]
    # Маска inpaint подключена ребром к create_gradient_mask.mask — если
    # inline-поля mask в графе нет, достаём через обход рёбер
    if not info["mask"]:
        edges = (batch.get("graph") or {}).get("edges") or []
        for nid, node in nodes.items():
            if isinstance(node, dict) and node.get("type") == "create_gradient_mask":
                m = _resolve_edge_image(nodes, edges, nid, "mask")
                if m and m != info["init_image"]:
                    info["mask"] = m
                    break
    # Промпт может лежать не в core_metadata, а в узлах prompt/compel
    if not info["positive"] or not info["negative"]:
        for node in nodes.values():
            if not isinstance(node, dict):
                continue
            nid = str(node.get("id", ""))
            is_negative = "negative" in nid.lower()
            for fname, target in (("positive", "positive"), ("prompt", "positive"), ("negative", "negative")):
                val = node.get(fname)
                if isinstance(val, str) and val.strip():
                    if is_negative and target == "negative":
                        info["negative"] = info["negative"] or val
                    elif not is_negative and target == "positive" and not info["positive"]:
                        info["positive"] = val
    # ...или в batch.data (значения полей узлов: node_path/field_name/items)
    for data_group in batch.get("data") or []:
        for item in data_group or []:
            try:
                node_path = str(item.get("node_path", ""))
                values = item.get("items") or []
                value = values[0] if values else None
            except AttributeError:
                continue
            if not isinstance(value, str) or not value.strip():
                continue
            if "negative" in node_path.lower():
                info["negative"] = info["negative"] or value
            elif "positive" in node_path.lower():
                info["positive"] = value
    info["width"] = int(info["width"] or 1024)
    info["height"] = int(info["height"] or 1024)
    # референсы: без дублей и без подложки/маски (имена и метаданные — парой)
    _seen_refs: set = set()
    _refs: list[str] = []
    _details: list[dict] = []
    for name, det in zip(info["references"], info["ref_details"]):
        if name in _seen_refs or name in (info["init_image"], info["mask"]):
            continue
        _seen_refs.add(name)
        _refs.append(name)
        _details.append(det)
    info["references"] = _refs
    info["ref_details"] = _details
    return info


def _item_to_pil(item: dict) -> Any:
    """Элемент ответа API (url или b64_json) -> PIL.Image (RGB) или None."""
    from PIL import Image

    raw: Optional[bytes] = None
    url = item.get("url")
    if url:
        r = requests.get(url, timeout=TIMEOUT_GENERATE)
        if r.status_code == 200:
            raw = r.content
    elif item.get("b64_json"):
        try:
            raw = base64.b64decode(item["b64_json"])
        except (binascii.Error, ValueError):
            raw = None
    if not raw:
        return None
    img = Image.open(io.BytesIO(raw))
    return img.convert("RGB")


def _pil_to_durl(img: Any, fmt: str = "PNG", max_side: int = 0, quality: int = 92) -> str:
    """PIL-картинка -> data-URL для JSON-тела edits-эндпоинта.

    PNG сохраняет альфу холста (прозрачные поля остаются прозрачными —
    решение пользователя 05.09), JPEG с даунскейлом экономит объём для
    референсов-фотографий.
    """
    im = img
    if fmt == "JPEG":
        im = img.convert("RGB")
        if max_side and max(im.size) > max_side:
            im.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    if fmt == "JPEG":
        im.save(buf, format="JPEG", quality=quality)
    else:
        im.save(buf, format="PNG")
    return f"data:image/{fmt.lower()};base64," + base64.b64encode(buf.getvalue()).decode()


def _queue_event_factories(queue_id: str, batch: dict, graph: dict, services: Any):
    """Фабрики событий очереди для облачной генерации (canvas и апскейл):
    бейдж очереди (queue_item_status_changed), алерт «Generating»
    (invocation_started/progress). Возврат: (dispatch, status_event,
    progress_event, batch_id, origin, destination, session_id)."""
    from invokeai.app.services.events.events_common import (
        InvocationProgressEvent,
        QueueItemStatusChangedEvent,
    )
    from invokeai.app.invocations.image import SaveImageInvocation
    from invokeai.app.services.session_queue.session_queue_common import BatchStatus

    batch_id = str(batch.get("batch_id") or uuid.uuid4())
    session_id = str(graph.get("id") or batch_id)
    origin = batch.get("origin") or "canvas"
    destination = batch.get("destination") or "canvas"

    def status_event(status: str, completed: int = 0, failed: int = 0) -> QueueItemStatusChangedEvent:
        return QueueItemStatusChangedEvent(
            queue_id=queue_id,
            item_id=0,
            batch_id=batch_id,
            origin=origin,
            destination=destination,
            status=status,
            batch_status=BatchStatus(
                queue_id=queue_id,
                batch_id=batch_id,
                origin=origin,
                destination=destination,
                pending=0,
                in_progress=1 if status == "in_progress" else 0,
                completed=completed,
                failed=failed,
                canceled=0,
                total=max(1, completed + failed),
            ),
            queue_status=services.session_queue.get_queue_status(queue_id=queue_id),
            session_id=session_id,
        )

    def progress_event(message: str) -> InvocationProgressEvent:
        return InvocationProgressEvent(
            queue_id=queue_id,
            item_id=0,
            batch_id=batch_id,
            origin=origin,
            destination=destination,
            session_id=session_id,
            invocation=SaveImageInvocation(id="imagerouter_save"),
            invocation_source_id="imagerouter_save",
            message=message,
        )

    return services.events.dispatch, status_event, progress_event, batch_id, origin, destination, session_id


def _handle_canvas_generation(queue_id: str, payload: dict, studio_user: str | None = None) -> dict:
    """Генерация через ImageRouter вместо локального исполнения графа."""
    from PIL import Image

    from invokeai.app.api.dependencies import ApiDependencies
    from invokeai.app.invocations.fields import ImageField
    from invokeai.app.invocations.image import SaveImageInvocation
    from invokeai.app.invocations.primitives import ImageOutput
    from invokeai.app.services.events.events_common import (
        BatchEnqueuedEvent,
        InvocationCompleteEvent,
        InvocationStartedEvent,
    )
    from invokeai.app.services.image_records.image_records_common import ImageCategory, ResourceOrigin

    batch = payload.get("batch") or {}
    graph = batch.get("graph") or {}
    info = _extract_ir_info(batch)
    model_key = info["model_key"]
    if not model_key:
        raise _IRClientError("No generation model selected")
    mid = model_key[len(IR_KEY_PREFIX):]
    _ref_log = " ".join(
        f"{d['type'] or '?'}:{_ref_weight(d):g}" if _ref_weight(d) is not None else str(d["type"] or "?")
        for d in info["ref_details"]
    )
    print(
        f"[imagerouter] enqueue: model={mid} mode={info['mode']} "
        f"init={info['init_image']} mask={info['mask']} refs={info['references']}"
        + (f" types=[{_ref_log}]" if _ref_log else ""),
        flush=True,
    )
    key = effective_key(studio_user)
    if not key:
        raise _IRClientError(
            ("Персональный токен ImageRouter не задан — обратитесь к администратору."
             if studio_user and studio_user != "admin-local" else
             "Generation service is not configured: no API key. "
             "Please contact your administrator."),
            401,
        )

    runs = max(1, min(int(batch.get("runs") or 1), MAX_RUNS))
    services = ApiDependencies.invoker.services
    dispatch, _status_event, _progress_event, batch_id, origin, destination, session_id = (
        _queue_event_factories(queue_id, batch, graph, services)
    )
    events = services.events

    events.dispatch(
        BatchEnqueuedEvent(
            queue_id=queue_id, batch_id=batch_id, enqueued=runs, requested=runs, priority=0, origin=origin
        )
    )
    _studio_tag("batch", batch_id, studio_user)

    _inflight_inc(queue_id)
    # invalidates SessionQueueStatus -> клиент перезапросит /status (он патчится
    # мидлварью, пока _INFLIGHT[queue_id] > 0) и покажет «в работе»
    events.dispatch(_status_event("in_progress"))
    events.dispatch(
        InvocationStartedEvent(
            queue_id=queue_id,
            item_id=0,
            batch_id=batch_id,
            origin=origin,
            destination=destination,
            session_id=session_id,
            invocation=SaveImageInvocation(id="imagerouter_save"),
            invocation_source_id="imagerouter_save",
        )
    )
    # «пульс» для алерта «Generating» — реальные проценты облако не отдаёт
    ticker_stop = threading.Event()
    run_state = {"run": 0}

    def _ticker() -> None:
        t0 = time.time()
        while not ticker_stop.wait(PROGRESS_TICK):
            try:
                events.dispatch(
                    _progress_event(f"Generating · {mid} · {run_state['run']}/{runs} · {int(time.time() - t0)}s")
                )
            except Exception:  # noqa: BLE001
                break

    threading.Thread(target=_ticker, daemon=True, name="ir-progress").start()

    saved: list[Any] = []
    try:
        # --- режим правки: есть исходник и/или референсные изображения ---
        refs_pil: list[Any] = []
        if info["references"]:
            try:
                refs_pil = [services.images.get_pil_image(n) for n in info["references"]]
            except Exception as e:  # noqa: BLE001
                raise _IRClientError(f"Failed to load reference image ({e})", 500) from e

        is_edit = info["mode"] in ("inpaint", "outpaint", "img2img") and info["init_image"]
        # референсы тоже уходят через edits-эндпоинт (multipart image[])
        use_edits = is_edit or bool(refs_pil)
        init_full = None
        mask_full = None
        zone_full = None
        edit_bbox = None
        init_pil = None
        mask_pil = None
        if use_edits:
            if not _supports_image_input(mid):
                raise _IRClientError(
                    f"The model '{mid}' does not support editing (it does not accept an image as input). "
                    "Please select a model with the 'editing' mark.",
                    400,
                )
            if info["init_image"]:
                try:
                    init_full = services.images.get_pil_image(info["init_image"])
                    mask_full = services.images.get_pil_image(info["mask"]) if info["mask"] else None
                except Exception as e:  # noqa: BLE001
                    raise _IRClientError(f"Failed to load source image ({e})", 500) from e
                # зона правки в семантике канваса: 255 = менять
                zone_full = _mask_edit_alpha(mask_full).point(lambda v: 255 - v) if mask_full is not None else None
                # Кадрируем по содержимому и маске (+8px запас): без прозрачных полей
                # канваса модель правит точнее. Результат затем вклеивается только
                # в зону маски (см. _apply_edit_mask)
                alpha_full = init_full.convert("RGBA").getchannel("A")
                content = alpha_full.point(lambda v: 255 if v > 8 else 0).getbbox()
                zone_bbox = zone_full.point(lambda v: 255 if v >= 128 else 0).getbbox() if zone_full is not None else None
                if zone_bbox is None:
                    # Маска не нарисована (слоя нет или выделение пустое).
                    # ГРАБЛИ (20.08): с пустой зоной кроп делался только по
                    # содержимому, модель правила его, но _apply_edit_mask
                    # выбрасывала результат — пользователь получал исходник
                    # назад. Вместо этого правим картинку ЦЕЛИКОМ.
                    # 05.09 (решение пользователя): белый фон модели НЕ
                    # подкладываем — прозрачные поля холста остаются
                    # прозрачными (PNG с альфа-каналом). IFC-снимок идёт с
                    # прозрачным фоном, модель получает объект без окружения
                    # и дорисовывает его сама; непрозрачные исходники (фото,
                    # фрагменты PDF) от изменения не страдают — они и так
                    # без прозрачности. Паддинг до сетки 64 остаётся.
                    zone_full = None
                    mask_full = None
                    src = init_full.convert("RGBA")
                    w64 = min(2048, max(128, (src.width + 63) // 64 * 64))
                    h64 = min(2048, max(128, (src.height + 63) // 64 * 64))
                    flat = Image.new("RGBA", (w64, h64), (0, 0, 0, 0))
                    flat.alpha_composite(src, ((w64 - src.width) // 2, (h64 - src.height) // 2))
                    init_full = flat
                    edit_bbox = (0, 0, w64, h64)
                else:
                    boxes = [b for b in (content, zone_bbox) if b]
                    if boxes:
                        pad = 8
                        edit_bbox = (
                            max(0, min(b[0] for b in boxes) - pad),
                            max(0, min(b[1] for b in boxes) - pad),
                            min(init_full.width, max(b[2] for b in boxes) + pad),
                            min(init_full.height, max(b[3] for b in boxes) + pad),
                        )
                    else:
                        edit_bbox = (0, 0, init_full.width, init_full.height)
                    # Внешний API требует стороны кратно 64 (128..2048), а зона
                    # правки после кадрирования по содержимому этому не отвечает
                    # (например, снимок IFC 832px внутри композита 1024px даёт
                    # 832+2*8=840). Расширяем зону до сетки 64 — сдвигами внутри
                    # границ картинки; содержимое зоны не обрезается.
                    bx0, by0, bx1, by1 = edit_bbox
                    ax0, ay0 = (bx0 // 64) * 64, (by0 // 64) * 64
                    ax1, ay1 = ((bx1 + 63) // 64) * 64, ((by1 + 63) // 64) * 64
                    if ax1 > init_full.width:
                        ax0 = max(0, ax0 - (ax1 - init_full.width))
                        ax1 = init_full.width
                    if ay1 > init_full.height:
                        ay0 = max(0, ay0 - (ay1 - init_full.height))
                        ay1 = init_full.height
                    if (ax1 - ax0) % 64 == 0 and (ay1 - ay0) % 64 == 0:
                        edit_bbox = (ax0, ay0, ax1, ay1)
                init_pil = init_full.crop(edit_bbox)
                mask_pil = mask_full.crop(edit_bbox) if mask_full is not None else None
                size = _pick_size(mid, init_pil.width, init_pil.height)
            else:
                size = _pick_size(mid, info["width"], info["height"])
        else:
            size = _pick_size(mid, info["width"], info["height"])

        base_prompt = (info["positive"] or "").strip()
        if refs_pil or init_pil is not None:
            # блок референсов: роль и вес каждой картинки по её типу
            # («Основной», «3D-ракурс», …); с исходником он начинает с
            # вшитых гвардов геометрии и сквозных окон — работают и когда
            # референсов нет (снимок + текстовый промт стиля)
            base_prompt += _reference_prompt_block(info["ref_details"], init_pil is not None)

        use_marker = False  # модель отвергла параметр mask — зона правки подсвечивается в картинке
        marked_pil: Any = None
        for i in range(runs):
            run_state["run"] = i + 1
            if use_edits and refs_pil:
                # ГРАБЛЯ (06.09): multipart со несколькими файлами (image +
                # image[]) доставляет модели ТОЛЬКО ПЕРВОЕ изображение —
                # референсы молча терялись, и модель рисовала материал «из
                # головы» (винтажные обои вместо кирпича со штукатуркой).
                # JSON-тело с массивом data-URL доходит целиком (проверено
                # 06.09 контактным листом и сценарием «материалы на стены»).
                # Параметр mask шлюз не принимает вовсе (19.08) — сразу маркер.
                if mask_pil is not None:
                    if marked_pil is None:
                        marked_pil = _draw_mask_marker(init_pil, mask_pil)
                    send_init, send_prompt = marked_pil, base_prompt + PROMPT_MARKER_NOTE
                else:
                    send_init, send_prompt = init_pil, base_prompt
                images: list[str] = []
                if send_init is not None:
                    images.append(_pil_to_durl(send_init))  # PNG: альфа холста
                images += [_pil_to_durl(r, "JPEG", 1024, 85) for r in refs_pil]
                body_json: dict[str, Any] = {"model": mid, "prompt": send_prompt, "image": images}
                if size:
                    body_json["size"] = size
                resp = requests.post(
                    EDITS_URL,
                    headers={"Authorization": f"Bearer {key}"},
                    json=body_json,
                    timeout=TIMEOUT_GENERATE,
                )
                print(f"[imagerouter] edits json ({len(images)} img) -> HTTP {resp.status_code}", flush=True)
                try:
                    data_out = _upstream_json(resp)
                except HTTPException as e:
                    raise _IRClientError(f"Generation failed: {e.detail}", e.status_code) from e
                err = _api_error_message(data_out)
                if err:
                    raise _IRClientError(f"Generation failed: {err}", 502)
            elif use_edits:
                while True:
                    if use_marker:
                        if marked_pil is None:
                            marked_pil = _draw_mask_marker(init_pil, mask_pil)
                        send_init = marked_pil
                        send_prompt = base_prompt + PROMPT_MARKER_NOTE
                        send_mask = None
                    else:
                        send_init, send_prompt, send_mask = init_pil, base_prompt, mask_pil
                    data: dict[str, Any] = {"model": mid, "prompt": send_prompt}
                    if size:
                        data["size"] = size
                    files: list[Any] = []
                    if send_init is not None:
                        buf = io.BytesIO()
                        send_init.save(buf, format="PNG")
                        files.append(("image", ("image.png", buf.getvalue(), "image/png")))
                    if send_mask is not None:
                        # OpenAI-семантика: правится прозрачная (alpha=0) область
                        alpha = _mask_edit_alpha(send_mask)
                        mask_out = Image.new("RGB", alpha.size, (0, 0, 0)).convert("RGBA")
                        mask_out.putalpha(alpha)
                        mbuf = io.BytesIO()
                        mask_out.save(mbuf, format="PNG")
                        files.append(("mask", ("mask.png", mbuf.getvalue(), "image/png")))
                    # референсные изображения — дополнительные входные картинки
                    for j, ref in enumerate(refs_pil):
                        rb = io.BytesIO()
                        ref.save(rb, format="PNG")
                        files.append(("image[]", (f"ref{j + 1}.png", rb.getvalue(), "image/png")))
                    resp = requests.post(
                        EDITS_URL,
                        headers={"Authorization": f"Bearer {key}"},
                        data=data,
                        files=files,
                        timeout=TIMEOUT_GENERATE,
                    )
                    try:
                        data_out = _upstream_json(resp)
                    except HTTPException as e:
                        raise _IRClientError(f"Generation failed: {e.detail}", e.status_code) from e
                    err = _api_error_message(data_out)
                    if not err:
                        break
                    # шлюз ImageRouter не принимает параметр mask (проверено 19.08
                    # на всех моделях правки) — подсвечиваем зону в картинке и повторяем
                    if mask_pil is not None and not use_marker and "mask" in err.lower():
                        use_marker = True
                        continue
                    raise _IRClientError(f"Generation failed: {err}", 502)
            else:
                body: dict[str, Any] = {"model": mid, "prompt": info["positive"]}
                if size:
                    body["size"] = size
                resp = requests.post(
                    GENERATIONS_URL, headers={"Authorization": f"Bearer {key}"}, json=body, timeout=TIMEOUT_GENERATE
                )
                try:
                    data_out = _upstream_json(resp)
                except HTTPException as e:
                    raise _IRClientError(f"Generation failed: {e.detail}", e.status_code) from e
                err = _api_error_message(data_out)
                if err:
                    raise _IRClientError(f"Generation failed: {err}", 502)
            for item in data_out.get("data", []) if isinstance(data_out, dict) else []:
                pil = _item_to_pil(item)
                if pil is None:
                    continue
                if use_edits and init_pil is not None and _is_echo(init_pil, pil):
                    raise _IRClientError(
                        f"The model '{mid}' returned the source image unedited — it is listed with an "
                        "image input but does not perform editing. "
                        "Please select an editing model.",
                        400,
                    )
                if is_edit and zone_full is not None:
                    pil = _apply_edit_mask(init_full, zone_full, pil, edit_bbox)
                metadata = json.dumps(
                    {
                        # edits-эндпоинт используется и для чистых референсов (без
                        # исходника) — метка режима должна это отражать
                        "generation_mode": "imagerouter-edit" if (is_edit or refs_pil) else "imagerouter",
                        "imagerouter_model": mid,
                        "positive_prompt": info["positive"],
                        "negative_prompt": info["negative"],
                        "width": info["width"],
                        "height": info["height"],
                        "source_image": info["init_image"],
                        # список референсов — в БД, чтобы не гадать по дампу,
                        # дошли ли они до запроса (диагностика 06.09);
                        # ref_details — тип и вес каждого (21.09)
                        "ref_images": info["references"],
                        "ref_details": info["ref_details"],
                    },
                    ensure_ascii=False,
                )
                dto = services.images.create(
                    image=pil,
                    image_origin=ResourceOrigin.INTERNAL,
                    image_category=ImageCategory.GENERAL,
                    board_id=info["board_id"],
                    metadata=metadata,
                )
                _studio_tag("image", dto.image_name, studio_user)
                saved.append(dto)
                print(f"[imagerouter] saved {dto.image_name}", flush=True)
                events.dispatch(
                    InvocationCompleteEvent(
                        queue_id=queue_id,
                        item_id=0,
                        batch_id=batch_id,
                        origin=origin,
                        destination=destination,
                        session_id=session_id,
                        invocation=SaveImageInvocation(
                            id="imagerouter_save", image=ImageField(image_name=dto.image_name)
                        ),
                        invocation_source_id="imagerouter_save",
                        result=ImageOutput.build(dto),
                    )
                )
        if not saved:
            raise _IRClientError("The generation service returned no images", 502)
    except Exception:
        ticker_stop.set()
        _inflight_dec(queue_id)
        try:
            events.dispatch(_status_event("failed", failed=1))
        except Exception:  # noqa: BLE001
            traceback.print_exc()
        raise
    ticker_stop.set()
    # уменьшаем ДО отправки статуса: перезапрошенный /status должен быть чистым
    _inflight_dec(queue_id)

    events.dispatch(_status_event("completed", completed=len(saved)))

    return {
        "queue_id": queue_id,
        "enqueued": runs,
        "requested": runs,
        "batch": batch,
        "priority": 0,
        "item_ids": [0] * len(saved),
    }


def _handle_upscale_generation(queue_id: str, payload: dict, studio_user: str | None = None) -> dict:
    """Апскейлинг через ImageRouter (вкладка Upscaling и quick-action из
    контекстного меню картинки): исходник + масштаб → edits-эндпоинт с
    серверным промптом, результат — в галерею. Проверка эха НЕ применяется:
    честный апскейл после даунскейла к размеру входа почти совпадает с ним
    (низкая средняя разница пикселей) и ловилась бы как «модель вернула
    исходник»."""
    from invokeai.app.api.dependencies import ApiDependencies
    from invokeai.app.invocations.fields import ImageField
    from invokeai.app.invocations.image import SaveImageInvocation
    from invokeai.app.invocations.primitives import ImageOutput
    from invokeai.app.services.events.events_common import (
        BatchEnqueuedEvent,
        InvocationCompleteEvent,
        InvocationStartedEvent,
    )
    from invokeai.app.services.image_records.image_records_common import ImageCategory, ResourceOrigin

    batch = payload.get("batch") or {}
    graph = batch.get("graph") or {}
    info = _extract_ir_info(batch)
    model_key = info.get("upscale_model_key")
    if not model_key:
        raise _IRClientError(
            "The upscaling model is not selected or unavailable. "
            "Please contact your administrator.",
            400,
        )
    mid = model_key[len(IR_UPSCALE_KEY_PREFIX):]
    if not info.get("init_image"):
        raise _IRClientError("No source image to upscale", 400)
    scale = float(info.get("upscale_scale") or 2)
    print(
        f"[imagerouter] upscale enqueue: model={mid} scale={scale} "
        f"mode={info.get('upscale_mode')} format={info.get('upscale_format')} "
        f"init={info['init_image']} creativity={info.get('upscale_creativity')} "
        f"structure={info.get('upscale_structure')}",
        flush=True,
    )
    key = effective_key(studio_user)
    if not key:
        raise _IRClientError(
            ("Персональный токен ImageRouter не задан — обратитесь к администратору."
             if studio_user and studio_user != "admin-local" else
             "Generation service is not configured: no API key. "
             "Please contact your administrator."),
            401,
        )
    if not _supports_image_input(mid):
        raise _IRClientError(
            f"The model '{mid}' does not accept an image as input and cannot upscale. "
            "Administrator: remove it from the upscaling model list.",
            400,
        )

    runs = max(1, min(int(batch.get("runs") or 1), MAX_RUNS))
    services = ApiDependencies.invoker.services
    dispatch, _status_event, _progress_event, batch_id, origin, destination, session_id = (
        _queue_event_factories(queue_id, batch, graph, services)
    )
    events = services.events

    events.dispatch(
        BatchEnqueuedEvent(
            queue_id=queue_id, batch_id=batch_id, enqueued=runs, requested=runs, priority=0, origin=origin
        )
    )
    _studio_tag("batch", batch_id, studio_user)

    _inflight_inc(queue_id)
    events.dispatch(_status_event("in_progress"))
    events.dispatch(
        InvocationStartedEvent(
            queue_id=queue_id,
            item_id=0,
            batch_id=batch_id,
            origin=origin,
            destination=destination,
            session_id=session_id,
            invocation=SaveImageInvocation(id="imagerouter_save"),
            invocation_source_id="imagerouter_save",
        )
    )
    ticker_stop = threading.Event()
    run_state = {"run": 0}

    def _ticker() -> None:
        t0 = time.time()
        while not ticker_stop.wait(PROGRESS_TICK):
            try:
                events.dispatch(
                    _progress_event(f"Upscaling · {mid} · {run_state['run']}/{runs} · {int(time.time() - t0)}s")
                )
            except Exception:  # noqa: BLE001
                break

    threading.Thread(target=_ticker, daemon=True, name="ir-upscale-progress").start()

    saved: list[Any] = []
    try:
        try:
            init_pil = services.images.get_pil_image(info["init_image"])
        except Exception as e:  # noqa: BLE001
            raise _IRClientError(f"Failed to load source image ({e})", 500) from e
        # Режим из селектора вкладки первичнее слайдерного scale: у моделей
        # с явными размерами берём точный размер режима, у факторных — их
        # честный множитель (-2x игнорирует больший scale).
        scale, size, size_label, fmt = _upscale_request_params(mid, info, init_pil.width, init_pil.height)
        prompt = _upscale_prompt(
            None if size_label else scale,
            info.get("upscale_creativity"),
            info.get("upscale_structure"),
            size_label,
        )
        for i in range(runs):
            run_state["run"] = i + 1
            body: dict[str, Any] = {
                "model": mid,
                "prompt": prompt,
                "image": [_pil_to_durl(init_pil)],
                "output_format": fmt,
            }
            if size:
                body["size"] = size
            resp = requests.post(
                EDITS_URL,
                headers={"Authorization": f"Bearer {key}"},
                json=body,
                timeout=TIMEOUT_GENERATE,
            )
            print(f"[imagerouter] upscale edits json -> HTTP {resp.status_code}", flush=True)
            try:
                data_out = _upstream_json(resp)
            except HTTPException as e:
                raise _IRClientError(f"Generation failed: {e.detail}", e.status_code) from e
            err = _api_error_message(data_out)
            if err:
                raise _IRClientError(f"Generation failed: {err}", 502)
            for item in data_out.get("data", []) if isinstance(data_out, dict) else []:
                pil = _item_to_pil(item)
                if pil is None:
                    continue
                metadata = json.dumps(
                    {
                        "generation_mode": "imagerouter-upscale",
                        "imagerouter_model": mid,
                        "upscale_scale": scale,
                        "upscale_requested_size": size,
                        "source_image": info["init_image"],
                    },
                    ensure_ascii=False,
                )
                dto = services.images.create(
                    image=pil,
                    image_origin=ResourceOrigin.INTERNAL,
                    image_category=ImageCategory.GENERAL,
                    board_id=info["board_id"],
                    metadata=metadata,
                )
                _studio_tag("image", dto.image_name, studio_user)
                saved.append(dto)
                print(f"[imagerouter] upscale saved {dto.image_name}", flush=True)
                events.dispatch(
                    InvocationCompleteEvent(
                        queue_id=queue_id,
                        item_id=0,
                        batch_id=batch_id,
                        origin=origin,
                        destination=destination,
                        session_id=session_id,
                        invocation=SaveImageInvocation(
                            id="imagerouter_save", image=ImageField(image_name=dto.image_name)
                        ),
                        invocation_source_id="imagerouter_save",
                        result=ImageOutput.build(dto),
                    )
                )
        if not saved:
            raise _IRClientError("The generation service returned no images", 502)
    except Exception:
        ticker_stop.set()
        _inflight_dec(queue_id)
        try:
            events.dispatch(_status_event("failed", failed=1))
        except Exception:  # noqa: BLE001
            traceback.print_exc()
        raise
    ticker_stop.set()
    _inflight_dec(queue_id)

    events.dispatch(_status_event("completed", completed=len(saved)))

    return {
        "queue_id": queue_id,
        "enqueued": runs,
        "requested": runs,
        "batch": batch,
        "priority": 0,
        "item_ids": [0] * len(saved),
    }


# --- ASGI-мидлварь ---

_ENQUEUE_RE = re.compile(r"^/api/v1/queue/[^/]+/enqueue_batch$")
_QUEUE_STATUS_RE = re.compile(r"^/api/v1/queue/[^/]+/status$")


def _queue_status_mutator(n: int):
    """Пока идёт облачная генерация, очередь для UI не пустая: in_progress + n."""

    def mutate(data: Any) -> None:
        q = data.get("queue") if isinstance(data, dict) else None
        if isinstance(q, dict):
            q["in_progress"] = int(q.get("in_progress") or 0) + n
            q["total"] = int(q.get("total") or 0) + n

    return mutate


async def _read_body(receive) -> bytes:
    chunks = []
    while True:
        message = await receive()
        if message["type"] != "http.request":
            break
        chunks.append(message.get("body", b""))
        if not message.get("more_body", False):
            break
    return b"".join(chunks)


def _replay_receive(body: bytes):
    """Новый receive, отдающий сохранённое тело запроса нижележащему приложению."""
    sent = False

    async def receive():
        nonlocal sent
        if sent:
            await asyncio.sleep(3600)
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    return receive


def _ir_error_body(message: str) -> dict:
    """Тело ошибки для enqueue_batch в формате, который показывает UI.

    Тост «Не удалось поставить пакет в очередь» разбирает только 422-ответы
    вида detail=[{loc,msg,type}] (zod-схема в бандле); любой другой статус
    или форма отображаются как «Неизвестная ошибка».
    """
    return {"detail": [{"loc": [], "msg": message, "type": "value_error"}]}


def _studio_user_from_scope(scope) -> "str | None":
    """Пользователь студии, инжектированный SiteAuthMiddleware (sso-режим)."""
    for k, v in scope.get("headers", []):
        if k == b"x-studio-user":
            return v.decode("latin-1") or None
    return None


def _studio_tag(kind: str, key, user: "str | None") -> None:
    """Записать владение в оверлей-БД; без деплоя studio_store — молча пропустить."""
    if not user or not key:
        return
    try:
        from invokeai.app.api.routers import studio_store
        studio_store.tag(kind, str(key), user)
    except Exception:
        pass


def _studio_store():
    try:
        from invokeai.app.api.routers import studio_store
    except ImportError:  # дерево проекта (тесты)
        import studio_store
    return studio_store


def _gen_log(studio_user, kind, model, status, images=0, cost_usd=None,
             duration_s=0.0, error=None) -> None:
    """Журнал генераций для админ-панели (кто/что/деньги/время/ошибка).
    Любой сбой записи глотается — учёт не должен ломать генерацию."""
    if not studio_user:
        return
    try:
        _studio_store().log_generation(studio_user, kind, model, status,
                                       images, cost_usd, duration_s, error)
    except Exception:
        pass


def _catalog_price(mid: str) -> Optional[float]:
    """Оценка цены картинки по каталогу ImageRouter (~$/img). Читает ТОЛЬКО
    кэш: журнал пишется из async-мидлвари, и сетевой запрос здесь на срок
    до TIMEOUT_SHORT замораживал бы event loop всего сервера. Каталога в
    кэше нет (холодный старт) -> None («—» в панели); кэш греется любым
    запросом списка моделей (пикер UI делает это постоянно)."""
    try:
        for m in _ir_models_cache.get("items") or []:
            if m.get("id") == mid:
                return _avg_price(m)
    except Exception:
        pass
    return None


def _gen_log_entry(studio_user, info: dict, status: str, images: int,
                   duration_s: float, error=None) -> None:
    """Запись журнала по info перехваченного enqueue_batch: kind/model из
    графа, стоимость — цена каталога × картинок (только успех)."""
    if not studio_user:
        return
    key = info.get("upscale_model_key") if info.get("is_upscale") else info.get("model_key")
    kind = "upscale" if info.get("is_upscale") else (info.get("mode") or "txt2img")
    mid = str(key or "")
    if mid.startswith(IR_UPSCALE_KEY_PREFIX):
        mid = mid[len(IR_UPSCALE_KEY_PREFIX):]
    elif mid.startswith(IR_KEY_PREFIX):
        mid = mid[len(IR_KEY_PREFIX):]
    cost = None
    if status == "ok" and images and mid:
        price = _catalog_price(mid)
        if price is not None:
            cost = round(price * images, 6)
    _gen_log(studio_user, kind, mid, status, images, cost, duration_s, error)


def _personal_token(studio_user: "str | None") -> "str | None":
    """Персональный токен ImageRouter аккаунта (users-режим); None — нет аккаунта."""
    if not studio_user or studio_user == "admin-local":
        return None
    try:
        u = _studio_store().get_user(studio_user)
        if u:
            return (u.get("ir_token") or "").strip() or None
    except Exception:  # noqa: BLE001
        pass
    return None


def effective_key(studio_user: "str | None") -> Optional[str]:
    """Ключ ImageRouter для запроса от имени пользователя студии.

    Персональный токен приоритетен. Обычному пользователю (role=user) без
    токена глобальный ключ НЕ подставляется — иначе тратятся кредиты
    владельца; генерация завершится понятной ошибкой. admin / admin-local
    без своего токена работают на глобальном ключе."""
    tok = _personal_token(studio_user)
    if tok:
        return tok
    if studio_user and studio_user != "admin-local":
        try:
            if (_studio_store().effective_role(studio_user) or "user") != "admin":
                return None
        except Exception:  # noqa: BLE001 — БД недоступна: работаем на глобальном
            pass
    return _load_key()


def user_for_session(session_id: str) -> "str | None":
    """Владелец сессии графа (тегируется на enqueue): облачные ноды (Ask AI,
    Prompt Enhancer) выполняются вне HTTP-контекста и находят пользователя
    по session_id."""
    if not session_id:
        return None
    try:
        return _studio_store().owner("session", session_id)
    except Exception:
        return None


def _tag_session_owner(payload, studio_user: "str | None") -> None:
    """Запомнить владельца сессии (graph.id = session_id) на enqueue_batch."""
    if not studio_user or not isinstance(payload, dict):
        return
    try:
        graph = (payload.get("batch") or {}).get("graph") or {}
        sid = str(graph.get("id") or "")
        if sid:
            _studio_tag("session", sid, studio_user)
    except Exception:
        pass


class ImageRouterCanvasMiddleware:
    """Добавляет модели ImageRouter в /api/v2/models и перехватывает их генерацию."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")
        method = scope.get("method", "")

        if method == "GET" and path.rstrip("/") == "/api/v2/models":
            await self._models_list(scope, receive, send)
            return

        if path.startswith("/api/v2/models/i/") and method in ("GET", "DELETE"):
            key = unquote(path[len("/api/v2/models/i/"):].rstrip("/"))
            if key.startswith(IR_UPSCALE_KEY_PREFIX):
                # spandrel-фейки моделей апскейлинга (роль отличается от main)
                if method == "GET":
                    m = _ir_model_by_id(key[len(IR_UPSCALE_KEY_PREFIX):])
                    if m:
                        await self._send_json(send, _ir_upscale_fake_config(m))
                        return
                else:  # DELETE
                    await self._send_json(
                        send,
                        {"detail": "Cloud models are provided via API and cannot be deleted locally."},
                        status=400,
                    )
                    return
            elif key.startswith(IR_KEY_PREFIX):
                if method == "GET":
                    if key == TILE_CONTROLNET_FAKE_KEY:
                        await self._send_json(send, _ir_tile_fake())
                        return
                    m = _ir_model_by_id(key[len(IR_KEY_PREFIX):])
                    if m:
                        await self._send_json(send, _ir_fake_config(m))
                        return
                    if key == IPADAPTER_FAKE_KEY:
                        await self._send_json(send, _ir_ipadapter_fake())
                        return
                else:  # DELETE
                    await self._send_json(
                        send,
                        {"detail": "Cloud models are provided via API and cannot be deleted locally."},
                        status=400,
                    )
                    return
            await self.app(scope, receive, send)
            return

        if method == "GET" and _QUEUE_STATUS_RE.match(path):
            # во время облачной генерации отчёт очереди должен показывать
            # «в работе», иначе UI стирает прогресс (см. _INFLIGHT выше)
            n = _inflight_count(path.split("/")[4])
            if n:
                await self._proxy_json(scope, receive, send, _queue_status_mutator(n))
                return
            await self.app(scope, receive, send)
            return

        if method == "POST" and _ENQUEUE_RE.match(path):
            body = await _read_body(receive)
            try:
                payload = json.loads(body) if body else {}
            except ValueError:
                payload = None
            batch = (payload or {}).get("batch") or {}
            info = _extract_ir_info(batch)
            # граф апскейлинга проверяем ПЕРВЫМ: во вкладке Upscaling в графе есть
            # и main-модель (sdxl_loader с imagerouter/-ключом), а quick-action
            # контекстного меню строит граф вовсе без main-модели
            handler = _handle_upscale_generation if info.get("is_upscale") else (
                _handle_canvas_generation if info["model_key"] else None
            )
            if handler is not None:
                # /api/v1/queue/{queue_id}/enqueue_batch -> queue_id в пятом сегменте
                queue_id = path.split("/")[4]
                # диагностический дамп последнего перехваченного графа
                try:
                    Path(get_config().root_path, "_ir_last_graph.json").write_text(
                        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8"
                    )
                except Exception:
                    pass
                studio_user = _studio_user_from_scope(scope)
                _tag_session_owner(payload, studio_user)
                t0 = time.monotonic()
                try:
                    result = await asyncio.to_thread(handler, queue_id, payload, studio_user)
                except _IRClientError as e:
                    # 06.09: ошибки улетали тостом в UI, не оставляя следа в
                    # ir_server.log — при разборе «что реально ушло» приходилось
                    # гадать; теперь каждое падение пишется в лог
                    print(f"[imagerouter] FAILED: {e}", flush=True)
                    _gen_log_entry(studio_user, info, "error", 0,
                                   time.monotonic() - t0, str(e))
                    await self._send_json(send, _ir_error_body(str(e)), status=422)
                    return
                except Exception as e:  # noqa: BLE001
                    traceback.print_exc()
                    _gen_log_entry(studio_user, info, "error", 0,
                                   time.monotonic() - t0, f"{e}")
                    await self._send_json(send, _ir_error_body(f"ImageRouter: {e}"), status=422)
                    return
                # журнал генераций админ-панели: картинок = длина item_ids
                _gen_log_entry(studio_user, info, "ok",
                               len((result or {}).get("item_ids") or []),
                               time.monotonic() - t0)
                await self._send_json(send, result)
                return
            # сквозной граф (облачные ноды Ask AI / Prompt Enhancer): запоминаем
            # владельца сессии — ноды выполняются вне HTTP-контекста и берут
            # пользователя (и персональный ключ IR) по session_id
            _tag_session_owner(payload, _studio_user_from_scope(scope))
            await self.app(scope, _replay_receive(body), send)
            return

        await self.app(scope, receive, send)

    async def _models_list(self, scope, receive, send) -> None:
        """Прокси ответа /api/v2/models с добавлением моделей ImageRouter."""
        await self._proxy_json(scope, receive, send, _add_ir_models)

    async def _proxy_json(self, scope, receive, send, mutator) -> None:
        """Проксирует ответ приложения и правит JSON-тело через mutator(data)."""
        status_code, headers, chunks = 200, [], []

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                nonlocal status_code, headers
                status_code = message["status"]
                headers = list(message.get("headers", []))
            elif message["type"] == "http.response.body":
                chunks.append(message.get("body", b""))

        await self.app(scope, receive, send_wrapper)

        raw = b"".join(chunks)
        try:
            data = json.loads(raw or b"{}")
            mutator(data)
            raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
        except Exception:
            traceback.print_exc()
        headers = [(k, v) for k, v in headers if k.lower() != b"content-length"]
        headers.append((b"content-length", str(len(raw)).encode("latin-1")))
        await send({"type": "http.response.start", "status": status_code, "headers": headers})
        await send({"type": "http.response.body", "body": raw})

    @staticmethod
    async def _send_json(send, data: Any, status: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        headers = [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode("latin-1"))]
        await send({"type": "http.response.start", "status": status, "headers": headers})
        await send({"type": "http.response.body", "body": body})
