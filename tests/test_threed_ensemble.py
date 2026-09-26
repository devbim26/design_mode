# -*- coding: utf-8 -*-
"""Ансамбль: compare/merge/реферти (Task 5) + интеграция в роутер (Task 8).
Часть функций — чистые (этот файл, без venv); роутерные — через изолятор."""
import copy
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from threed import threed_ensemble as E  # noqa: E402


def _facade(storeys=5, width=20.0, fh=3.0, rows=2, cols=4, skip=None,
            entrance=True):
    return {"storeys": storeys, "floor_height": fh, "width_m": width,
            "depth_m": 12.0, "roof": "flat", "roof_height": 2.5,
            "windows": {"rows": rows, "cols": cols, "w_m": 1.5, "h_m": 1.5,
                        "margin_x_m": 1.0, "margin_y_m": 0.8,
                        "skip": skip if skip is not None else
                        [[False] * cols for _ in range(rows)],
                        "shape": "rect"},
            "entrance": ({"x_m": 10.0, "w_m": 2.0, "style": "porch"}
                         if entrance else None),
            "balconies": [], "dormers": [], "chimneys": [], "towers": [],
            "custom_parts": [], "colors": {"walls": "#c8b89a"}}


def test_compare_full_agreement():
    A, B = _facade(), _facade(width=20.5)  # Δwidth 2.5% < 15%
    cmp = E.compare_scenes("facade", A, B)
    assert cmp["disputed"] == {}, cmp["disputed"]
    assert cmp["agree_rate"] == 1.0
    assert set(cmp["agreed"]) == {"storeys", "width_m", "floor_height",
                                  "windows.rows", "windows.cols",
                                  "windows.skip", "entrance"}
    print("test_compare_full_agreement OK")


def test_compare_disputes():
    A = _facade()
    B = _facade(storeys=3, width=30.0, fh=3.6, rows=1, entrance=False)
    cmp = E.compare_scenes("facade", A, B)
    # skip спорит из-за формы (rows differ -> матрицы разного размера)
    assert set(cmp["disputed"]) == {"storeys", "width_m", "floor_height",
                                    "windows.rows", "windows.skip",
                                    "entrance"}, cmp["disputed"]
    assert cmp["agree_rate"] == round(1 / 7, 3)  # согласован только cols
    assert abs(cmp["metrics"]["width_m_pct"] - 10 / 30) < 1e-3  # /max(a,b)
    print("test_compare_disputes OK")


def test_skip_dispute_two_cells():
    A = _facade()
    B = _facade()
    B["windows"]["skip"] = [[True, True, False, False], [False] * 4]
    cmp = E.compare_scenes("facade", A, B)
    assert "windows.skip" in cmp["disputed"], "Δ=2 клетки -> спор"
    B2 = _facade()
    B2["windows"]["skip"] = [[True, False, False, False], [False] * 4]
    cmp2 = E.compare_scenes("facade", A, B2)
    assert "windows.skip" not in cmp2["disputed"], "Δ=1 клетка — согласовано"
    print("test_skip_dispute_two_cells OK")


def test_merge_average_and_referee():
    A, B = _facade(width=20.0), _facade(width=21.0)  # Δ5% — согласовано
    cmp = E.compare_scenes("facade", A, B)
    scene, conf, wns = E.merge_scenes("facade", A, B, cmp)
    assert abs(scene["width_m"] - 20.5) < 1e-9, "согласованный float — среднее"
    assert conf["agree_rate"] == 1.0 and conf["referee_used"] is False
    assert not wns

    # спор: реферти выбирает B по storeys, молчит по width_m
    A2, B2 = _facade(storeys=5), _facade(storeys=3, width=40.0)
    cmp2 = E.compare_scenes("facade", A2, B2)
    assert set(cmp2["disputed"]) == {"storeys", "width_m"}
    calls = []

    def referee(fields):
        calls.append(fields)
        return {"choices": {"storeys": "B"}}

    scene2, conf2, wns2 = E.merge_scenes("facade", A2, B2, cmp2, referee=referee)
    assert calls and calls[0] == ["storeys", "width_m"], "спорные поля по алфавиту"
    assert scene2["storeys"] == 3, "выбор B применён"
    assert scene2["width_m"] == 20.0, "реферти молчит -> вариант A"
    assert conf2["referee_used"] is True
    assert any("width_m" in w for w in wns2), "неспособный реферти -> A + warning"

    # реферти выбрал B по ОБОИМ полям -> оба из B
    scene2b, _, _ = E.merge_scenes(
        "facade", A2, B2, cmp2,
        referee=lambda f: {"choices": {"storeys": "B", "width_m": "B"}})
    assert scene2b["storeys"] == 3 and scene2b["width_m"] == 40.0

    # сбой реферти (None) -> всё A, генерация не падает
    scene3, conf3, wns3 = E.merge_scenes(
        "facade", A2, B2, cmp2, referee=lambda f: None)
    assert scene3["storeys"] == 5 and scene3["width_m"] == 20.0
    assert conf3["referee_used"] is False and wns3
    # входы не мутируются
    assert A2["storeys"] == 5 and B2["width_m"] == 40.0
    print("test_merge_average_and_referee OK")


def test_merge_flag_field_types():
    """C1 (финальное ревью): flag-поля (entrance) в merge берут ИСХОДНОЕ
    значение B (dict | None), а не нормализованное 0/1 из compare — иначе
    build_facade падает на e["x_m"], роняя генерацию (инвариант «сбой части
    ансамбля — warning + работа с A»)."""
    # (a) A без входа, B со входом, реферти выбрал B -> merged = DICT из B
    A = _facade(entrance=False)
    B = _facade(entrance=True)
    cmp = E.compare_scenes("facade", A, B)
    assert cmp["disputed"] == {"entrance": (0, 1)}, cmp["disputed"]
    scene, _, wns = E.merge_scenes(
        "facade", A, B, cmp, referee=lambda f: {"choices": {"entrance": "B"}})
    assert isinstance(scene["entrance"], dict), \
        f"entrance должен быть dict из B, а не {scene['entrance']!r}"
    assert scene["entrance"] == B["entrance"]
    # доступ в стиле threed_build.build_facade не падает
    e = scene["entrance"]
    _ = e["x_m"] - 10.0, e["w_m"] / 2, e["style"]

    # (b) A со входом, B без, реферти выбрал B -> merged = None («входа нет»)
    A2, B2 = _facade(entrance=True), _facade(entrance=False)
    cmp2 = E.compare_scenes("facade", A2, B2)
    scene2, _, _ = E.merge_scenes(
        "facade", A2, B2, cmp2, referee=lambda f: {"choices": {"entrance": "B"}})
    assert scene2["entrance"] is None, repr(scene2["entrance"])

    # (c) реферти выбрал A -> dict из A остаётся как был
    scene3, _, _ = E.merge_scenes(
        "facade", A, B, cmp, referee=lambda f: {"choices": {"entrance": "A"}})
    assert scene3["entrance"] is None
    print("test_merge_flag_field_types OK")


def test_referee_prompt_shape():
    assert "A" in E.SYSTEM_REFEREE and "B" in E.SYSTEM_REFEREE
    s = {"windows": {"rows": 2}}
    assert E._get(s, "windows.rows") == 2
    E._set(s, "windows.rows", 3)
    assert s["windows"]["rows"] == 3
    print("test_referee_prompt_shape OK")


# ===================== plan + interior (Task 9) =====================

def _plan_scene(n=3, floors=(5, 3, 2), scale=0.25):
    def poly(i):
        x = 100 + i * 250
        return [[x, 100], [x + 200, 100], [x + 200, 300], [x, 300]]
    return {"trace_width": 1024, "trace_height": 768,
            "metres_per_trace_pixel": scale,
            "residential_storey_height": 3.1, "public_storey_height": 3.3,
            "sections": [{"id": f"B{i}", "building": f"B{i}",
                          "use": "Residential", "floors": floors[i],
                          "points_px": poly(i), "partial": False}
                         for i in range(n)],
            "context": [{"kind": "Ground", "z": -0.45, "depth": 0.35,
                         "points_px": [[0, 0], [1024, 0], [1024, 768],
                                       [0, 768]]}]}


def test_compare_plan():
    A = _plan_scene()
    B = _plan_scene(floors=(5, 3, 5))          # спор floors (Δ=3 у 3-й)
    cmp = E.compare_scenes("plan", A, B)
    assert cmp["disputed"] == {"floors": (2, 5)}, cmp["disputed"]
    B2 = _plan_scene(n=2)                      # спор числа секций
    cmp2 = E.compare_scenes("plan", A, B2)
    assert "sections_count" in cmp2["disputed"]
    # IoU футпринтов: B сдвинул первую секцию на 150 px (>40% ширины)
    B3 = _plan_scene()
    B3["sections"][0]["points_px"] = [[400, 100], [600, 100],
                                      [600, 300], [400, 300]]
    cmp3 = E.compare_scenes("plan", A, B3)
    assert "footprint_iou" in cmp3["disputed"], cmp3["disputed"]
    print("test_compare_plan OK")


def test_merge_plan_component():
    A, B = _plan_scene(), _plan_scene(floors=(5, 3, 5))
    cmp = E.compare_scenes("plan", A, B)
    # реферти выбирает B по floors -> секции ЦЕЛИКОМ из B (компонентно)
    scene, conf, wns = E.merge_scenes(
        "plan", A, B, cmp, referee=lambda f: {"choices": {"floors": "B"}})
    assert scene["sections"][2]["floors"] == 5
    assert scene["metres_per_trace_pixel"] == 0.25  # scale не спорили
    # большинство за A -> секции A
    scene2, _, _ = E.merge_scenes(
        "plan", A, B, cmp, referee=lambda f: {"choices": {}})
    assert scene2["sections"][2]["floors"] == 2
    print("test_merge_plan_component OK")


def _interior_scene(rooms=3, doors=2, windows=1):
    walls = [[(60, 60), (460, 60)], [(460, 60), (460, 640)],
             [(460, 640), (60, 640)], [(60, 640), (60, 60)],
             [(60, 350), (460, 350)]]
    return {"trace_width": 900, "trace_height": 700,
            "metres_per_trace_pixel": 0.01, "wall_height": 2.7,
            "outline": [[60, 60], [460, 60], [460, 640], [60, 640]],
            "walls": [{"points_px": list(w), "thickness_m": 0.35,
                       "exterior": True} for w in walls],
            "openings": ([{"wall_idx": 1, "x_px": 130.0, "width_m": 0.9,
                           "height_m": 2.1, "sill_m": 0.0, "kind": "door"}]
                         * doors
                         + [{"wall_idx": 2, "x_px": 140.0, "width_m": 1.2,
                             "height_m": 1.5, "sill_m": 0.9,
                             "kind": "window"}] * windows),
            "rooms": [{"name": f"R{i}", "type": "other",
                       "points_px": [[60, 60], [300, 60], [300, 350],
                                     [60, 350]]} for i in range(rooms)],
            "furniture": []}


def test_compare_interior():
    A = _interior_scene()
    B = _interior_scene(doors=4)
    cmp = E.compare_scenes("interior", A, B)
    assert cmp["disputed"] == {"doors_count": (2, 4)}, cmp["disputed"]
    B2 = _interior_scene(rooms=5)
    assert "rooms_count" in E.compare_scenes("interior", A, B2)["disputed"]
    print("test_compare_interior OK")


# ===================== роутерная часть (Task 8: изолятор + интеграция) =====================

TMP = ROOT / "tests" / "_threed_tmp"

_ENS_ENV_KEYS = ("THREED_ENSEMBLE", "THREED_ENSEMBLE_MODEL",
                 "THREED_REFEREE_MODEL", "THREED_MAX_CALLS_PER_ATTEMPT")


class _Env:
    """THREED*-рульки на блок: ensemble-ключи + собственные kwargs снимает/
    ставит, на выходе восстанавливает ВСЁ, что трогал (паттерн
    test_threed_tiered._Env, расширен на ensemble-рульки)."""

    def __init__(self, **kw):
        self.kw, self.saved = kw, {}

    def __enter__(self):
        for k in dict.fromkeys((*_ENS_ENV_KEYS, *self.kw)):
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


def _router():
    """Роутер дерева с модулями дерева: threed_router импортирует
    build/scenarios/verify/ground/ensemble/regular из venv, где копии
    деплоя могут отставать (грабля п.45-3 / п.58а)."""
    import threed.threed_router as R
    from threed import (threed_build, threed_scenarios, threed_verify,
                        threed_ground, threed_ensemble, threed_regular)
    R.threed_build, R.threed_scenarios, R.threed_verify = (
        threed_build, threed_scenarios, threed_verify)
    R.threed_ground, R.threed_ensemble, R.threed_regular = (
        threed_ground, threed_ensemble, threed_regular)
    return R


def _facade_json():
    return json.dumps(_facade(), ensure_ascii=False)


def test_router_ensemble_happy_path():
    """Порядок стадий: analysis -> B(grounding) -> merge (полное согласие) ->
    verify(2 картинки). Тег ensemble в usage, дамп, pset EnsembleAgreement.
    Геометрия B подобрана под A ( порог согласия): дверь 84px -> масштаб
    0.025; контур 780x550 px -> 19.5м x этаж 2.75 (дельты 2.5%/8.3% < порогов);
    10 полос окон (2 ряда В ЭТАЖЕ x 5 этажей, шаг 50 > 0.6*80 допуска
    кластеров) x 4 столбца; нижняя дверь -> entrance."""
    R = _router()
    from PIL import Image
    img = Image.new("RGB", (800, 600), "white")
    calls = []

    def fake_vlm(system, prompt, image_url, model):
        calls.append({"system": system, "images": image_url, "model": model,
                      "stage": R._usage_stage[0]})
        if "facade grounding model" in system:
            boxes = [{"label": "building", "x1": 10, "y1": 40,
                      "x2": 790, "y2": 590},
                     {"label": "door", "x1": 370, "y1": 506,
                      "x2": 430, "y2": 590}]
            # rows = ceil(полос/этажей) = ceil(10/5) = 2 = A (live-хвост п.60)
            for cy in (96 + j * 50 for j in range(10)):
                for cx in (190, 370, 550, 730):  # 4 столбца (зазор 180)
                    boxes.append({"label": "window", "x1": cx - 30,
                                  "y1": cy - 40, "x2": cx + 30,
                                  "y2": cy + 40})
            return json.dumps({"boxes": boxes,
                               "meta": {"floors": 5, "roof": "flat"}},
                              ensure_ascii=False)
        if "QA verifier" in system:
            assert isinstance(image_url, list) and len(image_url) == 2, \
                "verify: [оригинал, оверлей] (з.5)"
            return '{"ok": true, "issues": []}'
        return _facade_json()

    R._call_vlm = fake_vlm
    R._vlm_list_cached = lambda: []  # каталог не запрашиваем: тесты без сети
    with _Env(THREED_ENSEMBLE="1", THREED_ENSEMBLE_MODEL="fake/qwen",
              THREED_VERIFY="1", THREED_VERIFY_ITERS="0",
              THREED_MODEL="fake/one"):
        res = R._generate_impl("facade", "t", img, TMP)
    stages = [c["stage"] for c in calls]
    assert stages[0] == "analysis" and "ensemble" in stages, stages
    assert calls[1]["model"] == "fake/qwen", "прогон B на ENSEMBLE-модели"
    dump = json.loads((TMP / "_threed_last.json").read_text(encoding="utf-8"))
    ens = dump["ensemble"]
    assert ens["mode"] == "grounding" and ens["agree_rate"] == 1.0, ens
    assert res["ensemble"]["agree_rate"] == 1.0
    # pset EnsembleAgreement в IFC победителя
    import ifcopenshell
    model = ifcopenshell.open(str(TMP / res["name"]))
    rels = [r for r in model.by_type("IfcRelDefinesByProperties")
            if r.RelatingPropertyDefinition.Name == "DevBIM"]
    props = {}
    for q in rels[0].RelatingPropertyDefinition.HasProperties:
        props[q.Name] = getattr(q.NominalValue, "wrappedValue", None)
    assert "EnsembleAgreement" in props and props["EnsembleAgreement"], props
    # usage: моки заменяют _call_vlm целиком -> usage пуст (учёт живых вызовов
    # в _record_usage); проверяем тег косвенно — stages выше уже содержит
    # "ensemble" в момент вызова B
    print("test_router_ensemble_happy_path OK")


def test_router_b_failure_falls_back():
    """Сбой прогона B (не JSON) — warning, генерация на A."""
    R = _router()
    from PIL import Image
    img = Image.new("RGB", (64, 64), "white")

    def fake_vlm(system, prompt, image_url, model):
        if "grounding" in system:
            return "I cannot answer in JSON, sorry"
        if "QA verifier" in system:
            return '{"ok": true, "issues": []}'
        return _facade_json()

    R._call_vlm = fake_vlm
    R._vlm_list_cached = lambda: []  # каталог не запрашиваем: тесты без сети
    with _Env(THREED_ENSEMBLE="1", THREED_ENSEMBLE_MODEL="fake/qwen",
              THREED_VERIFY="1", THREED_VERIFY_ITERS="0",
              THREED_MODEL="fake/one"):
        res = R._generate_impl("facade", "t", img, TMP)
    assert any("B" in w for w in res["warnings"]), res["warnings"]
    assert (res.get("ensemble") or {}).get("agree_rate") is None
    print("test_router_b_failure_falls_back OK")


def test_router_ensemble_disabled():
    """THREED_ENSEMBLE=0 — ровно один analysis-вызов, поведение до п.60."""
    R = _router()
    from PIL import Image
    img = Image.new("RGB", (64, 64), "white")
    seen = []

    def fake_vlm(system, prompt, image_url, model):
        seen.append(system[:20])
        if "QA verifier" in system:
            return '{"ok": true, "issues": []}'
        return _facade_json()

    R._call_vlm = fake_vlm
    R._vlm_list_cached = lambda: []  # каталог не запрашиваем: тесты без сети
    with _Env(THREED_ENSEMBLE="0", THREED_VERIFY="1",
              THREED_VERIFY_ITERS="0", THREED_MODEL="fake/one"):
        R._generate_impl("facade", "t", img, TMP)
    assert len(seen) == 2, seen  # analysis + verify, без B
    print("test_router_ensemble_disabled OK")


def test_router_budget_and_referee():
    """Бюджет THREED_MAX_CALLS_PER_ATTEMPT=3: analysis(1) + B(1) + реферти(1)
    исчерпали -> verify пропущен (ok=None), генерация жива. Рефери вызывается
    РОВНО один раз; мусорный ответ реферти -> вариант A + warning."""
    R = _router()
    from PIL import Image
    img = Image.new("RGB", (64, 64), "white")
    b_calls, r_calls = [], []

    def fake_vlm(system, prompt, image_url, model):
        if "facade grounding model" in system:
            b_calls.append(1)
            # B: этажей 2 против A=5 -> споры storeys/rows/cols/skip/width/
            # entrance (floor_height совпадёт 3.0)
            return json.dumps({"boxes": [
                {"label": "building", "x1": 0, "y1": 0, "x2": 60, "y2": 60},
                {"label": "window", "x1": 10, "y1": 10, "x2": 30, "y2": 30}],
                "meta": {"floors": 2}}, ensure_ascii=False)
        if "geometry referee" in system:
            r_calls.append(prompt)
            return "garbage not json"
        if "QA verifier" in system:
            return '{"ok": true, "issues": []}'
        return _facade_json()

    R._call_vlm = fake_vlm
    R._vlm_list_cached = lambda: []  # каталог не запрашиваем: тесты без сети
    with _Env(THREED_ENSEMBLE="1", THREED_ENSEMBLE_MODEL="fake/qwen",
              THREED_MAX_CALLS_PER_ATTEMPT="3", THREED_VERIFY="1",
              THREED_VERIFY_ITERS="0", THREED_MODEL="fake/one"):
        res = R._generate_impl("facade", "t", img, TMP)
    assert len(b_calls) == 1
    assert len(r_calls) == 1, "реферти <=1 вызова на попытку"
    v = res["verify"]["verdict"]
    assert v["ok"] is None, "verify за бюджетом -> ok=None (не крах)"
    assert res["ensemble"]["agree_rate"] < 1.0
    dump = json.loads((TMP / "_threed_last.json").read_text(encoding="utf-8"))
    assert dump["ensemble"]["disputed_fields"], dump["ensemble"]
    print("test_router_budget_and_referee OK")


if __name__ == "__main__":
    test_compare_full_agreement()
    test_compare_disputes()
    test_skip_dispute_two_cells()
    test_merge_average_and_referee()
    test_merge_flag_field_types()
    test_referee_prompt_shape()
    test_compare_plan()
    test_merge_plan_component()
    test_compare_interior()
    test_router_ensemble_happy_path()
    test_router_b_failure_falls_back()
    test_router_ensemble_disabled()
    test_router_budget_and_referee()
    print("ALL OK")
