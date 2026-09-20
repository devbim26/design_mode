# -*- coding: utf-8 -*-
"""3D Design: тесты VLM-верификации собранной модели (пилот MCP4IFC-паттерна).

Обзор сцены (4 сценария), подсчёт построенного из готового IFC, разбор
вердикта, интеграция в роутер (вкл/выкл THREED_VERIFY, отказоустойчивость).
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ["THREED_VERIFY"] = "1"

TMP = ROOT / "tests" / "_threed_tmp"


def _legacy():
    """Модуль ретро-теста по пути файла: в venv есть сторонний пакет
    site-packages/tests, перекрывающий нашу папку как namespace-пакет."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "_threed_legacy_samples", ROOT / "tests" / "test_threed.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _samples():
    """Переиспользуем сэмплы ретро-теста (одна точка правды на сцену).
    ВАЖНО: test_threed на импорте ставит THREED_VERIFY=0 — возвращаем «1»."""
    L = _legacy()
    os.environ["THREED_VERIFY"] = "1"
    return {"plan": L.sample_scene(), "facade": L.sample_facade_scene(),
            "interior": L.sample_interior_scene(), "scene": L.sample_scene_scene()}


def test_scene_overview():
    from threed.threed_verify import scene_overview
    s = _samples()

    fac = scene_overview("facade", s["facade"])
    assert fac["storeys"] == 5 and fac["windows"]["cols"] == 4
    assert fac["windows"]["skipped_cells"] == 1  # skip-матрица = паттерн этажа
    assert fac["balconies_count"] == 2 and fac["roof"] == "gable"
    assert fac["colors"]["walls"] == "#d9c7a7"
    # v1-сэмпл: новых полей нет — нули/False и дефолт shape (обратная совместимость)
    assert fac["roof_height_m"] == 2.5 and fac["windows"]["shape"] == "rect"
    assert fac["dormers"] == 0 and fac["chimneys"] == 0 and fac["towers"] == 0
    assert fac["entrance"] is False and fac["custom_parts"] == 0

    # v2-поля фасада (финальное ревью): сторона A «задумано» обязана их
    # видеть, иначе верификатор не кросс-чекнет детали против B «построено»
    villa = {
        "storeys": 2, "floor_height": 4.0, "width_m": 9.5, "depth_m": 12.0,
        "roof": "hip", "roof_height": 1.8,
        "windows": {"rows": 2, "cols": 2, "w_m": 1.3, "h_m": 2.6,
                    "shape": "arched"},
        "balconies": [],
        "dormers": [{"floor": 2, "x_m": 3.0, "w_m": 1.4, "h_m": 1.6},
                    {"floor": 2, "x_m": 6.5, "w_m": 1.4, "h_m": 1.6}],
        "chimneys": [{"x_m": 2.0, "floor": 2}],
        "entrance": {"x_m": 4.75, "w_m": 2.2, "style": "portico"},
        "towers": [{"x_m": -4.75, "w_m": 3.0, "depth_m": 3.0, "floors": 3,
                    "round": True, "roof": "cone", "roof_h_m": 2.0}],
        "custom_parts": [{"kind": "box", "size": [1.0, 0.6, 0.6], "pos": [0, 0, 0]},
                         {"kind": "cylinder", "size": [1.0, 1.0, 1.0], "pos": [0, 0, 0]},
                         {"kind": "cone", "size": [1.0, 1.0, 1.0], "pos": [0, 0, 0]}],
        "colors": {},
    }
    v2 = scene_overview("facade", villa)
    assert v2["roof_height_m"] == 1.8          # hip тоже отдаёт высоту крыши
    assert v2["windows"]["shape"] == "arched"
    assert v2["dormers"] == 2 and v2["chimneys"] == 1
    assert v2["towers"] == 1 and v2["custom_parts"] == 3
    assert v2["entrance"] is True

    sc = scene_overview("scene", s["scene"])
    assert sc["buildings"] and sc["buildings"][0]["main"] is True
    assert isinstance(sc["context"]["trees"], int) and "azimuth_deg" in sc["camera"]
    # мягкие ассерты scene-сэмпла на новые ключи: нули/False, flat -> None
    b0 = sc["buildings"][0]
    assert b0["dormers"] == 0 and b0["chimneys"] == 0 and b0["towers"] == 0
    assert b0["entrance"] is False and b0["custom_parts"] == 0
    assert b0["windows"]["shape"] == "rect" and b0["roof_height_m"] is None
    assert sc["buildings"][1]["roof_height_m"] == 2.0  # gable

    pl = scene_overview("plan", s["plan"])
    assert {sec["id"] for sec in pl["sections"]} == {"Ж-1", "Ш-1"}
    assert pl["context_counts"].get("Ground") == 1

    it = scene_overview("interior", s["interior"])
    assert it["walls"] == 5 and it["rooms"] == 2
    assert it["openings"] == {"doors": 2, "windows": 1}
    assert it["furniture"].get("bed") == 1

    # пустая/битая сцена не взрывает обзор
    assert scene_overview("facade", {})["storeys"] is None
    print("test_scene_overview OK")


def test_built_overview():
    from threed.threed_build import build_facade
    from threed.threed_verify import built_overview
    s = _samples()
    TMP.mkdir(exist_ok=True)
    ifc = TMP / "3D_verify_facade.ifc"
    prev = TMP / "3D_verify_facade_preview.png"
    build_facade(s["facade"], ifc, prev, {"Scenario": "facade"})

    counts = built_overview(ifc)
    assert counts["CONCEPTUAL_STOREY"] == 5          # тома-этажи
    assert counts["CONCEPTUAL_WINDOW"] == 15         # 5 этажей × (4 − 1 skip)
    assert counts["CONCEPTUAL_BALCONY"] == 2
    assert counts["CONCEPTUAL_PLINTH"] == 1
    assert counts["CONCEPTUAL_ROOF"] == 1            # gable
    print("test_built_overview OK")


def test_verify_verdict_parse():
    from threed.threed_verify import SYSTEM_VERIFY, verify

    overview = {"scene": {"storeys": 5}, "built": {"CONCEPTUAL_STOREY": 5}}
    ok_text = '```json\n{"ok": true, "issues": []}\n```'
    seen_systems = []

    def branch(system, prompt, image_url, model):
        seen_systems.append(system)
        return ok_text
    v = verify("data:image/png;base64,x", overview, branch, "test/model")
    assert v == {"ok": True, "issues": []}
    assert any("QA verifier" in s for s in seen_systems)  # зовётся SYSTEM_VERIFY

    bad_text = '{"ok": false, "issues": ["storeys: built 5, image shows 4", "", null]}'
    v = verify("x", overview,
               lambda sys_, pr, img, m: bad_text, "test/model")
    assert v["ok"] is False and v["issues"] == ["storeys: built 5, image shows 4"]

    # строковый ok / не-JSON / исключение VLM -> ok=None
    v = verify("x", overview, lambda *a: '{"ok": "true"}', "m")
    assert v["ok"] is True
    v = verify("x", overview, lambda *a: "мусор", "m")
    assert v["ok"] is None and "error" in v
    def boom(*a):
        raise RuntimeError("сеть отвалилась")
    v = verify("x", overview, boom, "m")
    assert v["ok"] is None and "сеть" in v["error"]

    # ok=true с мусорными issues — замечания затираются (правило промпта)
    v = verify("x", overview, lambda *a: '{"ok": true, "issues": ["x"]}', "m")
    assert v["issues"] == []
    assert "STRICT JSON" in SYSTEM_VERIFY and "ok" in SYSTEM_VERIFY
    print("test_verify_verdict_parse OK")


def test_generate_impl_with_verify():
    """Роутер: ветвящийся мок (анализ -> сцена, верификация -> вердикт)."""
    from PIL import Image
    import threed.threed_router as R
    R._vlm_list_cached = lambda: []
    R._model_store_path = lambda: TMP / "missing_threed_model.json"
    scene = _samples()["facade"]

    def branch(system, prompt, image_url, model):
        if "QA verifier" in system:
            assert '"CONCEPTUAL_WINDOW": 15' in prompt  # обзор «построено» дошёл
            return '{"ok": true, "issues": []}'
        return "```json\n" + json.dumps(scene, ensure_ascii=False) + "\n```"
    R._call_vlm = branch
    TMP.mkdir(exist_ok=True)
    img = Image.new("RGB", (600, 800), (250, 250, 250))
    res = R._generate_impl("facade", "тест верификации", img, TMP)
    assert res["verify"]["verdict"] == {"ok": True, "issues": []}
    assert res["verify"]["overview"]["scene"]["storeys"] == 5
    assert res["verify"]["overview"]["built"]["CONCEPTUAL_STOREY"] == 5
    dump = json.loads((TMP / "_threed_last.json").read_text(encoding="utf-8"))
    assert dump["verify"]["verdict"]["ok"] is True

    # THREED_VERIFY=0 -> второго запроса нет, ключа verify нет
    os.environ["THREED_VERIFY"] = "0"
    try:
        res2 = R._generate_impl("facade", "", img, TMP)
        assert "verify" not in res2
    finally:
        os.environ["THREED_VERIFY"] = "1"
    print("test_generate_impl_with_verify OK")


def test_verify_never_breaks():
    """Сбой верификации (VLM кидает / не JSON) не роняет генерацию."""
    from PIL import Image
    import threed.threed_router as R
    R._vlm_list_cached = lambda: []
    scene = _samples()["facade"]

    def branch(system, prompt, image_url, model):
        if "QA verifier" in system:
            raise RuntimeError("500 Internal")
        return json.dumps(scene)
    R._call_vlm = branch
    TMP.mkdir(exist_ok=True)
    img = Image.new("RGB", (600, 800), (250, 250, 250))
    res = R._generate_impl("facade", "", img, TMP)
    assert res["name"].startswith("3D_facade_") and (TMP / res["name"]).is_file()
    assert res["verify"]["verdict"]["ok"] is None
    assert "500" in res["verify"]["verdict"]["error"]

    # не-JSON от верификатора — та же деградация
    R._call_vlm = lambda system, p, i, m: (
        "нет json" if "QA verifier" in system else json.dumps(scene))
    res2 = R._generate_impl("facade", "", img, TMP)
    assert res2["verify"]["verdict"]["ok"] is None
    print("test_verify_never_breaks OK")


def test_generate_impl_scene_loop():
    """Петля самокоррекции работает и для сцены (п.46-4; раньше только
    facade): ok=False+issues -> повторный анализ с CORRECTIONS -> ok=True
    побеждает (файл победителя _r2)."""
    from PIL import Image
    import threed.threed_router as R
    R._vlm_list_cached = lambda: []
    R._model_store_path = lambda: TMP / "missing_threed_model.json"
    scene = _samples()["scene"]
    calls = {"scene": 0, "verify": 0, "saw_corrections": False}

    def branch(system, prompt, image_url, model):
        if "QA verifier" in system:
            calls["verify"] += 1
            return json.dumps(
                {"ok": False,
                 "issues": ["Furniture: built none, image shows a balcony lounger."]}
                if calls["verify"] == 1 else {"ok": True, "issues": []})
        calls["scene"] += 1
        if calls["scene"] == 2:
            calls["saw_corrections"] = "CORRECTIONS" in prompt
        return json.dumps(scene, ensure_ascii=False)

    R._call_vlm = branch
    TMP.mkdir(exist_ok=True)
    img = Image.new("RGB", (691, 647), (250, 250, 250))
    res = R._generate_impl("scene", "тест петли", img, TMP)
    assert calls["scene"] == 2 and calls["verify"] == 2 and calls["saw_corrections"]
    assert res["name"].endswith("_r2.ifc")
    assert (TMP / res["name"]).is_file()
    assert res["verify"]["verdict"]["ok"] is True and res["verify"]["iterations"] == 2
    print("test_generate_impl_scene_loop OK")


if __name__ == "__main__":
    test_scene_overview()
    test_built_overview()
    test_verify_verdict_parse()
    test_generate_impl_with_verify()
    test_generate_impl_scene_loop()
    test_verify_never_breaks()
    print("ALL OK")
