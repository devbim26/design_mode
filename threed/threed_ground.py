# -*- coding: utf-8 -*-
"""Прогон B — grounding-извлечение (спека п.60, з.2): VLM отдаёт боксы в
ПИКСЕЛЯХ исходной картинки + минимальный текстовый блок; геометрию считает
код (конвертеры ниже по модулю). Модуль ЧИСТЫЙ: без invokeai.*, тянется
тестами из дерева (грабля п.45-3 не касается)."""

try:  # в venv threed_scenarios лежит рядом; в дереве — пакет threed
    from invokeai.app.api.routers import threed_scenarios
except ImportError:
    from threed import threed_scenarios

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
