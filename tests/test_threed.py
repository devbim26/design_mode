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
    assert "toast(t().soon)" not in src.split("function build()")[1].split("function isYellow")[0]
    print("test_widget_3d_modal OK")


def test_admin_threed_section():
    src = (ROOT / "imagerouter" / "imagerouter.html").read_text(encoding="utf-8")
    assert 'id="threedsec"' in src
    assert "/api/v1/threed/model" in src
    assert 'id="threed-save"' in src
    print("test_admin_threed_section OK")


if __name__ == "__main__":
    test_build_genplan()
    test_extract_json()
    test_validate_genplan()
    test_generate_impl()
    test_model_choice_and_put()
    test_setup_threed()
    test_ifcviewer_autoload()
    test_widget_3d_modal()
    test_admin_threed_section()
    print("ALL OK")
