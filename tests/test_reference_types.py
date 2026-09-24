# -*- coding: utf-8 -*-
"""Тесты типов референсов (решение 21.09, спека
docs/superpowers/specs/2026-09-21-reference-types-design.md):

  - фронт: якоря патчей в живых бандлах применены (App: селектор
    «Тип референса» вместо Mode, без CLIP Vision/Begin-End, авто-вес;
    index: дефолт «Основной», zod-enum расширен);
  - фронт: patch_reference_types на синтетических бандлах (идемпотентность);
  - роутер: _extract_ir_info собирает тип/вес из узлов ip_adapter
    (включая дедупликацию), _reference_prompt_block дописывает роль и вес
    каждого референса с нумерацией массива image[];
  - согласованность дефолтных весов JS (авто-вес в UI) и Python (промт).

Запуск: venv\\Scripts\\python.exe tests\\test_reference_types.py
"""
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import setup_imagerouter as sir  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "imagerouter"))
import imagerouter_router as ir  # noqa: E402


def test_frontend_fragments_applied():
    """В живых бандлах патчи на месте, старые фрагменты отсутствуют."""
    app = [
        f for f in sir.DIST.glob("assets/*.js")
        if 'displayName="RefImageSettingsContent"' in f.read_text(encoding="utf-8")
    ]
    assert len(app) == 1, [f.name for f in app]
    s = app[0].read_text(encoding="utf-8")
    assert sir.JS_REF_METHOD_OLD not in s, "старый селектор Mode всё ещё в бандле"
    assert sir.JS_REF_METHOD_NEW in s, "селектора «Тип референса» нет"
    assert sir.JS_REF_CLIPVISION_OLD not in s, "CLIP Vision Model не убран из карточки"
    assert sir.JS_REF_BEGINEND_OLD not in s, "Begin/End % не убран из карточки"
    assert sir.JS_REF_METHOD_CB_NEW in s, "авто-вес при смене типа не установлен"
    # региональные настройки (другой компонент) не тронуты
    assert "o.jsx(MS,{beginEndStepPct:r.beginEndStepPct" in s

    idx = [
        f for f in sir.DIST.glob("assets/*.js")
        if sir.JS_REF_ENUM_NEW in f.read_text(encoding="utf-8")
        or sir.JS_REF_ENUM_OLD in f.read_text(encoding="utf-8")
    ]
    assert len(idx) == 1, [f.name for f in idx]
    s2 = idx[0].read_text(encoding="utf-8")
    assert sir.JS_REF_DEFAULT_NEW in s2, "дефолт новых референсов не «Основной»"
    assert sir.JS_REF_DEFAULT_OLD not in s2
    assert s2.count(sir.JS_REF_ENUM_NEW) == 2, "zod-enum должен быть расширен дважды"
    assert sir.JS_REF_ENUM_OLD not in s2
    print("OK: типы референсов применены в живых бандлах (App + index)")


def test_patch_on_fake_bundles():
    """patch_reference_types на «свежих» бандлах + идемпотентность."""
    app_fake = (
        "const x=1;" + sir.JS_REF_METHOD_OLD
        + ";const kne=1;" + sir.JS_REF_CLIPVISION_OLD + "y("
        + sir.JS_REF_METHOD_CB_OLD + ");"
        + "z(o.jsx(Cne,{})," + sir.JS_REF_BEGINEND_OLD + ");"
        + 'kne.displayName="RefImageSettingsContent";export{x};'
    )
    idx_fake = (
        "const rS={type:'ip_adapter',image:null,model:null,"
        + sir.JS_REF_DEFAULT_OLD + ",weight:1};"
        + "xe({image:Oc,method:" + sir.JS_REF_ENUM_OLD + "});"
        + "KJ=" + sir.JS_REF_ENUM_OLD + ";export{rS};"
    )
    with tempfile.TemporaryDirectory() as td:
        dist = Path(td)
        assets = dist / "assets"
        assets.mkdir()
        (assets / "App-fake.js").write_text(app_fake, encoding="utf-8")
        (assets / "index-fake.js").write_text(idx_fake, encoding="utf-8")
        sir.patch_reference_types.__globals__["DIST"] = dist
        try:
            assert sir.patch_reference_types(), "первый прогон должен патчить"
            s = (assets / "App-fake.js").read_text(encoding="utf-8")
            assert sir.JS_REF_METHOD_NEW in s and sir.JS_REF_METHOD_CB_NEW in s
            assert sir.JS_REF_CLIPVISION_OLD not in s and sir.JS_REF_BEGINEND_OLD not in s
            s2 = (assets / "index-fake.js").read_text(encoding="utf-8")
            assert sir.JS_REF_DEFAULT_NEW in s2
            assert s2.count(sir.JS_REF_ENUM_NEW) == 2
            # повторный прогон — пропуск без ошибок и правок
            assert not sir.patch_reference_types(), "второй прогон должен пропускать"
        finally:
            sir.patch_reference_types.__globals__["DIST"] = sir.DIST
    print("OK: patch_reference_types на свежих бандлах (идемпотентен)")


def _graph(nodes: dict) -> dict:
    return {"graph": {"nodes": nodes, "edges": []}}


def test_extract_ref_details():
    """Тип и вес референса читаются из узла ip_adapter; дубли и маска
    отфильтровываются вместе с метаданными."""
    nodes = {
        "ip_adapter_ref1": {
            "type": "ip_adapter",
            "method": "main",
            "weight": 1.0,
            "image": {"image_name": "ref_main.png"},
        },
        "ip_adapter_ref2": {
            "type": "ip_adapter",
            "method": "view3d",
            "weight": 2,
            "image": {"image_name": "ref_3d.png"},
        },
        "ip_adapter_dup": {
            "type": "ip_adapter",
            "method": "extra",
            "image": {"image_name": "ref_main.png"},  # дубль имени
        },
        "core_metadata": {"positive_prompt": "дом", "width": 1024, "height": 1024},
    }
    info = ir._extract_ir_info(_graph(nodes))
    assert info["references"] == ["ref_main.png", "ref_3d.png"], info["references"]
    assert [d["type"] for d in info["ref_details"]] == ["main", "view3d"]
    assert [d["weight"] for d in info["ref_details"]] == [1.0, 2]
    # вес отсутствует -> None (дефолт подставится в промте по типу)
    nodes2 = {
        "r": {"type": "ip_adapter", "method": "extra", "image": {"image_name": "a.png"}},
    }
    info2 = ir._extract_ir_info(_graph(nodes2))
    assert info2["ref_details"] == [{"image": "a.png", "type": "extra", "weight": None}]
    # старый/чужой method (сессия до патча) остаётся как есть
    nodes3 = {
        "r": {"type": "ip_adapter", "method": "full", "weight": 0.7, "image": {"image_name": "b.png"}},
    }
    info3 = ir._extract_ir_info(_graph(nodes3))
    assert info3["ref_details"][0]["type"] == "full"
    assert ir._ref_weight(info3["ref_details"][0]) == 0.7
    print("OK: _extract_ir_info собирает тип/вес референсов")


def test_reference_prompt_block():
    """Блок референсов: нумерация с исходником и без, вес из узла или
    дефолт типа, неизвестный тип — универсальная формулировка.
    Фикс 24.09: с исходником блок ОБЯЗАН приказывать модели сохранить
    геометрию/ракурс изображения 1 (без этого модель перерисовывала
    сцену с референса — жалоба «не видит фото из канваса») и заканчиваться
    гвардом «референсы не копировать целиком»."""
    meta = [
        {"image": "a.png", "type": "main", "weight": None},      # дефолт типа -> 1
        {"image": "b.png", "type": "view3d", "weight": 2.0},
        {"image": "c.png", "type": "extra", "weight": 0.15},     # пользователь подвинул
        {"image": "d.png", "type": "full", "weight": None},      # старая сессия
    ]
    with_init = ir._reference_prompt_block(meta, has_init=True)
    assert with_init.startswith(
        "\n\nПервое изображение — исходник для редактирования: сохрани"
    ), "первая строка должна приказывать сохранить геометрию исходника"
    assert "СТРОГО без изменений — это основа сцены" in with_init
    assert "Референсы не копируй целиком и не меняй ракурс сцены" in with_init
    assert "композиция и геометрия — строго с первого изображения" in with_init
    assert "не перебивая основной референс" not in with_init, (
        "заметка extra не должна ссылаться на несуществующий «основной референс»"
    )
    assert "Изображение 2 — основной референс (вес 1):" in with_init
    assert "Изображение 3 — 3D-ракурс (вес 2):" in with_init
    assert "Изображение 4 — дополнительный референс (вес 0.15):" in with_init
    assert "формы и цвета самой схемы не используй" in with_init
    assert "Изображение 5 — референс (общий): учитывай стиль и содержание этой картинки." in with_init
    assert "(вес" not in with_init.split("Изображение 5")[1].split("\n")[0], "без веса при неизвестном типе"
    # гвард идёт последней строкой блока (после всех ролей)
    assert with_init.strip().splitlines()[-1].startswith("Референсы не копируй")
    # вшитый оконный гвард (живой прогон 24.09: без приказа модель клеит
    # стекло на сплошную стену) — только при исходнике
    assert "ВАЖНО, ОКНА" in with_init
    assert "сквозными" in with_init and "ВНУТРИ проёма" in with_init
    assert "сплошную стену под стеклом" in with_init
    # замыкающий гвард усилен запретом изменений состава сцены
    assert "Ничего не добавляй, не убирай и не перемещай" in with_init

    no_init = ir._reference_prompt_block(meta[:1], has_init=False)
    assert "исходник" not in no_init
    assert "не меняй ракурс" not in no_init, "гвард про ракурс — только при исходнике"
    assert "ВАЖНО, ОКНА" not in no_init, "оконный гвард — только при исходнике"
    assert "Ничего не добавляй" not in no_init
    assert no_init.strip().startswith("Изображение 1 — основной референс (вес 1):")

    # исходник без референсов (снимок 3D + текстовый промт стиля):
    # гварды геометрии/окон вшиты, ролей и финального гварда референсов нет
    init_only = ir._reference_prompt_block([], has_init=True)
    assert init_only.startswith(
        "\n\nПервое изображение — исходник для редактирования: сохрани"
    )
    assert "ВАЖНО, ОКНА" in init_only
    assert "Изображение" not in init_only, "без референсов нумерованных ролей быть не должно"
    assert "Референсы не копируй" not in init_only
    print("OK: блок референсов в промте (роли, веса, нумерация, геометрия исходника)")


def test_js_py_weights_consistent():
    """Дефолтные веса типов в JS (авто-вес в UI) и в Python (промт) совпадают."""
    js = {}
    for m in re.finditer(r'(\w+):([\d.]+)', sir.JS_REF_TYPE_WEIGHTS_JS):
        js[m.group(1)] = float(m.group(2))
    assert js == {k: v["weight"] for k, v in ir.IR_REF_TYPES.items()}, (
        js,
        {k: v["weight"] for k, v in ir.IR_REF_TYPES.items()},
    )
    print("OK: веса типов согласованы между фронтом и роутером")


if __name__ == "__main__":
    test_frontend_fragments_applied()
    test_patch_on_fake_bundles()
    test_extract_ref_details()
    test_reference_prompt_block()
    test_js_py_weights_consistent()
    print("ВСЕ ТЕСТЫ OK")
