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
