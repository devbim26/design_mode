# -*- coding: utf-8 -*-
"""Тесты улучшителя промтов в менеджере + фото модалки 3D Design (08.10):

1. Цепочка модели энхансера: data/imagerouter_prompt_model.json ->
   .env PROMPT_ENHANCER_MODEL -> дефолт (паттерн THREED_MODEL).
2. PUT /enhancer-model: валидация по каталогу VLM, сохранение файла.
3. POST /enhance-test: тот же SYSTEM_ENHANCE/модель/ключ, вывод для
   редактирования; стаб модуля инвокций в sys.modules.
4. /threed/modal-media: загрузка фото (dataURL -> JPEG<=1024), список с
   url, подписи, удаление; GET несуществующего слота — 404.

Запуск: venv\\Scripts\\python.exe tests\\test_enhancer_media.py
"""
import base64
import io
import json
import os
import sys
import tempfile
import types
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "imagerouter"))

os.environ.setdefault("THREED_VERIFY", "0")
os.environ.setdefault("THREED_ENSEMBLE", "0")

import imagerouter_router as ir  # noqa: E402
import threed.threed_router as R  # noqa: E402

from fastapi import HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from PIL import Image  # noqa: E402


def png_dataurl(w=1200, h=40, color=(200, 30, 30)) -> str:
    img = Image.new("RGB", (w, h), color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def main():
    tmp = Path(tempfile.mkdtemp())
    ir.get_config = lambda: SimpleNamespace(root_path=str(tmp))
    R.get_config = lambda: SimpleNamespace(root_path=str(tmp))
    old_env = os.environ.get("PROMPT_ENHANCER_MODEL")
    try:
        # --- 1. цепочка модели энхансера: default -> env -> file ---

        os.environ.pop("PROMPT_ENHANCER_MODEL", None)
        assert ir._load_enhancer_choice() == (ir.DEFAULT_ENHANCER_MODEL, "default")
        os.environ["PROMPT_ENHANCER_MODEL"] = "x/test-vlm"
        assert ir._load_enhancer_choice() == ("x/test-vlm", "env")
        store = tmp / "data" / "imagerouter_prompt_model.json"
        store.parent.mkdir(parents=True, exist_ok=True)
        store.write_text(json.dumps({"model": "y/better-vlm"}), encoding="utf-8")
        assert ir._load_enhancer_choice() == ("y/better-vlm", "file")
        # _enhancer_model (его читает инвокация и /status) следует цепочке
        assert ir._enhancer_model() == "y/better-vlm"
        print("OK цепочка модели энхансера (default -> env -> file)")

        # --- 2. GET/PUT /enhancer-model: каталог VLM + валидация ---

        ir._fetch_vlm_ids = lambda force=False: ["y/better-vlm", "z/other-vlm"]
        app = __import__("fastapi").FastAPI()
        app.include_router(ir.imagerouter_router, prefix="/api")
        client = TestClient(app)

        d = client.get("/api/v1/imagerouter/enhancer-model").json()
        assert d["model"] == "y/better-vlm" and d["source"] == "file", d
        assert d["vlms"] == ["y/better-vlm", "z/other-vlm"], d

        r = client.put("/api/v1/imagerouter/enhancer-model",
                       json={"model": "not/a-vlm"})
        assert r.status_code == 400, r.text
        r = client.put("/api/v1/imagerouter/enhancer-model",
                       json={"model": "z/other-vlm"})
        assert r.status_code == 200 and r.json()["model"] == "z/other-vlm", r.text
        assert ir._load_enhancer_choice() == ("z/other-vlm", "file")
        print("OK GET/PUT /enhancer-model (валидация по каталогу VLM)")

        # каталог недоступен (пусто) — PUT сохраняет как есть (не блокирует)
        ir._fetch_vlm_ids = lambda force=False: []
        r = client.put("/api/v1/imagerouter/enhancer-model",
                       json={"model": "offline/vlm"})
        assert r.status_code == 200, r.text
        print("OK PUT /enhancer-model при пустом каталоге")

        # --- 3. POST /enhance-test: стаб модуля инвокций ---

        calls = {}

        def fake_call_vlm(system, prompt, image_urls, key=None, model=None):
            calls["system"], calls["prompt"] = system, prompt
            calls["images"] = list(image_urls)
            calls["model"] = ir._enhancer_model()
            # реальный call_vlm возвращает уже sanitize()-нутый текст
            return "Improved prompt, 80 words"

        def fake_prepare_image(pil):
            assert pil.size[0] <= 4096
            return "data:image/jpeg;base64,prepared"

        stub = types.SimpleNamespace(
            SYSTEM_ENHANCE="SYS", call_vlm=fake_call_vlm,
            prepare_image=fake_prepare_image)
        mod_name = "invokeai.app.invocations.devbim_prompt_enhancer"
        prev_mod = sys.modules.get(mod_name)
        sys.modules[mod_name] = stub
        try:
            r = client.post("/api/v1/imagerouter/enhance-test",
                            json={"prompt": "дом у моря", "image": png_dataurl()})
            assert r.status_code == 200, r.text
            out = r.json()["prompt"]
            assert out == "Improved prompt, 80 words", out
            assert calls["system"] == "SYS"
            assert calls["prompt"] == "дом у моря"
            assert calls["images"] == ["data:image/jpeg;base64,prepared"]
            assert calls["model"] == "offline/vlm"  # выбранный в менеджере
            # пустой запрос -> 400
            r = client.post("/api/v1/imagerouter/enhance-test", json={"prompt": "  "})
            assert r.status_code == 400, r.text
            # ошибка VLM прокидывается как 400 с текстом
            stub.call_vlm = lambda *a, **k: (_ for _ in ()).throw(
                ValueError("no key configured"))
            r = client.post("/api/v1/imagerouter/enhance-test",
                            json={"prompt": "x"})
            assert r.status_code == 400 and "no key" in r.json()["detail"], r.text
        finally:
            if prev_mod is not None:
                sys.modules[mod_name] = prev_mod
            else:
                sys.modules.pop(mod_name, None)
        print("OK POST /enhance-test (стаб call_vlm/prepare_image)")

        # --- 4. /threed/modal-media: фото + подписи ---

        app3 = __import__("fastapi").FastAPI()
        app3.include_router(R.threed_router, prefix="/api")
        c3 = TestClient(app3)

        assert c3.get("/api/v1/threed/modal-media").json() == {"items": []}

        r = c3.post("/api/v1/threed/modal-media/1/image",
                    json={"image": png_dataurl()})
        assert r.status_code == 200 and r.json()["ok"], r.text
        f1 = tmp / "threed_modal" / "1.jpg"
        assert f1.is_file()
        with Image.open(f1) as im:  # даунскейл 1200 -> 1024
            assert max(im.size) == 1024 and im.format == "JPEG"

        r = c3.post("/api/v1/threed/modal-media/3/image", json={"image": png_dataurl()})
        assert r.status_code == 400, r.text
        r = c3.post("/api/v1/threed/modal-media/2/image",
                    json={"image": "data:image/png;base64," + "!" * 64})
        assert r.status_code == 400, r.text
        print("OK загрузка фото (даунскейл 1024, JPEG, слот 1..2, битые данные)")

        r = c3.get("/api/v1/threed/modal-media/1/image")
        assert r.status_code == 200 and r.headers["content-type"].startswith("image/jpeg")
        assert c3.get("/api/v1/threed/modal-media/2/image").status_code == 404

        r = c3.put("/api/v1/threed/modal-media", json={"items": [
            {"slot": 1, "caption": "3D-модель, новый ракурс"},
            {"slot": 2, "caption": "ИИ-рендер по изначальному фото"},
        ]})
        assert r.status_code == 200 and r.json()["ok"], r.text
        items = c3.get("/api/v1/threed/modal-media").json()["items"]
        assert len(items) == 1, items  # слот 2 без файла не отдаётся
        assert items[0]["slot"] == 1
        assert items[0]["caption"] == "3D-модель, новый ракурс"
        assert items[0]["url"] == "/api/v1/threed/modal-media/1/image"

        r = c3.post("/api/v1/threed/modal-media/2/image", json={"image": png_dataurl()})
        assert r.status_code == 200, r.text
        items = c3.get("/api/v1/threed/modal-media").json()["items"]
        assert [it["slot"] for it in items] == [1, 2]
        assert items[1]["caption"] == "ИИ-рендер по изначальному фото"  # подпись жила до файла

        r = c3.delete("/api/v1/threed/modal-media/1/image")
        assert r.status_code == 200, r.text
        assert not f1.exists()
        items = c3.get("/api/v1/threed/modal-media").json()["items"]
        assert [it["slot"] for it in items] == [2]
        assert c3.get("/api/v1/threed/modal-media/1/image").status_code == 404
        print("OK подписи, список с url, удаление")

        # --- 5. статика виджета: тултипы и фото-блок в исходнике ---

        js = (ROOT / "imagerouter" / "devbim_topright_buttons.js").read_text(encoding="utf-8")
        for frag in ("peTip:", "tdTip:", "applyTitles", "devbim-3d-photos",
                     "threed/modal-media"):
            assert frag in js, frag
        assert "mkBtn('devbim-tr-pe', 'Prompt Assistant', SPARK_SVG, t().peTip)" in js
        assert "mkBtn('devbim-tr-3d', '3D Design', '', t().tdTip, '3D')" in js
        html = (ROOT / "imagerouter" / "imagerouter.html").read_text(encoding="utf-8")
        for frag in ('id="pesec"', 'id="mediasec"', "enhancer-model", "enhance-test",
                     "modal-media"):
            assert frag in html, frag
        print("OK статика: тултипы/фото в виджете, секции менеджера")

        print("\nВсе тесты OK")
    finally:
        if old_env is None:
            os.environ.pop("PROMPT_ENHANCER_MODEL", None)
        else:
            os.environ["PROMPT_ENHANCER_MODEL"] = old_env


if __name__ == "__main__":
    main()
