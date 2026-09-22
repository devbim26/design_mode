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
    # Как _supports_image_input роутера: явный пустой input_modalities —
    # вход-image нет (text-only), «image» в списке — есть. (Отклонение от
    # брифа: хвост `or not inputs` противоречил тесту — пустой [] считался
    # image-ok и edit не отсекал text-модель.)
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


# --- инвокции ---

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
