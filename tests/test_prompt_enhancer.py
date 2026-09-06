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


def _load_enhancer_mod():
    spec = importlib.util.spec_from_file_location(
        "devbim_prompt_enhancer", ROOT / "imagerouter" / "prompt_enhancer.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # pydantic 2.13: без регистрации в sys.modules строковые
    # аннотации (from __future__ import annotations) не резолвятся -> InvalidFieldError
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
    # альфа=128 на белом: (255, ~127, ~127) — светлый красный; чёрная подложка дала бы (128,0,0)
    assert px[0] > 200 and 100 < px[1] < 160  # альфа склеена с белым, не с чёрным
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


if __name__ == "__main__":
    test_router_enhancer_model()
    test_sanitize()
    test_prepare_image()
    test_build_body()
    test_live_smoke()
