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
