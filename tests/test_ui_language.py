# -*- coding: utf-8 -*-
"""Тесты языка интерфейса: дефолт EN, переключатель EN|RU, полнота ru.json.

Проверяет (без запуска сервера):
  1. баннер devbim_banner.js — английский дефолт, переключатель
     диспатчит system/languageChanged, «Выйти» локализован;
  2. кнопки ✨/3D (imagerouter/devbim_topright_buttons.js) — дефолт EN;
  3. setup_ru_locale.py — merge добавляет только отсутствующие ключи
     (идемпотентен), бренд «DevBIM» не затирается;
  4. деплоенный ru.json покрывает ВСЕ ключи en.json, кроме разделов
     workflows.*/nodes.* (вкладка Workflows скрыта из рейки);
  5. setup_navbar_labels.py — карта DBLT двуязычная (EN/RU), миграция
     v1->v2 находит якорь.

Запуск: venv\\Scripts\\python.exe tests\\test_ui_language.py
"""
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

DIST = BASE / "venv" / "Lib" / "site-packages" / "invokeai" / "frontend" / "web" / "dist"


def test_banner_default_en_and_switcher():
    s = (BASE / "devbim_banner.js").read_text(encoding="utf-8")
    assert "var lang = 'en'" in s, "английский — дефолт до чтения настроек"
    assert "var lang = 'ru'" not in s
    # переключатель
    assert "system/languageChanged" in s, "диспатч смены языка в стор приложения"
    assert "devbim-lang" in s, "сегмент EN|RU в баннере"
    assert "'EN'" in s and "'RU'" in s
    # локализованный выход
    assert "logout: 'Выйти'" in s and "logout: 'Log out'" in s
    # фолбэк прямой записью в IndexedDB
    assert "function writeLanguage" in s and "@@invokeai-system" in s
    # грабля 08.10: баннер НЕ должен создавать базу «invoke» сам — иначе на
    # свежем профиле браузера пустая база v1 убивает персистентность redux
    assert "onupgradeneeded" in s and "oldVersion === 0" in s, \
        "открытие IndexedDB обязано откатывать создание новой базы"
    assert "objectStoreNames.contains('invoke-store')" in s, \
        "без стора приложения читать нечего — тихо null"
    print("OK: баннер — дефолт EN, переключатель EN|RU, «Выйти» локализован")


def test_banner_js_syntax():
    r = subprocess.run(
        ["node", "--check", str(BASE / "devbim_banner.js")],
        capture_output=True, text=True,
    )
    if r.returncode != 0 and "не найден" in (r.stderr or "") + str(r):
        print("SKIP: node не найден")
        return
    assert r.returncode == 0, r.stderr
    print("OK: node --check devbim_banner.js")


def test_topright_default_en():
    s = (BASE / "imagerouter" / "devbim_topright_buttons.js").read_text(encoding="utf-8")
    assert "var lang = 'en'" in s, "кнопки ✨/3D стартуют с английского"
    assert "var lang = 'ru'" not in s
    # та же защита от создания пустой базы «invoke» (грабля 08.10)
    assert "onupgradeneeded" in s and "oldVersion === 0" in s
    assert "objectStoreNames.contains('invoke-store')" in s
    print("OK: кнопки ✨/3D — дефолт EN + защита IndexedDB")


def test_ru_locale_merge_missing_only():
    import setup_ru_locale as srl

    with tempfile.TemporaryDirectory() as td:
        dst = Path(td) / "ru.json"
        dst.write_text(
            json.dumps({"common": {"search": "АПСТРИМ"}, "absent": {"x": 1}}, ensure_ascii=False),
            encoding="utf-8",
        )
        patch = {"common": {"search": "Поиск", "clear": "Очистить"}, "new": {"y": 2}}
        (Path(td)).mkdir(exist_ok=True)
        ru = json.loads(dst.read_text(encoding="utf-8"))
        added = srl.deep_merge_missing(ru, patch)
        assert added == 2, added
        assert ru["common"]["search"] == "АПСТРИМ", "существующие ключи не трогаем"
        assert ru["common"]["clear"] == "Очистить" and ru["new"]["y"] == 2
        assert srl.deep_merge_missing(ru, patch) == 0, "повторный merge ничего не добавляет"
    print("OK: ru-merge добавляет только отсутствующие ключи (идемпотентен)")


def test_ru_json_complete_and_branded():
    if not (DIST / "locales" / "ru.json").exists():
        print("SKIP: ru.json не деплоен")
        return
    en = json.loads((DIST / "locales" / "en.json").read_text(encoding="utf-8"))
    ru = json.loads((DIST / "locales" / "ru.json").read_text(encoding="utf-8"))

    def flat(d, p=""):
        out = {}
        for k, v in d.items():
            kk = f"{p}.{k}" if p else k
            if isinstance(v, dict):
                out.update(flat(v, kk))
            else:
                out[kk] = v
        return out

    fe, fr = flat(en), flat(ru)
    missing = [
        k for k in fe
        if k not in fr and not k.startswith(("workflows.", "nodes."))
    ]
    assert not missing, f"не переведены: {missing[:10]}"
    # бренд не затёрт и в новых строках
    assert "DevBIM" in fr.get("newUserExperience.toGetStartedLocal", ""), fr["newUserExperience"]["toGetStartedLocal"][:80]
    # плейсхолдеры сохранены
    for k, v in fr.items():
        if k in fe and isinstance(v, str):
            te, tr = sorted(re.findall(r"\{\{\w+\}\}", fe[k])), sorted(re.findall(r"\{\{\w+\}\}", v))
            if te:
                assert tr == te, f"плейсхолдеры сломаны в {k}: {te} != {tr}"
    print(f"OK: ru.json покрывает все {len(fe)} ключей en (кроме workflows/nodes), бренд на месте")


def test_navbar_bilingual_tooltips():
    import setup_navbar_labels as snl

    # v2: три элемента [подпись, EN, RU] и выбор по языку
    assert snl.AD_V2_MARKER in snl.JS_AD_NEW
    assert snl.JS_AD_NEW.count('["Generate","Generate images from a text prompt"') == 1
    for tab in ("generate", "canvas", "upscaling", "ifc", "pdf", "designcode"):
        m = re.search(rf'{tab}:\["[^"]+","[^"]+","[^"]+"\]', snl.JS_AD_NEW)
        assert m, f"у {tab} нет трёх элементов [подпись, EN, RU]"
    # миграция: v1-фрагмент заменяется на v2 целиком (якорь уникален)
    fake = "x=1;" + snl.JS_AD_V1 + "y=2;"
    assert fake.count(snl.JS_AD_V1) == 1
    assert snl.AD_V2_MARKER not in fake
    assert snl.AD_V2_MARKER in fake.replace(snl.JS_AD_V1, snl.JS_AD_NEW, 1)
    # свежая установка: якорь Ad без карты
    assert "DBLT" not in snl.JS_AD_OLD
    print("OK: navbar — карта DBLT v2 (EN+RU), миграция v1->v2 работает")


def test_deployed_bundle_v2():
    if not DIST.exists():
        print("SKIP: dist не деплоен")
        return
    apps = [f for f in (DIST / "assets").glob("*.js")
            if 'displayName="TabContent"' in f.read_text(encoding="utf-8")]
    assert len(apps) == 1, f"App-бандл найден {len(apps)} раз"
    s = apps[0].read_text(encoding="utf-8")
    assert "T(_G)===\"ru\"?c[2]:c[1]" in s, "деплой не содержит v2-патч тултипов"
    assert "_G=ge(H2,e=>e.language)" in s, "селектор system.language должен быть в том же бандле"
    print("OK: деплоенный App-бандл содержит v2-тултипы и селектор языка")


if __name__ == "__main__":
    test_banner_default_en_and_switcher()
    test_banner_js_syntax()
    test_topright_default_en()
    test_ru_locale_merge_missing_only()
    test_ru_json_complete_and_branded()
    test_navbar_bilingual_tooltips()
    test_deployed_bundle_v2()
    print("\nВСЕ ТЕСТЫ OK")
