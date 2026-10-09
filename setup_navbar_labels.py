# -*- coding: utf-8 -*-
"""Подписи под пиктограммами левой рейки + поясняющие тултипы + скрыть Workflows.

Что делает (App-бандл, единственный с displayName="TabContent"):
  1. Переписывает TabButton (Ad): под иконкой появляется короткая
     подпись (карта DBLT), тултип при наведении — пояснение из карты,
     ПО ЯЗЫКУ ИНТЕРФЕЙСА (элемент 1 = EN, элемент 2 = RU; язык читается
     селектором _G = system.language того же бандла, переключатель —
     в баннере DevBIM / Settings). Вкладок вне карты касается только
     тултип — он остаётся прежним label. Клик по подписи тоже
     переключает вкладку.
  2. Убирает из рейки кнопку Workflows (вкладка недоступна в локальной
     сборке; контент вкладки в TabContent не трогается).

Почему отдельный скрипт и почему последним в цепочке: кнопка Workflows
— якорь вставки вкладки IFC в setup_ifcviewer.py (PDF цепляется за IFC,
Design Code за PDF); прятать её раньше звена нельзя. Патч Ad от
кол-сайтов не зависит, но подписи нужны всем вкладкам, включая
добавленные, — поэтому запускается после setup_style_presets.py.

Порядок после pip install --force-reinstall invokeai==6.2.0:
  1. rebrand_devbim.py  2. setup_imagerouter.py  3. setup_ifcviewer.py
  4. setup_pdfviewer.py 5. setup_designcode.py   6. setup_threed.py
  7. setup_site_auth.py 8. setup_style_presets.py 9. setup_ru_locale.py
  10. setup_navbar_labels.py

Идемпотентен; умеет мигрировать бандл с картой DBLT v1 (2-элементной,
тултип только RU) на v2 (3-элементную, EN+RU). Откат: восстановить
App-*.js из *.navbarlabels-bak.
"""
import shutil
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
VENV = BASE / "venv"
DIST = VENV / "Lib" / "site-packages" / "invokeai" / "frontend" / "web" / "dist"

# --- App-бандл: TabButton (Ad). Было: IconButton в тултипе; стало:
#     колонка E [IconButton, подпись W], тултип = пояснение из DBLT
#     по языку интерфейса (T(_G) — useSelector системного языка).
#     Сигнатура вызовов (tab/icon/label) не меняется.
JS_AD_OLD = (
    'Ad=u.memo(({tab:e,icon:t,label:n})=>{const s=u.useRef(null),i=T(Ln),'
    'a=u.useCallback(()=>{Fe.switchToTab(e)},[e]);return rf(a,s,300),'
    'o.jsx($e,{label:n,placement:"end",children:o.jsx(re,{p:0,ref:s,onClick:a,'
    'icon:t,size:"md",fontSize:"24px",variant:"link","data-selected":i===e,'
    '"aria-label":n,"data-testid":n,sx:c5e})})});Ad.displayName="TabButton";'
)

# E/W — импорты модуля (flex-контейнер и Text), TDZ нет; onClick на
# контейнере ловит клики по подписи (пузырь от кнопки даёт второй вызов
# switchToTab той же вкладки — идемпотентно).
# ВНИМАНИЕ: Ad входит в цепочку объявлений «...,c5e={...},Ad=...» — DBLT
# объявляется ОТДЕЛЬНЫМ оператором ПОСЛЕ закрытия цепочки (const после
# запятой — SyntaxError); Ad читает DBLT/_G только в рендере, который
# выполняется после инициализации модуля, — TDZ нет (_G — селектор
# system.language, объявлен в этом же чанке ниже по файлу).
JS_AD_NEW = (
    'Ad=u.memo(({tab:e,icon:t,label:n})=>{const s=u.useRef(null),i=T(Ln),'
    'a=u.useCallback(()=>{Fe.switchToTab(e)},[e]),c=DBLT[e];'
    'return rf(a,s,300),o.jsx($e,{label:c?(T(_G)==="ru"?c[2]:c[1]):n,'
    'placement:"end",children:'
    'o.jsxs(E,{flexDir:"column",alignItems:"center",'
    'onClick:c?a:void 0,cursor:c?"pointer":"default",children:['
    'o.jsx(re,{p:0,ref:s,onClick:a,icon:t,size:"md",fontSize:"24px",'
    'variant:"link","data-selected":i===e,"aria-label":n,"data-testid":n,sx:c5e}),'
    'c?o.jsx(W,{fontSize:"9px",lineHeight:1.3,fontWeight:500,letterSpacing:"tight",'
    'color:i===e?"invokeYellow.300":"base.400",textAlign:"center",'
    'userSelect:"none",children:c[0]}):null]})})});'
    'Ad.displayName="TabButton";'
    # карта [подпись, тултип EN, тултип RU]; RU-пояснения — по запросу
    # пользователя, EN — дефолт продукта (08.10: тултипы двуязычные)
    'const DBLT={generate:["Generate","Generate images from a text prompt",'
    '"Генерация изображений по описанию"],'
    'canvas:["Canvas","Canvas — image editing, layers and masks",'
    '"Холст — редактирование изображений, слои и маски"],'
    'upscaling:["Upscaling","Upscaling — increase image resolution",'
    '"Апскейл — увеличение разрешения изображений"],'
    'ifc:["IFC","IFC viewer — 3D viewing of BIM models",'
    '"IFC-вьювер — 3D-просмотр BIM-моделей"],'
    'pdf:["PDF","PDF viewer — view PDF documents",'
    '"PDF-вьювер — просмотр документов PDF"],'
    'designcode:["Design Code","Viewer of the design code site database",'
    '"Вьювер сайт-базы дизайн-кода"]};'
)

AD_MARKER = "const DBLT={"  # признак уже применённого патча Ad (v1 или v2)
AD_V2_MARKER = 'T(_G)==="ru"?c[2]:c[1]'  # патч v2: тултипы по языку

# v1 (до 08.10): карта [подпись, тултип RU] без выбора языка — для
# миграции уже-пропатченного бандла на v2.
JS_AD_V1 = (
    'Ad=u.memo(({tab:e,icon:t,label:n})=>{const s=u.useRef(null),i=T(Ln),'
    'a=u.useCallback(()=>{Fe.switchToTab(e)},[e]),c=DBLT[e];'
    'return rf(a,s,300),o.jsx($e,{label:c?c[1]:n,placement:"end",children:'
    'o.jsxs(E,{flexDir:"column",alignItems:"center",'
    'onClick:c?a:void 0,cursor:c?"pointer":"default",children:['
    'o.jsx(re,{p:0,ref:s,onClick:a,icon:t,size:"md",fontSize:"24px",'
    'variant:"link","data-selected":i===e,"aria-label":n,"data-testid":n,sx:c5e}),'
    'c?o.jsx(W,{fontSize:"9px",lineHeight:1.3,fontWeight:500,letterSpacing:"tight",'
    'color:i===e?"invokeYellow.300":"base.400",textAlign:"center",'
    'userSelect:"none",children:c[0]}):null]})})});'
    'Ad.displayName="TabButton";'
    'const DBLT={generate:["Generate","Генерация изображений по описанию"],'
    'canvas:["Canvas","Холст — редактирование изображений, слои и маски"],'
    'upscaling:["Upscaling","Апскейл — увеличение разрешения изображений"],'
    'ifc:["IFC","IFC-вьювер — 3D-просмотр BIM-моделей"],'
    'pdf:["PDF","PDF-вьювер — просмотр документов PDF"],'
    'designcode:["Design Code","Вьювер сайт-базы дизайн-кода"]};'
)

# --- App-бандл: вырезать кнопку Workflows из рейки (якорь вставки IFC
#     в setup_ifcviewer.py — ПОСЛЕ этого скрипта в цепочку не возвращаться
#     на свежей установке; при повторном запуске ifcviewer на пропатченном
#     бандле его «уже на месте»-детект срабатывает раньше якоря).
JS_WORKFLOWS_OLD = (
    'a&&o.jsx(Ad,{tab:"workflows",icon:o.jsx(M1,{}),label:e("ui.tabs.workflows")}),'
)

WORKFLOWS_MARKER = 'o.jsx(Ad,{tab:"workflows"'  # любая кнопка Workflows в рейке


def _app_bundle() -> Path:
    targets = [
        f for f in DIST.glob("assets/*.js")
        if 'displayName="TabContent"' in f.read_text(encoding="utf-8")
    ]
    if len(targets) != 1:
        print(f"ОШИБКА: App-бандл (TabContent) найден {len(targets)} раз (ожидался 1)")
        sys.exit(1)
    return targets[0]


def main() -> None:
    if not DIST.exists():
        print("Не найден venv InvokeAI:", DIST)
        sys.exit(1)
    f = _app_bundle()
    s = f.read_text(encoding="utf-8")
    orig = s

    wf_done = JS_WORKFLOWS_OLD not in s and WORKFLOWS_MARKER not in s
    if not wf_done and JS_WORKFLOWS_OLD not in s:
        # кнопка Workflows есть, но якорь другой формы — структура изменилась
        print('ОШИБКА: кнопка Workflows в рейке не совпала с якорем — патч не применён')
        sys.exit(1)

    if AD_V2_MARKER in s:
        print("TabButton: двуязычные подписи/тултипы (v2) уже на месте, пропуск")
    elif AD_MARKER in s:
        # бандл пропатчен v1 (до 08.10: тултипы только RU) — миграция на v2
        if s.count(JS_AD_V1) != 1:
            print(f"ОШИБКА: патч TabButton v1 найден {s.count(JS_AD_V1)} раз (ожидался 1)")
            sys.exit(1)
        s = s.replace(JS_AD_V1, JS_AD_NEW, 1)
        print("TabButton: v1 -> v2 (тултипы EN/RU по языку интерфейса)")
    else:
        if s.count(JS_AD_OLD) != 1:
            print(f"ОШИБКА: определение Ad найдено {s.count(JS_AD_OLD)} раз (ожидался 1)")
            sys.exit(1)
        s = s.replace(JS_AD_OLD, JS_AD_NEW, 1)
        print("TabButton: подписи под иконками + двуязычные тултипы")

    if wf_done:
        print("Кнопка Workflows уже скрыта, пропуск")
    else:
        if s.count(JS_WORKFLOWS_OLD) != 1:
            print(f"ОШИБКА: фрагмент Workflows найден {s.count(JS_WORKFLOWS_OLD)} раз (ожидался 1)")
            sys.exit(1)
        s = s.replace(JS_WORKFLOWS_OLD, "", 1)
        print("Кнопка Workflows скрыта из левой рейки")

    if s == orig:
        return
    bak = f.with_suffix(f.suffix + ".navbarlabels-bak")
    if not bak.exists():
        shutil.copy2(f, bak)
    f.write_text(s, encoding="utf-8")
    print(f"App-бандл пропатчен: {f.name} (бэкап: {bak.name})")


if __name__ == "__main__":
    main()
