# -*- coding: utf-8 -*-
"""3D Design: тесты фазы 1 (сборщик, сценарий, роутер, статика виджета)."""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import os
os.environ["THREED_VERIFY"] = "0"  # ретро-тесты: без второй VLM-генерации
# (самопроверка — tests/test_threed_verify.py; тут моки считают вызовы)
os.environ["THREED_ENSEMBLE"] = "0"  # ретро-тесты: без прогона B (п.60)

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


def sample_facade_scene():
    """Фасад: 5 эт. × 3.0 м, 24×12 м, двускатная крыша 2.5 м, окна 1 ряд по 4
    (второе пропущено на всех этажах), балконы на 2 и 3 этаже."""
    return {
        "storeys": 5, "floor_height": 3.0, "width_m": 24.0, "depth_m": 12.0,
        "roof": "gable", "roof_height": 2.5,
        "windows": {"rows": 1, "cols": 4, "w_m": 1.5, "h_m": 1.5,
                    "margin_x_m": 1.0, "margin_y_m": 0.7,
                    "skip": [[False, True, False, False]]},
        "balconies": [{"floor": 2, "x_m": 4.0, "w_m": 3.0, "d_m": 1.2},
                      {"floor": 3, "x_m": 4.0, "w_m": 3.0, "d_m": 1.2}],
        "colors": {"walls": "#d9c7a7", "roof": "#52616b", "plinth": "#8d8d8d"},
    }


def sample_interior_scene():
    """Интерьер: прямоугольник 40×30 px-контур (scale 0.25 м/px -> 10×7.5 м),
    внутренняя стена с дверью, окно на контуре, 2 комнаты, кровать 90°."""
    return {
        "trace_width": 40, "trace_height": 30, "metres_per_trace_pixel": 0.25,
        "wall_height": 2.7,
        "outline": [[2, 2], [38, 2], [38, 28], [2, 28]],
        "walls": [
            {"points_px": [[2, 2], [38, 2]], "thickness_m": 0.4, "exterior": True},
            {"points_px": [[38, 2], [38, 28]], "thickness_m": 0.4, "exterior": True},
            {"points_px": [[38, 28], [2, 28]], "thickness_m": 0.4, "exterior": True},
            {"points_px": [[2, 28], [2, 2]], "thickness_m": 0.4, "exterior": True},
            {"points_px": [[20, 2], [20, 28]], "thickness_m": 0.15, "exterior": False},
        ],
        "openings": [
            {"wall_idx": 0, "x_px": 6, "width_m": 0.9, "height_m": 2.1,
             "sill_m": 0.0, "kind": "door"},
            {"wall_idx": 1, "x_px": 12, "width_m": 1.4, "height_m": 1.5,
             "sill_m": 0.9, "kind": "window"},
            {"wall_idx": "outline", "x_px": 4, "width_m": 0.9, "height_m": 2.1,
             "sill_m": 0.0, "kind": "door"},
        ],
        "rooms": [
            {"name": "Кухня", "type": "kitchen",
             "points_px": [[2, 2], [20, 2], [20, 28], [2, 28]]},
            {"name": "Спальня", "type": "bedroom",
             "points_px": [[20, 2], [38, 2], [38, 28], [20, 28]]},
        ],
        "furniture": [
            {"type": "bed", "x_px": 10, "y_px": 20, "w_m": 2.0, "d_m": 1.6,
             "h_m": 0.5, "rot_deg": 90},
            {"type": "table", "x_px": 29, "y_px": 20, "w_m": 1.2, "d_m": 0.8,
             "h_m": 0.75, "rot_deg": 0},
        ],
    }


def test_build_interior():
    import ifcopenshell
    from ifcopenshell.util.element import get_psets
    from ifcopenshell.util.placement import get_local_placement
    from threed.threed_build import build_interior

    TMP.mkdir(exist_ok=True)
    ifc = TMP / "3D_interior_test.ifc"
    prev = TMP / "3D_interior_test_preview.png"
    path = build_interior(sample_interior_scene(), ifc, prev,
                          {"Scenario": "interior", "Prompt": "тест",
                           "Model": "test/model", "Source": "3D Design"})
    assert path == ifc and ifc.is_file() and prev.is_file()

    m = ifcopenshell.open(str(ifc))
    assert m.schema == "IFC4"
    gids = [r.GlobalId for r in m.by_type("IfcRoot")]
    assert len(gids) == len(set(gids)), "GlobalId не уникальны"
    assert len(m.by_type("IfcSlab")) == 1                    # плита пола
    assert len(m.by_type("IfcWall")) == 5                    # 5 сегментов
    assert len(m.by_type("IfcSpace")) == 2                   # комнаты
    space_names = sorted(s.Name for s in m.by_type("IfcSpace"))
    assert space_names == ["Кухня", "Спальня"]               # имена с плана
    # все IfcSpace в одном сторе
    assert len(m.by_type("IfcBuildingStorey")) == 1
    # проёмы в стенах — настоящие IfcDoor/IfcWindow в IfcOpeningElement;
    # на контуре (wall_idx="outline") — прокси без стены-носителя
    proxies = [p for p in m.by_type("IfcBuildingElementProxy")]
    kinds = {}
    for p in proxies:
        kinds[p.ObjectType] = kinds.get(p.ObjectType, 0) + 1
    assert kinds.get("CONCEPTUAL_DOOR") == 1                 # дверь на контуре
    assert kinds.get("CONCEPTUAL_WINDOW") is None
    assert len(m.by_type("IfcDoor")) == 1                    # дверь в стене 0
    assert len(m.by_type("IfcWindow")) == 1                  # окно в стене 1
    assert len(m.by_type("IfcOpeningElement")) == 2
    assert len(m.by_type("IfcRelVoidsElement")) == 2
    assert len(m.by_type("IfcRelFillsElement")) == 2
    furn = m.by_type("IfcFurnishingElement")
    assert len(furn) == 2
    ftypes = sorted(f.ObjectType for f in furn)
    assert ftypes == ["FURNITURE_BED", "FURNITURE_TABLE"]
    # кровать повёрнута на 90° (в сборке Rz(-90) из-за Y-флипа):
    # mat = [[0,1,0],[-1,0,0],…] -> mat[0,0]≈0, mat[1,0]≈-1
    bed = [f for f in furn if f.ObjectType == "FURNITURE_BED"][0]
    mat = get_local_placement(bed.ObjectPlacement)
    assert abs(mat[0, 0] - 0.0) < 1e-6 and abs(mat[1, 0] - (-1.0)) < 1e-6, \
        "кровать должна быть повёрнута Rz(-90)"
    # pset DevBIM у проекта + InteriorModel у здания
    assert get_psets(m.by_type("IfcProject")[0]).get("DevBIM", {}).get("Scenario") \
        == "interior"
    fm = get_psets(m.by_type("IfcBuilding")[0]).get("InteriorModel", {})
    assert fm.get("WallHeight") == 2.7 and fm.get("Rooms") == 2 \
        and fm.get("Furniture") == 2
    print("test_build_interior OK")


def test_interior_wall_palette():
    import ifcopenshell
    from ifcopenshell.util.element import get_psets
    from threed.threed_build import (build_interior, INTERIOR_WALL_PALETTE,
                                     wall_palette_key, INTERIOR_COLOR_LEGEND)

    scene = sample_interior_scene()
    # сектор в МЕТРАХ плана (Y-флип учтён), ось двунаправленная -> 4 корзины
    assert wall_palette_key(scene, scene["walls"][0]) == ("ext", "X")   # [2,2]->[38,2]
    assert wall_palette_key(scene, scene["walls"][1]) == ("ext", "Y")   # [38,2]->[38,28]
    assert wall_palette_key(scene, scene["walls"][4]) == ("int", "Y")   # перегородка
    diag = dict(scene)
    # (отклонение от брифа: [[0,0],[10,10]] в метрах плана — диагональ ↘, -45° -> D135;
    # фикстура заменена на ↗ +45° ([0,28]->[10,18]: юго-запад -> северо-восток),
    # чтобы выполнялся ассерт брифа ("int", "D45") при вербатим-реализации)
    diag["walls"] = [{"points_px": [[0, 28], [10, 18]], "thickness_m": 0.2,
                      "exterior": False}]
    assert wall_palette_key(diag, diag["walls"][0]) == ("int", "D45")

    TMP.mkdir(exist_ok=True)
    ifc = TMP / "3D_interior_palette.ifc"
    prev = TMP / "3D_interior_palette_preview.png"
    build_interior(scene, ifc, prev, {"Scenario": "interior", "Prompt": "тест",
                                      "Model": "test/model", "Source": "3D Design"})
    assert ifc.is_file() and prev.is_file()

    m = ifcopenshell.open(str(ifc))

    def style_name(product):
        item = product.Representation.Representations[0].Items[0]
        return item.StyledByItem[0].Styles[0].Name

    walls = m.by_type("IfcWall")
    assert len(walls) == 5
    names = sorted(w.Name for w in walls)
    assert any("наружная В-З" in n for n in names), names
    assert any("перегородка С-Ю" in n for n in names), names
    assert not any("нар." in n for n in names), "старый суффикс «нар.» должен уйти"
    # каждой стене — свой стиль по типу×ориентации
    assert {style_name(w) for w in walls} == {"WallExtX", "WallExtY", "WallIntY"}

    # двери — один стиль, окна — голубые полупрозрачные: заполнения
    # IfcDoor/IfcWindow в стенах + дверь-прокси на контуре
    proxies = m.by_type("IfcBuildingElementProxy")
    doors = [p for p in proxies if p.ObjectType == "CONCEPTUAL_DOOR"]
    wins = [p for p in proxies if p.ObjectType == "CONCEPTUAL_WINDOW"]
    ifc_doors, ifc_wins = m.by_type("IfcDoor"), m.by_type("IfcWindow")
    assert len(doors) == 1 and wins == [] and len(ifc_doors) == 1 \
        and len(ifc_wins) == 1
    assert {style_name(p) for p in doors + ifc_doors} == {"Door"}
    assert {style_name(p) for p in ifc_wins} == {"Window"}
    shading = [s for s in m.by_type("IfcSurfaceStyleShading")
               if s.SurfaceColour.Name == "window"][0]
    assert abs(shading.Transparency - 0.55) < 1e-6, "окно должно быть прозрачным"
    # web-ifc (вьювер) читает Transparency только с подтипа IfcSurfaceStyleRendering:
    # базовому Shading цвет берёт, альфу молча игнорирует (окно видно сплошным)
    assert shading.is_a("IfcSurfaceStyleRendering"), \
        "прозрачность окна должна ехать на IfcSurfaceStyleRendering"
    col = shading.SurfaceColour
    assert abs(col.Red - 0xA8 / 255) < 0.02 and abs(col.Blue - 0xEA / 255) < 0.02 \
        and abs(col.Green - 0xD4 / 255) < 0.02, "окно должно быть голубым #A8D4EA"

    # цвет WallExtX = терракота #C2765B; одноимённые сектора ext/int различаются
    def surf_rgb(style_name_):
        st = [s for s in m.by_type("IfcSurfaceStyle") if s.Name == style_name_][0]
        c = st.Styles[0].SurfaceColour
        return (c.Red, c.Green, c.Blue)
    import matplotlib.colors as _mc
    for name, hexc in (("WallExtX", "#C2765B"), ("WallIntX", "#E8C9B8")):
        want = _mc.to_rgb(hexc)
        got = surf_rgb(name)
        assert all(abs(a - b) < 0.02 for a, b in zip(want, got)), (name, got)
    assert len(INTERIOR_WALL_PALETTE) == 8

    # легенда едет с файлом
    pset = get_psets(m.by_type("IfcBuilding")[0]).get("InteriorModel", {})
    assert INTERIOR_COLOR_LEGEND[:40] in (pset.get("ColorLegend") or ""), pset
    print("test_interior_wall_palette OK")


def test_interior_real_openings():
    """Настоящие проёмы (фикс 24.09): IfcOpeningElement режет стену,
    IfcWindow/IfcDoor сидят внутри проёма; посадка клампится в габарит
    сегмента; огрызки (<0,6 м) проёмов не держат. Живой кейс до фикса:
    окно за торцом стены на 0,2 м, дверь на огрызке 0,2 м под 90°."""
    import ifcopenshell
    import numpy as np
    from ifcopenshell.util.placement import get_local_placement
    from threed.threed_build import build_interior

    # стена 0: 8 м; стена 1: огрызок 0,32 м (2×0,16 м/px)
    scene = {
        "trace_width": 40, "trace_height": 30, "metres_per_trace_pixel": 0.16,
        "wall_height": 2.7,
        "outline": [[2, 2], [38, 2], [38, 28], [2, 28]],
        "walls": [
            {"points_px": [[2, 2], [52, 2]], "thickness_m": 0.4, "exterior": True},
            {"points_px": [[4, 28], [6, 28]], "thickness_m": 0.3, "exterior": True},
        ],
        "openings": [
            # окно шире остатка до правого торца: центр заx_px=45 (7,2 м) у
            # конца стены 8 м -> кламп центра, проём целиком в сегменте
            {"wall_idx": 0, "x_px": 45, "width_m": 2.0, "height_m": 1.5,
             "sill_m": 0.9, "kind": "window"},
            # дверь на огрызке 0,32 м — должна выброситься
            {"wall_idx": 1, "x_px": 1, "width_m": 0.9, "height_m": 2.1,
             "sill_m": 0.0, "kind": "door"},
        ],
        "rooms": [], "furniture": [],
    }
    TMP.mkdir(exist_ok=True)
    ifc = TMP / "3D_interior_openings_test.ifc"
    prev = TMP / "3D_interior_openings_test_preview.png"
    build_interior(scene, ifc, prev, {"Scenario": "interior", "Prompt": "тест",
                                      "Model": "test/model", "Source": "3D Design"})
    m = ifcopenshell.open(str(ifc))

    # огрызок не держит проём: 1 окно, 0 дверей, 1+1 voids/fills
    assert len(m.by_type("IfcWindow")) == 1
    assert len(m.by_type("IfcDoor")) == 0
    assert len(m.by_type("IfcOpeningElement")) == 1
    assert len(m.by_type("IfcRelVoidsElement")) == 1
    assert len(m.by_type("IfcRelFillsElement")) == 1
    rel = m.by_type("IfcRelVoidsElement")[0]
    assert rel.RelatingBuildingElement.is_a("IfcWall")
    assert rel.RelatedOpeningElement.is_a("IfcOpeningElement")
    assert m.by_type("IfcRelFillsElement")[0].RelatedBuildingElement.is_a("IfcWindow")

    # геометрия: окно внутри проёма, глубина стекла меньше толщины стены,
    # посадка в сегменте (стена от x=0,32 до 8,32 м при y≈0,32; вдоль X)
    wall = rel.RelatingBuildingElement
    win = m.by_type("IfcWindow")[0]
    op = m.by_type("IfcOpeningElement")[0]

    def box(el):
        mat = get_local_placement(el.ObjectPlacement)
        pts = el.Representation.Representations[0].Items[0] \
            .SweptArea.OuterCurve.Points.CoordList
        xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
        return ((mat[0, 3], mat[1, 3], mat[2, 3]),
                max(xs) - min(xs), max(ys) - min(ys),
                el.Representation.Representations[0].Items[0].Depth)

    (wx, wy, wz), wbw, wbd, wdep = box(wall)
    (ox, oy, oz), obw, obd, odep = box(op)
    (vx, vy, vz), vbw, vbd, vdep = box(win)
    wall_t = wbd
    # коробка проёма режет стену насквозь с запасом, стекло — внутри стены
    assert obd > wall_t and abs(obd - wall_t - 0.02) < 1e-6
    assert vbd < wall_t and abs(vbd - min(wall_t - 0.04, 0.08)) < 1e-6, \
        "стекло не должно выступать за плоскости стены"
    # центр вдоль стены: x_px=45*0.16=7,2 м; конец стены 8,32-0,32=8,0 м
    # от p1; кламп центра: 8,0 - 2,0/2 - 0,05 = 6,95 -> мировой x = 0,32+6,95
    assert abs(ox - (0.32 + 6.95)) < 1e-3, (ox, ox - 0.32)
    assert abs(vx - ox) < 1e-6 and abs(vy - oy) < 1e-6
    lo, hi = ox - obw / 2, ox + obw / 2
    assert 0.32 - 1e-6 <= lo and hi <= 8.32 + 1e-6, (lo, hi)
    print("test_interior_real_openings OK")


def test_build_facade():
    import ifcopenshell
    from threed.threed_build import build_facade

    TMP.mkdir(exist_ok=True)
    ifc = TMP / "3D_facade_test.ifc"
    prev = TMP / "3D_facade_test_preview.png"
    path = build_facade(sample_facade_scene(), ifc, prev,
                        {"Scenario": "facade", "Prompt": "тест", "Model": "test/model",
                         "Source": "3D Design"})
    assert path == ifc and ifc.is_file() and prev.is_file()

    m = ifcopenshell.open(str(ifc))
    assert m.schema == "IFC4"
    gids = [r.GlobalId for r in m.by_type("IfcRoot")]
    assert len(gids) == len(set(gids)), "GlobalId не уникальны"
    assert len(m.by_type("IfcBuilding")) == 1
    assert len(m.by_type("IfcBuildingStorey")) == 5
    proxies = m.by_type("IfcBuildingElementProxy")
    by_type = {}
    for p in proxies:
        by_type[p.ObjectType] = by_type.get(p.ObjectType, 0) + 1
    assert by_type.get("CONCEPTUAL_STOREY") == 5            # поэтажные тома
    assert by_type.get("CONCEPTUAL_WINDOW") == 3 * 5        # 4 минус skip, на этаж
    assert by_type.get("CONCEPTUAL_BALCONY") == 2
    # балкон этажа k стоит на уровне ПОЛА этого этажа: верх плиты (k-1)*fh
    # (регресс: раньше строились на этаж выше — floor*fh)
    from ifcopenshell.util.placement import get_local_placement
    bal2 = [p for p in proxies if p.ObjectType == "CONCEPTUAL_BALCONY"
            and "этаж 2" in (p.Name or "")][0]
    win1 = [p for p in proxies if p.ObjectType == "CONCEPTUAL_WINDOW"][0]
    assert abs(get_local_placement(bal2.ObjectPlacement)[2, 3] - (1 * 3.0 - 0.18)) < 1e-6
    # спека A1: мировой центр балкона = x_m - width/2 (4.0 - 12.0 = -8.0)
    assert abs(get_local_placement(bal2.ObjectPlacement)[0, 3] - (4.0 - 24.0 / 2)) < 1e-6
    # спека A4: фасад на IFC -Y (окна/балконы на отрицательной стороне Y)
    assert abs(get_local_placement(win1.ObjectPlacement)[1, 3] - (-12.0 / 2)) < 1e-6
    assert abs(get_local_placement(bal2.ObjectPlacement)[1, 3]
               - (-(12.0 / 2 + 1.2 / 2))) < 1e-6
    assert by_type.get("CONCEPTUAL_PLINTH") == 1
    assert by_type.get("CONCEPTUAL_ROOF") == 1              # двускатная призма
    # этажи на своих отметках
    elev = sorted(s.Elevation for s in m.by_type("IfcBuildingStorey"))
    assert elev == [0.0, 3.0, 6.0, 9.0, 12.0]
    # объём первого этажа: 24 × 12 × 3 = 864 м³
    from ifcopenshell.util.element import get_psets
    storey1 = [p for p in proxies if p.ObjectType == "CONCEPTUAL_STOREY"][0]
    qto = get_psets(storey1).get("Qto_BuildingElementProxyQuantities", {})
    assert abs(qto.get("NetVolume", 0) - 24 * 12 * 3.0) < 1.0
    # pset DevBIM у проекта + FacadeModel у здания
    assert get_psets(m.by_type("IfcProject")[0]).get("DevBIM", {}).get("Scenario") == "facade"
    b = m.by_type("IfcBuilding")[0]
    fm = get_psets(b).get("FacadeModel", {})
    assert fm.get("Storeys") == 5 and fm.get("WindowsTotal") == 15
    print("test_build_facade OK")


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


def test_extract_json():
    from threed.threed_scenarios import extract_json
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('Вот ответ: {"a": [1,2]} конец.') == {"a": [1, 2]}
    assert extract_json("никакого json нет") is None
    print("test_extract_json OK")


def test_validate_genplan():
    from threed.threed_scenarios import validate_genplan
    # валидная сцена проходит, дефолты проставлены
    s = sample_scene()
    s.pop("residential_storey_height")
    out, warn = validate_genplan(s, 800, 600)
    assert out["residential_storey_height"] == 3.1
    assert len(out["sections"]) == 2
    # координаты за пределами картинки клампятся
    s = sample_scene()
    s["sections"][0]["points_px"] = [[-50, 100], [900, 100], [900, 300], [-50, 300]]
    out, warn = validate_genplan(s, 800, 600)
    xs = [p[0] for p in out["sections"][0]["points_px"]]
    assert min(xs) >= 0 and max(xs) <= 800
    # битая секция выкидывается с warning
    s = sample_scene()
    s["sections"][1]["points_px"] = [[1, 1]]  # мало точек
    out, warn = validate_genplan(s, 800, 600)
    assert len(out["sections"]) == 1 and any("Ш-1" in w for w in warn)
    # этажность клампится 1..30
    s = sample_scene()
    s["sections"][0]["floors"] = 99
    out, _ = validate_genplan(s, 800, 600)
    assert out["sections"][0]["floors"] == 30
    # неизвестный kind контекста выкидывается
    s = sample_scene()
    s["context"].append({"kind": "Beach", "z": 0, "depth": 0.1,
                         "points_px": [[0, 0], [10, 0], [10, 10], [0, 10]]})
    out, warn = validate_genplan(s, 800, 600)
    assert len(out["context"]) == 1 and any("Beach" in w for w in warn)
    print("test_validate_genplan OK")


def test_validate_facade():
    from threed.threed_scenarios import validate_facade
    # валидная сцена проходит без изменений структуры
    out, warn = validate_facade(sample_facade_scene())
    assert out["storeys"] == 5 and out["windows"]["cols"] == 4
    assert out["windows"]["skip"] == [[False, True, False, False]]
    # дефолты на пустых полях
    out, warn = validate_facade({"storeys": 3})
    assert out["floor_height"] == 3.0 and out["windows"]["cols"] == 3
    assert out["depth_m"] == 12.0 and out["roof"] == "flat"
    # клампы
    out, warn = validate_facade({"storeys": 99, "floor_height": 9.0, "width_m": 500.0})
    assert out["storeys"] == 30 and out["floor_height"] == 6.0 and out["width_m"] == 200.0
    # крыша вне белого списка -> flat + warning (v2: hip/mansard уже валидны)
    out, warn = validate_facade({"storeys": 2, "roof": "onion", "roof_height": 1.0})
    assert out["roof"] == "flat" and any("onion" in w for w in warn)
    # FIT: окна не влезают по ширине -> w_m сжат
    s = {"storeys": 2, "width_m": 10.0,
         "windows": {"rows": 1, "cols": 4, "w_m": 3.0, "h_m": 1.5,
                     "margin_x_m": 1.0, "margin_y_m": 0.5}}
    out, warn = validate_facade(s)
    assert abs(out["windows"]["w_m"] - (10.0 - 2.0) / 4) < 1e-9
    assert any("w_m" in w for w in warn)
    # skip неправильной формы -> all False + warning
    s = sample_facade_scene()
    s["windows"]["skip"] = [[True], [True, False]]
    out, warn = validate_facade(s)
    assert out["windows"]["skip"] == [[False] * 4]
    assert any("skip" in w for w in warn)
    # балкон с этажем вне диапазона выкидывается; центр вне фасада —
    # клампится, балкон сохраняется (спека A2: «Балконы сохраняем»)
    s = sample_facade_scene()
    s["balconies"] = [{"floor": 9, "x_m": 4, "w_m": 3, "d_m": 1},
                      {"floor": 1, "x_m": 40, "w_m": 3, "d_m": 1}]
    out, warn = validate_facade(s)
    assert len(out["balconies"]) == 1 and out["balconies"][0]["x_m"] == 22.5
    assert len(warn) >= 2
    # цвет не hex -> дефолт + warning
    s = sample_facade_scene()
    s["colors"] = {"walls": "red"}
    out, warn = validate_facade(s)
    assert out["colors"]["walls"] == "#c8b89a" and any("walls" in w for w in warn)
    # не dict / пустышка -> ValueError
    for bad in ([1, 2], {"prompt": "x"}, None):
        try:
            validate_facade(bad)
            raise AssertionError("ожидалась ошибка")
        except ValueError:
            pass
    # фаза 2, ревью: поля съедают фасад -> поля сжаты, w_m положителен
    out, warn = validate_facade({"storeys": 2, "width_m": 3.0,
                                 "windows": {"cols": 4, "margin_x_m": 5.0}})
    assert out["windows"]["w_m"] >= 0.3 and out["windows"]["margin_x_m"] <= 1.05
    # фаза 2, ревью: не-dict/не-список из VLM -> деградация, не краш
    out, warn = validate_facade({"storeys": 2, "windows": ["x"], "balconies": 5,
                                 "colors": ["y"]})
    assert out["windows"]["cols"] == 3 and out["balconies"] == []
    assert out["colors"]["walls"] == "#c8b89a"
    assert sum(1 for w in warn if "дефолт" in w or "пропущены" in w) >= 3
    print("test_validate_facade OK")


def test_validate_interior():
    from threed.threed_scenarios import validate_interior, SYSTEM_INTERIOR
    assert "furniture" in SYSTEM_INTERIOR and "wall_height" in SYSTEM_INTERIOR

    scene = sample_interior_scene()
    out, warn, issues = validate_interior(scene, 40, 30)
    assert out["trace_width"] == 40 and out["trace_height"] == 30
    assert out["wall_height"] == 2.7 and len(out["walls"]) == 5
    assert len(out["openings"]) == 3 and out["openings"][0]["kind"] == "door"
    assert [r["name"] for r in out["rooms"]] == ["Кухня", "Спальня"]
    assert out["furniture"][0]["type"] == "bed"
    assert warn == []
    assert issues == []  # контракт посадки (п.56): чистый сэмпл без нарушений

    # не-dict / пустая сцена -> ValueError
    for bad in (None, [], {}, {"rooms": []}):
        try:
            validate_interior(bad, 100, 100)
            raise AssertionError("ожидалась ошибка для " + repr(bad))
        except ValueError:
            pass

    # дефолты: масштаб/высота/толщина; мусорные поля выбрасываются
    out2, warn2, issues2 = validate_interior({"outline": [[0, 0], [99, 0], [99, 99], [0, 99]],
                                              "walls": [
                                                  {"points_px": [[0, 0], [99, 0]],
                                                   "thickness_m": "мусор", "exterior": True},
                                                  {"points_px": [[0, 0]], "thickness_m": 0.1},
                                                  {"points_px": [[0, 0], [1, 0]],
                                                   "thickness_m": 99.0}],
                                              "openings": [
                                                  {"wall_idx": 7, "x_px": 5, "width_m": 1.0,
                                                   "height_m": 2.0, "sill_m": 0, "kind": "door"},
                                                  {"wall_idx": 0, "x_px": 50, "width_m": 1.0,
                                                   "height_m": 2.0, "sill_m": 0, "kind": "window"}],
                                              "rooms": [{"name": 123, "type": "sauna",
                                                         "points_px": [[1, 1], [9, 1], [9, 9], [1, 9]]}],
                                              "furniture": [
                                                  {"type": "spaceship", "x_px": 5, "y_px": 5,
                                                   "w_m": 2.0, "d_m": 2.0, "h_m": 1.0,
                                                   "rot_deg": 900}]},
                                             100, 100)
    assert abs(out2["metres_per_trace_pixel"] - 0.01) < 1e-9   # дефолт
    assert out2["wall_height"] == 2.7
    assert len(out2["walls"]) == 2                              # нулевая длина выброшена
    assert out2["walls"][0]["thickness_m"] == 0.15              # мусор -> дефолт
    assert out2["walls"][1]["thickness_m"] == 0.6               # кламп сверху
    assert len(out2["openings"]) == 1                           # wall_idx 7 выброшен
    assert out2["rooms"][0]["name"] == "Комната 1"              # не-строка -> дефолт
    assert out2["rooms"][0]["type"] == "other"                  # sauna -> other
    assert out2["furniture"][0]["type"] == "other"              # spaceship -> other
    assert out2["furniture"][0]["rot_deg"] == 180.0             # кламп 900 -> 180
    assert any("walls" in w for w in warn2) or warn2
    # контракт посадки (п.56): окно x_px=50 при стене 0,99 м — ширина срезана
    # до 0,89, центр посажен на 0,495 м (warning'и, не issues)
    assert any("посажен" in w for w in warn2)
    assert issues2 == []
    print("test_validate_interior OK")


def test_interior_seating_contract():
    """Контракт посадки п.56 на фикстурах живых кейсов п.55: нормализуемое
    чинится кодом с warning'ами «посажено», семантическое — в issues."""
    from threed.threed_scenarios import validate_interior

    # кейс п.55-1: окно за торцом стены 8 м (x_px=45 при scale 0.16 ->
    # t=7,2 м; правая граница посадки 8 - 2/2 - 0,05 = 6,95 м)
    scene = {
        "trace_width": 60, "trace_height": 30, "metres_per_trace_pixel": 0.16,
        "wall_height": 2.7,
        "outline": [[2, 2], [38, 2], [38, 28], [2, 28]],
        "walls": [{"points_px": [[2, 2], [52, 2]], "thickness_m": 0.4,
                   "exterior": True}],
        "openings": [{"wall_idx": 0, "x_px": 45, "width_m": 2.0,
                      "height_m": 1.5, "sill_m": 0.9, "kind": "window"}],
        "rooms": [], "furniture": [],
    }
    out, warn, issues = validate_interior(scene, 60, 30)
    assert issues == []
    assert abs(out["openings"][0]["x_px"] - 6.95 / 0.16) < 1e-6
    assert any("посажен" in w for w in warn)

    # кейс п.55-2: дверь на огрызке 0,32 м — перенос на ближайшую стену
    # >= 0,6 м (wall 2: [2,28]-[38,28], 5,76 м, дистанция 0)
    scene["walls"] = [
        {"points_px": [[2, 2], [52, 2]], "thickness_m": 0.4, "exterior": True},
        {"points_px": [[4, 28], [6, 28]], "thickness_m": 0.3, "exterior": True},
        {"points_px": [[2, 28], [38, 28]], "thickness_m": 0.3, "exterior": True},
    ]
    scene["openings"] = [{"wall_idx": 1, "x_px": 1, "width_m": 0.9,
                          "height_m": 2.1, "sill_m": 0.0, "kind": "door"}]
    out, warn, issues = validate_interior(scene, 60, 30)
    assert issues == []
    assert out["openings"][0]["wall_idx"] == 2
    assert any("огрызок" in w and "посажен" in w for w in warn)

    # тот же огрызок, подходящей стены рядом нет (ближайшая 4,16 м > 1,5) —
    # семантический issue, проём удалён
    scene["walls"] = scene["walls"][:2]
    out, warn, issues = validate_interior(scene, 60, 30)
    assert out["openings"] == []
    assert any("без стены-носителя" in i for i in issues)

    # мебель вне комнат — семантический issue (вход ремонта п.56)
    scene2 = sample_interior_scene()
    scene2["furniture"][1]["x_px"] = 60          # стол за спальней
    out, warn, issues = validate_interior(scene2, 80, 40)
    assert len(issues) == 1 and "вне комнат" in issues[0]

    # комната не замкнута стенами (одна стена из четырёх) — issue
    scene3 = {
        "trace_width": 40, "trace_height": 30, "metres_per_trace_pixel": 0.25,
        "wall_height": 2.7, "outline": [],
        "walls": [{"points_px": [[2, 2], [38, 2]], "thickness_m": 0.4,
                   "exterior": True}],
        "openings": [],
        "rooms": [{"name": "Зал", "type": "living",
                   "points_px": [[2, 2], [20, 2], [20, 28], [2, 28]]}],
        "furniture": [],
    }
    out, warn, issues = validate_interior(scene3, 40, 30)
    assert any("не замкнута" in i for i in issues)
    print("test_interior_seating_contract OK")


def _mock_vlm_ok(text):
    def call(system, prompt, image_url, model):
        return text
    return call


def test_generate_impl(monkeypatch=None):
    """Роутерная логика без HTTP: мок VLM -> IFC в tmp-каталоге."""
    from PIL import Image
    import threed.threed_router as R
    R._vlm_list_cached = lambda: []  # каталог не запрашиваем: тесты без сети

    scene = sample_scene()
    R._call_vlm = _mock_vlm_ok("```json\n" + json.dumps(scene, ensure_ascii=False) + "\n```")
    TMP.mkdir(exist_ok=True)
    img = Image.new("RGB", (800, 600), (245, 245, 240))
    res = R._generate_impl("plan", "тест", img, TMP)
    assert res["name"].startswith("3D_plan_") and res["name"].endswith(".ifc")
    assert (TMP / res["name"]).is_file()
    assert (TMP / (Path(res["name"]).stem + "_preview.png")).is_file()
    assert (TMP / "_threed_last.json").is_file()

    # ретрай: первый ответ мусор, второй валидный
    calls = {"n": 0}
    def flaky(system, prompt, image_url, model):
        calls["n"] += 1
        return "мусор без json" if calls["n"] == 1 else json.dumps(scene)
    R._call_vlm = flaky
    res2 = R._generate_impl("plan", "", img, TMP)
    assert res2["name"].startswith("3D_plan_") and calls["n"] == 2

    # два мусорных ответа -> ValueError
    R._call_vlm = _mock_vlm_ok("no json here")
    try:
        R._generate_impl("plan", "", img, TMP)
        raise AssertionError("ожидалась ошибка")
    except ValueError as e:
        assert "JSON" in str(e) or "сцену" in str(e)
    print("test_generate_impl OK")


def test_generate_impl_facade():
    from PIL import Image
    import threed.threed_router as R
    R._vlm_list_cached = lambda: []  # тесты без сети (фаза 1)

    assert "facade" in R.SCENARIOS and "interior" in R.SCENARIOS  # фаза 3
    scene = sample_facade_scene()
    R._call_vlm = _mock_vlm_ok("```json\n" + json.dumps(scene, ensure_ascii=False) + "\n```")
    TMP.mkdir(exist_ok=True)
    img = Image.new("RGB", (600, 800), (250, 250, 250))
    res = R._generate_impl("facade", "тест фасада", img, TMP)
    assert res["name"].startswith("3D_facade_") and res["name"].endswith(".ifc")
    assert (TMP / res["name"]).is_file()
    assert (TMP / (Path(res["name"]).stem + "_preview.png")).is_file()
    assert (TMP / "_threed_last.json").is_file()
    # неизвестный сценарий -> гейт-ошибка (интерьер активен — фаза 3)
    try:
        R._generate_impl("attic", "", img, TMP)
        raise AssertionError("ожидалась ошибка")
    except ValueError as e:
        assert "plan, facade" in str(e)
    print("test_generate_impl_facade OK")


def test_generate_impl_interior(monkeypatch=None):
    """Роутер: сценарий interior (мок VLM) -> 3D_interior_*.ifc."""
    import threed.threed_router as R
    R._vlm_list_cached = lambda: []  # каталог не запрашиваем: тесты без сети
    scene = sample_interior_scene()
    R._call_vlm = _mock_vlm_ok("```json\n" + json.dumps(scene, ensure_ascii=False) + "\n```")
    TMP.mkdir(exist_ok=True)
    from PIL import Image
    img = Image.new("RGB", (40, 30), (250, 250, 248))
    res = R._generate_impl("interior", "тест", img, TMP)
    assert res["name"].startswith("3D_interior_") and res["name"].endswith(".ifc")
    assert (TMP / res["name"]).is_file()
    assert (TMP / (Path(res["name"]).stem + "_preview.png")).is_file()
    assert res["warnings"] == []
    # docstring/ошибка для неизвестного сценария больше не называет интерьер
    # «в разработке»
    try:
        R._generate_impl("attic", "", img, TMP)
        raise AssertionError("ожидалась ошибка")
    except ValueError as e:
        assert "plan, facade, interior" in str(e)
    print("test_generate_impl_interior OK")


def test_model_choice_and_put(monkeypatch=None):
    import threed.threed_router as R
    # дефолт без файла
    R._model_store_path = lambda: TMP / "missing_threed_model.json"
    assert R._load_model_choice() == ("openai/gpt-6-astra", "default")
    # PUT-валидация по списку VLM (мок каталога)
    R._vlm_list_cached = lambda: [{"id": "openai/gpt-6-astra"}, {"id": "x/vlm-2"}]
    p = TMP / "threed_model.json"
    R._model_store_path = lambda: p
    R._save_model_choice("x/vlm-2")
    assert R._load_model_choice() == ("x/vlm-2", "file")
    try:
        R._validate_model_in_list("no/such")
        raise AssertionError("ожидалась ошибка")
    except ValueError:
        pass
    print("test_model_choice_and_put OK")


def test_generate_job_flow():
    """Фоновая задача (фикс 524): _run_job синхронно — статусы/этапы/result.
    _ifc_dir мокается на TMP — артефакты теста не попадают в боевой data/ifc."""
    from PIL import Image
    import threed.threed_router as R
    R._vlm_list_cached = lambda: []  # без сети
    orig_ifc_dir = R._ifc_dir
    R._ifc_dir = lambda: TMP
    try:
        scene = sample_scene()
        R._call_vlm = _mock_vlm_ok("```json\n" + json.dumps(scene, ensure_ascii=False) + "\n```")
        TMP.mkdir(exist_ok=True)
        img = Image.new("RGB", (800, 600), (245, 245, 240))
        job = R._job_new("plan")
        assert job["status"] == "queued" and len(job["id"]) == 12
        R._run_job(job, "тест", img)  # в главном потоке: семафор свободен
        assert job["status"] == "done", job.get("error")
        assert (TMP / job["result"]["name"]).is_file()
        pub = R._job_public(job)
        assert pub["jobId"] == job["id"] and pub["status"] == "done"
        assert pub["result"]["name"].startswith("3D_plan_") and \
            pub["result"]["name"].endswith(".ifc")
        assert pub["elapsed_s"] >= 0
        # прямой прогресс-контракт _generate_impl: анализ -> сборка (verify выкл)
        seen = []
        R._generate_impl("plan", "", img, TMP, progress=seen.append)
        assert seen[0] == "analysis" and seen[-1] == "build"
    finally:
        R._ifc_dir = orig_ifc_dir
    print("test_generate_job_flow OK")


def test_job_cleanup_ttl():
    import threed.threed_router as R
    R._jobs.clear()
    old = R._job_new("plan")
    old.update(status="done", ts=time.time() - R.JOBS_TTL_S - 1)
    fresh = R._job_new("facade")
    assert old["id"] not in R._jobs, "устаревшая done-задача не удалена"
    assert fresh["id"] in R._jobs
    # лимит количества: JOBS_MAX не превышается
    for _ in range(R.JOBS_MAX + 5):
        R._job_new("scene")
    assert len(R._jobs) <= R.JOBS_MAX
    R._jobs.clear()
    print("test_job_cleanup_ttl OK")


def test_get_job_404():
    from fastapi import HTTPException
    import threed.threed_router as R
    try:
        R.get_job("nosuchjob")
        raise AssertionError("ожидался 404")
    except HTTPException as e:
        assert e.status_code == 404
    # живая задача отдаётся публичным видом без внутренних полей
    job = R._job_new("plan")
    pub = R.get_job(job["id"])
    assert pub["jobId"] == job["id"] and "created" not in pub
    R._jobs.clear()
    print("test_get_job_404 OK")


def test_post_generate_shape():
    """POST /generate: битая dataURL — синхронный 422; валидная — {jobId},
    сценарий-гейт внутри задачи -> error с текстом «в разработке»."""
    import base64
    import io as _io
    from PIL import Image
    from fastapi import HTTPException
    import threed.threed_router as R
    R._vlm_list_cached = lambda: []
    R._jobs.clear()
    try:
        R.generate(R.GenerateBody(scenario="plan", prompt="",
                                  image="data:image/png;base64,not-base64!"))
        raise AssertionError("ожидался 422 на битую dataURL")
    except HTTPException as e:
        assert e.status_code == 422 and "изображение" in e.detail.lower()
    assert not R._jobs, "битая dataURL не должна создавать задачу"
    buf = _io.BytesIO()
    Image.new("RGB", (40, 30), (250, 250, 248)).save(buf, format="PNG")
    dataurl = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    resp = R.generate(R.GenerateBody(scenario="attic", prompt="", image=dataurl))
    assert resp.get("jobId") and resp.get("status") == "queued"
    assert resp["jobId"] in R._jobs
    # фоновый поток доводит гейт-ошибку до error (без VLM-затрат)
    for _ in range(100):  # до 5 с
        if R._jobs[resp["jobId"]]["status"] in ("done", "error"):
            break
        time.sleep(0.05)
    job = R._jobs[resp["jobId"]]
    assert job["status"] == "error" and "в разработке" in job["error"]
    pub = R._job_public(job)
    assert pub["error"] == job["error"] and "result" not in pub
    R._jobs.clear()
    print("test_post_generate_shape OK")


def test_usage_cost_and_record():
    """Учёт стоимости VLM: тарифы каталога -> расчёт -> запись -> итог;
    мок VLM в _generate_impl usage не пишет (обратная совместимость)."""
    from PIL import Image
    import threed.threed_router as R
    R._vlm_list_cached = lambda: [
        {"id": "openai/gpt-6-astra",
         "pricing": {"prompt": "10.0e-6", "completion": "50.0e-6",
                     "input_cache_read": "1.0e-6"}}]
    R._usage_log.clear()
    # расчёт по тарифам: 2000 вх×10e-6 + 3000 вых×50e-6 = $0.17
    u = {"prompt_tokens": 2000, "completion_tokens": 3000}
    assert abs(R._call_cost_usd("openai/gpt-6-astra", u) - 0.17) < 1e-9
    # кэш-чтение дешевле полного входа: (2000-1000)×10e-6 + 1000×1e-6
    u2 = {"prompt_tokens": 2000, "completion_tokens": 0,
          "prompt_tokens_details": {"cached_tokens": 1000}}
    assert abs(R._call_cost_usd("openai/gpt-6-astra", u2) - 0.011) < 1e-9
    # готовый cost из API приоритетнее тарифов
    assert R._call_cost_usd("openai/gpt-6-astra", {"cost": "0.123"}) == 0.123
    # модель без тарифов -> None
    assert R._call_cost_usd("x/unknown", u) is None
    # запись успешных вызовов с тегами этапов
    R._usage_stage[0] = "analysis"
    R._record_usage("openai/gpt-6-astra",
                    {"usage": {"prompt_tokens": 2000, "completion_tokens": 3000}})
    R._usage_stage[0] = "verify"
    R._record_usage("openai/gpt-6-astra",
                    {"usage": {"prompt_tokens": 2500, "completion_tokens": 150}})
    s = R._usage_summary()
    assert s["tokens"] == {"in": 4500, "out": 3150}
    assert [c["stage"] for c in s["calls"]] == ["analysis", "verify"]
    assert abs(s["cost_usd"] - round(0.17 + 2500 * 10e-6 + 150 * 50e-6, 4)) < 1e-9
    R._usage_log.clear()
    assert R._usage_summary() == {}
    # мок VLM -> генерация без usage-секции (изоляция от выбора модели
    # в test_model_choice_and_put: дефолт astra есть в каталоге-моке)
    R._model_store_path = lambda: TMP / "missing_usage_model.json"
    scene = sample_scene()
    R._call_vlm = _mock_vlm_ok(json.dumps(scene))
    img = Image.new("RGB", (800, 600), (245, 245, 240))
    res = R._generate_impl("plan", "", img, TMP)
    assert "usage" not in res
    print("test_usage_cost_and_record OK")


def test_widget_cost_toast():
    src = (ROOT / "imagerouter" / "devbim_topright_buttons.js").read_text(encoding="utf-8")
    assert "cost_usd" in src, "фронт не показывает стоимость"
    assert "потрачено" in src and "spent" in src
    print("test_widget_cost_toast OK")


def test_setup_threed():
    import setup_threed as S
    TMP.mkdir(exist_ok=True)
    fake = TMP / "fakevenv"
    routers = fake / "Lib" / "site-packages" / "invokeai" / "app" / "api" / "routers"
    routers.mkdir(parents=True, exist_ok=True)
    (routers / "imagerouter.py").write_text("# existing", encoding="utf-8")
    api_app = fake / "Lib" / "site-packages" / "invokeai" / "app" / "api_app.py"
    api_app.write_text(
        "from invokeai.app.api.routers import (\n    pdf,\n    design_code,\n)\n"
        'app.include_router(pdf.pdf_router, prefix="/api")\n'
        'app.include_router(design_code.design_code_router, prefix="/api")\n',
        encoding="utf-8")
    S.deploy_files(fake)
    assert (routers / "threed.py").is_file()
    assert (routers / "threed_scenarios.py").is_file()
    assert (routers / "threed_build.py").is_file()
    changed = S.patch_api_app(api_app)
    s = api_app.read_text(encoding="utf-8")
    assert changed and "    threed,\n" in s
    assert 'app.include_router(threed.threed_router, prefix="/api")' in s
    # идемпотентность: второй прогон ничего не меняет
    assert S.patch_api_app(api_app) is False
    assert S.deploy_files(fake) is False
    print("test_setup_threed OK")


def test_ifcviewer_autoload():
    import re
    src = (ROOT / "ifc" / "ifcviewer.html").read_text(encoding="utf-8")
    m = re.search(r'<script type="module">(.*?)</script>', src, re.S)
    assert m, "module-скрипт не найден"
    chk = ROOT / "ifc" / "_chk.mjs"
    chk.write_text(m.group(1), encoding="utf-8")
    try:
        import subprocess
        r = subprocess.run(["node", "--check", str(chk)], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
    finally:
        chk.unlink(missing_ok=True)
    assert 'if (!EMBED) {' in m.group(1)
    assert m.group(1).count("loadServerModel(lastTab)") == 1
    # спека: автозагрузка обязана быть ВНЕ блока if (EMBED) — топ-уровень
    # module-скрипта без отступа; тело embed-блока всегда с отступом
    assert re.search(r"^if \(!EMBED\) \{", m.group(1), re.M), \
        "блок автозагрузки должен быть топ-уровневым (вне if (EMBED))"
    # фаза 4: camHint — камера по подсказке генерации сцены
    assert "function applyCamHint(" in m.group(1)
    assert "devbim:ifc:camHint" in m.group(1)
    assert "if (!applyCamHint(name)) fitModel();" in m.group(1)
    # interior3d: человек + «Вид от глаз» + персистентность по модели
    assert "devbim:ifc:interiorCam" in m.group(1)
    assert "placePersonExact(ewx, floorWY, ewz);" in m.group(1)
    assert "enterFP();" in m.group(1)
    print("test_ifcviewer_autoload OK")


def test_widget_3d_modal():
    src = (ROOT / "imagerouter" / "devbim_topright_buttons.js").read_text(encoding="utf-8")
    import subprocess
    r = subprocess.run(["node", "--check",
                        str(ROOT / "imagerouter" / "devbim_topright_buttons.js")],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    for marker in ("/api/v1/threed/generate", "__devbimSwitchTab('ifc')",
                   "devbim:ifc:lastModel", "images_by_names", "open3D()"):
        assert marker in src, marker
    assert "refresh3D();" not in src and "refresh3DSource();" in src, \
        "open3D обязан вызывать refresh3DSource (не refresh3D)"
    assert "cPresent.rasterLayers && cPresent.rasterLayers.entities" in src, \
        "canvasComposite обязан читать per-type entities (rasterLayers/controlLayers)"
    assert "toast(t().soon)" not in src.split("function build()")[1].split("function isYellow")[0]
    # фасад убран из модалки 05.10 (бэкенд-сценарий сохранён)
    assert 'data-s="facade"' not in src and "promptPhFacade" not in src
    # EN-плейсхолдеры без HTML-сущностей: свойство placeholder не декодирует их,
    # экранирование — только в точке innerHTML-интерполяции
    assert "&quot;" not in src.split("en: {")[1].split("}")[0], \
        "TEXTS.en не должен хранить &quot; (утечка при присваивании свойства)"
    assert "promptPhPlan.replace(/\"/g, '&quot;')" in src, \
        "placeholder экранируется в точке HTML-интерполяции"
    # фаза 3: плитка плана квартиры (Floor Plan, ключ interior) активна
    assert '<button class="devbim-3d-tile" data-s="interior"><span>📐</span>' in src
    assert 'data-s="interior" disabled' not in src
    assert "promptPhInterior" in src and "soon3d" not in src
    assert "promptPhInterior: 'Уточнения:" in src
    assert "var ph = {plan: t().promptPhPlan" in src
    # фаза 4: плитка «Exterior» (сцена) активна, placeholder, camHint
    assert '<button class="devbim-3d-tile" data-s="scene"><span>🌇</span>' in src
    assert 'data-s="scene" disabled' not in src
    assert "promptPhScene: 'Уточнения:" in src
    assert "promptPhScene: 'Hints:" in src
    assert "var ph = {plan: t().promptPhPlan" in src and "scene: t().promptPhScene" in src
    assert "devbim:ifc:camHint" in src
    # interior3d (05.10): плитка «Interior» активна, placeholder RU/EN
    assert '<button class="devbim-3d-tile" data-s="interior3d"><span>🛋</span>' in src
    assert 'data-s="interior3d" disabled' not in src
    assert "promptPhInterior3d: 'Уточнения:" in src
    assert "promptPhInterior3d: 'Hints:" in src
    assert "interior3d: t().promptPhInterior3d" in src
    print("test_widget_3d_modal OK")


def test_validate_facade_balcony_fit():
    """Спека этапа A2: плита балкона целиком в фасаде — кламп центра."""
    from threed.threed_scenarios import validate_facade
    s = sample_facade_scene()
    s["balconies"] = [{"floor": 2, "x_m": 23.5, "w_m": 3.0, "d_m": 1.2},
                      {"floor": 3, "x_m": 0.5, "w_m": 3.0, "d_m": 1.2}]
    out, warn = validate_facade(s)
    assert [b["x_m"] for b in out["balconies"]] == [22.5, 1.5], out["balconies"]
    assert any("Балкон 1" in w for w in warn), warn
    assert any("Балкон 2" in w for w in warn), warn
    # влезающий балкон не сдвигается и не даёт предупреждений
    s["balconies"] = [{"floor": 2, "x_m": 4.0, "w_m": 3.0, "d_m": 1.2}]
    out2, warn2 = validate_facade(s)
    assert out2["balconies"][0]["x_m"] == 4.0 and warn2 == []
    print("test_validate_facade_balcony_fit OK")


def sample_scene_scene():
    """Сцена: главное 7-эт. здание в (0,0) 27×15 м, второе 3-эт. в (32,8);
    камера азимут -30 (слева), деревья/машины/люди. Третье здание с повторным
    main валидатор отбрасывает, четвёртое — за лимитом 1..3 (остаются 2)."""
    return {
        "camera": {"azimuth_deg": -30, "eye_height_m": 1.7, "dist_m": 40},
        "buildings": [
            {"main": True, "x_m": 0, "y_m": 0, "width_m": 27.0, "depth_m": 15.0,
             "storeys": 7, "floor_height": 3.1, "roof": "flat", "roof_height": 0.5,
             "windows": {"rows": 1, "cols": 8, "w_m": 1.4, "h_m": 1.8,
                         "margin_x_m": 1.5, "margin_y_m": 0.6},
             "balconies": [{"floor": 2, "x_m": 1.5, "w_m": 3.0, "d_m": 1.2}],
             "colors": {"walls": "#c9b49a", "roof": "#52616b", "plinth": "#8d8d8d"}},
            {"main": False, "x_m": 32.0, "y_m": 8.0, "width_m": 14.0, "depth_m": 10.0,
             "storeys": 3, "floor_height": 3.0, "roof": "gable", "roof_height": 2.0,
             "windows": {"rows": 1, "cols": 4, "w_m": 1.4, "h_m": 1.6,
                         "margin_x_m": 1.0, "margin_y_m": 0.7},
             "balconies": [], "colors": {}},
            {"main": True, "x_m": -40.0, "y_m": 0.0, "width_m": 10.0, "depth_m": 10.0,
             "storeys": 2, "floor_height": 3.0, "roof": "flat", "roof_height": 1.0,
             "windows": {}, "balconies": [], "colors": {}},
            {"main": False, "x_m": 60.0, "y_m": -20.0, "width_m": 8.0, "depth_m": 8.0,
             "storeys": 1, "floor_height": 3.0, "roof": "flat", "roof_height": 0.5,
             "windows": {}, "balconies": [], "colors": {}},
        ],
        "context": {
            "trees": [{"x_m": 8.0, "y_m": -12.0, "h_m": 7.0, "crown_d_m": 3.5},
                      {"x_m": "bad"}, {"x_m": 15.0, "y_m": -14.0, "h_m": 99,
                                       "crown_d_m": 3.0}],
            "cars": [{"x_m": -6.0, "y_m": -10.0, "rot_deg": 15}],
            # человек 1 — на балконе главного (этаж 2, fh 3.1 -> z_m 3.1;
            # балкон x_m 1.5 от левого края 27 м -> x=-12, y=-(7.5+0.6)=-8.1)
            "people": [{"x_m": -12.0, "y_m": -8.1, "z_m": 3.1}, {"x_m": 6.0, "y_m": -9.5}],
            "furniture": [
                {"type": "lounger", "x_m": -12.0, "y_m": -8.3, "z_m": 3.1,
                 "w_m": 1.8, "d_m": 0.7, "h_m": 0.8, "rot_deg": 0},
                {"type": "bench", "x_m": 10.0, "y_m": -10.0, "z_m": 0, "rot_deg": 30},
                {"type": "fountain"},
                {"x_m": "bad"},
            ],
        },
    }


def test_validate_scene():
    from threed.threed_scenarios import validate_scene, SYSTEM_SCENE
    assert "azimuth_deg" in SYSTEM_SCENE and "crown_d_m" in SYSTEM_SCENE
    assert "furniture" in SYSTEM_SCENE and "z_m" in SYSTEM_SCENE
    out, warn = validate_scene(sample_scene_scene())
    assert out["camera"] == {"azimuth_deg": -30, "eye_height_m": 1.7, "dist_m": 40}
    b0, b1 = out["buildings"][0], out["buildings"][1]
    assert b0["main"] is True and b1["main"] is False
    assert len(out["buildings"]) == 2          # третий (dup main) отброшен, 4-й >3
    assert any("больше 3" in w for w in warn)
    # окна второго здания прошли как есть; балкон главного влез
    assert b1["windows"]["cols"] == 4 and b1["windows"]["w_m"] == 1.4
    # дерево: 'bad'-элемент выкинут, h_m=99 -> кламп 30
    assert len(out["context"]["trees"]) == 2
    assert out["context"]["trees"][1]["h_m"] == 30.0
    assert any("tree.h_m" in w for w in warn)
    assert len(out["context"]["people"]) == 2
    # человек 1 на балконе: z_m прошёл как есть
    assert out["context"]["people"][0]["z_m"] == 3.1
    furn = out["context"]["furniture"]
    assert len(furn) == 3                      # 'bad'-элемент выкинут
    assert furn[0]["type"] == "lounger" and furn[0]["z_m"] == 3.1
    # bench без размеров -> дефолты по типу
    assert furn[1]["w_m"] == 1.8 and furn[1]["d_m"] == 0.5 and furn[1]["h_m"] == 0.45
    assert furn[2]["type"] == "other"          # fountain -> other + warning
    assert any("fountain" in w for w in warn)
    # гейты
    for bad in (None, {}, {"buildings": []}, {"buildings": "x"}):
        try:
            validate_scene(bad)
            raise AssertionError("ожидалась ошибка")
        except ValueError:
            pass
    print("test_validate_scene OK")


def test_build_scene():
    import ifcopenshell
    from threed.threed_scenarios import validate_scene
    from threed.threed_build import build_scene

    clean, _ = validate_scene(sample_scene_scene())
    TMP.mkdir(exist_ok=True)
    ifc = TMP / "3D_scene_test.ifc"
    prev = TMP / "3D_scene_test_preview.png"
    path = build_scene(clean, ifc, prev,
                       {"Scenario": "scene", "Prompt": "тест", "Model": "test/model",
                        "Source": "3D Design"})
    assert path == ifc and ifc.is_file() and prev.is_file()

    m = ifcopenshell.open(str(ifc))
    assert m.schema == "IFC4"
    gids = [r.GlobalId for r in m.by_type("IfcRoot")]
    assert len(gids) == len(set(gids)), "GlobalId не уникальны"
    proxies = m.by_type("IfcBuildingElementProxy")
    by_type = {}
    for p in proxies:
        by_type[p.ObjectType] = by_type.get(p.ObjectType, 0) + 1
    assert by_type.get("CONCEPTUAL_STOREY") == 7 + 3      # тома-этажи 2 зданий
    assert by_type.get("CONCEPTUAL_PLINTH") == 2
    assert by_type.get("CONCEPTUAL_ROOF") == 1            # gable у второго
    # главное (27 м, шаг фронта (24-1.4)/7+1.4=3.23; depth 15):
    # side_cols = clamp(round((15-2*1.5)/3.23),1,6)=4 -> фронт 7×8 + бок 7×2×4=112
    assert by_type.get("CONCEPTUAL_WINDOW") == 112 + 3 * 4
    assert by_type.get("CONCEPTUAL_BALCONY") == 1
    assert by_type.get("CONCEPTUAL_TREE") == 4            # 2 дерева × (ствол+крона)
    assert by_type.get("CONCEPTUAL_CAR") == 1
    assert by_type.get("CONCEPTUAL_PERSON") == 2
    assert by_type.get("CONCEPTUAL_FURNITURE") == 3
    assert by_type.get("CONCEPTUAL_GROUND") == 1
    # фронт главного здания на IFC -Y: окна при y_m=0 -> центры -depth/2
    from ifcopenshell.util.placement import get_local_placement
    wins = [p for p in proxies if p.ObjectType == "CONCEPTUAL_WINDOW"
            and "Гл" in (p.Name or "") and "бок" not in (p.Name or "")]
    assert wins and all(get_local_placement(w.ObjectPlacement)[1, 3] < -5.0 for w in wins)
    # человек 1 стоит на балконе главного: низ фигуры z = (2-1)*3.1
    p1 = next(p for p in proxies if p.ObjectType == "CONCEPTUAL_PERSON"
              and (p.Name or "").startswith("Человек 1"))
    assert abs(get_local_placement(p1.ObjectPlacement)[2, 3] - 3.1) < 1e-6
    # мебель 1 (lounger) — тоже на балконе: низ бокса z = 3.1
    f1 = next(p for p in proxies if p.ObjectType == "CONCEPTUAL_FURNITURE"
              and "lounger" in (p.Name or ""))
    assert abs(get_local_placement(f1.ObjectPlacement)[2, 3] - 3.1) < 1e-6
    # CameraHint на проекте
    from ifcopenshell.util.element import get_psets
    hint = get_psets(m.by_type("IfcProject")[0]).get("CameraHint", {})
    assert abs(hint.get("AzimuthDeg", 999) - (-30)) < 1e-6
    assert abs(hint.get("EyeHeightM", 0) - 1.7) < 1e-6
    sm = get_psets(m.by_type("IfcBuilding")[0]).get("SceneModel", {})
    assert sm.get("Buildings") == 2 and sm.get("WindowsTotal") == 112 + 12
    assert sm.get("Furniture") == 3
    # превью: план рисуется (содержательная проверка — E2E задачи 11)
    from PIL import Image
    im = Image.open(prev)
    assert im.size[0] > 400 and im.size[1] > 300
    print("test_build_scene OK")


def test_generate_impl_scene():
    from PIL import Image
    import threed.threed_router as R
    R._vlm_list_cached = lambda: []  # тесты без сети
    scene = sample_scene_scene()
    R._call_vlm = _mock_vlm_ok("```json\n" + json.dumps(scene, ensure_ascii=False) + "\n```")
    TMP.mkdir(exist_ok=True)
    img = Image.new("RGB", (691, 647), (250, 250, 250))
    res = R._generate_impl("scene", "тест сцены", img, TMP)
    assert res["name"].startswith("3D_scene_") and res["name"].endswith(".ifc")
    assert (TMP / res["name"]).is_file()
    assert res["camHint"] == {"azimuth_deg": -30, "eye_height_m": 1.7, "dist_m": 40,
                              # фокус: центроид человека на балконе (-12,-8.1,3.1)
                              # и лаунжера (-12,-8.3,3.1)
                              "focus": {"x_m": -12.0, "y_m": -8.2, "z_m": 3.1}}
    assert "scene" in R.SCENARIOS
    try:
        R._generate_impl("attic", "", img, TMP)
        raise AssertionError("ожидалась ошибка")
    except ValueError as e:
        assert "scene" in str(e)
    print("test_generate_impl_scene OK")


def test_scene_overview_furniture():
    """verify-обзор сцены: счётчики мебели и людей на высоте (задача 46-3)."""
    from threed.threed_scenarios import validate_scene
    from threed.threed_verify import scene_overview, SYSTEM_VERIFY
    clean, _ = validate_scene(sample_scene_scene())
    ov = scene_overview("scene", clean)
    assert ov["context"]["furniture"] == {"lounger": 1, "bench": 1, "other": 1}
    assert ov["context"]["people"] == 2 and ov["context"]["people_elevated"] == 1
    assert "furniture" in SYSTEM_VERIFY
    print("test_scene_overview_furniture OK")


def test_admin_threed_section():
    src = (ROOT / "imagerouter" / "imagerouter.html").read_text(encoding="utf-8")
    assert 'id="threedsec"' in src
    assert "/api/v1/threed/model" in src
    assert 'id="threed-save"' in src
    print("test_admin_threed_section OK")


# =========== Сценарий «Interior 3D» (рендер интерьера, 05.10) ===========

def sample_interior3d_scene():
    """Гостиная 6×4.5×2.8: окно на северной стене, дверь восток, дверь юг
    (вне стены + с подоконником — на клампы), диван/стол/фонтан(→other)/
    кровать (дефолты), 2 человека, камера у южной стены."""
    return {
        "room": {"width_m": 6.0, "depth_m": 4.5, "height_m": 2.8,
                 "ceiling": True, "wall_color": "#e8e2d8",
                 "floor_color": "#8a6f4d", "ceiling_color": "#f2efe8"},
        "openings": [
            {"wall": "north", "x_m": 1.5, "w_m": 1.8, "h_m": 1.6, "sill_m": 0.9,
             "kind": "window"},
            {"wall": "east", "x_m": 1.0, "w_m": 0.9, "h_m": 2.1, "sill_m": 0.0,
             "kind": "door"},
            {"wall": "south", "x_m": 99.0, "w_m": 0.9, "h_m": 2.1, "sill_m": 0.5,
             "kind": "door"},
            {"wall": "roof", "x_m": 1.0, "w_m": 1.0, "h_m": 1.0, "sill_m": 0.0,
             "kind": "window"},
        ],
        "furniture": [
            {"type": "sofa", "x_m": -1.2, "y_m": -1.6, "w_m": 2.2, "d_m": 0.9,
             "h_m": 0.8, "rot_deg": 0, "color": "#667788"},
            {"type": "table", "x_m": 0.0, "y_m": 0.2, "rot_deg": 15},
            {"type": "fountain", "x_m": 99, "y_m": 99},
            {"type": "bed"},
        ],
        "people": [
            {"x_m": 1.0, "y_m": 0.8, "h_m": 1.75, "rot_deg": -90},
            {"x_m": -2.8, "y_m": 1.8, "h_m": 1.65},
        ],
        "camera": {
            "eye_x_m": 0.3, "eye_y_m": -1.7, "eye_z_m": 1.6,
            "yaw_deg": 5, "target_x_m": -0.2, "target_y_m": 1.9, "target_z_m": 1.1,
        },
    }


def test_validate_interior3d():
    from threed.threed_scenarios import validate_interior3d, SYSTEM_INTERIOR3D
    assert "eye_x_m" in SYSTEM_INTERIOR3D and "target_z_m" in SYSTEM_INTERIOR3D
    assert '"south"|"north"|"east"|"west"' in SYSTEM_INTERIOR3D
    out, warn = validate_interior3d(sample_interior3d_scene())
    r = out["room"]
    assert (r["width_m"], r["depth_m"], r["height_m"]) == (6.0, 4.5, 2.8)
    assert r["ceiling"] is True and r["floor_color"] == "#8a6f4d"
    # 3 проёма: roof-стена выкинута, остальные живут
    assert len(out["openings"]) == 3
    assert any("roof" in w for w in warn)
    south = next(o for o in out["openings"] if o["wall"] == "south")
    # дверь на юге: x_m=99 -> кламп в длину стены (6-0.45-0.05), sill -> 0
    assert abs(south["x_m"] - 5.5) < 1e-9 and south["sill_m"] == 0.0
    assert any("подоконник" in w for w in warn) and any("вне стены" in w for w in warn)
    # мебель: fountain -> other + кламп x=3.0; bed — дефолты по типу
    assert len(out["furniture"]) == 4
    other = next(f for f in out["furniture"] if f["type"] == "other")
    assert other["x_m"] == 3.0 and other["y_m"] == 2.25
    assert any("fountain" in w for w in warn) and any("вне комнаты" in w for w in warn)
    bed = next(f for f in out["furniture"] if f["type"] == "bed")
    assert (bed["w_m"], bed["d_m"], bed["h_m"]) == (2.0, 1.6, 0.5)
    assert out["furniture"][0]["color"] == "#667788"      # hex от VLM живёт
    assert len(out["people"]) == 2 and out["people"][0]["h_m"] == 1.75
    cam = out["camera"]
    assert (cam["eye_x_m"], cam["eye_y_m"], cam["eye_z_m"]) == (0.3, -1.7, 1.6)
    assert (cam["target_x_m"], cam["target_y_m"], cam["target_z_m"]) == (-0.2, 1.9, 1.1)
    # глаз за стеной -> кламп внутрь комнаты
    sc = sample_interior3d_scene()
    sc["camera"]["eye_x_m"] = 12.0
    out2, warn2 = validate_interior3d(sc)
    assert abs(out2["camera"]["eye_x_m"] - 2.7) < 1e-9    # w/2-0.3
    assert any("eye_x_m" in w for w in warn2)
    # гейты: не объект / нет комнаты (нулевые габариты не гейт — кламп,
    # как в фасаде)
    for bad in (None, {}, {"room": "x"}, 42, [1, 2]):
        try:
            validate_interior3d(bad)
            raise AssertionError("ожидалась ошибка")
        except ValueError:
            pass
    zero, zw = validate_interior3d({"room": {"width_m": 0, "depth_m": 0}})
    assert zero["room"]["width_m"] == 2.0 and zero["room"]["depth_m"] == 2.0
    assert any("width_m" in w for w in zw)
    print("test_validate_interior3d OK")


def test_build_interior3d():
    import ifcopenshell
    from threed.threed_scenarios import validate_interior3d
    from threed.threed_build import build_interior3d, INTERIOR3D_WALL_T

    clean, _ = validate_interior3d(sample_interior3d_scene())
    TMP.mkdir(exist_ok=True)
    ifc = TMP / "3D_interior3d_test.ifc"
    prev = TMP / "3D_interior3d_test_preview.png"
    path = build_interior3d(clean, ifc, prev,
                            {"Scenario": "interior3d", "Prompt": "тест",
                             "Model": "test/model", "Source": "3D Design"})
    assert path == ifc and ifc.is_file() and prev.is_file()

    m = ifcopenshell.open(str(ifc))
    assert m.schema == "IFC4"
    gids = [r.GlobalId for r in m.by_type("IfcRoot")]
    assert len(gids) == len(set(gids)), "GlobalId не уникальны"
    # shoebox: 4 стены, пол, потолок (ceiling=true)
    assert len(m.by_type("IfcWall")) == 4
    # палитра ориентаций стен (05.10, «не сливаться»): юг/север — терракота,
    # запад/восток — хаки; hex-ы фазы 3 — их узнаёт AI-палитра вьювера
    from threed.threed_build import INTERIOR3D_WALL_COLORS, INTERIOR_WALL_PALETTE
    assert INTERIOR3D_WALL_COLORS["x"] == INTERIOR_WALL_PALETTE[("ext", "X")]
    assert INTERIOR3D_WALL_COLORS["y"] == INTERIOR_WALL_PALETTE[("ext", "Y")]
    assert INTERIOR3D_WALL_COLORS["x"] != INTERIOR3D_WALL_COLORS["y"]
    surf = {s.Name: s for s in m.by_type("IfcSurfaceStyle")}
    assert "Int3dWallX" in surf and "Int3dWallY" in surf

    def surf_rgb(name):
        ss = surf[name].Styles[0].SurfaceColour
        return (round(ss.Red, 3), round(ss.Green, 3), round(ss.Blue, 3))
    assert surf_rgb("Int3dWallX") != surf_rgb("Int3dWallY")
    slabs = m.by_type("IfcSlab")
    assert len(slabs) == 1 and slabs[0].ObjectType == "CONCEPTUAL_FLOOR"
    covers = m.by_type("IfcCovering")
    assert len(covers) == 1 and covers[0].ObjectType == "CONCEPTUAL_CEILING"
    by_ot = {}
    for p in m.by_type("IfcBuildingElementProxy"):
        by_ot[p.ObjectType] = by_ot.get(p.ObjectType, 0) + 1
    assert by_ot.get("CONCEPTUAL_DOOR") == 2
    assert by_ot.get("CONCEPTUAL_WINDOW") == 1
    assert by_ot.get("CONCEPTUAL_PERSON") == 2
    assert len(m.by_type("IfcFurnishingElement")) == 4
    # геометрия room-frame: северная стена y = d/2 + T/2; южная = -(d/2 + T/2)
    from ifcopenshell.util.placement import get_local_placement
    walls = {w.Name: get_local_placement(w.ObjectPlacement)[1, 3]
             for w in m.by_type("IfcWall")}
    assert abs(walls["Стена северная"] - (4.5 / 2 + INTERIOR3D_WALL_T / 2)) < 1e-6
    assert abs(walls["Стена южная (за камерой)"] + (4.5 / 2 + INTERIOR3D_WALL_T / 2)) < 1e-6
    # дверь юга («Дверь 2»: восточная идёт первой): x_m=5.5 от ЛЕВОГО
    # (восточного) конца -> мир x = w/2-5.5 = -2.5; внутренняя грань юга
    # y=-d/2, коробка +0.06 в комнату
    south_door = next(p for p in m.by_type("IfcBuildingElementProxy")
                      if p.ObjectType == "CONCEPTUAL_DOOR"
                      and (p.Name or "") == "Дверь 2")
    pl = get_local_placement(south_door.ObjectPlacement)
    assert abs(pl[0, 3] - (-2.5)) < 1e-6 and abs(pl[1, 3] - (-4.5 / 2 + 0.06)) < 1e-6
    # дверь востока («Дверь 1»): x_m=1.0 от ЛЕВОГО (северного) конца ->
    # мир y = d/2-1.0 = 1.25; грань востока x=w/2, коробка -0.06 в комнату
    east_door = next(p for p in m.by_type("IfcBuildingElementProxy")
                     if p.ObjectType == "CONCEPTUAL_DOOR"
                     and (p.Name or "") == "Дверь 1")
    ple = get_local_placement(east_door.ObjectPlacement)
    assert abs(ple[0, 3] - (6.0 / 2 - 0.06)) < 1e-6 \
        and abs(ple[1, 3] - (4.5 / 2 - 1.0)) < 1e-6
    # окно севера: x_m=1.5 от ЛЕВОГО (западного) конца -> мир x = -w/2+1.5 = -1.5
    north_win = next(p for p in m.by_type("IfcBuildingElementProxy")
                     if p.ObjectType == "CONCEPTUAL_WINDOW")
    plw = get_local_placement(north_win.ObjectPlacement)
    assert abs(plw[0, 3] - (-1.5)) < 1e-6 and abs(plw[1, 3] - (4.5 / 2 - 0.06)) < 1e-6
    # CameraHint на проекте: mode=interior + глаз/цель room-frame + IFC-бокс
    from ifcopenshell.util.element import get_psets
    hint = get_psets(m.by_type("IfcProject")[0]).get("CameraHint", {})
    assert hint.get("Mode") == "interior"
    assert abs(hint.get("EyeXM", 9) - 0.3) < 1e-6
    assert abs(hint.get("EyeYM", 9) + 1.7) < 1e-6
    assert abs(hint.get("EyeZM", 9) - 1.6) < 1e-6
    assert abs(hint.get("TargetYM", 9) - 1.9) < 1e-6
    assert abs(hint.get("BoxMinX", 9) + 3.15) < 1e-6
    assert abs(hint.get("BoxMaxZ", 0) - 2.92) < 1e-6
    rm = get_psets(m.by_type("IfcBuilding")[0]).get("RoomModel", {})
    assert rm.get("WidthM") == 6.0 and rm.get("Ceiling") is True
    assert rm.get("Furniture") == 4 and rm.get("People") == 2
    assert rm.get("OpeningsDoors") == 2 and rm.get("OpeningsWindows") == 1
    # превью-план нарисован
    from PIL import Image
    im = Image.open(prev)
    assert im.size[0] > 400 and im.size[1] > 300
    print("test_build_interior3d OK")


def test_generate_impl_interior3d():
    from PIL import Image
    import threed.threed_router as R
    R._vlm_list_cached = lambda: []  # тесты без сети
    scene = sample_interior3d_scene()
    R._call_vlm = _mock_vlm_ok("```json\n" + json.dumps(scene, ensure_ascii=False) + "\n```")
    TMP.mkdir(exist_ok=True)
    img = Image.new("RGB", (800, 600), (250, 250, 250))
    res = R._generate_impl("interior3d", "тест интерьера", img, TMP)
    assert res["name"].startswith("3D_interior3d_") and res["name"].endswith(".ifc")
    assert (TMP / res["name"]).is_file()
    # camHint вьювера: mode=interior, глаз/цель room-frame + IFC-бокс
    # (вьювер сдвигает модель в мире — переводит координаты по боксам)
    hint = res["camHint"]
    assert hint["mode"] == "interior" and hint["yaw_deg"] == 5
    assert hint["eye"] == {"eye_x_m": 0.3, "eye_y_m": -1.7, "eye_z_m": 1.6}
    assert hint["target"] == {"target_x_m": -0.2, "target_y_m": 1.9,
                              "target_z_m": 1.1}
    assert hint["box"] == {"min": [-3.15, -2.4, -0.15],
                           "max": [3.15, 2.4, 2.92]}
    assert "interior3d" in R.SCENARIOS
    assert (TMP / "_threed_last.json").is_file()
    dump = json.loads((TMP / "_threed_last.json").read_text(encoding="utf-8"))
    assert dump["scenario"] == "interior3d"
    print("test_generate_impl_interior3d OK")


def test_interior3d_overview_and_viewer():
    """verify-обзор interior3d + вьювер понимает mode=interior."""
    from threed.threed_scenarios import validate_interior3d
    from threed.threed_verify import scene_overview
    clean, _ = validate_interior3d(sample_interior3d_scene())
    ov = scene_overview("interior3d", clean)
    assert ov["room"]["width_m"] == 6.0 and ov["room"]["ceiling"] is True
    assert ov["openings"] == {"doors": 2, "windows": 1}
    assert ov["furniture"] == {"sofa": 1, "table": 1, "other": 1, "bed": 1}
    assert ov["people"] == 2 and "camera" in ov
    src = (ROOT / "ifc" / "ifcviewer.html").read_text(encoding="utf-8")
    assert 'hint.mode === "interior"' in src
    # 05.10 (продолжение): IFC->мир по боксам (вьювер СДВИГАЕТ модель —
    # «сырые» координаты оставляли камеру за стеной), человек на полу
    # без луча + камера «Вид от глаз» (зафиксирована: мышь — осмотр,
    # орбиты нет) + персистентность camHint по имени модели (F5 возвращает
    # вид изнутри, а не fitModel снаружи коробки)
    assert "const ewx = ex + ox, ewy = ez + oy, ewz = -ey + oz;" in src
    assert "placePersonExact(ewx, floorWY, ewz);" in src
    assert "function placePersonExact(" in src
    assert "enterFP();" in src
    assert "devbim:ifc:interiorCam" in src
    print("test_interior3d_overview_and_viewer OK")


if __name__ == "__main__":
    test_build_facade()
    test_build_interior()
    test_interior_wall_palette()
    print("OK test_interior_wall_palette")
    test_build_genplan()
    test_extract_json()
    test_validate_genplan()
    test_validate_facade()
    test_validate_interior()
    test_interior_seating_contract()
    test_validate_facade_balcony_fit()
    test_validate_scene()
    test_scene_overview_furniture()
    test_build_scene()
    test_generate_impl_scene()
    test_generate_impl()
    test_generate_impl_facade()
    test_generate_impl_interior()
    test_model_choice_and_put()
    test_generate_job_flow()
    test_job_cleanup_ttl()
    test_get_job_404()
    test_post_generate_shape()
    test_usage_cost_and_record()
    test_widget_cost_toast()
    test_setup_threed()
    test_ifcviewer_autoload()
    test_widget_3d_modal()
    test_admin_threed_section()
    test_validate_interior3d()
    test_build_interior3d()
    test_generate_impl_interior3d()
    test_interior3d_overview_and_viewer()
    print("ALL OK")
