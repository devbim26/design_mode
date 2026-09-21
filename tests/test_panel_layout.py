# -*- coding: utf-8 -*-
"""Тесты компоновки левой панели (решение 19.09): секция «Генерация»
(выбор модели) выше секции «Изображение», без бейджа базы фейковой
модели (sdxl), без строки Seed (Seed/Random/Shuffle Seed) и пометки
«Manual Seed» в бейджах; виджет описания модели (devbim-model-info.js)
развёрнут и подключён; серверное описание модели обогащено (форматы,
«до NK», слово «редактирование» сохранено для гейта фолбэка).

Запуск: venv\\Scripts\\python.exe tests\\test_panel_layout.py
"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import setup_imagerouter as sir


def test_deploy_model_info_idempotent():
    with tempfile.TemporaryDirectory() as td:
        dist = Path(td)
        (dist / "index.html").write_text(
            "<html><head><title>t</title></head><body></body></html>",
            encoding="utf-8",
        )
        sir.deploy_model_info(dist)
        changed_again = sir.deploy_model_info(dist)
        s = (dist / "index.html").read_text(encoding="utf-8")
        assert s.count('src="/devbim-model-info.js"') == 1, s
        assert (dist / "devbim-model-info.js").exists()
        assert not changed_again, "повторный деплой не должен менять index.html"
    print("OK: деплой описания модели идемпотентен")


def test_widget_js_syntax_and_content():
    node = shutil.which("node")
    src = sir.SRC / "devbim_model_info.js"
    js = src.read_text(encoding="utf-8")
    # аккордеон Generation + описание из конфига модели (как в гейте фолбэка)
    assert 'data-testid="generation-accordion"' in js, js
    assert "/api/v2/models/i/" in js, js
    assert "__devbimPEStore" in js and "__devbimCanvasBridge" in js, js
    assert "imagerouter/" in js, "локальные модели скрываем"
    if node:
        r = subprocess.run([node, "--check", str(src)], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        print("OK: node --check devbim_model_info.js")
    else:
        print("SKIP: node не найден")
    print("OK: содержимое виджета описания")


def test_panel_layout_fragments_applied():
    """В живом бандле все NEW-фрагменты на месте, OLD — отсутствуют."""
    targets = [
        f for f in sir.DIST.glob("assets/*.js")
        if 'displayName="ParametersPanelGenerate"' in f.read_text(encoding="utf-8")
    ]
    assert len(targets) == 1, [t.name for t in targets]
    s = targets[0].read_text(encoding="utf-8")
    pairs = (
        (sir.JS_SWAP_GENERATE_OLD, sir.JS_SWAP_GENERATE_NEW, "своп Generate"),
        (sir.JS_SWAP_CANVAS_OLD, sir.JS_SWAP_CANVAS_NEW, "своп Canvas"),
        (sir.JS_BASE_BADGE_OLD, sir.JS_BASE_BADGE_NEW, "бейдж базы"),
        (sir.JS_SEED_GENERATE_OLD, sir.JS_SEED_GENERATE_NEW, "Seed Generate"),
        (sir.JS_SEED_CANVAS_OLD, sir.JS_SEED_CANVAS_NEW, "Seed Canvas"),
        (sir.JS_BADGE_SEED_GEN_OLD, sir.JS_BADGE_SEED_GEN_NEW, "Manual Seed Generate"),
        (sir.JS_BADGE_SEED_CANVAS_OLD, sir.JS_BADGE_SEED_CANVAS_NEW, "Manual Seed Canvas"),
    )
    for old, new, title in pairs:
        assert old not in s, f"{title}: старый фрагмент всё ещё в бандле"
        assert new in s, f"{title}: нового фрагмента нет"
    print("OK: компоновка панели применена (своп, без sdxl-бейджа, без Seed)")


def test_panel_layout_on_fake_fresh_bundle():
    """patch_panel_layout на «свежем» бандле (после patch_left_panel):
    идемпотентность и миграция старого состояния."""
    fresh = (
        "const x=1;"
        # панель Generate после patch_left_panel (дети уже обрезаны)
        + sir.JS_SWAP_GENERATE_OLD + ';c.displayName="ParametersPanelGenerate";'
        # панель Canvas — аналогично
        + sir.JS_SWAP_CANVAS_OLD + ';d.displayName="ParametersPanelCanvas";'
        # аккордеоны/бейджи
        + "const y=1;(" + sir.JS_BASE_BADGE_OLD + ");"
        + "q(" + sir.JS_SEED_GENERATE_OLD + ')});Aoe.displayName="X";'
        + "w(" + sir.JS_SEED_CANVAS_OLD + 'label:e("accordions.advanced.options")'
        + "const a=[];(" + sir.JS_BADGE_SEED_GEN_OLD + ");"
        + "(" + sir.JS_BADGE_SEED_CANVAS_OLD + ");export{x};"
    )
    with tempfile.TemporaryDirectory() as td:
        dist = Path(td)
        assets = dist / "assets"
        assets.mkdir()
        f = assets / "App-fake.js"
        f.write_text(fresh, encoding="utf-8")
        sir.patch_panel_layout.__globals__["DIST"] = dist
        try:
            changed = sir.patch_panel_layout()
            assert changed, "первый прогон должен патчить"
            s = f.read_text(encoding="utf-8")
            assert sir.JS_SWAP_GENERATE_NEW in s and sir.JS_SEED_GENERATE_NEW in s, s
            # повторный прогон — пропуск без ошибок
            changed2 = sir.patch_panel_layout()
            assert not changed2, "второй прогон должен пропускать"
        finally:
            sir.patch_panel_layout.__globals__["DIST"] = sir.DIST
    print("OK: patch_panel_layout на свежем бандле + идемпотентность")


def test_description_enrichment():
    """Описание фейковой модели: слово «редактирование» (гейт фолбэка),
    форматы, дайджест размеров; без цены."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "imagerouter"))
    import imagerouter_router as ir  # noqa: E402

    m = {
        "id": "test/vendor-model",
        "architecture": {"input_modalities": ["text", "image"], "output_modalities": ["image"]},
        "supported_parameters": ["size"],
        "parameters": {"size": ["1024x1024", "3136x1344", "custom"]},
        "pricing": {"min": 0.01, "average": 0.02, "max": 0.03},
    }
    cfg = ir._ir_fake_config(m)
    d = cfg["description"]
    assert "Облачная генерация изображений" in d, d
    assert "редактирование" in d, "гейт Generate-фолбэка опирается на слово «редактирование»"
    assert "PNG, JPEG, WebP" in d, d
    assert "до 3K (3136×1344)" in d, d
    assert "произвольный размер" in d, d
    assert "$" not in d and "цена" not in d, "цену пользователю не показываем (решение 08.09)"

    # без image-входа — без «редактирования»; sizes только fixed
    m2 = {
        "id": "test/pure-txt",
        "architecture": {"input_modalities": ["text"], "output_modalities": ["image"]},
        "parameters": {"size": ["512x512"]},
    }
    d2 = ir._ir_fake_config(m2)["description"]
    assert "редактирование" not in d2, d2
    assert "до 1K (512×512)" in d2, d2
    assert "произвольный" not in d2, d2

    # sizes пустые/кривые — дайджест пустой, описание не падает
    m3 = {"id": "test/none", "architecture": {}, "parameters": {"size": ["auto", "weird"]}}
    d3 = ir._ir_fake_config(m3)["description"]
    assert "до" not in d3 and "произвольный" not in d3, d3
    # 5K+ округляется честно (nano-banana-pro 5056 -> 5K)
    m4 = {"id": "test/big", "architecture": {}, "parameters": {"size": ["5056x3392"]}}
    assert "до 5K (5056×3392)" in ir._ir_fake_config(m4)["description"]
    print("OK: описание модели (возможности/форматы/размер, «редактирование» сохранено)")


if __name__ == "__main__":
    test_deploy_model_info_idempotent()
    test_widget_js_syntax_and_content()
    test_panel_layout_fragments_applied()
    test_panel_layout_on_fake_fresh_bundle()
    test_description_enrichment()
    print("ВСЕ ТЕСТЫ OK")
