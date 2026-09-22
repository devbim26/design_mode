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


# --- фикстурыinvoke: фейковый роутер/requests/context (задачи 2-3) ---

import io

from PIL import Image


def _fake_ir():
    def durl(img, fmt="PNG", max_side=0, quality=92):
        # JPEG -> RGB + даунскейл, как у настоящего _pil_to_durl роутера
        # (RGBA-референсы иначе не сохраняются в JPEG; паттерн п.26/47)
        if fmt == "JPEG":
            img = img.convert("RGB")
            if max_side and max(img.size) > max_side:
                img.thumbnail((max_side, max_side))
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


if __name__ == "__main__":
    test_model_choices_from_admin_file()
    test_model_choices_fallbacks()
    test_prompt_batch()
    test_snap_side()
    test_post_images_errors()
    test_api_no_key()
    test_generate_node()
    test_generate_node_batch()
    test_edit_node()
    test_edit_node_explicit_size_no_refs()
    test_generate_node_fail_en()
