# -*- coding: utf-8 -*-
"""Тесты пометок моделей (звёзды 1–5 + мини-баннеры): дефолты и файл
настроек, эндпоинты GET/PUT /model-marks, инъекция usage_info в
конфиги моделей списка генерации.

Запуск: venv\\Scripts\\python.exe tests\\test_model_marks.py
"""
import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "imagerouter"))

import imagerouter_router as ir  # noqa: E402


CATALOG = [
    {
        "id": "google/nano-banana-2",
        "architecture": {"input_modalities": ["image"]},
        "pricing": {"average": 0.03},
    },
    {
        "id": "HiDream-ai/HiDream-I1",
        "architecture": {"input_modalities": []},
        "pricing": {"average": 0.004},
    },
    {
        "id": "bria/remove-background",
        "architecture": {"input_modalities": ["image"]},
        "pricing": {"average": 0.005},
    },
]

MARKS_PATH = None  # <tmp>/data/imagerouter_model_marks.json


def reset():
    ir._marks_cache["key"] = None
    ir._marks_cache["data"] = None


def write_marks(payload: dict) -> None:
    MARKS_PATH.parent.mkdir(parents=True, exist_ok=True)
    MARKS_PATH.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    reset()


def main():
    tmp = Path(tempfile.mkdtemp())
    ir.get_config = lambda: SimpleNamespace(root_path=str(tmp))
    global MARKS_PATH
    MARKS_PATH = tmp / "data" / "imagerouter_model_marks.json"

    # --- 1. дефолты: файла нет -> встроенные пометки ---

    st = ir.get_model_marks()
    assert st["source"] == "defaults", st
    assert st["badges"]["edit"]["label"] == "EDIT"
    assert "google/nano-banana-2" in st["marks"], "дефолт помечает редакторов"
    eff = ir._effective_marks()
    assert eff["marks"]["google/nano-banana-2"]["stars"] == 4
    assert "badges" in eff["marks"]["google/nano-banana-2"]
    print("OK дефолты без файла")

    # --- 2. строка usage_info ---

    u = ir._marks_usage_info({"id": "google/nano-banana-2"})
    assert u == "★★★★☆ · EDIT", u
    u_bg = ir._marks_usage_info({"id": "bria/remove-background"})
    assert u_bg == "BG CUT", u_bg          # 0 звёзд — только баннер
    u_none = ir._marks_usage_info({"id": "HiDream-ai/HiDream-I1"})
    assert u_none == "", u_none           # без пометок — поля нет
    assert ir._marks_usage_info({"id": "no/such"}) == ""
    print("OK usage_info (звёзды + баннеры, без пометок)")

    # --- 3. инъекция в конфиг main-модели ---

    cfg = ir._ir_fake_config(CATALOG[0])
    assert cfg["usage_info"] == "★★★★☆ · EDIT", cfg.get("usage_info")
    assert "editing" in cfg["description"]  # гейт Generate-фолбэка не тронут
    cfg_txt = ir._ir_fake_config(CATALOG[1])
    assert "usage_info" not in cfg_txt, cfg_txt
    # служебные фейки без пометок
    assert "usage_info" not in ir._ir_ipadapter_fake()
    assert "usage_info" not in ir._ir_upscale_fake_config(CATALOG[0])
    print("OK инъекция usage_info в main-конфиги")

    # --- 4. файл настроек перекрывает дефолты ---

    write_marks({
        "badges": {
            "edit": {"label": "ПРАВКА", "color": "bad-color", "title": ""},
            "my": {"label": "МОЙ", "color": "#123456", "title": "свой баннер"},
            "bad key!": {"label": "X", "color": "#000000", "title": ""},
        },
        "marks": {
            "google/nano-banana-2": {"stars": 99, "badges": ["edit", "nope", "edit"]},
            "bria/remove-background": {"stars": 0, "badges": ["my"]},
            "junk": "not-a-dict",
            "": {"stars": 3, "badges": []},
        },
    })
    st = ir.get_model_marks()
    assert st["source"] == "file", st
    assert set(st["badges"]) == {"edit", "my"}, st["badges"]      # ключ-мусор отсеян
    assert st["badges"]["edit"]["color"] == "#4a5568"             # кривой цвет -> дефолт
    mk = st["marks"]["google/nano-banana-2"]
    assert mk == {"stars": 5, "badges": ["edit"]}, mk             # кламп + дубли + неизвестные
    assert st["marks"]["bria/remove-background"] == {"stars": 0, "badges": ["my"]}
    assert "junk" not in st["marks"] and "" not in st["marks"]
    u = ir._marks_usage_info({"id": "google/nano-banana-2"})
    assert u == "★★★★★ · ПРАВКА", u
    assert ir._marks_usage_info({"id": "HiDream-ai/HiDream-I1"}) == ""
    print("OK файл настроек + санитизация")

    # --- 5. PUT: валидация и запись ---

    body = ir.ModelMarksBody(
        badges={"t": {"label": "TEST", "color": "#abcdef", "title": "проверка"}},
        marks={
            "HiDream-ai/HiDream-I1": {"stars": 2, "badges": ["t"]},
            "google/nano-banana-2": {"stars": 7, "badges": ["t", "ghost"]},
            "future/model": {"stars": 1, "badges": []},   # не в каталоге — сохраняем
            "": {"stars": 4, "badges": ["t"]},
        },
    )
    res = ir.put_model_marks(body)
    assert res["source"] == "file"
    assert res["marks"]["HiDream-ai/HiDream-I1"] == {"stars": 2, "badges": ["t"]}
    assert res["marks"]["google/nano-banana-2"] == {"stars": 5, "badges": ["t"]}
    assert res["marks"]["future/model"] == {"stars": 1, "badges": []}
    assert "" not in res["marks"]
    saved = json.loads(MARKS_PATH.read_text(encoding="utf-8"))
    assert saved["marks"] == res["marks"]
    assert saved["badges"]["t"]["title"] == "проверка"
    # пустой каталог баннеров -> сохраняются дефолтные (UI всегда с чипами)
    res2 = ir.put_model_marks(ir.ModelMarksBody(badges={}, marks={}))
    assert res2["badges"] == ir._DEFAULT_BADGES
    assert res2["marks"] == {}
    print("OK PUT /model-marks")

    # --- 6. после PUT дефолты больше не действуют (только файл) ---

    assert ir._marks_usage_info({"id": "google/nano-banana-2"}) == ""
    st = ir.get_model_marks()
    assert st["source"] == "file" and st["marks"] == {}

    # --- 7. удаление файла возвращает дефолты ---

    MARKS_PATH.unlink()
    reset()
    st = ir.get_model_marks()
    assert st["source"] == "defaults"
    assert ir._marks_usage_info({"id": "google/nano-banana-2"}) == "★★★★☆ · EDIT"
    print("OK возврат к дефолтам после удаления файла")

    # --- 8. битый файл = дефолты (не падаем) ---

    MARKS_PATH.write_text("{не json", encoding="utf-8")
    reset()
    assert ir.get_model_marks()["source"] == "defaults"
    print("OK битый файл -> дефолты")

    print("\nВСЕ ТЕСТЫ OK")


if __name__ == "__main__":
    main()
