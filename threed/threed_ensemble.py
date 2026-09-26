# -*- coding: utf-8 -*-
"""Ансамбль двух извлечений (спека п.60, з.3): детерминированное сравнение
валидированных сцен A и B; слияние согласованного (float — среднее);
спорное — ОДИН реферти-вызов (картинка + оба варианта спорных полей);
сбой/неуверенность реферти -> вариант A + warning. Модуль чистый.

Сравнение фасада (7 полей, пороги спеки): storeys d>=1; width_m d>15%;
floor_height d>10%; windows.rows / windows.cols — несовпадение;
windows.skip — d>=2 клеток; entrance — 0/1 (d>=1)."""

import copy

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
    """Валидированные A/B -> {agreed, disputed, metrics, agree_rate}.
    plan/interior — Task 9 (до него сравнение этих тем = полное согласие
    по нулевому набору полей, ensemble их не включает)."""
    if scenario == "facade":
        return _compare_facade(A, B)
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


def merge_scenes(scenario, A, B, cmp, referee=None):
    """Слияние: base = deepcopy(A); согласованные float — среднее; спорные —
    по вердикту реферти (referee(list_fields) -> {"choices": ...} | None),
    неспособный/молчащий реферти -> A + warning. Возвращает (scene,
    confidence, warnings). План/интерьер (Task 9) — компонентное слияние,
    до него проходят base=A."""
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
    confidence = {"agree_rate": cmp.get("agree_rate", 1.0),
                  "disputed_fields": sorted(disputed),
                  "referee_used": bool(choices)}
    return scene, confidence, warnings
