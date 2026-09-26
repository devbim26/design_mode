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
os.environ["THREED_ENSEMBLE"] = "0"  # ретро-тесты: без прогона B (п.60)

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
            {"kind": "box", "size": [1.0, 0.6, 0.6], "pos": [2.0, 0.3, 4.5],
             "rot_deg": 0, "color": "plinth"},
            {"kind": "prism", "size": [2.0, 0.8, 0.9], "pos": [-2.5, 0.3, 5.0],
             "profile": [[-1.0, 0.0], [1.0, 0.0], [0.0, 0.9]], "color": "roof"},
            {"kind": "cone", "size": [1.2, 1.2, 1.0], "pos": [0.0, 0.3, 8.0],
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


def test_build_facade_v2_villa():
    import ifcopenshell
    from threed.threed_scenarios import validate_facade
    from threed.threed_build import build_facade
    clean, _ = validate_facade(villa_raw())
    TMP.mkdir(exist_ok=True)
    ifc = TMP / "3D_v2_villa.ifc"
    prev = TMP / "3D_v2_villa_preview.png"
    build_facade(clean, ifc, prev, {"Scenario": "facade"})
    m = ifcopenshell.open(str(ifc))
    assert m.schema == "IFC4"
    counts = {}
    for p in m.by_type("IfcBuildingElementProxy"):
        counts[p.ObjectType] = counts.get(p.ObjectType, 0) + 1
    assert counts["CONCEPTUAL_TOWER"] == 2      # тело-цилиндр + конус
    assert counts["CONCEPTUAL_DORMER"] == 2
    assert counts["CONCEPTUAL_CHIMNEY"] == 1
    assert counts["CONCEPTUAL_ENTRANCE"] == 4   # portico: 2 колонны + навес + дверь
    # окна: сетка 2x2 без skip на каждом из 2 этажей + 2 dormer-остекления
    # (2*2*2: storeys × rows × cols — семантика v1, регресс test_build_facade)
    assert counts["CONCEPTUAL_WINDOW"] == 2 * 2 * 2 + 2
    assert counts["CONCEPTUAL_ROOF"] == 1       # hip
    assert counts["CONCEPTUAL_CUSTOM"] == 3
    # M1: круглой башне офсет по w_m (цилиндр игнорирует depth_m):
    # w=3, глубина здания 12 -> центр Y = -6 + 1.5 - 0.06
    tower = next(p for p in m.by_type("IfcBuildingElementProxy")
                 if p.ObjectType == "CONCEPTUAL_TOWER" and p.Name == "Башня 01")
    coords = tower.Representation.Representations[0].Items[0].Coordinates.CoordList
    assert abs(sum(c[1] for c in coords) / len(coords) - (-4.56)) < 0.01
    assert prev.is_file()
    print("test_build_facade_v2_villa OK")


def test_round_tower_depth_independent():
    """M1: меш-цилиндр башни не знает depth_m — эффективная глубина = w_m.
    Villa с towers[0].depth_m=5 (≠ w_m=3): центр Y обязан остаться -6+1.5-0.06,
    а не «боксовым» -6+2.5-0.06."""
    import ifcopenshell
    from threed.threed_scenarios import validate_facade
    from threed.threed_build import build_facade
    raw = villa_raw()
    raw["towers"][0]["depth_m"] = 5.0
    clean, _ = validate_facade(raw)
    TMP.mkdir(exist_ok=True)
    ifc = TMP / "3D_v2_tower.ifc"
    build_facade(clean, ifc, TMP / "3D_v2_tower_preview.png", {"Scenario": "facade"})
    m = ifcopenshell.open(str(ifc))
    tower = next(p for p in m.by_type("IfcBuildingElementProxy")
                 if p.ObjectType == "CONCEPTUAL_TOWER" and p.Name == "Башня 01")
    item = tower.Representation.Representations[0].Items[0]
    assert item.is_a("IfcPolygonalFaceSet")
    coords = item.Coordinates.CoordList
    center_y = sum(c[1] for c in coords) / len(coords)
    assert abs(center_y - (-6.0 + 1.5 - 0.06)) < 0.01, center_y
    print("test_round_tower_depth_independent OK")


def test_custom_parts_build():
    """Edge: cylinder+cone -> 2 CONCEPTUAL_CUSTOM, геометрия PolygonalFaceSet."""
    import ifcopenshell
    from ifcopenshell.util.placement import get_local_placement
    from threed.threed_scenarios import validate_facade
    from threed.threed_build import build_facade
    raw = _legacy().sample_facade_scene()
    raw["custom_parts"] = [
        {"kind": "cylinder", "size": [0.8, 0.8, 1.0], "pos": [3.0, 0.5, 0.0],
         "rot_deg": 0, "color": "plinth"},
        {"kind": "cone", "size": [1.0, 1.0, 0.8], "pos": [-3.0, 0.5, 1.0],
         "rot_deg": 0, "color": "#123456"},
    ]
    clean, _ = validate_facade(raw)
    TMP.mkdir(exist_ok=True)
    ifc = TMP / "3D_v2_custom.ifc"
    build_facade(clean, ifc, TMP / "3D_v2_custom_preview.png", {"Scenario": "facade"})
    m = ifcopenshell.open(str(ifc))
    customs = [p for p in m.by_type("IfcBuildingElementProxy")
               if p.ObjectType == "CONCEPTUAL_CUSTOM"]
    assert len(customs) == 2
    kinds = sorted(i.is_a() for p in customs
                   for r in p.Representation.Representations
                   for i in r.Items)
    assert any("PolygonalFaceSet" in k for k in kinds)
    # M5: pos.y — от фасадного фронта вглубь: мир Y = -depth/2 + yv
    # (depth 12, yv 0.5 -> центр цилиндра на -5.5, в плоскости фронта)
    cyl = next(p for p in customs if p.Name == "Деталь 01")
    assert abs(get_local_placement(cyl.ObjectPlacement)[1, 3] - (-5.5)) < 0.01
    print("test_custom_parts_build OK")


def test_chimney_clears_roof():
    """Ревью задачи 3: труба обязана выходить над коньком скатной крыши.

    Villa: hip, roof_height 1.8, storeys 2 × floor_height 4 -> карниз 8 м,
    конёк 9.8 м. База трубы min(floor,n)*fh-0.3 = 7.7; высота 1.2+rh = 3.0 ->
    верх 10.7 > конька (иначе труба целиком погребена под кровлей)."""
    import ifcopenshell
    from ifcopenshell.util.placement import get_local_placement
    from threed.threed_scenarios import validate_facade
    from threed.threed_build import build_facade
    clean, _ = validate_facade(villa_raw())
    TMP.mkdir(exist_ok=True)
    ifc = TMP / "3D_v2_chimney.ifc"
    build_facade(clean, ifc, TMP / "3D_v2_chimney_preview.png", {"Scenario": "facade"})
    m = ifcopenshell.open(str(ifc))
    chim = [p for p in m.by_type("IfcBuildingElementProxy")
            if p.ObjectType == "CONCEPTUAL_CHIMNEY"]
    assert len(chim) == 1
    item = chim[0].Representation.Representations[0].Items[0]
    assert item.is_a("IfcExtrudedAreaSolid")
    z = get_local_placement(chim[0].ObjectPlacement)[2, 3]
    assert abs(z - 7.7) < 0.01, z                    # база: 2*4 - 0.3
    assert abs(item.Depth - 3.0) < 0.01, item.Depth  # 1.2 + roof_height 1.8
    assert z + item.Depth > 2 * 4.0 + 1.8            # 10.7 > конёк 9.8
    print("test_chimney_clears_roof OK")


def _router():
    """Роутер дерева с модулями дерева. ГРАБЛЯ: threed_router импортирует
    threed_build/scenarios/verify из venv (try-ветка), где лежат копии
    последнего setup_threed.py — до деплоя v2 они устаревшие (валидатор
    режет towers/dormers, hip -> flat) и петля молока тестировала старый
    код. Привязываем текущие модули дерева напрямую."""
    import threed.threed_router as R
    from threed import threed_build, threed_scenarios, threed_verify
    R.threed_build, R.threed_scenarios, R.threed_verify = (
        threed_build, threed_scenarios, threed_verify)
    return R


def test_router_loop():
    """Задача 5: петля самокоррекции фасада — verify issues -> повторный
    анализ с блоком CORRECTIONS -> пересборка -> повторный verify; победитель
    по ok/числу issues (тай — последняя попытка)."""
    from PIL import Image
    R = _router()
    R._vlm_list_cached = lambda: []
    L = _legacy()
    os.environ["THREED_VERIFY"] = "1"   # ПОСЛЕ _legacy(): test_threed.py
    os.environ["THREED_VERIFY_ITERS"] = "1"  # на импорте ставит THREED_VERIFY=0
    scene_v1 = L.sample_facade_scene()          # итерация 1: без башни
    scene_v2 = dict(villa_raw())                # итерация 2: с деталями
    calls = []

    def branch(system, prompt, image_url, model):
        calls.append((system[:20], "CORRECTIONS" in prompt))
        if "QA verifier" in system:
            # system[:20] верификатора = "You are a BIM QA ver" (20 симв.):
            # startswith, а не == — литерал брифа короче на 1 символ
            if len([c for c in calls
                    if c[0].startswith("You are a BIM QA ve")]) == 1:
                return '{"ok": false, "issues": ["roof: built gable, image shows hip with tower"]}'
            return '{"ok": true, "issues": []}'
        return "```json\n" + json.dumps(
            scene_v1 if len(calls) == 1 else scene_v2, ensure_ascii=False) + "\n```"
    R._call_vlm = branch
    TMP.mkdir(exist_ok=True)
    img = Image.new("RGB", (600, 800), (250, 250, 250))
    before_ifc = {p.name for p in TMP.glob("3D_facade_*.ifc")}
    before_prev = {p.name for p in TMP.glob("3D_facade_*_preview.png")}
    res = R._generate_impl("facade", "тест петли", img, TMP)
    assert res["verify"]["verdict"]["ok"] is True      # победила итерация 2
    assert res["verify"]["iterations"] == 2
    # M3: вакуумный ассерт («... or True») заменён осмысленным: обзор
    # победителя — от итерации 2 (villa: hip, у сэмпла v1 — gable), и
    # круглая башня реально дошла до IFC (цилиндр + конус = 2 продукта)
    assert res["verify"]["overview"]["scene"]["roof"] == "hip"
    assert res["verify"]["overview"]["built"]["CONCEPTUAL_TOWER"] == 2
    dump = json.loads((TMP / "_threed_last.json").read_text(encoding="utf-8"))
    assert len(dump["verify"]["history"]) == 2
    assert any(c[1] for c in calls)                  # второй анализ с поправками
                                                          # (c[1] — bool «CORRECTIONS in prompt»)
    # победитель: файл IFC+превью на месте, проигравший удалён
    assert (TMP / res["name"]).is_file()
    assert res["name"].startswith("3D_facade_") and res["name"].endswith(".ifc")
    # M4(а): от этого прогона в TMP остался РОВНО один новый IFC — победителя
    # (с _r2) — и его превью; файлы проигравшей попытки 1 удалены
    after_ifc = {p.name for p in TMP.glob("3D_facade_*.ifc")}
    after_prev = {p.name for p in TMP.glob("3D_facade_*_preview.png")}
    assert after_ifc - before_ifc == {res["name"]}
    assert after_prev - before_prev == {Path(res["name"]).stem + "_preview.png"}

    # THREED_VERIFY_ITERS=0 -> одна итерация
    os.environ["THREED_VERIFY_ITERS"] = "0"
    calls.clear()
    R._call_vlm = branch
    res2 = R._generate_impl("facade", "", img, TMP)
    assert res2["verify"]["iterations"] == 1 and len(calls) == 2  # анализ+verify
    os.environ["THREED_VERIFY_ITERS"] = "1"

    # M4(б): победитель «меньше issues»: попытка 1 ok=False (2 issues),
    # попытка 2 ok=False (1 issue) -> берётся попытка 2 (файл _r2)
    verify_n = [0]

    def branch_rank(system, prompt, image_url, model):
        if "QA verifier" in system:
            verify_n[0] += 1
            return ('{"ok": false, "issues": ["storeys: built 5, image shows 4", '
                    '"roof: built gable, image shows hip"]}' if verify_n[0] == 1
                    else '{"ok": false, "issues": ["roof: built gable, image shows hip"]}')
        return "```json\n" + json.dumps(scene_v2, ensure_ascii=False) + "\n```"
    R._call_vlm = branch_rank
    res3 = R._generate_impl("facade", "", img, TMP)
    assert res3["name"].endswith("_r2.ifc") and (TMP / res3["name"]).is_file()
    assert res3["verify"]["verdict"]["ok"] is False
    assert len(res3["verify"]["verdict"]["issues"]) == 1
    assert res3["verify"]["iterations"] == 2
    print("test_router_loop OK")


def test_loop_iteration2_failure_survives():
    """C1 (ревью задачи 5): исключение в попытке >= 2 (повторный анализ
    кидает RuntimeError) НЕ роняет генерацию — победителем остаётся
    валидная попытка 1, cleanup проигравших и дамп выполняются
    (п.44: петля НИКОГДА не роняет генерацию)."""
    from PIL import Image
    R = _router()
    R._vlm_list_cached = lambda: []
    L = _legacy()                      # до env: test_threed.py ставит VERIFY=0
    os.environ["THREED_VERIFY"] = "1"
    os.environ["THREED_VERIFY_ITERS"] = "1"
    scene_v1 = L.sample_facade_scene()
    analyze_calls = []

    def branch(system, prompt, image_url, model):
        if "QA verifier" in system:    # итерация 1: ок, но с issues -> повтор
            return '{"ok": false, "issues": ["roof: built gable, image shows hip"]}'
        analyze_calls.append(prompt)
        if len(analyze_calls) >= 2:
            raise RuntimeError("сеть отвалилась на повторном анализе")
        return json.dumps(scene_v1)
    R._call_vlm = branch
    TMP.mkdir(exist_ok=True)
    img = Image.new("RGB", (600, 800), (250, 250, 250))
    res = R._generate_impl("facade", "C1", img, TMP)  # исключение НЕ всплывает
    assert res["verify"]["verdict"]["ok"] is False    # победитель = попытка 1
    assert res["verify"]["iterations"] == 2           # сбойная попытка 2 в history
    assert not res["name"].endswith("_r2.ifc")
    assert (TMP / res["name"]).is_file()              # файл попытки 1 жив
    dump = json.loads((TMP / "_threed_last.json").read_text(encoding="utf-8"))
    h = dump["verify"]["history"]
    assert len(h) == 2 and h[1]["verdict"]["ok"] is None
    assert "attempt failed" in h[1]["verdict"]["error"]
    print("test_loop_iteration2_failure_survives OK")


def test_loop_gate():
    """I2 (ревью задачи 5): повтор строго при ok is False И непустых issues.
    ok=None (verify кидает) и ок=False с пустыми issues вторую платную
    итерацию НЕ запускают — без CORRECTIONS исправлять нечем."""
    from PIL import Image
    R = _router()
    R._vlm_list_cached = lambda: []
    scene = _legacy().sample_facade_scene()   # до env: импорт ставит VERIFY=0
    os.environ["THREED_VERIFY"] = "1"
    os.environ["THREED_VERIFY_ITERS"] = "1"
    img = Image.new("RGB", (600, 800), (250, 250, 250))
    TMP.mkdir(exist_ok=True)

    def run(verify_answer=None, verify_raises=False):
        analyze = []

        def branch(system, prompt, image_url, model):
            if "QA verifier" in system:
                if verify_raises:
                    raise RuntimeError("500 Internal")
                return verify_answer
            analyze.append(1)
            return json.dumps(scene)
        R._call_vlm = branch
        return R._generate_impl("facade", "", img, TMP), len(analyze)

    # ok=None: verify кидает -> НЕТ второй итерации
    res, n = run(verify_raises=True)
    assert n == 1 and res["verify"]["iterations"] == 1
    assert res["verify"]["verdict"]["ok"] is None
    # ок=False с ПУСТЫМИ issues -> тоже нет второй итерации
    res, n = run('{"ok": false, "issues": []}')
    assert n == 1 and res["verify"]["iterations"] == 1
    assert res["verify"]["verdict"]["ok"] is False
    print("test_loop_gate OK")


def test_loop_rank_verified_wins():
    """Финальное ревью (ранг петли): попытка, чей verify ОТВЕТИЛ (ok=False
    + issues), бьёт попытку со сбоем verify (ok=None). Старый ранг
    (ok is True, -issues) давал (0,0) > (0,-1) — «молчаливая» попытка 2
    перебивала информативную попытку 1. Новый: (ok is True, ok is not None,
    -issues) — при прочих равных предпочитаем ответившего верификатора."""
    from PIL import Image
    R = _router()
    R._vlm_list_cached = lambda: []
    scene = _legacy().sample_facade_scene()   # до env: импорт ставит VERIFY=0
    os.environ["THREED_VERIFY"] = "1"
    os.environ["THREED_VERIFY_ITERS"] = "1"
    verify_n = [0]

    def branch(system, prompt, image_url, model):
        if "QA verifier" in system:
            verify_n[0] += 1
            if verify_n[0] == 1:  # попытка 1: verify ответил ok=False, 1 issue
                return '{"ok": false, "issues": ["storeys: built 5, image shows 4"]}'
            raise RuntimeError("500 Internal")  # попытка 2: verify сломался
        return json.dumps(scene)
    R._call_vlm = branch
    TMP.mkdir(exist_ok=True)
    img = Image.new("RGB", (600, 800), (250, 250, 250))
    res = R._generate_impl("facade", "", img, TMP)
    # победитель — ПОПЫТКА 1: её вердикт/обзор живы, файл жив, _r2 удалён
    assert res["verify"]["verdict"]["ok"] is False
    assert res["verify"]["verdict"]["issues"] == ["storeys: built 5, image shows 4"]
    assert res["verify"]["overview"]["scene"]["storeys"] == 5
    assert not res["name"].endswith("_r2.ifc") and (TMP / res["name"]).is_file()
    stem = Path(res["name"]).stem
    assert not (TMP / f"{stem}_r2.ifc").exists()
    assert not (TMP / f"{stem}_r2_preview.png").exists()
    dump = json.loads((TMP / "_threed_last.json").read_text(encoding="utf-8"))
    h = dump["verify"]["history"]
    assert len(h) == 2 and h[1]["verdict"]["ok"] is None  # сбой — в history
    print("test_loop_rank_verified_wins OK")


if __name__ == "__main__":
    test_validate_facade_v2()
    test_validate_facade_v2_guards()
    test_build_facade_v2_hip()
    test_build_facade_v2_villa()
    test_custom_parts_build()
    test_round_tower_depth_independent()
    test_chimney_clears_roof()
    test_router_loop()
    test_loop_iteration2_failure_survives()
    test_loop_gate()
    test_loop_rank_verified_wins()
    print("ALL OK")
