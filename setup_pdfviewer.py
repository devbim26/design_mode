# -*- coding: utf-8 -*-
"""
Вкладка «PDF» (PDF-вьювер) в DevBIM / InvokeAI 6.2.0.

Что делает:
  1. Копирует роутер pdf_router.py в venv/Lib/site-packages/invokeai/app/api/routers/
     (API: /api/v1/pdf/list|upload|file/{name}).
  2. Копирует страницу pdfviewer.html и ассеты PDF.js (dist/pdf/) в dist фронтенда.
  3. Патчит api_app.py: подключает роутер (бэкап *.pdfviewer-bak).
  4. Патчит собранный JS (бэкап *.pdfviewer-bak):
     - App-бандл: в левую рейку добавляется кнопка «PDF» (после IFC,
       иконка vx — «документ»), в TabContent — панель с iframe /pdfviewer.html;
     - App-бандл: на вкладке «Холст» в главную dockview-область добавляется
       панель «PDF Viewer» (iframe /pdfviewer.html?embed=1 — вьювер без
       шапки/сайдбара/фута), рядом с «Image Viewer»/«IFC Viewer»; компонент
       PDFV, как и IFCV, держит window.__devbimIfcCtx для моста «To Canvas»;
     - index-бандл: 'pdf' добавляется в zod-enum activeTab, чтобы сохранённая
       вкладка пережила перезагрузку страницы.
  «На холст» из вьювера использует СУЩЕСТВУЮЩИЙ мост window.__devbimIfc.toCanvas
  (setup_ifcviewer.py) — поэтому сначала должен быть установлен IFC-вьювер.

Идемпотентен: повторный запуск ничего не меняет.
Запуск: venv\\Scripts\\python.exe setup_pdfviewer.py
Восстановление: скопировать *.pdfviewer-bak поверх патченных файлов,
удалить venv/.../routers/pdf.py, dist/pdfviewer.html и dist/pdf/.

Порядок после pip install --force-reinstall invokeai==6.2.0:
  1. rebrand_devbim.py  2. setup_imagerouter.py  3. setup_ifcviewer.py
  4. setup_pdfviewer.py 5. setup_site_auth.py
"""
import re
import shutil
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
SRC = BASE / "pdf"
VENV = BASE / "venv"
SP = VENV / "Lib" / "site-packages"
DIST = SP / "invokeai" / "frontend" / "web" / "dist"
ROUTER_DST = SP / "invokeai" / "app" / "api" / "routers" / "pdf.py"
API_APP = SP / "invokeai" / "app" / "api_app.py"

ASSETS = ("pdf.min.mjs", "pdf.worker.min.mjs")

# --- App-бандл: кнопка «PDF» в левой рейке (после IFC; vx — иконка «документ»,
#     function-декларация в той же области видимости, что и RA у IFC) ---
JS_NAVBAR_OLD = 'o.jsx(Ad,{tab:"ifc",icon:o.jsx(RA,{}),label:"IFC"})'
JS_NAVBAR_NEW = (
    'o.jsx(Ad,{tab:"ifc",icon:o.jsx(RA,{}),label:"IFC"}),'
    'o.jsx(Ad,{tab:"pdf",icon:o.jsx(vx,{}),label:"PDF"})'
)

# --- App-бандл: панель вкладки в TabContent (iframe со страницей вьювера) ---
JS_TABCONTENT_OLD = 'e==="ifc"&&o.jsx(IFE,{})'
JS_TABCONTENT_NEW = 'e==="ifc"&&o.jsx(IFE,{}),e==="pdf"&&o.jsx(PDFE,{})'

# --- App-бандл: компонент панели (вставляется перед AppContent, рядом с IFE).
#     Как и IFCV (панель IFC на холсте), PDFE захватывает Je() (redux-store
#     {dispatch,getState}) в window.__devbimIfcCtx — мост «На холст»
#     (window.__devbimIfc.toCanvas) без него не работает, а IFCV монтируется
#     только на вкладке «Холст»: с вкладки PDF контекст был бы null.
#     Вкладки pdf и canvas не активны одновременно — компоненты не спорят
#     за глобальный контекст (cleanup старого выполняется до effect нового). ---
JS_PDF_PANEL_V2 = (
    'const PDFE=u.memo(()=>{const e=Je();'
    'u.useEffect(()=>{window.__devbimIfcCtx=e;return()=>{window.__devbimIfcCtx=null}},[e]);'
    'u.useEffect(()=>()=>Fe.unregisterTab("pdf"),[]);'
    'return o.jsx(yf,{tab:"pdf",children:o.jsx("iframe",{src:"/pdfviewer.html",'
    'title:"PDF",style:{width:"100%",height:"100%",border:"none"}})});});'
    'PDFE.displayName="PDFTab";'
)
# первая версия — без захвата контекста (мигрируется на V2 повторным запуском)
JS_PDF_PANEL_V1 = (
    'const PDFE=u.memo(()=>(u.useEffect(()=>()=>Fe.unregisterTab("pdf"),[]),'
    'o.jsx(yf,{tab:"pdf",children:o.jsx("iframe",{src:"/pdfviewer.html",'
    'title:"PDF",style:{width:"100%",height:"100%",border:"none"}})})));'
    'PDFE.displayName="PDFTab";'
)
JS_APPCONTENT_ANCHOR = 'const cue=u.memo('

# --- App-бандл: гарантия панели «PDF Viewer» в dockview холста (как IFCE у
#     IFC): registerContainer восстанавливает сохранённый layout из storage
#     через fromJSON — колбэк дефолтного layout при этом НЕ вызывается,
#     поэтому панель добавляем ПОСЛЕ регистрации (в onReady goe); добавление
#     само сохраняется через onDidLayoutChange. PDFV, как и IFCV, захватывает
#     Je() в __devbimIfcCtx — неактивные панели dockview демонтируются, активная
#     панель обязана держать контекст моста «To Canvas». ---
JS_ONREADY_OLD = '({api:n})=>{eWe(e,n),IFCE(e,n)}'
JS_ONREADY_NEW = '({api:n})=>{eWe(e,n),IFCE(e,n),PDFP(e,n)}'

# --- App-бандл: компонент pdfviewer в карте компонентов dockview холста
#     (в точке использования, не в литерале JUe — иначе TDZ-ошибка). ---
JS_COMPONENTS_OLD = 'components:{...JUe,ifcviewer:jn(IFCV)},onReady:t,theme:ew'
JS_COMPONENTS_NEW = 'components:{...JUe,ifcviewer:jn(IFCV),pdfviewer:jn(PDFV)},onReady:t,theme:ew'

# --- App-бандл: PDFP (добавление панели) + PDFV (iframe ?embed=1).
#     focusRegion — только "viewer" (общий с Image Viewer; белый список
#     регионов зашит в бандле), tabComponent — t$ (как у панели Image Viewer),
#     иначе addPanel падает. ---
JS_PDF_EMBED_PANEL = (
    'const PDFP=(e,t)=>{try{'
    'const p=[...t.panels];'
    'if(p.some(x=>x.id==="pdfviewer"))return;'
    'const r=p.find(x=>x.id==="ifcviewer")||p.find(x=>x.id==="viewer")||p[0];'
    't.addPanel({id:"pdfviewer",component:"pdfviewer",title:"PDF Viewer",tabComponent:t$,'
    'params:{tab:e,focusRegion:"viewer"},position:{direction:"within",referencePanel:r.id}})'
    '}catch(a){console.warn("PDF panel:",a)}};'
    'const PDFV=u.memo(()=>{const e=Je();'
    'u.useEffect(()=>{window.__devbimIfcCtx=e;return()=>{window.__devbimIfcCtx=null}},[e]);'
    'return o.jsx(yf,{tab:"canvas",children:o.jsx("iframe",{src:"/pdfviewer.html?embed=1",'
    'title:"PDF Viewer",style:{width:"100%",height:"100%",border:"none"}})});});'
    'PDFV.displayName="PDFViewerPanel";'
)

# --- index-бандл: zod-enum activeTab (сохранение вкладки в storage) ---
JS_ENUM_OLD = 'ct(["generate","canvas","upscaling","workflows","models","queue","ifc"])'
JS_ENUM_NEW = 'ct(["generate","canvas","upscaling","workflows","models","queue","ifc","pdf"])'


def deploy_files() -> None:
    shutil.copy2(SRC / "pdf_router.py", ROUTER_DST)
    shutil.copy2(SRC / "pdfviewer.html", DIST / "pdfviewer.html")
    dist_pdf = DIST / "pdf"
    dist_pdf.mkdir(parents=True, exist_ok=True)
    for name in ASSETS:
        shutil.copy2(SRC / "assets" / name, dist_pdf / name)
    print("Роутер развернут:", ROUTER_DST)
    print("Страница развернута:", DIST / "pdfviewer.html")
    print("Ассеты развернуты:", dist_pdf)


def patch_api_app() -> bool:
    s = API_APP.read_text(encoding="utf-8")
    if "include_router(pdf.pdf_router" in s:
        print("api_app.py уже пропатчен, пропуск")
        return False
    if "include_router(ifc.ifc_router" not in s:
        print("ОШИБКА: api_app.py без IFC-роутера — сначала запустите setup_ifcviewer.py")
        sys.exit(1)
    bak = API_APP.with_suffix(".py.pdfviewer-bak")
    if not bak.exists():
        shutil.copy2(API_APP, bak)
    orig = s
    s = s.replace("    ifc,\n", "    ifc,\n    pdf,\n", 1)
    s = s.replace(
        'app.include_router(ifc.ifc_router, prefix="/api")\n',
        'app.include_router(ifc.ifc_router, prefix="/api")\n'
        'app.include_router(pdf.pdf_router, prefix="/api")\n',
        1,
    )
    if s == orig:
        print("ОШИБКА: не найдены точки вставки в api_app.py — патч не применён")
        sys.exit(1)
    API_APP.write_text(s, encoding="utf-8")
    print("api_app.py пропатчен (бэкап:", bak.name + ")")
    return True


def _backup(f: Path) -> Path:
    bak = f.with_suffix(f.suffix + ".pdfviewer-bak")
    if not bak.exists():
        shutil.copy2(f, bak)
    return bak


def patch_app_bundle() -> bool:
    """Кнопка в рейке + панель в TabContent + компонент вкладки +
    панель «PDF Viewer» в dockview холста."""
    targets = [f for f in DIST.glob("assets/*.js") if 'displayName="TabContent"' in f.read_text(encoding="utf-8")]
    if len(targets) != 1:
        print(f"ОШИБКА: бандл с TabContent найден {len(targets)} раз (ожидался 1)")
        sys.exit(1)
    f = targets[0]
    s = f.read_text(encoding="utf-8")

    # мост «To Canvas» общий с IFC-вьювером — без него установка бессмысленна
    if "__devbimIfc" not in s:
        print("ОШИБКА: в App-бандле нет моста __devbimIfc — сначала запустите setup_ifcviewer.py")
        sys.exit(1)

    orig = s

    # --- 1) вкладка «PDF» в левой рейке + TabContent ---
    if JS_PDF_PANEL_V1 in s:
        # миграция PDFE v1 (без захвата __devbimIfcCtx) -> v2
        s = s.replace(JS_PDF_PANEL_V1, JS_PDF_PANEL_V2, 1)
        print("App-бандл: PDFE обновлён (захват __devbimIfcCtx)")
    elif JS_TABCONTENT_NEW not in s:
        for old, new, title in (
            (JS_NAVBAR_OLD, JS_NAVBAR_NEW, "кнопка «PDF» в левой рейке"),
            (JS_TABCONTENT_OLD, JS_TABCONTENT_NEW, "панель PDF в TabContent"),
        ):
            if s.count(old) != 1:
                print(f"ОШИБКА: фрагмент «{title}» найден {s.count(old)} раз (ожидался 1)")
                sys.exit(1)
            s = s.replace(old, new, 1)
        if s.count(JS_APPCONTENT_ANCHOR) < 1 or "AppContent" not in s:
            print("ОШИБКА: не найдена точка вставки компонента PDF-панели")
            sys.exit(1)
        s = s.replace(JS_APPCONTENT_ANCHOR, JS_PDF_PANEL_V2 + JS_APPCONTENT_ANCHOR, 1)
        print("App-бандл: вкладка PDF добавлена")
    else:
        print("App-бандл: вкладка PDF уже на месте, пропуск")

    # --- 2) панель «PDF Viewer» в dockview холста ---
    if JS_ONREADY_NEW in s:
        print("App-бандл: панель PDF на холсте уже на месте, пропуск")
    else:
        for old, new, title in (
            (JS_ONREADY_OLD, JS_ONREADY_NEW, "добавление панели «PDF Viewer» после регистрации dockview"),
            (JS_COMPONENTS_OLD, JS_COMPONENTS_NEW, "компонент pdfviewer в карте dockview"),
        ):
            if s.count(old) != 1:
                print(f"ОШИБКА: фрагмент «{title}» найден {s.count(old)} раз (ожидался 1)")
                sys.exit(1)
            s = s.replace(old, new, 1)
        if s.count(JS_APPCONTENT_ANCHOR) < 1:
            print("ОШИБКА: не найдена точка вставки компонента PDFV")
            sys.exit(1)
        s = s.replace(JS_APPCONTENT_ANCHOR, JS_PDF_EMBED_PANEL + JS_APPCONTENT_ANCHOR, 1)
        print("App-бандл: панель «PDF Viewer» на холсте добавлена")

    if s == orig:
        return False
    bak = _backup(f)
    f.write_text(s, encoding="utf-8")
    print(f"App-бандл пропатчен: {f.name} (бэкап: {bak.name})")
    return True


def patch_index_bundle() -> bool:
    """'pdf' в zod-enum activeTab — иначе перезагрузка со вкладкой PDF
    сбрасывает настройки UI (parse storage падает)."""
    # после патчей более поздних вкладок (designcode) enum содержит записи
    # ПОСЛЕ "pdf" — «уже пропатчено» определяем regex-ом по наличию "pdf"
    # в актуальном enum, а не по точному NEW-фрагменту (та же грабля, что
    # была у setup_ifcviewer, п.20 HANDOFF)
    enum_re = re.compile(r'ct\(\["generate","canvas","upscaling","workflows","models","queue"(?:,"[a-z]+")*\]\)')
    targets: list[Path] = []
    already: list[Path] = []
    for f in DIST.glob("assets/*.js"):
        s = f.read_text(encoding="utf-8")
        if JS_ENUM_OLD in s:
            targets.append(f)
        else:
            m = enum_re.search(s)
            if m and '"pdf"' in m.group(0):
                already.append(f)
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
    print(f"index-бандл пропатчен (enum activeTab + pdf): {f.name} (бэкап: {bak.name})")
    return True


def main() -> None:
    for p in [SRC / "pdf_router.py", SRC / "pdfviewer.html"] + [SRC / "assets" / n for n in ASSETS]:
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
    print("Готово. Перезапустите сервер, затем вкладка «PDF» в левой рейке.")


if __name__ == "__main__":
    main()
