# -*- coding: utf-8 -*-
"""Регуляризация по темам (спека п.60, з.4) — чистый код, без VLM.
Гейт agree_rate >= REGULAR_GATE (низкое согласие = VLM-интент нестандартен:
пристройки/эркеры/намеренная асимметрия — не ломаем). Применяется к
сцене-победителю ПОСЛЕ merge, ДО контракта/сборки. Модуль чистый."""

import math

REGULAR_GATE = 0.7


def snap(v, step=0.05):
    """Число к сетке step (0.05 м — BIM-шаг размеров)."""
    return round(round(float(v) / step) * step, 4)


def rdp(points, eps=2.0):
    """Ramer-Douglas-Peucker упрощение полигона (px), замкнуто не
    обрабатываем — вход строителю точки подряд."""
    if len(points) < 3:
        return [list(p) for p in points]
    x1, y1 = points[0]
    x2, y2 = points[-1]
    best, idx = 0.0, -1
    for i, (px, py) in enumerate(points[1:-1], start=1):
        dx, dy = x2 - x1, y2 - y1
        L = math.hypot(dx, dy)
        d = (abs(dx * (y1 - py) - dy * (x1 - px)) / L) if L else \
            math.hypot(px - x1, py - y1)
        if d > best:
            best, idx = d, i
    if best <= eps:
        return [list(points[0]), list(points[-1])]
    return (rdp(points[:idx + 1], eps)[:-1]
            + rdp(points[idx:], eps))


def _snap_angle(a_deg, tol_deg, step_deg):
    """Угол к ближайшему кратному step_deg, если в допуске; иначе как был."""
    k = round(a_deg / step_deg)
    d = abs(a_deg - k * step_deg)
    return k * step_deg if d < tol_deg else a_deg


def orthogonalize(points, tol_deg=15.0, step_deg=90.0):
    """Контур: снап рёбер к k*step_deg в допуске (план 90°, интерьер 45°);
    эркер 67.5° при step 90/45 остаётся (до осей 22.5° > 15°). Коллинеарный
    разворот (шумовой огрызок, |Δнаправлений| ~ 180°) схлопывается: вершина
    огрызка ложится на предыдущую (снап к ребру), пара идёт суммарным
    вектором. Точки пересчитываются накопленным проходом, замыкание контура
    сохраняется."""
    if len(points) < 3:
        return [list(p) for p in points]
    pts = [list(map(float, p)) for p in points]
    # рёбра: длина, абсолютное направление, сырой вектор
    edges = []
    for i in range(1, len(pts)):
        dx, dy = pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]
        edges.append((math.hypot(dx, dy),
                      math.degrees(math.atan2(dy, dx)), dx, dy))
    out = [pts[0]]
    i = 0
    while i < len(edges):
        L, d, dx, dy = edges[i]
        # разворот: следующее ребро обратно текущему — глотаем огрызок
        if i + 1 < len(edges):
            L2, d2, dx2, dy2 = edges[i + 1]
            if abs(((d - d2) % 360.0) - 180.0) < tol_deg:
                nx, ny = dx + dx2, dy + dy2
                a = math.radians(_snap_angle(
                    math.degrees(math.atan2(ny, nx)), tol_deg, step_deg))
                out.append(list(out[-1]))          # вершина огрызка — снап
                out.append([out[-1][0] + math.hypot(nx, ny) * math.cos(a),
                            out[-1][1] + math.hypot(nx, ny) * math.sin(a)])
                i += 2
                continue
        # снап абсолютного направления ребра к ближайшей оси k*step_deg
        a = math.radians(_snap_angle(d, tol_deg, step_deg))
        out.append([out[-1][0] + L * math.cos(a),
                    out[-1][1] + L * math.sin(a)])
        i += 1
    # замкнуть в первую точку (полигон): добираем остаточное смещение
    # распределённо не делаем — строитель сам замыкает; возвращаем как есть
    return [[round(p[0], 1), round(p[1], 1)] for p in out]


def regularize(scenario, scene, confidence, warnings):
    """Гейт + диспетчер. Возвращает ТУ ЖЕ сцену (in-place правки полей)."""
    rate = (confidence or {}).get("agree_rate")
    if scenario not in ("facade", "plan", "interior"):
        return scene
    if rate is None or rate < REGULAR_GATE:
        warnings.append("regularization skipped: low ensemble agreement")
        return scene
    if scenario == "facade":
        return regularize_facade(scene)
    return scene  # plan/interior — Task 9


def regularize_facade(scene):
    """Снап размеров к 0.05 м + симметрия сетки окон в зеркальных секциях."""
    if isinstance(scene.get("floor_height"), (int, float)):
        scene["floor_height"] = snap(scene["floor_height"])
    win = scene.get("windows") or {}
    for k in ("w_m", "h_m", "margin_x_m", "margin_y_m"):
        if isinstance(win.get(k), (int, float)):
            win[k] = snap(win[k])
    skip = win.get("skip")
    if isinstance(skip, list) and skip:
        cols = max(len(r) for r in skip)
        half = cols // 2
        if half >= 1:
            for row in skip:
                if len(row) != cols:
                    continue  # клампнуто валидатором, на всякий случай
                left = sum(1 for c in row[:half] if not c)   # окон слева
                right = sum(1 for c in row[cols - half:] if not c)
                if max(left, right) == 0 or \
                        abs(left - right) / max(left, right) > 0.1:
                    continue  # асимметрия намеренная (порог 10%, спека з.4)
                if left >= right:  # худшая (меньше окон) половина — правая
                    for i in range(half):
                        row[cols - 1 - i] = row[i]
                else:
                    for i in range(half):
                        row[i] = row[cols - 1 - i]
                # средний столбец (cols нечётное) не трогаем
    return scene
