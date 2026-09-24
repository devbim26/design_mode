# -*- coding: utf-8 -*-
"""Тесты модернизации сечений IFC-вьювера (панель «Сечения», 06.09.2026).

Проверяется исходник ifc/ifcviewer.html и его деплой в dist:
  - новые элементы панели сечений на месте, старые кнопки удалены;
  - три типа сечений (горизонтальное, вертикальные X/Z);
  - скрытие плоскостей без отмены сечения (clipper.visible / plane.visible);
  - флип стороны отсечения и слайдер позиции;
  - обход библиотечного reset() (кватернион helper вместо lookAt).

Запуск: venv\\Scripts\\python.exe tests\\test_ifc_sections.py
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


def test_panel_markup() -> None:
    s = SRC.read_text(encoding="utf-8")
    for frag in (
        'id="btn-sections"',       # кнопка-переключатель панели в тулбаре
        'id="secpanel"',           # всплывающая панель
        'id="sec-add-h"',          # горизонтальное сечение
        'id="sec-add-x"',          # вертикальное X
        'id="sec-add-z"',          # вертикальное Z
        'id="sec-show-planes"',    # скрытие плоскостей (сечение остаётся)
        'id="sec-list"',           # список активных сечений
        'id="sec-del-all',         # удалить все
    ):
        assert frag in s, f"нет фрагмента {frag}"
    # старые кнопки единственного горизонтального сечения удалены
    assert 'id="btn-plane"' not in s, "старая кнопка btn-plane осталась"
    assert 'id="btn-planes-del"' not in s, "старая кнопка btn-planes-del осталась"


def test_sections_logic() -> None:
    js = module_script(SRC.read_text(encoding="utf-8"))
    # три типа сечений с нормалями -Y / ±X / ±Z
    assert 'new Vector3(0, -1, 0)' in js, "нет горизонтальной нормали (0,-1,0)"
    assert re.search(r"camPos\.x >= center\.x \? 1 : -1, 0, 0", js), "нет вертикальной нормали X со знаком камеры"
    assert re.search(r"0, 0, camPos\.z >= center\.z \? 1 : -1", js), "нет вертикальной нормали Z со знаком камеры"
    # скрытие плоскостей: глобальный тумблер и по-плоскостно
    assert "clipper.visible = !allPlanesVisible()" in js, "нет глобального тумблера clipper.visible"
    assert "plane.visible = !plane.visible" in js, "нет по-плоскостного тумблера видимости"
    # флип стороны отсечения
    assert "plane.normal.clone().negate()" in js, "нет флипа нормали"
    # слайдер двигает плоскость вдоль оси нормали
    assert re.search(r"p\[axis\] = v;", js), "слайдер не двигает плоскость"
    # после drag стрелкой слайдеры обновляются (в 3.4.8 у Event метод .add)
    assert "clipper.onAfterDrag.add(" in js, "нет подписки на onAfterDrag"
    # обход библиотечного reset(): ориентация helper кватернионом
    assert "setFromUnitVectors(Z_UNIT" in js, "нет setFromUnitVectors для ориентации helper"
    # сечения переживают перезагрузку модели (панель перерисовывается)
    assert "renderSecList();        # сечения переживают" in SRC.read_text(encoding="utf-8") or \
        "renderSecList();" in js, "renderSecList не вызывается"


def test_no_stale_api() -> None:
    js = module_script(SRC.read_text(encoding="utf-8"))
    # библиотечный setFromNormalAndCoplanarPoint у плоскости НЕ используется
    # (грабля 3.4.8: reset() ломает ориентацию helper при флипе к (1,0,0))
    assert not re.search(r"plane\.setFromNormalAndCoplanarPoint", js), \
        "используется библиотечный plane.setFromNormalAndCoplanarPoint"


def test_deployed() -> None:
    assert DIST.exists(), "ifcviewer.html не развернут в dist (запустите setup_ifcviewer.py)"
    src = SRC.read_text(encoding="utf-8")
    dep = DIST.read_text(encoding="utf-8")
    assert src == dep, "dist/ifcviewer.html отличается от исходника — перезапустите setup_ifcviewer.py"


def test_person_markup() -> None:
    s = SRC.read_text(encoding="utf-8")
    for frag in (
        'id="btn-person"',        # кнопка «👤 ▾» в тулбаре
        'id="personpanel"',       # всплывающая панель «Человек»
        'id="person-place"',      # постановка на перекрытие
        'id="person-eye"',        # вид от глаз 1,7 м
        'id="person-remove"',     # убрать человека
    ):
        assert frag in s, f"нет фрагмента {frag}"


def test_person_logic() -> None:
    js = module_script(SRC.read_text(encoding="utf-8"))
    # высота глаз 1.7 и силуэт 1.75
    assert "EYE_HEIGHT = 1.7" in js and "PERSON_H = 1.75" in js
    # привязка к перекрытию: вертикальный луч через временную камеру
    assert "snapToGround" in js and "new PerspectiveCamera(35, 1, 0.01, 60)" in js
    assert "cam.lookAt(x, y - 1, z)" in js, "временная камера должна смотреть строго вниз"
    # биллборд разворачивается к камере
    assert "billboardLoop" in js and "atan2(" in js
    # FP: сохранение позы/проекции, отключение controls, WASD
    assert "projection.set(fpState.saved.projection)" in js
    assert "controls.enabled = false" in js
    assert 'k.has("w") || k.has("up")' in js
    assert 'new Euler(fpState.pitch, fpState.yaw, 0, "YXZ")' in js
    # клик в режиме постановки ставит человека, а не выбирает элемент
    assert "if (placingPerson)" in js and "await placePerson(hit.point" in js
    # при загрузке ДРУГОЙ модели человек убирается
    assert "personModelName !== name" in js


def test_snapbar_tab_mode() -> None:
    """Нижняя панель «To Canvas / To Assets» видна и в ПОЛНОЦЕННОЙ вкладке
    IFC (не только в embed-панели на холсте), кнопки подключены всегда,
    тост работает в обоих режимах, IFE v2 держит __devbimIfcCtx."""
    s = SRC.read_text(encoding="utf-8")
    # CSS: snapbar показывается без embed-гейта; селектор моделей — только embed
    assert "body:not(.embed) #snapbar select{display:none}" in s, \
        "селектор моделей должен скрываться вне embed-режима"
    assert re.search(r"#snapbar\{\s*display:flex", s), \
        "snapbar должен быть видим по умолчанию (обе вкладки)"
    assert "body.embed #snapbar{display:flex}" not in s, \
        "старый embed-гейт snapbar удалён"
    js = module_script(s)
    # обработчики кнопок — до if (EMBED), т.е. работают в обоих режимах
    handlers = js.find('$("btn-snap").addEventListener')
    embed_block = js.find("if (EMBED) {")
    assert handlers != -1 and embed_block != -1 and handlers < embed_block, \
        "обработчики btn-snap/btn-snap-assets должны подключаться до if (EMBED)"
    assert "if (!EMBED) return;" not in js, \
        "тост embedToast не должен глушиться вне embed-режима"
    assert "toCanvasViaBridge" in js and "__devbimSendToCanvas" in js, \
        "фолбэк моста для старого App-бандла (страница без F5), исполнение в контексте приложения"
    # setup: IFE v2 захватывает контекст моста «To Canvas»
    import sys
    sys.path.insert(0, str(BASE))
    import setup_ifcviewer as si
    assert "__devbimIfcCtx=e" in si.JS_IFC_PANEL_V2 and 'unregisterTab("ifc")' in si.JS_IFC_PANEL_V2
    assert si.JS_IFC_PANEL_V2 != si.JS_IFC_PANEL and 'displayName="IFCTab"' in si.JS_IFC_PANEL
    # деплой: в App-бандле стоит IFE v2
    bundles = [f for f in (BASE / "venv" / "Lib" / "site-packages" / "invokeai" /
                           "frontend" / "web" / "dist").glob("assets/*.js")
               if 'displayName="TabContent"' in f.read_text(encoding="utf-8")]
    assert len(bundles) == 1, f"App-бандл найден {len(bundles)} раз"
    bundle = bundles[0].read_text(encoding="utf-8")
    assert si.JS_IFC_PANEL_V2 in bundle, \
        "в App-бандле нет IFE v2 (захват __devbimIfcCtx) — перезапустите setup_ifcviewer.py"


def test_ai_palette() -> None:
    s = SRC.read_text(encoding="utf-8")
    assert 'id="btn-palette"' in s, "нет кнопки AI-палитры в тулбаре"
    assert "#toolbar button.active" in s, "нет стиля активной кнопки тулбара"
    js = module_script(s)
    assert 'posX: "#F0A35C"' in js, "нет палитры шести корзин"
    assert "AI_SHELL_HEXES" in js and "AI_EXT_HEXES" in js, "нет hex-наборов оболочки"
    assert "dFdx(vAIWorld)" in js and "dFdy(vAIWorld)" in js, \
        "нет покраски по геометрической нормали грани"
    assert 'localStorage.getItem("devbim:ifc:aiPalette")' in js, "состояние не переживает F5"
    assert "aiPaletteState.on ? AI_PALETTE_LEGEND" in js, "легенда не копируется при снимке"
    assert "if (aiPaletteState.on) aiApply();" in js, "палитра не переживает загрузку модели"
    assert "if (aiPaletteState.on) aiEnsure();" in js, "нет самопроверки подмены при LOD"
    # init стреляет update синхронно → TDZ: объявление обязано стоять до слушателя камеры
    decl = js.find("const aiPaletteState")
    listener = js.find('controls.addEventListener("update"')
    assert decl != -1 and listener != -1 and decl < listener, \
        "const aiPaletteState объявлен после слушателя камеры — ReferenceError при синхронном update в init"
    assert "palette: {" in js, "нет отладочного __ifc.palette"
    # hex-контракт сборщик↔вьювер — держать синхронно при правке палитры
    import sys
    sys.path.insert(0, str(BASE))
    from threed.threed_build import INTERIOR_WALL_PALETTE, INTERIOR_DEFAULT_COLORS

    def viewer_hexes(name):
        m = re.search(re.escape(name) + r"\s*=\s*new Set\(\[(.*?)\]\)", js, re.S)
        assert m, f"во вьювере нет {name} = new Set([...])"
        return set(re.findall(r'"(#[0-9A-Fa-f]{6})"', m.group(1)))

    ext_js = viewer_hexes("AI_EXT_HEXES")
    shell_js = viewer_hexes("AI_SHELL_HEXES") | ext_js   # спред ...AI_EXT_HEXES
    expected_ext = {"#" + INTERIOR_WALL_PALETTE[k].lstrip("#").upper()
                    for k in INTERIOR_WALL_PALETTE if k[0] == "ext"}
    expected_shell = ({"#" + c.lstrip("#").upper()
                       for c in INTERIOR_WALL_PALETTE.values()}
                      | {INTERIOR_DEFAULT_COLORS["slab"].upper()})
    assert ext_js == expected_ext, \
        f"AI_EXT_HEXES разошлись с INTERIOR_WALL_PALETTE: {ext_js} != {expected_ext}"
    assert shell_js == expected_shell, \
        f"AI_SHELL_HEXES разошлись с палитрой сборщика: {shell_js} != {expected_shell}"


def test_module_syntax() -> None:
    import subprocess
    js = module_script(SRC.read_text(encoding="utf-8"))
    p = BASE / "tests" / "_threed_tmp" / "ifc_module.mjs"
    p.parent.mkdir(exist_ok=True)
    p.write_text(js, encoding="utf-8")
    r = subprocess.run(["node", "--check", str(p)], capture_output=True, text=True)
    assert r.returncode == 0, f"синтаксис module-скрипта: {r.stderr[:400]}"


if __name__ == "__main__":
    test_panel_markup()
    print("OK test_panel_markup")
    test_sections_logic()
    print("OK test_sections_logic")
    test_no_stale_api()
    print("OK test_no_stale_api")
    test_person_markup()
    print("OK test_person_markup")
    test_person_logic()
    print("OK test_person_logic")
    test_snapbar_tab_mode()
    print("OK test_snapbar_tab_mode")
    test_ai_palette()
    print("OK test_ai_palette")
    test_module_syntax()
    print("OK test_module_syntax")
    test_deployed()
    print("OK test_deployed")
    print("ВСЕ ТЕСТЫ OK")
