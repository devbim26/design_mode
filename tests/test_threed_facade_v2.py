# tests/test_threed_facade_v2.py
# -*- coding: utf-8 -*-
"""Фасад v2: детали (roof hip/mansard, dormers, chimneys, entrance, towers,
custom_parts, arched) — валидация + сборка + петля (задачи 1-5)."""
import importlib.util
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["THREED_VERIFY"] = "0"  # роутерные тесты петли включат сами

TMP = ROOT / "tests" / "_threed_tmp"


def _legacy():
    spec = importlib.util.spec_from_file_location(
        "_threed_legacy_samples", ROOT / "tests" / "test_threed.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def villa_raw():
    """Сырая (невалидированная) сцена «вилла» с полным набором v2-полей."""
    return {
        "storeys": 2, "floor_height": 4.0, "width_m": 9.5, "depth_m": 12.0,
        "roof": "hip", "roof_height": 1.8,
        "windows": {"rows": 2, "cols": 2, "w_m": 1.3, "h_m": 2.6,
                    "margin_x_m": 1.0, "margin_y_m": 0.5, "shape": "arched"},
        "dormers": [{"floor": 2, "x_m": 3.0, "w_m": 1.4, "h_m": 1.6},
                    {"floor": 2, "x_m": 6.5, "w_m": 1.4, "h_m": 1.6}],
        "chimneys": [{"x_m": 2.0, "floor": 2}],
        "entrance": {"x_m": 4.75, "w_m": 2.2, "style": "portico"},
        "towers": [{"x_m": -4.75, "w_m": 3.0, "depth_m": 3.0, "floors": 3,
                    "round": True, "roof": "cone", "roof_h_m": 2.0}],
        "custom_parts": [
            {"kind": "box", "size": [1.0, 0.6, 0.6], "pos": [2.0, -6.0, 4.5],
             "rot_deg": 0, "color": "plinth"},
            {"kind": "prism", "size": [2.0, 0.8, 0.9], "pos": [-2.5, -6.05, 5.0],
             "profile": [[-1.0, 0.0], [1.0, 0.0], [0.0, 0.9]], "color": "roof"},
            {"kind": "cone", "size": [1.2, 1.2, 1.0], "pos": [0.0, -5.9, 8.0],
             "color": "#8d8d8d"},
        ],
        "colors": {"walls": "#c5b58c", "roof": "#555b60", "plinth": "#8a8575"},
    }


def test_validate_facade_v2():
    from threed.threed_scenarios import validate_facade
    clean, warns = validate_facade(villa_raw())
    assert clean["roof"] == "hip" and clean["windows"]["shape"] == "arched"
    assert len(clean["dormers"]) == 2 and clean["dormers"][0]["floor"] == 2
    assert clean["chimneys"] == [{"x_m": 2.0, "floor": 2}]
    assert clean["entrance"]["style"] == "portico"
    t = clean["towers"][0]
    assert t["round"] is True and t["roof"] == "cone" and t["floors"] == 3
    assert len(clean["custom_parts"]) == 3
    assert clean["custom_parts"][2]["color"] == "#8d8d8d"

    # клампы и дропы
    bad = villa_raw()
    bad["dormers"] = [{"floor": 99, "x_m": 999.0, "w_m": 0.1, "h_m": 50.0}]
    clean2, warns2 = validate_facade(bad)
    assert clean2["dormers"][0]["floor"] == 2 and clean2["dormers"][0]["w_m"] == 0.6
    assert any("dormer" in w.lower() for w in warns2)

    bad = villa_raw()
    bad["entrance"] = {"style": "arch", "x_m": -99, "w_m": 99}
    clean3, warns3 = validate_facade(bad)
    assert clean3["entrance"]["style"] == "porch"
    assert any("entrance" in w for w in warns3)

    bad = villa_raw()
    bad["roof"] = "onion"
    bad["windows"]["shape"] = "round"
    clean4, warns4 = validate_facade(bad)
    assert clean4["roof"] == "flat" and clean4["windows"]["shape"] == "rect"

    # грамматика: мусорные части дропаются, >60 срезается
    bad = villa_raw()
    bad["custom_parts"] = [{"kind": "torus"}] + villa_raw()["custom_parts"] + \
        [{"kind": "box", "size": [1, 1, 1], "pos": [0, 0, 0]}] * 60
    clean5, warns5 = validate_facade(bad)
    assert len(clean5["custom_parts"]) == 60
    assert any("kind" in w for w in warns5) and any("больше 60" in w for w in warns5)

    # обратная совместимость: сцена v1 без новых полей
    L = _legacy()
    clean6, _ = validate_facade(L.sample_facade_scene())
    assert clean6.get("dormers") == [] and clean6.get("entrance") is None \
        and clean6.get("towers") == [] and clean6["windows"]["shape"] == "rect"
    print("test_validate_facade_v2 OK")


def test_validate_facade_v2_guards():
    from threed.threed_scenarios import validate_facade

    # не-списки вместо dormers/chimneys/towers -> дефолты + warnings, не TypeError
    bad = villa_raw()
    bad["dormers"] = {"floor": 2}
    bad["chimneys"] = 5
    bad["towers"] = "x"
    clean, warns = validate_facade(bad)
    assert clean["dormers"] == [] and clean["chimneys"] == [] and clean["towers"] == []
    assert any("dormers: не список" in w for w in warns)
    assert any("chimneys: не список" in w for w in warns)
    assert any("towers: не список" in w for w in warns)

    # переполнение: chimneys > 6, towers > 4 — срез + warning
    over = villa_raw()
    over["chimneys"] = [{"x_m": float(i), "floor": 2} for i in range(7)]
    over["towers"] = [{"x_m": -4.0, "w_m": 3.0, "depth_m": 3.0, "floors": 3,
                       "roof": "cone", "roof_h_m": 2.0} for _ in range(5)]
    clean2, warns2 = validate_facade(over)
    assert len(clean2["chimneys"]) == 6
    assert len(clean2["towers"]) == 4
    assert any("chimneys: больше 6" in w for w in warns2)
    assert any("towers: больше 4" in w for w in warns2)
    print("test_validate_facade_v2_guards OK")


def test_build_facade_v2_hip():
    import ifcopenshell
    from threed.threed_scenarios import validate_facade
    from threed.threed_build import build_facade
    clean, _ = validate_facade(villa_raw())
    clean["roof"] = "hip"
    TMP.mkdir(exist_ok=True)
    ifc = TMP / "3D_v2_hip.ifc"
    prev = TMP / "3D_v2_hip_preview.png"
    build_facade(clean, ifc, prev, {"Scenario": "facade"})
    m = ifcopenshell.open(str(ifc))
    roofs = [p for p in m.by_type("IfcBuildingElementProxy")
             if p.ObjectType == "CONCEPTUAL_ROOF"]
    assert len(roofs) == 1
    item = roofs[0].Representation.Representations[0].Items[0]
    assert item.is_a("IfcPolygonalFaceSet") and len(item.Faces) >= 4
    assert prev.is_file()
    # helpers
    from threed.threed_build import _hull, _ring
    pts, faces = _hull([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [.5, .5, 1]])
    assert all(isinstance(i, int) for f in faces for i in f) and len(_ring(1.0, 0.0)) == 16
    print("test_build_facade_v2_hip OK")


if __name__ == "__main__":
    test_validate_facade_v2()
    test_validate_facade_v2_guards()
    test_build_facade_v2_hip()
    print("ALL OK")
