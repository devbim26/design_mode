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


# ===================== Фаза 2: сценарий «Фасад» =====================

SYSTEM_FACADE = """You are a BIM facade analyst. Look at the attached image: a PHOTO or
RENDER of a building facade, OR an elevation DRAWING (possibly with dimension lines).
Estimate the facade as a parametric metric model. Reply with STRICT JSON ONLY - no
markdown fences, no comments, no extra keys.

Schema (ALL VALUES ARE METERS - no pixel coordinates):
{
 "storeys": <int 1-30, number of storeys>,
 "floor_height": <float m, storey height, 2.5-4 typical>,
 "width_m": <float m, facade width>,
 "depth_m": <float m, building depth - NOT visible from the facade; use 12 or the
   USER PROMPT if it states one>,
 "roof": "flat" | "gable",
 "roof_height": <float m, ridge height above the eave, only for gable>,
 "windows": {
   "rows": <int 1-4, window rows per storey>,
   "cols": <int 1-10, windows per row>,
   "w_m": <float m, window width>, "h_m": <float m, window height>,
   "margin_x_m": <float m, side margin>, "margin_y_m": <float m, margin inside a storey>,
   "skip": <rows x cols boolean matrix, true = NO window there (e.g. stair shaft,
     blind panels); all-false if every cell is glazed>
 },
 "balconies": [{"floor": <int 1-based>, "x_m": <center position from facade LEFT edge,
   m>, "w_m": <width>, "d_m": <projection depth>}],
 "colors": {"walls": "#rrggbb", "roof": "#rrggbb", "plinth": "#rrggbb"}
}

Rules:
- SCALE: if the image has dimension lines - use them (they are exact). Otherwise use
  anchors: storey ~3 m, window ~1.5 x 1.5 m, entrance door ~2.1 m, balcony ~3 x 1.2 m.
- Count storeys and window columns CAREFULLY; one window row per storey is typical.
- Perspective in photos: treat the facade as flat (orthographic).
- The USER PROMPT overrides your guesses (storeys, depth, roof, colors) wherever it
  states them.
"""


def _facade_float(value, default, lo, hi, field, warnings):
    try:
        v = float(value)
    except (TypeError, ValueError):
        warnings.append(f"{field}: неверное значение — дефолт {default}")
        return default
    if v != v:  # NaN
        warnings.append(f"{field}: NaN — дефолт {default}")
        return default
    if v < lo or v > hi:
        clamped = max(lo, min(hi, v))
        warnings.append(f"{field}: {v:g} вне [{lo}, {hi}] — кламп до {clamped:g}")
        return clamped
    return v


def _is_hex(value):
    import re as _re
    return isinstance(value, str) and _re.fullmatch(r"#[0-9a-fA-F]{6}", value) is not None


def validate_facade(scene):
    """Сцена фасада от VLM -> (чистая сцена, warnings). ValueError — не фасад."""
    if not isinstance(scene, dict) or not any(
            k in scene for k in ("storeys", "width_m", "windows", "floor_height")):
        raise ValueError("Не удалось распознать фасад на картинке")
    warnings = []
    out = {}
    out["storeys"] = int(_facade_float(scene.get("storeys", 5), 5, 1, 30, "storeys", warnings))
    out["floor_height"] = _facade_float(scene.get("floor_height", 3.0), 3.0, 2.0, 6.0,
                                        "floor_height", warnings)
    out["width_m"] = _facade_float(scene.get("width_m", 18.0), 18.0, 3.0, 200.0,
                                   "width_m", warnings)
    out["depth_m"] = _facade_float(scene.get("depth_m", 12.0), 12.0, 3.0, 60.0,
                                   "depth_m", warnings)
    roof = scene.get("roof", "flat")
    if roof not in ("flat", "gable"):
        warnings.append(f"roof: «{roof}» не поддержан — flat")
        roof = "flat"
    out["roof"] = roof
    out["roof_height"] = _facade_float(scene.get("roof_height", 2.5), 2.5, 0.5, 8.0,
                                       "roof_height", warnings)

    src = scene.get("windows")
    if not isinstance(src, dict):
        if src is not None:
            warnings.append("windows: не объект — дефолты сетки окон")
        src = {}
    win = {}
    win["rows"] = int(_facade_float(src.get("rows", 1), 1, 1, 4, "windows.rows", warnings))
    win["cols"] = int(_facade_float(src.get("cols", 3), 3, 1, 10, "windows.cols", warnings))
    win["margin_x_m"] = _facade_float(src.get("margin_x_m", 1.0), 1.0, 0.05, 5.0,
                                      "windows.margin_x_m", warnings)
    win["margin_y_m"] = _facade_float(src.get("margin_y_m", 0.8), 0.8, 0.05, 3.0,
                                      "windows.margin_y_m", warnings)
    win["w_m"] = _facade_float(src.get("w_m", 1.5), 1.5, 0.3, 5.0, "windows.w_m", warnings)
    win["h_m"] = _facade_float(src.get("h_m", 1.5), 1.5, 0.3, 4.0, "windows.h_m", warnings)
    # поля не должны съедать фасад/этаж: гарантия ≥0.3 м на окно до FIT
    max_mx = max(0.05, (out["width_m"] - 0.3 * win["cols"]) / 2)
    if win["margin_x_m"] > max_mx:
        warnings.append(f"windows.margin_x_m: {win['margin_x_m']:g} велик — сжат до {max_mx:g}")
        win["margin_x_m"] = max_mx
    max_my = max(0.05, (out["floor_height"] - 0.3 * win["rows"]) / 2)
    if win["margin_y_m"] > max_my:
        warnings.append(f"windows.margin_y_m: {win['margin_y_m']:g} велик — сжат до {max_my:g}")
        win["margin_y_m"] = max_my
    # FIT: сетка обязана влезать в фасад/этаж
    fit_w = (out["width_m"] - 2 * win["margin_x_m"]) / win["cols"]
    if win["w_m"] > fit_w:
        warnings.append(f"windows.w_m: {win['w_m']:g} не влезает — сжат до {fit_w:g}")
        win["w_m"] = fit_w
    fit_h = (out["floor_height"] - 2 * win["margin_y_m"]) / win["rows"]
    if win["h_m"] > fit_h:
        warnings.append(f"windows.h_m: {win['h_m']:g} не влезает — сжат до {fit_h:g}")
        win["h_m"] = fit_h
    # skip -> строго rows×cols из bool
    raw_skip = src.get("skip")
    skip = [[False] * win["cols"] for _ in range(win["rows"])]
    if raw_skip is not None:
        ok = isinstance(raw_skip, list) and len(raw_skip) == win["rows"] and all(
            isinstance(r, list) and len(r) == win["cols"] for r in raw_skip)
        if ok:
            for j in range(win["rows"]):
                for i in range(win["cols"]):
                    skip[j][i] = bool(raw_skip[j][i])
        else:
            warnings.append("windows.skip: неверная форма — все окна считаются остеклёнными")
    win["skip"] = skip
    out["windows"] = win

    out["balconies"] = []
    raw_balconies = scene.get("balconies")
    if not isinstance(raw_balconies, list):
        if raw_balconies:
            warnings.append("balconies: не список — пропущены")
        raw_balconies = []
    for idx, bal in enumerate(raw_balconies, start=1):
        if not isinstance(bal, dict):
            warnings.append(f"Балкон {idx}: не объект — пропущен")
            continue
        try:
            floor = int(bal.get("floor", 0))
        except (TypeError, ValueError):
            floor = 0
        if floor < 1 or floor > out["storeys"]:
            warnings.append(f"Балкон {idx}: этаж {floor} вне 1..{out['storeys']} — пропущен")
            continue
        try:
            x = float(bal.get("x_m", out["width_m"] / 2))
            w_b = float(bal.get("w_m", 3.0))
            d_b = float(bal.get("d_m", 1.2))
        except (TypeError, ValueError):
            warnings.append(f"Балкон {idx}: неверные размеры — пропущен")
            continue
        if not (0.0 <= x <= out["width_m"]) or not (0.5 <= w_b <= out["width_m"]) \
                or not (0.3 <= d_b <= 5.0):
            warnings.append(f"Балкон {idx}: размеры вне диапазона — пропущен")
            continue
        out["balconies"].append({"floor": floor, "x_m": x, "w_m": w_b, "d_m": d_b})

    src_colors = scene.get("colors")
    if not isinstance(src_colors, dict):
        if src_colors is not None:
            warnings.append("colors: не объект — дефолты цветов")
        src_colors = {}
    out["colors"] = {}
    for key, default in (("walls", "#c8b89a"), ("roof", "#52616b"), ("plinth", "#8d8d8d")):
        value = src_colors.get(key)
        if _is_hex(value):
            out["colors"][key] = value
        else:
            warnings.append(f"colors.{key}: не hex — дефолт {default}")
            out["colors"][key] = default
    return out, warnings
