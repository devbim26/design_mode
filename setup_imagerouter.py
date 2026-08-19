# -*- coding: utf-8 -*-
"""
Интеграция ImageRouter (docs.imagerouter.io) в DevBIM / InvokeAI 6.2.0.

Что делает:
  1. Копирует роутер-прокси imagerouter_router.py в
     venv/Lib/site-packages/invokeai/app/api/routers/imagerouter.py
     (API: /api/v1/imagerouter/status|key|credits|models|generate).
  2. Копирует страницу imagerouter.html в dist фронтенда — открывается как
     вкладка «ImageRouter» в Model Manager.
  3. Патчит api_app.py: подключает роутер (бэкап *.imagerouter-bak).
  4. Патчит собранный JS: в Model Manager вкладки добавления локальных моделей
     (Launchpad / URL или локальный путь / HuggingFace / Сканировать папку /
     Стартовые модели) и очередь установки заменяются одной вкладкой
     «ImageRouter» с iframe-страницей (бэкап *.imagerouter-bak).

Идемпотентен: повторный запуск ничего не меняет.
Запуск: venv\Scripts\python.exe setup_imagerouter.py
Восстановление: скопировать *.imagerouter-bak поверх патченных файлов
и удалить venv/.../routers/imagerouter.py и dist/imagerouter.html.

Требование: rebrand_devbim.py уже применён (не обязательно, но
регулярное выражение рассчитано на текущее состояние бандла).
"""
import re
import shutil
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
SRC = BASE / "imagerouter"
VENV = BASE / "venv"
SP = VENV / "Lib" / "site-packages"
DIST = SP / "invokeai" / "frontend" / "web" / "dist"
ROUTER_DST = SP / "invokeai" / "app" / "api" / "routers" / "imagerouter.py"
API_APP = SP / "invokeai" / "app" / "api_app.py"

# Новый компонент InstallModels: одна вкладка ImageRouter с iframe.
# __NAME__ — имя минифицированного компонента из оригинального бандла.
JS_NEW_COMPONENT = (
    'const __NAME__=u.memo(()=>{const{t:e}=M();'
    'return o.jsxs(E,{layerStyle:"first",borderRadius:"base",w:"full",h:"full",flexDir:"column",gap:4,children:['
    'o.jsxs(E,{alignItems:"center",justifyContent:"space-between",children:['
    'o.jsx(Ct,{fontSize:"xl",children:"ImageRouter"}),'
    'o.jsx(pe,{alignItems:"center",variant:"link",leftIcon:o.jsx(Zp,{}),'
    'onClick:()=>window.open("https://docs.imagerouter.io/"),'
    'children:o.jsx(W,{variant:"subtext",children:"docs.imagerouter.io"})})'
    ']}),'
    'o.jsxs(a1,{variant:"collapse",height:"100%",display:"flex",flexDir:"column",index:0,children:['
    'o.jsxs(r1,{children:[o.jsx(bs,{children:"ImageRouter"})]}),'
    'o.jsxs(l1,{p:3,height:"100%",children:['
    'o.jsx(Cs,{height:"100%",children:o.jsx("iframe",{src:"/imagerouter.html",title:"ImageRouter",'
    'style:{width:"100%",height:"100%",minHeight:"240px",border:"none"}})})'
    ']})]})]})});__NAME__.displayName="InstallModels";'
)

# Оригинальный InstallModels: аккордеон с 5 вкладками локальной установки.
JS_OLD_RE = re.compile(
    r'const (\w+)=u\.memo\(\(\)=>\{const\{t:e\}=M\(\),t=ie\(nI\),'
    r'n=u\.useCallback\(\(\)=>\{window\.open\("[^"]*"\)\},\[\]\);'
    r'.*?displayName="InstallModels";',
    re.DOTALL,
)


def deploy_files() -> None:
    shutil.copy2(SRC / "imagerouter_router.py", ROUTER_DST)
    shutil.copy2(SRC / "imagerouter.html", DIST / "imagerouter.html")
    print("Роутер развернут:", ROUTER_DST)
    print("Страница развернута:", DIST / "imagerouter.html")


def patch_api_app() -> bool:
    s = API_APP.read_text(encoding="utf-8")
    if "include_router(imagerouter.imagerouter_router" in s:
        print("api_app.py уже пропатчен, пропуск")
        return False
    bak = API_APP.with_suffix(".py.imagerouter-bak")
    if not bak.exists():
        shutil.copy2(API_APP, bak)
    orig = s
    s = s.replace("    images,\n", "    images,\n    imagerouter,\n", 1)
    s = s.replace(
        'app.include_router(style_presets.style_presets_router, prefix="/api")\n',
        'app.include_router(style_presets.style_presets_router, prefix="/api")\n'
        'app.include_router(imagerouter.imagerouter_router, prefix="/api")\n',
        1,
    )
    # Мидлварь моделей ImageRouter — регистрируется ДО add_middleware(CORS/GZip),
    # чтобы оказаться внутри них и работать с несжатым JSON.
    s = s.replace(
        "socket_io = SocketIO(app)\n",
        "socket_io = SocketIO(app)\n"
        "app.add_middleware(imagerouter.ImageRouterCanvasMiddleware)\n",
        1,
    )
    if s == orig:
        print("ОШИБКА: не найдены точки вставки в api_app.py — патч не применён")
        sys.exit(1)
    API_APP.write_text(s, encoding="utf-8")
    print("api_app.py пропатчен (бэкап:", bak.name + ")")
    return True


def patch_js() -> bool:
    targets = [f for f in DIST.glob("assets/*.js") if "launchpadTab" in f.read_text(encoding="utf-8")]
    if not targets:
        already = [f for f in DIST.glob("assets/*.js") if "imagerouter.html" in f.read_text(encoding="utf-8")]
        if already:
            print("JS уже пропатчен (вкладка ImageRouter на месте), пропуск")
            return False
        print("ОШИБКА: не найден бандл с вкладками Model Manager")
        sys.exit(1)
    if len(targets) > 1:
        print("ОШИБКА: несколько кандидатов:", [t.name for t in targets])
        sys.exit(1)
    f = targets[0]
    s = f.read_text(encoding="utf-8")
    matches = JS_OLD_RE.findall(s)
    if len(matches) != 1:
        print(f"ОШИБКА: компонент InstallModels найден {len(matches)} раз (ожидался 1) в {f.name}")
        sys.exit(1)
    new_component = JS_NEW_COMPONENT.replace("__NAME__", matches[0])
    s2 = JS_OLD_RE.sub(lambda m: new_component, s, count=1)
    bak = f.with_suffix(f.suffix + ".imagerouter-bak")
    if not bak.exists():
        shutil.copy2(f, bak)
    f.write_text(s2, encoding="utf-8")
    print(f"JS пропатчен: {f.name} (бэкап: {bak.name})")
    return True


def patch_generate_button() -> bool:
    """Главная кнопка генерации называется 'DevBIM' (после ребрендинга) —
    переименовываем в понятную 'Generate' и правим подсказки про неё."""
    changed = False
    for f in DIST.glob("assets/*.js"):
        s = f.read_text(encoding="utf-8")
        if 'm7="DevBIM"' in s:
            f.write_text(s.replace('m7="DevBIM"', 'm7="Generate"'), encoding="utf-8")
            print(f"Кнопка генерации переименована (DevBIM -> Generate): {f.name}")
            changed = True
    n = 0
    for f in DIST.glob("locales/*.json"):
        s = f.read_text(encoding="utf-8")
        orig = s
        for a, b in (
            ("Pressing DevBIM", "Pressing Generate"),
            ("Press DevBIM", "Press Generate"),
            ("click the DevBIM button", "click the Generate button"),
            ("<StrongComponent>DevBIM</StrongComponent>", "<StrongComponent>Generate</StrongComponent>"),
        ):
            s = s.replace(a, b)
        if s != orig:
            f.write_text(s, encoding="utf-8")
            n += 1
    if n:
        print(f"Подсказок про кнопку обновлено в {n} локалях")
    if not changed and not n:
        print("Кнопка генерации уже переименована, пропуск")
    return changed or n > 0


def main() -> None:
    for p in (SRC / "imagerouter_router.py", SRC / "imagerouter.html", DIST, API_APP.parent):
        if not p.exists():
            print("Не найдено:", p)
            sys.exit(1)
    deploy_files()
    patch_api_app()
    patch_js()
    patch_generate_button()
    print("Готово. Перезапустите сервер, затем: Model Manager → «Добавить модели» → вкладка ImageRouter.")


if __name__ == "__main__":
    main()
