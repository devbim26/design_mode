# -*- coding: utf-8 -*-
"""Ручная разметка GT-боксов фасада (спека з.1a). Клик-drag рисует бокс,
кнопка/клавиша переключает метку, S сохраняет JSON. Координаты — пиксели
КАРТИНКИ (канвас 1:1, скролл не нужен: vlm_test_house.png 455x534).

Запуск: venv\\Scripts\\python.exe data\\probe\\_gt_mark.py [картка] [сценарий]
"""
import json
import sys
import tkinter as tk
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LABELS = ["window", "door", "building"]

img_path = Path(sys.argv[1]) if len(sys.argv) > 1 else \
    ROOT / "data" / "probe" / "vlm_test_house.png"
scenario = sys.argv[2] if len(sys.argv) > 2 else "facade"
out_path = ROOT / "data" / "probe" / "_threed_ground_gt.json"

import tkinter.filedialog  # noqa: E402,F401
from PIL import Image, ImageTk  # noqa: E402

boxes = []
if out_path.is_file():  # дозагрузка прошлой разметки этой же картинки
    for e in json.loads(out_path.read_text(encoding="utf-8")):
        if e.get("image") == img_path.name:
            boxes = e.get("boxes", [])

root = tk.Tk()
root.title(f"GT mark: {img_path.name} [{scenario}]")
img = Image.open(img_path).convert("RGB")
tkimg = ImageTk.PhotoImage(img)
cv = tk.Canvas(root, width=img.width, height=img.height)
cv.pack()
cv.create_image(0, 0, anchor="nw", image=tkimg)
cur = {"label": tk.StringVar(value=LABELS[0]), "start": None, "rect": None}


def redraw():
    cv.delete("all")
    cv.create_image(0, 0, anchor="nw", image=tkimg)
    for b in boxes:
        x1, y1, x2, y2 = b["x1"], b["y1"], b["x2"], b["y2"]
        cv.create_rectangle(x1, y1, x2, y2, outline="#ff3b30", width=2)
        cv.create_text(x1, max(0, y1 - 8), text=b["label"], fill="#ff3b30")


def press(ev):
    cur["start"] = (ev.x, ev.y)


def drag(ev):
    if cur["rect"]:
        cv.delete(cur["rect"])
    cur["rect"] = cv.create_rectangle(cur["start"][0], cur["start"][1],
                                      ev.x, ev.y, outline="#00a8ff", width=2)


def release(ev):
    if cur["start"]:
        x1, y1 = cur["start"]
        boxes.append({"label": cur["label"].get(),
                      "x1": min(x1, ev.x), "y1": min(y1, ev.y),
                      "x2": max(x1, ev.x), "y2": max(y1, ev.y)})
    cur["start"], cur["rect"] = None, None
    redraw()


def save(_ev=None):
    entries = []
    if out_path.is_file():  # другие картинки сохраняем
        entries = [e for e in json.loads(out_path.read_text(encoding="utf-8"))
                   if e.get("image") != img_path.name]
    entries.append({"image": img_path.name, "scenario": scenario,
                    "boxes": boxes})
    out_path.write_text(json.dumps(entries, indent=1), encoding="utf-8")
    print("saved", len(boxes), "boxes ->", out_path)


def undo(_ev=None):
    if boxes:
        boxes.pop()
        redraw()


def cycle_label(_ev=None):
    i = LABELS.index(cur["label"].get())
    cur["label"].set(LABELS[(i + 1) % len(LABELS)])


bar = tk.Frame(root)
bar.pack()
tk.Label(bar, textvariable=cur["label"], fg="#00a8ff").pack(side="left")
tk.Button(bar, text="Label (L)", command=cycle_label).pack(side="left")
tk.Button(bar, text="Undo (U)", command=undo).pack(side="left")
tk.Button(bar, text="Save (S)", command=save).pack(side="left")
cv.bind("<Button-1>", press)
cv.bind("<B1-Motion>", drag)
cv.bind("<ButtonRelease-1>", release)
root.bind("s", save)
root.bind("u", undo)
root.bind("l", cycle_label)
redraw()
root.mainloop()
