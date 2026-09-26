# -*- coding: utf-8 -*-
"""Прогон B — grounding-извлечение (спека п.60, з.2): VLM отдаёт боксы в
ПИКСЕЛЯХ исходной картинки + минимальный текстовый блок; геометрию считает
код (конвертеры ниже по модулю). Модуль ЧИСТЫЙ: без invokeai.*, тянется
тестами из дерева (грабля п.45-3 не касается)."""

try:  # в venv threed_scenarios лежит рядом; в дереве — пакет threed
    from invokeai.app.api.routers import threed_scenarios
except ImportError:
    from threed import threed_scenarios

try:  # ортогонализация рёбер — общий хелпер regular (venv | дерево)
    from invokeai.app.api.routers import threed_regular
except ImportError:
    from threed import threed_regular

# какие метки принимает каждая тема (чужие — мусор, дроп с warning)
GROUND_LABELS = {
    "facade": {"window", "door", "building"},
    "plan": {"building", "parking", "sport"},
    "interior": {"room", "door", "window"},
}

# якоря метрических размеров (скилл tools/image-to-ifc): м
ANCHOR_PARKING = (2.5, 5.0)    # стойло: короткая/длинная сторона
ANCHOR_SPORT = (17.0, 34.0)    # спортплощадка 16-18 x 32-36 -> медианы
ANCHOR_DOOR_H = 2.1            # высота входной двери, м
ANCHOR_DOOR_W = 0.9            # ширина двери интерьера, м
ANCHOR_WINDOW_H = 1.5          # высота окна фасада, м
ANCHOR_STOREY = 3.0            # этаж, м


def _box_xyxy(b):
    """GT/pred бокс (dict x1..y2 | dict box[4] | list[4]) -> (x1,y1,x2,y2)|None."""
    if isinstance(b, dict):
        raw = b.get("box")
        if isinstance(raw, (list, tuple)) and len(raw) == 4:
            vals = raw
        else:
            vals = (b.get("x1"), b.get("y1"), b.get("x2"), b.get("y2"))
    elif isinstance(b, (list, tuple)) and len(b) == 4:
        vals = b
    else:
        return None
    try:
        x1, y1, x2, y2 = (float(v) for v in vals)
    except (TypeError, ValueError):
        return None
    if x1 == x2 or y1 == y2:  # вырожденный
        return None
    return x1, y1, max(x1, x2), max(y1, y2)


def _compute_iou(pred, gt) -> float:
    """IoU двух боксов (строки спеки з.1a: sanity разметки; з.1b: метрика
    зонда). Формы: dict/list, координаты любые — сам нормализует."""
    a, b = _box_xyxy(pred), _box_xyxy(gt)
    if not a or not b:
        return 0.0
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    union = ((a[2] - a[0]) * (a[3] - a[1])
             + (b[2] - b[0]) * (b[3] - b[1]) - inter)
    return inter / union if union > 0 else 0.0


def normalize_boxes(payload, img_w, img_h, scenario="facade"):
    """Сырой payload B (или GT-запись) -> (boxes, meta, warnings): плоские
    ключи, кламп к границе, дроп чужих label/вырожденных. Валидные GT-записи
    проходят без единого warning."""
    warnings = []
    if not isinstance(payload, dict):
        return [], {}, ["grounding: ответ не объект"]
    raw = payload.get("boxes")
    if not isinstance(raw, list):
        return [], {}, ["grounding: нет массива boxes"]
    allowed = GROUND_LABELS[scenario]
    boxes = []
    for i, b in enumerate(raw, start=1):
        label = b.get("label") if isinstance(b, dict) else None
        if label not in allowed:
            warnings.append(f"бокс {i}: label {label!r} не в {sorted(allowed)} — дроп")
            continue
        xy = _box_xyxy(b)
        if xy is None:
            warnings.append(f"бокс {i} ({label}): битые координаты — дроп")
            continue
        x1, y1, x2, y2 = xy
        cx2, cy2 = min(x2, float(img_w)), min(y2, float(img_h))
        if (x1, y1, x2, y2) != (max(0.0, x1), max(0.0, y1), cx2, cy2):
            warnings.append(f"бокс {i} ({label}): кламп к границе картинки")
        x1, y1, x2, y2 = max(0.0, x1), max(0.0, y1), cx2, cy2
        if x2 - x1 < 1.0 or y2 - y1 < 1.0:
            warnings.append(f"бокс {i} ({label}): меньше 1 px после клампа — дроп")
            continue
        boxes.append({"label": label, "x1": x1, "y1": y1, "x2": x2, "y2": y2})
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    return boxes, dict(meta), warnings


def validate_gt(entries):
    """GT-файл -> (ok, errors). Минимумы спеки з.1a: фасад >=8 окон +
    дверь + контур; план >=3 корпуса; интерьер >=3 комнаты + 2 двери."""
    errors = []
    seen = {"facade": [], "plan": [], "interior": []}
    for e in entries if isinstance(entries, list) else []:
        sc = e.get("scenario")
        if sc not in seen:
            errors.append(f"запись {e.get('image')}: сценарий {sc!r} не в темах")
            continue
        boxes, _, wns = normalize_boxes(e, 10 ** 6, 10 ** 6, scenario=sc)
        if wns:
            errors.append(f"{e.get('image')}: битые GT-боксы ({wns[:2]})")
        seen[sc].append((e.get("image"), [b["label"] for b in boxes]))
    for img, labels in seen["facade"]:
        if labels.count("window") < 8:
            errors.append(f"{img}: facade окон {labels.count('window')} < 8")
        if "door" not in labels or "building" not in labels:
            errors.append(f"{img}: facade нужны door и building")
    for img, labels in seen["plan"]:
        if labels.count("building") < 3:
            errors.append(f"{img}: plan корпусов {labels.count('building')} < 3")
    for img, labels in seen["interior"]:
        if labels.count("room") < 3 or labels.count("door") < 2:
            errors.append(f"{img}: interior нужно >=3 room и >=2 door")
    if not any(seen["facade"]) or not any(seen["plan"]) or not any(seen["interior"]):
        errors.append("нужна хотя бы одна запись каждой темы (facade/plan/interior)")
    return not errors, errors


# ===================== зонд (з.1b): метрики и выбор модели =====================

def probe_metrics(pred_boxes, gt_boxes, iou_thresh=0.5):
    """pred/gt списки боксов -> {iou_mean, iou_median, recall, precision}.
    Сопоставление жадное по лучшему IoU (один pred закрывает один gt)."""
    pairs = []
    for g in gt_boxes:
        best_iou, best_j = 0.0, -1
        for j, p in enumerate(pred_boxes):
            iou = _compute_iou(p, g)
            if iou > best_iou:
                best_iou, best_j = iou, j
        pairs.append((best_iou, best_j))
    ious = [iou for iou, _ in pairs]
    matched = [j for iou, j in pairs if iou >= iou_thresh and j >= 0]
    used, hits = set(), 0
    for j in matched:  # один pred не закрывает два gt
        if j not in used:
            used.add(j)
            hits += 1
    return {"iou_mean": round(sum(ious) / len(ious), 4) if ious else 0.0,
            "iou_median": round(sorted(ious)[len(ious) // 2], 4) if ious else 0.0,
            "recall": round(hits / len(gt_boxes), 4) if gt_boxes else 0.0,
            "precision": round(hits / len(pred_boxes), 4) if pred_boxes else 0.0}


def probe_candidates(vlm_ids):
    """Каталог id -> кандидаты зонда: qwen-vl семейство + sol; контроль —
    astra (модель анализа A). Порядок стабилен."""
    ids = list(vlm_ids)
    qwen = sorted(i for i in ids if "qwen" in i.lower() and "vl" in i.lower())
    out = []
    if qwen:
        out.append(qwen[0])  # первый qwen-vl каталога (обычно базовый)
    for m in ("openai/gpt-6-sol", "openai/gpt-6-astra"):
        if m in ids:
            out.append(m)
    return out


def pick_model(results):
    """Таблица зонда -> (model, mode). Гейт спеки з.1b: best mean IoU >= 0.5
    И json_valid >= 0.5, иначе text-fallback ("" — модель выберет роутер)."""
    ok = [r for r in results
          if r.get("iou_mean", 0) >= 0.5 and r.get("json_valid", 0) >= 0.5]
    if not ok:
        return "", "text"
    best = max(ok, key=lambda r: r["iou_mean"])
    return best["model"], "grounding"


# ===================== промпты прогона B (з.2) =====================

SYSTEM_GROUND_FACADE = """You are a facade grounding model. Look at the attached
image of a building facade (photo/render/elevation). Detect objects and output
their boxes in ABSOLUTE IMAGE PIXELS. Reply with STRICT JSON ONLY - no markdown
fences, no comments, no extra keys:
{"boxes": [{"label": "window" | "door" | "building",
            "x1": <int>, "y1": <int>, "x2": <int>, "y2": <int>}, ...],
 "meta": {"floors": <int storeys>, "roof": "flat"|"gable"|"hip"|"mansard"}}

Rules:
- "building" = exactly ONE box tightly around the whole main facade volume.
- One box per visible window (a pane group counts as one window); include
  dormer windows in the roof.
- One box per ground-floor entrance door.
- x1 < x2, y1 < y2; coordinates of the ATTACHED image, y axis down.
- Count storeys carefully; meta carries no descriptions.
"""

SYSTEM_GROUND_PLAN = """You are a site-plan grounding model. Look at the attached
top-down master plan / aerial scheme. Detect objects and output their boxes in
ABSOLUTE IMAGE PIXELS. Reply with STRICT JSON ONLY:
{"boxes": [{"label": "building" | "parking" | "sport",
            "x1": <int>, "y1": <int>, "x2": <int>, "y2": <int>}, ...],
 "meta": {"sections": [{"use": "Residential"|"School"|"Kindergarten",
                        "floors": <int>}, ...], "scale_hint": <float m/px>}}

Rules:
- One "building" box per building volume (same order as meta.sections).
- "parking" = ONE single parking stall box; "sport" = one sport ground box
  (they anchor the metric scale).
- x1 < x2, y1 < y2; coordinates of the ATTACHED image, y axis down.
"""

SYSTEM_GROUND_INTERIOR = """You are a floor-plan grounding model. Look at the
attached 2D floor plan drawing. Detect objects and output their boxes in
ABSOLUTE IMAGE PIXELS. Reply with STRICT JSON ONLY:
{"boxes": [{"label": "room" | "door" | "window",
            "x1": <int>, "y1": <int>, "x2": <int>, "y2": <int>}, ...],
 "meta": {"scale_hint": <float m/px>, "wall_height": 2.7}}

Rules:
- One "room" box per enclosed room (inner surface of its walls).
- "door"/"window" = the opening gap on a wall (small elongated box).
- x1 < x2, y1 < y2; coordinates of the ATTACHED image, y axis down.
"""


# ===================== конвертеры боксы -> сцена (з.2) =====================

def _clusters(values, gap):
    """Значения -> список групп индексов: соседние ближе gap в одну группу
    (кластеризация строк/столбцов окон по центрам)."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    groups, last = [], None
    for i in order:
        if last is None or values[i] - values[last] > gap:
            groups.append([i])
        else:
            groups[-1].append(i)
        last = i
    return groups


def _med(vals):
    import statistics
    return statistics.median(vals) if vals else 0.0


def facade_boxes_to_scene(payload, img_w, img_h):
    """Боксы фасада -> raw-сцена validate_facade (только голосующие поля).
    Геометрию считает код: сетка = кластеры центров окон, масштаб = якорь
    двери (2.1 м) -> этажа (3.0 м) -> окна (1.5 м)."""
    boxes, meta, warnings = normalize_boxes(payload, img_w, img_h, "facade")
    wins = [b for b in boxes if b["label"] == "window"]
    doors = [b for b in boxes if b["label"] == "door"]
    bld = next((b for b in boxes if b["label"] == "building"), None)
    if not wins or bld is None:
        return {}, ["facade B: нет боксов окон/контура — сцена B пустая"]
    med_w = _med([b["x2"] - b["x1"] for b in wins])
    med_h = _med([b["y2"] - b["y1"] for b in wins])
    rows_g = _clusters([(b["y1"] + b["y2"]) / 2 for b in wins], 0.6 * med_h)
    cols_g = _clusters([(b["x1"] + b["x2"]) / 2 for b in wins], 0.6 * med_w)
    rows, cols = len(rows_g), len(cols_g)
    row_of, col_of = {}, {}
    for gi, grp in enumerate(rows_g):
        for i in grp:
            row_of[i] = gi
    for gi, grp in enumerate(cols_g):
        for i in grp:
            col_of[i] = gi
    skip = [[True] * cols for _ in range(rows)]
    for i in range(len(wins)):
        skip[row_of[i]][col_of[i]] = False
    try:
        floors = int(meta.get("floors") or 0)
    except (TypeError, ValueError):
        floors = 0
    floors = max(1, min(30, floors or max(rows, 1)))
    b_w, b_h = bld["x2"] - bld["x1"], bld["y2"] - bld["y1"]
    scale = None
    if doors:
        dh = _med([b["y2"] - b["y1"] for b in doors])
        if dh > 2:
            scale = ANCHOR_DOOR_H / dh
    if not scale and b_h > 2:
        scale = (floors * ANCHOR_STOREY) / b_h
    if not scale and med_h > 2:
        scale = ANCHOR_WINDOW_H / med_h
    leftmost = min(b["x1"] for b in wins)
    topmost = min(b["y1"] for b in wins)
    entrance = None
    if doors:
        d0 = min(doors, key=lambda b: b["y2"])  # самая нижняя дверь
        entrance = {"x_m": round(((d0["x1"] + d0["x2"]) / 2 - bld["x1"]) * scale, 2),
                    "w_m": round((d0["x2"] - d0["x1"]) * scale, 2),
                    "style": "porch"}
    roof = meta.get("roof")
    scene = {"storeys": floors,
             "floor_height": round(b_h * scale / floors, 2),
             "width_m": round(b_w * scale, 2), "depth_m": 12.0,
             "roof": roof if roof in ("flat", "gable", "hip", "mansard") else "flat",
             "roof_height": 2.5,
             "windows": {"rows": rows, "cols": cols,
                         "w_m": round(med_w * scale, 2),
                         "h_m": round(med_h * scale, 2),
                         "margin_x_m": round(max((leftmost - bld["x1"]) * scale, 0.05), 2),
                         "margin_y_m": round(max((topmost - bld["y1"]) * scale, 0.05), 2),
                         "skip": skip, "shape": "rect"},
             "entrance": entrance}
    return scene, warnings


def facade_pixel_hint(payload, img_w, img_h):
    """Бокс building -> (x1, y1, x2, y2) пикселей (якорь оверлея фасада)."""
    boxes, _, _ = normalize_boxes(payload, img_w, img_h, "facade")
    b = next((x for x in boxes if x["label"] == "building"), None)
    return (b["x1"], b["y1"], b["x2"], b["y2"]) if b else None


def lsq_scale(pairs):
    """МНК-масштаб по якорям (px, м): scale = sum(px*m)/sum(px*px).
    0.0 = якорей нет (вызывающий берёт scale_hint/дефолт)."""
    if not pairs:
        return 0.0
    sx = sum(px * m for px, m in pairs)
    sxx = sum(px * px for px, m in pairs)
    return sx / sxx if sxx > 0 else 0.0


def _scale_from_anchors(boxes, hint, lo=0.05, hi=10.0):
    """Масштаб плана: parking (2.5x5) + sport (17x34) якоря -> МНК; иначе
    hint; иначе дефолт генплана."""
    anchors = []
    for b in boxes:
        w, h = b["x2"] - b["x1"], b["y2"] - b["y1"]
        if b["label"] == "parking":
            anchors += [(min(w, h), ANCHOR_PARKING[0]), (max(w, h), ANCHOR_PARKING[1])]
        elif b["label"] == "sport":
            anchors += [(min(w, h), ANCHOR_SPORT[0]), (max(w, h), ANCHOR_SPORT[1])]
    scale = lsq_scale(anchors)
    if not (lo <= scale <= hi):
        try:
            scale = float(hint or 0) or threed_scenarios.DEFAULT_SCALE
        except (TypeError, ValueError):
            scale = threed_scenarios.DEFAULT_SCALE
    return scale


def plan_boxes_to_scene(payload, img_w, img_h):
    """Боксы генплана -> raw-сцена validate_genplan. Ортогонализация контуров
    — в regularize_plan (з.4); тут прямоугольники боксов как есть.
    threed_regular импортирован в шапке модуля (try/except venv|дерево)."""
    boxes, meta, warnings = normalize_boxes(payload, img_w, img_h, "plan")
    blds = [b for b in boxes if b["label"] == "building"]
    if not blds:
        return {}, ["plan B: нет боксов зданий — сцена B пустая"]
    scale = _scale_from_anchors(boxes, meta.get("scale_hint"))
    sections_meta = meta.get("sections") if isinstance(
        meta.get("sections"), list) else []
    sections = []
    for i, b in enumerate(blds):
        m = sections_meta[i] if i < len(sections_meta) and isinstance(
            sections_meta[i], dict) else {}
        use = m.get("use")
        if use not in ("Residential", "School", "Kindergarten"):
            use = "Residential"
        try:
            floors = int(m.get("floors") or 5)
        except (TypeError, ValueError):
            floors = 5
        pts = threed_regular.orthogonalize(
            [[b["x1"], b["y1"]], [b["x2"], b["y1"]],
             [b["x2"], b["y2"]], [b["x1"], b["y2"]]])
        sections.append({"id": f"B{i + 1}", "building": f"B{i + 1}",
                         "use": use, "floors": max(1, min(30, floors)),
                         "points_px": pts, "partial": False})
    scene = {"trace_width": int(img_w), "trace_height": int(img_h),
             "metres_per_trace_pixel": round(scale, 4),
             "residential_storey_height": 3.1, "public_storey_height": 3.3,
             "sections": sections,
             "context": [{"kind": "Ground", "z": -0.45, "depth": 0.35,
                          "points_px": [[0, 0], [img_w, 0],
                                        [img_w, img_h], [0, img_h]]}]}
    return scene, warnings


def _collinear_contained(a, b):
    """Отрезок a содержится в коллинеарном b (допуск 1 px)."""
    (ax1, ay1), (ax2, ay2) = a
    (bx1, by1), (bx2, by2) = b
    cross = (ax2 - ax1) * (by2 - by1) - (ay2 - ay1) * (bx2 - bx1)
    if abs(cross) > 1e-6 * (1 + abs(bx2 - bx1) + abs(by2 - by1)):
        return False

    def within(px, py):
        return (min(bx1, bx2) - 1 <= px <= max(bx1, bx2) + 1
                and min(by1, by2) - 1 <= py <= max(by1, by2) + 1)

    return within(ax1, ay1) and within(ax2, ay2)


def interior_boxes_to_scene(payload, img_w, img_h):
    """Боксы плана этажа -> raw-сцена validate_interior: outline = union
    комнат, стены = рёбра комнат (общие/поглощённые рёбра схлопываются,
    выжившее ребро между комнатами = внутренняя стена), проёмы к ближайшей
    стене. Толщины: все 0.35 (наружная), общие рёбра помечаются interior;
    нормализация толщин — regularize_interior (з.4)."""
    import math as _math
    from shapely.geometry import Polygon
    boxes, meta, warnings = normalize_boxes(payload, img_w, img_h, "interior")
    rooms = [b for b in boxes if b["label"] == "room"]
    ops = [b for b in boxes if b["label"] in ("door", "window")]
    if not rooms:
        return {}, ["interior B: нет боксов комнат — сцена B пустая"]
    # якорь двери: ДЛИННАЯ сторона бокса = ширина проёма 0.9 м (короткая —
    # толщина стены, не масштаб)
    door_ws = [max(b["x2"] - b["x1"], b["y2"] - b["y1"]) for b in ops
               if b["label"] == "door"]
    scale = ANCHOR_DOOR_W / _med(door_ws) if door_ws else 0.0
    try:
        hint = float(meta.get("scale_hint") or 0)
    except (TypeError, ValueError):
        hint = 0.0
    if not (0.001 <= scale <= 0.5):
        scale = hint or 0.01
    # outline: union прямоугольников комнат
    uni = None
    for r in rooms:
        p = Polygon([(r["x1"], r["y1"]), (r["x2"], r["y1"]),
                     (r["x2"], r["y2"]), (r["x1"], r["y2"])])
        uni = p if uni is None else uni.union(p)
    outline = [[round(x), round(y)] for x, y in
               list(uni.exterior.coords)[:-1]] if uni and uni.is_valid else []

    def edges(r):
        x1, y1, x2, y2 = r["x1"], r["y1"], r["x2"], r["y2"]
        return [[(x1, y1), (x2, y1)], [(x2, y1), (x2, y2)],
                [(x2, y2), (x1, y2)], [(x1, y2), (x1, y1)]]

    # стены: рёбра по убыванию длины; ребро, содержащееся в уже принятом
    # коллинеарном, НЕ добавляется, а помечает то внутренним (граница комнат)
    edges_all = [e for r in rooms for e in edges(r)]
    edges_all.sort(key=lambda e: -_math.hypot(e[1][0] - e[0][0],
                                              e[1][1] - e[0][1]))
    walls = []
    for e in edges_all:
        hit = False
        for w in walls:
            if _collinear_contained(e, w["points_px"]):
                w["exterior"] = False
                hit = True
        if not hit:
            walls.append({"points_px": [list(e[0]), list(e[1])],
                          "thickness_m": 0.35, "exterior": True})

    openings = []
    for b in ops:
        cx, cy = (b["x1"] + b["x2"]) / 2, (b["y1"] + b["y2"]) / 2
        best, best_d = None, 1e18
        for wi, wl in enumerate(walls):
            (ax, ay), (bx2, by2) = wl["points_px"]
            dx, dy = bx2 - ax, by2 - ay
            L2 = dx * dx + dy * dy or 1.0
            t = max(0.0, min(1.0, ((cx - ax) * dx + (cy - ay) * dy) / L2))
            px, py = ax + t * dx, ay + t * dy
            d = (cx - px) ** 2 + (cy - py) ** 2
            if d < best_d:
                best, best_d = (wi, t), d
        if best is None:
            continue
        wi, t = best
        (ax, ay), (bx2, by2) = walls[wi]["points_px"]
        L = _math.hypot(bx2 - ax, by2 - ay)
        openings.append({
            "wall_idx": wi,
            "x_px": round(t * L, 1),
            "width_m": round(max(b["x2"] - b["x1"], b["y2"] - b["y1"]) * scale, 2),
            "height_m": 2.1 if b["label"] == "door" else 1.5,
            "sill_m": 0.0 if b["label"] == "door" else 0.9,
            "kind": b["label"]})
    scene = {"trace_width": int(img_w), "trace_height": int(img_h),
             "metres_per_trace_pixel": round(scale, 4), "wall_height": 2.7,
             "outline": outline, "walls": walls, "openings": openings,
             "rooms": [{"name": f"Room {i + 1}", "type": "other",
                        "points_px": [[r["x1"], r["y1"]], [r["x2"], r["y1"]],
                                      [r["x2"], r["y2"]], [r["x1"], r["y2"]]]}
                       for i, r in enumerate(rooms)],
             "furniture": []}
    return scene, warnings


# конвертеры по темам (роутер зовёт через словарь)
CONVERTERS = {"facade": facade_boxes_to_scene,
              "plan": plan_boxes_to_scene,
              "interior": interior_boxes_to_scene}


# ===================== рантайм прогона B (вызов VLM) =====================

def run_ground_pass(scenario, image_url, model, call_vlm):
    """Grounding-вызов: SYSTEM_GROUND_* -> strict JSON боксов. (payload |
    None, warnings); None = невалидный ответ (вызывающий работает с A).
    call_vlm передаётся роутером (модуль чистый, invokeai.* не трогает)."""
    system = {"facade": SYSTEM_GROUND_FACADE, "plan": SYSTEM_GROUND_PLAN,
              "interior": SYSTEM_GROUND_INTERIOR}[scenario]
    raw = call_vlm(system, "Detect all objects. STRICT JSON only.",
                   image_url, model)
    payload = threed_scenarios.extract_json(raw)
    if payload is None:
        return None, [f"grounding B: ответ не JSON ({raw[:80]!r})"]
    return payload, []


def run_text_pass(scenario, user_prompt, image_url, model, call_vlm):
    """Text-fallback B (зонд провалился): тот же параметрический промпт, что
    у A, но ДРУГАЯ модель — двухканальность ловит галлюцинации и без
    grounding. Возвращает (raw_scene | None, warnings)."""
    system = {"facade": threed_scenarios.SYSTEM_FACADE,
              "plan": threed_scenarios.SYSTEM_GENPLAN,
              "interior": threed_scenarios.SYSTEM_INTERIOR}[scenario]
    raw = call_vlm(system, user_prompt, image_url, model)
    scene = threed_scenarios.extract_json(raw)
    if scene is None:
        return None, [f"text B: ответ не JSON ({raw[:80]!r})"]
    return scene, []
