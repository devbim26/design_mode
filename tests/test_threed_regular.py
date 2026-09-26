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


if __name__ == "__main__":
    test_gate()
    test_snaps()
    test_symmetry_mirror()
    test_rdp_orthogonalize()
    print("ALL OK")
