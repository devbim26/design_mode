# -*- coding: utf-8 -*-
"""Ансамбль двух извлечений (спека п.60, з.3): детерминированное сравнение
валидированных сцен A и B; слияние согласованного (float — среднее);
спорное — ОДИН реферти-вызов (картинка + оба варианта спорных полей);
сбой/неуверенность реферти -> вариант A + warning. Модуль чистый.

Сравнение фасада (7 полей, пороги спеки): storeys d>=1; width_m d>15%;
floor_height d>10%; windows.rows / windows.cols — несовпадение;
windows.skip — d>=2 клеток; entrance — 0/1 (d>=1)."""

import copy
import math

SYSTEM_REFEREE = """You are a geometry referee. The attached image was analyzed
by two independent extraction passes (A and B); they disagree on a few fields.
For EACH field pick the value that better matches the image. Reply with STRICT
JSON ONLY - no fences, no extra keys:
{"choices": {"<field>": "A" | "B", ...}}

Rules:
- Judge ONLY the listed fields; do not invent new ones.
- If unsure, pick "A" (the primary pass).
"""


def _get(obj, path):
    for k in path.split("."):
        if not isinstance(obj, dict) or k not in obj:
            return None
        obj = obj[k]
    return obj


def _set(obj, path, val):
    keys = path.split(".")
    for k in keys[:-1]:
        obj = obj.setdefault(k, {})
    obj[keys[-1]] = val


def _pct(a, b):
    return abs(a - b) / max(abs(a), abs(b), 1e-9)


def _skip_diff(a, b):
    if not isinstance(a, list) or not isinstance(b, list):
        return 99
    flat_a = [c for row in a for c in row]
    flat_b = [c for row in b for c in row]
    if len(flat_a) != len(flat_b):
        return 99
    return sum(1 for x, y in zip(flat_a, flat_b) if bool(x) != bool(y))


# фасад: (поле, путь|getter, вид сравнения, порог)
_FACADE_FIELDS = (
    ("storeys", "storeys", "int", 1),
    ("width_m", "width_m", "pct", 0.15),
    ("floor_height", "floor_height", "pct", 0.10),
    ("windows.rows", "windows.rows", "int", 1),
    ("windows.cols", "windows.cols", "int", 1),
    ("windows.skip", "windows.skip", "skip", 2),
    ("entrance", "entrance", "flag", 1),
)


def compare_scenes(scenario, A, B):
    """Валидированные A/B -> {agreed, disputed, metrics, agree_rate}."""
    if scenario == "facade":
        return _compare_facade(A, B)
    if scenario == "plan":
        return _compare_plan(A, B)
    if scenario == "interior":
        return _compare_interior(A, B)
    return {"agreed": [], "disputed": {}, "metrics": {},
            "agree_rate": 1.0}


def _compare_facade(A, B):
    agreed, disputed, metrics = [], {}, {}
    for field, path, kind, thresh in _FACADE_FIELDS:
        a, b = _get(A, path), _get(B, path)
        if kind == "flag":
            a_n, b_n = 1 if a else 0, 1 if b else 0
            diff = abs(a_n - b_n)
            metrics[field] = (a_n, b_n)
            if diff >= thresh:
                disputed[field] = (a_n, b_n)
            else:
                agreed.append(field)
            continue
        if a is None or b is None:
            metrics[field] = {"a": a, "b": b}
            agreed.append(field)  # нет значения у B — не спор, A прав
            continue
        if kind == "int":
            diff = abs(float(a) - float(b))
        elif kind == "skip":
            diff = _skip_diff(a, b)
        else:
            diff = _pct(float(a), float(b))
            metrics[path.replace(".", "_") + "_pct"] = round(diff, 4)
        # int/skip — спор при d>=порога (storeys d>=1, skip d>=2 клеток);
        # pct — строго d>порога (width d>15%, floor_height d>10%)
        if diff >= thresh if kind in ("int", "skip") else diff > thresh:
            disputed[field] = (a, b)
        else:
            agreed.append(field)
    total = len(agreed) + len(disputed)
    return {"agreed": agreed, "disputed": disputed, "metrics": metrics,
            "agree_rate": round(len(agreed) / total, 3) if total else 1.0}


def _poly_iou(pa, pb):
    """IoU полигонов px (shapely); 0.0 при невалидных."""
    try:
        from shapely.geometry import Polygon
        a, b = Polygon(pa), Polygon(pb)
        if not a.is_valid or not b.is_valid or a.area + b.area <= 0:
            return 0.0
        return a.intersection(b).area / a.union(b).area
    except Exception:
        return 0.0


def _match_sections(A, B):
    """Секции A/B -> список (i, j, iou) жадно по лучшему IoU."""
    out = []
    used = set()
    for i, sa in enumerate(A["sections"]):
        best, bj = 0.0, -1
        for j, sb in enumerate(B["sections"]):
            if j in used:
                continue
            iou = _poly_iou(sa["points_px"], sb["points_px"])
            if iou > best:
                best, bj = iou, j
        if bj >= 0:
            used.add(bj)
            out.append((i, bj, best))
    return out


def _compare_plan(A, B):
    agreed, disputed, metrics = [], {}, {}
    matched = _match_sections(A, B)
    iou_by_a = {i: iou for i, j, iou in matched}
    # несопоставленная секция A = IoU 0 (спор футпринта), не «согласие»
    min_iou = min((iou_by_a.get(i, 0.0)
                   for i in range(len(A["sections"]))), default=0.0)
    metrics["footprint_iou"] = round(min_iou, 4)
    if min_iou < 0.6:
        disputed["footprint_iou"] = (round(min_iou, 3), round(min_iou, 3))
    else:
        agreed.append("footprint_iou")
    na, nb = len(A["sections"]), len(B["sections"])
    metrics["sections_count"] = (na, nb)
    if abs(na - nb) >= 1:
        disputed["sections_count"] = (na, nb)
    else:
        agreed.append("sections_count")
    pairs = [(A["sections"][i]["floors"], B["sections"][j]["floors"])
             for i, j, _ in matched]
    dfloors = max((abs(a - b) for a, b in pairs), default=0)
    metrics["floors"] = dfloors
    if dfloors >= 1:
        disputed["floors"] = max(pairs, key=lambda p: abs(p[0] - p[1]))
    else:
        agreed.append("floors")
    wa = max(_bbox_wh(s["points_px"])[0] for s in A["sections"]) * \
        A["metres_per_trace_pixel"]
    wb = max(_bbox_wh(s["points_px"])[0] for s in B["sections"]) * \
        B["metres_per_trace_pixel"]
    metrics["width_m"] = (round(wa, 2), round(wb, 2))
    if _pct(wa, wb) > 0.20:
        disputed["width_m"] = (round(wa, 2), round(wb, 2))
    else:
        agreed.append("width_m")
    sa, sb = A["metres_per_trace_pixel"], B["metres_per_trace_pixel"]
    metrics["scale_pct"] = round(_pct(sa, sb), 4)
    if _pct(sa, sb) > 0.15:
        disputed["scale"] = (sa, sb)
    else:
        agreed.append("scale")
    total = len(agreed) + len(disputed)
    return {"agreed": agreed, "disputed": disputed, "metrics": metrics,
            "agree_rate": round(len(agreed) / total, 3) if total else 1.0}


def _bbox_wh(points):
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return max(xs) - min(xs), max(ys) - min(ys)


def _walls_len(s):
    import math
    return sum(math.hypot(w["points_px"][1][0] - w["points_px"][0][0],
                          w["points_px"][1][1] - w["points_px"][0][1])
               for w in s["walls"])


def _compare_interior(A, B):
    agreed, disputed, metrics = [], {}, {}
    la, lb = _walls_len(A), _walls_len(B)
    metrics["walls_len"] = (round(la), round(lb))
    if _pct(la, lb) > 0.15:
        disputed["walls_len"] = (round(la), round(lb))
    else:
        agreed.append("walls_len")
    for name, kind in (("rooms_count", "rooms"), ("doors_count", None),
                       ("windows_count", None)):
        if kind:
            va, vb = len(A[kind]), len(B[kind])
        else:
            k = "door" if "doors" in name else "window"
            va = sum(1 for o in A["openings"] if o["kind"] == k)
            vb = sum(1 for o in B["openings"] if o["kind"] == k)
        metrics[name] = (va, vb)
        if abs(va - vb) >= 1:
            disputed[name] = (va, vb)
        else:
            agreed.append(name)
    # rooms.wh: max Δ% габарита по matching-у комнат (близкие центры)
    worst = 0.0
    for ra in A["rooms"]:
        wa, ha = _bbox_wh(ra["points_px"])
        for rb in B["rooms"]:
            wb, hb = _bbox_wh(rb["points_px"])
            if abs(_cx(ra) - _cx(rb)) < 50 and abs(_cy(ra) - _cy(rb)) < 50:
                worst = max(worst, _pct(wa, wb), _pct(ha, hb))
    metrics["rooms_wh_pct"] = round(worst, 4)
    (disputed if worst > 0.15 else agreed).append("rooms.wh")
    total = len(agreed) + len(disputed)
    return {"agreed": agreed, "disputed": disputed, "metrics": metrics,
            "agree_rate": round(len(agreed) / total, 3) if total else 1.0}


def _cx(room):
    return sum(p[0] for p in room["points_px"]) / len(room["points_px"])


def _cy(room):
    return sum(p[1] for p in room["points_px"]) / len(room["points_px"])


def merge_scenes(scenario, A, B, cmp, referee=None):
    """Слияние: base = deepcopy(A); согласованные float — среднее; спорные —
    по вердикту реферти (referee(list_fields) -> {"choices": ...} | None),
    неспособный/молчащий реферти -> A + warning. Возвращает (scene,
    confidence, warnings). План/интерьер — компонентное слияние: секции
    (rooms+walls+outline) целиком из A|B по большинству голосов полей,
    scale/openings — точечно."""
    scene = copy.deepcopy(A)
    warnings = []
    disputed = cmp.get("disputed") or {}
    choices = {}
    if disputed and referee is not None:
        try:
            verdict = referee(sorted(disputed))
        except Exception as e:  # сеть/бюджет — не роняем слияние
            verdict = None
            warnings.append(f"ансамбль: реферти сбой ({e}) — спорные из A")
        if isinstance(verdict, dict):
            raw = verdict.get("choices")
            if isinstance(raw, dict):
                choices = {k: v for k, v in raw.items()
                           if k in disputed and v in ("A", "B")}
    # фасад: согласованные float осредняем, спорные точкично
    if scenario == "facade":
        for f in ("width_m", "floor_height"):
            if f in cmp.get("agreed", []):
                a, b = _get(scene, f), _get(B, f)
                if isinstance(a, (int, float)) and isinstance(b, (int, float)):
                    _set(scene, f, round((a + b) / 2, 3))
        for f, (a, b) in disputed.items():
            pick = choices.get(f)
            if pick == "B" and b is not None:
                _set(scene, f, copy.deepcopy(b))
            elif f not in choices:
                warnings.append(f"ансамбль: спор {f} не решён — вариант A")
    elif scenario == "plan":
        votes = [choices.get(f) for f in
                 ("sections_count", "footprint_iou", "floors", "width_m")]
        if votes.count("B") > votes.count("A"):
            scene["sections"] = copy.deepcopy(B["sections"])
        elif disputed:
            warnings.append("ансамбль: спор секций не решён — вариант A")
        if choices.get("scale") == "B":
            scene["metres_per_trace_pixel"] = B["metres_per_trace_pixel"]
    elif scenario == "interior":
        votes = [choices.get(f) for f in
                 ("rooms_count", "walls_len", "rooms.wh")]
        if votes.count("B") > votes.count("A"):
            for k in ("rooms", "walls", "outline"):
                scene[k] = copy.deepcopy(B[k])
        elif any(f in disputed for f in ("rooms_count", "walls_len",
                                         "rooms.wh")):
            warnings.append("ансамбль: спор комнат/стен не решён — вариант A")
        votes2 = [choices.get(f) for f in ("doors_count", "windows_count")]
        if votes2.count("B") > votes2.count("A"):
            scene["openings"] = copy.deepcopy(B["openings"])
    confidence = {"agree_rate": cmp.get("agree_rate", 1.0),
                  "disputed_fields": sorted(disputed),
                  "referee_used": bool(choices)}
    return scene, confidence, warnings
