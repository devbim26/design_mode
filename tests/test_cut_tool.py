# -*- coding: utf-8 -*-
"""Тесты инструмента «Вырезать по контуру» (✂): деплой идемпотентен,
синтаксис JS валиден, ключевые конструкции виджета на месте.

Запуск: venv\\Scripts\\python.exe tests\\test_cut_tool.py
"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import setup_imagerouter as sir


def test_deploy_idempotent():
    with tempfile.TemporaryDirectory() as td:
        dist = Path(td)
        (dist / "index.html").write_text(
            "<html><head><title>t</title></head><body></body></html>",
            encoding="utf-8",
        )
        sir.deploy_cut_tool(dist)
        changed_again = sir.deploy_cut_tool(dist)
        s = (dist / "index.html").read_text(encoding="utf-8")
        assert s.count('src="/devbim-cut-tool.js"') == 1, s
        assert "<script" in s and "</head>" in s
        assert (dist / "devbim-cut-tool.js").exists()
        assert not changed_again, "повторный деплой не должен менять index.html"
    print("OK: деплой идемпотентен")


def test_widget_js_syntax():
    node = shutil.which("node")
    if not node:
        print("SKIP: node не найден")
        return
    r = subprocess.run(
        [node, "--check", str(sir.CUT_TOOL_SRC)],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    print("OK: node --check devbim_cut_tool.js")


def test_widget_key_constructs():
    s = sir.CUT_TOOL_SRC.read_text(encoding="utf-8")
    # мост и менеджер
    assert "__devbimCanvasBridge" in s
    assert "getManager()" in s
    # экранные <-> документы через трансформ stage
    assert "getAbsoluteTransform" in s
    # растеризация слоя штатным рендерером
    assert "renderer.getCanvas" in s
    # маскирование куска полигоном (исходник НЕ трогаем — дырки нет)
    assert "destination-in" in s
    assert "destination-out" not in s, "источник больше не стирается"
    # upload: параметры обязаны идти в QUERY (грабля 6.2)
    assert "/api/v1/images/upload?image_category=other" in s
    # диспетчи канвас-слайса (живое состояние в canvas.present)
    assert 'canvas/entityRasterized' in s
    assert "addRasterLayer" in s
    # новый слой поверх, БЕЗ выделения (нет рамки-обводки вокруг кусочка)
    assert s.count("isSelected: false") >= 3, s.count("isSelected: false")
    assert "isSelected: true" not in s, "автовыделение включает рамку выделения"
    # режим: минимум 3 точки, Enter/Esc/Ctrl+C, замыкание у первой точки
    assert "points.length < 3" in s
    assert '"Enter"' in s and '"Escape"' in s
    assert '(e.key === "c" || e.key === "C")' in s
    # Ctrl+V — вставка копии последнего кусочка (глобальный перехват)
    assert '(e.key !== "v" && e.key !== "V")' in s
    assert "lastCut" in s and "pastePiece" in s
    # поля ввода не перехватываем
    assert 't.tagName === "TEXTAREA"' in s
    # плавное перемещение кусочков: пока тащат наш кусочек — сетка 1 px
    assert "ensureSmoothPatch" in s and "ourPieceDragging" in s
    assert 'indexOf("image_devbimcut_") === 0' in s
    assert "isDragging()" in s
    # иконка ✂ — как у штатных иконок (1em), не растянута на кнопку
    assert 'viewBox="0 0 24 24" width="1em" height="1em"' in s
    # при активных ножницах прочие кнопки-инструменты выглядят неактивными
    assert "devbim-cut-mode" in s and "devbim-cut-rail" in s
    # клик по другому инструменту завершает режим ножниц
    assert "onRailOtherTool" in s
    # рейка ищется по хоткеям (B)/(E), а не по локализованным подписям
    assert "\\(B\\)" in s and "\\(E\\)" in s
    # перехват событий в capture-фазе (konva не получает клики)
    assert "addEventListener(\"pointerdown\", onPointerDown, true)" in s
    # отладка
    assert "window.__devbimCut" in s
    print("OK: ключевые конструкции виджета на месте")


def test_no_stale_state_read():
    """canvas-слайс в redux-undo: читаем только через canvas.present."""
    s = sir.CUT_TOOL_SRC.read_text(encoding="utf-8")
    assert "c.present ? c.present : c" in s
    print("OK: чтение состояния через present")


if __name__ == "__main__":
    test_deploy_idempotent()
    test_widget_js_syntax()
    test_widget_key_constructs()
    test_no_stale_state_read()
    print("Все тесты пройдены")
