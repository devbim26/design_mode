# -*- coding: utf-8 -*-
"""
Интеграция ImageRouter (docs.imagerouter.io) в DevBIM / InvokeAI 6.2.0.

Что делает:
  1. Копирует роутер-прокси imagerouter_router.py в
     venv/Lib/site-packages/invokeai/app/api/routers/imagerouter.py
     (API: /api/v1/imagerouter/status|key|credits|models|generate|admin-auth).
  2. Копирует страницу imagerouter.html в dist фронтенда — открывается как
     вкладка «ImageRouter» в Model Manager.
  3. Патчит api_app.py: подключает роутер (бэкап *.imagerouter-bak).
  4. Патчит собранный JS: в Model Manager вкладки добавления локальных моделей
     (Launchpad / URL или локальный путь / HuggingFace / Сканировать папку /
     Стартовые модели) и очередь установки заменяются одной вкладкой
     «ImageRouter» с iframe-страницей (бэкап *.imagerouter-bak).
  5. Патчит собранный JS: в левой панели Generate/Canvas скрываются параметры,
     относящиеся только к локальным моделям (Refiner, Advanced/VAE, Compositing,
     Concepts/LoRA, «Advanced Options» с Scheduler/Steps/CFG). Остаётся только
     то, что использует ImageRouter API: промпт, модель, размер, seed.
  6. Админский доступ по паролю (.env: ADMIN_PASSWORD):
     - вкладка «Модели» убирается из левой рейки;
     - в меню (шестерёнка «Настройки») добавляется пункт «Менеджер моделей»;
     - клик по шестерёнке и по пункту открывает модальное окно пароля
       (dist/devbim-admin.js, проверка через POST /api/v1/imagerouter/admin-auth);
     - переключение на вкладку «models» из любых мест UI (кнопка в выборе
       модели, горячие клавиши) без пароля блокируется (патч switchToTab).

Секреты (ключ ImageRouter, админский пароль) читаются сервером из .env
в корне проекта; скрипт создаёт .env по шаблону, если его ещё нет.

Идемпотентен: повторный запуск ничего не меняет.
Запуск: venv\Scripts\python.exe setup_imagerouter.py
Восстановление: скопировать *.imagerouter-bak поверх патченных файлов
и удалить venv/.../routers/imagerouter.py, dist/imagerouter.html
и dist/devbim-admin.js.

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
INDEX_HTML = DIST / "index.html"
ADMIN_JS_DST = DIST / "devbim-admin.js"

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
    shutil.copy2(SRC / "devbim_admin.js", ADMIN_JS_DST)
    print("Роутер развернут:", ROUTER_DST)
    print("Страница развернута:", DIST / "imagerouter.html")
    print("Скрипт админдоступа развернут:", ADMIN_JS_DST)


def ensure_env_file() -> None:
    """Создаёт .env в корне проекта по шаблону, если его ещё нет.
    Существующий файл не трогает — это источник ключа и админского пароля."""
    env = BASE / ".env"
    if env.exists():
        print(".env на месте:", env)
        return
    key = ""
    ir_json = BASE / "data" / "imagerouter.json"
    try:
        import json

        key = json.loads(ir_json.read_text(encoding="utf-8")).get("api_key", "")
    except Exception:
        pass
    env.write_text(
        "# DevBIM Image Studio — секреты сервера (читаются при запуске).\n"
        f"IMAGEROUTER_API_KEY={key}\n"
        "ADMIN_PASSWORD=change-me\n",
        encoding="utf-8",
    )
    print("Создан .env по шаблону:", env, "— задайте ADMIN_PASSWORD!")


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


# ----------------------------------------------------------------------------
# Скрытие параметров локальных моделей в левой панели (генерация только via API)
#
# Убираются из рендера (Generate и Canvas):
#   - аккордеон «Refiner» (SDXL-рефайнер — локальная модель);
#   - аккордеон «Advanced» (VAE, VAE Precision, CFG Rescale, Seamless X/Y);
#   - аккордеон «Compositing» (Coherence/Infill — локальный пайплайн, Canvas);
#   - «Concepts»/LoRA-лист внутри аккордеона «Generation»;
#   - сворачиваемый блок «Advanced Options» (Scheduler, Steps, CFG Scale).
# Остаются параметры, релевантные ImageRouter API: промпт, модель,
# размер (size), seed, Reference Image.
# ----------------------------------------------------------------------------

# ParametersPanelCanvas: [... Compositing, Refiner, Advanced] -> [промпт, image, generation]
JS_CANVAS_PANEL_OLD = (
    'children:[o.jsx(J5,{}),o.jsx(ise,{}),o.jsx(sM,{}),!s&&o.jsx(Bne,{}),'
    'e&&o.jsx(iM,{}),!t&&!s&&o.jsx(eM,{})]'
)
JS_CANVAS_PANEL_NEW = 'children:[o.jsx(J5,{}),o.jsx(ise,{}),o.jsx(sM,{})]'

# ParametersPanelGenerate: [... Refiner, Advanced] -> [промпт, image, generation]
JS_GENERATE_PANEL_OLD = (
    'children:[o.jsx(J5,{}),o.jsx(Aoe,{}),o.jsx(sM,{}),'
    'e&&o.jsx(iM,{}),!t&&!s&&o.jsx(eM,{})]'
)
JS_GENERATE_PANEL_NEW = 'children:[o.jsx(J5,{}),o.jsx(Aoe,{}),o.jsx(sM,{})]'

# GenerationSettingsAccordion: без Concepts (LoRA) и без «Advanced Options»
JS_GENERATION_ACC_OLD = (
    'pb:a?4:0,children:[o.jsx(Une,{}),o.jsx(nM,{}),!a&&o.jsx(Vne,{}),!a&&o.jsx(tM,{})]}),'
    '!a&&o.jsx(xC,{label:e("accordions.advanced.options"),isOpen:d,onToggle:h,'
    'children:o.jsx(E,{gap:4,flexDir:"column",pb:4,children:o.jsxs(Ds,{formLabelProps:XVe,'
    'children:[!n&&!s&&!i&&o.jsx(qVe,{}),o.jsx(Hne,{}),n&&t&&!Cz(t)&&o.jsx(Gne,{}),'
    '!n&&o.jsx(HVe,{})]})})})]})'
)
JS_GENERATION_ACC_NEW = 'pb:a?4:0,children:[o.jsx(Une,{}),o.jsx(nM,{})]})]})'

JS_LEFT_PANEL_PATCHES = (
    (JS_CANVAS_PANEL_OLD, JS_CANVAS_PANEL_NEW, "панель Canvas"),
    (JS_GENERATE_PANEL_OLD, JS_GENERATE_PANEL_NEW, "панель Generate"),
    (JS_GENERATION_ACC_OLD, JS_GENERATION_ACC_NEW, "аккордеон Generation"),
)


def patch_left_panel() -> bool:
    """Убирает из левой панели параметры, относящиеся только к локальным моделям."""
    targets = [
        f for f in DIST.glob("assets/*.js")
        if 'displayName="ParametersPanelCanvas"' in f.read_text(encoding="utf-8")
    ]
    if len(targets) != 1:
        print(f"ОШИБКА: бандл с левой панелью найден {len(targets)} раз (ожидался 1)")
        sys.exit(1)
    f = targets[0]
    s = f.read_text(encoding="utf-8")
    if all(old not in s for old, _, _ in JS_LEFT_PANEL_PATCHES):
        if 'e&&o.jsx(iM,{})' not in s and '!a&&o.jsx(Vne,{})' not in s:
            print("Локальные параметры уже скрыты, пропуск")
            return False
        print("ОШИБКА: не найдены фрагменты левой панели (частичная правка?)")
        sys.exit(1)
    for old, new, title in JS_LEFT_PANEL_PATCHES:
        if s.count(old) != 1:
            print(f"ОШИБКА: фрагмент «{title}» найден {s.count(old)} раз (ожидался 1)")
            sys.exit(1)
        s = s.replace(old, new, 1)
    bak = f.with_suffix(f.suffix + ".imagerouter-bak")
    if not bak.exists():
        shutil.copy2(f, bak)
    f.write_text(s, encoding="utf-8")
    print(f"Локальные параметры скрыты в левой панели: {f.name} (бэкап: {bak.name})")
    return True


# ----------------------------------------------------------------------------
# Скрытие Control Layer (ControlNet) в меню добавления слоёв канваса.
# ControlNet-модели в облачной схеме не используются (генерация только через
# ImageRouter API), пункт «Слой управления» из меню «+» (EntityListGlobal-
# ActionBarAddLayerMenu) убирается. Вкладка Upscaling СОЗНАТЕЛЬНО не тронута —
# планируется её модернизация под облачную генерацию.
# ----------------------------------------------------------------------------

# Меню «Добавить слой»: убрать пункт «Слой управления», оставить растровый
JS_ADD_LAYER_CONTROL_OLD = (
    'children:[o.jsx(ve,{icon:o.jsx(an,{}),onClick:r,isDisabled:!c,'
    'children:e("controlLayers.controlLayer")}),'
    'o.jsx(ve,{icon:o.jsx(an,{}),onClick:a,children:e("controlLayers.rasterLayer")})]'
)
JS_ADD_LAYER_CONTROL_NEW = (
    'children:[o.jsx(ve,{icon:o.jsx(an,{}),onClick:a,'
    'children:e("controlLayers.rasterLayer")})]'
)


def patch_canvas_control_layer() -> bool:
    """Убирает пункт «Слой управления» (ControlNet) из меню добавления слоёв."""
    targets = [
        f for f in DIST.glob("assets/*.js")
        if "control-layers-add-layer-menu-button" in f.read_text(encoding="utf-8")
    ]
    if len(targets) != 1:
        print(f"ОШИБКА: бандл с меню добавления слоёв найден {len(targets)} раз (ожидался 1)")
        sys.exit(1)
    f = targets[0]
    s = f.read_text(encoding="utf-8")
    if JS_ADD_LAYER_CONTROL_OLD not in s:
        if 'e("controlLayers.controlLayer")' not in s:
            print("Пункт «Слой управления» уже скрыт, пропуск")
            return False
        print("ОШИБКА: не найден фрагмент меню слоёв (частичная правка?)")
        sys.exit(1)
    if s.count(JS_ADD_LAYER_CONTROL_OLD) != 1:
        print(f"ОШИБКА: фрагмент меню слоёв найден {s.count(JS_ADD_LAYER_CONTROL_OLD)} раз (ожидался 1)")
        sys.exit(1)
    s = s.replace(JS_ADD_LAYER_CONTROL_OLD, JS_ADD_LAYER_CONTROL_NEW, 1)
    bak = f.with_suffix(f.suffix + ".imagerouter-bak")
    if not bak.exists():
        shutil.copy2(f, bak)
    f.write_text(s, encoding="utf-8")
    print(f"Пункт «Слой управления» (ControlNet) убран из меню слоёв: {f.name} (бэкап: {bak.name})")
    return True


# ----------------------------------------------------------------------------
# Скрытие кнопок в левой вертикальной рейке (VerticalNavBar):
#   - вкладка «Очередь» (queue) — статус очереди и так виден у кнопки Generate;
#   - колокольчик Notifications — в его поповере «Что нового в DevBIM»
#     (обновления локальной сборки нам не актуальны; тосты остаются);
#   - кнопка Support Videos (обучающие видео Invoke).
# ----------------------------------------------------------------------------

# VerticalNavBar: убрать вкладку queue
JS_RAIL_QUEUE_OLD = (
    ',l&&o.jsx(Ad,{tab:"queue",icon:o.jsx($A,{}),label:e("ui.tabs.queue")})'
)
JS_RAIL_QUEUE_NEW = ''

# VerticalNavBar: убрать кнопки Notifications (Что нового) и Support Videos
JS_RAIL_BUTTONS_OLD = (
    'o.jsx(mt,{}),o.jsx(t5e,{}),o.jsx(r5e,{}),o.jsx(pq,{}),t||o.jsx(JTe,{})'
)
JS_RAIL_BUTTONS_NEW = 'o.jsx(mt,{}),o.jsx(t5e,{}),t||o.jsx(JTe,{})'


def patch_left_rail() -> bool:
    """Прячет кнопки queue / Что нового / Support Videos в левой рейке."""
    targets = [
        f for f in DIST.glob("assets/*.js")
        if 'displayName="VerticalNavBar"' in f.read_text(encoding="utf-8")
    ]
    if len(targets) != 1:
        print(f"ОШИБКА: бандл с VerticalNavBar найден {len(targets)} раз (ожидался 1)")
        sys.exit(1)
    f = targets[0]
    s = f.read_text(encoding="utf-8")
    if JS_RAIL_QUEUE_OLD not in s and JS_RAIL_BUTTONS_OLD not in s:
        if 'ui.tabs.queue' not in s and "o.jsx(r5e,{})" not in s and "o.jsx(pq,{})" not in s:
            print("Кнопки левой рейки уже скрыты, пропуск")
            return False
        print("ОШИБКА: не найдены фрагменты левой рейки (частичная правка?)")
        sys.exit(1)
    for old, new, title in (
        (JS_RAIL_QUEUE_OLD, JS_RAIL_QUEUE_NEW, "вкладка Очередь"),
        (JS_RAIL_BUTTONS_OLD, JS_RAIL_BUTTONS_NEW, "кнопки Что нового / Support Videos"),
    ):
        if s.count(old) != 1:
            print(f"ОШИБКА: фрагмент «{title}» найден {s.count(old)} раз (ожидался 1)")
            sys.exit(1)
        s = s.replace(old, new, 1)
    bak = f.with_suffix(f.suffix + ".imagerouter-bak")
    if not bak.exists():
        shutil.copy2(f, bak)
    f.write_text(s, encoding="utf-8")
    print(f"Кнопки левой рейки скрыты (Очередь, Что нового, Support Videos): {f.name}")
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


# ----------------------------------------------------------------------------
# Админский доступ по паролю (.env: ADMIN_PASSWORD):
#   - вкладка «Модели» убирается из левой рейки;
#   - в меню, в группу «Настройки», добавляется пункт «Менеджер моделей»;
#   - модальное окно пароля и перехват шестерёнки — в dist/devbim-admin.js
#     (подключается патчем index.html ниже).
# ----------------------------------------------------------------------------

# VerticalNavBar: убрать вкладку «Модели» (Менеджер моделей переезжает в меню)
JS_RAIL_MODELS_OLD = (
    ',r&&o.jsx(Ad,{tab:"models",icon:o.jsx(RA,{}),label:e("ui.tabs.models")})'
)
JS_RAIL_MODELS_NEW = ''

# Меню (шестерёнка): после пункта «Настройки» — пункт «Менеджер моделей»
JS_MENU_SETTINGS_OLD = (
    'o.jsx(YTe,{children:o.jsx(ve,{as:"button",icon:o.jsx(nje,{}),'
    'children:e("common.settingsLabel")})})]})'
)
JS_MENU_SETTINGS_NEW = (
    'o.jsx(YTe,{children:o.jsx(ve,{as:"button",icon:o.jsx(nje,{}),'
    'children:e("common.settingsLabel")})}),'
    'o.jsx(ve,{as:"button",icon:o.jsx(RA,{}),'
    'onClick:()=>window.__devbimOpenModels&&window.__devbimOpenModels(),'
    'children:"Менеджер моделей"})]})'
)


def patch_admin_gate() -> bool:
    """Прячет вкладку «Модели» из рейки и добавляет пункт
    «Менеджер моделей» в меню (группа «Настройки»)."""
    targets = [
        f for f in DIST.glob("assets/*.js")
        if 'displayName="VerticalNavBar"' in f.read_text(encoding="utf-8")
    ]
    if len(targets) != 1:
        print(f"ОШИБКА: бандл с VerticalNavBar найден {len(targets)} раз (ожидался 1)")
        sys.exit(1)
    f = targets[0]
    s = f.read_text(encoding="utf-8")
    if "Менеджер моделей" in s and JS_RAIL_MODELS_OLD not in s:
        print("Админский перенос уже настроен (пункт «Менеджер моделей» на месте), пропуск")
        return False
    for old, new, title in (
        (JS_RAIL_MODELS_OLD, JS_RAIL_MODELS_NEW, "вкладка Модели в рейке"),
        (JS_MENU_SETTINGS_OLD, JS_MENU_SETTINGS_NEW, "пункт «Менеджер моделей» в меню"),
    ):
        if s.count(old) != 1:
            print(f"ОШИБКА: фрагмент «{title}» найден {s.count(old)} раз (ожидался 1)")
            sys.exit(1)
        s = s.replace(old, new, 1)
    bak = f.with_suffix(f.suffix + ".imagerouter-bak")
    if not bak.exists():
        shutil.copy2(f, bak)
    f.write_text(s, encoding="utf-8")
    print(f"Менеджер моделей перенесён в меню «Настройки»: {f.name} (бэкап: {bak.name})")
    return True


# ----------------------------------------------------------------------------
# Охрана переключения на вкладку «models»: синглтон навигации (index-бандл)
# при заблокированном доступе вызывает window.__devbimGuardModels() (окно
# пароля) вместо переключения. Заодно выставляет window.__devbimSwitchTab /
# __devbimGetTab для devbim-admin.js.
# ----------------------------------------------------------------------------

JS_NAV_EXPOSE_OLD = 'connectToApp=t=>{this._app=t}'
JS_NAV_EXPOSE_NEW = (
    'connectToApp=t=>{window.__devbimSwitchTab=this.switchToTab.bind(this),'
    'window.__devbimGetTab=()=>this._app?this._app.activeTab.get():null,this._app=t}'
)

JS_NAV_GUARD_HEAD_OLD = 'switchToTab=t=>this._app?'
JS_NAV_GUARD_HEAD_NEW = (
    'switchToTab=t=>("models"!==t||!window.__devbimGuardModels||window.__devbimUnlocked?this._app?'
)
JS_NAV_GUARD_TAIL_OLD = ',!1);_registerPanel='
JS_NAV_GUARD_TAIL_NEW = ',!1):(window.__devbimGuardModels(),!1));_registerPanel='


def patch_tab_guard() -> bool:
    """Гейт на switchToTab('models') + экспорт навигации для devbim-admin.js."""
    targets = [
        f for f in DIST.glob("assets/*.js")
        if "__devbimGuardModels" in f.read_text(encoding="utf-8")
        or JS_NAV_GUARD_HEAD_OLD in f.read_text(encoding="utf-8")
    ]
    if len(targets) > 1:
        print(f"ОШИБКА: бандл с switchToTab найден {len(targets)} раз (ожидался 1)")
        sys.exit(1)
    if not targets:
        print("ОШИБКА: не найден бандл с синглтоном навигации (switchToTab)")
        sys.exit(1)
    f = targets[0]
    s = f.read_text(encoding="utf-8")
    if "__devbimGuardModels" in s:
        print("Охрана вкладки «models» уже установлена, пропуск")
        return False
    for old, new, title in (
        (JS_NAV_EXPOSE_OLD, JS_NAV_EXPOSE_NEW, "connectToApp (экспорт навигации)"),
        (JS_NAV_GUARD_HEAD_OLD, JS_NAV_GUARD_HEAD_NEW, "switchToTab (начало)"),
        (JS_NAV_GUARD_TAIL_OLD, JS_NAV_GUARD_TAIL_NEW, "switchToTab (хвост)"),
    ):
        if s.count(old) != 1:
            print(f"ОШИБКА: фрагмент «{title}» найден {s.count(old)} раз (ожидался 1)")
            sys.exit(1)
        s = s.replace(old, new, 1)
    bak = f.with_suffix(f.suffix + ".imagerouter-bak")
    if not bak.exists():
        shutil.copy2(f, bak)
    f.write_text(s, encoding="utf-8")
    print(f"Охрана вкладки «models» установлена: {f.name} (бэкап: {bak.name})")
    return True


def patch_index_html() -> bool:
    """Подключает /devbim-admin.js (окно пароля) к index.html."""
    s = INDEX_HTML.read_text(encoding="utf-8")
    if "devbim-admin.js" in s:
        print("index.html уже подключает devbim-admin.js, пропуск")
        return False
    tag = '  <script src="/devbim-admin.js" defer></script>\n</head>'
    if "</head>" not in s:
        print("ОШИБКА: в index.html нет </head>")
        sys.exit(1)
    bak = INDEX_HTML.with_suffix(".html.imagerouter-bak")
    if not bak.exists():
        shutil.copy2(INDEX_HTML, bak)
    INDEX_HTML.write_text(s.replace("</head>", tag, 1), encoding="utf-8")
    print(f"index.html подключает devbim-admin.js (бэкап: {bak.name})")
    return True


def main() -> None:
    for p in (SRC / "imagerouter_router.py", SRC / "imagerouter.html", SRC / "devbim_admin.js", DIST, API_APP.parent):
        if not p.exists():
            print("Не найдено:", p)
            sys.exit(1)
    ensure_env_file()
    deploy_files()
    patch_api_app()
    patch_js()
    patch_left_panel()
    patch_canvas_control_layer()
    patch_left_rail()
    patch_generate_button()
    patch_admin_gate()
    patch_tab_guard()
    patch_index_html()
    print("Готово. Перезапустите сервер: ключ и пароль подтянутся из .env.")
    print("Далее: Меню → «Настройки» → пароль → «Менеджер моделей» → вкладка ImageRouter.")


if __name__ == "__main__":
    main()
