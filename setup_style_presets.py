# -*- coding: utf-8 -*-
"""
setup_style_presets.py — профессиональные style-пресеты InvokeAI (DevBIM Image Studio).

Переписывает промты по умолчанию (style presets — шаблоны с плейсхолдером
{prompt}, выпадающий список «стилей» рядом с промптом) под три сценария
выпуска альбомов проектной документации:

  Facades     — «Facades — …»     (Neutral Daylight / Golden Hour / Blue
                                    Hour / Frontal — Album Sheet)
  Interiors   — «Interiors — …»   (Daylight / Evening Light / Public Space)
  Master Plan — «Master Plan — …» (Aerial Top-Down / Bird's Eye 45° /
                                    Orthographic — Album Sheet)
  Re-render   — «Facades|Interiors — Re-render from 3D View»: пересъёмка
                                    базового фото с камеры 3D-схемы (серый/
                                    рентген-скрин из IFC-вьювера). Весь
                                    контент — ТОЛЬКО с фото, из 3D-картинки —
                                    исключительно ракурс камеры (жалоба
                                    09.10: ИИ перетягивал форму и цвета
                                    из 3D). Роли картинок описываются по
                                    ВИДУ (цветное фото vs бесцветная схема),
                                    поэтому темплейт работает при любом
                                    порядке изображений в запросе.

Названия и тексты — на английском (русскоязычная адаптация интерфейса —
позже; после неё переименовать PRESETS и превью). Пользователь пишет свой
промпт (любой язык), пресет добавляет профессиональную архвиз-обвязку:
камера, свет, материалы, окружение, качество.

Как хранятся пресеты:
  - InvokeAI при каждом старте сервера УДАЛЯЕТ все пресеты type='default'
    и заново сеет их из venv/.../style_preset_records/default_style_presets.json
    (см. style_preset_records_sqlite.py::_sync_default_style_presets).
    Поэтому править только БД бессмысленно — правим seed-файл.
  - Живую БД синхронизируем тут же (DELETE + INSERT), чтобы работающий
    сервер увидел новые пресеты без перезапуска: сервис style_preset_records
    читает таблицу на каждый запрос, кэша нет.

Идемпотентен. Оригинальный стоковый набор один раз сохраняется рядом с
seed-файлом как default_style_presets.json.orig.

Превью: маленькие PNG (256 px) в style_preset_images/ (источник, в git),
генерируются скриптом make_style_previews.py через ImageRouter; setup
копирует их в venv (для default-пресетов InvokeAI ищет превью по ИМЕНИ
пресета в default_style_preset_images/). Имена пресетов обязаны быть
корректными именами файлов Windows.

Запуск:      venv\Scripts\python.exe setup_style_presets.py
Вернуть сток: venv\Scripts\python.exe setup_style_presets.py --restore
"""
from __future__ import annotations

import json
from contextlib import closing
import shutil
import sqlite3
import sys
import uuid
from pathlib import Path
from package_layout import site_packages

ROOT = Path(__file__).resolve().parent
SP = site_packages(ROOT / "venv")
SEED_JSON = (
    SP / "invokeai" / "app" / "services"
    / "style_preset_records" / "default_style_presets.json"
)
SEED_BACKUP = SEED_JSON.with_suffix(".json.orig")
DB = ROOT / "data" / "databases" / "invokeai.db"
# Превью пресетов: источник в проекте, деплой — в пакет. Для default-пресетов
# InvokeAI ищет картинку ПО ИМЕНИ ПРЕСЕТА в default_style_preset_images
# (см. style_preset_images_disk.py::get_path) — поэтому имена пресетов
# обязаны быть корректными именами файлов Windows (без / \ : * ? " < > |).
SRC_IMAGES = ROOT / "style_preset_images"
VENV_IMAGES = (
    SP / "invokeai" / "app" / "services"
    / "style_preset_images" / "default_style_preset_images"
)

# --- Негативные базы (общие куски по сценариям) ---

NEG_FACADE = (
    "painting, illustration, sketch, cartoon, anime, cgi look, low quality, "
    "blurry, jpeg artifacts, watermark, text, logo, distorted geometry, warped "
    "or melted windows, leaning walls, misaligned floors, fisheye distortion, "
    "oversaturated colors, hdr halos"
)
NEG_INTERIOR = (
    "painting, illustration, sketch, cartoon, anime, cgi look, low quality, "
    "blurry, distorted geometry, warped furniture, crooked walls, clutter, "
    "fisheye distortion, plastic-looking materials, overexposed windows, "
    "watermark, text"
)
NEG_PLAN = (
    "painting, illustration, sketch, cartoon, low quality, blurry, text, "
    "labels, annotations, legend, north arrow, dimension lines, blueprint "
    "style, watermark, distorted geometry, warped roads, fisheye"
)

# Ре-рендер по 3D-ракурсу: гоним перенос формы/цвета со схемы. Кусы
# «painting/blurry/…» уже есть в NEG_FACADE/NEG_INTERIOR, здесь — только
# специфичное, добавляется к ним через запятую. Блок boxy/low-poly —
# после живого теста 09.10: диван «квадратнел» как в 3D, а плейсхолдер
# растения (прямоугольник) отрисовывался шкафом.
NEG_RERENDER_3D = (
    "colors or materials copied from the 3d schematic, gray desaturated "
    "image, wireframe look, blueprint look, x-ray translucent ghost "
    "geometry, colored outline overlay, untextured clay render, flat "
    "white or gray surfaces, restyled architecture and furniture, "
    "mismatched photographic style, different season or time of day "
    "than the base photo, geometry copied from the 3d schematic, boxy "
    "or blocky furniture, squared-off cushions and armrests, cube-like "
    "placeholder objects, plain boxes rendered as wardrobes or cabinets, "
    "low-poly simplified shapes, altered object proportions, distorted "
    "object dimensions, missing or merged object parts, changed lamp "
    "shade counts"
)

# --- Новые промты по умолчанию: {prompt} = текст пользователя из UI ---

PRESETS: list[dict] = [
    # ---------- ФАСАДЫ (альбом фасадов) ----------
    {
        "name": "Facades — Neutral Daylight",
        "type": "default",
        "preset_data": {
            "positive_prompt": (
                "{prompt}, professional architectural exterior visualization, "
                "photorealistic building render, eye-level camera, two-point "
                "perspective, perfectly vertical lines, neutral overcast "
                "daylight, soft even shadows, physically accurate materials: "
                "brick masonry, architectural concrete, metal panels, glass "
                "curtain wall with true sky reflections, crisp clean geometry, "
                "detailed window frames and facade joints, mature landscaping, "
                "paved sidewalks, people and cars at a distance for scale, "
                "high dynamic range, ultra-detailed textures, 8k, shot on "
                "full-frame camera, f/11"
            ),
            "negative_prompt": NEG_FACADE,
        },
    },
    {
        "name": "Facades — Golden Hour",
        "type": "default",
        "preset_data": {
            "positive_prompt": (
                "{prompt}, photorealistic architectural exterior "
                "visualization, golden hour, low warm sunlight raking across "
                "the facade, long soft shadows, glass curtain wall reflecting "
                "the orange sky, subtle warm reflections on clean pavement, "
                "lush landscaping lit by the setting sun, professional real "
                "estate photography, eye-level camera, two-point perspective, "
                "perfectly vertical lines, ultra-detailed materials, 8k"
            ),
            "negative_prompt": NEG_FACADE,
        },
    },
    {
        "name": "Facades — Blue Hour (Evening)",
        "type": "default",
        "preset_data": {
            "positive_prompt": (
                "{prompt}, photorealistic architectural exterior "
                "visualization, blue hour dusk, deep blue gradient sky, warm "
                "interior lighting glowing through the windows, subtle "
                "architectural accent lighting on the facade, soft reflections "
                "on the pavement, street lamps just switched on, calm evening "
                "atmosphere, eye-level camera, two-point perspective, "
                "perfectly vertical lines, ultra-detailed, 8k"
            ),
            "negative_prompt": NEG_FACADE + ", pitch black, flat lighting",
        },
    },
    {
        "name": "Facades — Frontal (Album Sheet)",
        "type": "default",
        "preset_data": {
            "positive_prompt": (
                "{prompt}, straight-on frontal view of the building facade, "
                "camera perfectly level and centered, near-orthographic "
                "elevation, true proportions and real floor heights, neutral "
                "diffuse daylight, even illumination across the whole facade, "
                "plain smooth sky background, photorealistic architectural "
                "rendering, precise geometry, crisp facade edges, "
                "ultra-detailed materials, 8k"
            ),
            "negative_prompt": NEG_FACADE + (
                ", perspective distortion, converging verticals, tilted "
                "camera, cropped facade, foreground objects blocking the facade"
            ),
        },
    },
    # ---------- ИНТЕРЬЕРЫ (альбом интерьеров) ----------
    {
        "name": "Interiors — Daylight",
        "type": "default",
        "preset_data": {
            "positive_prompt": (
                "{prompt}, photorealistic interior visualization, interior "
                "design magazine photography, eye-level camera at 1.5 m, "
                "two-point perspective, perfectly vertical lines, natural "
                "daylight through large windows, soft fill light, balanced "
                "window exposure, accurate materials: oak wood, natural "
                "stone, textile, subtly glossy surfaces with realistic "
                "reflections, elegant furniture, styling with plants, books "
                "and decor, global illumination, raytraced reflections, "
                "ultra-detailed, 8k"
            ),
            "negative_prompt": NEG_INTERIOR,
        },
    },
    {
        "name": "Interiors — Evening Light",
        "type": "default",
        "preset_data": {
            "positive_prompt": (
                "{prompt}, photorealistic interior visualization, evening "
                "atmosphere, warm layered lighting: pendant lamps, floor "
                "lamps and hidden LED accent light, soft pools of warm light, "
                "deep cozy shadows, accurate materials with warm reflections, "
                "elegant furniture, interior design magazine photography, "
                "eye-level camera at 1.5 m, two-point perspective, perfectly "
                "vertical lines, ultra-detailed, 8k"
            ),
            "negative_prompt": NEG_INTERIOR,
        },
    },
    {
        "name": "Interiors — Public Space",
        "type": "default",
        "preset_data": {
            "positive_prompt": (
                "{prompt}, photorealistic interior visualization of a public "
                "space, wide interior photography of a spacious hall with "
                "high ceilings, natural daylight through floor-to-ceiling "
                "glazing, durable honest materials: terrazzo, wood panels, "
                "acoustic baffles, metal and glass details, clear circulation "
                "routes, people at a natural distance for scale, eye-level "
                "camera, two-point perspective, perfectly vertical lines, "
                "global illumination, ultra-detailed, 8k"
            ),
            "negative_prompt": NEG_INTERIOR,
        },
    },
    # ---------- ГЕНПЛАН (альбом генплана) ----------
    {
        "name": "Master Plan — Aerial (Top-Down)",
        "type": "default",
        "preset_data": {
            "positive_prompt": (
                "{prompt}, professional master plan rendering, top-down "
                "aerial view, straight nadir drone photography, complete site "
                "plan: building footprints, road network with lane markings, "
                "sidewalks and crosswalks, parking with cars, landscaped "
                "courtyards, mature trees, playgrounds and recreation zones, "
                "summer midday sun, crisp readable shadows, realistic "
                "vegetation, tiny people for scale, photorealistic, "
                "ultra-detailed, 8k"
            ),
            "negative_prompt": NEG_PLAN + ", tilted view",
        },
    },
    {
        "name": "Master Plan — Bird's Eye (45°)",
        "type": "default",
        "preset_data": {
            "positive_prompt": (
                "{prompt}, professional master plan rendering, bird's-eye "
                "aerial view at 45 degrees, three-quarter perspective over "
                "the site, urban context around: neighboring blocks, streets "
                "and greenery, complete development: buildings, roads, "
                "parking, landscaping, courtyards and walkways, summer "
                "daylight with soft shadows, realistic trees and vegetation, "
                "cars and people for scale, photorealistic, ultra-detailed, 8k"
            ),
            "negative_prompt": NEG_PLAN,
        },
    },
    {
        "name": "Master Plan — Orthographic (Album Sheet)",
        "type": "default",
        "preset_data": {
            "positive_prompt": (
                "{prompt}, flat site plan rendering seen from directly "
                "above, perfectly vertical nadir view, only roofs and "
                "ground surfaces visible, no building facades, no "
                "perspective and no axonometric tilt, no cast shadows, "
                "flat even ambient lighting like an overcast satellite "
                "image, true-to-scale footprints and distances, realistic "
                "surface materials: lawns, paving, asphalt, roofs, "
                "color-coded functional zones, crisp clean edges, "
                "high-contrast readable composition for a presentation "
                "board, ultra-detailed, 8k"
            ),
            "negative_prompt": NEG_PLAN + (
                ", strong cast shadows, perspective distortion, axonometric "
                "view, visible building facades, 3d buildings, tilted camera"
            ),
        },
    },
    # ---------- РЕ-РЕНДЕР ПО 3D-РАКУРСУ (фото + скрин IFC-вьювера) ----------
    # Сценарий (жалоба 09.10): есть базовое фото (все материалы, цвета,
    # люди) и скрин 3D-сцены в режиме «Серый»/«Рентген». Нужно развернуть
    # фото к камере 3D-сцены, НЕ перетаскивая из 3D ни форм, ни цветов.
    # Роли картинок описываем по ВИДУ, а не по номеру — работает и когда
    # фото — исходник/канвас, и когда оба лежат в референсах в любом
    # порядке. Темплейт стоит в промте ПЕРЕД блоком референсов роутера,
    # поэтому прямо объявляем свой приоритет над общими примечаниями.
    {
        "name": "Facades — Re-render from 3D View",
        "type": "default",
        "preset_data": {
            "positive_prompt": (
                "{prompt}, photorealistic re-render of the photographed "
                "project from a new camera angle. IMAGE ROLES — follow "
                "strictly, they take priority over any generic image notes. "
                "The full-color photograph is the master and the ONLY source "
                "of content, shapes and details: same building volumes, "
                "facade materials, colors, window and balcony design, "
                "landscaping, people and lighting as photographed. The "
                "colorless 3D schematic (grayscale or wireframe) is a CAMERA "
                "GUIDE ONLY: take from it only where the camera stands, its "
                "direction, height and framing — nothing else; ignore its "
                "gray tones, wireframe lines and its crude blocky "
                "placeholder geometry entirely. The schematic's plain blocks "
                "are just position markers: a block may stand for a canopy, "
                "a column, a tree or a bench — never draw a block as a plain "
                "box or cube; put the real photographed object there "
                "instead. Every element keeps its photographed shape and "
                "exact proportions — balconies, railings, window frames, "
                "canopies exactly as designed: never squared off, never "
                "resized, never simplified; reproduce them part-for-part "
                "(same mullions, railing posts, steps). Result: the very "
                "same photographed building re-shot from the new camera — "
                "same palette, white balance and photographic style, "
                "photorealistic, ultra-detailed, 8k. Surfaces not visible in "
                "the photograph: complete them naturally in the same "
                "materials and design language"
            ),
            "negative_prompt": NEG_FACADE + ", " + NEG_RERENDER_3D,
        },
    },
    {
        "name": "Interiors — Re-render from 3D View",
        "type": "default",
        "preset_data": {
            "positive_prompt": (
                "{prompt}, photorealistic re-render of the photographed "
                "interior from a new camera angle. IMAGE ROLES — follow "
                "strictly, they take priority over any generic image notes. "
                "The full-color photograph is the master and the ONLY source "
                "of content, shapes and details: same room geometry, "
                "finishes, furniture forms, decor, plants, people and "
                "lighting as photographed. The colorless 3D schematic "
                "(grayscale or wireframe) is a CAMERA GUIDE ONLY: take from "
                "it only where the camera stands, its direction, height and "
                "framing — nothing else; ignore its gray tones, wireframe "
                "lines and its crude blocky placeholder geometry entirely. "
                "The schematic's plain blocks are just position markers: a "
                "block may stand for a plant, a lamp or a table — never draw "
                "a block as a box, a cube or a wardrobe; put the real "
                "photographed object there instead. Every object keeps its "
                "photographed shape and exact proportions — soft rounded "
                "cushions, curved armrests, slender legs exactly as "
                "photographed: never squared off, never resized, never "
                "simplified; reproduce objects part-for-part (same number of "
                "lamp shades, cushions, drawers). Result: the very same "
                "photographed room re-shot from the new camera — same "
                "palette, white balance and photographic style, global "
                "illumination, ultra-detailed, 8k. Areas not visible in the "
                "photograph: complete them naturally in the same materials "
                "and furnishing style"
            ),
            "negative_prompt": NEG_INTERIOR + ", " + NEG_RERENDER_3D,
        },
    },
]


def _validate(presets: list[dict]) -> None:
    names = [p["name"] for p in presets]
    assert len(names) == len(set(names)), "дубликаты имён пресетов"
    bad = set('\\/:*?"<>|')
    for p in presets:
        assert p["type"] == "default"
        assert "{prompt}" in p["preset_data"]["positive_prompt"], p["name"]
        assert p["preset_data"]["negative_prompt"], p["name"]
        # превью для default-пресетов ищутся по имени файла — см. SRC_IMAGES
        assert not (set(p["name"]) & bad), (
            f"имя пресета не подходит под имя файла: {p['name']!r}")


def deploy_seed(presets: list[dict]) -> None:
    """Пишет набор в seed-файл venv. ensure_ascii=True принципиально:
    InvokeAI читает файл open() без encoding (Python 3.11, Windows ->
    cp1251 вне PYTHONUTF8=1), поэтому файл обязан быть чистым ASCII —
    кириллица уезжает в \\uXXXX-эскейпы, json.load() раскодирует их сам."""
    if not SEED_JSON.is_file():
        raise SystemExit(f"не найден {SEED_JSON} — venv установлен?")
    if not SEED_BACKUP.exists():
        shutil.copy2(SEED_JSON, SEED_BACKUP)
        print("Стоковый набор сохранён:", SEED_BACKUP.name)
    # ensure_ascii по умолчанию True; separators — как у pydantic model_dump_json
    text = json.dumps(presets, indent=2) + "\n"
    SEED_JSON.write_text(text, encoding="ascii", newline="\n")
    print(f"Seed-файл записан: {len(presets)} пресетов -> {SEED_JSON.name}")


def sync_db(db_path: Path, presets: list[dict]) -> None:
    """Заменяет в живой БД все пресеты type='default' на новые.
    Работает и при запущенном сервере (WAL + busy_timeout)."""
    if not db_path.is_file():
        print("БД не найдена, пропускаю:", db_path)
        return
    con = sqlite3.connect(db_path, timeout=15)
    try:
        con.execute("PRAGMA busy_timeout=15000")
        with con:
            con.execute("DELETE FROM style_presets WHERE type = 'default'")
            for p in presets:
                con.execute(
                    "INSERT INTO style_presets (id, name, preset_data, type) "
                    "VALUES (?, ?, ?, ?)",
                    (
                        str(uuid.uuid4()),
                        p["name"],
                        json.dumps(p["preset_data"], ensure_ascii=False,
                                   separators=(",", ":")),
                        p["type"],
                    ),
                )
    finally:
        con.close()
    with closing(sqlite3.connect(db_path)) as con:
        n = con.execute(
            "SELECT COUNT(*) FROM style_presets WHERE type = 'default'"
        ).fetchone()[0]
    print(f"БД синхронизирована ({db_path.parent.parent.name}/): "
          f"{n} default-пресетов")


def deploy_images() -> None:
    """Копирует превью из style_preset_images/ в пакет InvokeAI и убирает
    из пакета устаревшие PNG (не stock и не от текущих пресетов — напр.,
    после переименования пресетов). Отсутствующие превью — не ошибка
    (в UI будет заглушка), но сообщаем."""
    copied = 0
    for p in PRESETS:
        src = SRC_IMAGES / (p["name"] + ".png")
        if src.is_file():
            shutil.copy2(src, VENV_IMAGES / src.name)
            copied += 1
        else:
            print(f"без превью (заглушка в UI): {p['name']}")
    keep = {p["name"] + ".png" for p in PRESETS}
    if SEED_BACKUP.is_file():  # стоковые картинки пакета не трогаем
        stock = json.loads(SEED_BACKUP.read_text(encoding="utf-8"))
        keep |= {s["name"] + ".png" for s in stock}
    for f in VENV_IMAGES.glob("*.png"):
        if f.name not in keep:
            f.unlink()
            print(f"удалён устаревший файл превью: {f.name}")
    print(f"Превью скопировано: {copied} из {len(PRESETS)} "
          f"-> {VENV_IMAGES.parent.name}/{VENV_IMAGES.name}/")


def restore() -> None:
    """Возвращает стоковый набор InvokeAI (seed-файл, превью, БД)."""
    if not SEED_BACKUP.is_file():
        raise SystemExit("Бэкап .orig не найден — восстанавливать нечего.")
    presets = json.loads(SEED_BACKUP.read_text(encoding="utf-8"))
    shutil.copy2(SEED_BACKUP, SEED_JSON)
    print("Seed-файл восстановлен из .orig")
    for p in PRESETS:  # убрать наши превью из пакета
        f = VENV_IMAGES / (p["name"] + ".png")
        if f.is_file():
            f.unlink()
    sync_db(DB, presets)


def main() -> None:
    if "--restore" in sys.argv:
        restore()
        return
    _validate(PRESETS)
    deploy_seed(PRESETS)
    deploy_images()
    if "--no-db-sync" not in sys.argv:
        sync_db(DB, PRESETS)
    print("Готово. В UI список стилей обновится после F5 (кэш RTK Query).")


if __name__ == "__main__":
    main()
