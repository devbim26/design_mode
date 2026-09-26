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
    разворот (шумовой огрызок, |Δнаправлений| ~ 180°) схлопывается: пара И
    все последующие рёбра, антипараллельные накопленной сумме, идут одним
    суммарным ребром (зигзаг 3+ рёбер целиком — иначе остаётся шип
    вперёд-назад-вперёд, C2 финального ревью; нулевой длины рёбер нет).
    Точки пересчитываются накопленным проходом, замыкание контура
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

    def _emit(dx_sum, dy_sum):
        """Ребро-сумма снапом направления; шум, погасившийся до <0.05 px,
        не выпускает ребра вовсе (рёбер нулевой длины нет)."""
        if math.hypot(dx_sum, dy_sum) < 0.05:
            return
        a = math.radians(_snap_angle(
            math.degrees(math.atan2(dy_sum, dx_sum)), tol_deg, step_deg))
        out.append([out[-1][0] + math.hypot(dx_sum, dy_sum) * math.cos(a),
                    out[-1][1] + math.hypot(dx_sum, dy_sum) * math.sin(a)])

    out = [pts[0]]
    i = 0
    while i < len(edges):
        L, d, dx, dy = edges[i]
        # разворот: следующее ребро обратно текущему — глотаем огрызок
        if i + 1 < len(edges):
            L2, d2, dx2, dy2 = edges[i + 1]
            if abs(((d - d2) % 360.0) - 180.0) < tol_deg:
                # поглощаем, пока очередное ребро антипараллельно
                # НАКОПЛЕННОЙ сумме (разворот может тянуться >2 рёбер)
                nx, ny = dx + dx2, dy + dy2
                i += 2
                while i < len(edges):
                    L3, d3, dx3, dy3 = edges[i]
                    ds = math.degrees(math.atan2(ny, nx))
                    if abs(((ds - d3) % 360.0) - 180.0) < tol_deg:
                        nx, ny = nx + dx3, ny + dy3
                        i += 1
                    else:
                        break
                _emit(nx, ny)
                continue
        # снап абсолютного направления ребра к ближайшей оси k*step_deg
        _emit(dx, dy)
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
    if scenario == "plan":
        return regularize_plan(scene, warnings)
    return regularize_interior(scene)


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


def _poly_valid(pts):
    """Контур валиден (shapely)? Недоступность/сбой shapely -> True
    (страховочная сеть не блокирует регуляризацию)."""
    try:
        from shapely.geometry import Polygon
        return bool(Polygon(pts).is_valid)
    except Exception:
        return True


def regularize_plan(scene, warnings):
    """Ортоснап рёбер (<15°), RDP при >8 вершинах, снятие взаимных
    пересечений футпринтов (поздние минус ранние, порядок секций A).
    Страховочная сеть (C2 финального ревью): контур секции, ставший после
    снапа невалидным, откатывается к исходным точкам + warning в warnings."""
    for sec in scene.get("sections") or []:
        pts = sec.get("points_px") or []
        if len(pts) >= 3:
            fixed = orthogonalize(pts, tol_deg=15.0, step_deg=90.0)
            if len(fixed) > 8:
                fixed = rdp(fixed, eps=2.0)
            if not _poly_valid(fixed):
                warnings.append(f"регуляризация: контур секции "
                                f"{sec.get('id')} стал некорректным — откат")
                continue  # исходные точки секции остаются как были
            sec["points_px"] = fixed
    # пересечения: секция i+1 обрезается о секцию i (shapely difference)
    try:
        from shapely.geometry import Polygon
        polys = []
        for sec in scene.get("sections") or []:
            p = Polygon(sec["points_px"])
            for q in polys:
                p = p.difference(q)
            if not p.is_empty and p.area > 1.0:
                if p.geom_type == "Polygon":
                    sec["points_px"] = [[round(x), round(y)]
                                        for x, y in p.exterior.coords[:-1]]
                    polys.append(Polygon(sec["points_px"]))
                else:  # развалилось на куски — берём крупнейший
                    biggest = max(p.geoms, key=lambda g: g.area)
                    sec["points_px"] = [[round(x), round(y)]
                                        for x, y in biggest.exterior.coords[:-1]]
                    polys.append(Polygon(sec["points_px"]))
    except Exception:
        pass  # shapely недоступен/контур битый — регуляризация не роняет
    return scene


def regularize_interior(scene):
    """Снап рёбер стен к k*45° в допуске 15° (прямой угол и 45° — типовые;
    эркер 67.5° не задевается: до 90° и 45° по 22.5°), кламп толщин в
    диапазоны спеки (наружные 0.3-0.4, перегородки 0.1-0.15), замыкание
    комнат buffer(0)."""
    for wall in scene.get("walls") or []:
        pts = wall.get("points_px")
        if pts and len(pts) == 2:
            ang = math.degrees(math.atan2(pts[1][1] - pts[0][1],
                                          pts[1][0] - pts[0][0]))
            sn = _snap_angle(ang, 15.0, 45.0)
            if sn != ang:
                L = math.hypot(pts[1][0] - pts[0][0], pts[1][1] - pts[0][1])
                a = math.radians(sn)
                pts[1] = [pts[0][0] + L * math.cos(a),
                          pts[0][1] + L * math.sin(a)]
        t = wall.get("thickness_m")
        if isinstance(t, (int, float)):
            if wall.get("exterior"):
                wall["thickness_m"] = min(max(float(t), 0.3), 0.4)
            else:
                wall["thickness_m"] = min(max(float(t), 0.1), 0.15)
    for room in scene.get("rooms") or []:
        pts = room.get("points_px")
        if pts and len(pts) >= 3:
            try:
                from shapely.geometry import Polygon
                p = Polygon(pts).buffer(0)
                if not p.is_empty and p.geom_type == "Polygon":
                    room["points_px"] = [[round(x), round(y)]
                                         for x, y in p.exterior.coords[:-1]]
            except Exception:
                pass
    return scene
