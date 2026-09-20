# -*- coding: utf-8 -*-
"""3D Design: самопроверка собранной модели (пилот по паттерну MCP4IFC
get_ifc_scene_overview — Show2Instruct/ifc-bonsai-mcp, MIT).

После сборки IFC формируется компактный обзор: (A) scene_overview — что
ЗАДУМАНО (из валидированной сцены, метры/счётчики) и (B) built_overview —
что РЕАЛЬНО лежит в IFC (подсчёт продуктов по ObjectType). Обзор + исходная
картинка уходят вторым запросом в VLM, ответ — строгий JSON-вердикт
{"ok": bool, "issues": [...]}. Верификация НИКОГДА не роняет генерацию:
любой сбой -> {"ok": None, "error": ...} (диагностика в _threed_last.json).
Выключатель — env THREED_VERIFY (0/false/no/off) в роутере.
"""
import json

try:  # задеплоено в venv
    from invokeai.app.api.routers import threed_scenarios
except ImportError:  # дерево проекта (тесты)
    from threed import threed_scenarios

MAX_ISSUES = 8
ISSUE_MAX_LEN = 160

SYSTEM_VERIFY = """You are a BIM QA verifier. An earlier pass analyzed the attached image
and a parametric 3D massing model (IFC) was built from that analysis. You are given
(A) the final sanitized scene specification and (B) the element counts actually
written into the IFC file. Compare BOTH with what is VISIBLE in the image.
Reply with STRICT JSON ONLY - no markdown fences, no comments, no extra keys:
{"ok": true | false, "issues": [<short concrete mismatch lines in English>]}

Verdict rules:
- ok=true when the model plausibly represents the image: storey count, window
  grid (rows x cols), roof shape, balconies, building/room/furniture counts,
  context amounts (trees/cars/people/furniture), general colors.
- ok=false ONLY for real mismatches a person would also call out: wrong storey
  count, missing or extra window columns/rows, wrong roof type (gable vs flat),
  missing balconies, a building/room/furniture category missing entirely.
- Tolerate (NOT issues): building depth guesses (not visible), simplified side
  windows, dimensions within ~20%, colors shifted by lighting, massing-level
  simplification without facade detail.
- issues: up to 8 short lines, each naming the mismatch with built vs image
  values, e.g. "storeys: built 5, image shows 4". Empty list when ok=true.
"""


def _r(value, nd=2):
    """float -> округление для компактности промпта; остальное as-is."""
    try:
        return round(float(value), nd)
    except (TypeError, ValueError):
        return value


def _facade_summary(b):
    """Общий хелпер фасад-части (facade/scene): окна/балконы/цвета компактно.
    v2-детали (dormers/chimneys/towers/entrance/custom_parts, windows.shape)
    — счётчиками: верификатор кросс-чекает их против built_overview."""
    win = b.get("windows") or {}
    return {
        "storeys": b.get("storeys"),
        "floor_height_m": _r(b.get("floor_height")),
        "width_m": _r(b.get("width_m")),
        "depth_m": _r(b.get("depth_m")),
        "roof": b.get("roof"),
        "roof_height_m": _r(b.get("roof_height")) if b.get("roof") in ("gable", "hip", "mansard") else None,
        "windows": {"rows": win.get("rows"), "cols": win.get("cols"),
                    "w_m": _r(win.get("w_m")), "h_m": _r(win.get("h_m")),
                    "shape": win.get("shape", "rect")},
        "balconies_count": len(b.get("balconies") or []),
        "dormers": len(b.get("dormers") or []),
        "chimneys": len(b.get("chimneys") or []),
        "towers": len(b.get("towers") or []),
        "entrance": bool(b.get("entrance")),
        "custom_parts": len(b.get("custom_parts") or []),
        "colors": b.get("colors") or {},
    }


def scene_overview(scenario, scene):
    """ВАЛИДИРОВАННАЯ сцена -> семантический обзор (без пикселей)."""
    scene = scene or {}
    if scenario == "facade":
        out = _facade_summary(scene)
        skip = (scene.get("windows") or {}).get("skip") or []
        out["windows"]["skipped_cells"] = sum(1 for row in skip for cell in row if cell)
        return out
    if scenario == "scene":
        people = (scene.get("context") or {}).get("people") or []
        kinds = {}
        for item in (scene.get("context") or {}).get("furniture") or []:
            ftype = item.get("type", "other")
            kinds[ftype] = kinds.get(ftype, 0) + 1
        return {
            "camera": {k: _r(v) for k, v in (scene.get("camera") or {}).items()},
            "buildings": [dict(_facade_summary(b),
                               main=bool(b.get("main")),
                               x_m=_r(b.get("x_m")), y_m=_r(b.get("y_m")))
                          for b in scene.get("buildings") or []],
            "context": {"trees": len((scene.get("context") or {}).get("trees") or []),
                        "cars": len((scene.get("context") or {}).get("cars") or []),
                        "people": len(people),
                        "people_elevated": sum(
                            1 for p in people if float(p.get("z_m") or 0.0) > 0.05),
                        "furniture": kinds},
        }
    if scenario == "interior":
        kinds = {}
        for item in scene.get("furniture") or []:
            kinds[item.get("type", "other")] = kinds.get(item.get("type", "other"), 0) + 1
        doors = sum(1 for op in scene.get("openings") or [] if op.get("kind") == "door")
        windows = sum(1 for op in scene.get("openings") or [] if op.get("kind") == "window")
        return {"wall_height_m": _r(scene.get("wall_height")),
                "walls": len(scene.get("walls") or []),
                "openings": {"doors": doors, "windows": windows},
                "rooms": len(scene.get("rooms") or []),
                "furniture": kinds}
    # plan (генплан)
    context = scene.get("context") or []
    context_counts = {kind: sum(1 for c in context if c.get("kind") == kind)
                      for kind in sorted({c.get("kind") for c in context})}
    return {"scale_m_per_px": _r(scene.get("metres_per_trace_pixel"), 3),
            "storey_heights_m": {"residential": _r(scene.get("residential_storey_height")),
                                 "public": _r(scene.get("public_storey_height"))},
            "sections": [{"id": s.get("id"), "use": s.get("use"), "floors": s.get("floors")}
                         for s in scene.get("sections") or []],
            "context_counts": context_counts}


# классы, чьи продукты считаем (порядок = читаемость дампа)
_BUILT_CLASSES = ("IfcBuildingElementProxy", "IfcGeographicElement",
                  "IfcWall", "IfcSlab", "IfcSpace", "IfcFurnishingElement")


def built_overview(ifc_path):
    """Готовый IFC-файл -> {ObjectType: count}. Честная проверка сборщика:
    считаем то, что реально записано, а не задумано сценой."""
    import ifcopenshell
    model = ifcopenshell.open(str(ifc_path))
    counts = {}
    for cls in _BUILT_CLASSES:
        for product in model.by_type(cls):
            key = (product.ObjectType or cls).strip() or cls
            counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def _normalize_verdict(data, raw):
    """Ответ VLM -> {"ok": bool, "issues": [str]} | {"ok": None, "error": ...}."""
    if not isinstance(data, dict) or "ok" not in data:
        return {"ok": None, "error": "verify: ответ не JSON/без ключа ok",
                "raw_head": (raw or "")[:200]}
    ok = data.get("ok")
    if isinstance(ok, str):
        ok = ok.strip().lower() in ("true", "yes", "1")
    if not isinstance(ok, bool):
        return {"ok": None, "error": f"verify: ok не bool ({ok!r})",
                "raw_head": (raw or "")[:200]}
    raw_issues = data.get("issues")
    issues = []
    if isinstance(raw_issues, list):
        issues = [str(i)[:ISSUE_MAX_LEN] for i in raw_issues
                  if i is not None and str(i).strip()][:MAX_ISSUES]
    if ok and issues:
        issues = []  # ok=true — замечания не показываем (правило промпта)
    return {"ok": ok, "issues": issues}


def verify(image_url, overview, call_vlm, model):
    """Второй VLM-запрос: картинка + обзор -> вердикт. Отказоустойчиво."""
    prompt = ("An earlier pass analyzed the attached image and built a parametric "
              "3D model. Verify it.\n\n(A) final scene specification:\n"
              + json.dumps(overview.get("scene"), ensure_ascii=False)
              + "\n\n(B) elements actually created in the IFC file:\n"
              + json.dumps(overview.get("built"), ensure_ascii=False)
              + "\n\nCompare (A) and (B) against the image. Reply with STRICT "
                "JSON ONLY: {\"ok\": true|false, \"issues\": [...]}")
    try:
        raw = call_vlm(SYSTEM_VERIFY, prompt, image_url, model)
    except Exception as e:  # сеть/ключ/таймаут — верификация не роняет генерацию
        return {"ok": None, "error": f"VLM verify error: {e}"}
    return _normalize_verdict(threed_scenarios.extract_json(raw), raw)
