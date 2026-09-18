# -*- coding: utf-8 -*-
"""Сборка IFC4 «Генплан» по сцене-JSON (адаптация build_model.py скилла image-to-ifc).

Вход: scene (схема footprints: sections/context, пиксели + метры), PIL-картинка
исходника (после даунскейла), пути IFC и превью. Выход: путь к IFC.
"""
from collections import defaultdict
from pathlib import Path

import ifcopenshell
import ifcopenshell.api
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
