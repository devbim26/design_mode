# -*- coding: utf-8 -*-
"""3D Design: tiered-конвейер п.56 — per-stage модели (override/отключение),
ремонт JSON без картинки с гейтом, эскалация одной попыткой.

THREED_VERIFY=1 на импорте НЕ ставим модульно: _legacy() переисполняет
test_threed.py, который ставит 0 (грабля п.46-1) — каждый тест включает
verify сам ПОСЛЕ _legacy(). Роутер — с модулями дерева (грабля п.45-3).
"""
import importlib.util
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TMP = ROOT / "tests" / "_threed_tmp"

_STAGE_ENV_KEYS = ("THREED_MODEL", "THREED_ANALYSIS_MODEL", "THREED_REPAIR_MODEL",
                   "THREED_VERIFY_MODEL", "THREED_ESCALATION_MODEL",
                   "THREED_VERIFY_ITERS")


def _legacy():
    """Сэмплы ретро-файла одной точкой правды (переисполняет test_threed.py)."""
    spec = importlib.util.spec_from_file_location(
        "_threed_legacy_samples_tiered", ROOT / "tests" / "test_threed.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _router():
    """Роутер дерева с модулями дерева: threed_router импортирует
    build/scenarios/verify из venv, где копии деплоя могут отставать."""
    import threed.threed_router as R
    from threed import threed_build, threed_scenarios, threed_verify
    R.threed_build, R.threed_scenarios, R.threed_verify = (
        threed_build, threed_scenarios, threed_verify)
    return R


class _Env:
    """Изолированный набор THREED*-рулек на блок: чужие снимает, свои
    ставит, на выходе восстанавливает."""

    def __init__(self, **kw):
        self.kw = kw
        self.saved = {}

    def __enter__(self):
        for k in _STAGE_ENV_KEYS:
            self.saved[k] = os.environ.get(k)
            os.environ.pop(k, None)
        for k, v in self.kw.items():
            os.environ[k] = v
        return self

    def __exit__(self, *a):
        for k, v in self.saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _dump():
    return json.loads((TMP / "_threed_last.json").read_text(encoding="utf-8"))


def test_stage_model_resolution():
    """Дефолты стадий, per-stage рульки, полный override THREED_MODEL
    (env и file-store), пустая эскалация = выключено."""
    R = _router()
    R._vlm_list_cached = lambda: []
    TMP.mkdir(exist_ok=True)
    missing = lambda: TMP / "missing_tiered_model.json"
    R._model_store_path = missing
    _legacy()  # если юзер запускал verify-файл до нас — чистим рульки

    with _Env():
        assert R._stage_model("analysis") == ("openai/gpt-6-astra", "default")
        assert R._stage_model("repair") == ("openai/gpt-6-luna", "default")
        assert R._stage_model("verify") == ("openai/gpt-6-astra", "default")
        assert R._stage_model("escalation") == ("openai/gpt-6-astra", "default")
    with _Env(THREED_ANALYSIS_MODEL="fake/sol", THREED_REPAIR_MODEL="fake/mini"):
        assert R._stage_model("analysis") == ("fake/sol", "env:stage")
        assert R._stage_model("repair") == ("fake/mini", "env:stage")
        assert R._stage_model("verify") == ("openai/gpt-6-astra", "default")
    with _Env(THREED_ESCALATION_MODEL=""):
        assert R._stage_model("escalation") == ("", "off")
    with _Env(THREED_MODEL="fake/one", THREED_ANALYSIS_MODEL="fake/sol"):
        assert all(R._stage_model(s) == ("fake/one", "env") for s in R.STAGES), \
            "THREED_MODEL обязан глушить per-stage"

    # file-store (PUT /model) — тоже полный override
    p = TMP / "tiered_model.json"
    p.write_text(json.dumps({"model": "x/vlm-9"}), encoding="utf-8")
    R._model_store_path = lambda: p
    try:
        with _Env(THREED_ANALYSIS_MODEL="fake/sol"):
            assert all(R._stage_model(s) == ("x/vlm-9", "file") for s in R.STAGES)
    finally:
        R._model_store_path = missing
        p.unlink(missing_ok=True)
    print("test_stage_model_resolution OK")


def test_routing_analysis_repair_verify():
    """interior c мебелью вне комнат: порядок стадий analysis(astra) ->
    repair(luna, БЕЗ картинки) -> verify(astra); чистая сцена ремонт не
    запускает (счастливый путь не платит)."""
    from PIL import Image
    R = _router()
    R._vlm_list_cached = lambda: []
    R._model_store_path = lambda: TMP / "missing_tiered_model.json"
    L = _legacy()
    os.environ["THREED_VERIFY"] = "1"
    TMP.mkdir(exist_ok=True)

    bad = L.sample_interior_scene()
    bad["furniture"][1]["x_px"] = 60           # стол вне комнат -> issue
    fixed = L.sample_interior_scene()          # ремонт ставит стол на место
    calls = []

    def branch(system, prompt, image_url, model):
        if "data fixer" in system:
            calls.append(("repair", model, image_url))
            assert "вне комнат" in prompt and "Scene JSON:" in prompt
            return json.dumps(fixed, ensure_ascii=False)
        if "QA verifier" in system:
            calls.append(("verify", model, image_url))
            return '{"ok": true, "issues": []}'
        calls.append(("analysis", model, image_url))
        return "```json\n" + json.dumps(bad, ensure_ascii=False) + "\n```"

    R._call_vlm = branch
    img = Image.new("RGB", (80, 40), (250, 250, 248))
    with _Env():
        res = R._generate_impl("interior", "тест tiered", img, TMP)
    kinds = [c[0] for c in calls]
    assert kinds == ["analysis", "repair", "verify"], kinds
    assert calls[0][1] == "openai/gpt-6-astra"
    assert calls[1][1] == "openai/gpt-6-luna"
    assert calls[1][2] is None and calls[0][2] and calls[2][2], \
        "ремонт — text-only, анализ/verify — с картинкой"
    assert any("ремонт" in w for w in res["warnings"])
    d = _dump()
    assert d["verify"]["history"][0]["contract_issues"] == []  # ремонт помог
    assert d["stages"]["repair"] == "openai/gpt-6-luna"

    # счастливый путь: контракт чист — ремонт не вызывается
    calls.clear()
    ok_scene = L.sample_interior_scene()

    def branch_ok(system, prompt, image_url, model):
        if "QA verifier" in system:
            calls.append(("verify", model, image_url))
            return '{"ok": true, "issues": []}'
        calls.append(("analysis", model, image_url))
        return json.dumps(ok_scene, ensure_ascii=False)

    R._call_vlm = branch_ok
    with _Env():
        R._generate_impl("interior", "", img, TMP)
    assert [c[0] for c in calls] == ["analysis", "verify"]
    print("test_routing_analysis_repair_verify OK")


def test_repair_gate():
    """Гейт ремонта: кривой JSON на luna -> ОДИН повтор на sol -> валидный
    принят; оба кривые -> issues остаются и едут в CORRECTIONS итерации 2."""
    from PIL import Image
    R = _router()
    R._vlm_list_cached = lambda: []
    R._model_store_path = lambda: TMP / "missing_tiered_model.json"
    L = _legacy()
    os.environ["THREED_VERIFY"] = "1"
    TMP.mkdir(exist_ok=True)

    bad = L.sample_interior_scene()
    bad["furniture"][1]["x_px"] = 60
    fixed = L.sample_interior_scene()
    img = Image.new("RGB", (80, 40), (250, 250, 248))

    # (а) мусор от luna -> повтор на sol с тем же промптом -> принято
    repair_calls = []

    def branch(system, prompt, image_url, model):
        if "data fixer" in system:
            repair_calls.append(model)
            return "мусор не json" if len(repair_calls) == 1 \
                else json.dumps(fixed, ensure_ascii=False)
        if "QA verifier" in system:
            return '{"ok": true, "issues": []}'
        return json.dumps(bad, ensure_ascii=False)

    R._call_vlm = branch
    with _Env(THREED_VERIFY_ITERS="1"):
        res = R._generate_impl("interior", "", img, TMP)
    assert repair_calls == ["openai/gpt-6-luna", "openai/gpt-6-sol"]
    assert any("ремонт openai/gpt-6-sol" in w for w in res["warnings"])
    assert _dump()["verify"]["history"][0]["contract_issues"] == []

    # (б) оба ответа кривые -> issues контракта доехали до CORRECTIONS
    repair_calls.clear()
    analyze_prompts = []

    def branch2(system, prompt, image_url, model):
        if "data fixer" in system:
            repair_calls.append(model)
            return "опять мусор"
        if "QA verifier" in system:
            return '{"ok": false, "issues": ["rooms: built 2, image shows 3"]}'
        analyze_prompts.append(prompt)
        return json.dumps(bad, ensure_ascii=False)

    R._call_vlm = branch2
    with _Env(THREED_VERIFY_ITERS="1"):
        R._generate_impl("interior", "", img, TMP)
    # ремонт перезапускается в КАЖДОЙ попытке (анализ снова вернул битую
    # сцену -> снова issues -> снова luna+sol)
    assert repair_calls == ["openai/gpt-6-luna", "openai/gpt-6-sol"] * 2
    assert len(analyze_prompts) == 2
    assert "вне комнат" in analyze_prompts[1], \
        "issues контракта обязаны ехать в CORRECTIONS следующей итерации"
    assert "rooms: built 2" in analyze_prompts[1]
    d = _dump()
    assert d["verify"]["history"][0]["contract_issues"] != []
    print("test_repair_gate OK")


def test_escalation_single_attempt():
    """Раунд на дешёвой analysis (fake/sol) с ok=False -> ОДНА финальная
    попытка _r3 на эскалационной astra с накопленным CORRECTIONS; verify
    всегда на своей модели; победитель по рейтингу, проигравшие вычищены."""
    from PIL import Image
    R = _router()
    R._vlm_list_cached = lambda: []
    R._model_store_path = lambda: TMP / "missing_tiered_model.json"
    L = _legacy()
    os.environ["THREED_VERIFY"] = "1"
    scene = L.sample_facade_scene()
    calls = []
    analyze_prompts = []

    def branch(system, prompt, image_url, model):
        if "QA verifier" in system:
            calls.append(("verify", model))
            return '{"ok": false, "issues": ["storeys: built 5, image shows 4"]}'
        calls.append(("analysis", model))
        analyze_prompts.append(prompt)
        return json.dumps(scene, ensure_ascii=False)

    R._call_vlm = branch
    TMP.mkdir(exist_ok=True)
    img = Image.new("RGB", (600, 800), (250, 250, 250))
    with _Env(THREED_ANALYSIS_MODEL="fake/sol", THREED_VERIFY_ITERS="1"):
        res = R._generate_impl("facade", "эскалация", img, TMP)
    assert [c[0] for c in calls] == ["analysis", "verify"] * 3, calls
    assert [c[1] for c in calls] == ["fake/sol", "openai/gpt-6-astra",
                                     "fake/sol", "openai/gpt-6-astra",
                                     "openai/gpt-6-astra", "openai/gpt-6-astra"]
    assert res["name"].endswith("_r3.ifc") and (TMP / res["name"]).is_file()
    d = _dump()
    h = d["verify"]["history"]
    assert len(h) == 3 and [e["attempt"] for e in h] == [1, 2, 3]
    assert "CORRECTIONS" in analyze_prompts[2]
    assert "storeys: built 5" in analyze_prompts[2], "эскалация получает полный пул"
    assert d["stages"] == {"analysis": "fake/sol", "repair": "openai/gpt-6-luna",
                           "verify": "openai/gpt-6-astra",
                           "escalation": "openai/gpt-6-astra"}
    # проигравшие попытки вычищены, остался только победитель _r3
    base = res["name"].replace("_r3.ifc", ".ifc")
    assert not (TMP / base).exists()
    assert not (TMP / base.replace(".ifc", "_r2.ifc")).exists()
    print("test_escalation_single_attempt OK")


def test_escalation_disabled_and_override():
    """Пустой THREED_ESCALATION_MODEL выключает эскалацию; THREED_MODEL
    глушит per-stage — все вызовы на одной модели, эскалации нет."""
    from PIL import Image
    R = _router()
    R._vlm_list_cached = lambda: []
    R._model_store_path = lambda: TMP / "missing_tiered_model.json"
    L = _legacy()
    os.environ["THREED_VERIFY"] = "1"
    scene = L.sample_facade_scene()
    img = Image.new("RGB", (600, 800), (250, 250, 250))
    TMP.mkdir(exist_ok=True)

    def branch(system, prompt, image_url, model):
        if "QA verifier" in system:
            return '{"ok": false, "issues": ["storeys: built 5, image shows 4"]}'
        return json.dumps(scene, ensure_ascii=False)

    R._call_vlm = branch
    with _Env(THREED_ANALYSIS_MODEL="fake/sol", THREED_ESCALATION_MODEL="",
              THREED_VERIFY_ITERS="1"):
        res = R._generate_impl("facade", "", img, TMP)
    assert res["name"].endswith("_r2.ifc"), "эскалации быть не должно"
    assert not res["name"].endswith("_r3.ifc")

    # полный override: все стадии (и verify) на одной модели
    seen = []

    def branch_seen(system, prompt, image_url, model):
        seen.append(model)
        if "QA verifier" in system:
            return '{"ok": false, "issues": ["x"]}'
        return json.dumps(scene, ensure_ascii=False)

    R._call_vlm = branch_seen
    with _Env(THREED_MODEL="fake/one", THREED_ANALYSIS_MODEL="fake/sol",
              THREED_ESCALATION_MODEL="openai/gpt-6-astra",
              THREED_VERIFY_ITERS="1"):
        res2 = R._generate_impl("facade", "", img, TMP)
    assert set(seen) == {"fake/one"}, seen
    assert res2["name"].endswith("_r2.ifc"), \
        "analysis == escalation при override — эскалации нет"
    print("test_escalation_disabled_and_override OK")


if __name__ == "__main__":
    test_stage_model_resolution()
    test_routing_analysis_repair_verify()
    test_repair_gate()
    test_escalation_single_attempt()
    test_escalation_disabled_and_override()
    print("ALL OK")
