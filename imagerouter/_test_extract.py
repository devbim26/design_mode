# -*- coding: utf-8 -*-
"""Тест _extract_ir_info (извлечение данных из графа канваса).

Часть 1 — детерминированная: синтетические графы txt2img / sdxl_inpaint /
flux_img2img проверяют нормализацию режима, промпт (в т.ч. из batch.data),
исходное изображение и маску.
Часть 2 — информационная: если есть живой дамп data/_ir_last_graph.json,
печатается сводка по нему (без жёстких проверок — дамп меняется от
попытки к попытке).
Запуск: venv/Scripts/python.exe imagerouter/_test_extract.py
"""
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "imagerouter"))

import imagerouter_router as ir  # noqa: E402

failures = []


def check(name, cond, actual):
    if not cond:
        failures.append(f"{name}: получено {actual!r}")


def make_batch(mode, with_image=True, with_mask=False, prompt_in_data=True):
    nodes = {
        "core_metadata": {
            "id": "core_metadata",
            "type": "core_metadata",
            "generation_mode": mode,
            "model": {"key": "imagerouter/google/nano-banana:free", "hash": "h", "name": "NB", "base": "sdxl", "type": "main"},
            "positive_prompt": "",
            "negative_prompt": "",
            "width": 1024,
            "height": 1024,
        },
        "save_image": {"id": "save_image", "type": "save_image"},
    }
    if with_image or with_mask:
        cgm = {"id": "create_gradient_mask", "type": "create_gradient_mask"}
        if with_image:
            cgm["image"] = {"image_name": "init.png"}
        if with_mask:
            cgm["mask"] = {"image_name": "mask.png"}
        nodes["create_gradient_mask"] = cgm
    data = [[{"node_path": "positive_prompt:xyz", "field_name": "value", "items": ["удали человека"]}]] if prompt_in_data else []
    return {"graph": {"id": "g", "nodes": nodes, "edges": []}, "data": data, "runs": 1}


# --- txt2img: обычная генерация, без картинки ---
info = ir._extract_ir_info(make_batch("txt2img", with_image=False))
check("txt2img: mode", info["mode"] == "txt2img", info["mode"])
check("txt2img: промпт из batch.data", info["positive"] == "удали человека", info["positive"])
check("txt2img: нет init_image", info["init_image"] is None, info["init_image"])
check("txt2img: нет маски", info["mask"] is None, info["mask"])

# --- sdxl_inpaint: редактирование с картинкой и маской ---
info = ir._extract_ir_info(make_batch("sdxl_inpaint", with_image=True, with_mask=True))
check("sdxl_inpaint: mode нормализован в 'inpaint'", info["mode"] == "inpaint", info["mode"])
check("sdxl_inpaint: init_image", info["init_image"] == "init.png", info["init_image"])
check("sdxl_inpaint: mask", info["mask"] == "mask.png", info["mask"])
check(
    "sdxl_inpaint: is_edit",
    info["mode"] in ("inpaint", "outpaint", "img2img") and bool(info["init_image"]),
    True,
)

# --- flux_img2img: редактирование без маски ---
info = ir._extract_ir_info(make_batch("flux_img2img", with_mask=False))
check("flux_img2img: mode нормализован в 'img2img'", info["mode"] == "img2img", info["mode"])
check("flux_img2img: init_image", info["init_image"] == "init.png", info["init_image"])
check("flux_img2img: маски нет", info["mask"] is None, info["mask"])

# --- живой дамп: только сводка ---
dump = BASE / "data" / "_ir_last_graph.json"
if dump.exists():
    live = ir._extract_ir_info(json.loads(dump.read_text(encoding="utf-8"))["batch"])
    print("Живой дамп:", json.dumps(live, ensure_ascii=False))
else:
    print("Живой дамп отсутствует (data/_ir_last_graph.json) — пропущено")

if failures:
    print("FAIL:")
    for f in failures:
        print("  -", f)
    sys.exit(1)
print("OK: извлечение режимов/промпта/картинки/маски работает")
