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
    """Кнопка в рейке + панель в TabContent + компонент панели."""
    targets = [f for f in DIST.glob("assets/*.js") if 'displayName="TabContent"' in f.read_text(encoding="utf-8")]
    if len(targets) != 1:
        print(f"ОШИБКА: бандл с TabContent найден {len(targets)} раз (ожидался 1)")
        sys.exit(1)
    f = targets[0]
    s = f.read_text(encoding="utf-8")
    if JS_TABCONTENT_NEW in s:
        print("App-бандл уже пропатчен (вкладка IFC на месте), пропуск")
        return False
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
    s = s.replace(JS_APPCONTENT_ANCHOR, JS_IFC_PANEL + JS_APPCONTENT_ANCHOR, 1)
    bak = _backup(f)
    f.write_text(s, encoding="utf-8")
    print(f"App-бандл пропатчен (вкладка IFC): {f.name} (бэкап: {bak.name})")
    return True


def patch_index_bundle() -> bool:
    """'ifc' в zod-enum activeTab — иначе перезагрузка со вкладкой IFC
    сбрасывает настройки UI (parse storage падает)."""
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
