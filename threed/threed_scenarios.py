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
 "roof": "flat" | "gable" | "hip" | "mansard",
 "roof_height": <float m, ridge height above the eave, only for gable>,
 "windows": {
   "rows": <int 1-4, window rows per storey>,
   "cols": <int 1-10, windows per row>,
   "w_m": <float m, window width>, "h_m": <float m, window height>,
   "margin_x_m": <float m, side margin>, "margin_y_m": <float m, margin inside a storey>,
   "skip": <rows x cols boolean matrix, true = NO window there (e.g. stair shaft,
     blind panels); all-false if every cell is glazed>,
   "shape": "rect" | "arched"},
 "balconies": [{"floor": <int 1-based>, "x_m": <center position from facade LEFT edge,
   m>, "w_m": <width>, "d_m": <projection depth>}],
 "dormers": [{"floor": <int 2..storeys>, "x_m": <center from facade LEFT edge>,
   "w_m": 0.6-4, "h_m": 0.6-3}],
 "chimneys": [{"x_m": <from LEFT edge>, "floor": <last storey default>}] (max 6),
 "entrance": {"x_m": <center from LEFT edge>, "w_m": 0.9-5,
   "style": "porch" (крыльцо) | "portico" (колонны+навес)} | null,
 "towers": [{"x_m": <center, may stand beside the facade edge>, "w_m", "depth_m",
   "floors": <int>, "round": <bool: cylinder body>, "roof": "cone"|"pyramid"|"flat",
   "roof_h_m": <apex height>}] (max 4),
 "custom_parts": [free-form details from primitives, max 60:
   {"kind": "box" | "prism" | "cylinder" | "cone",
    "size": [w, d, h] m, "pos": [x, y, z] m (x along facade from CENTER, y from
      facade face positive INTO the building, z from ground),
    "rot_deg": <yaw>, "profile": [[x, y], ...] (prism only, 3-32 pts, local),
    "color": "#rrggbb" | "walls"|"roof"|"plinth"|"glazing"|"balcony"}],
 "colors": {"walls": "#rrggbb", "roof": "#rrggbb", "plinth": "#rrggbb"}
}

Rules:
- SCALE: if the image has dimension lines - use them (they are exact). Otherwise use
  anchors: storey ~3 m, window ~1.5 x 1.5 m, entrance door ~2.1 m, balcony ~3 x 1.2 m.
- Count storeys and window columns CAREFULLY; one window row per storey is typical.
- Perspective in photos: treat the facade as flat (orthographic).
- Use dormers/towers/chimneys/entrance/custom_parts when the image shows them
  (dormer windows in the roof, corner turrets, chimneys, entrance porches).
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


CUSTOM_KINDS = {"box", "prism", "cylinder", "cone"}
CUSTOM_COLOR_KEYS = {"walls", "roof", "plinth", "glazing", "balcony"}


def _valid_custom_parts(raw, out, warnings):
    """Грамматика примитивов -> чистый список (клампы/дропы с warnings)."""
    if not isinstance(raw, list):
        if raw:
            warnings.append("custom_parts: не список — пропущены")
        return []
    parts = []
    # лимит 60 — на ВЫХОДЕ: дропнутый мусор не съедает квоту валидным частям
    for idx, p in enumerate(raw, start=1):
        if len(parts) >= 60:
            break
        if not isinstance(p, dict):
            warnings.append(f"custom_parts {idx}: не объект — пропущен")
            continue
        kind = p.get("kind")
        if kind not in CUSTOM_KINDS:
            warnings.append(f"custom_parts {idx}: kind «{kind}» не поддержан — пропущен")
            continue
        try:
            wv, dv, hv = (float(v) for v in (p.get("size") or [1.0, 1.0, 1.0]))
            xv, yv, zv = (float(v) for v in (p.get("pos") or [0.0, 0.0, 0.0]))
        except (TypeError, ValueError):
            warnings.append(f"custom_parts {idx}: size/pos не числа — пропущен")
            continue
        if wv != wv or dv != dv or hv != hv or xv != xv or yv != yv or zv != zv:
            warnings.append(f"custom_parts {idx}: NaN — пропущен")
            continue
        h_max = out["storeys"] * out["floor_height"] + 15.0
        part = {"kind": kind,
                "size": [_clamp(wv, 0.05, out["width_m"]),
                         _clamp(dv, 0.05, out["depth_m"] + 10.0),
                         _clamp(hv, 0.05, h_max)],
                "pos": [_clamp(xv, -out["width_m"], out["width_m"]),
                        _clamp(yv, -(out["depth_m"] + 10.0), out["depth_m"] + 10.0),
                        _clamp(zv, 0.0, h_max)],
                "rot_deg": _facade_float(p.get("rot_deg", 0), 0, -180.0, 180.0,
                                         f"custom_parts {idx}.rot_deg", warnings)}
        if kind == "prism":
            profile, ok = [], True
            raw_pts = p.get("profile")
            if not isinstance(raw_pts, list) or not 3 <= len(raw_pts) <= 32:
                ok = False
            else:
                for pt in raw_pts:
                    if not isinstance(pt, (list, tuple)) or len(pt) != 2:
                        ok = False
                        break
                    try:
                        px, py = float(pt[0]), float(pt[1])
                    except (TypeError, ValueError):
                        ok = False
                        break
                    if px != px or py != py:
                        ok = False
                        break
                    profile.append([_clamp(px, -30.0, 30.0), _clamp(py, -30.0, 30.0)])
            if not ok:
                warnings.append(f"custom_parts {idx}: профиль нужен 3..32 точки — пропущен")
                continue
            part["profile"] = profile
        color = p.get("color")
        part["color"] = color if (isinstance(color, str) and
                                  (color in CUSTOM_COLOR_KEYS or _is_hex(color))) else "walls"
        parts.append(part)
    if len(raw) > 60:
        warnings.append("custom_parts: больше 60 — лишние отброшены")
    return parts


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
    if roof not in ("flat", "gable", "hip", "mansard"):
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
    shape = src.get("shape", "rect")
    if shape not in ("rect", "arched"):
        warnings.append(f"windows.shape «{shape}» не поддержан — rect")
        shape = "rect"
    win["shape"] = shape
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
        if x != x or w_b != w_b or d_b != d_b:  # NaN
            warnings.append(f"Балкон {idx}: неверные размеры — пропущен")
            continue
        if not (0.5 <= w_b <= out["width_m"]) or not (0.3 <= d_b <= 5.0):
            warnings.append(f"Балкон {idx}: размеры вне диапазона — пропущен")
            continue
        # плита целиком в фасаде: центр в [w_b/2, width-w_b/2] (кламп, не дроп)
        lo, hi = w_b / 2, out["width_m"] - w_b / 2
        if x < lo or x > hi:
            clamped = max(lo, min(hi, x))
            warnings.append(
                f"Балкон {idx}: центр {x:g} — плита выходит за фасад, "
                f"центр смещён до {clamped:g}")
            x = clamped
        out["balconies"].append({"floor": floor, "x_m": x, "w_m": w_b, "d_m": d_b})

    out["dormers"] = []
    for idx, d in enumerate((scene.get("dormers") or [])[:12], start=1):
        if not isinstance(d, dict):
            warnings.append(f"Dormer {idx}: не объект — пропущен")
            continue
        floor = int(_facade_float(d.get("floor", 2), 2, 2, out["storeys"],
                                  f"dormer {idx}.floor", warnings))
        w_d = _facade_float(d.get("w_m", 1.2), 1.2, 0.6, 4.0,
                            f"dormer {idx}.w_m", warnings)
        h_d = _facade_float(d.get("h_m", 1.2), 1.2, 0.6, 3.0,
                            f"dormer {idx}.h_m", warnings)
        x = _facade_float(d.get("x_m", out["width_m"] / 2), out["width_m"] / 2,
                          w_d / 2, out["width_m"] - w_d / 2, f"dormer {idx}.x_m", warnings)
        out["dormers"].append({"floor": floor, "x_m": x, "w_m": w_d, "h_m": h_d})
    if isinstance(scene.get("dormers"), list) and len(scene["dormers"]) > 12:
        warnings.append("dormers: больше 12 — лишние отброшены")

    out["chimneys"] = []
    for idx, c in enumerate((scene.get("chimneys") or [])[:6], start=1):
        if not isinstance(c, dict):
            warnings.append(f"Труба {idx}: не объект — пропущена")
            continue
        x = _facade_float(c.get("x_m", out["width_m"] / 2), out["width_m"] / 2,
                          0.0, out["width_m"], f"труба {idx}.x_m", warnings)
        floor = int(_facade_float(c.get("floor", out["storeys"]), out["storeys"],
                                  1, out["storeys"], f"труба {idx}.floor", warnings))
        out["chimneys"].append({"x_m": x, "floor": floor})

    out["entrance"] = None
    e = scene.get("entrance")
    if isinstance(e, dict):
        style = e.get("style", "porch")
        if style not in ("porch", "portico"):
            warnings.append(f"entrance.style «{style}» не поддержан — porch")
            style = "porch"
        w_e = _facade_float(e.get("w_m", 2.0), 2.0, 0.9, 5.0, "entrance.w_m", warnings)
        x_e = _facade_float(e.get("x_m", out["width_m"] / 2), out["width_m"] / 2,
                            w_e / 2, out["width_m"] - w_e / 2, "entrance.x_m", warnings)
        out["entrance"] = {"x_m": x_e, "w_m": w_e, "style": style}

    out["towers"] = []
    for idx, t in enumerate((scene.get("towers") or [])[:4], start=1):
        if not isinstance(t, dict):
            warnings.append(f"Башня {idx}: не объект — пропущена")
            continue
        w_t = _facade_float(t.get("w_m", 3.0), 3.0, 1.0, 10.0, f"башня {idx}.w_m", warnings)
        d_t = _facade_float(t.get("depth_m", w_t), w_t, 1.0, 10.0,
                            f"башня {idx}.depth_m", warnings)
        floors = int(_facade_float(t.get("floors", out["storeys"]), out["storeys"],
                                   1, 30, f"башня {idx}.floors", warnings))
        x = _facade_float(t.get("x_m", 0.0), 0.0,
                          -out["width_m"] / 2 - w_t / 2, out["width_m"] / 2 + w_t / 2,
                          f"башня {idx}.x_m", warnings)
        roof = t.get("roof", "cone")
        if roof not in ("cone", "pyramid", "flat"):
            warnings.append(f"Башня {idx}: крыша «{roof}» не поддержана — cone")
            roof = "cone"
        rh = _facade_float(t.get("roof_h_m", 1.5), 1.5, 0.3, 6.0,
                           f"башня {idx}.roof_h_m", warnings)
        out["towers"].append({"x_m": x, "w_m": w_t, "depth_m": d_t, "floors": floors,
                              "round": bool(t.get("round")), "roof": roof, "roof_h_m": rh})

    out["custom_parts"] = _valid_custom_parts(scene.get("custom_parts"), out, warnings)

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


# ===================== Фаза 3: сценарий «Интерьер» =====================

SYSTEM_INTERIOR = """You are a BIM interior analyst. Look at the attached 2D FLOOR PLAN
(apartment / room drawing, PDF page fragment or screenshot; NOT a photo of a finished
interior). Trace the plan into a parametric model. Reply with STRICT JSON ONLY - no
markdown fences, no comments, no extra keys.

Schema (positions in PIXELS of the image, sizes/heights in METERS):
{
 "metres_per_trace_pixel": <float: meters per image pixel. Estimate from anchors:
   door opening 0.9-1 m, bed 2.0 x 1.6 m, toilet 0.4 m, or printed dimension lines
   (they are exact). Typical flat plan ~0.005-0.02.>,
 "wall_height": <float m, floor-to-ceiling, default 2.7>,
 "outline": [[x, y], ...outer boundary pixels, y=0 at the TOP of the image],
 "walls": [
   {"points_px": [[x1, y1], [x2, y2]], "thickness_m": <float m, interior 0.1-0.2,
     exterior 0.3-0.5>, "exterior": <bool>}
 ],
 "openings": [
   {"wall_idx": <int index into walls> | "outline", "x_px": <position ALONG the wall
     from its first point, image pixels>, "width_m": 0.9, "height_m": 2.1,
     "sill_m": <0.0 for doors, ~0.9 for windows>, "kind": "door" | "window"}
 ],
 "rooms": [
   {"name": "<label read from the plan, e.g. Kitchen; Room N if unlabeled>",
    "type": "living|bedroom|kitchen|bath|wc|hall|wardrobe|balcony|other",
    "points_px": [[x, y], ...]}
 ],
 "furniture": [
   {"type": "bed|sofa|table|chair|wardrobe|kitchen|bath|toilet|sink|lamp|other",
    "x_px": <center x>, "y_px": <center y>, "w_m": <width>, "d_m": <depth>,
    "h_m": <height>, "rot_deg": <rotation around center, 0 = as drawn>}
 ]
}

Rules:
- y=0 is the TOP of the image; pixel coordinates only for positions/along-wall
  distances; all sizes, heights and thicknesses are meters.
- List every wall segment with its drawn thickness; exterior walls form the outline.
- Rooms MUST use the label text read on the plan when present.
- Furniture: one entry per item, placed as drawn (position + rotation).
- The USER PROMPT overrides your guesses (scale, wall height) wherever it states them.
"""

ROOM_TYPES = {"living", "bedroom", "kitchen", "bath", "wc", "hall",
              "wardrobe", "balcony", "other"}
FURNITURE_TYPES = {"bed", "sofa", "table", "chair", "wardrobe", "kitchen",
                   "bath", "toilet", "sink", "lamp", "other"}
INTERIOR_SCALE_DEFAULT = 0.01
# MAX 0.5 (не 0.1): валидны и миниатюрные растровые планы — 40×30 px ≈
# 10×7.5 м при 0.25 м/px; жёсткий потолок ловит лишь бессмыслицу от VLM.
INTERIOR_SCALE_MIN, INTERIOR_SCALE_MAX = 0.001, 0.5


def _num(value, default, lo, hi, field, warnings):
    """float с NaN-гвардом и клампом (паттерн _facade_float, обобщено)."""
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


def _px_point(value, w, h):
    """Одна точка [x, y] -> [x, y] клампнутая | None."""
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    try:
        x, y = float(value[0]), float(value[1])
    except (TypeError, ValueError):
        return None
    if x != x or y != y:
        return None
    return [_clamp(x, 0, w), _clamp(y, 0, h)]


def validate_interior(scene, img_w, img_h):
    """Сцена интерьера от VLM -> (чистая сцена, warnings). ValueError — не план."""
    if not isinstance(scene, dict):
        raise ValueError("Сцена не является JSON-объектом")
    warnings = []
    out = {"trace_width": int(img_w), "trace_height": int(img_h),
           "metres_per_trace_pixel": INTERIOR_SCALE_DEFAULT, "wall_height": 2.7,
           "outline": [], "walls": [], "openings": [], "rooms": [], "furniture": []}
    scale = _num(scene.get("metres_per_trace_pixel"), INTERIOR_SCALE_DEFAULT,
                 INTERIOR_SCALE_MIN, INTERIOR_SCALE_MAX, "metres_per_trace_pixel",
                 warnings)
    out["metres_per_trace_pixel"] = scale
    out["wall_height"] = _num(scene.get("wall_height"), 2.7, 2.0, 4.0,
                              "wall_height", warnings)
    if not (scene.get("outline") or scene.get("walls")):
        raise ValueError("Не удалось распознать план помещения")

    outline = _valid_points(scene.get("outline"), img_w, img_h)
    if outline is None:
        warnings.append("outline: битый контур — стены по segments")
    else:
        out["outline"] = outline

    raw_walls = scene.get("walls")
    if not isinstance(raw_walls, list):
        warnings.append("walls: не список — пропущены")
        raw_walls = []
    for idx, wall in enumerate(raw_walls, start=1):
        if not isinstance(wall, dict):
            warnings.append(f"Стена {idx}: не объект — пропущена")
            continue
        pts = wall.get("points_px")
        if not isinstance(pts, list) or len(pts) != 2:
            warnings.append(f"Стена {idx}: нужен ровно 2 точки — пропущена")
            continue
        p1 = _px_point(pts[0], img_w, img_h)
        p2 = _px_point(pts[1], img_w, img_h)
        if p1 is None or p2 is None:
            warnings.append(f"Стена {idx}: битые координаты — пропущена")
            continue
        if abs(p2[0] - p1[0]) + abs(p2[1] - p1[1]) < 1.0:
            warnings.append(f"Стена {idx}: нулевая длина — пропущена")
            continue
        out["walls"].append({
            "points_px": [p1, p2],
            "thickness_m": _num(wall.get("thickness_m", 0.15), 0.15, 0.05, 0.6,
                                f"Стена {idx}.thickness_m", warnings),
            "exterior": bool(wall.get("exterior")),
        })

    raw_ops = scene.get("openings")
    if not isinstance(raw_ops, list):
        if raw_ops:
            warnings.append("openings: не список — пропущены")
        raw_ops = []
    for idx, op in enumerate(raw_ops, start=1):
        if not isinstance(op, dict):
            warnings.append(f"Проём {idx}: не объект — пропущен")
            continue
        widx = op.get("wall_idx")
        if widx != "outline" and not (isinstance(widx, int) and 0 <= widx < len(out["walls"])):
            warnings.append(f"Проём {idx}: wall_idx {widx} не указывает на стену — пропущен")
            continue
        if widx == "outline" and not out["outline"]:
            warnings.append(f"Проём {idx}: нет outline — пропущен")
            continue
        kind = op.get("kind")
        if kind not in ("door", "window"):
            warnings.append(f"Проём {idx}: kind {kind} не поддержан — пропущен")
            continue
        h_default = 2.1 if kind == "door" else 1.5
        out["openings"].append({
            "wall_idx": widx,
            "x_px": _num(op.get("x_px", 0), 0, 0, 100000, f"Проём {idx}.x_px", warnings),
            "width_m": _num(op.get("width_m", 0.9), 0.9, 0.4, 4.0,
                            f"Проём {idx}.width_m", warnings),
            "height_m": _num(op.get("height_m", h_default), h_default, 0.5, 3.0,
                             f"Проём {idx}.height_m", warnings),
            "sill_m": _num(op.get("sill_m", 0.0 if kind == "door" else 0.9),
                           0.0, 0.0, 2.0, f"Проём {idx}.sill_m", warnings),
            "kind": kind,
        })

    raw_rooms = scene.get("rooms")
    if not isinstance(raw_rooms, list):
        if raw_rooms:
            warnings.append("rooms: не список — пропущены")
        raw_rooms = []
    for idx, room in enumerate(raw_rooms, start=1):
        if not isinstance(room, dict):
            warnings.append(f"Комната {idx}: не объект — пропущена")
            continue
        points = _valid_points(room.get("points_px"), img_w, img_h)
        if points is None:
            warnings.append(f"Комната {idx}: битый контур — пропущена")
            continue
        name = room.get("name")
        name = str(name).strip()[:24] if isinstance(name, str) and name.strip() \
            else f"Комната {idx}"
        rtype = room.get("type")
        if rtype not in ROOM_TYPES:
            warnings.append(f"Комната {name}: тип {rtype} не поддержан — other")
            rtype = "other"
        out["rooms"].append({"name": name, "type": rtype, "points_px": points})

    raw_furn = scene.get("furniture")
    if not isinstance(raw_furn, list):
        if raw_furn:
            warnings.append("furniture: не список — пропущены")
        raw_furn = []
    for idx, item in enumerate(raw_furn, start=1):
        if not isinstance(item, dict):
            warnings.append(f"Мебель {idx}: не объект — пропущена")
            continue
        p = _px_point([item.get("x_px"), item.get("y_px")], img_w, img_h)
        if p is None:
            warnings.append(f"Мебель {idx}: битая позиция — пропущена")
            continue
        ftype = item.get("type")
        if ftype not in FURNITURE_TYPES:
            warnings.append(f"Мебель {idx}: тип {ftype} не поддержан — other")
            ftype = "other"
        out["furniture"].append({
            "type": ftype, "x_px": p[0], "y_px": p[1],
            "w_m": _num(item.get("w_m", 0.6), 0.6, 0.1, 6.0,
                        f"Мебель {idx}.w_m", warnings),
            "d_m": _num(item.get("d_m", 0.6), 0.6, 0.1, 6.0,
                        f"Мебель {idx}.d_m", warnings),
            "h_m": _num(item.get("h_m", 0.5), 0.5, 0.05, 3.0,
                        f"Мебель {idx}.h_m", warnings),
            "rot_deg": _num(item.get("rot_deg", 0), 0, -180.0, 180.0,
                            f"Мебель {idx}.rot_deg", warnings),
        })

    if not out["walls"] and not out["rooms"] and not out["furniture"]:
        raise ValueError("На картинке не найдено объектов для 3D-модели")
    return out, warnings


# ===================== Фаза 4: сценарий «Сцена» (camera mapping) =====================

SYSTEM_SCENE = """You are a BIM street-scene analyst. Look at the attached PHOTO of a
street / yard with 1-3 buildings, trees, cars and people. Reconstruct a rough 3D
massing scene as parametric JSON. Reply with STRICT JSON ONLY - no markdown
fences, no comments, no extra keys.

Schema (ALL VALUES ARE METERS; plan axes: X east, Y north; the MAIN building
facade faces SOUTH = -Y and stands near the origin):
{
 "camera": {
   "azimuth_deg": <float -75..75; 0 = camera straight in front of the main facade
     (south of it, looking north); positive = camera moved to the RIGHT of the
     facade (east side)>,
   "eye_height_m": <camera eye height; street-level photo ~1.5-1.8>,
   "dist_m": <distance from camera to the main facade, 10..200>
 },
 "buildings": [
   {"main": <bool; true ONLY for the building closest to the camera>,
    "x_m": <center X>, "y_m": <center Y>,
    "width_m": <facade length along X>, "depth_m": <along Y>,
    "storeys": <int 1-30>, "floor_height": <2.0-6.0, typical 3.0>,
    "roof": "flat" | "gable", "roof_height": <ridge above eave>,
    "windows": {"rows": <1-2>, "cols": <1-10>, "w_m": <>, "h_m": <>,
      "margin_x_m": <>, "margin_y_m": <>},
    "balconies": [{"floor": <int, 2..storeys>, "x_m": <center from facade LEFT
      edge, m>, "w_m": <>, "d_m": <projection depth>}],
    "colors": {"walls": "#rrggbb", "roof": "#rrggbb", "plinth": "#rrggbb"}}
 ],
 "context": {
   "trees": [{"x_m": <>, "y_m": <>, "h_m": <5-15>, "crown_d_m": <2-6>}],
   "cars": [{"x_m": <>, "y_m": <>, "rot_deg": <heading; 0 = along X>}],
   "people": [{"x_m": <>, "y_m": <>}]
 }
}

Rules:
- Scale anchors: storey ~3 m, window ~1.5 x 1.5 m, door ~2.1 m, car 4.5 x 1.8 m,
  tree 5-8 m, person 1.7 m. Printed dimension lines are exact.
- The MAIN building is the one closest to the camera: place it at x_m=0, y_m=0
  with its main facade facing -Y (south). Other buildings: offsets in meters.
- Count storeys and window columns of the MAIN building CAREFULLY; perspective in
  photos: treat facades as flat (orthographic).
- Side walls get a simplified window grid automatically - do not invent them.
- The USER PROMPT overrides your guesses wherever it states them.
"""


def validate_scene(scene):
    """Сцена улицы от VLM -> (чистая сцена, warnings). ValueError — нет зданий."""
    if not isinstance(scene, dict) or not isinstance(scene.get("buildings"), list) \
            or not scene["buildings"]:
        raise ValueError("Не удалось распознать сцену на картинке (нет зданий)")
    warnings = []
    out = {"camera": {}, "buildings": [], "context": {}}

    cam = scene.get("camera") if isinstance(scene.get("camera"), dict) else {}
    out["camera"]["azimuth_deg"] = _facade_float(
        cam.get("azimuth_deg", 25.0), 25.0, -75.0, 75.0, "camera.azimuth_deg", warnings)
    out["camera"]["eye_height_m"] = _facade_float(
        cam.get("eye_height_m", 1.6), 1.6, 0.3, 30.0, "camera.eye_height_m", warnings)
    out["camera"]["dist_m"] = _facade_float(
        cam.get("dist_m", 35.0), 35.0, 10.0, 200.0, "camera.dist_m", warnings)

    main_seen = False
    for idx, b in enumerate(scene["buildings"][:3], start=1):
        if not isinstance(b, dict):
            warnings.append(f"Здание {idx}: не объект — пропущено")
            continue
        if bool(b.get("main")) and main_seen:
            warnings.append(f"Здание {idx}: main уже назначен — здание отброшено")
            continue
        main = bool(b.get("main"))
        main_seen = main_seen or main
        bld = {"main": main}
        bld["x_m"] = _facade_float(b.get("x_m", 0.0), 0.0, -150.0, 150.0,
                                   f"Здание {idx}.x_m", warnings)
        bld["y_m"] = _facade_float(b.get("y_m", 0.0), 0.0, -150.0, 150.0,
                                   f"Здание {idx}.y_m", warnings)
        bld["width_m"] = _facade_float(b.get("width_m", 18.0), 18.0, 3.0, 120.0,
                                       f"Здание {idx}.width_m", warnings)
        bld["depth_m"] = _facade_float(b.get("depth_m", 12.0), 12.0, 3.0, 60.0,
                                       f"Здание {idx}.depth_m", warnings)
        bld["storeys"] = int(_facade_float(b.get("storeys", 5), 5, 1, 30,
                                           f"Здание {idx}.storeys", warnings))
        bld["floor_height"] = _facade_float(b.get("floor_height", 3.0), 3.0, 2.0, 6.0,
                                            f"Здание {idx}.floor_height", warnings)
        roof = b.get("roof", "flat")
        if roof not in ("flat", "gable"):
            warnings.append(f"Здание {idx}: крыша «{roof}» не поддержана — flat")
            roof = "flat"
        bld["roof"] = roof
        bld["roof_height"] = _facade_float(b.get("roof_height", 2.5), 2.5, 0.5, 8.0,
                                           f"Здание {idx}.roof_height", warnings)
        wsrc = b.get("windows") if isinstance(b.get("windows"), dict) else {}
        win = {}
        win["rows"] = int(_facade_float(wsrc.get("rows", 1), 1, 1, 2,
                                        f"Здание {idx}.windows.rows", warnings))
        win["cols"] = int(_facade_float(wsrc.get("cols", 4), 4, 1, 10,
                                        f"Здание {idx}.windows.cols", warnings))
        win["margin_x_m"] = _facade_float(wsrc.get("margin_x_m", 1.0), 1.0, 0.05, 5.0,
                                          f"Здание {idx}.windows.margin_x_m", warnings)
        win["margin_y_m"] = _facade_float(wsrc.get("margin_y_m", 0.8), 0.8, 0.05, 3.0,
                                          f"Здание {idx}.windows.margin_y_m", warnings)
        win["w_m"] = _facade_float(wsrc.get("w_m", 1.5), 1.5, 0.3, 5.0,
                                   f"Здание {idx}.windows.w_m", warnings)
        win["h_m"] = _facade_float(wsrc.get("h_m", 1.5), 1.5, 0.3, 4.0,
                                   f"Здание {idx}.windows.h_m", warnings)
        max_mx = max(0.05, (bld["width_m"] - 0.3 * win["cols"]) / 2)
        win["margin_x_m"] = min(win["margin_x_m"], max_mx)
        max_my = max(0.05, (bld["floor_height"] - 0.3 * win["rows"]) / 2)
        win["margin_y_m"] = min(win["margin_y_m"], max_my)
        win["w_m"] = min(win["w_m"], (bld["width_m"] - 2 * win["margin_x_m"]) / win["cols"])
        win["h_m"] = min(win["h_m"], (bld["floor_height"] - 2 * win["margin_y_m"]) / win["rows"])
        bld["windows"] = win
        bals = []
        raw_bals = b.get("balconies") if isinstance(b.get("balconies"), list) else []
        for j, bal in enumerate(raw_bals[:20], start=1):
            if not isinstance(bal, dict):
                warnings.append(f"Здание {idx} балкон {j}: не объект — пропущен")
                continue
            try:
                floor = int(bal.get("floor", 0))
                x = float(bal.get("x_m", bld["width_m"] / 2))
                w_b = float(bal.get("w_m", 3.0))
                d_b = float(bal.get("d_m", 1.2))
            except (TypeError, ValueError):
                warnings.append(f"Здание {idx} балкон {j}: неверные размеры — пропущен")
                continue
            if x != x or w_b != w_b or d_b != d_b:  # NaN
                continue
            if floor < 2 or floor > bld["storeys"]:
                continue  # 1-й этаж — не балкон; вне диапазона — тихий skip
            if not (0.5 <= w_b <= bld["width_m"]) or not (0.3 <= d_b <= 5.0):
                warnings.append(f"Здание {idx} балкон {j}: размеры вне диапазона — пропущен")
                continue
            lo, hi = w_b / 2, bld["width_m"] - w_b / 2
            if x < lo or x > hi:
                x = max(lo, min(hi, x))
                warnings.append(f"Здание {idx} балкон {j}: центр вне фасада — кламп {x:g}")
            bals.append({"floor": floor, "x_m": x, "w_m": w_b, "d_m": d_b})
        bld["balconies"] = bals
        src_colors = b.get("colors") if isinstance(b.get("colors"), dict) else {}
        colors = {}
        for key, default in (("walls", "#c8b89a"), ("roof", "#52616b"),
                             ("plinth", "#8d8d8d")):
            v = src_colors.get(key)
            colors[key] = v if _is_hex(v) else default
        bld["colors"] = colors
        out["buildings"].append(bld)
    if len(scene["buildings"]) > 3:
        warnings.append("buildings: больше 3 — лишние отброшены")
    if not out["buildings"]:
        raise ValueError("На картинке не найдено зданий для 3D-модели")
    if not main_seen:
        out["buildings"][0]["main"] = True  # первое — главное

    ctx_raw = scene.get("context") if isinstance(scene.get("context"), dict) else {}
    ctx = {"trees": [], "cars": [], "people": []}
    raw_trees = ctx_raw.get("trees")
    if isinstance(raw_trees, list):
        for it in raw_trees[:40]:
            if not isinstance(it, dict):
                continue
            try:
                x, y = float(it.get("x_m", 0.0)), float(it.get("y_m", 0.0))
            except (TypeError, ValueError):
                continue
            if x != x or y != y:
                continue
            ctx["trees"].append({
                "x_m": _clamp(x, -150.0, 150.0), "y_m": _clamp(y, -150.0, 150.0),
                "h_m": _facade_float(it.get("h_m", 6.0), 6.0, 2.0, 30.0,
                                     "tree.h_m", warnings),
                "crown_d_m": _facade_float(it.get("crown_d_m", 3.0), 3.0, 1.0, 10.0,
                                           "tree.crown_d_m", warnings)})
    raw_cars = ctx_raw.get("cars")
    if isinstance(raw_cars, list):
        for it in raw_cars[:20]:
            if not isinstance(it, dict):
                continue
            try:
                x, y = float(it.get("x_m", 0.0)), float(it.get("y_m", 0.0))
                rot = float(it.get("rot_deg", 0.0))
            except (TypeError, ValueError):
                continue
            if x != x or y != y:
                continue
            ctx["cars"].append({"x_m": _clamp(x, -150.0, 150.0),
                                "y_m": _clamp(y, -150.0, 150.0),
                                "rot_deg": _clamp(rot, -180.0, 180.0)})
    raw_people = ctx_raw.get("people")
    if isinstance(raw_people, list):
        for it in raw_people[:40]:
            if not isinstance(it, dict):
                continue
            try:
                x, y = float(it.get("x_m", 0.0)), float(it.get("y_m", 0.0))
            except (TypeError, ValueError):
                continue
            if x != x or y != y:
                continue
            ctx["people"].append({"x_m": _clamp(x, -150.0, 150.0),
                                  "y_m": _clamp(y, -150.0, 150.0)})
    out["context"] = ctx
    return out, warnings
