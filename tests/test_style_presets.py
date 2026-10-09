# -*- coding: utf-8 -*-
"""Тесты setup_style_presets. Запуск: venv\\Scripts\\python.exe tests\\test_style_presets.py

Проверяет: seed-файл в venv валиден и ASCII-безопасен (InvokeAI читает его
open() без encoding), каждая запись проходит валидацию pydantic-моделью
сеятеля (сервер не упадёт на старте), в живой БД — наши пресеты и нет
стоковых. Пресеты можно менять в setup_style_presets.py и перезапускать
setup + этот тест.
"""
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import setup_style_presets as sp

# 1. seed-файл существует и читается как чистый ASCII (независимо от
#    PYTHONUTF8/локали: кириллические названия уехали в \uXXXX-эскейпы)
raw = sp.SEED_JSON.read_bytes()
raw.decode("ascii")
presets = json.loads(raw)
assert len(presets) == len(sp.PRESETS), (len(presets), len(sp.PRESETS))

# 2. каждая запись валидна моделью сеятеля — restart сервера не упадёт
from invokeai.app.services.style_preset_records.style_preset_records_common import (
    StylePresetWithoutId,
)
for p in presets:
    StylePresetWithoutId.model_validate(p)

# 3. имена уникальны, {prompt} ровно один, негатив непустой
names = [p["name"] for p in presets]
assert len(names) == len(set(names))
for p in presets:
    assert p["preset_data"]["positive_prompt"].count("{prompt}") == 1, p["name"]
    assert p["preset_data"]["negative_prompt"].strip(), p["name"]

# 4. покрытие трёх сценариев (названия — английские; русская локализация
#    интерфейса запланирована отдельно, потом переименовать PRESETS+превью)
for prefix in ("Facades", "Interiors", "Master Plan"):
    got = [n for n in names if n.startswith(prefix + " —")]
    assert got, f"нет пресетов сценария {prefix}"
    print(f"{prefix}: {len(got)} пресетов")

# 4b. ре-рендер по 3D-ракурсу: якоря живых уроков обязаны присутствовать
#     в текстах (утечка цвета/формы из 3D — диван «квадратнел», плейсхолдер
#     растения → шкаф; дрейф пропорций; ГЛАВНЫЙ УРОК итерации 4: длинный
#     промпт (~350 слов) РАЗМЫВАЕТ внимание редактирующей модели и boxy
#     вернулся — поэтому v4 компрессирована и прижата лимитом длины)
rr = [p for p in sp.PRESETS if "Re-render from 3D View" in p["name"]]
assert len(rr) == 2, f"ожидались 2 пресета Re-render, есть {len(rr)}"
for p in rr:
    pos = p["preset_data"]["positive_prompt"]
    assert "CAMERA GUIDE ONLY" in pos, p["name"]
    assert "position markers" in pos, p["name"]
    assert "never draw a block" in pos, p["name"]
    assert "never squared off, never resized, never simplified" in pos, p["name"]
    assert "part-for-part" in pos, p["name"]
    assert "take priority over any generic image notes" in pos, p["name"]
    # грабля итерации 3->4: не давать промпту снова разрастись
    assert len(pos.split()) <= 240, (
        f"{p['name']}: {len(pos.split())} слов — компрессия нарушена")
    neg = p["preset_data"]["negative_prompt"]
    assert "boxy" in neg and "low-poly" in neg, p["name"]
    assert "geometry copied from the 3d schematic" in neg, p["name"]
    assert "missing or merged object parts" in neg, p["name"]

# 5. живая БД: default-пресеты совпадают с seed-файлом по именам и текстам
con = sqlite3.connect(sp.DB)
rows = con.execute(
    "SELECT name, preset_data FROM style_presets WHERE type = 'default'"
).fetchall()
con.close()
assert len(rows) == len(presets), (len(rows), len(presets))
db_map = {n: json.loads(d) for n, d in rows}
for p in presets:
    assert p["name"] in db_map, p["name"]
    assert db_map[p["name"]] == p["preset_data"], p["name"]

# 6. стоковых пресетов не осталось
for stock in ("Photography", "Anime", "Concept Art", "Architectural Visualization"):
    assert not any(stock in n for n in db_map), stock

# 7. бэкап стокового набора на месте (есть что возвращать через --restore)
assert sp.SEED_BACKUP.is_file()
assert "Photography" in sp.SEED_BACKUP.read_text(encoding="utf-8")

# 8. имена пресетов — корректные имена файлов Windows: превью default-пресетов
#    ищутся ПО ИМЕНИ (default_style_preset_images/{name}.png), слэш в имени
#    («(3/4)») молча ломает и сохранение, и поиск превью
bad = set('\\/:*?"<>|')
for n in names:
    assert not (set(n) & bad), f"имя не подходит под имя файла: {n!r}"

# 9. превью: исходник в проекте + задеплоено в venv для каждого пресета
for n in names:
    src = sp.SRC_IMAGES / (n + ".png")
    assert src.is_file(), f"нет превью {src.name} — запустите make_style_previews.py"
    dst = sp.VENV_IMAGES / (n + ".png")
    assert dst.is_file(), f"превью не задеплоено: {dst} — запустите setup_style_presets.py"

print("OK")
