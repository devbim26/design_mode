# -*- coding: utf-8 -*-
"""Тесты кнопок «Prompt Assistant» / «3D Design» (правый угол баннера):
деплой идемпотентен, патч хоста v2 ставится и мигрирует V1, синтаксис JS валиден.

Запуск: venv\\Scripts\\python.exe tests\\test_topright_buttons.py
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
        sir.deploy_topright_buttons(dist)
        changed_again = sir.deploy_topright_buttons(dist)
        s = (dist / "index.html").read_text(encoding="utf-8")
        assert s.count('src="/devbim-topright-buttons.js"') == 1, s
        assert "<script" in s and "</head>" in s
        assert (dist / "devbim-topright-buttons.js").exists()
        assert not changed_again, "повторный деплой не должен менять index.html"
    print("OK: деплой идемпотентен")


def test_widget_js_syntax_and_content():
    node = shutil.which("node")
    src = sir.SRC / "devbim_topright_buttons.js"
    js = src.read_text(encoding="utf-8")
    # кнопки с текстом, высота как у Generate (36px), правый угол левой панели
    assert "Prompt Assistant" in js and "3D Design" in js, js
    assert "height:36px" in js, js
    assert "findQueueRow" in js and "chakra-numberinput" in js, js  # ряд очереди
    assert "__devbimPromptEnhance" in js and "__devbimPEPending" in js, js
    assert "devbim-banner" not in js, "кнопки живут в левой панели, не в баннере"
    # адаптивность: мало места -> компактный вид (звёздочка + «3D»), не исчезают
    assert "devbim-tr-compact" in js and "FULL_NEED" in js, js
    assert 'data-short' in js and "'3D'" in js, js  # короткая подпись компактного вида
    assert "min-width:14px" in js, js  # при жуткой тесноте — полоски, но видны
    if node:
        r = subprocess.run([node, "--check", str(src)], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        print("OK: node --check devbim_topright_buttons.js")
    else:
        print("SKIP: node не найден")
    print("OK: содержимое виджета")


def _fake_fresh() -> str:
    return (
        'const x=1;const m7="Generate",pne=u.memo(()=>1);'
        'o.jsx(mt,{})]})})]})});pne.displayName="InvokeQueueBackButton";export{pne};'
    )


def _fake_v1() -> str:
    return (
        sir.JS_PE_BTN
        + 'const m7="Generate",pne=u.memo(()=>1);'
        'o.jsx(mt,{})]})}),o.jsx(DevbimPEBtn,{})]})});pne.displayName="InvokeQueueBackButton";'
    )


def test_patch_fresh_and_idempotent():
    with tempfile.TemporaryDirectory() as td:
        b = Path(td) / "App-fake.js"
        b.write_text(_fake_fresh(), encoding="utf-8")
        assert sir.patch_prompt_enhance_button(b) is True
        assert sir.patch_prompt_enhance_button(b) is False  # повторный запуск — пропуск
        s = b.read_text(encoding="utf-8")
        assert s.count("DevbimPEWatch") == 2, s  # определение + вставка в ряд
        assert "DevbimPEBtn" not in s, s
        assert s.count("window.__devbimPromptEnhance=") == 1, s
        assert s.count("const m7=\"Generate\",pne=u.memo(") == 1, s  # якорь сохранён
        assert s.index("window.__devbimPromptEnhance") < s.index('const m7="Generate"')
        assert (Path(td) / "App-fake.js.imagerouter-bak").exists()
    print("OK: патч хоста v2 на свежем бандле, идемпотентен")


def test_patch_migrates_v1():
    with tempfile.TemporaryDirectory() as td:
        b = Path(td) / "App-fake.js"
        b.write_text(_fake_v1(), encoding="utf-8")
        assert sir.patch_prompt_enhance_button(b) is True
        assert sir.patch_prompt_enhance_button(b) is False  # повторный запуск — пропуск
        s = b.read_text(encoding="utf-8")
        assert "DevbimPEBtn" not in s, s
        assert s.count("DevbimPEWatch") == 2, s
        assert s.count("window.__devbimPromptEnhance=") == 1, s
        assert (Path(td) / "App-fake.js.imagerouter-bak").exists()
    print("OK: миграция V1 (кнопка в ряду Generate) -> V2 (хост + виджет)")


if __name__ == "__main__":
    test_deploy_idempotent()
    test_widget_js_syntax_and_content()
    test_patch_fresh_and_idempotent()
    test_patch_migrates_v1()
