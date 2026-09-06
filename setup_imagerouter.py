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
  6. Патчит собранный JS: у кнопки Generate убираются кнопки локальной
     очереди — меню «полоски» (пауза/очистка очереди) и «крестик» (отмена);
     локальная очередь при облачной генерации не используется, полоса
     прогресса сохраняется.
  7. Админский доступ по паролю (.env: ADMIN_PASSWORD):
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

MASK_TOGGLE_SRC = SRC / "devbim_mask_toggle.js"
MASK_TOGGLE_NAME = "devbim-mask-toggle.js"

PE_SRC = SRC / "prompt_enhancer.py"
PE_DST = SP / "invokeai" / "app" / "invocations" / "devbim_prompt_enhancer.py"

# Якорь тот же, что у setup_ifcviewer.py (JS_APPCONTENT_ANCHOR): вставка
# префиксом, якорь сохраняется для IFC-патча при любом порядке запуска.
JS_CANVAS_BRIDGE_ANCHOR = "const cue=u.memo("
JS_CANVAS_BRIDGE = "window.__devbimCanvasBridge={getManager:()=>ru.get()};"

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


def deploy_mask_toggle(dist: Path | None = None) -> bool:
    """Деплой тумблера «Маска / Слой»: копия в dist/ + script в index.html."""
    dist = dist or DIST
    dst = dist / MASK_TOGGLE_NAME
    index = dist / "index.html"
    if not MASK_TOGGLE_SRC.exists():
        print("ОШИБКА: нет источника", MASK_TOGGLE_SRC)
        sys.exit(1)
    if not index.exists():
        print("ОШИБКА: нет index.html в", dist)
        sys.exit(1)
    shutil.copy2(MASK_TOGGLE_SRC, dst)
    s = index.read_text(encoding="utf-8")
    if MASK_TOGGLE_NAME in s:
        print("index.html уже подключает", MASK_TOGGLE_NAME + ", пропуск")
        print("Тумблер развернут:", dst)
        return False
    if "</head>" not in s:
        print("ОШИБКА: в index.html нет </head>")
        sys.exit(1)
    bak = index.with_suffix(".html.masktoggle-bak")
    if not bak.exists():
        shutil.copy2(index, bak)
    tag = f'  <script src="/{MASK_TOGGLE_NAME}" defer></script>\n</head>'
    index.write_text(s.replace("</head>", tag, 1), encoding="utf-8")
    print("index.html подключает", MASK_TOGGLE_NAME + f" (бэкап: {bak.name})")
    print("Тумблер развернут:", dst)
    return True


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
        if JS_ADD_LAYER_CONTROL_NEW in s:
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
# Кнопки локальной очереди у кнопки Generate (ряд QueueControls:
# [InvokeQueueBackButton, Spacer, QueueActionsMenuButton, CancelIconButton]).
# Генерация полностью облачная — локальная очередь всегда пуста, поэтому
# кнопка-«полоски» (меню очереди: пауза/возобновление/очистка) и кнопка-
# «крестик» (отмена текущего элемента очереди) бесполезны и убираются из
# рендера. Сам компонент QueueActionsMenuButton остаётся в бандле (не
# используется), полоса прогресса под кнопкой Generate сохраняется — через
# неё виден прогресс облачной генерации (события invocation_progress).
# ----------------------------------------------------------------------------

# Ряд кнопок QueueControls: убрать меню очереди (cne) и отмену (fne)
JS_QUEUE_BUTTONS_OLD = (
    'children:[o.jsx(pne,{}),o.jsx(mt,{}),o.jsx(cne,{}),o.jsx(fne,{})]'
)
JS_QUEUE_BUTTONS_NEW = 'children:[o.jsx(pne,{}),o.jsx(mt,{})]'


def patch_queue_buttons() -> bool:
    """Убирает кнопки локальной очереди («полоски» и «крестик») справа от Generate."""
    targets = [
        f for f in DIST.glob("assets/*.js")
        if 'displayName="InvokeQueueBackButton"' in f.read_text(encoding="utf-8")
    ]
    if len(targets) != 1:
        print(f"ОШИБКА: бандл с рядом кнопок Generate найден {len(targets)} раз (ожидался 1)")
        sys.exit(1)
    f = targets[0]
    s = f.read_text(encoding="utf-8")
    if JS_QUEUE_BUTTONS_OLD not in s:
        if JS_QUEUE_BUTTONS_NEW in s:
            print("Кнопки очереди у Generate уже скрыты, пропуск")
            return False
        print("ОШИБКА: не найден ряд кнопок Generate (частичная правка?)")
        sys.exit(1)
    if s.count(JS_QUEUE_BUTTONS_OLD) != 1:
        print(f"ОШИБКА: ряд кнопок Generate найден {s.count(JS_QUEUE_BUTTONS_OLD)} раз (ожидался 1)")
        sys.exit(1)
    s = s.replace(JS_QUEUE_BUTTONS_OLD, JS_QUEUE_BUTTONS_NEW, 1)
    bak = f.with_suffix(f.suffix + ".imagerouter-bak")
    if not bak.exists():
        shutil.copy2(f, bak)
    f.write_text(s, encoding="utf-8")
    print(f"Кнопки локальной очереди убраны у Generate: {f.name} (бэкап: {bak.name})")
    return True


# ----------------------------------------------------------------------------
# Prompt Enhancer: улучшение промта через VLM ImageRouter.
#   deploy_prompt_enhancer — модуль инвокаций claude_expand_prompt /
#   claude_analyze_image в пакет (новый файл, автоподхват __init__.py).
#   Три патча App-бандла (все идемпотентны, бэкап *.imagerouter-bak):
#     patch_prompt_enhance_button  — голубая кнопка #38BDF8 в слоте 60px
#                                    справа от жёлтой Generate;
#     patch_expand_graph_refs      — референсы (Reference Images) в граф
#                                    расширения промта (state.canvas.present
#                                    .referenceImages.entities[].ipAdapter.image);
#     patch_expansion_overlay_edit — оверлей результата: статический текст ->
#                                    редактируемый textarea (uncontrolled,
#                                    defaultValue), Replace/Insert читают
#                                    отредактированное значение из DOM.
# ----------------------------------------------------------------------------

def deploy_prompt_enhancer() -> bool:
    """Копирует модуль инвокаций Prompt Enhancer в пакет invokeai."""
    if not PE_SRC.exists():
        print("ОШИБКА: нет источника", PE_SRC)
        sys.exit(1)
    if PE_DST.exists() and PE_DST.read_text(encoding="utf-8") == PE_SRC.read_text(encoding="utf-8"):
        print("Модуль Prompt Enhancer уже развернут, пропуск")
        return False
    PE_DST.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(PE_SRC, PE_DST)
    print("Модуль инвокаций развернут:", PE_DST)
    return True


# Кнопка Prompt Enhance: компонент + вставка в контейнер Generate (слот 60px).
# Je — стор-хук (как у штатной кнопки расширения), ie(ci.$state) — стор
# Prompt Expansion, lb — штатный enqueue-and-wait, KC — иконка-искра.
JS_PE_BTN = (
    'const DevbimPEBtn=u.memo(()=>{const{dispatch:e,getState:t}=Je(),'
    '{isPending:n}=ie(ci.$state),s=u.useCallback(()=>{ci.setPending(),'
    'lb({dispatch:e,getState:t})},[e,t]);return o.jsx($e,{label:"Prompt Enhance",'
    'placement:"top",hasArrow:!0,children:o.jsx(pe,{"aria-label":"Prompt Enhance",'
    'onClick:s,isDisabled:n,position:"absolute",right:0,top:0,w:"56px",h:"40px",'
    'minW:"56px",px:0,variant:"solid",sx:{background:"#38BDF8",color:"#0B0C0E",'
    '_hover:{background:"#5CC8FA"},_disabled:{background:"#38BDF8",opacity:.5}},'
    'children:o.jsx(KC,{size:16})})})});'
)
JS_PE_PREFIX_OLD = 'const m7="Generate",pne=u.memo('
JS_PE_TAIL_OLD = 'o.jsx(mt,{})]})})]})});pne.displayName="InvokeQueueBackButton"'
JS_PE_TAIL_NEW = 'o.jsx(mt,{})]})}),o.jsx(DevbimPEBtn,{})]})});pne.displayName="InvokeQueueBackButton"'


def patch_prompt_enhance_button(bundle: Path | None = None) -> bool:
    """Голубая кнопка «Prompt Enhance» справа от жёлтой Generate."""
    if bundle is None:
        targets = [
            f for f in DIST.glob("assets/*.js")
            if 'displayName="InvokeQueueBackButton"' in f.read_text(encoding="utf-8")
        ]
        if len(targets) != 1:
            print(f"ОШИБКА: бандл с кнопкой Generate найден {len(targets)} раз (ожидался 1)")
            sys.exit(1)
        bundle = targets[0]
    s = bundle.read_text(encoding="utf-8")
    if "DevbimPEBtn" in s:
        print("Кнопка Prompt Enhance уже установлена, пропуск")
        return False
    if s.count(JS_PE_PREFIX_OLD) != 1 or s.count(JS_PE_TAIL_OLD) != 1:
        print("ОШИБКА: якоря кнопки Generate найдены не по одному разу — структура изменилась")
        sys.exit(1)
    s = s.replace(JS_PE_PREFIX_OLD, JS_PE_BTN + JS_PE_PREFIX_OLD, 1)
    s = s.replace(JS_PE_TAIL_OLD, JS_PE_TAIL_NEW, 1)
    bak = bundle.with_suffix(bundle.suffix + ".imagerouter-bak")
    if not bak.exists():
        shutil.copy2(bundle, bak)
    bundle.write_text(s, encoding="utf-8")
    print(f"Кнопка Prompt Enhance установлена у Generate: {bundle.name} (бэкап: {bak.name})")
    return True


# Референсы в граф расширения промта: глобальные Reference Images канваса
# (redux-undo: живое состояние в .present; грабля тумблера, п.16 HANDOFF).
JS_REFS_OLD = (
    'const i=V2(e),a=new Et(Q("claude-expand-prompt-graph")),r=a.addNode('
    '{type:"claude_expand_prompt",id:Q("claude_expand_prompt"),'
    'model_architecture:s,prompt:i});return{graph:a,outputNodeId:r.id}'
)
JS_REFS_COLLECTOR = (
    'images:(function(st){var acc=[];try{var c=st&&st.canvas?st.canvas:null;'
    'c=c&&c.present?c.present:c;var ents=(c&&c.referenceImages&&'
    'c.referenceImages.entities)||[];ents.forEach(function(x){'
    'if(x&&x.isEnabled!==false&&x.ipAdapter&&x.ipAdapter.image&&'
    'x.ipAdapter.image.image_name)acc.push({image_name:x.ipAdapter.image.image_name})})'
    '}catch(err){acc=[]}return acc})(e)'
)
JS_REFS_NEW = JS_REFS_OLD.replace("prompt:i});", "prompt:i," + JS_REFS_COLLECTOR + "});")


def patch_expand_graph_refs(bundle: Path | None = None) -> bool:
    """Прикладывает Reference Images к графу улучшения промта."""
    if bundle is None:
        targets = [
            f for f in DIST.glob("assets/*.js")
            if 'displayName="TabContent"' in f.read_text(encoding="utf-8")
        ]
        if len(targets) != 1:
            print(f"ОШИБКА: бандл с рядом кнопок Generate найден {len(targets)} раз (ожидался 1)")
            sys.exit(1)
        bundle = targets[0]
    s = bundle.read_text(encoding="utf-8")
    if JS_REFS_COLLECTOR in s:
        print("Референсы в графе расширения уже подключены, пропуск")
        return False
    if s.count(JS_REFS_OLD) != 1:
        print(f"ОШИБКА: фрагмент yke найден {s.count(JS_REFS_OLD)} раз (ожидался 1)")
        sys.exit(1)
    s = s.replace(JS_REFS_OLD, JS_REFS_NEW, 1)
    bak = bundle.with_suffix(bundle.suffix + ".imagerouter-bak")
    if not bak.exists():
        shutil.copy2(bundle, bak)
    bundle.write_text(s, encoding="utf-8")
    print(f"Референсы подключены к улучшению промта: {bundle.name} (бэкап: {bak.name})")
    return True


# Оверлей результата: редактируемый textarea вместо статического текста.
# Ns — chakra Textarea (та же, что у промпт-бокса). Uncontrolled defaultValue:
# React не перезаписывает правки пользователя; Replace/Insert читают значение
# из DOM (querySelector по data-devbim-enhanced).
JS_OVERLAY_ANCHOR_START = 'W$e=({expandedText:e})=>{'
JS_OVERLAY_ANCHOR_END = ']})]})},Lne=u.memo('
JS_OVERLAY_NEW = (
    'W$e=({expandedText:e})=>{const t=K(),n=T(V2),'
    's=u.useCallback(()=>{const el=document.querySelector("textarea[data-devbim-enhanced]");'
    't(nb(el?el.value:e)),ci.reset()},[t,e]),'
    'i=u.useCallback(()=>{const el=document.querySelector("textarea[data-devbim-enhanced]"),'
    'v2=el?el.value:e,r=n,l=r?`${r}\\n${v2}`:v2;t(nb(l)),ci.reset()},[t,e,n]),'
    'a=u.useCallback(()=>{ci.reset()},[]);'
    'return o.jsxs(E,{pos:"absolute",inset:0,bg:"base.800",backdropFilter:"blur(8px)",'
    'zIndex:10,direction:"column",children:['
    'o.jsx(E,{flex:1,p:2,borderRadius:"md",overflowY:"auto",minH:0,children:'
    'o.jsx(Ns,{"data-devbim-enhanced":!0,defaultValue:e,variant:"darkFilled",'
    'fontSize:"sm",w:"full",resize:"none",placeholder:"Enhanced prompt",'
    'sx:{"::placeholder":{color:"rgba(255,255,255,.4)"}}})}),'
    'o.jsxs(E,{gap:2,p:1,justifyContent:"flex-end",pos:"absolute",bottom:0,right:0,'
    'flexDirection:"column",children:[o.jsxs(Fn,{orientation:"vertical",children:['
    'o.jsx($e,{label:"Replace",placement:"right",children:o.jsx(re,{onClick:s,'
    'icon:o.jsx(Wp,{}),colorScheme:"invokeGreen",size:"xs","aria-label":"Replace"})}),'
    'o.jsx($e,{label:"Insert",placement:"right",children:o.jsx(re,{onClick:i,'
    'icon:o.jsx(an,{}),colorScheme:"invokeBlue",size:"xs","aria-label":"Insert"})})]}),'
    'o.jsx($e,{label:"Discard",placement:"right",children:o.jsx(re,{onClick:a,'
    'icon:o.jsx(Yt,{}),colorScheme:"invokeRed",size:"xs","aria-label":"Discard"})})'
    ']})]})},Lne=u.memo('
)


def patch_expansion_overlay_edit(bundle: Path | None = None) -> bool:
    """Оверлей результата расширения промта становится редактируемым."""
    if bundle is None:
        targets = [
            f for f in DIST.glob("assets/*.js")
            if 'displayName="TabContent"' in f.read_text(encoding="utf-8")
        ]
        if len(targets) != 1:
            print(f"ОШИБКА: App-бандл (TabContent) найден {len(targets)} раз (ожидался 1)")
            sys.exit(1)
        bundle = targets[0]
    s = bundle.read_text(encoding="utf-8")
    if "data-devbim-enhanced" in s:
        print("Оверлей расширения уже редактируемый, пропуск")
        return False
    if s.count(JS_OVERLAY_ANCHOR_START) != 1 or s.count(JS_OVERLAY_ANCHOR_END) != 1:
        print("ОШИБКА: якоря оверлея W$e найдены не по одному разу — структура изменилась")
        sys.exit(1)
    i = s.index(JS_OVERLAY_ANCHOR_START)
    j = s.index(JS_OVERLAY_ANCHOR_END, i) + len(JS_OVERLAY_ANCHOR_END)
    s = s[:i] + JS_OVERLAY_NEW + s[j:]
    bak = bundle.with_suffix(bundle.suffix + ".imagerouter-bak")
    if not bak.exists():
        shutil.copy2(bundle, bak)
    bundle.write_text(s, encoding="utf-8")
    print(f"Оверлей расширения промта редактируемый: {bundle.name} (бэкап: {bak.name})")
    return True


def patch_canvas_bridge(bundle: Path | None = None) -> bool:
    """Мост менеджера канваса для тумблера «Маска/Слой» (devbim_mask_toggle.js)."""
    if bundle is None:
        targets = [
            f for f in DIST.glob("assets/*.js")
            if 'displayName="TabContent"' in f.read_text(encoding="utf-8")
        ]
        if len(targets) != 1:
            print(f"ОШИБКА: App-бандл (TabContent) найден {len(targets)} раз (ожидался 1)")
            sys.exit(1)
        bundle = targets[0]
    s = bundle.read_text(encoding="utf-8")
    if "__devbimCanvasBridge" in s:
        print("Мост канваса уже установлен, пропуск")
        return False
    if s.count(JS_CANVAS_BRIDGE_ANCHOR) != 1:
        print(f"ОШИБКА: якорь моста найден {s.count(JS_CANVAS_BRIDGE_ANCHOR)} раз (ожидался 1)")
        sys.exit(1)
    if ",ru=" not in s:
        print("ОШИБКА: в бандле нет ru (стор менеджера) — структура изменилась")
        sys.exit(1)
    bak = bundle.with_suffix(bundle.suffix + ".imagerouter-bak")
    if not bak.exists():
        shutil.copy2(bundle, bak)
    s = s.replace(JS_CANVAS_BRIDGE_ANCHOR, JS_CANVAS_BRIDGE + JS_CANVAS_BRIDGE_ANCHOR, 1)
    bundle.write_text(s, encoding="utf-8")
    print(f"Мост канваса установлен: {bundle.name} (бэкап: {bak.name})")
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
    for p in (SRC / "imagerouter_router.py", SRC / "imagerouter.html", SRC / "devbim_admin.js",
              MASK_TOGGLE_SRC, PE_SRC, DIST, API_APP.parent):
        if not p.exists():
            print("Не найдено:", p)
            sys.exit(1)
    ensure_env_file()
    deploy_files()
    deploy_mask_toggle()
    patch_api_app()
    patch_js()
    patch_left_panel()
    patch_canvas_control_layer()
    patch_queue_buttons()
    patch_canvas_bridge()
    deploy_prompt_enhancer()
    patch_prompt_enhance_button()
    patch_expand_graph_refs()
    patch_expansion_overlay_edit()
    patch_left_rail()
    patch_generate_button()
    patch_admin_gate()
    patch_tab_guard()
    patch_index_html()
    print("Готово. Перезапустите сервер: ключ и пароль подтянутся из .env.")
    print("Далее: Меню → «Настройки» → пароль → «Менеджер моделей» → вкладка ImageRouter.")


if __name__ == "__main__":
    main()
