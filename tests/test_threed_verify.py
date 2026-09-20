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

    sc = scene_overview("scene", s["scene"])
    assert sc["buildings"] and sc["buildings"][0]["main"] is True
    assert isinstance(sc["context"]["trees"], int) and "azimuth_deg" in sc["camera"]

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


if __name__ == "__main__":
    test_scene_overview()
    test_built_overview()
    test_verify_verdict_parse()
    test_generate_impl_with_verify()
    test_verify_never_breaks()
    print("ALL OK")
