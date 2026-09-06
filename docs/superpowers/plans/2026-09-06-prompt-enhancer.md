# Prompt Enhancer — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Голубая кнопка «Prompt Enhance» справа от жёлтой Generate отправляет текущий промт + Reference Images в VLM ImageRouter; результат — в редактируемом оверлее поверх промпт-бокса (Replace / Insert / Discard).

**Architecture:** Штатный клиентский флоу Prompt Expansion (граф `claude_expand_prompt` → реальная очередь → `string_output`) + наши серверные инвокации с этими именами, ходящие в `/v1/openai/chat/completions`. Три идемпотентных патча App-бандла: кнопка у Generate, референсы в графе, редактируемый оверлей. Спека: `docs/superpowers/specs/2026-09-06-prompt-enhancer-design.md`.

**Tech Stack:** InvokeAI 6.2.0 (pip, venv), FastAPI/pydantic (инвокации), requests, React-бандлы (минифицированный JS-патчинг), plain-assert тесты.

## Global Constraints

- InvokeAI 6.2.0 зафиксирован; пути: `venv/Lib/site-packages/invokeai/` (переменная `SP` в setup_imagerouter.py), dist — `SP/invokeai/frontend/web/dist`.
- Файлы в `venv/.../site-packages` руками НЕ править — только через `setup_imagerouter.py` (правки в `imagerouter/` проекта + перезапуск скрипта).
- Все патчи идемпотентны, бэкапы — общий суффикс `*.imagerouter-bak`.
- После каждого JS-патча обязательна проверка парсинга: `node -e "import('file:///<бандл>').catch(e=>console.log(e.message))"` — допустима ТОЛЬКО рантайм-ошибка (`document is not defined`), не SyntaxError.
- `PYTHONUTF8=1` в любых bat; тесты запускать `venv\Scripts\python.exe tests\<имя>.py` из корня проекта.
- Секреты (`.env`, `companies/*`, `companies.json`, ключи) в git НЕ коммитить; `git add` — только конкретные файлы задачи.
- В рабочем дереве есть чужие незакоммиченные изменения (`HANDOFF.md`, `setup_imagerouter.py` — завершённая фича п.21 «кнопки очереди»); их коммитим отдельным коммитом в Task 1, до начала своей работы.
- Сервер перезапускать только `_restart_server.ps1` (WMI); фоновые процессы агентских сессий умирают вместе с сессией.
- VLM по умолчанию `zai/glm-5.3-flash`, override `.env` `PROMPT_ENHANCER_MODEL`; вывод промта всегда на английском.

---

### Task 1: Ветка, коммит чужой работы, роутер — модель энхансера и URL чата

**Files:**
- Modify: `imagerouter/imagerouter_router.py` (блок констант после строки 64 `EDITS_URL = ...`; функция рядом с `_load_key`; эндпоинт `get_status`)
- Test: `tests/test_prompt_enhancer.py` (создать)

**Interfaces:**
- Consumes: `_ensure_env()` из imagerouter_router.py (уже есть).
- Produces: `CHAT_COMPLETIONS_URL: str`, `DEFAULT_ENHANCER_MODEL = "zai/glm-5.3-flash"`, `_enhancer_model() -> str` — их импортирует (лениво) модуль инвокаций из Task 2 и живой smoke-тест.

- [ ] **Step 1: Создать ветку и закоммитить чужую завершённую работу (п.21)**

```bash
cd "C:\Users\Lenovo\Desktop\проект SOFT_2\Дизайн\InvokeAI\InvokeAI"
git checkout -b feature/prompt-enhancer
git add HANDOFF.md setup_imagerouter.py
git commit -m "feat(queue): кнопки локальной очереди убраны у Generate (п.21 HANDOFF, завершено 05.09)"
```

Ожидание: коммит создан; `git status` чист (кроме untracked, если есть).

- [ ] **Step 2: Написать failing-тест**

Создать `tests/test_prompt_enhancer.py`:

```python
# -*- coding: utf-8 -*-
"""Тесты Prompt Enhancer: роутер (модель/URL), модуль инвокаций, патчи бандлов.

Запуск: venv\\Scripts\\python.exe tests\\test_prompt_enhancer.py
"""
import importlib.util
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _load_router():
    """imagerouter/ — не пакет; грузим imagerouter_router.py по пути."""
    spec = importlib.util.spec_from_file_location(
        "ir_router", ROOT / "imagerouter" / "imagerouter_router.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_router_enhancer_model():
    ir = _load_router()
    assert ir.CHAT_COMPLETIONS_URL == (
        "https://api.imagerouter.io/v1/openai/chat/completions"
    ), ir.CHAT_COMPLETIONS_URL
    assert ir.DEFAULT_ENHANCER_MODEL == "zai/glm-5.3-flash"
    old = os.environ.pop("PROMPT_ENHANCER_MODEL", None)
    try:
        assert ir._enhancer_model() == "zai/glm-5.3-flash"  # дефолт
        os.environ["PROMPT_ENHANCER_MODEL"] = "moonshot/kimi-k3"
        assert ir._enhancer_model() == "moonshot/kimi-k3"  # override
        os.environ["PROMPT_ENHANCER_MODEL"] = "   "
        assert ir._enhancer_model() == "zai/glm-5.3-flash"  # пусто -> дефолт
    finally:
        if old is None:
            os.environ.pop("PROMPT_ENHANCER_MODEL", None)
        else:
            os.environ["PROMPT_ENHANCER_MODEL"] = old
    print("OK: роутер — URL чата и модель энхансера")


if __name__ == "__main__":
    test_router_enhancer_model()
```

- [ ] **Step 3: Запустить — убедиться, что падает**

Run: `venv\Scripts\python.exe tests\test_prompt_enhancer.py`
Expected: FAIL — `AttributeError: ... has no attribute 'CHAT_COMPLETIONS_URL'`.

- [ ] **Step 4: Реализовать в `imagerouter/imagerouter_router.py`**

После строки `EDITS_URL = f"{IR_BASE}/v1/openai/images/edits"` (строка 64) добавить:

```python
CHAT_COMPLETIONS_URL = f"{IR_BASE}/v1/openai/chat/completions"

# VLM для улучшения промтов (Prompt Enhancer); override — .env PROMPT_ENHANCER_MODEL
DEFAULT_ENHANCER_MODEL = "zai/glm-5.3-flash"
```

Рядом с `_load_key()` (после него, ~строка 160) добавить:

```python
def _enhancer_model() -> str:
    _ensure_env()
    return (os.environ.get("PROMPT_ENHANCER_MODEL") or "").strip() or DEFAULT_ENHANCER_MODEL
```

В `get_status()` (строки 202–209) добавить поле — итоговый вид:

```python
@imagerouter_router.get("/status")
def get_status() -> dict:
    key = _load_key()
    return {
        "has_key": key is not None,
        "hint": f"...{key[-4:]}" if key else None,
        "key_source": "env" if _env_key() else ("file" if key else None),
        "prompt_enhancer_model": _enhancer_model(),
    }
```

- [ ] **Step 5: Запустить тест — PASS**

Run: `venv\Scripts\python.exe tests\test_prompt_enhancer.py`
Expected: `OK: роутер — URL чата и модель энхансера`

- [ ] **Step 6: Commit**

```bash
git add imagerouter/imagerouter_router.py tests/test_prompt_enhancer.py
git commit -m "feat(prompt-enhancer): роутер — URL chat completions и модель VLM из .env"
```

---

### Task 2: Модуль инвокаций `imagerouter/prompt_enhancer.py`

**Files:**
- Create: `imagerouter/prompt_enhancer.py`
- Test: `tests/test_prompt_enhancer.py` (дополнить)

**Interfaces:**
- Consumes: из Task 1 — `_load_key()`, `_enhancer_model()`, `CHAT_COMPLETIONS_URL` (ленивый импорт `invokeai.app.api.routers.imagerouter` — путь существует только в деплое).
- Produces: чистые функции `prepare_image(pil) -> str` (data URL JPEG), `sanitize(text) -> str`, `user_content(prompt, image_urls) -> list`, `build_body(model, system, prompt, image_urls) -> dict`, `call_vlm(system, prompt, image_urls, key=None, model=None) -> str`; константы `SYSTEM_ENHANCE`, `SYSTEM_ANALYZE`, `MAX_IMAGES=4`; классы `EnhancePromptInvocation` (тип `claude_expand_prompt`, поля `prompt: str`, `model_architecture: str`, `images: list[ImageField]`) и `AnalyzeImageInvocation` (тип `claude_analyze_image`, поля `image: ImageField`, `model_architecture: str`).

- [ ] **Step 1: Дописать failing-тесты**

В `tests/test_prompt_enhancer.py` перед `if __name__ == "__main__":` добавить:

```python
def _load_enhancer_mod():
    spec = importlib.util.spec_from_file_location(
        "devbim_prompt_enhancer", ROOT / "imagerouter" / "prompt_enhancer.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_sanitize():
    m = _load_enhancer_mod()
    assert m.sanitize("```json\n{\"p\": 1}\n```") == '{"p": 1}'
    assert m.sanitize('"quoted prompt"') == "quoted prompt"
    assert m.sanitize("  multiple   spaces\tand\ttabs  ") == "multiple spaces and tabs"
    assert m.sanitize("") == ""
    assert m.sanitize(None) == ""
    print("OK: sanitize")


def test_prepare_image():
    from PIL import Image

    m = _load_enhancer_mod()
    big = Image.new("RGBA", (3000, 1200), (255, 0, 0, 128))  # альфа + больше MAX_SIDE
    url = m.prepare_image(big)
    assert url.startswith("data:image/jpeg;base64,/")
    img = Image.open(__import__("io").BytesIO(__import__("base64").b64decode(url.split(",", 1)[1])))
    assert max(img.size) <= 1024
    assert img.mode == "RGB"
    px = img.getpixel((5, 5))
    assert px[0] > 200 and px[1] < 100  # альфа склеена с белым: светлый красный
    print("OK: prepare_image")


def test_build_body():
    m = _load_enhancer_mod()
    body = m.build_body("mm", m.SYSTEM_ENHANCE, "домик", ["data:image/jpeg;base64,QQ"])
    assert body["model"] == "mm"
    assert body["max_tokens"] == 1500 and body["temperature"] == 0.7
    sysmsg, usermsg = body["messages"]
    assert sysmsg["role"] == "system" and sysmsg["content"] == m.SYSTEM_ENHANCE
    kinds = [p["type"] for p in usermsg["content"]]
    assert kinds == ["text", "image_url"], kinds
    assert usermsg["content"][0]["text"] == "Draft prompt: домик"
    assert usermsg["content"][1]["image_url"]["url"].startswith("data:")
    empty = m.user_content("", [])
    assert empty[0]["text"] == "No draft prompt; use the attached reference images."
    print("OK: build_body / user_content")
```

и в `__main__` добавить вызовы:

```python
if __name__ == "__main__":
    test_router_enhancer_model()
    test_sanitize()
    test_prepare_image()
    test_build_body()
```

- [ ] **Step 2: Запустить — FAIL**

Run: `venv\Scripts\python.exe tests\test_prompt_enhancer.py`
Expected: FAIL — `FileNotFoundError` на `imager/prompt_enhancer.py`.

- [ ] **Step 3: Создать `imagerouter/prompt_enhancer.py`**

```python
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
from __future__ import annotations

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
        raise ValueError("API-ключ ImageRouter не задан (.env: IMAGEROUTER_API_KEY)")
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
        raise ValueError(f"ImageRouter: {msg or f'HTTP {resp.status_code}'}")
    if isinstance(data, dict):
        err = data.get("error")
        if isinstance(err, dict) and err.get("message"):
            raise ValueError(f"ImageRouter: {err['message']}")
    choices = data.get("choices") if isinstance(data, dict) else None
    content = ""
    if choices:
        content = ((choices[0].get("message") or {}).get("content")) or ""
    text = sanitize(content)
    if not text:
        raise ValueError(
            "VLM вернула пустой ответ (попробуйте другую модель в PROMPT_ENHANCER_MODEL)"
        )
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
            raise ValueError("Введите промт или приложите референсное изображение")
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
```

- [ ] **Step 4: Запустить тесты — PASS**

Run: `venv\Scripts\python.exe tests\test_prompt_enhancer.py`
Expected: 4 строки `OK: ...`, без ошибок.

- [ ] **Step 5: Живой smoke-тест (пропуск без ключа)**

Добавить в тест-файл:

```python
def test_live_smoke():
    import json

    import requests as rq

    key_file = ROOT / "data" / "imagerouter.json"
    env_file = ROOT / ".env"
    key = None
    if key_file.exists():
        try:
            key = json.loads(key_file.read_text(encoding="utf-8")).get("api_key")
        except Exception:
            key = None
    if not key and env_file.exists():
        for line in env_file.read_text(encoding="utf-8-sig").splitlines():
            if line.startswith("IMAGEROUTER_API_KEY="):
                key = line.split("=", 1)[1].strip()
    if not key:
        print("SKIP: живой smoke — нет ключа ImageRouter")
        return
    m = _load_enhancer_mod()
    from PIL import Image

    img = Image.new("RGB", (64, 64), (200, 30, 30))
    text = m.call_vlm(
        m.SYSTEM_ENHANCE, "красный квадрат, сделать красиво", [m.prepare_image(img)],
        key=key, model="zai/glm-5.3-flash",
    )
    assert text and not text.startswith("```"), text
    assert len(text.split()) >= 10, text  # развёрнутый промт, не огрызок
    print("OK: живой smoke VLM ->", text[:80], "...")
```

и вызов `test_live_smoke()` в `__main__` (последним).

Run: `venv\Scripts\python.exe tests\test_prompt_enhancer.py`
Expected: `OK: живой smoke VLM -> ...` (занимает ~5–20 с; при сетевой ошибке — разобраться, не игнорировать).

- [ ] **Step 6: Commit**

```bash
git add imagerouter/prompt_enhancer.py tests/test_prompt_enhancer.py
git commit -m "feat(prompt-enhancer): серверный модуль инвокаций claude_expand_prompt/claude_analyze_image через VLM"
```

---

### Task 3: setup_imagerouter.py — деплой узла и три патча App-бандла

**Files:**
- Modify: `setup_imagerouter.py` (новые константы и 4 функции; main())
- Test: `tests/test_prompt_enhancer.py` (дополнить)

**Interfaces:**
- Consumes: `imagerouter/prompt_enhancer.py` (Task 2); существующие `SRC`, `SP`, `DIST` в setup_imagerouter.py.
- Produces: `PE_SRC: Path`, `PE_DST: Path`; функции `deploy_prompt_enhancer() -> bool`, `patch_prompt_enhance_button(bundle: Path | None = None) -> bool`, `patch_expand_graph_refs(bundle: Path | None = None) -> bool`, `patch_expansion_overlay_edit(bundle: Path | None = None) -> bool` — все идемпотентны (повторный запуск возвращает False).

- [ ] **Step 1: Дописать failing-тесты (фейковые бандлы)**

В `tests/test_prompt_enhancer.py` добавить (перед `__main__`):

```python
import shutil
import tempfile

import setup_imagerouter as sir

# Минимальные фрагменты App-бандла, достаточные для якорей патчей
PE_FAKE = (
    'const m7="Generate",pne=u.memo(()=>{const e=FC(),t=qr(),n=T(K2);'
    'return o.jsxs(E,{pos:"relative",w:"200px",children:[o.jsx(hne,{}),'
    'o.jsx(mte,{prepend:t,children:o.jsxs(pe,{onClick:t?e.enqueueFront:e.enqueueBack,'
    'isLoading:e.isLoading||n,loadingText:m7,rightIcon:o.jsx(D1,{}),variant:"solid",'
    'colorScheme:"invokeYellow",size:"lg",w:"calc(100% - 60px)",'
    'children:[o.jsx("span",{children:m7}),o.jsx(mt,{})]})})]})});'
    'pne.displayName="InvokeQueueBackButton";'
)
REFS_FAKE = (
    'const yke=({state:e,imageDTO:t})=>{const n=sd(e);const s=["sdxl"].includes(n)?"tag_based":"sentence_based";'
    'if(t){const i=new Et(Q("claude-analyze-image-graph")),a=i.addNode({type:"claude_analyze_image",'
    'id:Q("claude_analyze_image"),model_architecture:s,image:ehe(t)});return{graph:i,outputNodeId:a.id}}'
    'else{const i=V2(e),a=new Et(Q("claude-expand-prompt-graph")),r=a.addNode({type:"claude_expand_prompt",'
    'id:Q("claude_expand_prompt"),model_architecture:s,prompt:i});return{graph:a,outputNodeId:r.id}}},'
    'lb=async e=>{const{dispatch:t,getState:n,imageDTO:s}=e,i=G0.get();if(!i)return;const{graph:a,outputNodeId:r}=yke({state:n(),imageDTO:s})},'
)
OVERLAY_FAKE = (
    'W$e=({expandedText:e})=>{const t=K(),n=T(V2),s=u.useCallback(()=>{t(nb(e)),ci.reset()},[t,e]),'
    'i=u.useCallback(()=>{const r=n,l=r?`${r}\\n${e}`:e;t(nb(l)),ci.reset()},[t,e,n]),'
    'a=u.useCallback(()=>{ci.reset()},[]);return o.jsxs(E,{pos:"absolute",inset:0,bg:"base.800",'
    'backdropFilter:"blur(8px)",zIndex:10,direction:"column",children:['
    'o.jsx(E,{flex:1,p:2,borderRadius:"md",overflowY:"auto",minH:0,children:'
    'o.jsxs(W,{fontSize:"sm",w:"full",pr:7,children:[o.jsx(Ue,{as:KC,boxSize:5,display:"inline",mr:2,'
    'color:"invokeYellow.500"}),e]})}),o.jsxs(E,{gap:2,p:1,justifyContent:"flex-end",pos:"absolute",'
    'bottom:0,right:0,flexDirection:"column",children:[o.jsxs(Fn,{orientation:"vertical",children:['
    'o.jsx($e,{label:"Replace",placement:"right",children:o.jsx(re,{onClick:s,icon:o.jsx(Wp,{}),'
    'colorScheme:"invokeGreen",size:"xs","aria-label":"Replace"})}),'
    'o.jsx($e,{label:"Insert",placement:"right",children:o.jsx(re,{onClick:i,icon:o.jsx(an,{}),'
    'colorScheme:"invokeBlue",size:"xs","aria-label":"Insert"})})]}),'
    'o.jsx($e,{label:"Discard",placement:"right",children:o.jsx(re,{onClick:a,icon:o.jsx(Yt,{}),'
    'colorScheme:"invokeRed",size:"xs","aria-label":"Discard"})})]})]})},'
    'Lne=u.memo(()=>{const{isSuccess:e,isPending:t}=ie(ci.$state)})'
)


def test_patch_prompt_enhance_button():
    with tempfile.TemporaryDirectory() as td:
        b = Path(td) / "App-fake.js"
        b.write_text(PE_FAKE, encoding="utf-8")
        assert sir.patch_prompt_enhance_button(b) is True
        assert sir.patch_prompt_enhance_button(b) is False  # идемпотентно
        s = b.read_text(encoding="utf-8")
        assert s.count("DevbimPEBtn") >= 2  # определение + использование
        assert s.count('const m7="Generate",pne=u.memo(') == 1  # якорь сохранён
        assert s.index("const DevbimPEBtn") < s.index('const m7="Generate"')
        assert s.count("o.jsx(DevbimPEBtn,{})") == 1
        assert (Path(td) / "App-fake.js.imagerouter-bak").exists()
    print("OK: патч кнопки Prompt Enhance идемпотентен")


def test_patch_expand_graph_refs():
    with tempfile.TemporaryDirectory() as td:
        b = Path(td) / "App-fake.js"
        b.write_text(REFS_FAKE, encoding="utf-8")
        assert sir.patch_expand_graph_refs(b) is True
        assert sir.patch_expand_graph_refs(b) is False
        s = b.read_text(encoding="utf-8")
        assert "prompt:i,images:(function(st){" in s
        assert "image_name:x.ipAdapter.image.image_name" in s
        assert "c.present" in s  # redux-undo развёрнут
        assert s.count("claude_analyze_image") == 2  # ветка анализа не тронута
        assert (Path(td) / "App-fake.js.imagerouter-bak").exists()
    print("OK: патч референсов идемпотентен")


def test_patch_expansion_overlay_edit():
    with tempfile.TemporaryDirectory() as td:
        b = Path(td) / "App-fake.js"
        b.write_text(OVERLAY_FAKE, encoding="utf-8")
        assert sir.patch_expansion_overlay_edit(b) is True
        assert sir.patch_expansion_overlay_edit(b) is False
        s = b.read_text(encoding="utf-8")
        # 3 вхождения: атрибут textarea + два querySelector в Replace/Insert
        assert s.count("data-devbim-enhanced") == 3, s.count("data-devbim-enhanced")
        assert "defaultValue:e" in s and "Lne=u.memo(" in s  # якорь-хвост сохранён
        assert (Path(td) / "App-fake.js.imagerouter-bak").exists()
    print("OK: патч оверлея идемпотентен")


def test_deploy_prompt_enhancer():
    with tempfile.TemporaryDirectory() as td:
        dst_dir = Path(td)
        # подменяем пути деплоя
        orig_dst = sir.PE_DST
        try:
            sir.PE_DST = dst_dir / "devbim_prompt_enhancer.py"
            assert sir.deploy_prompt_enhancer() is True
            assert sir.deploy_prompt_enhancer() is False  # повторно — пропуск
            text = sir.PE_DST.read_text(encoding="utf-8")
            assert 'claude_expand_prompt' in text and 'claude_analyze_image' in text
        finally:
            sir.PE_DST = orig_dst
    print("OK: деплой модуля инвокаций идемпотентен")
```

В `__main__` добавить:

```python
    test_patch_prompt_enhance_button()
    test_patch_expand_graph_refs()
    test_patch_expansion_overlay_edit()
    test_deploy_prompt_enhancer()
```

- [ ] **Step 2: Запустить — FAIL**

Run: `venv\Scripts\python.exe tests\test_prompt_enhancer.py`
Expected: FAIL — `AttributeError: module 'setup_imagerouter' has no attribute 'patch_prompt_enhance_button'`.

- [ ] **Step 3: Реализовать в `setup_imagerouter.py`**

После `MASK_TOGGLE_NAME = "devbim-mask-toggle.js"` (строка 60) добавить константы:

```python
PE_SRC = SRC / "prompt_enhancer.py"
PE_DST = SP / "invokeai" / "app" / "invocations" / "devbim_prompt_enhancer.py"
```

Добавить функции (после `patch_queue_buttons()`, ~строка 386):

```python
# ----------------------------------------------------------------------------
# Prompt Enhancer: улучшение промта через VLM ImageRouter.
#   deploy_prompt_enhancer — модуль инвокаций claude_expand_prompt /
#   claude_analyze_image в пакет (новый файл, автоподхват __init__.py).
#   Три патча App-бандла (все идемпотентны, бэкап *.imagerouter-bak):
#     patch_prompt_enhance_button  — голубая кнопка #38BDF8 в слоте 60px
#                                    справа от жёлтой Generate;
#     patch_expand_graph_refs      — референсы (Reference Images) в граф
#                                    расширения промта (state.canvas.present
#                                    .referenceImages.entities[].ipAdapter.image);
#     patch_expansion_overlay_edit — оверлей результата: статический текст ->
#                                    редактируемый textarea (uncontrolled,
#                                    defaultValue), Replace/Insert читают
#                                    отредактированное значение из DOM.
# ----------------------------------------------------------------------------

def deploy_prompt_enhancer() -> bool:
    """Копирует модуль инвокаций Prompt Enhancer в пакет invokeai."""
    if not PE_SRC.exists():
        print("ОШИБКА: нет источника", PE_SRC)
        sys.exit(1)
    if PE_DST.exists() and PE_DST.read_text(encoding="utf-8") == PE_SRC.read_text(encoding="utf-8"):
        print("Модуль Prompt Enhancer уже развернут, пропуск")
        return False
    PE_DST.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(PE_SRC, PE_DST)
    print("Модуль инвокаций развернут:", PE_DST)
    return True


# Кнопка Prompt Enhance: компонент + вставка в контейнер Generate (слот 60px).
# Je — стор-хук (как у штатной кнопки расширения), ie(ci.$state) — стор
# Prompt Expansion, lb — штатный enqueue-and-wait, KC — иконка-искра.
JS_PE_BTN = (
    'const DevbimPEBtn=u.memo(()=>{const{dispatch:e,getState:t}=Je(),'
    '{isPending:n}=ie(ci.$state),s=u.useCallback(()=>{ci.setPending(),'
    'lb({dispatch:e,getState:t})},[e,t]);return o.jsx($e,{label:"Prompt Enhance",'
    'placement:"top",hasArrow:!0,children:o.jsx(pe,{"aria-label":"Prompt Enhance",'
    'onClick:s,isDisabled:n,position:"absolute",right:0,top:0,w:"56px",h:"40px",'
    'minW:"56px",px:0,variant:"solid",sx:{background:"#38BDF8",color:"#0B0C0E",'
    '_hover:{background:"#5CC8FA"},_disabled:{background:"#38BDF8",opacity:.5}},'
    'children:o.jsx(KC,{size:16})})})});'
)
JS_PE_PREFIX_OLD = 'const m7="Generate",pne=u.memo('
JS_PE_TAIL_OLD = 'o.jsx(mt,{})]})})]})});pne.displayName="InvokeQueueBackButton"'
JS_PE_TAIL_NEW = 'o.jsx(mt,{})]})}),o.jsx(DevbimPEBtn,{})]})});pne.displayName="InvokeQueueBackButton"'


def patch_prompt_enhance_button(bundle: Path | None = None) -> bool:
    """Голубая кнопка «Prompt Enhance» справа от жёлтой Generate."""
    if bundle is None:
        targets = [
            f for f in DIST.glob("assets/*.js")
            if 'displayName="InvokeQueueBackButton"' in f.read_text(encoding="utf-8")
        ]
        if len(targets) != 1:
            print(f"ОШИБКА: бандл с кнопкой Generate найден {len(targets)} раз (ожидался 1)")
            sys.exit(1)
        bundle = targets[0]
    s = bundle.read_text(encoding="utf-8")
    if "DevbimPEBtn" in s:
        print("Кнопка Prompt Enhance уже установлена, пропуск")
        return False
    if s.count(JS_PE_PREFIX_OLD) != 1 or s.count(JS_PE_TAIL_OLD) != 1:
        print("ОШИБКА: якоря кнопки Generate найдены не по одному разу — структура изменилась")
        sys.exit(1)
    s = s.replace(JS_PE_PREFIX_OLD, JS_PE_BTN + JS_PE_PREFIX_OLD, 1)
    s = s.replace(JS_PE_TAIL_OLD, JS_PE_TAIL_NEW, 1)
    bak = bundle.with_suffix(bundle.suffix + ".imagerouter-bak")
    if not bak.exists():
        shutil.copy2(bundle, bak)
    bundle.write_text(s, encoding="utf-8")
    print(f"Кнопка Prompt Enhance установлена у Generate: {bundle.name} (бэкап: {bak.name})")
    return True


# Референсы в граф расширения промта: глобальные Reference Images канваса
# (redux-undo: живое состояние в .present; грабля тумблера, п.16 HANDOFF).
JS_REFS_OLD = (
    'const i=V2(e),a=new Et(Q("claude-expand-prompt-graph")),r=a.addNode('
    '{type:"claude_expand_prompt",id:Q("claude_expand_prompt"),'
    'model_architecture:s,prompt:i});return{graph:a,outputNodeId:r.id}'
)
JS_REFS_COLLECTOR = (
    'images:(function(st){var acc=[];try{var c=st&&st.canvas?st.canvas:null;'
    'c=c&&c.present?c.present:c;var ents=(c&&c.referenceImages&&'
    'c.referenceImages.entities)||[];ents.forEach(function(x){'
    'if(x&&x.isEnabled!==false&&x.ipAdapter&&x.ipAdapter.image&&'
    'x.ipAdapter.image.image_name)acc.push({image_name:x.ipAdapter.image.image_name})})'
    '}catch(err){acc=[]}return acc})(e)'
)
JS_REFS_NEW = JS_REFS_OLD.replace("prompt:i});", "prompt:i," + JS_REFS_COLLECTOR + "});")


def patch_expand_graph_refs(bundle: Path | None = None) -> bool:
    """Прикладывает Reference Images к графу улучшения промта."""
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
    if JS_REFS_COLLECTOR in s:
        print("Референсы в графе расширения уже подключены, пропуск")
        return False
    if s.count(JS_REFS_OLD) != 1:
        print(f"ОШИБКА: фрагмент yke найден {s.count(JS_REFS_OLD)} раз (ожидался 1)")
        sys.exit(1)
    s = s.replace(JS_REFS_OLD, JS_REFS_NEW, 1)
    bak = bundle.with_suffix(bundle.suffix + ".imagerouter-bak")
    if not bak.exists():
        shutil.copy2(bundle, bak)
    bundle.write_text(s, encoding="utf-8")
    print(f"Референсы подключены к улучшению промта: {bundle.name} (бэкап: {bak.name})")
    return True


# Оверлей результата: редактируемый textarea вместо статического текста.
# Ns — chakra Textarea (та же, что у промпт-бокса). Uncontrolled defaultValue:
# React не перезаписывает правки пользователя; Replace/Insert читают значение
# из DOM (querySelector по data-devbim-enhanced).
JS_OVERLAY_ANCHOR_START = 'W$e=({expandedText:e})=>{'
JS_OVERLAY_ANCHOR_END = ']})]})},Lne=u.memo('
JS_OVERLAY_NEW = (
    'W$e=({expandedText:e})=>{const t=K(),n=T(V2),'
    's=u.useCallback(()=>{const el=document.querySelector("textarea[data-devbim-enhanced]");'
    't(nb(el?el.value:e)),ci.reset()},[t,e]),'
    'i=u.useCallback(()=>{const el=document.querySelector("textarea[data-devbim-enhanced]"),'
    'v2=el?el.value:e,r=n,l=r?`${r}\\n${v2}`:v2;t(nb(l)),ci.reset()},[t,e,n]),'
    'a=u.useCallback(()=>{ci.reset()},[]);'
    'return o.jsxs(E,{pos:"absolute",inset:0,bg:"base.800",backdropFilter:"blur(8px)",'
    'zIndex:10,direction:"column",children:['
    'o.jsx(E,{flex:1,p:2,borderRadius:"md",overflowY:"auto",minH:0,children:'
    'o.jsx(Ns,{"data-devbim-enhanced":!0,defaultValue:e,variant:"darkFilled",'
    'fontSize:"sm",w:"full",resize:"none",placeholder:"Enhanced prompt",'
    'sx:{"::placeholder":{color:"rgba(255,255,255,.4)"}}})}),'
    'o.jsxs(E,{gap:2,p:1,justifyContent:"flex-end",pos:"absolute",bottom:0,right:0,'
    'flexDirection:"column",children:[o.jsxs(Fn,{orientation:"vertical",children:['
    'o.jsx($e,{label:"Replace",placement:"right",children:o.jsx(re,{onClick:s,'
    'icon:o.jsx(Wp,{}),colorScheme:"invokeGreen",size:"xs","aria-label":"Replace"})}),'
    'o.jsx($e,{label:"Insert",placement:"right",children:o.jsx(re,{onClick:i,'
    'icon:o.jsx(an,{}),colorScheme:"invokeBlue",size:"xs","aria-label":"Insert"})})]}),'
    'o.jsx($e,{label:"Discard",placement:"right",children:o.jsx(re,{onClick:a,'
    'icon:o.jsx(Yt,{}),colorScheme:"invokeRed",size:"xs","aria-label":"Discard"})})'
    ']})]})},Lne=u.memo('
)


def patch_expansion_overlay_edit(bundle: Path | None = None) -> bool:
    """Оверлей результата расширения промта становится редактируемым."""
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
    if "data-devbim-enhanced" in s:
        print("Оверлей расширения уже редактируемый, пропуск")
        return False
    if s.count(JS_OVERLAY_ANCHOR_START) != 1 or s.count(JS_OVERLAY_ANCHOR_END) != 1:
        print("ОШИБКА: якоря оверлея W$e найдены не по одному разу — структура изменилась")
        sys.exit(1)
    i = s.index(JS_OVERLAY_ANCHOR_START)
    j = s.index(JS_OVERLAY_ANCHOR_END, i) + len(JS_OVERLAY_ANCHOR_END)
    s = s[:i] + JS_OVERLAY_NEW + s[j:]
    bak = bundle.with_suffix(bundle.suffix + ".imagerouter-bak")
    if not bak.exists():
        shutil.copy2(bundle, bak)
    bundle.write_text(s, encoding="utf-8")
    print(f"Оверлей расширения промта редактируемый: {bundle.name} (бэкап: {bak.name})")
    return True
```

В `main()` после `patch_canvas_bridge()` добавить:

```python
    deploy_prompt_enhancer()
    patch_prompt_enhance_button()
    patch_expand_graph_refs()
    patch_expansion_overlay_edit()
```

и в стартовую проверку `for p in (...)` добавить `PE_SRC`.

- [ ] **Step 4: Запустить тесты — PASS**

Run: `venv\Scripts\python.exe tests\test_prompt_enhancer.py`
Expected: все `OK: ...`, включая новые четыре и живой smoke.

- [ ] **Step 5: Commit**

```bash
git add setup_imagerouter.py tests/test_prompt_enhancer.py
git commit -m "feat(prompt-enhancer): деплой узла + 3 патча App-бандла (кнопка, референсы, редактируемый оверлей)"
```

---

### Task 4: Развёртка на живом окружении и проверки

**Files:**
- Modify (через скрипт, не руками): `venv/.../invokeai/app/invocations/devbim_prompt_enhancer.py`, `venv/.../dist/assets/App-*.js`

**Interfaces:**
- Consumes: Task 3 (`setup_imagerouter.py`).
- Produces: работающая фича на http://127.0.0.1:9090.

- [ ] **Step 1: Применить setup-скрипт**

```bash
cd "C:\Users\Lenovo\Desktop\проект SOFT_2\Дизайн\InvokeAI\InvokeAI"
venv/Scripts/python.exe setup_imagerouter.py
```

Expected: среди строк — «Модуль инвокаций развернут», «Кнопка Prompt Enhance установлена», «Референсы подключены», «Оверлей расширения промта редактируемый»; существующие патчи — «уже ... пропуск». Любая «ОШИБКА» — стоп, разбираться.

- [ ] **Step 2: Проверить парсинг App-бандла (обязательная грабля)**

```bash
node -e "import('file:///C:/Users/Lenovo/Desktop/проект SOFT_2/Дизайн/InvokeAI/InvokeAI/venv/Lib/site-packages/invokeai/frontend/web/dist/assets/App-B3eY4dpl.js').catch(e=>console.log(e.message))"
```

Expected: только `document is not defined` (или похожая рантайм-ошибка). `SyntaxError` — СТОП: восстановить `App-B3eY4dpl.js.imagerouter-bak`, найти ошибку.

- [ ] **Step 3: Перезапустить сервер и дождаться готовности**

```powershell
powershell -ExecutionPolicy Bypass -File _restart_server.ps1
```

Затем (до ~1 мин): `curl -s http://127.0.0.1:9090/api/v1/imagerouter/status`
Expected JSON с `"prompt_enhancer_model":"zai/glm-5.3-flash"` и `"key_source":"env"`.

- [ ] **Step 4: Проверить регистрацию узлов**

```bash
venv/Scripts/python.exe -c "import invokeai.app.invocations.devbim_prompt_enhancer as m; from invokeai.app.invocations.baseinvocation import InvocationRegistry; assert InvocationRegistry.get_invocation_for_type('claude_expand_prompt') is m.EnhancePromptInvocation; assert InvocationRegistry.get_invocation_for_type('claude_analyze_image') is m.AnalyzeImageInvocation; print('OK: узлы зарегистрированы')"
```

Expected: `OK: узлы зарегистрированы`.

- [ ] **Step 5: E2E в браузере (вживую, login по паролю сайта)**

Чек-лист (каждый пункт отмечать):
1. F5 → в левой панели справа от жёлтой Generate видна голубая кнопка ✨ (56×40), тултип «Prompt Enhance».
2. Ввести промт «домик с крышей, второй этаж» → клик голубую кнопку → спиннер поверх промпт-бокса (~5–20 с) → оверлей с английским промтом.
3. Отредактировать текст в оверлее → Replace → в промпт-боксе отредактированная версия.
4. Повторить → Insert → текст дописан в конец исходного промта (через перевод строки).
5. Добавить Reference Image (референс с узнаваемым содержимым) + короткий промт → Enhance → результат упоминает содержимое референса.
6. Пустой промт без референсов → Enhance → красный тост «Не удалось расширить промт» (или локализованный аналог).
7. Вкладка Canvas — кнопка на месте, поток тот же.
8. DevTools Console — нет новых ошибок React/сети.

- [ ] **Step 6: Commit (если что-то правилось по итогам E2E)**

```bash
git add -A imagerouter/ tests/ setup_imagerouter.py
git commit -m "fix(prompt-enhancer): правки по итогам живой проверки"
```

(при чистом дереве — пропустить).

---

### Task 5: HANDOFF.md и финализация

**Files:**
- Modify: `HANDOFF.md`

- [ ] **Step 1: Добавить пункт в «Что реализовано»** (после п. 21, перед п. 17 — нумерация в файле уже непоследовательная, продолжить по хронологии сверху вниз так же, как сделано для п. 21)

Содержание (сократить по факту, отразить грабли, найденные при реализации):

```markdown
22. **Prompt Enhancer — улучшение промта через VLM ImageRouter** (06.09).
    Голубая кнопка ✨ (#38BDF8, слот 60px справа от жёлтой Generate; патч
    App-бандла `patch_prompt_enhance_button`) запускает ШТАТНЫЙ флоу
    Prompt Expansion (ci.setPending + lb — как у скрытой штатной кнопки):
    граф claude_expand_prompt -> реальная очередь -> string_output ->
    оверлей результата. Сервер: `imagerouter/prompt_enhancer.py` (деплой
    `deploy_prompt_enhancer` в invokeai/app/invocations/devbim_prompt_
    enhancer.py — пакет подхватывает новые *.py сам через __all__ в
    __init__.py + star-import graph.py) — инвокации claude_expand_prompt
    (prompt + images[]) и claude_analyze_image ходят в
    /v1/openai/chat/completions; модель zai/glm-5.3-flash, override .env
    PROMPT_ENHANCER_MODEL; вывод всегда английский; max_tokens 1500
    (грабля: reasoning-модели при малом лимите возвращают ПУСТОЙ content).
    Референсы: `patch_expand_graph_refs` дописывает в граф глобальные
    Reference Images (state.canvas.PRESENT.referenceImages.entities[].
    ipAdapter.image, до 4 шт). Оверлей: `patch_expansion_overlay_edit` —
    редактируемый textarea (uncontrolled defaultValue + чтение из DOM в
    Replace/Insert). Флаг allowPromptExpansion НЕ включаем: оверлей и
    блокировка промпта от него не зависят, точка входа одна — наша кнопка.
    Тесты: tests/test_prompt_enhancer.py (включая живой smoke VLM).
    Проверка после изменений: setup_imagerouter.py + node-import App-бандла
    + рестарт + E2E чек-лист (план docs/superpowers/plans/2026-09-06-prompt-enhancer.md).
```

- [ ] **Step 2: Прогнать все тесты ещё раз**

```bash
venv/Scripts/python.exe tests/test_prompt_enhancer.py
venv/Scripts/python.exe tests/test_mask_toggle.py
```

Expected: все OK/SKIP без исключений.

- [ ] **Step 3: Commit**

```bash
git add HANDOFF.md
git commit -m "docs(handoff): пункт 22 — Prompt Enhancer через VLM ImageRouter"
```

---

## Откат (на случай необходимости)

1. Восстановить `venv/.../dist/assets/App-*.js` из `App-*.js.imagerouter-bak`.
2. Удалить `venv/.../invokeai/app/invocations/devbim_prompt_enhancer.py`.
3. Перезапустить сервер (`_restart_server.ps1`), в браузере F5.
4. Роутерные изменения (CHAT_COMPLETIONS_URL и др.) безвредны без узла — можно оставить.
