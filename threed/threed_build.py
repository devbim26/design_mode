# -*- coding: utf-8 -*-
"""Сборка IFC4 «Генплан» по сцене-JSON (адаптация build_model.py скилла image-to-ifc).

Вход: scene (схема footprints: sections/context, пиксели + метры), PIL-картинка
исходника (после даунскейла), пути IFC и превью. Выход: путь к IFC.
"""
from collections import defaultdict
from pathlib import Path

import ifcopenshell
import ifcopenshell.api
from ifcopenshell.util.shape_builder import ShapeBuilder
import matplotlib
matplotlib.use("Agg")
import matplotlib.colors
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as PlotPolygon
import numpy as np
from PIL import Image
from shapely.geometry import Polygon
from shapely.geometry.polygon import orient

COLORS = {
    "Residential5": "#ded3b8", "Residential6": "#b6c7d3",
    "School": "#d68967", "Kindergarten": "#e5bd57",
    "Ground": "#c9d4b7", "Road": "#acafb3", "Parking": "#929ba5",
    "Sport": "#87ab6b", "Court": "#719eb3", "Play": "#d4ac9e",
}
USE_NAMES = {"Residential": "Жилой корпус", "School": "Школа", "Kindergarten": "Детский сад"}

ASSUMPTION = (
    "Концептуальная обводка кровель по растровой схеме (3D Design). Размеры, этажность "
    "секций и высоты оценочные. Геопривязка и ориентация на север отсутствуют. Не "
    "использовать как обмерную или рабочую документацию."
)


def _api(operation, **kwargs):
    return ifcopenshell.api.run(operation, **kwargs)


def _properties(model, product, name, values):
    pset = _api("pset.add_pset", file=model, product=product, name=name)
    _api("pset.edit_pset", file=model, pset=pset, properties=values)


def _metric_polygon(data, points):
    scale = data["metres_per_trace_pixel"]
    height = data["trace_height"]
    polygon = Polygon([(x * scale, (height - y) * scale) for x, y in points])
    if not polygon.is_valid or polygon.area <= 0:
        raise ValueError(f"Некорректный контур: {points}")
    return orient(polygon, sign=1.0)


def build_genplan(scene, image, ifc_path, preview_path, meta):
    """scene: dict схемы; image: PIL (уже ≤1536 px, белый фон); meta: pset DevBIM."""
    data = dict(scene)  # не мутировать вход
    data.setdefault("project_name", "3D Design — генплан")
    data.setdefault("site_name", "Участок")
    model = _api("project.create_file", version="IFC4")
    project = _api("root.create_entity", file=model, ifc_class="IfcProject",
                   name=data.get("project_name"))
    project.Description = ASSUMPTION
    units = [_api("unit.add_si_unit", file=model, unit_type=t)
             for t in ("LENGTHUNIT", "AREAUNIT", "VOLUMEUNIT")]
    _api("unit.assign_unit", file=model, units=units)
    context = _api("context.add_context", file=model, context_type="Model")
    body = _api("context.add_context", file=model, context_type="Model",
                context_identifier="Body", target_view="MODEL_VIEW", parent=context)
    site = _api("root.create_entity", file=model, ifc_class="IfcSite", name=data.get("site_name"))
    _api("aggregate.assign_object", file=model, products=[site], relating_object=project)
    _api("geometry.edit_object_placement", file=model, product=site, matrix=np.eye(4))
    _properties(model, project, "DevBIM", {
        "Source": meta.get("Source", "3D Design"), "Scenario": meta.get("Scenario", "plan"),
        "Prompt": (meta.get("Prompt") or "")[:1024], "Model": meta.get("Model", ""),
        "ApproximateGeometry": True, "Notes": ASSUMPTION,
    })
    _properties(model, site, "SourceAndAssumptions", {
        "SourceImage": meta.get("SourceImage", "canvas/viewer"),
        "GeometryStatus": "CONCEPTUAL / APPROXIMATE",
        "MetresPerTracePixel": data["metres_per_trace_pixel"],
        "TraceWidth": data["trace_width"], "TraceHeight": data["trace_height"],
        "Georeferenced": False, "NorthKnown": False, "Notes": ASSUMPTION,
    })
    styles = {}
    for key, color in COLORS.items():
        r, g, b = matplotlib.colors.to_rgb(color)
        style = _api("style.add_style", file=model, name=key)
        _api("style.add_surface_style", file=model, style=style,
             ifc_class="IfcSurfaceStyleShading",
             attributes={"SurfaceColour": {"Name": key, "Red": r, "Green": g, "Blue": b},
                         "Transparency": 0.0})
        styles[key] = style

    def mass(name, polygon, z, depth, container, color_key,
             ifc_class="IfcBuildingElementProxy", object_type="CONCEPTUAL_MASS"):
        product = _api("root.create_entity", file=model, ifc_class=ifc_class,
                       predefined_type="USERDEFINED", name=name)
        product.ObjectType = object_type
        xy = np.array(polygon.exterior.coords, dtype=float)
        origin = np.array(polygon.centroid.coords[0])
        profile = _api("profile.add_arbitrary_profile", file=model,
                       profile=(xy - origin).tolist(), name=name)
        representation = _api("geometry.add_profile_representation", file=model, context=body,
                              profile=profile, depth=depth, cardinal_point=None)
        _api("geometry.assign_representation", file=model, product=product,
             representation=representation)
        _api("spatial.assign_container", file=model, products=[product],
             relating_structure=container)
        matrix = np.eye(4)
        matrix[:3, 3] = [float(origin[0]), float(origin[1]), float(z)]
        _api("geometry.edit_object_placement", file=model, product=product, matrix=matrix)
        _api("style.assign_representation_styles", file=model, shape_representation=representation,
             styles=[styles[color_key]])
        return product

    groups = defaultdict(list)
    for section in data["sections"]:
        groups[section["building"]].append(section)
    for building_id, sections in groups.items():
        use = sections[0].get("use", "Residential")
        public = use != "Residential"
        floor_height = data["public_storey_height" if public else "residential_storey_height"]
        floors = max(s["floors"] for s in sections)
        name = f"{USE_NAMES.get(use, use)} {building_id}"
        if any(s.get("partial") for s in sections):
            name += " (видимый фрагмент)"
        building = _api("root.create_entity", file=model, ifc_class="IfcBuilding", name=name)
        building.Description = ASSUMPTION
        _api("aggregate.assign_object", file=model, products=[building], relating_object=site)
        _api("geometry.edit_object_placement", file=model, product=building, matrix=np.eye(4))
        _properties(model, building, "SiteMassing", {
            "BuildingId": building_id, "Use": use, "ApproximateGeometry": True,
            "NumberOfStoreys": floors, "MaximumHeight": floors * floor_height,
            "StoreyHeight": floor_height, "Source": "3D Design", "Notes": ASSUMPTION,
        })
        storeys = []
        for floor in range(floors):
            storey = _api("root.create_entity", file=model, ifc_class="IfcBuildingStorey",
                          name=f"{building_id} — этаж {floor + 1:02d}")
            storey.Elevation = floor * floor_height
            _api("aggregate.assign_object", file=model, products=[storey], relating_object=building)
            matrix = np.eye(4)
            matrix[2, 3] = storey.Elevation
            _api("geometry.edit_object_placement", file=model, product=storey, matrix=matrix)
            storeys.append(storey)
        for section in sections:
            polygon = _metric_polygon(data, section["points_px"])
            color_key = use if public else f"Residential{section['floors']}"
            if color_key not in styles:  # этажность без своего цвета -> ближайший
                color_key = "Residential5" if section["floors"] < 6 else "Residential6"
            for floor in range(section["floors"]):
                z = floor * floor_height
                product = mass(f"{USE_NAMES.get(use, use)} {section['id']} / этаж {floor + 1}",
                               polygon, z, floor_height, storeys[floor], color_key)
                _properties(model, product, "MassingElement", {
                    "Section": section["id"], "Use": use, "Storey": floor + 1,
                    "SectionStoreys": section["floors"], "StoreyHeight": floor_height,
                    "BaseElevation": z, "FootprintArea": polygon.area,
                    "ApproximateGeometry": True,
                    "PartialAtImageBoundary": bool(section.get("partial", False)),
                })
                qto = _api("pset.add_qto", file=model, product=product,
                           name="Qto_BuildingElementProxyQuantities")
                _api("pset.edit_qto", file=model, qto=qto, properties={
                    "NetSurfaceArea": float(polygon.area),
                    "NetVolume": float(polygon.area * floor_height)})
    for item in data.get("context", []):
        product = mass(item.get("name", item["kind"]), _metric_polygon(data, item["points_px"]),
                       item.get("z", -0.45), item.get("depth", 0.35), site, item["kind"],
                       ifc_class="IfcGeographicElement", object_type="SITE_SURFACE")
        _properties(model, product, "SiteContext",
                    {"Use": item["kind"], "ApproximateGeometry": True})

    model.header.file_name.name = ifc_path.name
    model.header.file_name.author = ("3D Design",)
    model.header.file_name.organization = ("DevBIM",)
    model.header.file_name.preprocessor_version = f"IfcOpenShell {ifcopenshell.version}"
    model.header.file_name.originating_system = "DevBIM 3D Design (VLM scene -> IFC)"
    model.header.file_name.authorization = "Approximate model; not construction documentation"
    ifc_path.parent.mkdir(parents=True, exist_ok=True)
    model.write(str(ifc_path))
    _draw_overlay(data, image, preview_path)
    return ifc_path


def _draw_overlay(data, image, preview_path):
    """Обводки + этажность поверх исходной картинки (как _footprints.png скилла)."""
    fig, ax = plt.subplots(figsize=(18, 10.125), facecolor="white")
    ax.imshow(image, extent=(0, data["trace_width"], data["trace_height"], 0))
    for section in data["sections"]:
        use = section.get("use", "Residential")
        key = use if use != "Residential" else f"Residential{section['floors']}"
        if key not in COLORS:
            key = "Residential5"
        ax.add_patch(PlotPolygon(section["points_px"], facecolor=COLORS[key],
                                 edgecolor="#263747", alpha=.78, linewidth=1.1))
        pt = Polygon(section["points_px"]).representative_point()
        ax.text(pt.x, pt.y, f"{section['id']}\n{section['floors']} эт.", ha="center",
                va="center", fontsize=6.5, color="#15232e", fontweight="bold",
                bbox=dict(facecolor="white", alpha=.65, pad=1, edgecolor="none"))
    ax.set_xlim(0, data["trace_width"])
    ax.set_ylim(data["trace_height"], 0)
    ax.axis("off")
    ax.set_title("3D Design — обводка зданий и этажность (контуры и масштаб оценочные)",
                 fontsize=14)
    fig.tight_layout()
    preview_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(preview_path, dpi=160, facecolor="white")
    plt.close(fig)


# ===================== Фаза 2: сценарий «Фасад» =====================

ASSUMPTION_FACADE = (
    "Концептуальная модель по изображению фасада (3D Design). Перспектива принята "
    "за ортогональную, глубина здания и толщины оценочные. Окна и балконы — схематичные "
    "объёмы. Не использовать как обмерную или рабочую документацию."
)

FACADE_DEFAULT_COLORS = {
    "walls": "#c8b89a", "roof": "#52616b", "plinth": "#8d8d8d",
    "glazing": "#202830", "balcony": "#9aa3ad",
}


def _write_header(model, ifc_path):
    """Шапка STEP-файла (как у genplan; вынесено для build_facade)."""
    model.header.file_name.name = ifc_path.name
    model.header.file_name.author = ("3D Design",)
    model.header.file_name.organization = ("DevBIM",)
    model.header.file_name.preprocessor_version = f"IfcOpenShell {ifcopenshell.version}"
    model.header.file_name.originating_system = "DevBIM 3D Design (VLM scene -> IFC)"
    model.header.file_name.authorization = "Approximate model; not construction documentation"


def _facade_grid(data):
    """Левые края окон по X (метры, от -w/2) и по Z внутри этажа; одинаково для всех этажей."""
    win, w, fh = data["windows"], data["width_m"], data["floor_height"]
    usable_w = w - 2 * win["margin_x_m"]
    gap_x = (usable_w - win["cols"] * win["w_m"]) / (win["cols"] - 1) \
        if win["cols"] > 1 else 0.0
    xs = [-w / 2 + win["margin_x_m"] + i * (win["w_m"] + max(gap_x, 0.0))
          for i in range(win["cols"])]
    usable_h = fh - 2 * win["margin_y_m"]
    gap_y = (usable_h - win["rows"] * win["h_m"]) / (win["rows"] - 1) \
        if win["rows"] > 1 else 0.0
    zs = [win["margin_y_m"] + j * (win["h_m"] + max(gap_y, 0.0))
          for j in range(win["rows"])]
    return xs, zs


def _window_skip(data):
    """skip[j][i] (True = окна нет); нормализован validate_facade до rows×cols."""
    return data["windows"].get("skip") or []


def _hull(points):
    """Точки xyz -> (points, faces) выпуклой оболочки; faces = plain int."""
    from scipy.spatial import ConvexHull
    faces = [list(map(int, s)) for s in ConvexHull(np.array(points, dtype=float)).simplices]
    return points, faces


def _ring(radius, z, nseg=16):
    """Кольцо точек [[x, y, z], ...] — цилиндры/конусы для мешей."""
    ang = np.linspace(0.0, 2.0 * np.pi, nseg, endpoint=False)
    return [[float(radius * np.cos(a)), float(radius * np.sin(a)), float(z)]
            for a in ang]


def _ensure_style(model, fstyles, key, hex_color):
    """Стиль по требованию (custom hex из custom_parts)."""
    if key in fstyles:
        return key
    style = _api("style.add_style", file=model, name=key)
    r, g, b = matplotlib.colors.to_rgb(hex_color)
    _api("style.add_surface_style", file=model, style=style,
         ifc_class="IfcSurfaceStyleShading",
         attributes={"SurfaceColour": {"Name": key, "Red": r, "Green": g, "Blue": b},
                     "Transparency": 0.0})
    fstyles[key] = style
    return key


def _mesh_product(model, body, sb, name, points, faces, container, object_type,
                  fstyles, color_key, matrix=np.eye(4)):
    """Меш -> IfcBuildingElementProxy (IfcPolygonalFaceSet) со стилем."""
    item = sb.mesh(points=[[float(c) for c in p] for p in points], faces=faces)
    rep = sb.get_representation(body, [item])
    product = _api("root.create_entity", file=model, ifc_class="IfcBuildingElementProxy",
                   predefined_type="USERDEFINED", name=name)
    product.ObjectType = object_type
    _api("geometry.assign_representation", file=model, product=product, representation=rep)
    _api("spatial.assign_container", file=model, products=[product],
         relating_structure=container)
    _api("geometry.edit_object_placement", file=model, product=product,
         matrix=np.asarray(matrix, dtype=float))
    _api("style.assign_representation_styles", file=model,
         shape_representation=rep, styles=[fstyles[color_key]])
    return product


def build_facade(scene, ifc_path, preview_path, meta):
    """Сцена-метрики фасада -> IFC4 + PNG-чертёж фасада. Возвращает ifc_path."""
    data = dict(scene)
    data.setdefault("storeys", 5)
    data.setdefault("floor_height", 3.0)
    data.setdefault("width_m", 18.0)
    data.setdefault("depth_m", 12.0)
    data.setdefault("roof", "flat")
    data.setdefault("roof_height", 2.5)
    data.setdefault("windows", {})
    data.setdefault("balconies", [])
    win = {"rows": 1, "cols": 3, "w_m": 1.5, "h_m": 1.5,
           "margin_x_m": 1.0, "margin_y_m": 0.8}
    win.update({k: v for k, v in (data["windows"] or {}).items() if k != "skip"})
    win["skip"] = (data["windows"] or {}).get("skip") or []
    data["windows"] = win
    colors = dict(FACADE_DEFAULT_COLORS)
    colors.update({k: v for k, v in (scene.get("colors") or {}).items() if k in colors})

    model = _api("project.create_file", version="IFC4")
    project = _api("root.create_entity", file=model, ifc_class="IfcProject",
                   name=data.get("project_name", "3D Design — фасад"))
    project.Description = ASSUMPTION_FACADE
    units = [_api("unit.add_si_unit", file=model, unit_type=t)
             for t in ("LENGTHUNIT", "AREAUNIT", "VOLUMEUNIT")]
    _api("unit.assign_unit", file=model, units=units)
    context = _api("context.add_context", file=model, context_type="Model")
    body = _api("context.add_context", file=model, context_type="Model",
                context_identifier="Body", target_view="MODEL_VIEW", parent=context)
    site = _api("root.create_entity", file=model, ifc_class="IfcSite", name="Участок")
    _api("aggregate.assign_object", file=model, products=[site], relating_object=project)
    _api("geometry.edit_object_placement", file=model, product=site, matrix=np.eye(4))
    _properties(model, project, "DevBIM", {
        "Source": meta.get("Source", "3D Design"), "Scenario": meta.get("Scenario", "facade"),
        "Prompt": (meta.get("Prompt") or "")[:1024], "Model": meta.get("Model", ""),
        "ApproximateGeometry": True, "Notes": ASSUMPTION_FACADE,
    })
    building = _api("root.create_entity", file=model, ifc_class="IfcBuilding",
                    name=data.get("building_name", "Здание по фасаду"))
    building.Description = ASSUMPTION_FACADE
    _api("aggregate.assign_object", file=model, products=[building], relating_object=site)
    _api("geometry.edit_object_placement", file=model, product=building, matrix=np.eye(4))

    fstyles = {}
    for key, color in colors.items():
        r, g, b = matplotlib.colors.to_rgb(color)
        style = _api("style.add_style", file=model, name=f"Facade{key.capitalize()}")
        _api("style.add_surface_style", file=model, style=style,
             ifc_class="IfcSurfaceStyleShading",
             attributes={"SurfaceColour": {"Name": key, "Red": r, "Green": g, "Blue": b},
                         "Transparency": 0.0})
        fstyles[key] = style

    w, d, fh, n = data["width_m"], data["depth_m"], data["floor_height"], data["storeys"]

    def box(name, bw, bd, bh, cx, cy, z, color_key, container,
            object_type="CONCEPTUAL_MASS", rot_deg=0.0):
        product = _api("root.create_entity", file=model, ifc_class="IfcBuildingElementProxy",
                       predefined_type="USERDEFINED", name=name)
        product.ObjectType = object_type
        pts = [[-bw / 2, -bd / 2], [bw / 2, -bd / 2], [bw / 2, bd / 2], [-bw / 2, bd / 2]]
        profile = _api("profile.add_arbitrary_profile", file=model, profile=pts, name=name)
        representation = _api("geometry.add_profile_representation", file=model, context=body,
                              profile=profile, depth=bh, cardinal_point=None)
        _api("geometry.assign_representation", file=model, product=product,
              representation=representation)
        _api("spatial.assign_container", file=model, products=[product],
             relating_structure=container)
        matrix = np.eye(4)
        yaw = np.radians(rot_deg)
        matrix[:2, :2] = [[np.cos(yaw), -np.sin(yaw)], [np.sin(yaw), np.cos(yaw)]]
        matrix[:3, 3] = [float(cx), float(cy), float(z)]
        _api("geometry.edit_object_placement", file=model, product=product, matrix=matrix)
        _api("style.assign_representation_styles", file=model,
             shape_representation=representation, styles=[fstyles[color_key]])
        return product

    storeys = []
    for f in range(n):
        storey = _api("root.create_entity", file=model, ifc_class="IfcBuildingStorey",
                      name=f"Этаж {f + 1:02d}")
        storey.Elevation = f * fh
        _api("aggregate.assign_object", file=model, products=[storey], relating_object=building)
        matrix = np.eye(4)
        matrix[2, 3] = storey.Elevation
        _api("geometry.edit_object_placement", file=model, product=storey, matrix=matrix)
        storeys.append(storey)

    windows_total = 0
    xs, zs = _facade_grid(data)
    skip = _window_skip(data)
    for f in range(n):
        box(f"Стены · этаж {f + 1}", w, d, fh, 0.0, 0.0, f * fh, "walls", storeys[f],
            object_type="CONCEPTUAL_STOREY")
        for j, z_in in enumerate(zs):
            for i, x in enumerate(xs):
                if j < len(skip) and i < len(skip[j]) and skip[j][i]:
                    continue
                box(f"Окно Э{f + 1}-{i + 1}", win["w_m"], 0.12, win["h_m"],
                    # центр по Y = -d/2: фасад на IFC -Y (после трансформа
                    # вьювера -> world +Z, дефолтная камера видит окна);
                    # передняя грань на 0.06 м перед фасадом — иначе луч
                    # выбора упирается в стену заподлицо и окно не кликается
                    x + win["w_m"] / 2, -d / 2, f * fh + z_in, "glazing",
                    storeys[f], object_type="CONCEPTUAL_WINDOW")
                windows_total += 1
    for b_idx, bal in enumerate(data["balconies"], start=1):
        # пол балкона = уровень пола его этажа (k-1)*fh: plate толщиной 0.18
        # верхом вровень с полом (box экструдирует вверх от z)
        bal_z = (bal["floor"] - 1) * fh - 0.18
        box(f"Балкон {b_idx} · этаж {bal['floor']}", bal["w_m"], bal["d_m"], 0.18,
            bal["x_m"] - w / 2, -(d / 2 + bal["d_m"] / 2), bal_z, "balcony",
            storeys[bal["floor"] - 1], object_type="CONCEPTUAL_BALCONY")
    box("Цоколь", w + 0.2, d + 0.2, 0.6, 0.0, 0.0, 0.0, "plinth", building,
        object_type="CONCEPTUAL_PLINTH")
    top = n * fh
    if data["roof"] == "gable" and data["roof_height"] > 0.05:
        gable = _api("root.create_entity", file=model, ifc_class="IfcBuildingElementProxy",
                     predefined_type="USERDEFINED", name="Крыша двускатная")
        gable.ObjectType = "CONCEPTUAL_ROOF"
        pts = [[-w / 2, 0.0], [w / 2, 0.0], [0.0, data["roof_height"]]]
        profile = _api("profile.add_arbitrary_profile", file=model, profile=pts,
                       name="Крыша двускатная")
        representation = _api("geometry.add_profile_representation", file=model, context=body,
                              profile=profile, depth=d, cardinal_point=None)
        _api("geometry.assign_representation", file=model, product=gable,
             representation=representation)
        _api("spatial.assign_container", file=model, products=[gable],
             relating_structure=building)
        # локальная X -> мировая X; локальная Y (высота профиля) -> мировая Z;
        # выдавливание (+Z локали) -> +Y (от лицевой грани -Y вглубь), origin на грани
        matrix = np.array([
            [1.0, 0.0, 0.0, 0.0],
            [0.0, 0.0, 1.0, -d / 2],
            [0.0, 1.0, 0.0, top],
            [0.0, 0.0, 0.0, 1.0],
        ])
        _api("geometry.edit_object_placement", file=model, product=gable, matrix=matrix)
        _api("style.assign_representation_styles", file=model,
             shape_representation=representation, styles=[fstyles["roof"]])

    sb = ShapeBuilder(model)
    if data["roof"] in ("hip", "mansard") and data["roof_height"] > 0.05:
        rh = data["roof_height"]
        inset = min(rh * (d / w), w / 2 - 0.1, d / 2 - 0.1)
        ridge = top + (rh * 0.6 if data["roof"] == "mansard" else rh)  # излом ≈ вальма ниже
        pts = [[-w / 2, -d / 2, top], [w / 2, -d / 2, top],
               [w / 2, d / 2, top], [-w / 2, d / 2, top],
               [-w / 2 + inset, 0.0, ridge], [w / 2 - inset, 0.0, ridge]]
        _mesh_product(model, body, sb,
                      "Крыша вальмовая" if data["roof"] == "hip" else "Крыша мансардная",
                      *_hull(pts), building, "CONCEPTUAL_ROOF", fstyles, "roof")

    _properties(model, building, "FacadeModel", {
        "Storeys": n, "FloorHeight": fh, "WidthM": w, "DepthM": d,
        "Roof": data["roof"], "RoofHeight": data["roof_height"] if data["roof"] == "gable" else 0.0,
        "WindowsTotal": windows_total, "BalconiesCount": len(data["balconies"]),
        "Dormers": len(data.get("dormers") or []),
        "Towers": len(data.get("towers") or []),
        "CustomParts": len(data.get("custom_parts") or []),
        "OrthoAssumption": True, "DepthAssumed": True,
        "Source": "3D Design", "Notes": ASSUMPTION_FACADE,
    })
    for f in range(n):
        qto = _api("pset.add_qto", file=model,
                   product=[p for p in model.by_type("IfcBuildingElementProxy")
                            if p.ObjectType == "CONCEPTUAL_STOREY"][f],
                   name="Qto_BuildingElementProxyQuantities")
        _api("pset.edit_qto", file=model, qto=qto, properties={
            "NetVolume": float(w * d * fh)})

    _write_header(model, ifc_path)
    ifc_path.parent.mkdir(parents=True, exist_ok=True)
    model.write(str(ifc_path))
    _draw_facade_preview(data, preview_path)
    return ifc_path


def _draw_facade_preview(data, preview_path):
    """Чертёж фасада (метры): стены, цоколь, сетка окон, балконы, крыша."""
    colors = dict(FACADE_DEFAULT_COLORS)
    colors.update({k: v for k, v in (data.get("colors") or {}).items() if k in colors})
    w, fh, n = data["width_m"], data["floor_height"], data["storeys"]
    H = n * fh
    fig, ax = plt.subplots(figsize=(12, 7), facecolor="white")
    ax.add_patch(PlotPolygon([[-w / 2, 0], [w / 2, 0], [w / 2, H], [-w / 2, H]],
                             facecolor=colors["walls"], edgecolor="#263747", linewidth=1.2))
    ax.add_patch(PlotPolygon([[-w / 2 - 0.1, 0], [w / 2 + 0.1, 0],
                              [w / 2 + 0.1, 0.6], [-w / 2 - 0.1, 0.6]],
                             facecolor=colors["plinth"], edgecolor="#263747", linewidth=1.0))
    xs, zs = _facade_grid(data)
    skip = _window_skip(data)
    win = data["windows"]
    for j, z_in in enumerate(zs):
        for i, x in enumerate(xs):
            if j < len(skip) and i < len(skip[j]) and skip[j][i]:
                continue
            for f in range(n):
                ax.add_patch(PlotPolygon(
                    [[x, f * fh + z_in], [x + win["w_m"], f * fh + z_in],
                     [x + win["w_m"], f * fh + z_in + win["h_m"]],
                     [x, f * fh + z_in + win["h_m"]]],
                    facecolor=colors["glazing"], edgecolor="white", linewidth=0.7))
    for b_idx, bal in enumerate(data["balconies"], start=1):
        bal_lo = (bal["floor"] - 1) * fh
        bx = bal["x_m"] - w / 2  # тот же мировой фрейм, что у окон
        ax.add_patch(PlotPolygon(
            [[bx - bal["w_m"] / 2, bal_lo],
             [bx + bal["w_m"] / 2, bal_lo],
             [bx + bal["w_m"] / 2, bal_lo + 1.0],
             [bx - bal["w_m"] / 2, bal_lo + 1.0]],
            facecolor="none", edgecolor=colors["balcony"], hatch="////", linewidth=1.2))
        ax.text(bx, bal_lo + 0.5, f"Б{b_idx}", ha="center", va="center",
                fontsize=7, color="#15232e")
    top = H
    if data["roof"] == "gable":
        ax.add_patch(PlotPolygon([[-w / 2, H], [w / 2, H], [0, H + data["roof_height"]]],
                                 facecolor=colors["roof"], edgecolor="#263747", alpha=.9))
        top = H + data["roof_height"]
    for f in range(1, n):
        ax.plot([-w / 2, w / 2], [f * fh, f * fh], color="#263747", linewidth=.5,
                linestyle="--", alpha=.5)
    for i, x in enumerate(xs):
        ax.text(x + win["w_m"] / 2, -0.9, f"О{i + 1}", ha="center", va="center",
                fontsize=7, color="#15232e")
    ax.set_xlim(-w / 2 - 1.5, w / 2 + 1.5)
    ax.set_ylim(-1.5, top + 1.0)
    ax.set_aspect("equal")
    ax.axis("off")
    dp = data["depth_m"]
    ax.set_title(f"3D Design — фасад: {n} эт. × {fh:g} м, {w:g}×{dp:g} м, "
                 f"крыша {data['roof']}", fontsize=13)
    fig.tight_layout()
    preview_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(preview_path, dpi=160, facecolor="white")
    plt.close(fig)


# ===================== Фаза 3: сценарий «Интерьер» =====================

ASSUMPTION_INTERIOR = (
    "Концептуальная модель квартиры по растровому плану (3D Design). Стены, проёмы "
    "и мебель — оценочные блоки по обводке плана; размеры по опорным объектам или "
    "размерным линиям. Не использовать как обмерную или рабочую документацию."
)

INTERIOR_DEFAULT_COLORS = {
    "slab": "#d9d4c8", "wall": "#c8b89a", "opening": "#202830", "room": "#e6ecf2",
    "bed": "#8fa3bf", "sofa": "#7f9b8e", "table": "#c9a227", "chair": "#d4ac9e",
    "wardrobe": "#a58d6f", "kitchen": "#9aa3ad", "bath": "#bfd8e6",
    "toilet": "#e0e4e8", "sink": "#d6e0e8", "lamp": "#f0d68a", "other": "#b8bcc2",
}

FURNITURE_RU = {
    "bed": "Кровать", "sofa": "Диван", "table": "Стол", "chair": "Стул",
    "wardrobe": "Шкаф", "kitchen": "Кухня", "bath": "Ванна", "toilet": "Унитаз",
    "sink": "Раковина", "lamp": "Лампа", "other": "Предмет",
}


def _rot_z(deg):
    a = np.radians(float(deg))
    c, s = np.cos(a), np.sin(a)
    return np.array([[c, -s, 0.0, 0.0], [s, c, 0.0, 0.0],
                     [0.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.0, 1.0]])


def _px_to_m(data, x, y):
    """Пиксели картинки -> метры плана (Y-флип: y=0 — верх картинки)."""
    s = data["metres_per_trace_pixel"]
    return float(x) * s, (data["trace_height"] - float(y)) * s


def _outline_point_at(data, dist_px):
    """Точка на контуре outline на расстоянии dist_px вдоль периметра от 1-й
    точки + направление сегмента (градусы). None = контура нет."""
    pts_m = [_px_to_m(data, x, y) for x, y in data["outline"]]
    segs = []
    total = 0.0
    for i in range(len(pts_m)):
        a, b = pts_m[i], pts_m[(i + 1) % len(pts_m)]
        ln = float(np.hypot(b[0] - a[0], b[1] - a[1])) / data["metres_per_trace_pixel"]
        segs.append((a, b, ln))  # ln в пикселях исходника
        total += ln
    t = max(0.0, min(float(dist_px), total))
    acc = 0.0
    for a, b, ln in segs:
        if ln <= 0:
            continue
        if acc + ln >= t or (a, b, ln) is segs[-1]:
            frac = (t - acc) / ln
            x = a[0] + (b[0] - a[0]) * frac
            y = a[1] + (b[1] - a[1]) * frac
            ang = np.degrees(np.arctan2(b[1] - a[1], b[0] - a[0]))
            return x, y, ang, ln
        acc += ln
    return None


def build_interior(scene, ifc_path, preview_path, meta):
    """Сцена интерьера (validate_interior) -> IFC4 + чертёж-превью."""
    data = dict(scene)
    colors = dict(INTERIOR_DEFAULT_COLORS)
    data["colors"] = colors  # сборщик не красит по VLM-цветам — палитра типов
    scale = data["metres_per_trace_pixel"]
    wh = data["wall_height"]

    model = _api("project.create_file", version="IFC4")
    project = _api("root.create_entity", file=model, ifc_class="IfcProject",
                   name=data.get("project_name", "3D Design — интерьер"))
    project.Description = ASSUMPTION_INTERIOR
    units = [_api("unit.add_si_unit", file=model, unit_type=t)
             for t in ("LENGTHUNIT", "AREAUNIT", "VOLUMEUNIT")]
    _api("unit.assign_unit", file=model, units=units)
    context = _api("context.add_context", file=model, context_type="Model")
    body = _api("context.add_context", file=model, context_type="Model",
                context_identifier="Body", target_view="MODEL_VIEW", parent=context)
    site = _api("root.create_entity", file=model, ifc_class="IfcSite", name="Участок")
    _api("aggregate.assign_object", file=model, products=[site], relating_object=project)
    _api("geometry.edit_object_placement", file=model, product=site, matrix=np.eye(4))
    building = _api("root.create_entity", file=model, ifc_class="IfcBuilding",
                    name=data.get("building_name", "Квартира по плану"))
    building.Description = ASSUMPTION_INTERIOR
    _api("aggregate.assign_object", file=model, products=[building],
         relating_object=site)
    _api("geometry.edit_object_placement", file=model, product=building, matrix=np.eye(4))
    storey = _api("root.create_entity", file=model, ifc_class="IfcBuildingStorey",
                  name="Этаж 01")
    storey.Elevation = 0.0
    _api("aggregate.assign_object", file=model, products=[storey], relating_object=building)
    _api("geometry.edit_object_placement", file=model, product=storey, matrix=np.eye(4))
    _properties(model, project, "DevBIM", {
        "Source": meta.get("Source", "3D Design"), "Scenario": "interior",
        "Prompt": (meta.get("Prompt") or "")[:1024], "Model": meta.get("Model", ""),
        "ApproximateGeometry": True, "Notes": ASSUMPTION_INTERIOR,
    })
    fstyles = {}
    for key, color in colors.items():
        r, g, b = matplotlib.colors.to_rgb(color)
        style = _api("style.add_style", file=model, name=f"Interior{key.capitalize()}")
        _api("style.add_surface_style", file=model, style=style,
             ifc_class="IfcSurfaceStyleShading",
             attributes={"SurfaceColour": {"Name": key, "Red": r, "Green": g, "Blue": b},
                         "Transparency": 0.0})
        fstyles[key] = style

    def rbox(name, bw, bd, bh, cx, cy, z, rot_deg, color_key, container,
             ifc_class, object_type, predefined=None):
        """Прямоугольный блок с поворотом вокруг Z: профиль bw×bd, выдавливание
        bh вверх от z. rot_deg — против часовой в метрах плана."""
        kwargs = dict(file=model, ifc_class=ifc_class, name=name)
        if predefined is not None:
            kwargs["predefined_type"] = predefined
        product = _api("root.create_entity", **kwargs)
        if object_type is not None:
            product.ObjectType = object_type
        pts = [[-bw / 2, -bd / 2], [bw / 2, -bd / 2], [bw / 2, bd / 2], [-bw / 2, bd / 2]]
        profile = _api("profile.add_arbitrary_profile", file=model, profile=pts, name=name)
        representation = _api("geometry.add_profile_representation", file=model,
                              context=body, profile=profile, depth=bh, cardinal_point=None)
        _api("geometry.assign_representation", file=model, product=product,
             representation=representation)
        _api("spatial.assign_container", file=model, products=[product],
             relating_structure=container)
        matrix = _rot_z(rot_deg)
        matrix[0, 3], matrix[1, 3], matrix[2, 3] = float(cx), float(cy), float(z)
        _api("geometry.edit_object_placement", file=model, product=product, matrix=matrix)
        _api("style.assign_representation_styles", file=model,
             shape_representation=representation, styles=[fstyles[color_key]])
        return product

    def poly(name, points_px, depth, z, color_key, container, ifc_class,
             object_type, predefined=None):
        """Полигон px -> профиль относительно центроида, выдавливание depth от z."""
        kwargs = dict(file=model, ifc_class=ifc_class, name=name)
        if predefined is not None:
            kwargs["predefined_type"] = predefined
        product = _api("root.create_entity", **kwargs)
        if object_type is not None:
            product.ObjectType = object_type
        pts_m = [_px_to_m(data, x, y) for x, y in points_px]
        polygon = orient(Polygon(pts_m), sign=1.0)
        if not polygon.is_valid or polygon.area <= 0:
            raise ValueError(f"Некорректный контур: {name}")
        xy = np.array(polygon.exterior.coords, dtype=float)
        origin = np.array(polygon.centroid.coords[0])
        profile = _api("profile.add_arbitrary_profile", file=model,
                       profile=(xy - origin).tolist(), name=name)
        representation = _api("geometry.add_profile_representation", file=model,
                              context=body, profile=profile, depth=depth,
                              cardinal_point=None)
        _api("geometry.assign_representation", file=model, product=product,
             representation=representation)
        # IfcSpace — сам пространственный элемент: в IFC4 он входит в этаж через
        # IfcRelAggregates (spatial.assign_container умеет только элементы и
        # падает на IfcSpace: нет ContainedInStructure)
        if ifc_class == "IfcSpace":
            _api("aggregate.assign_object", file=model, products=[product],
                 relating_object=container)
        else:
            _api("spatial.assign_container", file=model, products=[product],
                 relating_structure=container)
        matrix = np.eye(4)
        matrix[:3, 3] = [float(origin[0]), float(origin[1]), float(z)]
        _api("geometry.edit_object_placement", file=model, product=product, matrix=matrix)
        _api("style.assign_representation_styles", file=model,
             shape_representation=representation, styles=[fstyles[color_key]])
        return product

    # --- плита пола: outline, толщина 0.1 м, верх на z=0
    if data["outline"]:
        poly("Пол", data["outline"], 0.1, -0.1, "slab", storey,
             "IfcSlab", "CONCEPTUAL_FLOOR", predefined="FLOOR")

    # --- стены: сегменты -> повёрнутые боксы
    wall_geo = []  # (p1_m, p2_m, length_m, angle_deg) для проёмов
    for idx, wall in enumerate(data["walls"], start=1):
        p1 = _px_to_m(data, *wall["points_px"][0])
        p2 = _px_to_m(data, *wall["points_px"][1])
        dx, dy = p2[0] - p1[0], p2[1] - p1[1]
        length = float(np.hypot(dx, dy))
        wall_geo.append((p1, p2, length))
        if length < 0.05:
            continue
        ang = np.degrees(np.arctan2(dy, dx))
        ext = " нар." if wall.get("exterior") else ""
        rbox(f"Стена {idx:02d}{ext}", length, wall["thickness_m"], wh,
             (p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2, 0.0, ang,
             "wall", storey, "IfcWall", "CONCEPTUAL_WALL", predefined="USERDEFINED")

    # --- проёмы: сквозь стену с выступом 0.03 м (урок фазы 2: заподлицо
    #     совпадающие грани не рендерятся и не кликаются)
    n_doors = n_windows = 0
    for op in data["openings"]:
        widx = op["wall_idx"]
        if widx == "outline":
            hit = _outline_point_at(data, op["x_px"]) if data["outline"] else None
            if hit is None:
                continue
            cx, cy, ang, len_px = hit
            thickness = 0.4
        else:
            p1, p2, length = wall_geo[widx]
            if length < 0.05:  # вырожденный сегмент (пропущен стеной)
                continue
            thickness = data["walls"][widx]["thickness_m"]
            t = max(0.0, min(op["x_px"] * scale, length))
            ux, uy = (p2[0] - p1[0]) / length, (p2[1] - p1[1]) / length
            cx, cy = p1[0] + ux * t, p1[1] + uy * t
            ang = np.degrees(np.arctan2(p2[1] - p1[1], p2[0] - p1[0]))
        if op["kind"] == "door":
            n_doors += 1
            name, otype = f"Дверь {n_doors}", "CONCEPTUAL_DOOR"
        else:
            n_windows += 1
            name, otype = f"Окно {n_windows}", "CONCEPTUAL_WINDOW"
        rbox(name, op["width_m"], thickness + 0.06, op["height_m"], cx, cy,
             op["sill_m"], ang, "opening", storey,
             "IfcBuildingElementProxy", otype, predefined="USERDEFINED")

    # --- комнаты: IfcSpace с именами с плана + pset Room
    for room in data["rooms"]:
        space = poly(room["name"], room["points_px"], 0.02, 0.005, "room",
                     storey, "IfcSpace", "CONCEPTUAL_ROOM", predefined="SPACE")
        _properties(model, space, "Room", {"Type": room.get("type", "other")})

    # --- мебель: IfcFurnishingElement, цвет/имя по типу, поворот
    for idx, item in enumerate(data["furniture"], start=1):
        cx, cy = _px_to_m(data, item["x_px"], item["y_px"])
        ftype = item["type"] if item["type"] in FURNITURE_RU else "other"
        rbox(f"{FURNITURE_RU[ftype]} {idx:02d}", item["w_m"], item["d_m"],
             item["h_m"], cx, cy, 0.0, -item["rot_deg"],  # Y-флип инвертирует угол
             ftype, storey, "IfcFurnishingElement", f"FURNITURE_{ftype.upper()}")

    _properties(model, building, "InteriorModel", {
        "WallHeight": wh, "ScaleMPerPx": scale,
        "Walls": len(data["walls"]), "Openings": len(data["openings"]),
        "Rooms": len(data["rooms"]), "Furniture": len(data["furniture"]),
        "ApproximateGeometry": True, "Notes": ASSUMPTION_INTERIOR,
    })

    _write_header(model, ifc_path)
    ifc_path.parent.mkdir(parents=True, exist_ok=True)
    model.write(str(ifc_path))
    _draw_interior_preview(data, preview_path)
    return ifc_path


def _draw_interior_preview(data, preview_path):
    """Чертёж плана в метрах: контур, стены, проёмы, подписи комнат, мебель."""
    scale = data["metres_per_trace_pixel"]
    wh = data["wall_height"]

    def rect_corners(cx, cy, bw, bd, deg):
        a = np.radians(deg)
        c, s = np.cos(a), np.sin(a)
        loc = [(-bw / 2, -bd / 2), (bw / 2, -bd / 2), (bw / 2, bd / 2), (-bw / 2, bd / 2)]
        return [(cx + x * c - y * s, cy + x * s + y * c) for x, y in loc]

    fig, ax = plt.subplots(figsize=(12, 8), facecolor="white")
    if data["outline"]:
        pts = [_px_to_m(data, x, y) for x, y in data["outline"]]
        ax.add_patch(PlotPolygon(pts + [pts[0]], facecolor="#efece5",
                                 edgecolor="#263747", linewidth=1.0))
    for idx, wall in enumerate(data["walls"], start=1):
        p1 = _px_to_m(data, *wall["points_px"][0])
        p2 = _px_to_m(data, *wall["points_px"][1])
        length = float(np.hypot(p2[0] - p1[0], p2[1] - p1[1]))
        if length < 0.05:
            continue
        ang = np.degrees(np.arctan2(p2[1] - p1[1], p2[0] - p1[0]))
        t = wall["thickness_m"]
        ax.add_patch(PlotPolygon(rect_corners((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2,
                                              length, t, ang),
                                 facecolor=data["colors"]["wall"], edgecolor="#263747",
                                 linewidth=0.8))
    for op in data["openings"]:
        widx = op["wall_idx"]
        if widx == "outline":
            hit = _outline_point_at(data, op["x_px"]) if data["outline"] else None
            if hit is None:
                continue
            cx, cy, ang, _ = hit
            thickness = 0.4
        else:
            if not (isinstance(widx, int) and 0 <= widx < len(data["walls"])):
                continue
            p1, p2, length = (_px_to_m(data, *data["walls"][widx]["points_px"][0]),
                              _px_to_m(data, *data["walls"][widx]["points_px"][1]), 0.0)
            length = float(np.hypot(p2[0] - p1[0], p2[1] - p1[1]))
            if length < 0.05:
                continue
            thickness = data["walls"][widx]["thickness_m"]
            t = max(0.0, min(op["x_px"] * scale, length))
            ux, uy = ((p2[0] - p1[0]) / length, (p2[1] - p1[1]) / length) if length else (0, 0)
            cx, cy = p1[0] + ux * t, p1[1] + uy * t
            ang = np.degrees(np.arctan2(p2[1] - p1[1], p2[0] - p1[0]))
        ax.add_patch(PlotPolygon(rect_corners(cx, cy, op["width_m"], thickness + 0.06, ang),
                                 facecolor=data["colors"]["opening"], edgecolor="white",
                                 linewidth=0.6))
    for room in data["rooms"]:
        pts = [_px_to_m(data, x, y) for x, y in room["points_px"]]
        centroid = Polygon(pts).centroid
        ax.text(centroid.x, centroid.y, room["name"], ha="center", va="center",
                fontsize=10, color="#15232e")
    for item in data["furniture"]:
        cx, cy = _px_to_m(data, item["x_px"], item["y_px"])
        ftype = item["type"] if item["type"] in FURNITURE_RU else "other"
        ax.add_patch(PlotPolygon(rect_corners(cx, cy, item["w_m"], item["d_m"],
                                              -item["rot_deg"]),
                                 facecolor=data["colors"][ftype], edgecolor="#263747",
                                 linewidth=0.7, alpha=.9))
        ax.text(cx, cy, FURNITURE_RU[ftype][:1], ha="center", va="center",
                fontsize=7, color="#15232e")
    xs, ys = [], []
    for x, y in (data["outline"] or []):
        mx, my = _px_to_m(data, x, y)
        xs.append(mx); ys.append(my)
    for w in data["walls"]:
        for x, y in w["points_px"]:
            mx, my = _px_to_m(data, x, y)
            xs.append(mx); ys.append(my)
    if xs:
        pad = 0.5
        ax.set_xlim(min(xs) - pad, max(xs) + pad)
        ax.set_ylim(min(ys) - pad, max(ys) + pad)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title(f"3D Design — интерьер: стены {wh:g} м, масштаб {scale:g} м/px",
                 fontsize=13)
    fig.tight_layout()
    preview_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(preview_path, dpi=160, facecolor="white")
    plt.close(fig)


# ===================== Фаза 4: сценарий «Сцена» (camera mapping) =====================

ASSUMPTION_SCENE = (
    "Концептуальная уличная сцена по фотографии (3D Design). Здания, деревья, "
    "автомобили и люди — схематичные объёмы-примитивы; перспектива принята за "
    "ортогональную, размеры оценочные по опорным объектам. Не использовать как "
    "обмерную или рабочую документацию."
)

SCENE_COLORS = {
    "walls": "#c8b89a", "roof": "#52616b", "plinth": "#8d8d8d",
    "glazing": "#202830", "balcony": "#9aa3ad", "tree": "#4e7a4e",
    "trunk": "#7a5b3a", "car": "#5a6470", "person": "#38424e", "ground": "#b9c2b4",
}


def _scene_box(model, body, fstyles, container, name, bw, bd, bh,
               cx, cy, z, color_key, object_type, rot_deg=0.0):
    """Примитив-бокс сцены (как box() фасада, +поворот вокруг Z)."""
    product = _api("root.create_entity", file=model, ifc_class="IfcBuildingElementProxy",
                   predefined_type="USERDEFINED", name=name)
    product.ObjectType = object_type
    pts = [[-bw / 2, -bd / 2], [bw / 2, -bd / 2], [bw / 2, bd / 2], [-bw / 2, bd / 2]]
    profile = _api("profile.add_arbitrary_profile", file=model, profile=pts, name=name)
    representation = _api("geometry.add_profile_representation", file=model, context=body,
                          profile=profile, depth=bh, cardinal_point=None)
    _api("geometry.assign_representation", file=model, product=product,
         representation=representation)
    _api("spatial.assign_container", file=model, products=[product],
         relating_structure=container)
    matrix = np.eye(4)
    rad = np.radians(rot_deg)
    matrix[0, 0], matrix[0, 1] = np.cos(rad), -np.sin(rad)
    matrix[1, 0], matrix[1, 1] = np.sin(rad), np.cos(rad)
    matrix[:3, 3] = [float(cx), float(cy), float(z)]
    _api("geometry.edit_object_placement", file=model, product=product, matrix=matrix)
    _api("style.assign_representation_styles", file=model,
         shape_representation=representation, styles=[fstyles[color_key]])
    return product


def build_scene(scene, ifc_path, preview_path, meta):
    """Сцена улицы (validate_scene) -> IFC4 + PNG-план. Возвращает ifc_path."""
    data = dict(scene)
    data.setdefault("camera", {})
    data.setdefault("buildings", [])
    data.setdefault("context", {})
    colors = dict(SCENE_COLORS)

    model = _api("project.create_file", version="IFC4")
    project = _api("root.create_entity", file=model, ifc_class="IfcProject",
                   name=data.get("project_name", "3D Design — сцена"))
    project.Description = ASSUMPTION_SCENE
    units = [_api("unit.add_si_unit", file=model, unit_type=t)
             for t in ("LENGTHUNIT", "AREAUNIT", "VOLUMEUNIT")]
    _api("unit.assign_unit", file=model, units=units)
    context = _api("context.add_context", file=model, context_type="Model")
    body = _api("context.add_context", file=model, context_type="Model",
                context_identifier="Body", target_view="MODEL_VIEW", parent=context)
    site = _api("root.create_entity", file=model, ifc_class="IfcSite", name="Участок")
    _api("aggregate.assign_object", file=model, products=[site], relating_object=project)
    _api("geometry.edit_object_placement", file=model, product=site, matrix=np.eye(4))
    _properties(model, project, "DevBIM", {
        "Source": meta.get("Source", "3D Design"), "Scenario": meta.get("Scenario", "scene"),
        "Prompt": (meta.get("Prompt") or "")[:1024], "Model": meta.get("Model", ""),
        "ApproximateGeometry": True, "Notes": ASSUMPTION_SCENE,
    })
    building = _api("root.create_entity", file=model, ifc_class="IfcBuilding",
                    name="Сцена по фото")
    building.Description = ASSUMPTION_SCENE
    _api("aggregate.assign_object", file=model, products=[building], relating_object=site)
    _api("geometry.edit_object_placement", file=model, product=building, matrix=np.eye(4))
    storey = _api("root.create_entity", file=model, ifc_class="IfcBuildingStorey",
                  name="Уровень сцены")
    storey.Elevation = 0.0
    _api("aggregate.assign_object", file=model, products=[storey], relating_object=building)
    _api("geometry.edit_object_placement", file=model, product=storey, matrix=np.eye(4))

    fstyles = {}
    for key, color in colors.items():
        r, g, b = matplotlib.colors.to_rgb(color)
        style = _api("style.add_style", file=model, name=f"Scene{key.capitalize()}")
        _api("style.add_surface_style", file=model, style=style,
             ifc_class="IfcSurfaceStyleShading",
             attributes={"SurfaceColour": {"Name": key, "Red": r, "Green": g, "Blue": b},
                         "Transparency": 0.0})
        fstyles[key] = style

    def boxx(name, bw, bd, bh, cx, cy, z, color_key, otype, rot=0.0):
        return _scene_box(model, body, fstyles, storey, name, bw, bd, bh,
                          cx, cy, z, color_key, otype, rot)

    windows_total = 0
    for b_idx, b in enumerate(data["buildings"], start=1):
        w, d = b["width_m"], b["depth_m"]
        fh, n = b["floor_height"], b["storeys"]
        cx0, cy0 = b["x_m"], b["y_m"]
        tag = "Гл" if b.get("main") else f"Д{b_idx}"
        win = b["windows"]
        for f in range(n):
            boxx(f"Стены {tag} · этаж {f + 1}", w, d, fh, cx0, cy0, f * fh,
                 "walls", "CONCEPTUAL_STOREY")
        # фронт (IFC -Y): сетка как у фасада, x_m балкона — от левого края
        usable = w - 2 * win["margin_x_m"]
        gap = (usable - win["cols"] * win["w_m"]) / (win["cols"] - 1) \
            if win["cols"] > 1 else 0.0
        pitch = win["w_m"] + max(gap, 0.0)
        xs = [cx0 - w / 2 + win["margin_x_m"] + i * pitch + win["w_m"] / 2
              for i in range(win["cols"])]
        zs = [win["margin_y_m"] + win["h_m"] / 2]  # rows=1..2; центр строки
        if win["rows"] > 1:
            mid = (fh - 2 * win["margin_y_m"]) / 2
            zs = [win["margin_y_m"] + win["h_m"] / 2, mid + win["h_m"] / 2]
        for f in range(n):
            for z_in in zs:
                for x in xs:
                    boxx(f"Окно {tag} Э{f + 1}-{xs.index(x) + 1}", win["w_m"], 0.12,
                         win["h_m"], x, cy0 - d / 2, f * fh + z_in,
                         "glazing", "CONCEPTUAL_WINDOW")
                    windows_total += 1
        if b.get("main"):
            # боковины ±X упрощённой сеткой (глухие боковины рендер не достраивает)
            side_cols = max(1, min(6, round((d - 2 * win["margin_x_m"]) / pitch))) \
                if pitch > 0 else 1
            for f in range(n):
                for z_in in zs:
                    for sgn, sname in ((-1, "L"), (1, "R")):
                        for k in range(side_cols):
                            y = cy0 - d / 2 + win["margin_x_m"] + k * pitch \
                                + win["w_m"] / 2
                            boxx(f"Окно {tag} бок{sname} Э{f + 1}-{k + 1}",
                                 0.12, win["w_m"], win["h_m"],
                                 cx0 + sgn * (w / 2 + 0.06), y, f * fh + z_in,
                                 "glazing", "CONCEPTUAL_WINDOW")
                            windows_total += 1
        for j, bal in enumerate(b["balconies"], start=1):
            bal_z = (bal["floor"] - 1) * fh - 0.18
            boxx(f"Балкон {tag} {j} · этаж {bal['floor']}", bal["w_m"], bal["d_m"], 0.18,
                 cx0 + bal["x_m"] - w / 2, cy0 - (d / 2 + bal["d_m"] / 2), bal_z,
                 "balcony", "CONCEPTUAL_BALCONY")
        boxx(f"Цоколь {tag}", w + 0.2, d + 0.2, 0.6, cx0, cy0, 0.0,
             "plinth", "CONCEPTUAL_PLINTH")
        if b["roof"] == "gable" and b["roof_height"] > 0.05:
            ridge = _api("root.create_entity", file=model,
                         ifc_class="IfcBuildingElementProxy",
                         predefined_type="USERDEFINED", name=f"Крыша {tag} двускатная")
            ridge.ObjectType = "CONCEPTUAL_ROOF"
            prof = [[-w / 2, 0.0], [w / 2, 0.0], [0.0, b["roof_height"]]]
            profile = _api("profile.add_arbitrary_profile", file=model, profile=prof,
                           name=f"Крыша {tag}")
            representation = _api("geometry.add_profile_representation", file=model,
                                  context=body, profile=profile, depth=d,
                                  cardinal_point=None)
            _api("geometry.assign_representation", file=model, product=ridge,
                 representation=representation)
            _api("spatial.assign_container", file=model, products=[ridge],
                 relating_structure=storey)
            matrix = np.array([
                [1.0, 0.0, 0.0, cx0],
                [0.0, 0.0, 1.0, cy0 - d / 2],
                [0.0, 1.0, 0.0, n * fh],
                [0.0, 0.0, 0.0, 1.0],
            ])
            _api("geometry.edit_object_placement", file=model, product=ridge,
                 matrix=matrix)
            _api("style.assign_representation_styles", file=model,
                 shape_representation=representation, styles=[fstyles["roof"]])

    ctx = data["context"]
    for t_idx, tr in enumerate(ctx.get("trees", []), start=1):
        h, crown = tr["h_m"], tr["crown_d_m"]
        boxx(f"Дерево {t_idx} · ствол", 0.3, 0.3, h * 0.4, tr["x_m"], tr["y_m"], 0.0,
             "trunk", "CONCEPTUAL_TREE")
        boxx(f"Дерево {t_idx} · крона", crown, crown, h * 0.6, tr["x_m"], tr["y_m"],
             h * 0.4, "tree", "CONCEPTUAL_TREE")
    for c_idx, car in enumerate(ctx.get("cars", []), start=1):
        boxx(f"Машина {c_idx}", 1.8, 4.5, 1.4, car["x_m"], car["y_m"], 0.0,
             "car", "CONCEPTUAL_CAR", rot=car.get("rot_deg", 0.0))
    for p_idx, per in enumerate(ctx.get("people", []), start=1):
        boxx(f"Человек {p_idx}", 0.5, 0.3, 1.7, per["x_m"], per["y_m"], 0.0,
             "person", "CONCEPTUAL_PERSON")

    # земля: общий габарит + запас 4 м
    all_xy = [(b["x_m"] - b["width_m"] / 2, b["y_m"] - b["depth_m"] / 2,
               b["x_m"] + b["width_m"] / 2, b["y_m"] + b["depth_m"] / 2)
              for b in data["buildings"]]
    for it in ctx.get("trees", []) + ctx.get("cars", []) + ctx.get("people", []):
        all_xy.append((it["x_m"] - 2, it["y_m"] - 2, it["x_m"] + 2, it["y_m"] + 2))
    x0 = min(p[0] for p in all_xy) - 4 if all_xy else -20
    y0 = min(p[1] for p in all_xy) - 4 if all_xy else -20
    x1 = max(p[2] for p in all_xy) + 4 if all_xy else 20
    y1 = max(p[3] for p in all_xy) + 4 if all_xy else 20
    boxx("Земля", x1 - x0, y1 - y0, 0.25, (x0 + x1) / 2, (y0 + y1) / 2, -0.25,
         "ground", "CONCEPTUAL_GROUND")

    cam = data["camera"]
    _properties(model, project, "CameraHint", {
        "AzimuthDeg": cam.get("azimuth_deg", 25.0),
        "EyeHeightM": cam.get("eye_height_m", 1.6),
        "DistM": cam.get("dist_m", 35.0),
    })
    _properties(model, building, "SceneModel", {
        "Buildings": len(data["buildings"]),
        "Trees": len(ctx.get("trees", [])),
        "Cars": len(ctx.get("cars", [])),
        "People": len(ctx.get("people", [])),
        "WindowsTotal": windows_total,
        "OrthoAssumption": True, "Source": "3D Design", "Notes": ASSUMPTION_SCENE,
    })

    _write_header(model, ifc_path)
    model.write(str(ifc_path))
    _draw_scene_preview(data, preview_path)
    return ifc_path


def _draw_scene_preview(data, preview_path):
    """План сцены сверху: здания, контекст, маркер камеры с направлением."""
    import matplotlib.pyplot as plt
    import matplotlib.transforms
    from matplotlib.patches import Circle, FancyArrow, Rectangle

    fig, ax = plt.subplots(figsize=(10, 8), dpi=140)
    ctx = data["context"]
    for b in data["buildings"]:
        face = "#d9c7a7" if b.get("main") else "#c4cdd8"
        ax.add_patch(Rectangle((b["x_m"] - b["width_m"] / 2, b["y_m"] - b["depth_m"] / 2),
                               b["width_m"], b["depth_m"], facecolor=face,
                               edgecolor="#263747", linewidth=1.2))
        ax.text(b["x_m"], b["y_m"], f"{b['storeys']} эт.", ha="center", va="center",
                fontsize=9, color="#15232e", fontweight="bold")
    for t in ctx.get("trees", []):
        ax.add_patch(Circle((t["x_m"], t["y_m"]), t["crown_d_m"] / 2,
                            facecolor="#7fae7f", edgecolor="#3c603c", alpha=.85))
    for c in ctx.get("cars", []):
        rot = c.get("rot_deg", 0.0) or 0.0
        tr = matplotlib.transforms.Affine2D().rotate_deg_around(
            c["x_m"], c["y_m"], rot) + ax.transData
        rect = Rectangle((c["x_m"] - 0.9, c["y_m"] - 2.25), 1.8, 4.5,
                         facecolor="#9aa3ad", edgecolor="#263747")
        rect.set_transform(tr)
        ax.add_patch(rect)
    for p in ctx.get("people", []):
        ax.add_patch(Circle((p["x_m"], p["y_m"]), 0.4, facecolor="#38424e"))
    cam = data["camera"]
    az = np.radians(cam.get("azimuth_deg", 25.0))
    dist = cam.get("dist_m", 35.0)
    main = next((b for b in data["buildings"] if b.get("main")), {"x_m": 0, "y_m": 0})
    # фасад главного здания смотрит на -Y (юг): камера — южнее, az>0 восточнее
    cxp = main["x_m"] + dist * np.sin(az)
    cyp = main["y_m"] - dist * np.cos(az)
    ax.add_patch(Circle((cxp, cyp), 1.2, facecolor="#e2574c", edgecolor="#7a1f18"))
    ax.add_patch(FancyArrow(cxp, cyp, (main["x_m"] - cxp) * 0.3,
                            (main["y_m"] - cyp) * 0.3,
                            width=0.5, head_width=2.0, color="#e2574c", alpha=.8))
    ax.text(cxp, cyp + 2.5, f"камера {cam.get('azimuth_deg', 25):g}° · {dist:g} м",
            ha="center", fontsize=8, color="#7a1f18")
    ax.set_aspect("equal")
    ax.autoscale(True)
    ax.set_title("3D Design — сцена: план (схематично, метры)", fontsize=13)
    ax.axis("off")
    fig.tight_layout()
    preview_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(preview_path, facecolor="white")
    plt.close(fig)
