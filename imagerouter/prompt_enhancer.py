# -*- coding: utf-8 -*-
"""DevBIM Prompt Enhancer: инвокации улучшения промта через VLM ImageRouter.

Реализует серверные узлы для штатного UI «Prompt Expansion» InvokeAI 6.2
(Enterprise-узлы claude_expand_prompt / claude_analyze_image есть во
фронтенд-бандле, в OSS-пакете отсутствуют). Деплой: setup_imagerouter.py
копирует файл в invokeai/app/invocations/devbim_prompt_enhancer.py —
пакет подхватывает сам (app/invocations/__init__.py строит __all__ из
*.py каталога, services/shared/graph.py делает star-import и декораторы
@invocation регистрируют узлы в реестре).

Ключ и модель читаются лениво из роутера (единый источник, .env):
    IMAGEROUTER_API_KEY    — ключ ImageRouter
    PROMPT_ENHANCER_MODEL  — VLM (по умолчанию zai/glm-5.3-flash)
"""
# ВНИМАНИЕ: НЕ добавлять `from __future__ import annotations` — PEP 563
# превращает `-> StringOutput` в строку, run_app.py падает на
# output_annotation.__name__ ('str' has no attribute '__name__'),
# сервер не стартует (get_output_annotation возвращает строку).
import base64
import io
import re
from typing import Any, Optional

import requests
from invokeai.app.invocations.baseinvocation import BaseInvocation, invocation
from invokeai.app.invocations.fields import ImageField, InputField
from invokeai.app.invocations.primitives import StringOutput
from invokeai.app.services.shared.invocation_context import InvocationContext

MAX_IMAGES = 4  # референсов максимум (контекст VLM и стоимость)
MAX_SIDE = 1024  # даунскейл длинной стороны
JPEG_QUALITY = 85
MAX_TOKENS = 1500  # reasoning-модели тратят лимит до начала ответа (грабля glm-5.3-flash @300)
TEMPERATURE = 0.7
TIMEOUT_S = 120

SYSTEM_ENHANCE = (
    "You are a prompt engineer for architectural visualization and photorealistic "
    "rendering. The user provides a draft prompt (any language) and optional reference "
    "images. Rewrite the draft into ONE vivid, detailed English prompt for an "
    "image-generation model: keep the user's intent and every named detail, add "
    "specifics about architecture, materials, lighting, camera, composition and "
    "atmosphere. If reference images are attached, follow their style and content and "
    "do not contradict them. If the draft is empty, write a prompt that describes the "
    "reference images. Output ONLY the final prompt - no preamble, no quotes, no "
    "markdown, no explanations. Aim for 50-120 words."
)

SYSTEM_ANALYZE = (
    "You describe images as generation prompts. Look at the image and write ONE "
    "detailed English prompt for an image-generation model that would recreate it: "
    "subject, architecture and materials, colors, lighting, camera angle and "
    "atmosphere. Output ONLY the final prompt - no preamble, no quotes, no markdown. "
    "Aim for 50-120 words."
)


def prepare_image(pil: Any) -> str:
    """PIL-картинка -> data URL (JPEG): даунскейл до MAX_SIDE, альфа на белый."""
    from PIL import Image

    img = pil.convert("RGBA")
    if img.width > MAX_SIDE or img.height > MAX_SIDE:
        img.thumbnail((MAX_SIDE, MAX_SIDE))
    bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
    img = Image.alpha_composite(bg, img).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=JPEG_QUALITY)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def sanitize(text: Optional[str]) -> str:
    """Ответ VLM -> чистый промт: без ограждений/кавычек, пробелы схлопнуты."""
    t = (text or "").strip()
    t = re.sub(r"^```[a-zA-Z]*\s*", "", t)
    t = re.sub(r"\s*```$", "", t)
    t = t.strip().strip('"').strip("'").strip()
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def user_content(prompt: str, image_urls: list) -> list:
    parts: list = []
    p = (prompt or "").strip()
    if p:
        parts.append({"type": "text", "text": f"Draft prompt: {p}" if image_urls else p})
    else:
        parts.append({"type": "text", "text": "No draft prompt; use the attached reference images."})
    for u in image_urls:
        parts.append({"type": "image_url", "image_url": {"url": u}})
    return parts


def build_body(model: str, system: str, prompt: str, image_urls: list) -> dict:
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user_content(prompt, image_urls)},
        ],
        "max_tokens": MAX_TOKENS,
        "temperature": TEMPERATURE,
    }


def call_vlm(
    system: str, prompt: str, image_urls: list, key: Optional[str] = None, model: Optional[str] = None
) -> str:
    """Запрос в ImageRouter chat completions. Ошибки — исключениями: элемент
    очереди честно падает, UI показывает штатный тост «Prompt expansion failed»."""
    chat_url = "https://api.imagerouter.io/v1/openai/chat/completions"
    if key is None or model is None:
        from invokeai.app.api.routers.imagerouter import (
            CHAT_COMPLETIONS_URL,
            _enhancer_model,
            _load_key,
        )

        chat_url = CHAT_COMPLETIONS_URL
        key = key or _load_key()
        model = model or _enhancer_model()
    if not key:
        raise ValueError("Generation service is not configured: no API key. Please contact your administrator.")
    resp = requests.post(
        chat_url,
        headers={"Authorization": f"Bearer {key}"},
        json=build_body(model, system, prompt, image_urls),
        timeout=TIMEOUT_S,
    )
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
        raise ValueError(f"Generation service error: {msg or f'HTTP {resp.status_code}'}")
    if isinstance(data, dict):
        err = data.get("error")
        if isinstance(err, dict) and err.get("message"):
            raise ValueError(f"Generation service error: {err['message']}")
    choices = data.get("choices") if isinstance(data, dict) else None
    content = ""
    if choices:
        content = ((choices[0].get("message") or {}).get("content")) or ""
    text = sanitize(content)
    if not text:
        raise ValueError("The assistant model returned an empty response. Please try again.")
    return text


@invocation(
    "claude_expand_prompt",
    title="Enhance Prompt (DevBIM)",
    tags=["prompt", "devbim", "imagerouter"],
    category="prompt",
    version="1.0.0",
    use_cache=False,
)
class EnhancePromptInvocation(BaseInvocation):
    """Улучшает промт (и референсные изображения) через VLM ImageRouter."""

    prompt: str = InputField(default="", description="Черновик промта (любой язык)")
    model_architecture: str = InputField(
        default="tag_based",
        description="Совместимость фронтенда (tag_based/sentence_based); не используется",
    )
    images: list[ImageField] = InputField(default=[], description="Референсные изображения")

    def invoke(self, context: InvocationContext) -> StringOutput:
        urls = [
            prepare_image(context.images.get_pil(f.image_name))
            for f in (self.images or [])[:MAX_IMAGES]
        ]
        if not (self.prompt or "").strip() and not urls:
            raise ValueError("Enter a prompt or attach a reference image")
        return StringOutput(value=call_vlm(SYSTEM_ENHANCE, self.prompt, urls))


@invocation(
    "claude_analyze_image",
    title="Analyze Image (DevBIM)",
    tags=["prompt", "devbim", "imagerouter"],
    category="prompt",
    version="1.0.0",
    use_cache=False,
)
class AnalyzeImageInvocation(BaseInvocation):
    """Описывает изображение как промт через VLM ImageRouter."""

    image: ImageField = InputField(description="Изображение для анализа")
    model_architecture: str = InputField(
        default="tag_based",
        description="Совместимость фронтенда (tag_based/sentence_based); не используется",
    )

    def invoke(self, context: InvocationContext) -> StringOutput:
        url = prepare_image(context.images.get_pil(self.image.image_name))
        return StringOutput(value=call_vlm(SYSTEM_ANALYZE, "", [url]))
