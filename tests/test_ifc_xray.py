# -*- coding: utf-8 -*-
"""Тесты режимов перекраски IFC-вьювера: «Рентген» (каркас) и «Оттенки
серого» (08-09.10.2026).

Проверяется исходник ifc/ifcviewer.html:
  - кнопки «🦴 Рентген» и «🔳 Серый» в тулбаре (AI-палитра не тронута);
  - общий движок подмены shadeApply/shadeRestore/shadeEnsure/shadeRun:
    клон оригинального материала (шейдер-декодер нормалей @thatopen),
    массив материалов той же длины (LOD-меши), перенос lodSize,
    клиппинг-плоскости сечений;
  - рентген: fwidth-детектор рёбер, прозрачное тело, акцент #38BDF8;
  - серый: luma-градации (BT.601) — нейтральный снимок под перегенерацию
    цветовой раскраски;
  - переживание F5 (localStorage), смены модели (loadIfc-хук) и
    пересоздания мешей LOD (shadeEnsure на update камеры);
  - взаимоисключаемость трёх режимов (палитра/рентген/серый);
  - TDZ: состояния объявлены ДО слушателя камеры (init стреляет update
    синхронно — ReferenceError, как у aiPaletteState в п.54).

Запуск: venv\\Scripts\\python.exe tests\\test_ifc_xray.py
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


def test_markup() -> None:
    s = SRC.read_text(encoding="utf-8")
    assert 'id="btn-xray"' in s, "нет кнопки Рентгена в тулбаре"
    assert 'id="btn-gray"' in s, "нет кнопки Оттенков серого в тулбаре"
    assert "#toolbar" in s, "тулбар потерян"
    # AI-палитра («перерисовка») обязана остаться — она в ИИ-рендер-конвейере
    assert 'id="btn-palette"' in s, "кнопка AI-палитры пропала"
    # кнопки — в тулбаре
    tb = s[s.find('id="toolbar"'):s.find("</div>", s.find('id="btn-gray"'))]
    assert tb.count("<button") >= 2 and 'id="btn-gray"' in tb, "кнопка не в тулбаре"


def test_xray_material() -> None:
    js = module_script(SRC.read_text(encoding="utf-8"))
    # каркас рисуется ФРАГМЕНТНЫМ ШЕДЕРОМ: у геометрии фрагментов @thatopen
    # GPU-буферы без .array — material.wireframe роняет рендер (getWireframeAttribute);
    # вложенные производные dFdx(dFdx) на этом стеке дают ноль — только fwidth(varying)
    assert "function xrayShaderPatch(shader)" in js, "нет шейдерной инъекции рентгена"
    assert "varying vec3 vXN" in js, "нет мировой нормали в шейдере"
    assert "length(fwidth(vXN))" in js, \
        "рёбра не считаются по fwidth нормали (первая производная от varying)"
    assert "smoothstep(0.04, 0.25, edge)" in js, "нет плавного порога ребра"
    assert "0x38bdf8" in js, "цвет рёбер не акцент вьювера"
    assert "diffuseColor.a = mix(0.06, 1.0, isEdge)" in js, \
        "тело модели должно быть прозрачным (рентген-эффект)"
    assert not re.search(r"[^;]*material[^;]*\.wireframe\s*=\s*true", js), \
        "material.wireframe на фрагментах роняет рендер — использовать шейдер"


def test_gray_material() -> None:
    js = module_script(SRC.read_text(encoding="utf-8"))
    assert "function grayShaderPatch(shader)" in js, "нет шейдерной инъекции серого"
    # luma BT.601: весь цвет модели — градации серого
    assert "dot(diffuseColor.rgb, vec3(0.299, 0.587, 0.114))" in js, \
        "нет luma-преобразования цвета (BT.601)"
    assert 'grayState.key = "devbim:ifc:gray"' in js and 'grayState.btn = "btn-gray"' in js, \
        "состояние серого не привязано к ключу/кнопке"
    assert 'graySetEnabled(localStorage.getItem(grayState.key)' in js, "режим не читается из localStorage"
    assert "gray: {" in js, "нет отладочного __ifc.gray"


def test_shade_engine() -> None:
    s = SRC.read_text(encoding="utf-8")
    js = module_script(s)
    for frag in (
        "function shadeApply(state, patch, opts = {})",
        "function shadeRestore(state)",
        "function shadeEnsure(state)",
        "function shadeRun(state, on)",
    ):
        assert frag in js, f"нет {frag}"
    # подмена: встроенным материалам three — клон, vse — новый конструктором
    assert "xm = m.clone();" in js, "встроенный материал не клонируется"
    assert "xm.onBeforeCompile = patch" in js, "клону не ставится шейдерный патч"
    assert "if (!xm.vertexShader || !xm.fragmentShader) return" not in js, \
        "предохранитель по шейдер-строкам отсекает встроенные материалы three (interior-модели)"
    # ГРАБЛИ @thatopen: LOD-меши читают material[0].lodSize в onBeforeRender —
    # массив материалов подменяется массивом той же длины, lodSize переносится
    assert "Array.from(o.material, () => xm)" in js, \
        "массив материалов не сохраняется при подмене (LOD-меши роняют рендер)"
    # оригинал в userData, счётчик
    assert "o.userData.shadeOriginal = o.material" in js, "оригинал не сохраняется"
    # восстановление защищено от устаревших shadeOriginal (замена библиотекой)
    restore = js[js.find("function shadeRestore"):js.find("function shadeEnsure")]
    assert "cur.onBeforeCompile === xrayShaderPatch" in restore and \
        "cur.onBeforeCompile === grayShaderPatch" in restore, \
        "shadeRestore возвращает устаревший оригинал"
    # ensure считает действующие подмены по патчу состояния
    ensure = js[js.find("function shadeEnsure"):js.find("function shadeRun")]
    assert "cur.onBeforeCompile === state.patch" in ensure and \
        "shadeApply(state, state.patch, state.opts)" in ensure, \
        "shadeEnsure не дожимает сходимость при LOD"
    # vse ScreenSpace-LOD @thatopen — ЭТО ЛИНИИ (полосы-границы элементов):
    # clone() их класса ПАДАЕТ (new vse() без t.color), цвет — ЮНИФОРМА
    # lodColor — строим НОВЫЙ материал их конструктором
    assert "if (m.isLodMaterial)" in js, "нет ветки vse (isLodMaterial)"
    assert "new m.constructor({ color: col, opacity: op, transparent: !!m.transparent })" in js, \
        "vse-материал не строится конструктором (clone у них падает)"
    assert "col = new Color(g, g, g);" in js, "серому не передаётся luma-цвет в конструктор vse"
    assert "col = 0x38bdf8;" in js, "рентгену линии-границы не красятся акцентом"
    assert "gl_FragColor = vec4(vec3(0.22, 0.74, 0.97), 0.9);" in js, \
        "vse-линии не красятся целиком в акцент (якорь их фрагментника)"
    # сечения режут перекрашенное: клиппинг-плоскости копируются на клоны
    assert "cur.clippingPlanes = src.clippingPlanes" in js, "клиппинг не копируется"
    # состояния переживают F5
    assert 'xrayState.key = "devbim:ifc:xray"' in js, "нет ключа localStorage рентгена"
    assert 'localStorage.setItem(state.key' in js, "состояние не пишется в localStorage"
    # самопроверка подмены при LOD — в слушателе камеры, для обоих режимов
    assert "if (xrayState.on) shadeEnsure(xrayState);" in js and \
        "if (grayState.on) shadeEnsure(grayState);" in js, \
        "нет shadeEnsure в слушателе камеры"
    # дожим сходимости: стили @thatopen кладут материалы ПОВЕРХ подмены
    # асинхронно — без серии re-apply остаются цветные/залитые островки
    assert "function shadeConverge(state)" in js and \
        "[400, 1200, 2200, 3500, 5200, 8000]" in js, \
        "нет серии дожимающих re-apply после загрузки/включения"
    assert "function shadeStop(state)" in js, "нет остановки серии при выключении"
    assert "shadeApply(state, state.patch, state.opts); shadeConverge(state);" in js, \
        "включение режима не запускает дожим"
    assert "[xrayState, grayState].forEach((s) => { if (s.on) shadeConverge(s); });" in js, \
        "loadIfc-хук не дожимает режимы после стилей @thatopen"
    # светлый фон вьюпорта — в рентгене И сером (на тёмном каркас/серая
    # модель сливаются); снимается когда оба выключены
    assert "body.lightbg #viewport{background:#d4d4d4}" in s, "нет светлого фона вьюпорта"
    assert 'document.body.classList.toggle("lightbg", xrayState.on || grayState.on)' in js, \
        "lightbg-класс не пересчитывается по обоим режимам"
    # отладка
    assert "xray: {" in js, "нет отладочного __ifc.xray"


def test_modes_exclusive() -> None:
    js = module_script(SRC.read_text(encoding="utf-8"))
    # включение режима гасит второй режим и палитру
    run = js[js.find("function shadeRun"):js.find("xrayState.key = ")]
    assert "other.on) shadeRun(other, false)" in run, "режимы не гасят друг друга"
    assert "if (aiPaletteState.on) aiSetEnabled(false);" in run, "режим не выключает палитру"
    # включение палитры гасит оба режима
    ai = js[js.find("function aiSetEnabled"):js.find('$("btn-palette").addEventListener')]
    assert "xrayState.on) xraySetEnabled(false)" in ai, "палитра не выключает рентген"
    assert "grayState.on) graySetEnabled(false)" in ai, "палитра не выключает серый"


def test_tdz_order() -> None:
    """init @thatopen синхронно стреляет update камеры → объявление
    состояний обязано стоять ДО слушателя (ReferenceError иначе)."""
    js = module_script(SRC.read_text(encoding="utf-8"))
    listener = js.find('controls.addEventListener("update"')
    for decl in ("const aiPaletteState", "const xrayState", "const grayState"):
        pos = js.find(decl)
        assert pos != -1 and pos < listener, \
            f"{decl} объявлен после слушателя камеры — ReferenceError при синхронном update в init"


def test_module_syntax() -> None:
    import subprocess
    js = module_script(SRC.read_text(encoding="utf-8"))
    p = BASE / "tests" / "_threed_tmp" / "ifc_module.mjs"
    p.parent.mkdir(exist_ok=True)
    p.write_text(js, encoding="utf-8")
    r = subprocess.run(["node", "--check", str(p)], capture_output=True, text=True)
    assert r.returncode == 0, f"синтаксис module-скрипта: {r.stderr[:400]}"


def test_deployed() -> None:
    assert DIST.exists(), "ifcviewer.html не развернут в dist (запустите setup_ifcviewer.py)"
    src = SRC.read_text(encoding="utf-8")
    dep = DIST.read_text(encoding="utf-8")
    assert src == dep, "dist/ifcviewer.html отличается от исходника — перезапустите setup_ifcviewer.py"


if __name__ == "__main__":
    test_markup()
    print("OK test_markup")
    test_xray_material()
    print("OK test_xray_material")
    test_gray_material()
    print("OK test_gray_material")
    test_shade_engine()
    print("OK test_shade_engine")
    test_modes_exclusive()
    print("OK test_modes_exclusive")
    test_tdz_order()
    print("OK test_tdz_order")
    test_module_syntax()
    print("OK test_module_syntax")
    test_deployed()
    print("OK test_deployed")
    print("ВСЕ ТЕСТЫ OK")
