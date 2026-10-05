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
import math

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
    if scenario == "interior3d":
        kinds = {}
        for item in scene.get("furniture") or []:
            ftype = item.get("type", "other")
            kinds[ftype] = kinds.get(ftype, 0) + 1
        ops = scene.get("openings") or []
        room = scene.get("room") or {}
        cam = scene.get("camera") or {}
        return {"room": {"width_m": _r(room.get("width_m")),
                         "depth_m": _r(room.get("depth_m")),
                         "height_m": _r(room.get("height_m")),
                         "ceiling": bool(room.get("ceiling"))},
                "openings": {"doors": sum(1 for o in ops if o.get("kind") == "door"),
                             "windows": sum(1 for o in ops
                                            if o.get("kind") == "window")},
                "furniture": kinds, "people": len(scene.get("people") or []),
                "camera": {k: _r(v) for k, v in cam.items()}}
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


# классы, чьи продукты считаем (порядок = читаемость дампа); IfcDoor/IfcWindow —
# заполнения настоящих проёмов интерьера (IfcOpeningElement не считаем: это
# дыра, а не продукт, дубль с заполнением)
_BUILT_CLASSES = ("IfcBuildingElementProxy", "IfcGeographicElement",
                  "IfcWall", "IfcSlab", "IfcSpace", "IfcFurnishingElement",
                  "IfcDoor", "IfcWindow")


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


# классы, чью пространственную привязку проверяем. IfcOpeningElement исключён:
# живёт в стене через IfcRelVoidsElement, а не в контейнере — так задумано
_STRUCT_CLASSES = ("IfcBuildingElementProxy", "IfcGeographicElement",
                   "IfcWall", "IfcSlab", "IfcSpace", "IfcFurnishingElement",
                   "IfcDoor", "IfcWindow")
_STRUCT_NAMES_MAX = 5


def structural_report(ifc_path):
    """Готовый IFC -> детерминированные структурные проверки (п.58; паттерны
    Daviidro/ifcopenshell-mcp validate_ifc_model, MIT, и smartaec/ifcMCP
    get_openings_on_wall, Apache-2.0 — подход, не код). Проёмы без стены-
    носителя/заполнения, двери-окна вне проёма, элементы без привязки,
    безымянные продукты. Мягкий режим: только факты в overview/дамп; вердикт
    не меняет, генерацию не роняет (сбой глушится вызывающим)."""
    import ifcopenshell
    model = ifcopenshell.open(str(ifc_path))

    hosted, filled, filling_ids = set(), set(), set()
    for rel in model.by_type("IfcRelVoidsElement"):
        hosted.add(rel.RelatedOpeningElement.id())
    for rel in model.by_type("IfcRelFillsElement"):
        filled.add(rel.RelatingOpeningElement.id())
        filling_ids.add(rel.RelatedBuildingElement.id())

    attached = set()
    for rel in model.by_type("IfcRelContainedInSpatialStructure"):
        attached.update(e.id() for e in rel.RelatedElements)
    for rel in model.by_type("IfcRelAggregates"):
        attached.update(e.id() for e in rel.RelatedObjects)

    products = [p for cls in _STRUCT_CLASSES for p in model.by_type(cls)]
    openings_unhosted = [o for o in model.by_type("IfcOpeningElement")
                         if o.id() not in hosted]
    openings_unfilled = [o for o in model.by_type("IfcOpeningElement")
                         if o.id() not in filled]
    fillings_homeless = [e for e in model.by_type("IfcDoor")
                         + model.by_type("IfcWindow")
                         if e.id() not in filling_ids]
    uncontained = [e for e in products if e.id() not in attached]
    unnamed = [e for e in products if not (e.Name or "").strip()]

    report = {"openings_unhosted": len(openings_unhosted),
              "openings_unfilled": len(openings_unfilled),
              "fillings_homeless": len(fillings_homeless),
              "elements_uncontained": len(uncontained),
              "unnamed_products": len(unnamed),
              "examples": [e.Name for e in
                           (openings_unhosted + fillings_homeless
                            + uncontained)[:_STRUCT_NAMES_MAX]
                           if e.Name][:_STRUCT_NAMES_MAX]}
    issues = []
    if openings_unhosted:
        issues.append(f"проёмы без стены-носителя: {len(openings_unhosted)}")
    if openings_unfilled:
        issues.append(f"проёмы без заполнения: {len(openings_unfilled)}")
    if fillings_homeless:
        issues.append(f"двери/окна вне проёма: {len(fillings_homeless)}")
    if uncontained:
        issues.append(f"элементы без пространственной привязки: "
                      f"{len(uncontained)}")
    if unnamed:
        issues.append(f"продукты без имени: {len(unnamed)}")
    report["issues"] = issues[:MAX_ISSUES]
    report["ok"] = not issues
    return report


# ===================== оверлей извлечённой геометрии (п.60, з.5) =====================

OVERLAY_COLOR = (255, 59, 48)   # красный DevBIM-оверлей
OVERLAY_DOOR_COLOR = (0, 122, 255)


def facade_grid_boxes(scene, pixel_hint, img_w, img_h):
    """Пиксельные боксы окон сетки фасада (метрика «IoU оверлея по GT» з.7
    и геометрия оверлея — один источник). pixel_hint=None -> фитовое
    размещение (80% ширины, по центру), как в render_overlay."""
    st = max(1, int(scene.get("storeys") or 1))
    w_m = max(0.1, float(scene.get("width_m") or 10))
    fh = float(scene.get("floor_height") or 3)
    if pixel_hint:
        x1, y1, x2, y2 = pixel_hint
    else:
        bw = int(img_w * 0.8)
        bh = int(min(img_h * 0.9, bw * (st * fh) / w_m))
        x1, y1 = (img_w - bw) // 2, (img_h - bh) // 2
        x2, y2 = x1 + bw, y1 + bh
    win = scene.get("windows") or {}
    rows = max(1, int(win.get("rows") or 1))
    cols = max(1, int(win.get("cols") or 1))
    sx = (x2 - x1) / w_m  # px на метр по фасаду
    mx = float(win.get("margin_x_m") or 0) * sx
    ww = min(float(win.get("w_m") or 1.5) * sx, (x2 - x1) / cols)
    wh = min(float(win.get("h_m") or 1.5) * sx, (y2 - y1) / st)
    span = (x2 - x1) - 2 * mx - ww
    step = span / max(cols - 1, 1) if cols > 1 else 0
    skip = win.get("skip") or []
    storey_h = (y2 - y1) / st
    boxes = []
    for j in range(rows):
        cy = y1 + j * storey_h + (storey_h - wh) / 2
        for i in range(cols):
            if j < len(skip) and i < len(skip[j]) and skip[j][i]:
                continue
            cx = x1 + mx + i * step
            boxes.append([cx, cy, cx + ww, cy + wh])
    return boxes


def render_overlay(scenario, scene, image, pixel_hint=None):
    """Сцена-победитель ДО сборки поверх исходной картинки (PIL, паттерн
    draw_overlay скилла tools/image-to-ifc). Ловит ошибки АНАЛИЗА (сборку
    проверяет structural_report п.58). facade: сцена метрическая — пиксельный
    якорь = бокс building прогона B (pixel_hint), без него пропорциональный
    фит. Возвращает НОВУЮ картинку (копию)."""
    from PIL import ImageDraw
    im = image.convert("RGB").copy()
    d = ImageDraw.Draw(im)
    if scenario == "facade":
        st = max(1, int(scene.get("storeys") or 1))
        w_m = max(0.1, float(scene.get("width_m") or 10))
        fh = float(scene.get("floor_height") or 3)
        if pixel_hint:
            x1, y1, x2, y2 = pixel_hint
        else:
            bw = int(im.width * 0.8)
            bh = int(min(im.height * 0.9, bw * (st * fh) / w_m))
            x1, y1 = (im.width - bw) // 2, (im.height - bh) // 2
            x2, y2 = x1 + bw, y1 + bh
        d.rectangle([x1, y1, x2, y2], outline=OVERLAY_COLOR, width=3)
        for b in facade_grid_boxes(scene, pixel_hint, im.width, im.height):
            d.rectangle(b, outline=OVERLAY_COLOR, width=2)
    elif scenario == "plan":
        for sec in scene.get("sections") or []:
            pts = [tuple(p) for p in sec.get("points_px") or []]
            if len(pts) >= 3:
                d.line(pts + [pts[0]], fill=OVERLAY_COLOR, width=3)
    elif scenario == "interior":
        walls = scene.get("walls") or []
        for wall in walls:
            (ax, ay), (bx, by) = wall["points_px"]
            d.line([(ax, ay), (bx, by)], fill=OVERLAY_COLOR, width=3)
        for op in scene.get("openings") or []:
            widx = op.get("wall_idx")
            if not isinstance(widx, int) or not (0 <= widx < len(walls)):
                continue
            (ax, ay), (bx, by) = walls[widx]["points_px"]
            L = math.hypot(bx - ax, by - ay)
            t = min(max(float(op.get("x_px") or 0) / max(L, 1.0), 0.0), 1.0)
            cx, cy = ax + (bx - ax) * t, ay + (by - ay) * t
            r = 6
            d.ellipse([cx - r, cy - r, cx + r, cy + r],
                      outline=OVERLAY_DOOR_COLOR, width=2)
    return im


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


def verify(image_url, overview, call_vlm, model, overlay_url=None):
    """Второй VLM-запрос: картинка (+опционально оверлей з.5) + обзор ->
    вердикт. Отказоустойчиво."""
    prompt = ("An earlier pass analyzed the attached image and built a parametric "
              "3D model. Verify it.\n\n(A) final scene specification:\n"
              + json.dumps(overview.get("scene"), ensure_ascii=False)
              + "\n\n(B) elements actually created in the IFC file:\n"
              + json.dumps(overview.get("built"), ensure_ascii=False)
              + "\n\nCompare (A) and (B) against the image. Reply with STRICT "
                "JSON ONLY: {\"ok\": true|false, \"issues\": [...]}")
    structural = [str(s) for s in (overview.get("structural") or [])
                  if str(s).strip()][:MAX_ISSUES]
    if structural:  # п.58: машинные дефекты сборки — факт, а не догадка VLM
        prompt += ("\n\n(C) machine-detected IFC build defects (deterministic "
                   "ground truth, not guesses — report them as issues):\n- "
                   + "\n- ".join(structural))
    if overlay_url:
        prompt += ("\n\nImage 1 = the source. Image 2 = the SAME source with the "
                   "extracted geometry overlaid in red (contours, window grid, "
                   "walls; blue dots = openings). Check ALIGNMENT of the red "
                   "overlay with the source: shifted grids, wrong counts, "
                   "misplaced contours are issues.")
    images = [image_url, overlay_url] if overlay_url else image_url
    try:
        raw = call_vlm(SYSTEM_VERIFY, prompt, images, model)
    except Exception as e:  # сеть/ключ/таймаут — верификация не роняет генерацию
        return {"ok": None, "error": f"VLM verify error: {e}"}
    return _normalize_verdict(threed_scenarios.extract_json(raw), raw)
