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
    proxies = [p for p in m.by_type("IfcBuildingElementProxy")]
    kinds = {}
    for p in proxies:
        kinds[p.ObjectType] = kinds.get(p.ObjectType, 0) + 1
    assert kinds.get("CONCEPTUAL_DOOR") == 2                 # 2 двери
    assert kinds.get("CONCEPTUAL_WINDOW") == 1               # окно
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
    out, warn = validate_interior(scene, 40, 30)
    assert out["trace_width"] == 40 and out["trace_height"] == 30
    assert out["wall_height"] == 2.7 and len(out["walls"]) == 5
    assert len(out["openings"]) == 3 and out["openings"][0]["kind"] == "door"
    assert [r["name"] for r in out["rooms"]] == ["Кухня", "Спальня"]
    assert out["furniture"][0]["type"] == "bed"
    assert warn == []

    # не-dict / пустая сцена -> ValueError
    for bad in (None, [], {}, {"rooms": []}):
        try:
            validate_interior(bad, 100, 100)
            raise AssertionError("ожидалась ошибка для " + repr(bad))
        except ValueError:
            pass

    # дефолты: масштаб/высота/толщина; мусорные поля выбрасываются
    out2, warn2 = validate_interior({"outline": [[0, 0], [99, 0], [99, 99], [0, 99]],
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
    print("test_validate_interior OK")


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
    assert "function applyCamHint()" in m.group(1)
    assert "devbim:ifc:camHint" in m.group(1)
    assert "if (!applyCamHint()) fitModel();" in m.group(1)
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
    # фаза 2: плитка фасада активна, placeholder зависит от сценария
    facade_tile = '<button class="devbim-3d-tile" data-s="facade">'
    assert facade_tile + "<span>\U0001F3E2</span>" in src, \
        "плитка фасада должна быть активна (без disabled/title)"
    assert 'data-s="facade" disabled' not in src
    for key in ("promptPhPlan", "promptPhFacade"):
        assert key + ":" in src, key
    assert "promptPh:" not in src and "t().promptPh +" not in src
    assert "promptPhFacade" in src.split('data-s="facade"')[1], \
        "клик по плитке фасада подставляет promptPhFacade"
    # EN-плейсхолдеры без HTML-сущностей: свойство placeholder не декодирует их,
    # экранирование — только в точке innerHTML-интерполяции
    assert "promptPhFacade: 'Hints: \"5 storeys" in src
    assert "&quot;" not in src.split("en: {")[1].split("}")[0], \
        "TEXTS.en не должен хранить &quot; (утечка при присваивании свойства)"
    assert "promptPhPlan.replace(/\"/g, '&quot;')" in src, \
        "placeholder экранируется в точке HTML-интерполяции"
    # фаза 3: плитка интерьера активна, placeholder по 3 сценариям
    assert '<button class="devbim-3d-tile" data-s="interior"><span>🛋</span>' in src
    assert 'data-s="interior" disabled' not in src
    assert "promptPhInterior" in src and "soon3d" not in src
    # RU/EN тексты placeholder-ов интерьера
    assert "promptPhInterior: 'Уточнения:" in src
    # переключение placeholder-а через карту сценариев
    assert "var ph = {plan: t().promptPhPlan" in src
    # фаза 4: плитка «Сцена» активна, placeholder, camHint
    assert '<button class="devbim-3d-tile" data-s="scene"><span>🌇</span>' in src
    assert 'data-s="scene" disabled' not in src
    assert "promptPhScene: 'Уточнения:" in src
    assert "promptPhScene: 'Hints:" in src
    assert "var ph = {plan: t().promptPhPlan" in src and "scene: t().promptPhScene" in src
    assert "devbim:ifc:camHint" in src
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
    assert res["camHint"] == {"azimuth_deg": -30, "eye_height_m": 1.7, "dist_m": 40}
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


def test_generate_impl_scene_loop():
    """Петля самокоррекции работает и для сцены (п.46-4): ok=False+issues ->
    повторный анализ с CORRECTIONS -> ok=True побеждает (файл _r2)."""
    import threed.threed_router as R
    import threed.threed_verify as V
    from PIL import Image
    R._vlm_list_cached = lambda: []  # тесты без сети
    scene = sample_scene_scene()
    calls = {"scene": 0, "verify": 0, "saw_corrections": False}

    def call(system, prompt, image_url, model):
        if system.strip().startswith("You are a BIM QA verifier"):
            calls["verify"] += 1
            return json.dumps(
                {"ok": False,
                 "issues": ["Furniture: built none, image shows a balcony lounger."]}
                if calls["verify"] == 1 else {"ok": True, "issues": []})
        calls["scene"] += 1
        if calls["scene"] == 2:
            calls["saw_corrections"] = "CORRECTIONS" in prompt
        return json.dumps(scene, ensure_ascii=False)

    R._call_vlm = call
    TMP.mkdir(exist_ok=True)
    img = Image.new("RGB", (691, 647), (250, 250, 250))
    res = R._generate_impl("scene", "тест петли", img, TMP)
    assert calls["scene"] == 2 and calls["verify"] == 2 and calls["saw_corrections"]
    assert res["name"].endswith("_r2.ifc")
    assert (TMP / res["name"]).is_file()
    assert res["verify"]["verdict"]["ok"] is True and res["verify"]["iterations"] == 2
    print("test_generate_impl_scene_loop OK")


def test_admin_threed_section():
    src = (ROOT / "imagerouter" / "imagerouter.html").read_text(encoding="utf-8")
    assert 'id="threedsec"' in src
    assert "/api/v1/threed/model" in src
    assert 'id="threed-save"' in src
    print("test_admin_threed_section OK")


if __name__ == "__main__":
    test_build_facade()
    test_build_interior()
    test_build_genplan()
    test_extract_json()
    test_validate_genplan()
    test_validate_facade()
    test_validate_interior()
    test_validate_facade_balcony_fit()
    test_validate_scene()
    test_scene_overview_furniture()
    test_generate_impl_scene_loop()
    test_build_scene()
    test_generate_impl_scene()
    test_generate_impl()
    test_generate_impl_facade()
    test_generate_impl_interior()
    test_model_choice_and_put()
    test_setup_threed()
    test_ifcviewer_autoload()
    test_widget_3d_modal()
    test_admin_threed_section()
    print("ALL OK")
