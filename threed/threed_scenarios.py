# -*- coding: utf-8 -*-
"""Сценарии 3D Design: системные промпты, разбор JSON, валидация сцен.

Фаза 1 — «Генплан» (plan). Координаты позиций — ПИКСЕЛИ картинки,
размеры/высоты — метры (единое правило спеки).
"""

SYSTEM_GENPLAN = """You are a BIM site analyst. Look at the attached image (top-down
master plan / aerial / hand scheme). Trace building footprints and site context.
Reply with STRICT JSON ONLY - no markdown fences, no comments, no extra keys.

Schema:
{
 "metres_per_trace_pixel": <float: meters per image pixel. Estimate from anchors:
   sports ground 16-18 x 32-36 m, parking space 2.5 x 5 m, road width 6-10 m,
   or printed dimension labels. Typical scheme ~0.3-0.7.>,
 "residential_storey_height": 3.1,
 "public_storey_height": 3.3,
 "sections": [
   {"id": "<short unique id>", "building": "<group id; sections of one complex share it>",
    "use": "Residential|School|Kindergarten", "floors": <int 1-30>,
    "points_px": [[x, y], ...4-18 points, CLOCKWISE, image pixel coordinates,
      y=0 at the TOP of the image, buildings traced by ROOFS>,
    "partial": <true only if cut by the image edge>}
 ],
 "context": [
   {"kind": "Ground|Road|Parking|Sport|Court|Play", "z": <elevation, Ground=-0.45>,
    "depth": <thickness, Ground=0.35>, "points_px": [[x, y], ...]}
 ]
}

Rules:
- One section per building volume; split multi-part complexes into sections with the
  same "building".
- ALWAYS add one Ground context covering the whole image.
- The USER PROMPT overrides your guesses (floors, use, scale) wherever it states them.
- Positions are pixels of the ATTACHED image; only heights/thicknesses/scale are meters.
"""

DEFAULT_SCALE = 0.5
SCALE_MIN, SCALE_MAX = 0.05, 10.0
USE_WHITELIST = {"Residential", "School", "Kindergarten"}
KIND_WHITELIST = {"Ground", "Road", "Parking", "Sport", "Court", "Play"}


def extract_json(text):
    """Сырой ответ VLM -> dict | None (срез ```-заборов, первый {...} до последнего })."""
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.strip("`")
        if t[:4].lower() == "json":
            t = t[4:]
    start, end = t.find("{"), t.rfind("}")
    if start < 0 or end <= start:
        return None
    import json
    try:
        data = json.loads(t[start:end + 1])
        return data if isinstance(data, dict) else None
    except ValueError:
        return None


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def _valid_points(points, w, h):
    """Список точек -> (клампнутые точки | None). None = битый контур."""
    if not isinstance(points, list) or len(points) < 3 or len(points) > 32:
        return None
    fixed = []
    for p in points:
        if not isinstance(p, (list, tuple)) or len(p) != 2:
            return None
        try:
            x, y = float(p[0]), float(p[1])
        except (TypeError, ValueError):
            return None
        if not (x == x and y == y):  # NaN
            return None
        fixed.append([_clamp(x, 0, w), _clamp(y, 0, h)])
    return fixed


def validate_genplan(scene, img_w, img_h):
    """Сцена от VLM -> (чистая сцена, warnings). ValueError — не осталось секций."""
    warnings = []
    out = {
        "trace_width": int(img_w), "trace_height": int(img_h),
        "metres_per_trace_pixel": DEFAULT_SCALE,
        "residential_storey_height": 3.1, "public_storey_height": 3.3,
        "sections": [], "context": [],
    }
    if not isinstance(scene, dict):
        raise ValueError("Сцена не является JSON-объектом")
    try:
        scale = float(scene.get("metres_per_trace_pixel", DEFAULT_SCALE))
    except (TypeError, ValueError):
        scale = DEFAULT_SCALE
    if not (SCALE_MIN <= scale <= SCALE_MAX):
        warnings.append(f"Масштаб {scale} вне диапазона — принят {DEFAULT_SCALE} м/px")
        scale = DEFAULT_SCALE
    out["metres_per_trace_pixel"] = scale
    for key in ("residential_storey_height", "public_storey_height"):
        try:
            v = float(scene.get(key, out[key]))
            out[key] = _clamp(v, 2.0, 6.0)
        except (TypeError, ValueError):
            warnings.append(f"{key}: неверное значение — дефолт {out[key]}")

    for sec in scene.get("sections", []) or []:
        sid = str(sec.get("id", sec.get("building", "?")))[:24]
        points = _valid_points(sec.get("points_px", sec.get("points")), img_w, img_h)
        if points is None:
            warnings.append(f"Секция {sid}: битый контур — пропущена")
            continue
        use = sec.get("use", "Residential")
        if use not in USE_WHITELIST:
            warnings.append(f"Секция {sid}: тип {use} не поддержан — Residential")
            use = "Residential"
        try:
            floors = int(sec.get("floors", 5))
        except (TypeError, ValueError):
            floors = 5
        floors = _clamp(floors, 1, 30)
        out["sections"].append({
            "id": sid, "building": str(sec.get("building", sid))[:24], "use": use,
            "floors": floors, "points_px": points, "partial": bool(sec.get("partial")),
        })
    if not out["sections"]:
        raise ValueError("На картинке не найдено зданий для 3D-модели")

    for item in scene.get("context", []) or []:
        kind = item.get("kind")
        if kind not in KIND_WHITELIST:
            warnings.append(f"Контекст {kind}: неизвестный тип — пропущен")
            continue
        points = _valid_points(item.get("points_px", item.get("points")), img_w, img_h)
        if points is None:
            warnings.append(f"Контекст {kind}: битый контур — пропущен")
            continue
        try:
            z, depth = float(item.get("z", -0.45)), float(item.get("depth", 0.35))
        except (TypeError, ValueError):
            z, depth = -0.45, 0.35
        out["context"].append({"kind": kind, "z": z, "depth": depth, "points_px": points})
    return out, warnings
