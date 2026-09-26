# -*- coding: utf-8 -*-
"""Ансамбль: compare/merge/реферти (Task 5) + интеграция в роутер (Task 8).
Часть функций — чистые (этот файл, без venv); роутерные — через изолятор."""
import copy
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from threed import threed_ensemble as E  # noqa: E402


def _facade(storeys=5, width=20.0, fh=3.0, rows=2, cols=4, skip=None,
            entrance=True):
    return {"storeys": storeys, "floor_height": fh, "width_m": width,
            "depth_m": 12.0, "roof": "flat", "roof_height": 2.5,
            "windows": {"rows": rows, "cols": cols, "w_m": 1.5, "h_m": 1.5,
                        "margin_x_m": 1.0, "margin_y_m": 0.8,
                        "skip": skip if skip is not None else
                        [[False] * cols for _ in range(rows)],
                        "shape": "rect"},
            "entrance": ({"x_m": 10.0, "w_m": 2.0, "style": "porch"}
                         if entrance else None),
            "balconies": [], "dormers": [], "chimneys": [], "towers": [],
            "custom_parts": [], "colors": {"walls": "#c8b89a"}}


def test_compare_full_agreement():
    A, B = _facade(), _facade(width=20.5)  # Δwidth 2.5% < 15%
    cmp = E.compare_scenes("facade", A, B)
    assert cmp["disputed"] == {}, cmp["disputed"]
    assert cmp["agree_rate"] == 1.0
    assert set(cmp["agreed"]) == {"storeys", "width_m", "floor_height",
                                  "windows.rows", "windows.cols",
                                  "windows.skip", "entrance"}
    print("test_compare_full_agreement OK")


def test_compare_disputes():
    A = _facade()
    B = _facade(storeys=3, width=30.0, fh=3.6, rows=1, entrance=False)
    cmp = E.compare_scenes("facade", A, B)
    # skip спорит из-за формы (rows differ -> матрицы разного размера)
    assert set(cmp["disputed"]) == {"storeys", "width_m", "floor_height",
                                    "windows.rows", "windows.skip",
                                    "entrance"}, cmp["disputed"]
    assert cmp["agree_rate"] == round(1 / 7, 3)  # согласован только cols
    assert abs(cmp["metrics"]["width_m_pct"] - 10 / 30) < 1e-3  # /max(a,b)
    print("test_compare_disputes OK")


def test_skip_dispute_two_cells():
    A = _facade()
    B = _facade()
    B["windows"]["skip"] = [[True, True, False, False], [False] * 4]
    cmp = E.compare_scenes("facade", A, B)
    assert "windows.skip" in cmp["disputed"], "Δ=2 клетки -> спор"
    B2 = _facade()
    B2["windows"]["skip"] = [[True, False, False, False], [False] * 4]
    cmp2 = E.compare_scenes("facade", A, B2)
    assert "windows.skip" not in cmp2["disputed"], "Δ=1 клетка — согласовано"
    print("test_skip_dispute_two_cells OK")


def test_merge_average_and_referee():
    A, B = _facade(width=20.0), _facade(width=21.0)  # Δ5% — согласовано
    cmp = E.compare_scenes("facade", A, B)
    scene, conf, wns = E.merge_scenes("facade", A, B, cmp)
    assert abs(scene["width_m"] - 20.5) < 1e-9, "согласованный float — среднее"
    assert conf["agree_rate"] == 1.0 and conf["referee_used"] is False
    assert not wns

    # спор: реферти выбирает B по storeys, молчит по width_m
    A2, B2 = _facade(storeys=5), _facade(storeys=3, width=40.0)
    cmp2 = E.compare_scenes("facade", A2, B2)
    assert set(cmp2["disputed"]) == {"storeys", "width_m"}
    calls = []

    def referee(fields):
        calls.append(fields)
        return {"choices": {"storeys": "B"}}

    scene2, conf2, wns2 = E.merge_scenes("facade", A2, B2, cmp2, referee=referee)
    assert calls and calls[0] == ["storeys", "width_m"], "спорные поля по алфавиту"
    assert scene2["storeys"] == 3, "выбор B применён"
    assert scene2["width_m"] == 20.0, "реферти молчит -> вариант A"
    assert conf2["referee_used"] is True
    assert any("width_m" in w for w in wns2), "неспособный реферти -> A + warning"

    # реферти выбрал B по ОБОИМ полям -> оба из B
    scene2b, _, _ = E.merge_scenes(
        "facade", A2, B2, cmp2,
        referee=lambda f: {"choices": {"storeys": "B", "width_m": "B"}})
    assert scene2b["storeys"] == 3 and scene2b["width_m"] == 40.0

    # сбой реферти (None) -> всё A, генерация не падает
    scene3, conf3, wns3 = E.merge_scenes(
        "facade", A2, B2, cmp2, referee=lambda f: None)
    assert scene3["storeys"] == 5 and scene3["width_m"] == 20.0
    assert conf3["referee_used"] is False and wns3
    # входы не мутируются
    assert A2["storeys"] == 5 and B2["width_m"] == 40.0
    print("test_merge_average_and_referee OK")


def test_referee_prompt_shape():
    assert "A" in E.SYSTEM_REFEREE and "B" in E.SYSTEM_REFEREE
    s = {"windows": {"rows": 2}}
    assert E._get(s, "windows.rows") == 2
    E._set(s, "windows.rows", 3)
    assert s["windows"]["rows"] == 3
    print("test_referee_prompt_shape OK")


if __name__ == "__main__":
    test_compare_full_agreement()
    test_compare_disputes()
    test_skip_dispute_two_cells()
    test_merge_average_and_referee()
    test_referee_prompt_shape()
    print("ALL OK")
