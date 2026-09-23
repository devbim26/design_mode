# -*- coding: utf-8 -*-
"""Тесты уборки локальных элементов UI (решение 21.09, п.50): в поле промта
нет вертикальной группы иконок (добавить триггер {x}, SDXL-concat, предпросмотр
динамических промтов, добавление отрицательного промта — во ВСЕХ полях
промта), в панели слоёв холста нет строки Denoising Strength (облако силу
денойза не использует; в граф уходит дефолт 0.75, роутер его игнорирует).

Запуск: venv\\Scripts\\python.exe tests\\test_ui_cleanup.py
"""
import tempfile
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import setup_imagerouter as sir


def test_fragments_applied():
    """В живом бандле OLD-фрагменты отсутствуют, компоненты целы."""
    targets = [
        f for f in sir.DIST.glob("assets/*.js")
        if 'displayName="ParamPositivePrompt"' in f.read_text(encoding="utf-8")
    ]
    assert len(targets) == 1, [t.name for t in targets]
    s = targets[0].read_text(encoding="utf-8")
    olds = (
        (sir.JS_PROMPT_ICONS_GROUP_OLD, "иконки в поле промта (positive)"),
        (sir.JS_PROMPT_ICONS_NEG_OLD, "иконка {x} (negative)"),
        (sir.JS_PROMPT_ICONS_SDXL_OLD, "иконки {x} (SDXL-стили)"),
        (sir.JS_CANVAS_DENOISE_OLD, "Denoising Strength (панель слоёв)"),
    )
    for old, title in olds:
        assert old not in s, f"{title}: фрагмент всё ещё в бандле"
    # сами компоненты и панель слоёв живы (удаляли только ряды/группы)
    assert s.count('displayName="ParamPositivePrompt"') == 1
    assert s.count('displayName="CanvasLayersPanel"') == 1
    assert sir.JS_CANVAS_DENOISE_NEW in s, "строки сущностей панели слоёв нет"
    assert 'displayName="ParamDenoisingStrength"' in s, (
        "компонент DenoisingStrength должен остаться определённым (мёртвый код)")
    print("OK: иконки промта и Denoising Strength убраны из живого бандла")


def test_patch_on_fake_fresh_bundle():
    """patch_remove_local_ui на «свежем» бандле: патчит + идемпотентен."""
    fresh = (
        "const x=1;"
        + sir.JS_PROMPT_ICONS_GROUP_OLD + 'X5.displayName="ParamPositivePrompt";'
        + "z(" + sir.JS_PROMPT_ICONS_NEG_OLD + ");"
        + "q(" + sir.JS_PROMPT_ICONS_SDXL_OLD + 'neg");'
        + "q(" + sir.JS_PROMPT_ICONS_SDXL_OLD + 'pos");'
        + "wY(" + sir.JS_CANVAS_DENOISE_OLD + ')}});wY.displayName="CanvasLayersPanel";'
        + "export{x};"
    )
    with tempfile.TemporaryDirectory() as td:
        dist = Path(td)
        assets = dist / "assets"
        assets.mkdir()
        f = assets / "App-fake.js"
        f.write_text(fresh, encoding="utf-8")
        sir.patch_remove_local_ui.__globals__["DIST"] = dist
        try:
            changed = sir.patch_remove_local_ui()
            assert changed, "первый прогон должен патчить"
            s = f.read_text(encoding="utf-8")
            assert "o.jsx(Fu," not in s, "кнопки триггеров в полях промта должны исчезнуть"
            assert sir.JS_PROMPT_ICONS_NEG_NEW in s
            assert sir.JS_PROMPT_ICONS_SDXL_NEW in s
            assert sir.JS_CANVAS_DENOISE_NEW in s
            assert "!e&&o.jsx(mq,{})" in s and "o.jsx(SY,{})" not in s
            # повторный прогон — пропуск без ошибок
            changed2 = sir.patch_remove_local_ui()
            assert not changed2, "второй прогон должен пропускать"
        finally:
            sir.patch_remove_local_ui.__globals__["DIST"] = sir.DIST
    print("OK: patch_remove_local_ui на свежем бандле + идемпотентность")


if __name__ == "__main__":
    test_fragments_applied()
    test_patch_on_fake_fresh_bundle()
    print("ALL OK")
