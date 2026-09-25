# -*- coding: utf-8 -*-
"""
Вкладка «IFC» (IFC-вьювер / BIM) в DevBIM / InvokeAI 6.2.0.

Что делает:
  1. Копирует роутер ifc_router.py в venv/Lib/site-packages/invokeai/app/api/routers/
     (API: /api/v1/ifc/list|upload|file/{name}).
  2. Копирует страницу ifcviewer.html и ассеты (dist/ifc/: бандл @thatopen,
     воркер, web-ifc.wasm) в dist фронтенда.
  3. Патчит api_app.py: подключает роутер (бэкап *.ifcviewer-bak).
  4. Патчит собранный JS (бэкап *.ifcviewer-bak):
     - App-бандл: в левую рейку добавляется кнопка «IFC» (после Workflows),
       в TabContent — панель с iframe /ifcviewer.html;
     - App-бандл: на вкладке «Холст» в главную dockview-область добавляется
       панель «IFC Viewer» (iframe /ifcviewer.html?embed=1 — вьювер без
       боковых панелей), рядом с «Image Viewer»; компонент IFCV экспортирует
       мост window.__devbimIfc.toCanvas(imageDTO, generate) — снимок модели
       кладётся на холст подложкой (sentImageToCanvas) БЕЗ слоя маски,
       рамка ставится в 3:2 и слой вписывается в неё (fitToBbox), при
       generate сразу запускается генерация холста (enqueue);
     - index-бандл: 'ifc' добавляется в zod-enum activeTab, чтобы сохранённая
       вкладка пережила перезагрузку страницы.

Идемпотентен: повторный запуск ничего не меняет.
Запуск: venv\\Scripts\\python.exe setup_ifcviewer.py
Восстановление: скопировать *.ifcviewer-bak поверх патченных файлов,
удалить venv/.../routers/ifc.py, dist/ifcviewer.html и dist/ifc/.

Порядок после pip install --force-reinstall invokeai==6.2.0:
  1. rebrand_devbim.py  2. setup_imagerouter.py  3. setup_ifcviewer.py
"""
import re
import shutil
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
SRC = BASE / "ifc"
VENV = BASE / "venv"
SP = VENV / "Lib" / "site-packages"
DIST = SP / "invokeai" / "frontend" / "web" / "dist"
ROUTER_DST = SP / "invokeai" / "app" / "api" / "routers" / "ifc.py"
API_APP = SP / "invokeai" / "app" / "api_app.py"

ASSETS = ("thatopen.mjs", "worker.mjs", "web-ifc.wasm")

# --- App-бандл: кнопка «IFC» в левой рейке (после Workflows) ---
JS_NAVBAR_OLD = 'a&&o.jsx(Ad,{tab:"workflows",icon:o.jsx(M1,{}),label:e("ui.tabs.workflows")})'
JS_NAVBAR_NEW = (
    'a&&o.jsx(Ad,{tab:"workflows",icon:o.jsx(M1,{}),label:e("ui.tabs.workflows")}),'
    'o.jsx(Ad,{tab:"ifc",icon:o.jsx(RA,{}),label:"IFC"})'
)

# --- App-бандл: панель вкладки в TabContent (iframe со страницей вьювера) ---
JS_TABCONTENT_OLD = 'i&&e==="workflows"&&o.jsx(lue,{})'
JS_TABCONTENT_NEW = 'i&&e==="workflows"&&o.jsx(lue,{}),e==="ifc"&&o.jsx(IFE,{})'

# --- App-бандл: компонент панели (вставляется перед AppContent) ---
# V2: как PDFE/PDFV, IFE захватывает Je() (redux-store {dispatch,getState})
# в window.__devbimIfcCtx — иначе «📸 To Canvas» из ПОЛНОЦЕННОЙ вкладки IFC
# падает «canvas context unavailable»: мост __devbimIfc.toCanvas работает
# только пока какая-то смонтированная панель держит контекст, а раньше его
# держали лишь IFCV (embed-панель на холсте) и PDFE/PDFV. Вкладки ifc и
# canvas не активны одновременно — за глобаль не спорят.
JS_IFC_PANEL_V2 = (
    'const IFE=u.memo(()=>{const e=Je();'
    'u.useEffect(()=>{window.__devbimIfcCtx=e;return()=>{window.__devbimIfcCtx=null}},[e]);'
    'u.useEffect(()=>()=>Fe.unregisterTab("ifc"),[]);'
    'return o.jsx(yf,{tab:"ifc",children:o.jsx("iframe",{src:"/ifcviewer.html",'
    'title:"IFC",style:{width:"100%",height:"100%",border:"none"}})});});'
    'IFE.displayName="IFCTab";'
)
# первая версия — без захвата контекста (мигрируется на V2 повторным запуском)
JS_IFC_PANEL = (
    'const IFE=u.memo(()=>(u.useEffect(()=>()=>Fe.unregisterTab("ifc"),[]),'
    'o.jsx(yf,{tab:"ifc",children:o.jsx("iframe",{src:"/ifcviewer.html",'
    'title:"IFC",style:{width:"100%",height:"100%",border:"none"}})})));'
    'IFE.displayName="IFCTab";'
)
JS_APPCONTENT_ANCHOR = 'const cue=u.memo('

# --- index-бандл: zod-enum activeTab (сохранение вкладки в storage) ---
JS_ENUM_OLD = 'ct(["generate","canvas","upscaling","workflows","models","queue"])'
JS_ENUM_NEW = 'ct(["generate","canvas","upscaling","workflows","models","queue","ifc"])'

# --- App-бандл: гарантия панели «IFC Viewer» в dockview холста.
#     registerContainer восстанавливает сохранённый layout из storage через
#     fromJSON — колбэк дефолтного layout (eWe) при этом НЕ вызывается,
#     поэтому панель добавляем ПОСЛЕ регистрации (в onReady goe): покрывает и
#     свежие, и уже сохранённые layout'ы; добавление само сохраняется в
#     storage через onDidLayoutChange (дебаунс 300 мс). ---
JS_ONREADY_OLD = '({api:n})=>{eWe(e,n)}'
JS_ONREADY_NEW = '({api:n})=>{eWe(e,n),IFCE(e,n)}'

# --- App-бандл: компонент ifcviewer в карте компонентов dockview холста.
#     Расширяем в точке использования (в рендере goe), а не в литерале JUe={...}:
#     IFCV определяется позже по файлу, в литерале была бы TDZ-ошибка. ---
JS_COMPONENTS_OLD = 'components:JUe,onReady:t,theme:ew'
JS_COMPONENTS_NEW = 'components:{...JUe,ifcviewer:jn(IFCV)},onReady:t,theme:ew'

# --- App-бандл: IFCE + компонент IFCV (iframe ?embed=1) + мост iframe -> холст.
#     Je() даёт {dispatch,getState}; _c — sentImageToCanvas (та же функция,
#     что за кнопкой «Редактировать»/Edit в Image Viewer); ru — атом
#     менеджера холста (ЧИТАТЬ ru.get(), НЕ $p() — $p=()=>ie(ru) это ХУК
#     useSyncExternalStore, вызов вне компонента роняет React #321); QCe —
#     enqueue генерации холста (то же, что кнопка Generate на холсте).
#     «На холст» V3: withInpaintMask:!1 — слой «Маска перерисовки» НЕ
#     создаётся, кисть НЕ включается (нужна маска — виджет слоёв сверху);
#     ФОКУС-РЕГИОН: только "viewer" (общий с Image Viewer) — список
#     разрешённых регионов зашит в бандле (q2e), посторонний регион роняет
#     рендер панели (useFocusRegion читает K2e["$"+region]).
#     TAB-КОМПОНЕНТ: t$ — тот же, что у панели Image Viewer на холсте
#     (карта tabComponents вкладки canvas — QUe — знает только launchpad/
#     viewer/workspace; посторонний id роняет addPanel). ---
# V3 (25.09, п.56): БЕЗ «Маски перерисовки» и кисти; после укладки снимка
# рамка ставится в 3:2 сырым экшеном {type:"canvas/bboxAspectRatioIdChanged"}
# (строка типа стабильна между сборками, в отличие от минифицированных имён),
# затем слой вписывается в рамку той же последовательностью, что пункт
# «Fit to Bbox» меню слоя: startTransform({silent:!0}) -> fitToBboxContain()
# -> applyTransform(). Рамка — ПОСЛЕ _c: sentImageToCanvas ставит bbox.rect
# под пропорции картинки (bboxChangedFromCanvas), а редьюсер при смене
# пропорций сбрасывает aspectRatio.id в "Free" — отсюда и брался «Free».
#     Fit ждёт ГЛУБЖЕ, чем менеджер: адаптер слоя существует сразу, но
#     картинка рендерится асинхронно — пока не готова, у трансформера
#     $pixelRect 0x0, fitToBboxContain делит на proxyRect.width()=0 →
#     scale=Infinity, applyTransform растеризует пустой прямоугольник
#     (replaceObjects:!0) и СЛОЙ ТЕРЯЕТ объекты (поймано E2E в headless).
JS_BRIDGE_V3 = (
    'window.__devbimIfc={async toCanvas(e,t){'
    'const n=window.__devbimIfcCtx;'
    'if(!n)throw new Error("IFC: canvas context unavailable");'
    'await Fe.focusPanel("canvas",On),'
    'await _c({imageDTO:e,withResize:!1,withInpaintMask:!1,type:"raster_layer",'
    'dispatch:n.dispatch,getState:n.getState});'
    'n.dispatch({type:"canvas/bboxAspectRatioIdChanged",payload:{id:"3:2"}});'
    'let s=ru.get();'
    'for(let i=0;i<20&&!s;i++)await new Promise(k=>setTimeout(k,100)),s=ru.get();'
    'if(!s)throw new Error("IFC: canvas manager unavailable");'
    'const cs=()=>{const c=n.getState().canvas;return c&&c.present?c.present:c};'
    'let d=null;'
    'for(let i=0;i<40&&!d;i++){'
    'const sel=cs().selectedEntityIdentifier;'
    'if(sel&&sel.type==="raster_layer"){const a=s.getAdapter(sel),p=a&&a.transformer&&a.transformer.$pixelRect&&a.transformer.$pixelRect.get();'
    'p&&p.width>0&&p.height>0&&(d=a)}'
    'if(!d)await new Promise(k=>setTimeout(k,100))}'
    'if(d)try{await d.transformer.startTransform({silent:!0}),'
    'd.transformer.fitToBboxContain(),await d.transformer.applyTransform()}'
    'catch(y){console.warn("devbim fitToBbox:",y)}'
    'if(t)await QCe(n,s,!1)}};'
)
# Мост второй версии (withInpaintMask:!0 + кисть, рамка под снимок) —
# нужен для миграции уже пропатченных бандлов на поведение V3.
JS_BRIDGE_V2 = (
    'window.__devbimIfc={async toCanvas(e,t){'
    'const n=window.__devbimIfcCtx;'
    'if(!n)throw new Error("IFC: canvas context unavailable");'
    'await Fe.focusPanel("canvas",On),'
    'await _c({imageDTO:e,withResize:!1,withInpaintMask:!0,type:"raster_layer",'
    'dispatch:n.dispatch,getState:n.getState});'
    'let s=ru.get();'
    'for(let i=0;i<20&&!s;i++)await new Promise(k=>setTimeout(k,100)),s=ru.get();'
    'if(!s)throw new Error("IFC: canvas manager unavailable");'
    'try{s.tool.$tool.set("brush")}catch(a){}'
    'if(t)await QCe(n,s,!1)}};'
)
JS_IFC_EMBED_PANEL = (
    'const IFCE=(e,t)=>{try{'
    'const p=[...t.panels];'
    'if(p.some(x=>x.id==="ifcviewer"))return;'
    'const r=p.find(x=>x.id==="viewer")||p[0];'
    't.addPanel({id:"ifcviewer",component:"ifcviewer",title:"IFC Viewer",tabComponent:t$,'
    'params:{tab:e,focusRegion:"viewer"},position:{direction:"within",referencePanel:r.id}})'
    '}catch(a){console.warn("IFC panel:",a)}};'
    'const IFCV=u.memo(()=>{const e=Je();'
    'u.useEffect(()=>{window.__devbimIfcCtx=e;return()=>{window.__devbimIfcCtx=null}},[e]);'
    'return o.jsx(yf,{tab:"canvas",children:o.jsx("iframe",{src:"/ifcviewer.html?embed=1",'
    'title:"IFC Viewer",style:{width:"100%",height:"100%",border:"none"}})});});'
    'IFCV.displayName="IFCViewerPanel";'
) + JS_BRIDGE_V3

# Мост первой версии (withInpaintMask:!1, инструмент не переключался) —
# нужен для миграции уже пропатченных бандлов на поведение V3.
JS_BRIDGE_V1 = (
    'window.__devbimIfc={async toCanvas(e,t){'
    'const n=window.__devbimIfcCtx;'
    'if(!n)throw new Error("IFC: canvas context unavailable");'
    'await Fe.focusPanel("canvas",On),'
    'await _c({imageDTO:e,withResize:!1,withInpaintMask:!1,type:"raster_layer",'
    'dispatch:n.dispatch,getState:n.getState});'
    'if(t){let s=ru.get();'
    'for(let i=0;i<20&&!s;i++)await new Promise(k=>setTimeout(k,100)),s=ru.get();'
    'if(!s)throw new Error("IFC: canvas manager unavailable");'
    'await QCe(n,s,!1)}}};'
)


# Ревизии внутри V3 (миграция уже задеплоенных V3-мостов): ревизия 1 ждала
# только адаптер слоя — fit на нерендеренной картинке терял объекты,
# ревизия 2 ждёт ненулевой $pixelRect трансформера.
JS_V3_R1_WAIT_OLD = (
    'for(let i=0;i<20&&!d;i++){'
    'const sel=cs().selectedEntityIdentifier;'
    'if(sel&&sel.type==="raster_layer"){const a=s.getAdapter(sel);'
    'a&&a.transformer&&(d=a)}'
    'if(!d)await new Promise(k=>setTimeout(k,100))}'
)
JS_V3_R2_WAIT_NEW = (
    'for(let i=0;i<40&&!d;i++){'
    'const sel=cs().selectedEntityIdentifier;'
    'if(sel&&sel.type==="raster_layer"){const a=s.getAdapter(sel),p=a&&a.transformer&&a.transformer.$pixelRect&&a.transformer.$pixelRect.get();'
    'p&&p.width>0&&p.height>0&&(d=a)}'
    'if(!d)await new Promise(k=>setTimeout(k,100))}'
)


def deploy_files() -> None:
    shutil.copy2(SRC / "ifc_router.py", ROUTER_DST)
    shutil.copy2(SRC / "ifcviewer.html", DIST / "ifcviewer.html")
    dist_ifc = DIST / "ifc"
    dist_ifc.mkdir(parents=True, exist_ok=True)
    for name in ASSETS:
        shutil.copy2(SRC / "assets" / name, dist_ifc / name)
    print("Роутер развернут:", ROUTER_DST)
    print("Страница развернута:", DIST / "ifcviewer.html")
    print("Ассеты развернуты:", dist_ifc)


def patch_api_app() -> bool:
    s = API_APP.read_text(encoding="utf-8")
    if "include_router(ifc.ifc_router" in s:
        print("api_app.py уже пропатчен, пропуск")
        return False
    bak = API_APP.with_suffix(".py.ifcviewer-bak")
    if not bak.exists():
        shutil.copy2(API_APP, bak)
    orig = s
    s = s.replace("    images,\n", "    images,\n    ifc,\n", 1)
    s = s.replace(
        'app.include_router(imagerouter.imagerouter_router, prefix="/api")\n',
        'app.include_router(imagerouter.imagerouter_router, prefix="/api")\n'
        'app.include_router(ifc.ifc_router, prefix="/api")\n',
        1,
    )
    if s == orig:
        print("ОШИБКА: не найдены точки вставки в api_app.py — патч не применён")
        sys.exit(1)
    API_APP.write_text(s, encoding="utf-8")
    print("api_app.py пропатчен (бэкап:", bak.name + ")")
    return True


def _backup(f: Path) -> Path:
    bak = f.with_suffix(f.suffix + ".ifcviewer-bak")
    if not bak.exists():
        shutil.copy2(f, bak)
    return bak


def patch_app_bundle() -> bool:
    """Кнопка в рейке + панель в TabContent + компонент панели; панель
    «IFC Viewer» в dockview холста + мост iframe -> холст."""
    targets = [f for f in DIST.glob("assets/*.js") if 'displayName="TabContent"' in f.read_text(encoding="utf-8")]
    if len(targets) != 1:
        print(f"ОШИБКА: бандл с TabContent найден {len(targets)} раз (ожидался 1)")
        sys.exit(1)
    f = targets[0]
    s = f.read_text(encoding="utf-8")
    orig = s

    # 1) вкладка «IFC» в левой рейке
    if JS_TABCONTENT_NEW in s:
        if JS_IFC_PANEL_V2 in s:
            print("App-бандл: вкладка IFC уже на месте, пропуск")
        elif JS_IFC_PANEL in s:
            # миграция IFE v1 (без захвата __devbimIfcCtx) -> v2
            s = s.replace(JS_IFC_PANEL, JS_IFC_PANEL_V2, 1)
            print("App-бандл: IFE обновлён (захват __devbimIfcCtx для To Canvas из вкладки IFC)")
        else:
            print("App-бандл: вкладка IFC уже на месте (IFE не найден), пропуск")
    else:
        for old, new, title in (
            (JS_NAVBAR_OLD, JS_NAVBAR_NEW, "кнопка «IFC» в левой рейке"),
            (JS_TABCONTENT_OLD, JS_TABCONTENT_NEW, "панель IFC в TabContent"),
        ):
            if s.count(old) != 1:
                print(f"ОШИБКА: фрагмент «{title}» найден {s.count(old)} раз (ожидался 1)")
                sys.exit(1)
            s = s.replace(old, new, 1)
        if s.count(JS_APPCONTENT_ANCHOR) < 1 or "AppContent" not in s:
            print("ОШИБКА: не найдена точка вставки компонента IFC-панели")
            sys.exit(1)
        s = s.replace(JS_APPCONTENT_ANCHOR, JS_IFC_PANEL_V2 + JS_APPCONTENT_ANCHOR, 1)
        print("App-бандл: вкладка IFC добавлена")

    # 2) панель «IFC Viewer» на вкладке «Холст» + мост к холсту
    if "__devbimIfc" in s:
        if JS_BRIDGE_V3 in s:
            print("App-бандл: панель IFC на холсте уже на месте, пропуск")
        elif JS_BRIDGE_V2 in s:
            s = s.replace(JS_BRIDGE_V2, JS_BRIDGE_V3, 1)
            print("App-бандл: мост IFC->холст обновлён до V3 (без маски, рамка 3:2 + fitToBbox)")
        elif JS_BRIDGE_V1 in s:
            s = s.replace(JS_BRIDGE_V1, JS_BRIDGE_V3, 1)
            print("App-бандл: мост IFC->холст обновлён до V3 (без маски, рамка 3:2 + fitToBbox)")
        elif JS_V3_R1_WAIT_OLD in s:
            s = s.replace(JS_V3_R1_WAIT_OLD, JS_V3_R2_WAIT_NEW, 1)
            print("App-бандл: мост V3 обновлён (fit ждёт $pixelRect>0)")
        else:
            print("ОШИБКА: мост __devbimIfc неизвестной версии — патч не применён")
            sys.exit(1)
    else:
        for old, new, title in (
            (JS_ONREADY_OLD, JS_ONREADY_NEW, "добавление панели «IFC Viewer» после регистрации dockview"),
            (JS_COMPONENTS_OLD, JS_COMPONENTS_NEW, "компонент ifcviewer в карте dockview"),
        ):
            if s.count(old) != 1:
                print(f"ОШИБКА: фрагмент «{title}» найден {s.count(old)} раз (ожидался 1)")
                sys.exit(1)
            s = s.replace(old, new, 1)
        if s.count(JS_APPCONTENT_ANCHOR) < 1:
            print("ОШИБКА: не найдена точка вставки компонента IFCV")
            sys.exit(1)
        s = s.replace(JS_APPCONTENT_ANCHOR, JS_IFC_EMBED_PANEL + JS_APPCONTENT_ANCHOR, 1)
        print("App-бандл: панель IFC на холсте добавлена")

    if s == orig:
        return False
    bak = _backup(f)
    f.write_text(s, encoding="utf-8")
    print(f"App-бандл пропатчен: {f.name} (бэкап: {bak.name})")
    return True


def patch_index_bundle() -> bool:
    """'ifc' в zod-enum activeTab — иначе перезагрузка со вкладкой IFC
    сбрасывает настройки UI (parse storage падает)."""
    # после патчей других вкладок (pdf) enum может содержать дополнительные
    # записи ПОСЛЕ "ifc" — «уже пропатчено» определяем regex-ом по наличию
    # "ifc" в актуальном enum, а не по точному NEW-фрагменту
    enum_re = re.compile(r'ct\(\["generate","canvas","upscaling","workflows","models","queue"(?:,"[a-z]+")*\]\)')
    targets: list[Path] = []
    already: list[Path] = []
    for f in DIST.glob("assets/*.js"):
        s = f.read_text(encoding="utf-8")
        if JS_ENUM_OLD in s:
            targets.append(f)
        else:
            m = enum_re.search(s)
            if m and '"ifc"' in m.group(0):
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
    print(f"index-бандл пропатчен (enum activeTab + ifc): {f.name} (бэкап: {bak.name})")
    return True


def main() -> None:
    for p in [SRC / "ifc_router.py", SRC / "ifcviewer.html"] + [SRC / "assets" / n for n in ASSETS]:
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
    print("Готово. Перезапустите сервер, затем вкладка «IFC» в левой рейке.")


if __name__ == "__main__":
    main()
