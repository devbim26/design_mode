# -*- coding: utf-8 -*-
"""Тесты моста вьюверы -> холст V3 (п.56): без слоя маски, рамка 3:2 + fit.

Проверяет:
  1. setup_ifcviewer.py содержит JS_BRIDGE_V3 (withInpaintMask:!1, экшен
     canvas/bboxAspectRatioIdChanged c id 3:2, fitToBboxContain) и держит
     V1/V2 для миграции уже пропатченных бандлов;
  2. миграция V2 -> V3 применяется к «бандлу» (миграция V1 -> V3 тоже);
  3. синтаксис V3 валиден (node --check);
  4. подсказки кнопок/тостов вьюверов (IFC/PDF/Design Code) больше не
     обещают слой inpaint-маски и кисть;
  5. кнопка «Редактировать» (Edit) в Image Viewer переведена на V3
     (JS_EDIT_HOOK_V3 в setup_ifcviewer.py: без маски/кисти, 3:2 + fit,
     миграция + идемпотентность + синтаксис).

Запуск: venv\\Scripts\\python.exe tests\\test_canvas_bridge_v3.py
"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import setup_ifcviewer as siv


def test_bridge_v3_contents():
    v3 = siv.JS_BRIDGE_V3
    assert 'withInpaintMask:!1' in v3, "V3 не должен создавать слой маски"
    assert 'withInpaintMask:!0' not in v3
    assert 'tool.$tool.set("brush")' not in v3, "V3 не должен включать кисть"
    assert 'canvas/bboxAspectRatioIdChanged' in v3, "V3 должен ставить ratio"
    assert 'payload:{id:"3:2"}' in v3, "ratio по умолчанию — 3:2"
    assert 'fitToBboxContain' in v3, "V3 должен вписывать слой в рамку"
    assert 'applyTransform' in v3 and 'startTransform' in v3
    # порядок: экшен ratio ПОСЛЕ sentImageToCanvas (иначе bboxChangedFromCanvas
    # сбросит id в Free), fit — после экшена
    assert v3.index("_c({imageDTO:") < v3.index("bboxAspectRatioIdChanged") < v3.index("fitToBboxContain")
    # миграционные константы на месте
    assert 'withInpaintMask:!0' in siv.JS_BRIDGE_V2 and 'tool.$tool.set("brush")' in siv.JS_BRIDGE_V2
    assert 'withInpaintMask:!1' in siv.JS_BRIDGE_V1 and 'bboxAspectRatioIdChanged' not in siv.JS_BRIDGE_V1
    print("OK: содержимое JS_BRIDGE_V3 + миграционные V1/V2")


def test_migrate_v2_v1_to_v3():
    anchor = 'const cue=u.memo('
    for old in (siv.JS_BRIDGE_V2, siv.JS_BRIDGE_V1):
        bundle = 'nel";' + old + anchor + 'X"})});'
        assert siv.JS_BRIDGE_V3 not in bundle
        patched = bundle.replace(old, siv.JS_BRIDGE_V3, 1)
        assert siv.JS_BRIDGE_V3 in patched
        assert old not in patched, "старый мост должен быть заменён целиком"
    print("OK: миграция V2/V1 -> V3")


def test_bridge_v3_js_syntax():
    node = shutil.which("node")
    if not node:
        print("SKIP: node не найден")
        return
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "bridge.js"
        p.write_text(siv.JS_BRIDGE_V3, encoding="utf-8")
        r = subprocess.run([node, "--check", str(p)],
                           capture_output=True, text=True, timeout=30)
        assert r.returncode == 0, r.stderr
    print("OK: синтаксис JS_BRIDGE_V3 валиден")


def test_imageviewer_edit_v3_contents():
    new, old = siv.JS_EDIT_HOOK_V3, siv.JS_EDIT_HOOK_OLD
    # нативный хук действительно «старый»: маска + кисть
    assert 'withInpaintMask:!0' in old and 'tool.$tool.set("brush")' in old
    assert 'withInpaintMask:!1' in new, "Edit не должен создавать слой маски"
    assert 'withInpaintMask:!0' not in new
    assert 'tool.$tool.set("brush")' not in new, "Edit не должен включать кисть"
    assert 'canvas/bboxAspectRatioIdChanged' in new, "Edit должен ставить ratio"
    assert 'payload:{id:"3:2"}' in new, "ratio по умолчанию — 3:2"
    assert 'fitToBboxContain' in new and 'applyTransform' in new and 'startTransform' in new
    assert 'SENT_TO_CANVAS' in new, "тост об отправке на холст сохраняется"
    # порядок: фокус холста (менеджер смонтируется) -> укладка -> ratio -> fit
    assert new.index('focusPanel("canvas"') < new.index('_c({imageDTO:')
    assert new.index('_c({imageDTO:') < new.index('bboxAspectRatioIdChanged') < new.index('fitToBboxContain')
    # форма хука сохранена: наружу тот же {edit, isEnabled}, те же зависимости
    assert new.startswith('Ize=e=>{') and new.endswith(',isEnabled:a}}')
    assert new.count('[e,a,n,s,i,t]') == 1
    # самодостаточность: store из Je() прямо в хуке, без __devbimIfcCtx
    assert '__devbimIfcCtx' not in new
    print("OK: содержимое JS_EDIT_HOOK_V3 (Edit в Image Viewer)")


def test_imageviewer_edit_migration():
    bundle = 'ste.displayName="DeleteImageButton";' + siv.JS_EDIT_HOOK_OLD + 'X"})});'
    assert siv.JS_EDIT_HOOK_V3 not in bundle
    patched = bundle.replace(siv.JS_EDIT_HOOK_OLD, siv.JS_EDIT_HOOK_V3, 1)
    assert siv.JS_EDIT_HOOK_V3 in patched
    assert siv.JS_EDIT_HOOK_OLD not in patched, "хук должен быть заменён целиком"
    # идемпотентность: на пропатченном бандле замена больше ничего не меняет
    assert patched.replace(siv.JS_EDIT_HOOK_OLD, siv.JS_EDIT_HOOK_V3, 1) == patched
    print("OK: миграция Edit -> V3 + идемпотентность")


def test_imageviewer_edit_js_syntax():
    node = shutil.which("node")
    if not node:
        print("SKIP: node не найден")
        return
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "edit.js"
        p.write_text(siv.JS_EDIT_HOOK_V3, encoding="utf-8")
        r = subprocess.run([node, "--check", str(p)],
                           capture_output=True, text=True, timeout=30)
        assert r.returncode == 0, r.stderr
    print("OK: синтаксис JS_EDIT_HOOK_V3 валиден")


def test_viewer_hints_no_mask():
    base = Path(__file__).resolve().parents[1]
    files = [
        base / "ifc" / "ifcviewer.html",
        base / "pdf" / "pdfviewer.html",
        base / "design_code" / "design_code_viewer.html",
    ]
    for f in files:
        s = f.read_text(encoding="utf-8")
        assert "inpaint mask" not in s, f"{f.name}: подсказка всё ещё обещает маску"
        assert "brush an inpaint mask" not in s, f.name
        assert "3:2 frame" in s, f"{f.name}: нет упоминания рамки 3:2"
    print("OK: подсказки вьюверов без маски, с рамкой 3:2")


if __name__ == "__main__":
    test_bridge_v3_contents()
    test_migrate_v2_v1_to_v3()
    test_bridge_v3_js_syntax()
    test_viewer_hints_no_mask()
    test_imageviewer_edit_v3_contents()
    test_imageviewer_edit_migration()
    test_imageviewer_edit_js_syntax()
    print("ВСЕ ТЕСТЫ OK")
