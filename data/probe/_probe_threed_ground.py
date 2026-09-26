# -*- coding: utf-8 -*-
"""Зонд grounding-способности VLM каталога ImageRouter (спека п.60 з.1b).

Кандидаты x GT-картинки (Task 1/2): строгий JSON боксов -> IoU/recall/
precision/json-valid. Выход: data/probe/_probe_threed_ground_results.json
(таблица + winner/mode). Бюджет ~$0.10-0.30.

Запуск (сервер не нужен, ключ в .env):
    venv\\Scripts\\python.exe data\\probe\\_probe_threed_ground.py
"""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from invokeai.app.api.routers.threed import (  # noqa: E402  (venv-копии)
    _call_vlm, _to_dataurl, _vlm_list_cached)
from invokeai.app.api.routers import threed_scenarios  # noqa: E402
from threed import threed_ground as G  # noqa: E402  (дерево — источник правды)

PROBE = ROOT / "data" / "probe"
GT_FILES = [PROBE / "_threed_ground_gt.json",
            PROBE / "_threed_ground_gt_synthetic.json"]
RESULTS = PROBE / "_probe_threed_ground_results.json"

SYSTEM_GROUND = {  # черновик промптов (финальные — Task 4 в threed_ground)
    "facade": G.SYSTEM_GROUND_FACADE, "plan": G.SYSTEM_GROUND_PLAN,
    "interior": G.SYSTEM_GROUND_INTERIOR}


def load_gt():
    entries = []
    for p in GT_FILES:
        if p.is_file():
            entries += json.loads(p.read_text(encoding="utf-8"))
    return entries


def run_one(model, entry, image):
    t0 = time.time()
    try:
        raw = _call_vlm(SYSTEM_GROUND[entry["scenario"]],
                        "Detect all objects. STRICT JSON only.",
                        _to_dataurl(image), model)
        payload = threed_scenarios.extract_json(raw)
    except Exception as e:
        return {"ok": False, "error": str(e)[:120], "secs": round(time.time() - t0, 1)}
    if payload is None:
        return {"ok": False, "error": "not json", "secs": round(time.time() - t0, 1)}
    pred, _, _ = G.normalize_boxes(payload, image.width, image.height,
                                   scenario=entry["scenario"])
    gt, _, _ = G.normalize_boxes(entry, image.width, image.height,
                                 scenario=entry["scenario"])
    return {"ok": True, "secs": round(time.time() - t0, 1),
            **G.probe_metrics(pred, gt)}


def main() -> None:
    from PIL import Image
    gt = load_gt()
    assert gt, "нет GT — сначала Task 1/2"
    cands = G.probe_candidates([m["id"] for m in _vlm_list_cached()])
    print("кандидаты:", cands)
    table = []
    for model in cands:
        rows = []
        for entry in gt:
            img = Image.open(PROBE / entry["image"]).convert("RGB")
            r = run_one(model, entry, img)
            rows.append({"image": entry["image"], **r})
            print(f"  {model} x {entry['image']}: {r}")
        ok_rows = [r for r in rows if r.get("ok")]
        table.append({
            "model": model,
            "iou_mean": (round(sum(r["iou_mean"] for r in ok_rows) / len(ok_rows), 4)
                         if ok_rows else 0.0),
            "recall": (round(sum(r["recall"] for r in ok_rows) / len(ok_rows), 4)
                       if ok_rows else 0.0),
            "json_valid": round(len(ok_rows) / len(rows), 4),
            "rows": rows})
        print(f"{model}: mean IoU {table[-1]['iou_mean']}, "
              f"json_valid {table[-1]['json_valid']}")
    winner, mode = G.pick_model(table)
    out = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "winner": winner,
           "mode": mode, "table": table}
    RESULTS.write_text(json.dumps(out, ensure_ascii=False, indent=1),
                       encoding="utf-8")
    print(f"WINNER: {winner or '(text fallback)'} mode={mode} -> {RESULTS}")


if __name__ == "__main__":
    main()
