# -*- coding: utf-8 -*-
"""Тесты тумблера «Маска / Слой»: деплой идемпотентен, синтаксис JS валиден.

Запуск: venv\\Scripts\\python.exe tests\\test_mask_toggle.py
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
        sir.deploy_mask_toggle(dist)
        changed_again = sir.deploy_mask_toggle(dist)
        s = (dist / "index.html").read_text(encoding="utf-8")
        assert s.count('src="/devbim-mask-toggle.js"') == 1, s
        assert "<script" in s and "</head>" in s
        assert (dist / "devbim-mask-toggle.js").exists()
        assert not changed_again, "повторный деплой не должен менять index.html"
    print("OK: деплой идемпотентен")


def test_widget_js_syntax():
    node = shutil.which("node")
    if not node:
        print("SKIP: node не найден")
        return
    r = subprocess.run(
        [node, "--check", str(sir.SRC / "devbim_mask_toggle.js")],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    print("OK: node --check devbim_mask_toggle.js")


def test_bridge_patch_idempotent():
    with tempfile.TemporaryDirectory() as td:
        b = Path(td) / "App-fake.js"
        b.write_text(
            'const q=1;const cue=u.memo((e=>e));export{cue};,ru=De(null)',
            encoding="utf-8",
        )
        assert sir.patch_canvas_bridge(b) is True
        assert sir.patch_canvas_bridge(b) is False  # повторный запуск — пропуск
        s2 = b.read_text(encoding="utf-8")
        assert s2.count("__devbimCanvasBridge") == 1, s2
        assert s2.count("const cue=u.memo(") == 1, s2
        assert s2.index("window.__devbimCanvasBridge") < s2.index("const cue=u.memo(")
        assert (Path(td) / "App-fake.js.imagerouter-bak").exists()
    print("OK: патч моста идемпотентен, якорь сохранён")


if __name__ == "__main__":
    test_deploy_idempotent()
    test_widget_js_syntax()
    test_bridge_patch_idempotent()
