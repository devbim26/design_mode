# -*- coding: utf-8 -*-
"""
Вкладка «Design Code» (вьювер сайта дизайн-кода) в DevBIM / InvokeAI 6.2.0.

Что делает:
  1. Копирует роутер design_code_router.py в
     venv/Lib/site-packages/invokeai/app/api/routers/design_code.py
     (API: GET/POST /api/v1/designcode/auth — код доступа из .env:
     DESIGN_CODE_ACCESS_CODE, префилл адреса DESIGN_CODE_URL).
  2. Копирует страницу design_code_viewer.html в dist фронтенда
     (модальное окно «URL + код» → интерактивный iframe сайта,
     тулбар Reload / New tab / Change site).
  3. Патчит api_app.py: подключает роутер (бэкап *.designcode-bak).
  4. Патчит собранный JS (бэкап *.designcode-bak):
     - App-бандл: в левую рейку добавляется кнопка «Design Code» (после
       PDF; иконка-палитра DCI — Phosphor palette fill, строится тем же
       хелпером ue, что RA/vx), в TabContent — панель DCE с iframe
       /design_code_viewer.html;
     - index-бандл: 'designcode' добавляется в zod-enum activeTab, чтобы
       сохранённая вкладка пережила перезагрузку страницы.

Идемпотентен: повторный запуск ничего не меняет.
Запуск: venv\\Scripts\\python.exe setup_designcode.py
Восстановление: скопировать *.designcode-bak поверх патченных файлов,
удалить venv/.../routers/design_code.py и dist/design_code_viewer.html.

Порядок после pip install --force-reinstall invokeai==6.2.0:
  1. rebrand_devbim.py  2. setup_imagerouter.py  3. setup_ifcviewer.py
  4. setup_pdfviewer.py 5. setup_designcode.py  6. setup_site_auth.py
"""
import shutil
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
SRC = BASE / "design_code"
VENV = BASE / "venv"
SP = VENV / "Lib" / "site-packages"
DIST = SP / "invokeai" / "frontend" / "web" / "dist"
ROUTER_DST = SP / "invokeai" / "app" / "api" / "routers" / "design_code.py"
API_APP = SP / "invokeai" / "app" / "api_app.py"

# --- App-бандл: кнопка «Design Code» в левой рейке (после PDF).
#     DCI — иконка-палитра (Phosphor palette, fill-вес; тот же формат,
#     что у RA/vx: хелпер ue = GenIcon из react-icons). ---
JS_PALETTE_PATH = (
    "M200.77,53.89A103.27,103.27,0,0,0,128,24h-1.07A104,104,0,0,0,24,128c0,43,26.58,79.06,69.36,94.17"
    "A32,32,0,0,0,136,192a16,16,0,0,1,16-16h46.21a31.81,31.81,0,0,0,31.2-24.88,104.43,104.43,0,0,0,2.59-24"
    "A103.28,103.28,0,0,0,200.77,53.89ZM84,168a12,12,0,1,1,12-12A12,12,0,0,1,84,168Zm0-56a12,12,0,1,1,12-12"
    "A12,12,0,0,1,84,112Zm44-24a12,12,0,1,1,12-12A12,12,0,0,1,128,88Zm44,24a12,12,0,1,1,12-12A12,12,0,0,1,172,112Z"
)

JS_NAVBAR_OLD = 'o.jsx(Ad,{tab:"pdf",icon:o.jsx(vx,{}),label:"PDF"})'
JS_NAVBAR_NEW = (
    'o.jsx(Ad,{tab:"pdf",icon:o.jsx(vx,{}),label:"PDF"}),'
    'o.jsx(Ad,{tab:"designcode",icon:o.jsx(DCI,{}),label:"Design Code"})'
)

# --- App-бандл: панель вкладки в TabContent (iframe со страницей вьювера) ---
JS_TABCONTENT_OLD = 'e==="pdf"&&o.jsx(PDFE,{})'
JS_TABCONTENT_NEW = 'e==="pdf"&&o.jsx(PDFE,{}),e==="designcode"&&o.jsx(DCE,{})'

# --- App-бандл: иконка DCI + компонент панели DCE (вставляются перед
#     AppContent, тем же якорем, что компоненты IFC/PDF).
#     V2: как PDFE/IFCV, DCE захватывает Je() (redux-store {dispatch,getState})
#     в window.__devbimIfcCtx — мост «🖼 To Canvas» из нижней панели вьювера
#     (window.__devbimIfc.toCanvas) без контекста падает «canvas context
#     unavailable». Вкладки designcode и canvas не активны одновременно —
#     за глобаль с PDFE/IFE/IFCV/PDFV не спорят. ---
JS_DESIGNCODE_TAB_V2 = (
    'function DCI(e){return ue({attr:{viewBox:"0 0 256 256",fill:"currentColor"},'
    'child:[{tag:"path",attr:{d:"' + JS_PALETTE_PATH + '"},child:[]}]})(e)}'
    'const DCE=u.memo(()=>{const e=Je();'
    'u.useEffect(()=>{window.__devbimIfcCtx=e;return()=>{window.__devbimIfcCtx=null}},[e]);'
    'u.useEffect(()=>()=>Fe.unregisterTab("designcode"),[]);'
    'return o.jsx(yf,{tab:"designcode",children:o.jsx("iframe",{src:"/design_code_viewer.html",'
    'title:"Design Code",style:{width:"100%",height:"100%",border:"none"}})});});'
    'DCE.displayName="DesignCodeTab";'
)
# первая версия — без захвата контекста (мигрируется на V2 повторным запуском)
JS_DESIGNCODE_TAB = (
    'function DCI(e){return ue({attr:{viewBox:"0 0 256 256",fill:"currentColor"},'
    'child:[{tag:"path",attr:{d:"' + JS_PALETTE_PATH + '"},child:[]}]})(e)}'
    'const DCE=u.memo(()=>(u.useEffect(()=>()=>Fe.unregisterTab("designcode"),[]),'
    'o.jsx(yf,{tab:"designcode",children:o.jsx("iframe",{src:"/design_code_viewer.html",'
    'title:"Design Code",style:{width:"100%",height:"100%",border:"none"}})})));'
    'DCE.displayName="DesignCodeTab";'
)
JS_APPCONTENT_ANCHOR = 'const cue=u.memo('

# --- index-бандл: zod-enum activeTab (сохранение вкладки в storage) ---
JS_ENUM_OLD = 'ct(["generate","canvas","upscaling","workflows","models","queue","ifc","pdf"])'
JS_ENUM_NEW = 'ct(["generate","canvas","upscaling","workflows","models","queue","ifc","pdf","designcode"])'


def deploy_files() -> None:
    shutil.copy2(SRC / "design_code_router.py", ROUTER_DST)
    shutil.copy2(SRC / "design_code_viewer.html", DIST / "design_code_viewer.html")
    print("Роутер развернут:", ROUTER_DST)
    print("Страница развернута:", DIST / "design_code_viewer.html")


def patch_api_app() -> bool:
    s = API_APP.read_text(encoding="utf-8")
    if "include_router(design_code.design_code_router" in s:
        print("api_app.py уже пропатчен, пропуск")
        return False
    if "include_router(pdf.pdf_router" not in s:
        print("ОШИБКА: api_app.py без PDF-роутера — сначала запустите setup_pdfviewer.py")
        sys.exit(1)
    bak = API_APP.with_suffix(".py.designcode-bak")
    if not bak.exists():
        shutil.copy2(API_APP, bak)
    orig = s
    s = s.replace("    pdf,\n", "    pdf,\n    design_code,\n", 1)
    s = s.replace(
        'app.include_router(pdf.pdf_router, prefix="/api")\n',
        'app.include_router(pdf.pdf_router, prefix="/api")\n'
        'app.include_router(design_code.design_code_router, prefix="/api")\n',
        1,
    )
    if s == orig:
        print("ОШИБКА: не найдены точки вставки в api_app.py — патч не применён")
        sys.exit(1)
    API_APP.write_text(s, encoding="utf-8")
    print("api_app.py пропатчен (бэкап:", bak.name + ")")
    return True


def _backup(f: Path) -> Path:
    bak = f.with_suffix(f.suffix + ".designcode-bak")
    if not bak.exists():
        shutil.copy2(f, bak)
    return bak


def patch_app_bundle() -> bool:
    """Кнопка в рейке + панель в TabContent + компонент вкладки."""
    targets = [f for f in DIST.glob("assets/*.js") if 'displayName="TabContent"' in f.read_text(encoding="utf-8")]
    if len(targets) != 1:
        print(f"ОШИБКА: бандл с TabContent найден {len(targets)} раз (ожидался 1)")
        sys.exit(1)
    f = targets[0]
    s = f.read_text(encoding="utf-8")

    # якоря сидят на PDF-патчах — без них установка бессмысленна
    if 'e==="pdf"&&o.jsx(PDFE' not in s:
        print("ОШИБКА: в App-бандле нет панели PDF — сначала запустите setup_pdfviewer.py")
        sys.exit(1)

    orig = s

    if JS_NAVBAR_NEW in s:
        if JS_DESIGNCODE_TAB_V2 in s:
            print("App-бандл: вкладка Design Code уже на месте, пропуск")
        elif JS_DESIGNCODE_TAB in s:
            # миграция DCE v1 (без захвата __devbimIfcCtx) -> v2
            s = s.replace(JS_DESIGNCODE_TAB, JS_DESIGNCODE_TAB_V2, 1)
            print("App-бандл: DCE обновлён (захват __devbimIfcCtx для To Canvas из вкладки Design Code)")
        else:
            print("App-бандл: вкладка Design Code уже на месте (DCE не найден), пропуск")
    else:
        for old, new, title in (
            (JS_NAVBAR_OLD, JS_NAVBAR_NEW, "кнопка «Design Code» в левой рейке"),
            (JS_TABCONTENT_OLD, JS_TABCONTENT_NEW, "панель Design Code в TabContent"),
        ):
            if s.count(old) != 1:
                print(f"ОШИБКА: фрагмент «{title}» найден {s.count(old)} раз (ожидался 1)")
                sys.exit(1)
        if s.count(JS_APPCONTENT_ANCHOR) < 1 or "AppContent" not in s:
            print("ОШИБКА: не найдена точка вставки компонента Design Code")
            sys.exit(1)
        s = s.replace(JS_NAVBAR_OLD, JS_NAVBAR_NEW, 1)
        s = s.replace(JS_TABCONTENT_OLD, JS_TABCONTENT_NEW, 1)
        s = s.replace(JS_APPCONTENT_ANCHOR, JS_DESIGNCODE_TAB_V2 + JS_APPCONTENT_ANCHOR, 1)
        print("App-бандл: вкладка Design Code добавлена")

    if s == orig:
        return False
    bak = _backup(f)
    f.write_text(s, encoding="utf-8")
    print(f"App-бандл пропатчен: {f.name} (бэкап: {bak.name})")
    return True


def patch_index_bundle() -> bool:
    """'designcode' в zod-enum activeTab — иначе перезагрузка со вкладкой
    Design Code сбрасывает настройки UI (parse storage падает)."""
    targets = [f for f in DIST.glob("assets/*.js") if JS_ENUM_OLD in f.read_text(encoding="utf-8")]
    already = [f for f in DIST.glob("assets/*.js") if JS_ENUM_NEW in f.read_text(encoding="utf-8")]
    if already and not targets:
        print("index-бандл уже пропатчен (enum activeTab), пропуск")
        return False
    if len(targets) != 1:
        print(f"ОШИБКА: бандл с enum activeTab найден {len(targets)} раз (ожидался 1)")
        sys.exit(1)
    f = targets[0]
    s = f.read_text(encoding="utf-8")
    s = s.replace(JS_ENUM_OLD, JS_ENUM_NEW, 1)
    bak = _backup(f)
    f.write_text(s, encoding="utf-8")
    print(f"index-бандл пропатчен (enum activeTab + designcode): {f.name} (бэкап: {bak.name})")
    return True


def main() -> None:
    for p in [SRC / "design_code_router.py", SRC / "design_code_viewer.html"]:
        if not p.exists():
            print("Не найдено:", p)
            sys.exit(1)
    if not DIST.exists() or not API_APP.parent.exists():
        print("Не найден venv InvokeAI:", DIST)
        sys.exit(1)
    deploy_files()
    patch_api_app()
    patch_app_bundle()
    patch_index_bundle()
    print("Готово. Перезапустите сервер, затем вкладка «Design Code» в левой рейке.")


if __name__ == "__main__":
    main()
