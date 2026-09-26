# -*- coding: utf-8 -*-
"""Синтетические GT-картинки тем plan/interior (спека п.60 з.1a).

Рисует детерминированно и пишет авто-GT (боксы = нарисованные
прямоугольники, без ручной разметки). Фасад GT — ручной (_gt_mark.py).

  gt_plan_synthetic.png      1024x768, 0.25 м/px: 3 корпуса + спортплощадка
                            (17x34 м -> 68x136 px) + стойло парковки
                            (2.5x5 м -> 10x20 px) как якоря масштаба.
  gt_interior_synthetic.png   900x700, 0.01 м/px: 3 комнаты, 2 двери, 1 окно.

Запуск: venv\\Scripts\\python.exe data\\probe\\_make_gt_images.py
"""
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "probe"

PLAN_BOXES = {  # (x1, y1, x2, y2), подписи этажности рисуются рядом
    "buildings": [
        ((120, 120, 420, 320), "Residential", 5),
        ((520, 120, 888, 296), "School", 3),
        ((160, 470, 360, 660), "Kindergarten", 2),
    ],
    "sport": (440, 420, 576, 556),      # 68x136 px = 17x34 м
    "parking": (700, 470, 710, 490),    # 10x20 px = 2.5x5 м
}
INTERIOR_BOXES = {
    "rooms": [
        ((60, 60, 460, 350), "Living"),
        ((60, 350, 460, 640), "Bedroom"),
        ((460, 60, 840, 640), "Kitchen"),
    ],
    "doors": [(455, 190, 465, 280), (160, 345, 250, 355)],  # 0.9-0.1 м
    "windows": [(835, 200, 845, 320)],                      # 1.2 м
}


def draw_plan() -> dict:
    im = Image.new("RGB", (1024, 768), "white")
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, 1023, 767], outline=(200, 200, 200), width=2)
    entries = []
    for (box, use, floors) in PLAN_BOXES["buildings"]:
        d.rectangle(list(box), outline="black", width=3)
        d.text((box[0] + 6, box[1] + 6), f"{use} {floors} fl", fill="black")
        entries.append({"label": "building", "box": list(box),
                        "meta": {"use": use, "floors": floors}})
    x1, y1, x2, y2 = PLAN_BOXES["sport"]
    d.rectangle([x1, y1, x2, y2], outline=(70, 120, 60), width=3)
    d.text((x1 + 4, y1 + 4), "SPORT", fill=(70, 120, 60))
    entries.append({"label": "sport", "box": [x1, y1, x2, y2]})
    x1, y1, x2, y2 = PLAN_BOXES["parking"]
    d.rectangle([x1, y1, x2, y2], outline=(60, 60, 60), width=2)
    d.text((x1 - 4, y2 + 4), "P", fill=(60, 60, 60))
    entries.append({"label": "parking", "box": [x1, y1, x2, y2]})
    im.save(OUT / "gt_plan_synthetic.png")
    return {"image": "gt_plan_synthetic.png", "scenario": "plan",
            "metres_per_pixel": 0.25, "boxes": entries}


def draw_interior() -> dict:
    im = Image.new("RGB", (900, 700), "white")
    d = ImageDraw.Draw(im)
    entries = []
    for (box, name) in INTERIOR_BOXES["rooms"]:
        d.rectangle(list(box), outline="black", width=8)  # 8 px = 0.08 м
        d.text((box[0] + 12, box[1] + 12), name, fill="black")
        entries.append({"label": "room", "box": list(box), "meta": {"name": name}})
    for box in INTERIOR_BOXES["doors"] + INTERIOR_BOXES["windows"]:
        d.rectangle(list(box), fill="white", outline="black", width=2)
    for box in INTERIOR_BOXES["doors"]:
        entries.append({"label": "door", "box": list(box)})
    for box in INTERIOR_BOXES["windows"]:
        entries.append({"label": "window", "box": list(box)})
    im.save(OUT / "gt_interior_synthetic.png")
    return {"image": "gt_interior_synthetic.png", "scenario": "interior",
            "metres_per_pixel": 0.01, "boxes": entries}


def main() -> None:
    gt = [draw_plan(), draw_interior()]
    (OUT / "_threed_ground_gt_synthetic.json").write_text(
        json.dumps(gt, ensure_ascii=False, indent=1), encoding="utf-8")
    print("OK:", ", ".join(e["image"] for e in gt),
          "+ _threed_ground_gt_synthetic.json")


if __name__ == "__main__":
    main()
