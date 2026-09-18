# -*- coding: utf-8 -*-
"""3D Design: тесты фазы 1 (сборщик, сценарий, роутер, статика виджета)."""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TMP = ROOT / "tests" / "_threed_tmp"


def sample_scene():
    """Генплан 800x600: жилой 5 эт. (прямоуг.), школа 3 эт., земля."""
    return {
        "trace_width": 800, "trace_height": 600,
        "metres_per_trace_pixel": 0.25,
        "residential_storey_height": 3.1, "public_storey_height": 3.3,
        "sections": [
            {"id": "Ж-1", "building": "Ж-1", "use": "Residential", "floors": 5,
             "points_px": [[100, 100], [500, 100], [500, 300], [100, 300]]},
            {"id": "Ш-1", "building": "Ш-1", "use": "School", "floors": 3,
             "points_px": [[100, 400], [300, 400], [300, 550], [100, 550]]},
        ],
        "context": [
            {"kind": "Ground", "z": -0.45, "depth": 0.35,
             "points_px": [[0, 0], [800, 0], [800, 600], [0, 600]]},
        ],
    }


def test_build_genplan():
    import ifcopenshell
    from PIL import Image
    from threed.threed_build import build_genplan

    TMP.mkdir(exist_ok=True)
    img = Image.new("RGB", (800, 600), (245, 245, 240))
    ifc = TMP / "3D_plan_test.ifc"
    prev = TMP / "3D_plan_test_preview.png"
    path = build_genplan(sample_scene(), img, ifc, prev,
                         {"Scenario": "plan", "Prompt": "тест", "Model": "test/model",
                          "Source": "3D Design"})
    assert path == ifc and ifc.is_file() and prev.is_file()

    m = ifcopenshell.open(str(ifc))
    assert m.schema == "IFC4"
    gids = [r.GlobalId for r in m.by_type("IfcRoot")]
    assert len(gids) == len(set(gids)), "GlobalId не уникальны"
    assert len(m.by_type("IfcBuilding")) == 2          # Ж-1 и Ш-1
    assert len(m.by_type("IfcBuildingStorey")) == 5 + 3
    assert len(m.by_type("IfcBuildingElementProxy")) == 5 + 3
    assert len(m.by_type("IfcGeographicElement")) == 1  # Ground
    # объём первой секции: 400x200 px * 0.25 = 100x50 м -> 5000 м2 * 3.1
    from ifcopenshell.util.element import get_psets
    p = m.by_type("IfcBuildingElementProxy")[0]
    qto = get_psets(p).get("Qto_BuildingElementProxyQuantities", {})
    assert abs(qto.get("NetVolume", 0) - 5000 * 3.1) < 1.0
    # pset DevBIM у проекта
    proj = m.by_type("IfcProject")[0]
    assert get_psets(proj).get("DevBIM", {}).get("Scenario") == "plan"
    print("test_build_genplan OK")


if __name__ == "__main__":
    test_build_genplan()
    print("ALL OK")
