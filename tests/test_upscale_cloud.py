# -*- coding: utf-8 -*-
"""Тесты облачного апскейлинга (вкладка Upscaling через ImageRouter):
инъекция fake-моделей, разбор графа, подбор размера, промпт, эндпоинты
выбора администратора, режимы и форматы вывода (селекторы вкладки).

Запуск: venv\\Scripts\\python.exe tests\\test_upscale_cloud.py
"""
import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "imagerouter"))

import imagerouter_router as ir  # noqa: E402


# --- фикстуры каталога (формат /v3/models) ---

CATALOG = [
    {
        "id": "prunaai/P-Image-Upscale",
        "architecture": {"input_modalities": ["image"], "output_modalities": ["image"]},
        "pricing": {"average": 0.005},
        "parameters": {"size": ["2048x2048", "2896x2896"]},
    },
    {
        "id": "philz1337x/clarity-2x",
        "architecture": {"input_modalities": ["image"]},
        "pricing": {"average": 0.0038},
        "parameters": {"size": ["custom"]},
    },
    {
        "id": "text/only-model",
        "architecture": {"input_modalities": []},
        "pricing": {"average": 0.001},
    },
]


def setup_catalog():
    ir._fetch_ir_models = lambda force=False: list(CATALOG)
    ir._ir_model_by_id = lambda mid: next((m for m in CATALOG if m.get("id") == mid), None)


# --- граф вкладки Upscaling (упрощение структуры sSe из App-бандла) ---

def upscale_batch(scale=4, creativity=0.0, structure=0.0, board="b1", init="init_img.png", mode=None, fmt=None):
    denoising_start = (creativity * -1 + 10) * 4.99 / 100
    control_weight = (structure + 10) * 0.0325 + 0.3
    spandrel = {
        "type": "spandrel_image_to_image_autoscale",
        "image_to_image_model": {"key": "imagerouter-upscale/prunaai/P-Image-Upscale", "name": "P-Image-Upscale"},
        "image": {"image_name": init},
        "scale": scale,
    }
    # доп. поля от патченого билдера графа (селекторы режима/формата вкладки)
    if mode is not None:
        spandrel["upscale_mode"] = mode
    if fmt is not None:
        spandrel["output_format"] = fmt
    return {
        "batch": {
            "runs": 1,
            "origin": "upscaling",
            "destination": "upscaling",
            "graph": {
                "id": "g1",
                "nodes": {
                    "spandrel": spandrel,
                    "denoise": {
                        "type": "tiled_multi_diffusion_denoise_latents",
                        "denoising_start": denoising_start,
                    },
                    "controlnet_1": {
                        "type": "controlnet",
                        "control_model": {"key": "imagerouter/tile-controlnet", "name": "Tile ControlNet (ImageRouter)"},
                        "control_weight": control_weight,
                    },
                    # второй controlnet-узел (двухстадийный контроль) — вес
                    # слабее, Structure берём из ПЕРВОГО
                    "controlnet_2": {
                        "type": "controlnet",
                        "control_model": {"key": "imagerouter/tile-controlnet", "name": "Tile ControlNet (ImageRouter)"},
                        "control_weight": 0.21375,
                    },
                    "sdxl_model_loader": {
                        "type": "sdxl_model_loader",
                        "model": {"key": "imagerouter/google/nano-banana-2", "name": "nano-banana-2"},
                    },
                    "l2i": {"type": "l2i", "board": {"board_id": board}},
                },
                "edges": [],
            },
        }
    }


# --- quick-action из контекстного меню картинки (cSt: один spandrel-узел) ---

def adhoc_batch(init="quick.png"):
    return {
        "batch": {
            "runs": 1,
            "graph": {
                "id": "g2",
                "nodes": {
                    "spandrel": {
                        "type": "spandrel_image_to_image",
                        "image_to_image_model": {"key": "imagerouter-upscale/philz1337x/clarity-2x"},
                        "image": {"image_name": init},
                    },
                },
                "edges": [],
            },
        }
    }


def main():
    tmp = Path(tempfile.mkdtemp())
    ir.get_config = lambda: SimpleNamespace(root_path=str(tmp))
    setup_catalog()

    # --- 1. инъекция: spandrel-фейки только из выбора админа + tile-ControlNet ---

    (tmp / "data").mkdir()
    (tmp / "data" / "imagerouter_upscale.json").write_text(
        json.dumps({"models": ["prunaai/P-Image-Upscale", "text/only-model", "no/such-model"]}), encoding="utf-8"
    )
    data = {"models": [{"key": "local/model"}]}
    ir._add_ir_models(data)
    keys = {m["key"]: m for m in data["models"]}
    assert "imagerouter-upscale/prunaai/P-Image-Upscale" in keys, keys
    assert "imagerouter-upscale/no/such-model" not in keys  # нет в каталоге
    assert "imagerouter-upscale/text/only-model" not in keys  # без входа-image (страховка инъекции)
    sp = keys["imagerouter-upscale/prunaai/P-Image-Upscale"]
    assert sp["type"] == "spandrel_image_to_image", sp
    assert sp["base"] == "any", sp
    assert sp["hash"] and sp["name"] == "P-Image-Upscale", sp
    tile = keys["imagerouter/tile-controlnet"]
    assert tile["type"] == "controlnet" and tile["base"] == "sdxl", tile
    assert "tile" in tile["name"].lower(), tile
    # main-фейки по-прежнему на месте, ключи ролей не пересекаются
    assert "imagerouter/prunaai/P-Image-Upscale" in keys, keys
    assert keys["imagerouter/prunaai/P-Image-Upscale"]["type"] == "main"
    print("OK инъекция fake-моделей")

    # дефолт при отсутствии файла
    (tmp / "data" / "imagerouter_upscale.json").unlink()
    assert ir._load_upscale_selection() == ir.DEFAULT_UPSCALE_MODELS
    print("OK дефолт выбора")

    # --- 2. разбор графа вкладки Upscaling ---

    info = ir._extract_ir_info(upscale_batch(scale=4)["batch"])
    assert info["is_upscale"] is True
    assert info["upscale_model_key"] == "imagerouter-upscale/prunaai/P-Image-Upscale"
    assert info["init_image"] == "init_img.png"
    assert abs(info["upscale_scale"] - 4.0) < 1e-9
    assert info["board_id"] == "b1"
    # creativity = 1 - denoising_start; слайдер 0 -> denoising_start 0.499 -> ~0.5
    assert abs(info["upscale_creativity"] - 0.501) < 0.01, info["upscale_creativity"]
    # structure = control_weight; слайдер 0 -> (0+10)*0.0325+0.3 = 0.625
    assert abs(info["upscale_structure"] - 0.625) < 1e-9, info["upscale_structure"]
    # главная imagerouter-модель в графе тоже видна, но апскейл первичен
    assert info["model_key"] == "imagerouter/google/nano-banana-2"
    print("OK разбор графа вкладки")

    # --- 3. quick-action: spandrel-узел без main-модели, scale по умолчанию ---

    info2 = ir._extract_ir_info(adhoc_batch()["batch"])
    assert info2["is_upscale"] is True and info2["model_key"] is None
    assert info2["upscale_model_key"] == "imagerouter-upscale/philz1337x/clarity-2x"
    assert info2["init_image"] == "quick.png" and info2["upscale_scale"] is None
    # обычный txt2img-граф апскейлом не является
    plain = {"batch": {"graph": {"nodes": {"l": {"type": "main_model_loader",
        "model": {"key": "imagerouter/google/nano-banana-2"}}}, "edges": []}}}
    assert ir._extract_ir_info(plain["batch"])["is_upscale"] is False
    print("OK quick-action и обычный граф")

    # --- 4. подбор размера ---

    # явный список: цель 1024*2 -> ближайший покрывающий 2048x2048
    assert ir._pick_upscale_size("prunaai/P-Image-Upscale", 1024, 1024, 2) == "2048x2048"
    # цель больше максимума -> максимальный
    assert ir._pick_upscale_size("prunaai/P-Image-Upscale", 1400, 1400, 4) == "2896x2896"
    # custom: снап к 64 и кап 2048 (512*4=2048, 384*4=1536)
    assert ir._pick_upscale_size("philz1337x/clarity-2x", 512, 384, 4) == "2048x1536"
    # 300*2=600 -> ближайшее кратное 64 = 576
    assert ir._pick_upscale_size("philz1337x/clarity-2x", 300, 300, 2) == "576x576"
    assert ir._snap64(600) == 576 and ir._snap64(640) == 640
    # маленькие цели: 50*2=100 -> снап 128 (валидно); 40*2=80 -> снап 64 <128 -> None
    assert ir._pick_upscale_size("philz1337x/clarity-2x", 50, 50, 2) == "128x128"
    assert ir._pick_upscale_size("philz1337x/clarity-2x", 40, 40, 2) is None
    print("OK подбор размера")

    # --- 5. промпт ---

    p = ir._upscale_prompt(4)
    assert "4x" in p and "exactly the same" in p
    p_creative = ir._upscale_prompt(4, creativity=0.9)
    assert "creatively enhance" in p_creative
    p_strict = ir._upscale_prompt(4, creativity=0.1)
    assert "strictly faithful" in p_strict
    p_struct = ir._upscale_prompt(2, structure=0.6)
    assert "exact structure" in p_struct
    assert "2x" in p_struct
    print("OK промпт")

    # --- 6. эндпоинты выбора ---

    st = ir.get_upscale_models()
    assert st["defaults_used"] is True
    ids = [m["id"] for m in st["models"]]
    assert ids == ir.DEFAULT_UPSCALE_MODELS
    # PUT: невалидные (не в каталоге / без входа-image) отсеиваются
    res = ir.put_upscale_models(ir.UpscaleModelsBody(models=[
        "prunaai/P-Image-Upscale", "philz1337x/clarity-2x", "no/such", "text/only-model",
    ]))
    assert res["models"] == ["prunaai/P-Image-Upscale", "philz1337x/clarity-2x"], res
    assert set(res["skipped"]) == {"no/such", "text/only-model"}, res
    # файл создан, дефолт больше не используется
    assert json.loads((tmp / "data" / "imagerouter_upscale.json").read_text(encoding="utf-8"))["models"] == res["models"]
    st2 = ir.get_upscale_models()
    assert st2["defaults_used"] is False
    assert [m["id"] for m in st2["models"]] == res["models"]
    assert st2["models"][0]["available"] is True and st2["models"][0]["image_input"] is True
    print("OK эндпоинты выбора администратора")

    # --- 7. режимы моделей из каталога ---

    # явные размеры -> режим на каждый размер
    modes = ir._upscale_modes(CATALOG[0])
    assert [m["id"] for m in modes] == ["2048x2048", "2896x2896"], modes
    assert modes[0]["size"] == "2048x2048" and modes[1]["label"] == "2896\u00d72896", modes
    # суффикс id -2x -> единственный честный множитель
    modes = ir._upscale_modes(CATALOG[1])
    assert modes == [{"id": "2x", "label": "2\u00d7", "scale": 2}], modes
    # custom без суффикса -> фолбэк 2x/4x
    modes = ir._upscale_modes({"id": "some/plain-model", "parameters": {"size": ["custom"]}})
    assert [m["id"] for m in modes] == ["2x", "4x"], modes
    # поиск режима
    assert ir._upscale_mode_by_id("philz1337x/clarity-2x", "2x")["scale"] == 2
    assert ir._upscale_mode_by_id("philz1337x/clarity-2x", "9x") is None
    assert ir._upscale_mode_by_id("philz1337x/clarity-2x", None) is None
    print("OK режимы моделей")

    # --- 8. эндпоинт режимов/форматов (селекторы вкладки) ---

    opts = ir.get_upscale_options()
    ids = [m["id"] for m in opts["models"]]
    # тот же фильтр, что у инъекции spandrel-фейков: выбор админа минус
    # недоступные и без входа-image
    assert ids == ["prunaai/P-Image-Upscale", "philz1337x/clarity-2x"], ids
    by_id = {m["id"]: m for m in opts["models"]}
    assert [m["id"] for m in by_id["prunaai/P-Image-Upscale"]["modes"]] == ["2048x2048", "2896x2896"]
    assert by_id["philz1337x/clarity-2x"]["modes"] == [{"id": "2x", "label": "2\u00d7", "scale": 2}]
    for m in opts["models"]:
        assert m["formats"] == ["png", "jpeg", "webp"], m
        assert m["default_format"] == "png"
    print("OK эндпоинт upscale-options")

    # --- 9. параметры запроса: режим первичнее слайдера, формат с валидацией ---

    info = ir._extract_ir_info(upscale_batch(scale=4, mode="2896x2896", fmt="jpeg")["batch"])
    assert info["upscale_mode"] == "2896x2896" and info["upscale_format"] == "jpeg"
    # явный размер режима -> точный size, без подбора
    scale, size, size_label, fmt = ir._upscale_request_params("prunaai/P-Image-Upscale", info, 1024, 768)
    assert size == "2896x2896" and size_label == "2896\u00d72896", (size, size_label)
    assert fmt == "jpeg"
    p = ir._upscale_prompt(size_label=size_label)
    assert "2896\u00d72896 resolution" in p, p
    # факторный режим перекрывает слайдерный scale=4 -> честные 2x
    info = ir._extract_ir_info(
        {"graph": {"nodes": {
            "s": {"type": "spandrel_image_to_image", "scale": 4, "upscale_mode": "2x", "output_format": "bmp",
                  "image_to_image_model": {"key": "imagerouter-upscale/philz1337x/clarity-2x"},
                  "image": {"image_name": "x.png"}}}}}
    )
    scale, size, size_label, fmt = ir._upscale_request_params("philz1337x/clarity-2x", info, 512, 384)
    assert scale == 2.0, scale
    assert size == "1024x768", size  # 512*2/384*2 со снапом 64
    assert fmt == "png", fmt  # bmp не в белом списке -> png
    # без режима — прежнее поведение (quick-action: scale из графа/дефолт 2)
    info2 = ir._extract_ir_info(adhoc_batch()["batch"])
    scale, size, size_label, fmt = ir._upscale_request_params("philz1337x/clarity-2x", info2, 512, 384)
    assert scale == 2.0 and size == "1024x768" and size_label is None and fmt == "png"
    print("OK параметры запроса (режим/формат)")

    print("\nВСЕ ТЕСТЫ OK")


if __name__ == "__main__":
    main()
