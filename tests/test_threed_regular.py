# -*- coding: utf-8 -*-
"""Регуляризация по темам (з.4): гейт agree_rate, снапы, симметрия,
RDP/ортогонализация (plan/interior — Task 9)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from threed import threed_regular as RG  # noqa: E402


def _facade(skip):
    return {"storeys": 5, "floor_height": 3.02, "width_m": 20.0,
            "windows": {"rows": 2, "cols": 4, "w_m": 1.52, "h_m": 1.48,
                        "margin_x_m": 1.03, "margin_y_m": 0.81,
                        "skip": skip, "shape": "rect"}}


def test_gate():
    conf = {"agree_rate": 0.7}
    wn = []
    RG.regularize("facade", _facade([[False] * 4] * 2), conf, wn)
    assert not any("skipped" in w for w in wn)
    conf2 = {"agree_rate": 0.69}
    RG.regularize("facade", _facade([[False] * 4] * 2), conf2, wn)
    assert any("regularization skipped: low ensemble agreement" in w
               for w in wn), wn
    # scene-сценарий не регуляризуется вообще
    wn2 = []
    RG.regularize("scene", {"camera": {}}, {"agree_rate": 1.0}, wn2)
    assert not wn2
    print("test_gate OK")


def test_snaps():
    s = RG.regularize_facade(_facade([[False] * 4] * 2))
    assert s["floor_height"] == 3.0
    assert s["windows"]["w_m"] == 1.5 and s["windows"]["h_m"] == 1.5
    assert s["windows"]["margin_x_m"] == 1.05 and s["windows"]["margin_y_m"] == 0.8
    print("test_snaps OK")


def test_symmetry_mirror():
    # правило: в строке с |L-R|/max <= 10% (L/R = окна в половинах) половина
    # с МЕНЬШИМ числом окон зеркалится на большую; перевес > 10% ("намеренная
    # асимметрия") и нечётный средний столбец — не трогаются
    # [0,1,1,1]: L=1, R=2, перевес 0.5 -> не трогаем
    s = RG.regularize_facade(_facade([[False, True, True, True]]))
    assert s["windows"]["skip"] == [[False, True, True, True]], "не трогаем"
    # [0,1,1,0]: L=1, R=1, уже симметрична -> без изменений
    s2 = RG.regularize_facade(_facade([[False, True, True, False]]))
    assert s2["windows"]["skip"] == [[False, True, True, False]]
    # [1,1,1,0]: L=2, R=1, перевес 0.5 -> не трогаем
    s3 = RG.regularize_facade(_facade([[True, True, True, False]]))
    assert s3["windows"]["skip"] == [[True, True, True, False]]
    # [0,1,0,1]: L=1, R=1 (в допуске), половины [0,1]/[0,1] разные ->
    # правая зеркалится на левую -> [0,1,1,0]
    s4 = RG.regularize_facade(_facade([[False, True, False, True]]))
    assert s4["windows"]["skip"] == [[False, True, True, False]], s4
    # [0,1,1,0]: L=1, R=1, половины уже зеркальны -> без изменений
    s5 = RG.regularize_facade(_facade([[False, True, True, False]]))
    assert s5["windows"]["skip"] == [[False, True, True, False]]
    print("test_symmetry_mirror OK")


def test_rdp_orthogonalize():
    # RDP: коллинеарная точка выбрасывается
    pts = [[0, 0], [5, 0], [10, 0], [10, 10]]
    assert RG.rdp(pts, eps=0.5) == [[0, 0], [10, 0], [10, 10]]
    # ортогонализация: ребро 88° снапится к 90°, эркер 67.5° не трогается
    nearly = [[0, 0], [100, 0], [100, -3], [100, 100]]  # ребро ~88.3°
    fixed = RG.orthogonalize(nearly, tol_deg=15.0, step_deg=90.0)
    assert fixed[2] == [100, 0], fixed  # снап к горизонтальному ребру
    bay = [[0, 0], [38, 0], [52, -16], [66, 0], [104, 0], [104, 50],
           [0, 50]]  # рёбра эркера ~66-68°
    same = RG.orthogonalize(bay, tol_deg=15.0, step_deg=90.0)
    assert same == bay, "эркер вне допуска 15° — не трогаем"
    print("test_rdp_orthogonalize OK")


def test_regularize_plan():
    scene = {"metres_per_trace_pixel": 0.25,
             "sections": [
                 # верхнее ребро с дрожью 1 px (угол ~0.7° < 15° -> снап к 0°)
                 {"id": "A", "floors": 5, "points_px": [
                     [100, 100], [350, 100], [420, 100], [500, 101],
                     [500, 300], [100, 300]]},
                 # 10 вершин с коллинеарным шумом на верхней грани -> RDP
                 {"id": "C", "floors": 2, "points_px": [
                     [600, 100], [650, 101], [700, 100], [750, 99],
                     [800, 100], [800, 300], [750, 300], [700, 300],
                     [650, 300], [600, 300]]},
                 {"id": "B", "floors": 3, "points_px": [
                     [200, 200], [420, 200], [420, 380], [200, 380]]},
             ]}
    s = RG.regularize("plan", scene, {"agree_rate": 0.9}, [])
    pts = s["sections"][0]["points_px"]
    # дрожавшее ребро стало горизонтальным (все y верхней грани ~100)
    top = pts[:4]
    assert max(abs(p[1] - 100) for p in top) < 1.0, top
    # RDP упростил 10-вершинный контур (коллинеарный шум снят)
    assert len(s["sections"][1]["points_px"]) <= 6, \
        s["sections"][1]["points_px"]
    # пересечение футпринтов снято: B минус A/C (порядок обхода секций)
    from shapely.geometry import Polygon
    polys = [Polygon(sec["points_px"]) for sec in s["sections"]]
    for i in range(len(polys)):
        for j in range(i + 1, len(polys)):
            assert polys[i].intersection(polys[j]).area <= 1.0, \
                f"секции {i} и {j} пересекаются"
    print("test_regularize_plan OK")


def test_regularize_interior():
    scene = {"walls": [  # стена ~50° -> снап к 45° (tan=1); горизонтальная
                          # перегородка не трогается
                       {"points_px": [[0, 0], [100, 119]], "thickness_m": 0.2,
                        "exterior": True},
                      {"points_px": [[0, 0], [200, 0]], "thickness_m": 0.2,
                       "exterior": False}],
             "rooms": [{"name": "R", "type": "other",
                        "points_px": [[0, 0], [100, 0], [100, 100],
                                      [50, 150], [0, 100]]}],
             "openings": []}
    s = RG.regularize("interior", scene, {"agree_rate": 0.9}, [])
    w = s["walls"][0]
    dx = w["points_px"][1][0] - w["points_px"][0][0]
    dy = w["points_px"][1][1] - w["points_px"][0][1]
    assert abs(dy / dx - 1.0) < 0.02, "50° -> 45° (tan=1)"
    # толщины: кламп в диапазоны спеки (наружная -> 0.3..0.4, перегородка
    # -> 0.1..0.15), а не только замена «близких»
    assert 0.3 <= s["walls"][0]["thickness_m"] <= 0.4
    assert 0.1 <= s["walls"][1]["thickness_m"] <= 0.15
    # комната остаётся валидным полигоном после buffer(0)
    from shapely.geometry import Polygon
    p = Polygon(s["rooms"][0]["points_px"])
    assert p.is_valid or p.buffer(0).is_valid
    print("test_regularize_interior OK")


if __name__ == "__main__":
    test_gate()
    test_snaps()
    test_symmetry_mirror()
    test_rdp_orthogonalize()
    test_regularize_plan()
    test_regularize_interior()
    print("ALL OK")
