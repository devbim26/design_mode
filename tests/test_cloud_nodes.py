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


if __name__ == "__main__":
    test_model_choices_from_admin_file()
    test_model_choices_fallbacks()
    test_prompt_batch()
    test_snap_side()
    test_post_images_errors()
    test_api_no_key()
