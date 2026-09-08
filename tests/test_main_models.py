# -*- coding: utf-8 -*-
"""Тесты выбора основных моделей (генерация/правка) администратором:
инъекция (дефолт «весь каталог» и сохранённый список), эндпоинты,
описания без стоимости (со словом «редактирование» для гейта фолбэка).

Запуск: venv\\Scripts\\python.exe tests\\test_main_models.py
"""
import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "imagerouter"))

import imagerouter_router as ir  # noqa: E402


CATALOG = [
    {
        "id": "google/nano-banana-2",
        "architecture": {"input_modalities": ["image"]},
        "pricing": {"average": 0.03},
    },
    {
        "id": "black-forest-labs/FLUX-2-dev",
        "architecture": {"input_modalities": ["image"]},
        "pricing": {"average": 0.009},
    },
    {
        # чистая генерация, без входа-image
        "id": "HiDream-ai/HiDream-I1",
        "architecture": {"input_modalities": []},
        "pricing": {"average": 0.004},
    },
]


def main():
    tmp = Path(tempfile.mkdtemp())
    ir.get_config = lambda: SimpleNamespace(root_path=str(tmp))
    ir._fetch_ir_models = lambda force=False: list(CATALOG)
    ir._ir_model_by_id = lambda mid: next((m for m in CATALOG if m.get("id") == mid), None)

    # --- 1. дефолт: файла нет -> инъектируются ВСЕ модели каталога ---

    data = {"models": [{"key": "local/model"}]}
    ir._add_ir_models(data)
    keys = {m["key"] for m in data["models"]}
    for m in CATALOG:
        assert "imagerouter/" + m["id"] in keys, m["id"]
    print("OK дефолт: весь каталог")

    # --- 2. описание: без цены, с «редактирование» у edit-моделей ---

    cfg_edit = next(m for m in data["models"] if m["key"] == "imagerouter/google/nano-banana-2")
    assert "$" not in cfg_edit["description"], cfg_edit["description"]
    assert "редактирование" in cfg_edit["description"], cfg_edit["description"]  # гейт Generate-фолбэка
    assert "✏️" in cfg_edit["description"], cfg_edit["description"]
    cfg_txt = next(m for m in data["models"] if m["key"] == "imagerouter/HiDream-ai/HiDream-I1")
    assert "редактирование" not in cfg_txt["description"], cfg_txt["description"]
    # апскейл-фейк тоже без цены
    up = ir._ir_upscale_fake_config(CATALOG[0])
    assert "$" not in up["description"], up["description"]
    print("OK описания без цены, «редактирование» сохранено")

    # --- 3. сохранённый выбор: только выбранные, в порядке админа ---

    (tmp / "data").mkdir(exist_ok=True)
    (tmp / "data" / "imagerouter_main_models.json").write_text(
        json.dumps({"models": ["HiDream-ai/HiDream-I1", "google/nano-banana-2", "no/such-model"]}), encoding="utf-8"
    )
    data = {"models": []}
    ir._add_ir_models(data)
    main_keys = [m["key"] for m in data["models"] if m["key"].startswith("imagerouter/") and m["type"] == "main"]
    # порядок выбора, отсутствующие в каталоге отфильтрованы
    assert main_keys == [
        "imagerouter/HiDream-ai/HiDream-I1",
        "imagerouter/google/nano-banana-2",
    ], main_keys
    print("OK фильтрация и порядок выбора")

    # --- 4. эндпоинты ---

    st = ir.get_main_models()
    assert st["all_by_default"] is False
    # несуществующие id показываются с available=False (информативно),
    # инъекция их всё равно отфильтровывает
    ids = [it["id"] for it in st["models"]]
    assert ids == ["HiDream-ai/HiDream-I1", "google/nano-banana-2", "no/such-model"], ids
    by_id = {it["id"]: it for it in st["models"]}
    assert by_id["google/nano-banana-2"]["image_input"] is True
    assert by_id["HiDream-ai/HiDream-I1"]["image_input"] is False
    assert by_id["no/such-model"]["available"] is False

    # PUT: чистая генерация допустима (без входа-image), мусор отсеивается
    res = ir.put_main_models(ir.MainModelsBody(models=[
        "google/nano-banana-2", "HiDream-ai/HiDream-I1", "no/such",
    ]))
    assert res["models"] == ["google/nano-banana-2", "HiDream-ai/HiDream-I1"], res
    assert res["skipped"] == ["no/such"], res
    saved = json.loads((tmp / "data" / "imagerouter_main_models.json").read_text(encoding="utf-8"))["models"]
    assert saved == res["models"]
    # пустой список разрешён (полное отключение генерации)
    res2 = ir.put_main_models(ir.MainModelsBody(models=[]))
    assert res2["models"] == [] and res2["skipped"] == []
    data = {"models": []}
    ir._add_ir_models(data)
    assert not [m for m in data["models"] if m["type"] == "main"]
    print("OK эндпоинты выбора (вкл. пустой список)")

    # --- 5. обратно к дефолту после удаления файла ---

    (tmp / "data" / "imagerouter_main_models.json").unlink()
    st = ir.get_main_models()
    assert st["all_by_default"] is True
    assert st["models"] == [m["id"] for m in CATALOG]
    print("OK возврат к «весь каталог»")

    print("\nВСЕ ТЕСТЫ OK")


if __name__ == "__main__":
    main()
