# -*- coding: utf-8 -*-
"""Прогон B: GT-инфраструктура + IoU (Task 2), конвертеры (Task 4, 9).
Модуль чистый (без invokeai.*) — импорт из дерева, venv не нужен."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from threed import threed_ground as G  # noqa: E402


def test_compute_iou():
    # identical -> 1.0; disjoint -> 0.0; перекрытие 50% площади
    b = [0, 0, 10, 10]
    assert G._compute_iou(b, [0, 0, 10, 10]) == 1.0
    assert G._compute_iou(b, [20, 20, 30, 30]) == 0.0
    # [0,0,10,10] и [0,0,10,20]: пересечение 100, union 200 -> 0.5
    assert abs(G._compute_iou(b, [0, 0, 10, 20]) - 0.5) < 1e-9
    # dict-форма (GT-файл) и list-форма смешиваются
    assert G._compute_iou({"x1": 0, "y1": 0, "x2": 10, "y2": 10},
                          [0, 0, 10, 10]) == 1.0
    # вырожденные -> 0.0, не исключение
    assert G._compute_iou([0, 0, 0, 0], b) == 0.0
    print("test_compute_iou OK")


def test_normalize_boxes():
    payload = {"boxes": [
        {"label": "window", "x1": 10, "y1": 20, "x2": 60, "y2": 90},
        {"label": "hack", "x1": 0, "y1": 0, "x2": 5, "y2": 5},   # чужой label
        {"label": "door", "box": [100, 100, 140, 220]},          # форма "box"
        {"label": "window", "x1": 790, "y1": 590, "x2": 900, "y2": 700},  # кламп
        {"label": "window", "x1": 50, "y1": 50, "x2": 50, "y2": 50},      # вырожденный
    ], "meta": {"floors": 3}}
    boxes, meta, wns = G.normalize_boxes(payload, 800, 600)
    labels = [b["label"] for b in boxes]
    assert labels == ["window", "door", "window"], labels
    assert all(set(b) == {"label", "x1", "y1", "x2", "y2"} for b in boxes)
    d = next(b for b in boxes if b["label"] == "door")
    assert (d["x1"], d["y1"], d["x2"], d["y2"]) == (100, 100, 140, 220)
    w = next(b for b in boxes if b["x1"] == 790)
    assert (w["x2"], w["y2"]) == (800, 600), "кламп к границе картинки"
    assert meta == {"floors": 3}
    assert len(wns) == 3, wns  # чужой label + вырожденный + кламп
    print("test_normalize_boxes OK")


def test_validate_gt():
    ok, errors = G.validate_gt([
        {"image": "a.png", "scenario": "facade", "boxes": [
            {"label": "window", "x1": 1, "y1": 1, "x2": 2, "y2": 2}] * 8
            + [{"label": "door", "x1": 1, "y1": 1, "x2": 2, "y2": 2},
               {"label": "building", "x1": 0, "y1": 0, "x2": 9, "y2": 9}]},
        {"image": "b.png", "scenario": "plan", "boxes": [
            {"label": "building", "x1": 1, "y1": 1, "x2": 2, "y2": 2}] * 3},
        {"image": "c.png", "scenario": "interior", "boxes": [
            {"label": "room", "x1": 1, "y1": 1, "x2": 2, "y2": 2}] * 3
            + [{"label": "door", "x1": 1, "y1": 1, "x2": 2, "y2": 2}] * 2},
    ])
    assert ok, errors
    # фасад < 8 окон -> ошибка
    ok2, errors2 = G.validate_gt([
        {"image": "a.png", "scenario": "facade", "boxes": [
            {"label": "window", "x1": 1, "y1": 1, "x2": 2, "y2": 2}] * 7}])
    assert not ok2 and any("facade" in e for e in errors2), errors2
    print("test_validate_gt OK")


def test_probe_metrics():
    gt = [{"x1": 0, "y1": 0, "x2": 10, "y2": 10},
          {"x1": 20, "y1": 20, "x2": 30, "y2": 30}]
    perfect = [dict(b) for b in gt]
    m = G.probe_metrics(perfect, gt)
    assert m["iou_mean"] == 1.0 and m["iou_median"] == 1.0
    assert m["recall"] == 1.0 and m["precision"] == 1.0
    # один точный pred + один мусор: recall 0.5, precision 0.5
    m2 = G.probe_metrics([gt[0], {"x1": 90, "y1": 90, "x2": 99, "y2": 99}], gt)
    assert m2["recall"] == 0.5 and m2["precision"] == 0.5
    # пустые pred: нули, не исключение
    m3 = G.probe_metrics([], gt)
    assert m3["iou_mean"] == 0.0 and m3["recall"] == 0.0
    print("test_probe_metrics OK")


def test_pick_model():
    good = {"model": "qwen/vl-x", "iou_mean": 0.62, "json_valid": 0.9,
            "results": []}
    assert G.pick_model([good]) == ("qwen/vl-x", "grounding")
    bad = {"model": "openai/gpt-6-sol", "iou_mean": 0.3, "json_valid": 0.9,
           "results": []}
    assert G.pick_model([bad]) == ("", "text"), "IoU<0.5 -> text fallback"
    nojson = {"model": "m", "iou_mean": 0.9, "json_valid": 0.4, "results": []}
    assert G.pick_model([nojson]) == ("", "text")
    assert G.pick_model([]) == ("", "text")
    # лучший по mean IoU среди прошедших гейт
    both = [good, {"model": "m2", "iou_mean": 0.7, "json_valid": 1.0,
                   "results": []}]
    assert G.pick_model(both)[0] == "m2"
    print("test_pick_model OK")


def _synth_facade_payload():
    """800x600: контур (100,50)-(700,590) = 600x540 px; окна 3 строки x 4
    столбца (w=60,h=80), дверь 60x120 px (якорь 2.1 м -> scale 0.0175)."""
    boxes = [{"label": "building", "x1": 100, "y1": 50, "x2": 700, "y2": 590}]
    for j in range(3):    # строки: y центры 130 / 300 / 470
        for i in range(4):  # столбцы: x центры 190 / 330 / 470 / 610
            cx, cy = 190 + i * 140, 130 + j * 170
            boxes.append({"label": "window", "x1": cx - 30, "y1": cy - 40,
                          "x2": cx + 30, "y2": cy + 40})
    boxes.append({"label": "door", "x1": 370, "y1": 470, "x2": 430, "y2": 590})
    return {"boxes": boxes, "meta": {"floors": 3, "roof": "gable"}}


def test_facade_boxes_to_scene():
    scene, wns = G.facade_boxes_to_scene(_synth_facade_payload(), 800, 600)
    assert not wns, wns
    assert scene["storeys"] == 3 and scene["roof"] == "gable"
    # дверь 120 px * (2.1/120) = масштаб 0.0175; ширина 600 px -> 10.5 м
    assert abs(scene["width_m"] - 10.5) < 0.15, scene["width_m"]
    assert abs(scene["floor_height"] - 540 * 0.0175 / 3) < 0.15
    w = scene["windows"]
    assert (w["rows"], w["cols"]) == (3, 4)
    assert abs(w["w_m"] - 60 * 0.0175) < 0.1 and abs(w["h_m"] - 80 * 0.0175) < 0.1
    assert not any(any(row) for row in w["skip"]), "все окна остеклены"
    e = scene["entrance"]
    assert e and abs(e["x_m"] - (400 - 100) * 0.0175) < 0.1  # центр 400 px
    # сцена проходит штатный валидатор (сравнение идёт по клампнутым полям)
    from threed import threed_scenarios
    fixed, warns = threed_scenarios.validate_facade(dict(scene))
    assert fixed["storeys"] == 3 and fixed["windows"]["rows"] == 3
    print("test_facade_boxes_to_scene OK")


def test_facade_converter_edges():
    # нет окон -> пустая сцена + warning (B выпадает, работаем с A)
    bad = {"boxes": [{"label": "building", "x1": 0, "y1": 0,
                      "x2": 100, "y2": 100}], "meta": {}}
    scene, wns = G.facade_boxes_to_scene(bad, 800, 600)
    assert scene == {} and any("окон" in w for w in wns)
    # пропуск окна: клетка сетки без бокса -> skip=True (строка j=2: cy=470)
    p = _synth_facade_payload()
    p["boxes"] = [b for b in p["boxes"]
                  if not (b["label"] == "window" and b["x1"] == 160
                          and b["y1"] == 430)]  # (3-я строка, 1-й столбец)
    scene2, _ = G.facade_boxes_to_scene(p, 800, 600)
    assert scene2["windows"]["skip"][2][0] is True
    # пиксельный хинт
    hint = G.facade_pixel_hint(_synth_facade_payload(), 800, 600)
    assert hint == (100, 50, 700, 590)
    print("test_facade_converter_edges OK")


if __name__ == "__main__":
    test_compute_iou()
    test_normalize_boxes()
    test_validate_gt()
    test_probe_metrics()
    test_pick_model()
    test_facade_boxes_to_scene()
    test_facade_converter_edges()
    print("ALL OK")
