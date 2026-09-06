# -*- coding: utf-8 -*-
"""Тесты улучшений ИИ-рендеринга IFC-вьювера (06.09, ночь):
контактная тень в снимке, BIM-контекст промта, панель «Камера»
(FOV, вертикали, горизонт, орто-фасад, рамка кадра).

Запуск: venv\\Scripts\\python.exe tests\\test_ifc_ai_render.py
"""
import re
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
SRC = BASE / "ifc" / "ifcviewer.html"
DIST = BASE / "venv" / "Lib" / "site-packages" / "invokeai" / "frontend" / "web" / "dist" / "ifcviewer.html"


def module_script(html: str) -> str:
    m = re.search(r"<script type=\"module\">(.*?)</script>", html, re.S)
    assert m, "module-скрипт не найден"
    return m.group(1)


def test_camera_markup() -> None:
    s = SRC.read_text(encoding="utf-8")
    for frag in (
        'id="btn-camera"',        # кнопка «📷 ▾»
        'id="campanel"',          # панель «Камера»
        'id="cam-fov"',           # ползунок FOV
        'id="cam-verticals"',     # вертикали (двухточечная)
        'id="cam-horizon"',       # горизонт орбиты
        'id="cam-ortho"',         # орто-фасад
        'id="cam-persp"',         # возврат в перспективу
        'id="cam-guide"',         # рамка кадра
        'id="cropguide"',         # оверлей рамки
    ):
        assert frag in s, f"нет фрагмента {frag}"


def test_camera_logic() -> None:
    js = module_script(SRC.read_text(encoding="utf-8"))
    # FOV пишется в перспективную камеру
    assert "threePersp.fov = Number(fovSlider.value)" in js
    assert "threePersp.updateProjectionMatrix()" in js
    # вертикали: pitch -> 0 только в FP; горячая V
    assert "fpState.pitch = 0" in js and 'e.code === "KeyV"' in js
    # горизонт: полярный угол 90° при сохранении дистанции
    assert "horiz.normalize().multiplyScalar(off.length())" in js
    # орто-фасад: нормаль последнего клика либо ось к камере, y гасится
    # (СТРОКА проекции — "Orthographic", не "Ortho": чужое слово уходит в персп.)
    assert "lastHitNormal" in js and "n.y = 0" in js
    assert 'projection.set("Orthographic")' in js and 'projection.set("Perspective")' in js
    assert "world.camera.fit(model.object.children)" in js
    # рамка: кроп в renderSnapshot по прямоугольнику оверлея
    assert "cropGuide.getBoundingClientRect()" in js
    assert "drawImage(src, sx, sy, sw, sh," in js


def test_shadow() -> None:
    js = module_script(SRC.read_text(encoding="utf-8"))
    # проекция нижних углов bbox + эллипс до наложения WebGL-кадра
    assert "projectGroundRect" in js
    assert "box.min.y, gz" in js
    assert "drawShadowEllipse" in js
    assert "ctx.drawImage(src, sx, sy, sw, sh" in js
    # тень отключена в FP (интерьер от глаз) и рисуется до кадра
    assert "if (model && !fpState.active)" in js
    # за камерой / вне кадра — нет тени
    assert "sub(camPos).dot(camDir) <= 0" in js


def test_prompt_context() -> None:
    s = SRC.read_text(encoding="utf-8")
    js = module_script(s)
    # карта предков: этаж/помещение, имена одним пакетным getItemsData
    assert "IFCBUILDINGSTOREY" in js and '"IFCSPACE"' in js
    assert "getItemsData(list, { attributesDefault: true })" in js
    assert "LongName?.value ?? item?.Name?.value" in js
    # источник: элемент постановки человека (обновляется при ходьбе) или выделение
    assert "personCtxId = res?.localId ?? ctxLocalId" in js
    assert "placePerson(x, y, z, ctxLocalId = null)" in js.replace("async function ", "")
    # строка контекста и буфер обмена при снимке
    assert 'BIM context: ' in js
    assert "copyContextToClipboard();" in js
    assert "navigator.clipboard?.writeText" in js
    # поле в панели человека
    assert 'id="person-context"' in s and 'id="person-ctx"' in s


def test_deployed() -> None:
    assert DIST.exists(), "ifcviewer.html не развернут (setup_ifcviewer.py)"
    src = SRC.read_text(encoding="utf-8")
    dep = DIST.read_text(encoding="utf-8")
    assert src == dep, "dist/ifcviewer.html отличается от исходника — перезапустите setup_ifcviewer.py"


if __name__ == "__main__":
    test_camera_markup()
    print("OK test_camera_markup")
    test_camera_logic()
    print("OK test_camera_logic")
    test_shadow()
    print("OK test_shadow")
    test_prompt_context()
    print("OK test_prompt_context")
    test_deployed()
    print("OK test_deployed")
    print("ВСЕ ТЕСТЫ OK")
