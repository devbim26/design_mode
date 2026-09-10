# -*- coding: utf-8 -*-
"""Тесты инструмента «Текст» (T): деплой идемпотентен, синтаксис JS
валиден, ключевые конструкции виджета на месте.

Запуск: venv\\Scripts\\python.exe tests\\test_text_tool.py
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
        sir.deploy_text_tool(dist)
        changed_again = sir.deploy_text_tool(dist)
        s = (dist / "index.html").read_text(encoding="utf-8")
        assert s.count('src="/devbim-text-tool.js"') == 1, s
        assert "<script" in s and "</head>" in s
        assert (dist / "devbim-text-tool.js").exists()
        assert not changed_again, "повторный деплой не должен менять index.html"
    print("OK: деплой идемпотентен")


def test_widget_js_syntax():
    node = shutil.which("node")
    if not node:
        print("SKIP: node не найден")
        return
    r = subprocess.run(
        [node, "--check", str(sir.TEXT_TOOL_SRC)],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    print("OK: node --check devbim_text_tool.js")


def test_widget_key_constructs():
    s = sir.TEXT_TOOL_SRC.read_text(encoding="utf-8")
    # мост и менеджер
    assert "__devbimCanvasBridge" in s
    assert "getManager()" in s
    # ГРАБЛЯ: кэш абсолютного трансформа stage может быть NaN — координаты
    # считаем по АТРИБУТАМ stage (scaleX/x/y), без вызовов getAbsoluteTransform
    assert "stageXform" in s
    assert "getAbsoluteTransform().copy()" not in s, "кэш трансформа не читаем"
    assert "getAbsoluteTransform().point" not in s, "кэш трансформа не читаем"
    assert "isFinite" in s, "NaN-защита позиции"
    # рендер текста: измерение + заливка строк, baseline top
    assert "measureText" in s
    assert "textBaseline" in s and '"top"' in s
    assert "fillText" in s
    assert "1.25" in s, "межстрочный интервал"
    # upload: параметры обязаны идти в QUERY (грабля 6.2)
    assert "/api/v1/images/upload?image_category=other" in s
    # создание слоя ОДНИМ диспатчем через overrides (путь sentImageToCanvas)
    assert "addRasterLayer" in s
    assert "overrides" in s and "objects: [imageObject(dto)]" in s
    assert "isSelected: false" in s, "без рамки выделения (как у ✂-кусочков)"
    # правка: entityRasterized + синхронизация имени слоя
    assert 'canvas/entityRasterized' in s
    assert 'canvas/entityNameChanged' in s
    assert "replaceObjects: true" in s
    # реестр localStorage по id СЛОЯ (переживает bbox-растеризацию)
    assert '"devbimTextLayers"' in s
    assert "OBJ_PREFIX" in s and '"image_devbimtext_"' in s
    # превью нового текста — не перехватывает события
    assert "pointer-events:none" in s
    # плавный драг текстовых слоёв — своя обёртка, цепочится после ✂
    assert "ensureSmoothPatch" in s and "ourTextDragging" in s
    assert "__devbimTextSmooth" in s
    assert "isDragging()" in s
    # клавиатура: Esc — закрыть, Ctrl+Enter — добавить/применить
    assert '"Escape"' in s and '"Enter"' in s and "ctrlKey" in s
    # рейка ищется по хоткеям (B)/(E), а не по локализованным подписям
    assert "\\(B\\)" in s and "\\(E\\)" in s
    # иконка T — 1em, как у штатных иконок рейки
    assert 'viewBox="0 0 24 24" width="1em" height="1em"' in s
    # отладка
    assert "window.__devbimText" in s
    print("OK: ключевые конструкции виджета на месте")


def test_no_stale_state_read():
    """canvas-слайс в redux-undo: читаем только через canvas.present."""
    s = sir.TEXT_TOOL_SRC.read_text(encoding="utf-8")
    assert "c.present ? c.present : c" in s
    print("OK: чтение состояния через present")


if __name__ == "__main__":
    test_deploy_idempotent()
    test_widget_js_syntax()
    test_widget_key_constructs()
    test_no_stale_state_read()
    print("Все тесты пройдены")
