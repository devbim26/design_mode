# Хэндофф: DevBIM / InvokeAI + интеграция ImageRouter + IFC-вьювер

Дата: 20.08.2026 (вечер). Работа ведётся в двух ветках: `main` (ImageRouter,
админ-гейт — стабильно) и **`feature/ifc-viewer`** (вкладка IFC, эксперимент,
проверена пользователем вживую). Сессия 19.08 (вечер) добавила вкладку IFC
(п. 12); сессии 20.08 — панель «IFC Viewer» на «Холсте» + правки посредника
(п. 13, «эхо» моделей, генерация без маски) и брендинг: водяной знак вьювера
+ баннер над интерфейсом (п. 14).
Подробная пользовательская документация — в `README.md` (разделы
«ImageRouter», «IFC-вьювер» и «Диагностика»); здесь — рабочий контекст для
продолжения разработки.

## Проект в двух словах

Локальная установка InvokeAI 6.2.0 (CPU, порт 9090) с ребрендингом DevBIM
(`rebrand_devbim.py`) и интеграцией облачных моделей ImageRouter
(`setup_imagerouter.py`) и вкладкой IFC-вьювера (`setup_ifcviewer.py`,
только в ветке feature/ifc-viewer). Скрипты правят пакет в
`venv/Lib/site-packages/invokeai/` — после `pip install --force-reinstall
invokeai==6.2.0` их нужно запускать повторно в порядке: ребрендинг →
имагерос → ifcviewer. **Все скрипты запуска системы — в `launch/`** (с
23.09.2026; главный — `launch/start-system-design.bat`, краткий гайд —
`launch/START-HERE.txt`). Запуск сервера в консоли: `launch/start_devbim.bat`,
перезапуск из агентской сессии — `launch/_restart_server.ps1` (WMI,
отсоединённо).

## Что реализовано (сессия от 19.08.2026)

1. **Вкладка ImageRouter в Model Manager** («Добавить модели»): ввод/проверка
   API-ключа, каталог моделей (поиск, «только бесплатные», сортировка, цены),
   генерация с просмотром. Вкладки локальной установки (Launchpad, URL/путь,
   HuggingFace, скан папки, стартовые модели) и очередь установки скрыты
   (замена компонента `InstallModels` в собранном JS).
2. **Модели ImageRouter в выборе модели Canvas/Generate** — инъекция в ответ
   `GET /api/v2/models/` (мидлварь). 138 моделей, 85 с правкой фото
   (пометка «редактирование» в описании). Приложение авто-выбирает первую.
3. **Перехват генерации**: `POST /api/v1/queue/{q}/enqueue_batch` с моделью
   `imagerouter/...` не исполняется локально — обработчик вызывает API,
   сохраняет результат в галерею (`images.create`) и отправляет штатные
   события (`batch_enqueued`, `invocation_complete`,
   `queue_item_status_changed`) — UI обновляется как при обычной генерации.
4. **Редактирование (inpaint/outpaint/img2img)**: если в графе есть исходная
   картинка — запрос в `/v1/openai/images/edits` (multipart: image + mask +
   prompt + model + size). Маска канвертируется в OpenAI-семантику
   (редактируемая зона = прозрачная). Text-to-image модель при правке →
   понятная ошибка 400 со списком подходящих.
5. **Кнопка генерации** переименована «DevBIM» → «Generate» (+ подсказки
   в 6 локалях), т.к. пользователя путало название.
6. **Прокси-роутер** `/api/v1/imagerouter/*`: status/key/credits/models/
   generate. Ключ — `data/imagerouter.json`, в браузер не отдаётся.
7. **Референсные изображения** (Reference Image / IP-ассеты, 19.08 вечер):
   в список моделей добавлена фейковая IP-Adapter модель
   `imagerouter/ip-adapter-reference` (`_ir_ipadapter_fake`, base sdxl,
   format checkpoint) — без неё клиент выбрасывает референс из графа и
   пишет «Модель не выбрана». Референсы извлекаются из узлов `ip_adapter`
   (поле `image` — словарь или список, inline) и уходят в edits-запрос
   multipart-полем `image[]`; промпт дополняется `PROMPT_REFERENCE_NOTE`.
   Если исходника нет, а референсы есть — всё равно edits-эндпоинт.
   Проверено сквозным тестом 19.08 (nano-banana-2, HTTP 200).
   ⚠️ С 06.09 multipart заменён JSON-массивом (п.26): multipart
   доставлял модели только ПЕРВОЕ изображение.
8. **Полоска генерации / статус очереди** (19.08 вечер): при облачной
   генерации UI не показывал прогресс — события `invocation_progress` не
   отправлялись, а пустая реальная очередь очищала прогресс на клиенте
   (подписка `queue.in_progress === 0 → $lastProgressEvent = null`).
   Сделано в `imagerouter_router.py`:
   - реестр `_INFLIGHT` (счётчик выполняемых генераций на queue_id);
   - мидлварь патчит `GET /api/v1/queue/{q}/status`: пока генерация идёт,
     `queue.in_progress/total += N` (общий хелпер `_proxy_json`);
   - при старте шлются `queue_item_status_changed(in_progress)` +
     `invocation_started`; фоновый поток-«тикер» каждые 2 с шлёт
     `invocation_progress` с текстом
     `ImageRouter · модель · i/N · прошедшие секунды` (алерт «Generating»);
   - в конце/ошибке: `completed`/`failed` + останов тикера, декремент
     `_INFLIGHT` ДО отправки статуса (перезапрошенный /status должен быть
     чистым).
   Проверено 19.08 пользователем: строка прогресса видна.
9. **Левая панель без локальных параметров** (19.08, вечер): система работает
   только через API, поэтому из панели Generate/Canvas убраны чисто локальные
   настройки — аккордеоны Refiner и Advanced (VAE/VAE Precision/CFG
   Rescale/Seamless), Compositing (только канвас), Concepts/LoRA-лист и
   «Advanced Options» (Scheduler/Steps/CFG Scale) внутри аккордеона
   Generation. Реализовано функцией `patch_left_panel()` в
   `setup_imagerouter.py`: три замены в собранном JS (ParametersPanelCanvas,
   ParametersPanelGenerate, GenerationSettingsAccordion), идемпотентно,
   бэкап тот же `*.imagerouter-bak`. Осталось: промпт (+Reference Image),
   модель, Aspect/Width/Height (→ `size`), seed. «Advanced Options» внутри
   Image на канвасе (Scale Before Processing / Scaled W/H) оставлен —
   управляет кропом исходника для edits. Вкладка Upscaling не тронута
   (там свои компоненты, см. `Wae`/`Uae` в бандле).
10. **Левая вертикальная рейка без лишних кнопок** (19.08, вечер): в
   VerticalNavBar скрыты вкладка «Очередь» (`Ad tab:"queue"`), колокольчик
   Notifications (`r5e` — в его поповере раздел «Что нового в DevBIM») и
   Support Videos (`pq` = VideosModalButton). Реализовано `patch_left_rail()`
   в `setup_imagerouter.py` (две замены, идемпотентно). Тосты об ошибках
   (в т.ч. от ImageRouter-роутера) всплывают как раньше — они рендерятся
   отдельными регионами уведомлений, не через этот поповер. Статус очереди
   виден у кнопки Generate (счётчик + прогресс). Кнопка «Меню» и индикатор
   соединения оставлены.
11. **`.env` + админский пароль: «Менеджер моделей» за шестерёнкой**
   (19.08, поздний вечер). Секреты — `.env` в корне проекта
   (`IMAGEROUTER_API_KEY`, `ADMIN_PASSWORD`), грузится роутером при старте
   (`_load_env_file`: cwd → INVOKEAI_ROOT → на уровень выше; без перекрытия
   уже заданных переменных). Ключ из env имеет приоритет над
   `data/imagerouter.json` (`_load_key`, в `/status` появился
   `key_source: env|file|null`). Проверка пароля — `POST
   /api/v1/imagerouter/admin-auth` (hmac.compare_digest, 401 + пауза 0.3 с;
   `GET` того же пути — `{"protected":bool}`). UI: вкладка «Модели» убрана
   из рейки (`patch_admin_gate`, App-бандл); в меню в группу «Настройки»
   добавлен пункт «Менеджер моделей» (onClick → `window.__devbimOpenModels`);
   `patch_tab_guard` (index-бандл) оборачивает синглтон навигации:
   `connectToApp` экспортирует `window.__devbimSwitchTab/__devbimGetTab`,
   `switchToTab("models")` при незаблокированной сессии вызывает
   `window.__devbimGuardModels()` и НЕ переключает вкладку — гейтит все
   обходные пути (кнопка «Manage Models» в ModelPicker, хоткеи, тосты).
   Окно пароля — `imagerouter/devbim_admin.js` → `dist/devbim-admin.js`
   (подключён в `index.html`, `patch_index_html`): перехват клика по
   шестерёнке «Настройки» в capture-фазе (текст пункта сравнивается со
   значениями `common.settingsLabel` всех 19 локалей!), окно глотает
   mousedown/pointerdown (меню под ним не закрывается — после верного
   пароля пункт «нажимается» повторно программно). Разблокировка — до
   перезагрузки страницы; восстановленная после F5 вкладка «models»
   сбрасывается на generate (поллинг `__devbimGetTab`).
   ГРАБЛЯ: при правке хвоста `switchToTab` в index-бандле легко ошибиться
   со скобками (одна лишняя `)` ломала ВЕСЬ бандл — «Unexpected token»,
   белый экран). Проверка после патча обязательна:
   `node -e "import('file:///.../index-*.js').catch(e=>console.log(e.message))"`
   — допустима только рантайм-ошибка (document is not defined), не SyntaxError.
12. **Вкладка «IFC» — 3D-просмотр BIM-моделей** (19.08, ветка
   `feature/ifc-viewer`, эксперимент): кнопка в левой рейке после
   Workflows, панель — iframe `/ifcviewer.html`. Разбор IFC в браузере
   (@thatopen/components 3.4.8 + fragments 3.4.7 + three 0.182.0 +
   web-ifc 0.0.77; ассеты `ifc/assets/` → `dist/ifc/`; воркер разбора
   кладём локально — по умолчанию библиотека тянет его с unpkg.com).
   Дерево структуры (getSpatialStructure), клик-выбор (worker-raycast),
   свойства с psets (getItemsData), скрыть/изолировать (Hider), секущие
   плоскости (Clipper). Сервер: `ifc_router.py` (`/api/v1/ifc/list|upload|
   file/{name}` DELETE, хранение `data/ifc/`, лимит 500 МБ). Установка —
   `setup_ifcviewer.py` (идемпотентный, `*.ifcviewer-bak`). ГРАБЛИ:
   `fragments.raycast` ждёт мышь в ПИКСЕЛЯХ страницы (не NDC — screenToCast
   сам вычитает rect); в 3.x в сцену добавляется `model.object` (не сама
   модель) + `model.useCamera(cam)` + `fragments.core.update(true)`;
   `Worlds` создаётся `new Worlds(components)`, а не `components.worlds`;
   `ifc` добавлен в zod-enum activeTab (index-бандл
   `ct([...,"queue"])` → `+ "ifc"`), иначе перезагрузка со вкладкой IFC
   сбрасывает настройки UI. Идемпотентность патча App-бандла проверяется
   по сигнатуре `e==="ifc"&&o.jsx(IFE,{})` (первая версия проверяла
   неправильно и дублировала вкладку). Порядок скриптов после
   force-reinstall: rebrand → imagerouter → ifcviewer. `_ir_server_hidden.bat`
   теперь ставит PYTHONUTF8=1 (как start_devbim.bat) — без этого сервер,
   запущенный через WMI, падал на конфиге с кириллицей; перезапуск
   сервера — `_restart_server.ps1`. Отладка вьювера: в iframe доступен
   `window.__ifc` (модель, выбор, raycast, clipper). Подробности — README,
   раздел «IFC-вьювер».
13. **Панель «IFC Viewer» на вкладке «Холст» + снимок модели в генерацию**
   (20.08, ветка `feature/ifc-viewer`). В главной dockview-области холста
   рядом с «Image Viewer» — четвёртая панель «IFC Viewer»: тот же
   `/ifcviewer.html?embed=1` (CSS-режим `body.embed`: без шапки/дерева/
   свойств/фута; остаётся вьюпорт + плавающий тулбар + snapbar с селектором
   моделей и кнопками «📸 На холст» / «✨ Сгенерировать»). Поток: форс-рендер
   `world.renderer.three.render(...)` → `toDataURL`-канвас на белом фоне,
   стороны выравниваются кратно 64 (128..2048, требование ImageRouter,
   белые поля) → multipart `POST /api/v1/images/upload` (НЕ `POST /api/v1/
   images/` — в 6.2 это JSON «create upload entry» с width/height!) →
   ImageDTO → мост `window.__devbimIfc.toCanvas(dto, generate)` (патч
   App-бандла): `Fe.focusPanel("canvas",On)` + `_c` (sentImageToCanvas,
   raster_layer, подложка) + при generate — `QCe` (enqueue холста, тот же,
   что кнопка Generate). Синхронизация модели: localStorage
   `devbim:ifc:lastModel` пишется при загрузке модели с сервера (в обоих
   режимах), embed-панель при старте автозагружает её и слушает `storage`
   (живая синхронизация вкладка IFC → панель; односторонняя, локальные
   файлы с диска не синхронизируются). ГРАБЛИ: (а) dockview восстанавливает
   сохранённый layout из storage (`fromJSON`) — колбэк дефолтного layout НЕ
   вызывается, поэтому панель добавляет хелпер `IFCE` в onReady goe
   (после регистрации), добавление само сохраняется через
   onDidLayoutChange; (б) focusRegion панели — только "viewer" (общий с
   Image Viewer): белый список регионов зашит в бандле (q2e), посторонний
   регион роняет рендер (useFocusRegion читает K2e["$"+region]); (в)
   tabComponent — только `t$` (карта QUe вкладки canvas знает launchpad/
   viewer/workspace, посторонний id роняет addPanel с «Only React.memo...
   accepted as components»); (г) менеджер холста читать `ru.get()`, НЕ
   `$p()` — `$p=()=>ie(ru)` это ХУК useSyncExternalStore, вызов вне
   компонента даёт Minified React error #321; (д) панель в dockview
   демонтируется, когда неактивна — iframe теряет состояние (модель
   перезагружается авто, камера сбрасывается). Плюс фикс в
   `imagerouter_router.py`: зона правки (кроп по содержимому+8px)
   выравнивается до сетки 64 — иначе композит со снимком 832px внутри
   bbox 1024px давал кроп 840px и внешний API отвечал 422 «width must be
   multiples of 64». Проверено вживую 20.08: панель, автозагрузка,
   снимок-подложка, генерация через ImageRouter (результат в галерее,
   скриншоты `docs/ifcviewer-canvas-*.png`). Отладка: в iframe
   `window.__ifc.capture()` (dataURL), в приложении
   `window.__devbimIfc` / `window.__devbimIfcCtx` (dispatch/getState).
   Ещё грабля (20.08, вторая половина дня): модели без родной правки
   (пример — onomaai/illustrious-xl: в каталоге заявлен вход-картинка, но
   edits-эндпоинт возвращает ВХОД без изменений, растянутый под size; две
   «генерации» побайтово совпадают) — в посредник добавлен детектор эха
   `_is_echo` (средняя пиксельная разница вход/выход после нормализации
   размера ≤ 3.0; реальные правки дают 100+): вместо фейкового результата
   клиент получает 422 с рекомендацией выбрать модель правки
   (google/nano-banana:free, openai/gpt-image-2:free, qwen/qwen-image,
   black-forest-labs/flux-kontext-dev). Проверено вживую: nano-banana
   делает фотореалистичную правку снимка IFC «на ура»; у :free-моделей
   лимит 3 запроса/сутки. И ещё одна грабля там же (20.08, вечер):
   ГЕНЕРАЦИЯ БЕЗ МАСКИ возвращала исходник — зона правки считалась по
   содержимому+маске, маски не было, и _apply_edit_mask выбрасывала
   результат модели. Теперь при ПУСТОЙ маске (слоя нет или выделение
   пустое) правится картинка ЦЕЛИКОМ: прозрачные поля холста заливаются
   белым с паддингом до сетки 64 (модель дорисовывает окружение по
   промпту), вклейка по маске не делается. Проверено вживую с
   nano-banana-pro: без маски — фотореализм + окружение; с нарисованной
   маской — штатная локальная правка. UI-грабля: кнопка Generate холста
   блокируется, если на холсте есть слой «Региональная точность» без
   промпта (появляется warning у слоя) — удалить слой или ввести промпт.
   Кисть «Маски перерисовки» работает штатно (проверено попиксельно).
   «На холст» = «Редактировать» (20.08, поздний вечер): мост
   `window.__devbimIfc.toCanvas` приведён к поведению кнопки Edit
   («Редактировать») из Image Viewer (хук Ize в App-бандле):
   `withInpaintMask:!0` (вместо `!1`) — sentImageToCanvas вместе со
   снимком создаёт ВЫДЕЛЕННЫЙ слой «Маска перерисовки», после передачи
   включается кисть `manager.tool.$tool.set("brush")` — рисование по слою
   даёт штрихованную (наклонные полоски) маску; менеджер ждётся через
   `ru.get()` с тем же ретраем 20×100 мс (кисть ставится и в режиме
   «Сгенерировать» — не мешает: при ПУСТОЙ маске посредник правит весь
   кадр). Миграция уже патченных бандлов — в `setup_ifcviewer.py`:
   `JS_BRIDGE_V1` → `JS_BRIDGE_V2` (автозамена при повторном запуске,
   идемпотентно). Подсказка в тосте iframe обновлена («…кистью выделите
   „Маску перерисовки“»).

14. **Брендинг: водяной знак вьювера + баннер над интерфейсом** (20.08,
   вечер). (а) Водяной знак: SimpleRenderer движка @thatopen по умолчанию
   рисует свой лого «That Open Company» (div `[data-thatopen-logo]`,
   левый нижний угол вьюпорта) — отключено ШТАТНЫМ свойством
   `world.renderer.showLogo = false` (не патчем бандла!), на его месте
   собственный знак «DevBIM — Design» (SVG-куб + текст, «BIM» акцентом
   #38BDF8, pointer-events:none, виден и в embed-режиме). Всё — в
   `ifcviewer.html` (CSS `.devbim-logo` + вставка после создания
   рендерера), страница деплоится `setup_ifcviewer.py` как есть.
   ГРАБЛЯ (flex): «Dev» и «BIM» в разных flex-элементах раздвигались
   `gap`-ом контейнера (выглядело как «Dev BIM») — слово целиком в одном
   span. (б) Баннер над ВСЕМ интерфейсом: `devbim_banner.js` (деплой —
   новая `deploy_banner()` в `rebrand_devbim.py`: копия в
   `dist/devbim-banner.js` + `<script defer>` в `index.html`, бэкап
   `index.html.banner-bak`, идемпотентно). Тёмная полоса 44px перед
   `#root`: кликабельный логотип → страница регистрации (ЗАГЛУШКА
   `REG_URL = https://devbim.com/register`, `target=_blank`) + слоган
   справа («Создавай реалистичные AI-рендеры интерьеров и фасадов зданий
   с высочайшей точностью…»). Язык слогана следует за языком интерфейса:
   опрос раз в 1 с IndexedDB `invoke` → `invoke-store` → ключ
   `@@invokeai-system`, поле `language` (это redux-remember: префикс
   ключей `@@invokeai-`, сериализация — обычный JSON.stringify,
   persistDenylist среза system пуст, так что язык персистится; RU/EN,
   остальные → EN). ГРАБЛЯ (высота): приложение — `#invoke-app-wrapper`
   с inline `height:100dvh`, баннер в потоке выше `#root` обрезал бы низ
   (html/body/#root overflow:hidden) — в CSS баннера `#root` и
   `#invoke-app-wrapper` переведены на `calc(100dvh - 44px)` (для
   wrapper — `!important`, чтобы перебить inline-стиль chakra).
   Правки регенерируют раздачу перезапуском `rebrand_devbim.py`
   (баннер) / `setup_ifcviewer.py` (вьювер) без пересборки бандлов.
15. **Control Layer (ControlNet) убран из меню слоёв** (05.09). Генерация
   полностью облачная (ImageRouter / nano-banana), ControlNet-моделей нет
   и сервер их не поднимет — пункт «Слой управления» в меню «+» панели
   Control Layers (компонент `EntityListGlobalActionBarAddLayerMenu`,
   App-бандл) удалялся из рендера: `patch_canvas_control_layer()` в
   `setup_imagerouter.py` (замена убирает `ve`-пункт с
   `controlLayers.controlLayer`, оставляет raster layer; идемпотентно,
   бэкап тот же `*.imagerouter-bak`). Существующие control-слои в
   сохранённых канвасах продолжают отображаться (удалить вручную, если
   попадутся). Вкладка Upscaling СОЗНАТЕЛЬНО не тронута — планируется
   модернизация под облачную генерацию. Проверка после патча: node-import
   App-бандла — только `document is not defined`.

16. **Тумблер «Mask / Layer» на холсте** (05.09, вечер). Пилюля над нижней
    панелью холста: подсвечивает слой, которым рисует кисть (Mask =
    inpaint_mask, полосатая кисть; Layer = raster_layer, цвет), и переключает
    его одним кликом. Реализация: мост в App-бандле
    `window.__devbimCanvasBridge={getManager:()=>ru.get()}` (вставка перед
    якорем `const cue=u.memo(` — тот же якорь, что у IFC-патча; вставка
    префиксом, якорь сохраняется) + виджет `imagerouter/devbim_mask_toggle.js`
    → `dist/devbim-mask-toggle.js` + script в index.html. Всё — в
    `setup_imagerouter.py`: `patch_canvas_bridge()` (бандл ищется по
    `displayName="TabContent"`), `deploy_mask_toggle()` (бэкап
    `index.html.masktoggle-bak`). Виджет: тик 500 мс ждёт мост и
    `__devbimGetTab()`, показывается только на вкладке canvas И когда в
    dockview активна сама панель холста (`document.querySelector(
    '.konvajs-content')` — Launchpad/Image Viewer/IFC Viewer демонтируют
    рабочую область холста; текст вкладок не годится — локализация);
    подсветка —
    через `store.subscribe` (store = `manager.stateApi.store`), состояние
    `state.canvas.selectedEntityIdentifier.type`; клик: слой есть →
    `dispatch({type:"canvas/entitySelected",payload:{entityIdentifier:{id,type}}})`
    (самый свежий = последний в `entities`), нет →
    `stateApi.addInpaintMask({isSelected:true})` / `addRasterLayer`. Тесты:
    `tests/test_mask_toggle.py`. ГРАБЛЯ (05.09, вечер): canvas-слайс обёрнут
    в redux-undo (`[Ah.name]:x7(Ah.reducer,...)`, x7 = undoable) — живое
    состояние в `state.canvas.PRESENT`, а не в `state.canvas`; первый вариант
    виджета читал `.canvas.inpaintMasks` → undefined → клик умирал молча и
    подсветка не работала. Хелпер `canvasState(store)` в виджете разворачивает.
    Подписи кнопок — базовый английский («Mask»/«Layer»); русская адаптация
    (как у баннера, по языку интерфейса) — отдельная задача.
    ГРАБЛЯ (исправлено заодно): проверка
    идемпотентности `patch_canvas_control_layer` (п. 15) искала
    `e("controlLayers.controlLayer")` — эта строка живёт и в других
    компонентах, из-за чего повторный запуск setup падал с «не найден
    фрагмент»; теперь проверка по NEW-фрагменту, как у остальных патчей.
    Правка вида/позиции — правкой `imagerouter/devbim_mask_toggle.js` +
    повторный `setup_imagerouter.py` (как баннер). Откат: `*.imagerouter-bak`,
    `index.html.masktoggle-bak`, удалить `dist/devbim-mask-toggle.js`.
19. **Профессиональные style-пресеты** (промты по умолчанию, сессия от
    05.09.2026): стоковый набор InvokeAI заменён десятью пресетами под
    альбомы проектной документации — Facades (Neutral Daylight / Golden
    Hour / Blue Hour / Frontal — Album Sheet), Interiors (Daylight /
    Evening Light / Public Space), Master Plan (Aerial Top-Down / Bird's
    Eye 45° / Orthographic — Album Sheet). НАЗВАНИЯ на английском по
    решению пользователя (05.09, вечер); русская адаптация интерфейса
    запланирована позже — тогда переименовать PRESETS в
    `setup_style_presets.py` + переименовать PNG в `style_preset_images/`
    и перезапустить setup (устаревшие PNG из пакета он вычищает сам).
    ГРАБЛЯ: пресеты `type='default'` при каждом старте сервера
    пересеиваются из
    `venv/.../style_preset_records/default_style_presets.json` — править
    надо seed-файл (+ живая БД), чем и занимается идемпотентный
    `setup_style_presets.py` (откат: `--restore`, бэкап `.orig` рядом).
    Вторая грабля: InvokeAI читает seed-файл `open()` без encoding —
    файл обязан быть ASCII (`ensure_ascii=True`), иначе кириллица названий
    валит старт сервера на cp1251 вне PYTHONUTF8=1. Живая БД
    синхронизируется скриптом на лету (WAL, busy_timeout), серверный
    сервис пресетов читает таблицу на каждый запрос — перезапуск не нужен,
    в UI достаточно F5 (RTK-кэш вкладки живёт до перезагрузки страницы —
    «в списке английские стоковые названия» = просто несвежая вкладка).
    Тест: `tests/test_style_presets.py`.
    Превью (маленькие PNG 256 px): для default-пресетов InvokeAI ищет
    картинку ПО ИМЕНИ пресета в
    `.../style_preset_images/default_style_preset_images/{name}.png`
    (не по id в data/!). ГРАБЛЯ: имя пресета обязано быть корректным
    именем файла Windows — название со слэшем «(3/4)» молча ломало
    сохранение превью; тест теперь ловит такие имена. Генерация превью:
    `make_style_previews.py` (демо-сюжет подставляется вместо {prompt},
    модель Tongyi-MAI/Z-Image-Turbo ~0.0016 кредита/шт; :free-модели
    непригодны — 3 запроса/сутки исчерпываются сразу, проверено 05.09).
    Источник превью — `style_preset_images/` (в git), деплой в venv —
    setup-скриптом. Скриншот UI: `docs/style-presets-ui-en.png`.
20. **IFC-снапбар как в PDF + альфа-канал вместо белого фона** (05.09,
    вечер, по запросу пользователя). (а) Кнопки embed-панели IFC на
    «Холсте»: «✨ Сгенерировать» заменена на «💾 To Assets» — блок стал
    как в PDF-вьювере: «📸 To Canvas» (подложка + слой «Маска
    перерисовки» + кисть, генерация — штатной кнопкой Generate) и
    «💾 To Assets» (`image_category=user` → вкладка «Assets» галереи,
    мост НЕ нужен). Язык embed-панели IFC переведён на английский
    (кнопки/селектор/тосты), как у PDF (решение 05.09). Мост
    `__devbimIfc.toCanvas(dto, generate)` не менялся — параметр
    generate больше никем не вызывается, но работает. (б) Снимок IFC —
    на ПРОЗРАЧНОМ фоне: SimpleRenderer у @thatopen создаёт WebGL с
    `alpha:!0`, а сцена уже с `background=null` — из renderSnapshot()
    просто убрана белая fillRect; стороны по-прежнему кратны 64
    (128..2048), поля вокруг вида прозрачные. Проверено попиксельно:
    91% пикселей alpha=0, здание непрозрачно, PNG в галерее RGBA.
    (в) Посредник (`imagerouter_router.py`, пустая маска): раньше
    прозрачные поля холста заливались БЕЛЫМ (решение 20.08) — теперь
    подложка `Image.new("RGBA", ..., (0,0,0,0))`: модель получает PNG
    с альфа-каналом (здание без фона, окружение дорисовывает сама по
    промпту). Непрозрачные исходники (фото, PDF-фрагменты) не
    изменились — у них прозрачности нет. Путь С маской альфу и так
    сохранял (кроп без заливки). Деплой: `setup_imagerouter.py` +
    `setup_ifcviewer.py` + рестарт. Заодно починена идемпотентность
    `setup_ifcviewer.py` (patch_index_bundle): проверка «уже
    пропатчено» искала точный NEW-фрагмент enum, но pdf-патч дописал
    `"pdf"` ПОСЛЕ `"ifc"` — теперь regex по наличию "ifc" в актуальном
    enum (иначе повторный запуск после setup_pdfviewer падал
    «бандл найден 0 раз»; файлы при этом успевали развернуться).

## Ключевые технические детали (грабли, на которые уже наступили)

- **URL фронтенд строит из openapi operationId** (не литералы в JS).
  Важные пути: `GET /api/v2/models/` (список моделей), `POST /api/v1/queue/
  {queue_id}/enqueue_batch` (тело: `{"batch": {...}, "prepend": bool}`).
- **Фейковые конфиги моделей** обязаны иметь непустой `hash` (zod-схема
  `min(1)` на клиенте — иначе «Failed to parse main model» и модель не
  выбирается). База `sdxl` — чтобы клиент собрал граф без T5/CLIP.
- **Граф канваса**: режим в `core_metadata.generation_mode` с префиксом базы
  (`sdxl_inpaint`, `flux_img2img`) — нормализуется `split("_")[-1]`.
  `positive_prompt` в core_metadata бывает пустым — промпт берётся также из
  узлов и из `batch.data` (`node_path` содержит `positive_prompt`).
  Исходник/маска — узел `create_gradient_mask` (поля `image`/`mask`,
  словари `{image_name}`); маска хранится как обычная картинка.
- **Маска в графе 6.2** (грабля 19.08, вторая половина дня): маска подключается
  к `create_gradient_mask.mask` РЁБРОМ от `mask_combine` (растр слоя
  Inpaint Mask лежит в его `mask1`) — inline-поля `mask` в графе нет,
  извлекает `_resolve_edge_image`. Растр слоя-маски непрозрачный, выделение
  ЧЁРНОЕ на белом (`create_gradient_mask` ждёт 0 = править) — поэтому
  `_mask_edit_alpha` для непрозрачного растра берёт L БЕЗ инверсии.
- **Шлюз ImageRouter не принимает параметр `mask` НИ У ОДНОЙ модели**
  (проверено 19.08 на gpt-image-2, qwen-image-2, nano-banana: HTTP 200 +
  `{"error":{"message":"Mask editing is not supported..."}}`). Поэтому:
  первая попытка с `mask` → при такой ошибке автоповтор с подсветкой зоны
  пурпурной заливкой+рамкой в самой картинке (`_draw_mask_marker`) и
  пояснением в промпте (`PROMPT_MARKER_NOTE`).
- **Локальность правки гарантируется пост-обработкой** (`_apply_edit_mask`):
  запрос кадрируется по содержимому+маске (+8px), ответ модели вклеивается
  только в зону маски с растушёвкой 4px — вне маски пиксели не меняются
  вовсе (проверено 19.08: diff = 0 вне маски). Ошибки апстрима с HTTP 200
  разбирает `_api_error_message`.
- **queue_id из пути** = `path.split("/")[4]` (не [3]!). События сокетов
  шлём через `ApiDependencies.invoker.services.events.dispatch(...)` —
  работает из любого потока, комната = queue_id («default»).
- **API сервисов**: `images.get_pil_image(name)` (не get_pil),
  `ImageCategory.GENERAL` (не IMAGE), `ResourceOrigin.INTERNAL`.
- **Формат ошибок enqueue_batch** (грабля 19.08): тост «Не удалось
  поставить пакет в очередь» показывает текст только для 422-ответов вида
  `detail=[{loc,msg,type}]` (zod-схема в бандле проверяет статус === 422);
  `{"detail": "строка"}` с любым статусом → «Неизвестная ошибка».
  Поэтому мидлварь отдаёт ошибки через `_ir_error_body()` (всегда 422).
- **Мидлварь** (`ImageRouterCanvasMiddleware`, чистый ASGI) регистрируется
  в `api_app.py` ДО `add_middleware(CORS/GZip)` — иначе видит gzip-ответ
  и не может дописать модели в JSON.
- **ImageRouter API**: `GET /v3/models` — публичный (без ключа);
  проверка ключа `POST /v1/auth/test`; баланс `GET /v1/credits`;
  генерация/правка `POST /v1/openai/images/{generations,edits}`
  (правка — multipart `image`, `mask`, `image[]`).

## Текущее состояние

- Сервер запущен на `http://127.0.0.1:9090` отсоединённым процессом через
  WMI (`launch/_ir_server_hidden.bat`, лог — `ir_server.log`). Запущенные из
  агентских сессий фоновые процессы убиваются вместе с сессией —
  используйте WMI/`launch/start_devbim.bat`.
- **`.env` в корне проекта** — источник ключа и админского пароля
  (в git не входит, см. `.gitignore`). Ключ ImageRouter подтягивается при
  старте сервера (`key_source: env`), админский пароль — `ADMIN_PASSWORD`
  (менять в `.env` + перезапуск). При удалении `.env` ключ берётся из
  `data/imagerouter.json`, защита паролем отключается.
- Каталог моделей кэшируется на сервере 10 мин (`_ir_models_cache`).
- Диагностический дамп последнего перехваченного графа:
  `data/_ir_last_graph.json` (удобно для разбора «что ушло»).

## Что НЕ сделано (кандидаты на продолжение)

- `quality` с канваса не используется (только size). Параметры
  steps/cfg/scheduler из UI скрыты (п. 9), но по-прежнему ходят в графе
  со значениями по умолчанию и игнорируются роутером. Селектор quality
  (auto/low/medium/high) требует сборки фронтенда — в собранном бандле
  протащить своё поле в граф нельзя.
- Несколько картинок (runs) генерируются последовательными вызовами —
  параметр `n` у API отсутствует.
- Удаление imagerouter-модели из списка моделей возвращает 400 с пояснением
  (это каталог API, не файлы) — можно сделать «скрытие» с состоянием.
- Генерация синхронная: HTTP-запрос ждёт облако (до ~5 мин таймаута).
  Индикация в UI уже есть (п. 8); полноценная асинхронность — при
  необходимости.
- **IFC → ИИ: скриншот вида и отправка в генерацию — ВЫПОЛНЕНО 20.08**
  (см. п. 13). Реализовано иначе, чем предполагал исходный план ниже:
  отдельный эндпоинт не понадобился — снимок заливается стандартным
  `POST /api/v1/images/upload`, кладётся на холст подложкой
  (sentImageToCanvas) и генерация идёт штатным конвейером холста через
  перехват enqueue_batch. Исходный план (для истории):
  1) Скриншот: канвас вьювера — WebGL без preserveDrawingBuffer, поэтому
     `canvas.toDataURL()` ПОСЛЕ форс-рендера в том же кадре:
     `world.renderer.three.render(scene, camera)` затем toDataURL
     (обе ссылки есть через `window.__ifc` в iframe). Альтернатива —
     включить preserveDrawingBuffer в параметрах SimpleRenderer при
     создании (страница наша, можно свободно). Ещё вариант —
     `components.renderer`… проще всего форс-рендер. Не забыть про
     devicePixelRatio (скриншот в полном разрешении канваса).
  2) Куда отправлять: готового эндпоинта «правка картинки с диска» НЕТ —
     `POST /api/v1/imagerouter/generate` это generations (только
     промпт), а edits-логика (`_handle_canvas_generation`,
     `/v1/openai/images/edits`) живёт внутри перехвата enqueue_batch и
     ждёт граф канваса. Нужен новый эндпоинт в imagerouter_router.py,
     напр. `POST /api/v1/imagerouter/edit-image` (multipart: image,
     prompt, model) → обёртка над EDITS_URL, ответ — url/b64 картинки.
     ВАЖНО: шлюз ImageRouter не принимает `mask` ни у одной модели
     (п. грабель выше) — только image+prompt.
  3) Куда класть результат: либо просто показывать в панели вьювера
     (img в правой панели/модалка), либо сохранять в галерею InvokeAI
     (`services.images.create(...)` как в `_handle_canvas_generation`) —
     тогда результат доступен в Canvas для доработки. Для сохранения
     нужен ещё эндпоинт (галерея пишется только изнутри сервера).
     Минимальный UX: кнопка «📷→ИИ» в тулбаре вьювера → промпт →
     результат рядом со скриншотом; «в галерею» — вторым шагом.
  4) UI-мелочь: локальный select «с сервера» не обновляется сам после
     upload из другой вкладки — уже есть кнопка ↻ (обновить список).

21. **Кнопки локальной очереди убраны у Generate** (05.09, поздний вечер,
    по запросу пользователя). Справа от жёлтой кнопки Generate стояли две
    кнопки локальной очереди — «полоски» (QueueActionsMenuButton: пауза/
    возобновление/очистка/новая очередь) и «крестик» (CancelIconButton:
    отмена текущего элемента). При облачной генерации локальная очередь
    всегда пуста — кнопки бесполезны. Удалены из рендера ряда QueueControls
    (App-бандл, компонент D$e): children ряда
    `[InvokeQueueBackButton(pne), Spacer(mt), QueueActionsMenuButton(cne),
    CancelIconButton(fne)]` → `[pne, mt]` — реализовано `patch_queue_buttons()`
    в `setup_imagerouter.py` (бандл ищется по displayName=
    "InvokeQueueBackButton", идемпотентно, бэкап тот же
    `*.imagerouter-bak`). Компоненты cne/fne остаются в бандле
    определёнными, но нигде не используются (each o.jsx — ровно 1 раз
    был). Полоса прогресса ПОД кнопкой (`nw`, L$e) сохранена — через неё
    виден прогресс облачной генерации (п. 8). Проверка после патча:
    node-import App-бандла (только document is not defined) + логин через
    siteauth и GET /assets/App-*.js — старого фрагмента нет, новый на
    месте. F5 в браузере достаточно; действует на все инстансы компаний
    (venv общий).

22. **Prompt Enhancer — улучшение промта через VLM ImageRouter** (06.09).
    Голубая кнопка ✨ (#38BDF8, 56×40px, слот 60px справа от жёлтой
    Generate; патч App-бандла `patch_prompt_enhance_button` в
    setup_imagerouter.py) запускает ШТАТНЫЙ флоу Prompt Expansion
    (ci.setPending + lb — как у скрытой штатной кнопки): граф
    claude_expand_prompt → реальная очередь → string_output → оверлей
    результата. Сервер: `imagerouter/prompt_enhancer.py`, деплой
    `deploy_prompt_enhancer` в `venv/.../invokeai/app/invocations/
    devbim_prompt_enhancer.py` — пакет подхватывает новые *.py сам
    (__all__ в __init__.py + star-import graph.py). Инвокации
    claude_expand_prompt (prompt + images[]) и claude_analyze_image ходят
    в /v1/openai/chat/completions; модель zai/glm-5.3-flash, override
    .env PROMPT_ENHANCER_MODEL; вывод всегда английский; max_tokens 1500
    (ГРАБЛЯ: reasoning-модели при малом лимите возвращают ПУСТОЙ content —
    бюджет съедается размышлениями до начала ответа, поймано на glm-5.3-
    flash @300). Референсы: `patch_expand_graph_refs` дописывает в граф
    глобальные Reference Images (state.canvas.present.referenceImages.
    entities[].ipAdapter.image; сервер берёт до 4 шт, даунскейл до 1024,
    JPEG q85). V2 (06.09, вечер, по жалобе «дом во вьювере не учитывался»):
    если включённых референсов НЕТ — фолбэк на текущий выбор галереи
    (state.gallery.selection, последние 4) — «что открыто во вьювере, то
    и учитывается»; уже пропатченные V1-бандлы мигрируют на V2 повторным
    запуском setup (JS_REFS_COLLECTOR_V1 → V2); поведение коллектора
    проверяется тестом в node. ГЕНЕРАЦИЯ с пустым канвасом (вторая жалоба
    06.09, «вьювер не отсылается на генерацию»): patch_generate_viewer_
    fallback — клик Generate сначала зовёт __devbimGenFallback(store)
    (хелпер перед const m7, в pne добавлен g=Je(), onClick обёрнут в
    .finally): нет контента на канвасе (raster/control) и нет включённых
    референсов -> последняя выбранная картинка галереи прикладывается
    глобальным референсом штатным экшеном (E1+id+H0, как ПКМ «Use as
    Reference Image»); гейты: модель imagerouter/* из state.params.model.key
    и «редактирование» в описании (иначе txt2img не ломаем). ГРАБЛЯ: DTO
    картинки — ТОЛЬКО POST /api/v1/images/images_by_names ({image_names:
    […]}), GET /api/v1/images/{name} в 6.2 отдаёт 404 (V1 фолбэка молча
    уходила в txt2img — миграция V1→V2 повторным setup). Метка режима в
    метаданных: «imagerouter-edit» теперь и для чистых референсов.
    Проверено вживую 06.09: пустой канвас + выбранная картинка -> в графе
    ip_adapter, посредник шлёт edits c image[]. Оверлей: `patch_expansion_overlay_edit` — редактируемый
    textarea (uncontrolled defaultValue + чтение из DOM в Replace/Insert).
    Флаг allowPromptExpansion НЕ включаем: оверлей и блокировка промпта
    от него не зависят, точка входа одна — наша кнопка. Пустой промт без
    референсов → тост «Введите промт или приложите референсное
    изображение». ГРАБЛИ (найдены при деплое 06.09): (а) `from __future__
    import annotations` в модуле инвокций ВАЛИТ СЕРВЕР на старте (fix
    7add770): InvokeAI-реестр разбирает аннотацию выхода `-> StringOutput`
    через inspect.signature БЕЗ eval_str, получает строку 'StringOutput',
    и run_app падает на `.__name__` — future-annotations в
    invokeai/app/invocations ЗАПРЕЩЕНЫ (в модуле стоит guard-комментарий);
    (б) порядок в main() (fix a3367e5): patch_generate_button()
    (переименование m7="DevBIM"→"Generate") обязан идти ДО
    patch_prompt_enhance_button() — на свежем force-reinstall+rebrand
    якорь кнопки PE — m7="Generate". VLM отвечает 5–30 с — оверлей крутит
    спиннер, textarea до ответа disabled. Проверено вживую 06.09 (обе
    вкладки, Generate и Canvas): Replace/Insert берут отредактированный
    текст, референсы доходят до VLM (ответ явно опирается на «as shown in
    the reference image»), консоль чистая; скриншот
    docs/prompt-enhance-button.png. Ключ/URL/модель читаются ЛЕНИВО
    внутри call_vlm из задеплоенного роутера
    invokeai.app.api.routers.imagerouter (единый источник — .env).
    use_cache=False на обеих инвокациях — свежий результат на повторных
    кликах (temperature > 0). Тесты: tests/test_prompt_enhancer.py
    (включая живой smoke VLM). Проверка после изменений:
    setup_imagerouter.py + node-import App-бандла + рестарт + E2E
    чек-лист (план docs/superpowers/plans/2026-09-06-prompt-enhancer.md).

23. **Диагностика «картинки из вьювера не уходят в генерацию» — код
    исправлен не был, причина в старой вкладке браузера** (06.09, поздний
    вечер; жалоба пользователя после V2). Разбор по дампу
    `data/_ir_last_graph.json`: попытка 17:38 («сделай дрон вью»,
    nano-banana-2) ушла БЕЗ узла ip_adapter — фолбэк не отработал на
    клиенте. Что проверено и работает: (а) все гейты фолбэка — живыми
    fetch из браузера `/api/v2/models/i/imagerouter%2F...` обе модели
    отдают описание с «· редактирование», `POST images_by_names` — 200;
    (б) живой E2E в свежей вкладке Playwright: и «Холст», и «Generate»
    прикладывают выбранную во вьювере картинку (в enqueue_batch есть
    ip_adapter с image_name; origin=canvas, destination=canvas:<id> |
    generate — оба варианта); (в) прямым тестом к `/v1/openai/images/edits`
    (nano-banana-2, контрольное поле `image` против `image[]`): шлюз
    принимает ОБА имени поля, модель видит картинку в обоих случаях —
    «шлюз теряет image[]» опровергнуто. ПРИЧИНА жалобы: вкладка браузера
    пользователя была открыта ДО рестарта 17:16 и работала со старой
    V1-сборкой, где фолбэк молча падал на `GET /api/v1/images/{name}`
    (404 в 6.2). Лечение: F5/Ctrl+F5. ГРАБЛИ: (а) после каждого
    setup_* + рестарта пользовательская вкладка ОБЯЗАНА перезагрузиться —
    браузер держит старый JS и «фича не работает» без всяких ошибок;
    (б) в дампе `origin`/`destination` лежат ВНУТРИ `batch`, а не в корне
    payload (прочитал не тот уровень — чуть не искал несуществующий
    «enqueue без origin»); (в) дамп перезаписывается каждым перехватом —
    первый инструмент ответа «что реально ушло»: референсы = узлы
    type=ip_adapter (+ core_metadata.ref_images); (г) полностью чёрные
    референсы (например, результат «сделай ночь») модель сохранить не
    может — результат выглядит «как с чистого промта», не путать с
    «картинка не ушла» (проверяется по дампу); (д) фолбэк прикладывает
    ТОЛЬКО последнюю выбранную (sel[length-1]) картинку и референсы
    НАКАПЛИВАЮТСЯ в состоянии канваса между кликами (H0-add без cleanup)
    — в тесте в граф ушло 2 референса подряд, при желании чистить
    референсы перед генерацией. Стоимость диагностики: ~$0.6 кредитов
    (3 генерации + 2 прямых API-запроса), остаток $18.64.

24. **Модернизация сечений IFC-вьювера** (06.09, вечер, по запросу
    пользователя «вертикальные сечения + скрытие плоскости + что-то ещё»).
    Кнопки «Сечение»/«✕ сечения» заменены кнопкой «Сечения ▾» —
    всплывающая панель `#secpanel` в тулбаре вьюпорта (видна и в
    embed-режиме панели «IFC Viewer» на холсте). Всё — внутри
    `ifc/ifcviewer.html`, деплой штатным setup_ifcviewer.py (копия
    as-is), бандлы не тронуты. Возможности: (а) три типа сечений —
    горизонтальное (нормаль (0,-1,0), 75% высоты) и вертикальные X/Z
    (нормаль ±X/±Z со ЗНАКОМ ПО КАМЕРЕ — срезается половина,
    обращённая к наблюдателю); (б) тумблер «👁 Плоскости» — clipper.visible
    (скрывает ВСЕ helpers, клиппинг остаётся); (в) карточка на каждое
    сечение: слайдер позиции вдоль оси в пределах bbox (live-координата
    в метрах), ⇄ флип нормали, 👁 видимость конкретной плоскости
    (plane.visible), ✕ удаление (clipper.delete(world,id)); «Удалить все»;
    (г) после перетаскивания стрелки слайдеры обновляются
    (clipper.onAfterDrag); сечения переживают перезагрузку модели.
    ГРАБЛИ (03.09…06.09 проверено по бандлу 3.4.8): (1) у Event из
    @thatopen метод подписки `.add()`, НЕ `.on()` — на `.on()` падает
    молча «TypeError: onAfterDrag.on is not a function»; (2)
    библиотечный plane.setFromNormalAndCoplanarPoint НЕ годится для
    флипа: его reset() делает helper.lookAt(normal) ДО сброса позиции
    helper — при флипе к нормали (1,0,0) второй lookAt пропускается
    (normal.equals) и квадрат/стрелка оказываются повёрнуты криво;
    вместо него своя movePlane(): normal.copy + origin.copy +
    helper.position.copy + helper.quaternion.setFromUnitVectors(ẑ,
    normal) + update() — update() синхронизирует three.plane из
    normal+helper.position, клиппинг едет вживую (объекты плоскостей в
    материалах те же); (3) ЖИВАЯ позиция после drag — только
    plane.helper.position (plane.origin при drag НЕ обновляется);
    (4) clipper.createFromNormalAndCoplanarPoint возвращает id
    (string), порядок clipper.list = порядок создания; (5) при
    добавлении сечения clipper.visible=true принудительно (иначе при
    скрытых helpers новое сечение «не появляется»); (6) агрегат-тумблер
    «👁 Плоскости» показывает «скрыты», если скрыта ХОТЯ БЫ одна
    (every-visible), клик по нему показывает ВСЕ. Отладка:
    window.__ifc.addSection('h'|'x'|'z'), __ifc.refreshSections(),
    __ifc.movePlane. Тесты: `tests/test_ifc_sections.py` (+ node
    --check извлечённого module-скрипта вручную). Скриншоты:
    docs/ifc-sections-*.png (panel-open/horizontal/vertical-x/
    planes-hidden/flipped). Спека:
    docs/superpowers/specs/2026-09-06-ifc-sections-upgrade-design.md.

25. **«Человек» в IFC-вьювере: силуэт + камера от глаз 1,7 м** (06.09,
    поздний вечер, по запросу «как в SketchUp»). Кнопка «👤 ▾» в тулбаре
    → панель #personpanel (структура/деплой — как сечения, всё в
    ifcviewer.html). (а) Постановка: «Поставить на перекрытие» включает
    режим (body.placing, курсор crosshair), следующий КЛИК по модели
    ставит фигуру (в pointerup-выборе guard `if (placingPerson)`).
    Привязка к перекрытию — snapToGround(): вертикальный луч ВНИЗ от
    точки клика (+0,1) через fragments.raycast с ВРЕМЕННОЙ
    PerspectiveCamera(fov 35, near 0.01, far 60), смотрящей строго вниз;
    мышь = центр канваса (screenToCast вычитает rect, setFromCamera
    строит луч от переданной камеры — камера может быть любой, проверено
    на школе с офсетом x≈27, z≈19). Клик по горизонтали → та же
    поверхность; по стене → пол под ней; ПРОМАХ (двор без плиты — в
    school.ifc центр bbox это двор!) → высота клика как есть. (б) Фигура:
    биллборд PlaneGeometry 0.55×1.75 + CanvasTexture (силуэт рисуется
    canvas 2D, colorSpace SRGB), свой rAF разворачивает по азимуту
    камеры (atan2 dx,dz); маркер-сфера уровня глаз на 1,7. (в) «Вид от
    глаз»: controls.enabled=false, поза+проекция сохраняются
    (controls.getTarget(new Vector3()) — camera-controls 3.x ТРЕБУЕТ
    out-параметр!), камера ведётся вручную quaternion.setFromEuler(
    Euler(pitch,yaw,0,'YXZ')) в собственном rAF; осмотр — pointer drag
    (pitch clamp ±1.45), ходьба WASD/стрелки 1,6 м/с (Shift 4,8),
    forward по горизонту от yaw ((-sinφ,-cosφ), right (cosφ,-sinφ));
    человек следует x/z с перепривязкой snapToGround (троттлинг 150 мс,
    snapToken от гонок); fragments.core.update() при движении (LOD);
    ESC/кнопка — выход: setLookAt(saved)+проекция, силуэт показывается.
    При загрузке ДРУГОЙ модели человек убирается (personModelName!==name).
    ГРАБЛИ: (1) ГЛАВНЫЙ БАГ: snapToGround при промахе возвращал y ГЛАЗ —
    ходьба по пустоте поднимала камеру на +1,7 каждые 150 мс (улетела на
    y=7.75 при высоте модели 2,7); фикс — промах возвращает null, высота
    сохраняется; (2) чтение camera.position сразу после enterFP() даёт
    СТАРУЮ позу — fpLoop копирует eye только со следующего rAF-кадра (не
    баг, но в тестах ждать кадр); (3) рендер непрерывный (Components.update
    rAF-цикл) — ручная камера/биллборд отображаются без доп. триггеров;
    (4) клик по канвасу закрывает панели (внешний клик) — после постановки
    человека панель закрывается, принято. Отладка: window.__ifc.person
    (place/enterFP/exitFP/remove/state). Тесты: tests/test_ifc_sections.py
    (+ test_person_markup/logic). Скриншоты: docs/ifc-person-*.png
    (placed/fp-roof/fp-ground/orbit/fp-school). Спека — там же,
    дополнение от 06.09 (вечер).

26. **ИИ-рендеринг: контактная тень + BIM-контекст промта + панель
    «Камера»** (06.09, ночь; первая очередь из обзора «что полезного для
    ИИ-рендеринга», утверждена пользователем). Всё — в ifcviewer.html,
    деплой setup_ifcviewer.py. (а) КОНТАКТНАЯ ТЕНЬ в снимке: 4 нижних
    угла bbox проецируются камерой (projectGroundRect), мягкий
    радиальный эллипс (rgba(8,10,14,0.42)→0, 0.55× габарита) рисуется
    ДО наложения WebGL-кадра — виден только в прозрачных полях, здание
    «стоит» на земле; отключена в FP и когда основание за камерой
    (dot<=0)/вне кадра; в орто-фасаде вырождается (ry<2 → skip).
    Проверено пиксельно: ~120k тёмно-полупрозрачных пикселей.
    (б) BIM-КОНТЕКСТ ПРОМТА: walkCtx по getSpatialStructure строит
    ctxMap localId→{storey,space,cat}; ГРАБЛЯ (главная): в структуре
    КОНТЕЙНЕР имеет category без localId, а его сущность — ДОЧЕРНИЙ
    узел с localId без category (example: IFCBUILDINGSTOREY#null →
    ?#144 → IFCSLAB#null → ?#22620) — id этажа/помещения берём у
    первого потомка с localId, класс элемента — с ближайшего
    контейнера-предка; иначе контекст ПУСТОЙ (первая версия смотрела
    category у id-узла). Имена этажей/помещений — ОДНИМ пакетным
    model.getItemsData (LongName ?? Name), асинхронно после дерева.
    Источник: элемент клика постановки человека (personCtxId,
    обновляется при ходьбе по snap-лучу) либо одиночное выделение.
    Строка «BIM context: floor "Nivel 1", element SLAB» — в поле
    #person-context панели «Человек» (клик — select());
    при «📸 To Canvas»/«💾 To Assets» — copyContextToClipboard()
    (navigator.clipboard, фолбэк textarea+execCommand, тост «paste
    into the prompt (Ctrl+V)») — вставить в промт руками, поле промта
    приложения не патчим. (в) ПАНЕЛЬ «📷 ▾» (#campanel): FOV-слайдер
    20–90° (threePersp.fov + updateProjectionMatrix); «⌷ Вертикали» —
    в FP pitch→0 (горячая V; вне FP — подсказка), проверено: Euler.x=0;
    «— Горизонт» — орбита: офсет цели проецируется в горизонталь при
    сохранении длины; «▦ Орто-фасад» — projection.set("Orthographic")
    + setLookAt по нормали (lastHitNormal последнего raycast-клика, y
    гасится; нет клика — ось X/Z к камере) + world.camera.fit(
    model.object.children); «◐ Перспектива» — назад; рамка кадра
    (#cropguide, select 1:1/3:2/16:9/…) — пунктир + затемнение вне
    (box-shadow 200vmax), renderSnapshot кропит по прямоугольнику
    (CSS→буфер через DPR), стороны по-прежнему snap64 (кроп 1190×670 →
    1216×704). ГРАБЛИ: строка проекции — "Orthographic", НЕ "Ortho"
    (ProjectionManager.set: всё не-"Orthographic" уходит в перспективу
    — первый вариант молча не переключал); #toolbar потребовал z-index
    над затемнением рамки. Отладка: window.__ifc.promptContext,
    __ifc.camera.{setFov,setGuide,levelVerticals,levelOrbit,orthoFacade,
    lastHitNormal}. Тесты: tests/test_ifc_ai_render.py. Скриншоты:
    docs/ifc-ai-{shadow-snapshot,ortho-facade,panels}.png. Спека —
    docs/superpowers/specs/2026-09-06-ifc-sections-upgrade-design.md,
    дополнение 2. НЕ СДЕЛАНО (кандидаты следом): «кадры» (сохранение
    видов+серия снимков), авто-маска по элементу (силуэт через Hider →
    мост V3), пакетная генерация + PDF-альбом.

17. **Мультикомпанность: экземпляр сервера на компанию** (05.09.2026).
    Продажа по компаниям: каждой — отдельный процесс InvokeAI со своим

    портом (9100+), паролем и корнем `companies/<код>/data` (галерея,
    IFC-файлы, БД изолированы автоматически; venv и патчи общие).
    Спека/план: `docs/superpowers/specs|plans/2026-09-05-company-instances*`.
    - Скрипты: `create_company.py` (--name/--code/--valid-until/--password;
      создаёт `.env`, `data/invokeai.yaml` с портом, `CREDENTIALS.txt`,
      запись в `companies.json`; защита от перезаписи существующего
      каталога), `start_company.bat <код>` (cwd=companies/<код>,
      INVOKEAI_ROOT=.../data, chcp 65001, лог companies/<код>/server.log),
      `stop_company.py` (psutil по порту; AccessDenied → нужен админ),
      `list_companies.py`; библиотека `company_manager.py`.
    - `siteauth/site_auth.py`: +`SITE_VALID_UNTIL` (ГГГГ-ММ-ДД) — при
      просрочке все запросы (http+ws) закрываются страницей «Лицензия
      истекла» (200); дата входит в токен куки sha256(соль+пароль+дата).
      ГРАБЛЯ (исправлено): `_load_env_file` кэширует значения в
      os.environ — из-за этого правка .env не подхватывалась без
      перезапуска; теперь `_env_value(key)` перечитывает .env-файл на
      каждом вызове (порядок кандидатов INVOKEAI_ROOT → parent → cwd,
      файл — источник истины, пустое значение = бессрочно). Пароль по
      умолчанию «devbim», fallback os.environ при отсутствии файлов.
    - IFC per-company: `_store_dir()` = `get_config().root_path/ifc` —
      у каждой компании своя папка, создаётся при первой загрузке;
      перенос моделей = копирование файлов.
    - Тесты (plain asserts, печать OK): `tests/test_site_auth.py`,
      `test_company_manager.py`, `test_create_company.py`.
    - Проверка компании: create → `start_company.bat <код>` (первый старт
      ~1 мин — инициализация БД) → `curl http://127.0.0.1:<порт>/auth/login`
      → stop. Секреты (`companies/*`, `companies.json`, `.env`) в git
      не входят; в git только `companies/.gitkeep`.

18. **PDF-вьювер: вкладка «PDF», фрагменты страниц → холст/ассеты**
    (05.09, ветка `feature/pdf-viewer`, проверено вживую Playwright-ом).
    Поток: загрузка PDF (диск / сервер; хранение `data/pdf/` per-company,
    лимит 500 МБ; API `/api/v1/pdf/list|upload|file/{name}` DELETE,
    роутер `pdf/pdf_router.py` — копия паттерна ifc_router) → поиск
    страницы (миниатюры с ленивым рендером IntersectionObserver,
    оглавление `getOutline` + `destToPage`, поле номера, ←/→/PageUp/
    PageDown, зум −/+/Ctrl+колесо/100%, «Ширина»/«Вписать», поворот)
    → рамка фрагмента (ЛКМ-drag по странице, затемнение вне рамки
    box-shadow-трюком, ESC/клик — сброс, новая заменяет прежнюю) →
    «🖼 To Canvas» / «💾 To Assets» (интерфейс на АНГЛИЙСКОМ — базовый
    язык, русская локализация отдельно; изначально был русский,
    переведён 05.09 по решению пользователя). Рендер PDF.js 5.4.149, ассеты
    `pdf/assets/` → `dist/pdf/` (mjs отдаётся как application/javascript
    на этой машине — воркер работает; проверять после переноса).
    Кроп: offscreen-рендер страницы под целевую длинную сторону фрагмента
    2048 px (лимит полной страницы 16 Мп, абсолютный cap масштаба ×12,
    белый фон) → PNG → `POST /api/v1/images/upload`.
    «To Canvas» = мост `__devbimIfc.toCanvas(dto,false)` (категория
    general, поведение «Редактировать»: подложка + слой «Маска
    перерисовки» + кисть). «To Assets» = `image_category=user`: вкладка
    «Assets» галереи фильтрует categories=control|mask|user|other,
    а general попал бы в «Изображения» (грабля найдена снапшотом сети).
    ГРАБЛЯ (главная): `window.__devbimIfcCtx` выставляет только панель
    IFCV на холсте — с вкладки PDF мост падал «canvas context
    unavailable» (у IFC не проявлялось: его кнопки «На холст» живут
    только в embed-панели, т.е. на холсте). Решение: PDFE (компонент
    вкладки PDF в App-бандле) сам захватывает `Je()` в `__devbimIfcCtx`
    при монтировании; вкладки pdf/canvas не активны одновременно — за
    глобаль не спорят (cleanup старой вкладки до effect новой).
    Миграция уже патченных бандлов: `JS_PDF_PANEL_V1` → `V2` повторным
    запуском `setup_pdfviewer.py` (идемпотентно). Прочее: iframe вкладки
    размонтируется при переключении — последний серверный документ +
    страница восстанавливаются из localStorage
    (`devbim:pdf:lastDoc`/`lastPage`); иконка вкладки `vx` («документ»,
    function-декларация в App-бандле — тот же приём, что `RA` у IFC);
    `pdf` добавлен в zod-enum activeTab (index-бандл); патч вставляется
    префиксом перед якорем `const cue=u.memo(` — совместим с мостом
    `__devbimCanvasBridge` из п.16 (тот же якорь, тоже префикс).
    Порядок после force-reinstall: rebrand → imagerouter → ifcviewer →
    **pdfviewer** (гейт: без `__devbimIfc` в бандле откажется) → siteauth.
    + ПАНЕЛЬ «PDF Viewer» НА ХОЛСТЕ (05.09, вечер, вслед за запросом
    пользователя): в главную dockview-область рядом с «Image Viewer»/
    «IFC Viewer» добавляется третья панель (iframe ?embed=1 — без
    шапки/сайдбара/фута, плавающие тулбар/навигация/селектор документов
    `#embedbar`, статусы — тостом `#etoast`). Реализация — как IFCE/IFCV
    у IFC: `PDFP(e,t)` вызывается в onReady goe ПОСЛЕ регистрации
    (fromJSON не зовёт колбэк дефолтного layout — покрыты оба пути),
    `pdfviewer:jn(PDFV)` в карте компонентов, focusRegion "viewer",
    tabComponent t$, position `within` группы viewer-панели. PDFV, как
    PDFE и IFCV, захватывает Je() в `__devbimIfcCtx` — активной бывает
    одна панель dockview (неактивные демонтируются), за глобаль не
    спорят. ГРАБЛИ (ожидаемое поведение, не баг): после «To Canvas»
    мост делает focusPanel("canvas") — активной становится панель
    редактора, PDF-панель демонтируется (iframe detach) — как у IFC;
    документ/страница восстанавливаются автозагрузкой при возврате на
    панель. Embed-синхронизация: storage-событие по lastDoc — вкладка
    «PDF» открыла другой документ, панель перезагружает его (как IFC).
    Layout с панелью сохраняется и переживает F5. Якоря патча (после
    ifcviewer): onReady `({api:n})=>{eWe(e,n),IFCE(e,n)}` → `+PDFP(e,n)`,
    компоненты `components:{...JUe,ifcviewer:jn(IFCV)}` → `+pdfviewer:
    jn(PDFV)`; идемпотентность — по наличию `PDFP(e,n)` в onReady.
    Тесты: `tests/test_pdf_router.py`; генератор тестового PDF с
    оглавлением — `tests/make_test_pdf.py`. Отладка: `window.__pdf`
    в iframe (doc/page/selection/gotoPage).

26. **Референсы доходят до модели: JSON-массив вместо multipart** (06.09,
    поздний вечер; жалоба «добавил в Reference Image несколько фото, но
    они не уходят вместе с промтом и картинкой из canvas»). Симптом:
    генерация 22:03 прошла УСПЕШНО (в БД есть результат, режим
    imagerouter-edit), но модель игнорировала референсы и рисовала
    материал «из головы» — вместо кирпича и жёлтой штукатурки с
    референсов вышли винтажные обои. КОРНЕВАЯ ПРИЧИНА (4 контрольных
    запроса к /v1/openai/images/edits, nano-banana-2): multipart с
    несколькими файлами — будь то image + image[], повторённое имя
    image — доставляет модели ТОЛЬКО ПЕРВОЕ изображение, остальные
    молча отбрасываются (HTTP 200, ошибки нет; «контактный лист» из
    двух референов выходил двумя копиями первого). Проверка 19.08
    (п.7) была с ОДНИМ референсом — поэтому грабля ждала пользователя.
    Работает JSON-тело с "image": [data-URL, data-URL, ...] — доходят
    все картинки. Фикс в `imagerouter_router.py` (деплой штатным
    setup_imagerouter.py): при референсах edits уходит JSON-массивом
    (база — PNG data-URL, альфа холста сохраняется; референсы — JPEG
    1024/q85, как в п.22); маска → сразу маркер (шлюз mask отвергает);
    к промпту добавляется PROMPT_REFERENCE_ROLES_NOTE (первая картинка
    — исходник, остальные — референсы материалов); БЕЗ референсов —
    прежний multipart-путь (не тронут). Диагностика: строки
    [imagerouter] enqueue/edits json/saved/FAILED в ir_server.log
    (раньше _IRClientError уходил тостом в UI, не оставляя следа в
    логе — 22:03 пришлось разбирать по дампу); в метаданных результата
    теперь ref_images. Эталон: docs/diag-edits-refs-json-0609.png;
    живой диагностический скрипт tests/_diag_edits_refs_json.py
    (~$0.07/запуск). E2E 06.09: реальный граф 22:03 (канвас + маска +
    2 референса), отправленный POST-ом в enqueue_batch живого сервера,
    — стены облицованы кирпичом и штукатуркой с референсов, геометрия
    сохранена. ГРАБЛИ: (а) created_at в БД — UTC (22:04 локальное =
    19:04 в БД; едва не сделан вывод «результат не сохранился»);
    (б) шлюз ошибки отдаёт HTTP 200 с телом {"error": ...} — статус
    коду доверять нельзя, только _api_error_message; (в) фикс чисто
    серверный — F5 вкладке не нужен.

27. **Облачный апскейлинг: вкладка Upscaling через ImageRouter + выбор
    моделей администратором** (08.09; запрос пользователя «настрой
    upscaling… в меню пользователя — модели, выбранные администратором»).
    Спека/план: `docs/superpowers/specs|plans/2026-09-08-cloud-upscaling*`.
    Всё серверное — в `imagerouter_router.py` (деплой штатным
    setup_imagerouter.py, JS-бандлы НЕ тронуты), админ-UI — секция
    «Апскейлинг» в imagerouter.html.
    - **Механика вкладки 6.2** (разведка по бандлам): unified-апскейл
      требует main sd-1/sdxl (фейки уже sdxl), tile-ControlNet (type=
      controlnet, base=main, «tile» в имени — автоселект эффектом в `_Ke`)
      и spandrel-модель (дропдаун = все type=spandrel_image_to_image,
      предикат `RI`, автоселект первого + ПЕРСИСТИТ прежний выбор —
      у «свежего» пользователя по умолчанию ПЕРВЫЙ элемент списка админа).
      Граф `sSe`: spandrel_image_to_image_autoscale(модель+scale+image) →
      unsharp → i2l → tiled_multi_diffusion(denoising_start=f(creativity))
      + ДВА controlnet-узла (control_weight=f(structure) у ПЕРВОГО) → l2i.
      Quick-action «Постобработка (Shift+U)» строит adhoc-граф с ОДНИМ
      узлом spandrel_image_to_image (без main-модели) — поэтому is_upscale
      определяется по spandrel-узлу, а не по main-ключу.
    - **Ключи ролей разделены**: `imagerouter-upscale/<id>` для spandrel-
      фейков — одна модель может быть main и апскейлером одновременно, а
      GET /api/v2/models/i/{key} отдаёт один конфиг на ключ. Плюс фейк
      `imagerouter/tile-controlnet` (base sdxl) — чисто декорация.
    - **Выбор администратора**: `data/imagerouter_upscale.json` (в
      INVOKEAI_ROOT/data — это data/data/ в проекте, per-company),
      дефолт в коде DEFAULT_UPSCALE_MODELS (5 апскейлеров, все проверены
      живыми edits-запросами 08.09). Эндпоинты GET/PUT
      /api/v1/imagerouter/upscale-models (PUT валидирует: каталог +
      вход-image). Админ-UI: чекбоксы (только модели со входом-image),
      стрелки ↑↓ = порядок = модель по умолчанию первая, подсказка про F5.
    - **Перехват**: `_extract_ir_info` ищет spandrel-узлы → is_upscale,
      upscale_model_key, init_image, scale (adhoc → 2), board — из поля
      board ЛЮБОГО узла (у апскейла доска на l2i, не save_image);
      creativity = 1 − denoising_start, structure = control_weight
      ПЕРВОГО controlnet (грабля: в графе их два, второй 0.21375 —
      перезапись давала мусор). Обработчик `_handle_upscale_generation`:
      JSON edits (image=[data-URL], промпт серверный EN c порогами
      creativity/structure), size = _pick_upscale_size (явные sizes →
      ближайший покрывающий; иначе snap64, кап стороны 2048), события
      через общие фабрики `_queue_event_factories` (вынесены из
      canvas-обработчика). Проверка эха НЕ применяется (честный апскейл
      после даунскейла ≈ вход — ложное «эхо»).
    - **ГРАБЛЯ (фактический размер)**: size — пожелание; clarity-2x/
      swinir-2x/latent-2x/ccsr-2x дают ровно ×2 от входа (4x вернёт 2x),
      P-Image-Upscale — 2048²/2896². Для большего — повторный прогон.
    - **Лончпад вкладки почищен** (08.09, по запросу пользователя):
      `patch_upscale_launchpad` в setup_imagerouter.py убирает блок
      «Creativity & Structure Defaults» (пресеты Conservative/Balanced/
      Creative/Artistic + подсказки про промт) — управление ЛОКАЛЬНОЙ
      tiled-диффузией, в облачной схеме мусор; остались загрузка и
      «Ready to upscale!». ГРАБЛЯ идемпотентности: маркер поиска бандла
      — `displayName="UpscalingLaunchpadPanel"` (сам текст блока после
      патча исчезает — первый вариант с маркером «Creativity & Structure
      Defaults» падал на повторном запуске «найден 0 раз»). Слайдеры
      Creativity/Structure в «Опциях Расширенных» левой панели оставлены
      (переводятся в промпт). Скриншот docs/upscale-launchpad-clean.png.
    - E2E 08.09 (Playwright): вкладка без предупреждения, дропдаун =
      выбор админа (5 дефолт / 2 / 6 при смене файла), апскейл 512×384 →
      1024×768 в галерее, quick-action перехвачен (scale=2), админ-секция
      сохраняет. Скриншоты docs/upscale-{models-dropdown,admin-section}.png.
      Тесты: `tests/test_upscale_cloud.py` (инъекция, extraction двух
      графов, size-picker, промпт, эндпоинты). Стоимость проверки ~$0.05.

28. **Основные модели для пользователей: выбор администратора** (08.09,
    вечер; запрос «добавь выбор ИИ-моделей для генерации и редактирования
    с той же логикой, что апскейлинг… краткое описание, значок правки,
    стоимость не выводить»). Та же механика, что у апскейла (п.27):
    - Хранение: `data/imagerouter_main_models.json` (per-company).
      **Файла нет → инъектируются ВСЕ модели каталога** (обратная
      совместимость, ничего не ломается); пустой список разрешён (=
      отключить генерацию). Эндпоинты GET/PUT
      /api/v1/imagerouter/main-models (PUT валидирует только наличие в
      каталоге — чистая генерация без входа-image допустима; GET отдаёт
      пропавшие из каталога id с available=False — информативно,
      инъекция их фильтрует).
    - Инъекция: `_selected_main_models()` — выбор в порядке админа,
      первый элемент = модель по умолчанию у «свежих» пользователей
      (персистентный выбор пользователя живёт, пока модель в списке).
    - Админ-UI: секция «Генерация и правка — модели для пользователей» в
      imagerouter.html (все модели каталога, поиск, чекбоксы, ↑↓, краткое
      описание по модальностям, значок «✏️ правка», БЕЗ цен — цены
      остались в «Каталоге моделей» для бюджета админа).
    - **Цены убраны из пользовательских описаний** (решение 08.09): main —
      «Облачная генерация изображений · ✏️ редактирование», upscale —
      «Облачный апскейл изображений». ГРАБЛЯ: слово «редактирование» в
      описании main-моделей ОБЯЗАТЕЛЬНО — на него опирается гейт
      Generate-фолбэка (п.22), ✏️-эмблема его не заменяет.
    - E2E 08.09: PUT двух моделей → /api/v2/models содержит ровно их,
      дропдаун пользователя «2 models», админ-секция «выбрано: 2 из 142»;
      после удаления файла — снова весь каталог (all_by_default).
      Тесты: `tests/test_main_models.py`. Скриншот
      docs/main-models-admin-section.png.

29. **Upscaling: панель вкладки под облако — режимы и форматы из
    каталога, локальные пункты убраны** (09.09; запрос пользователя
    «в апскейлинге есть пункты меню, актуальные для локальной разработки —
    удалить и адаптировать под облачные модели; система должна знать
    режимы (2×, 4K…), подтягивать автоматически; формат изображения —
    тоже автоматически для выбранных моделей»). Спека:
    `docs/superpowers/specs/2026-09-09-upscale-cloud-ui-design.md`.
    - **Убрано из левой панели вкладки** (патч `patch_upscale_cloud_panel`
      в setup_imagerouter.py, бандл App-*.js, 4 замены, идемпотентно по
      маркеру `window.__devbimUpscaleMode`): аккордеоны «Генерация»
      (Wae: main-модель/LoRA/планировщик/шаги) и «Опции Расширенные»
      (Uae: VAE/precision/seed); внутри «Увеличить» — блок main-модели+
      tile-ControlNet (_Ke) и «Advanced Options» с Creativity/Structure
      (pKe/bKe; решение 08.09 «оставить» отменено — серверный промпт
      теперь фиксируется режимом). Main-модель остаётся в стейте
      (автоселект sdxl-фейка) — граф без неё не строится, но UI её не
      показывает. Слайдер «Масштаб» 2–8× (Yae) ЗАМЕНЁН селекторами
      «Режим увеличения» + «Формат изображения».
    - **Режимы**: `GET /api/v1/imagerouter/upscale-options` — по моделям
      выбора админа (тот же фильтр, что инъекция spandrel-фейков — списки
      совпадают один-в-один). Вывод из каталога v3 (`parameters.size`):
      явные размеры → режим-на-размер (P-Image-Upscale: 2048×2048,
      2896×2896); суффикс id `…-<n>x` → единственный честный множитель
      (clarity/swinir/latent/ccsr-2x → «2×»); прочий custom → фолбэк
      2×/4×. Форматы: png/jpeg/webp (глобальный параметр output_format
      generations/edits API, docs.imagerouter.io), дефолт png, выбор
      персистится в localStorage (devbimUpscaleFormat). Режимов «на
      глаз» больше нет — UI не предлагает того, что модель не умеет.
    - **Передача выбора**: новый Yae (минифицированный код в
      JS_UP_SLIDER_NEW, идентификаторы бандла u/o/E/K/T, селекторы Pve/
      Lve/qE/S$) пишет window-глобалы `__devbimUpscaleMode` /
      `__devbimUpscaleFormat` и синхронизирует scale-стейт (бейдж
      «модель WxH» пересчитывается). Патч билдера sSe кладёт оба поля
      прямо в spandrel-узел графа (undefined → JSON.stringify молча
      выбрасывает: quick-action из контекстного меню не затронут,
      работает по-старому scale=2/png). `_extract_ir_info` вычитывает
      upscale_mode/upscale_format; `_upscale_request_params` (тестируемый
      хелпер): режим с size → точный size запроса; режим с scale →
      честный множитель (перекрывает слайдерный); без режима — прежнее
      поведение; формат валидируется по белому списку → в edits-тело.
      Промпт `_upscale_prompt` умеет цель-размер («to 2048×2048
      resolution»).
    - **ГРАБЛЯ (фактический размер, продолжение п.27)**: каталог P-Image-
      Upscale заявляет 2048×2048/2896×2896, но для входа 512×384 модель
      вернула 3344×2508 (≈8.4MP — похоже, у неё кап по ПЛОЩАДИ, не по
      стороне). Режим — корректный запрос к API, фактический результат
      определяет провайдер.
    - **ГРАБЛЯ (E2E)**: после `select_option` режима снапшот мог показать
      прежний selected при одновременном RTK-refetch /api/v2/models
      (автоселект spandrel-модели на миг сбрасывал выбор на первую);
      повторное последовательное взаимодействие — стабильно. Если в E2E
      модель «сама переключилась» — повторить выбор после паузы.
    - E2E 09.09 (Playwright): локальных аккордеонов нет, селекторы на
      месте; смена модели P-Image-Upscale → режимы автоматически
      2048×2048/2896×2896, бейдж пересчитался; реальный прогон:
      mode=2896x2896 format=jpeg в enqueue-тело, сервер ушёл с точным
      size, HTTP 200, 512×384 → 3344×2508 сохранено в галерею.
      Тесты: `tests/test_upscale_cloud.py` (+3 секции: режимы,
      upscale-options, параметры запроса). Скриншоты
      docs/upscale-cloud-{tab,panel}.png. Стоимость прогона ~$0.005.

30. **«Вырезать по контуру» (✂) на холсте** (09.09; запрос пользователя:
    «кнопка-ножницы, рисуют замкнутую полилинию, подтвердить/отменить,
    система вырезает кусок картинки на новый слой поверх текущего, чтобы
    кусочек можно было двигать»). Спека:
    `docs/superpowers/specs/2026-09-09-canvas-cut-tool-design.md`.
    - **Виджет** `imagerouter/devbim_cut_tool.js` → `dist/devbim-cut-tool.js`
      + script в index.html (новая `deploy_cut_tool()` в
      setup_imagerouter.py, бэкап `index.html.cuttool-bak`, идемпотентно;
      JS-бандлы НЕ тронуты, перезапуск сервера не нужен — только F5).
      Использует мост `__devbimCanvasBridge` (п. 16).
    - **UI**: кнопка ✂ (иконка-«ножницы», стиль скопирован с соседней
      кнопки) вставляется в ВЕРТИКАЛЬНУЮ рейку инструментов холста —
      рейка ищется по суффиксам хоткеев aria-label «(B)»+«(E)» в
      `div.chakra-button__group` (локали-независимо; при ремоунте рейки
      пере-вставляется тиком 500 мс, React её не вычищает). Режим:
      клики = точки, ПКМ = убрать точку, клик ≤14px от первой = замкнуть;
      пилюля ✓/✕ справа от тумблера Mask/Layer (bottom:96px,
      translateX(+150px)); Enter/Esc; превью — SVG-оверлей поверх
      konva (fixed, pointer-events:none, rAF-синхронизация с rect
      контейнера и `stage.getAbsoluteTransform()`), зум колесом живой
      (wheel не перехватывается), pointerdown/dblclick/contextmenu над
      канвасом блокируются в capture-фазе — konva не рисует/не панорамирует.
    - **Вырезание** (протестировано вживую, попиксельно): источник =
      выделенный raster_layer (не растровое → верхний с объектами; нет →
      тост). `adapter.renderer.getCanvas({rect})` — ШТАТНАЯ растеризация
      Konva-группы слоя (cloneObjectGroup+cache, уважает ластики/фильтры);
      rect = объединение границ документа, bbox полигона и clientRect
      группы, в координатах ОБЪЕКТОВ (= документ − position слоя — ГРАБЛЯ:
      у raster-layer есть position, полигон обязан переводиться в
      объектные координаты, а позиция нового слоя = bbox+старая position).
      Кусок = destination-in по полигону, источник = destination-out;
      обе картинки → `/api/v1/images/upload?image_category=other&
      is_intermediate=true&silent=true` (ГРАБЛЯ 6.2: параметры в QUERY,
      поля формы дают 422). Затем stateApi.addRasterLayer() + опрос нового
      id (тупое сравнение множества id, ≤3 с) и ДВА raw-диспетча
      `{type:"canvas/entityRasterized"}` (prepare у экшена нет, payload
      проходит как есть): источник replaceObjects:true с прежней
      position; новый слой (последний = поверх всех) — кусок, position=
      bbox полигона, isSelected:true. Undo: [rasterLayerAdded] +
      [2×entityRasterized за 1 тик] → 2 шага Ctrl+Z (+1, если кусок
      двигали). ImageObject ровно как строит приложение:
      `{id, type:"image", image:{image_name,width,height}}`.
    - E2E 09.09 (Playwright, реальная мышь): кнопка в рейке; 4 клика =
      точки ровно в doc-координатах; Enter → в источнике прозрачная
      дырка (alpha=0 внутри полигона), красный/фон целы; кусок = слой
      pos(70,50) с 1 объектом, выделен; «Двигать (V)» перетаскивает
      (70,50 → 1600,1024); треугольный вырез круга + перенесённый кусок
      видны в композите stage.toCanvas (дырка = фон 39,43,49, кусок =
      зелёный 39,99,42); Esc отменяет без изменений. Скриншоты
      docs/cut-tool-{drawing,e2e-result}.png. Отладка в консоли:
      `window.__devbimCut` (state/cancel/confirm). Тесты:
      `tests/test_cut_tool.py` (деплой идемпотентен, node --check,
      ключевые конструкции). Безвредный шум в консоли: «Konva error:
      Can not cache the node…» — тот же даёт штатный filter-apply
      (кэширование пустой группы после replaceObjects).
    - **V2 (10.09, фидбек пользователя)**: (1) подложка НЕ меняется —
      destination-out/загрузка «источника с дыркой» убраны, кусок только
      копируется на новый слой; (2) новый слой создаётся с
      `isSelected:false` — голубая рамка-обводка (трансформер выделения)
      не появляется; «Двигать (V)» при этом всё равно тащит кусок по
      хит-тесту верхнего объекта (проверено E2E: кусок (70,50) →
      (-320,448), источник остался (0,0)); (3) подтверждение — Enter ИЛИ
      Ctrl+C (перехват в capture только в активном режиме), плюс
      глобальный Ctrl+V — вставка копии последнего кусочка новым слоем
      со сдвигом +24px за вставку (перехват ТОЛЬКО когда есть свой буфер
      `lastCut`, вкладка canvas, и курсор не в поле ввода; иначе событие
      проходит приложению/ОС штатно — stopPropagation в capture глушит и
      bubble-обработчики). Отладка: `__devbimCut.paste()` /
      `.clipboard()`. E2E 10.09: Ctrl+C после 4 точек → источник
      попиксельно цел (red/green/bg), кусок (70,50), выделение осталось
      на подложке; Ctrl+V×2 → слои (94,74) и (118,98). Скриншот
      docs/cut-tool-v2-result.png.
    - **V3 (10.09, фидбек «кусочек прыгает по крупной сетке»)**: штатная
      привязка позиций к сетке — `stateApi.getPositionGridSize =
      settings.snapToGrid ? (Ctrl/Meta ? 8 : 64) : 1` — при отдалённом
      зуме даёт огромные шаги. Виджет в тике патчит менеджера
      (`ensureSmoothPatch`, один раз на инстанс, метка
      `stateApi.__devbimSmooth`): обёрнутый getPositionGridSize возвращает
      1, ЕСЛИ сейчас тащат один из НАШИХ кусочков. Кусочки опознаются по
      префиксу id объекта `image_devbimcut_` — маркер живёт в состоянии
      канваса и ПЕРЕЖИВАЕТ F5; детект драга —
      `adapter.transformer.konva.proxyRect.isDragging()` (трансформер
      тащит именно proxyRect; $isTransforming при drag НЕ поднимается —
      грабля). Прочие слои/рамка генерации снапятся как раньше (глобальная
      настройка не тронута). E2E 10.09: после F5 кусок драгается
      пиксельно точно (+72,−37 doc при зуме 0.456 — не кратно 64),
      источник при том же драге лёг на сетку (64,−64). ЗАМЕТКА: дельта
      перетаскивания в doc-пикселях = экранный дельта / зум.
    - **V4 (10.09, фидбек «иконка ✂ огромная» + «прочие кнопки-инструменты
      остаются активными»)**: (а) иконке ✂ добавлены width/height="1em" —
      ровно как у штатных иконок рейки (было 30px без атрибутов, стало
      14px, у пилюли размер задаёт её CSS 15px — не тронут); (б) при
      активных ножницах body получает класс `devbim-cut-mode`, рейка —
      `devbim-cut-rail` (в ensureRailButton, пере-накатывается тиком при
      ремоунте), CSS глушит вид АКТИВНОЙ штатной кнопки до неактивного
      (rgb(138,146,163)/rgb(22,24,29) — вычисленные стили этой темы,
      !important против chakra-класса активной кнопки css-1bg4tlz
      rgb(71,177,230)); сама ✂ в активном режиме красится как штатная
      активная (синий фон + тёмная иконка, inline-стили в
      syncRailButton); (в) клик по ДРУГОЙ кнопке рейки при активных
      ножницах завершает режим (onRailOtherTool, capture pointerdown),
      инструмент включается штатно. E2E: размеры/цвета проверены,
      скриншот docs/cut-tool-v4-active.png.


31. **Upscaling: модели вкладки = выбор менеджера + поля Ширина/Высота/
    Качество** (09.09; запрос пользователя «в апскейлинг приходят не те
    модели что в менеджере.. надо поля где видно размеры.. длина ширина и
    качество 1 234 К»). Спека:
    `docs/superpowers/specs/2026-09-09-upscale-models-match-manager-design.md`.
    - **Диагноз**: дропдаун «Модель увеличения» показывал 5 дефолтных
      спец-апскейлеров (DEFAULT_UPSCALE_MODELS, файл выбора не создавался),
      а «модели пользователя» в менеджере — сохранённый выбор «Генерация
      и правка» (14 моделей, все с входом-image). Решение пользователя:
      дропдаун повторяет выбор менеджера.
    - **Цепочка источников** (`_upscale_selection_source` в
      imagerouter_router.py): файл `imagerouter_upscale.json` есть —
      сохранённый выбор (пустой список = отключить апскейл); файла нет,
      есть `imagerouter_main_models.json` — наследуем его («main»);
      нет обоих — DEFAULT_UPSCALE_MODELS («default»). GET /upscale-models
      отдаёт `selection_source` + `inherited_from_main` + legacy
      `defaults_used` (теперь True только в ветке default). Инъекция
      по-прежнему фильтрует по каталогу и вход-image. Админ-UI
      (imagerouter.html): при наследовании подсказка «Показан выбор из
      секции „Генерация и правка“…»; чекбоксы секции «Апскейлинг»
      отражают эффективный список — сохранение закрепляет отдельный.
    - **Поля изображения** (патч v2 `Yae` в setup_imagerouter.py, над
      «Режимом увеличения»): Ширина/Высота (ImageDTO из qE) + Качество =
      размер файла оригинала в КБ (HEAD по image_url — ImageRecord не
      несёт file_size), формат «1 234 К» (toLocaleString ru-RU); без
      картинки «—», при загрузке «…». Отладочный window-глобал
      `__devbimUpscaleImgInfo={width,height,kb}`.
    - **Идемпотентность v1→v2**: маркер v2 — `__devbimUpscaleImgInfo`;
      бандл с v1 (`window.__devbimUpscaleMode` без v2) перепатчивается
      только в части селекторов (константа JS_UP_SLIDER_NEW_V1 — источник
      замены), свежий бандл — все четыре замены. Повторный запуск —
      «уже с полями изображения (v2), пропуск».
    - E2E 09.09 (Playwright + живой прогон): дропдаун = 14 моделей
      менеджера (первая FLUX-2-max автоселект), поля «512 px / 384 px /
      7 К», режимы FLUX-2-max 2×/4× (фолбэк — у main-моделей нет явных
      размеров); реальный апскейл FLUX-2-max 512×384 mode=2x jpeg →
      HTTP 200 → 1024×768 в галерее (~$0,005). Тесты:
      `tests/test_upscale_cloud.py` (+секция 6b: наследование, флаги,
      фильтрация инъекцией, возврат default). Скриншот
      docs/upscale-panel-models-manager.png.

32. **«Текст» (T): текстовый слой на холсте** (10.09; запрос
    пользователя «пишу текст — формируется на отдельном слое… поменять
    цвет… размер изменением размеров слоя или вводя размер шрифта»).
    Спека: `docs/superpowers/specs/2026-09-10-canvas-text-layer-design.md`.
    - **Решение**: отдельный тип entity в минифицированном бандле не
      создать — текстовый слой = растровый слой с одним объектом-
      картинкой (`image_devbimtext_*`), который виджет создаёт и
      ПЕРЕРИСОВЫВАЕТ. Настройки (текст/цвет/размер/гарнитура/жирность)
      в localStorage `devbimTextLayers` ПО ID СЛОЯ — переживают F5 и
      bbox-растеризацию (у которой меняется лишь id объекта, слой тот
      же). Размер меняется BOTH способами: вводом размера шрифта
      (перерисовка) И штатным bbox (B).
    - **Виджет** `imagerouter/devbim_text_tool.js` → `dist/devbim-
      text-tool.js` + script в index.html (`deploy_text_tool()` в
      setup_imagerouter.py, бэкап `index.html.texttool-bak`,
      идемпотентно; бандлы НЕ тронуты — достаточно F5). Кнопка T (иконка
      «type», 1em) в рейке инструментов (поиск рейки по «(B)»+«(E)»);
      панель fixed bottom:142px (над пилюлей Mask/Layer на 96px, где
      142px — как ✂-пилюля): textarea (многострочно), color+hex,
      размер 8–512 px, Sans/Serif/Mono, «Ж», «Добавить»/«Применить»+
      «Новый слой»; Esc — закрыть, Ctrl+Enter — применить. RU/EN.
      Живое превью НОВОГО текста — div-оверлей (pointer-events:none,
      rAF) в центре видимой области с зум-скейлом; при правке существ.
      слоя превью выключено (под ним реальный объект). Отладка:
      `window.__devbimText` (state/open/close/add/apply/registry).
    - **Создание** — ОДИН диспатч `addRasterLayer({isSelected:false,
      overrides:{name, objects:[…], position}})` (путь sentImageToCanvas:
      overrides проходят deepmerge Wi, проверено). Позиция — центр
      видимой области в doc-координатах (clamp в документ). Имя слоя
      `T · первая строка ≤24 симв.` (видно в списке слоёв). Konva
      показывает картинку объекта в НАТУРАЛЬНОМ размере (image.width/
      height из DTO; поля width/height самого объекта рендером
      ИГНОРИРУЮТСЯ — проверено по бандлу) → растр рендерится ровно
      1:1 в документных пикселях (offscreen canvas, textBaseline top,
      межстрочный 1.25, pad max(2,12%)). Upload — как у ✂ (QUERY-
      параметры!). **Правка** — raw-диспетчи `canvas/entityRasterized`
      (replaceObjects:true, позиция слоя сохраняется) +
      `canvas/entityNameChanged` (имя вслед за текстом); один тик =
      один шаг undo. Подписка на store: выделение текстового слоя при
      открытой панели автоматически переключает её в режим правки.
      **Плавный драг**: своя обёртка `getPositionGridSize` (флаг
      `__devbimTextSmooth`, цепочкой после ✂-обёртки `__devbimSmooth` —
      сосуществуют): пока тащат наш слой (id в реестре ИЛИ префикс
      объекта) — сетка 1 px, остальные слои снапятся штатно (64).
    - ГРАБЛИ (E2E 10.09): (а) кэш абсолютного трансформа stage бывает
      отравлен NaN при чистых attrs (getAbsoluteTransform() → NaN до
      РЕАЛЬНОГО изменения атрибута; повтор с тем же значением Konva
      шорткатит) — виджет считает doc↔screen по АТРИБУТАМ
      stage.scaleX()/x()/y() + isFinite-фолбэк в центр документа;
      ✂-виджет (toDoc через invert) не тронут; (б) панель fixed
      перекрывает канвас — мышь уходит в панель, Konva молча не
      получает события (драг «не работает» без ошибок!) — закрыть
      панель перед работой с канвасом; (в) синтетические
      setPointersPositions({x,y}) без clientX/clientY → NaN в
      getPointerPosition → getImageData-ошибка в getIntersection —
      артефакт тестирования, не баг приложения.
    - E2E 10.09: создание (96px/#38BDF8/жирный → растр 630×144,
      4765 голубых пикселей), правка (48/#ff3333 → 308×72, 1153
      красных, имя слоя обновилось), драг V: (198,384)→(542,214)
      = +344/−170 doc при экранной +72/−37 (не кратно 64), F5 — всё
      живо (слой/имя/позиция/реестр/правка). Скриншоты
      `docs/text-tool-{panel-preview,created,final}.png`. Тесты:
      `tests/test_text_tool.py` (+ в блок «Проверка после изменений»).

33. **Вкладка «Design Code» — вьювер сайта дизайн-кода** (10.09; запрос
    пользователя: кнопка вьювера → модальное окно «URL сайта + код» →
    интерактивное окно с сайтом типа https://nw.dev-bim.com/). Спека:
    `docs/superpowers/specs/2026-09-10-design-code-viewer-design.md`.
    Всё по паттерну PDF-вьювера (п.18), БЕЗ моста на холст (сайт внешний,
    cross-origin).
    - **UI**: кнопка в левой рейке после PDF (id `designcode`, label
      «Design Code», иконка-палитра — Phosphor palette fill; встраивается
      собственной function-декларацией `DCI` через бандловый хелпер `ue`
      (GenIcon) — того же формата, что RA/vx; ГРАБЛЯ: глобы/palette в
      бандле НЕТ, путь взят из react-icons@5.5.0/pi PiPaletteFill).
      Панель вкладки — iframe `/design_code_viewer.html` (компонент `DCE`
      перед `const cue=u.memo(`, unregisterTab в cleanup, `designcode`
      добавлен в zod-enum activeTab index-бандла — вкладка переживает F5).
    - **Страница** `design_code/design_code_viewer.html`: без сохранённого
      URL/разблокировки — модальная карточка «Site URL» (префилл из
      DESIGN_CODE_URL .env или последнего ввода) + «Access code» →
      POST /api/v1/designcode/auth → при успехе iframe грузит сайт, URL —
      в localStorage `devbim:designcode:url`, разблокировка — в
      sessionStorage `devbim:designcode:unlocked` (код спрашивается РАЗ
      на вкладку браузера, как админ-гейт; «⚙ Change site» → модалка
      снова, Esc/Cancel — назад к сайту). Плавающий тулбар: чип хоста,
      «⟳ Reload», «↗ New tab» (если сайт запрещает встраивание
      X-Frame-Options — iframe пустой, спасает ↗), «⚙ Change site».
      Язык EN (базовый, решение 05.09); RU — отдельная задача.
    - **Роутер** `design_code/design_code_router.py` →
      `routers/design_code.py`: GET/POST `/api/v1/designcode/auth`;
      код — `DESIGN_CODE_ACCESS_CODE` из .env (per-company, перечитывается
      на каждом вызове как siteauth — смена кода БЕЗ рестарта; не задан
      или пустой → защита выключена, модалка код не спрашивает — зеркало
      admin-auth); URL обязан http(s)://; неверный код — 401 + пауза 0.3 с
      (hmac.compare_digest).
    - Деплой: `setup_designcode.py` (идемпотентен, бэкапы
      `*.designcode-bak`; гейт: PDF-патчи обязаны быть применены — якоря
      сидят на pdf-кнопке/панели). Порядок после force-reinstall: rebrand
      → imagerouter → ifcviewer → pdfviewer → **designcode** → siteauth.
      venv общий — вкладка появляется у всех компаний, код у каждой свой
      (`companies/<код>/.env`).
    - E2E 10.09 (Playwright, живой туннель): кнопка в рейке → модалка с
      префиллом https://nw.dev-bim.com/ → неверный код «Неверный код
      доступа» → nw2026 → сайт «Северный Берег» открыт в iframe (скриншот
      docs/designcode-site-open.png), ⚙/Esc/⟳ работают, F5 — вкладка
      восстановилась, код НЕ запрошен повторно (0 ошибок консоли).
      Скриншоты: docs/designcode-{gate,site-open,after-f5}.png.
      Тесты: `tests/test_designcode.py`. Отладка: код в .env (дефолт
      nw2026), страница — прямой URL /design_code_viewer.html.

34. **Нижние панели «To Canvas / To Assets» в вкладках Design Code и IFC**
    (11.09; запрос пользователя «добавь панель (внизу окна) копирования на
    холст или в ассеты, как в PDF-вьюере»). Спека:
    `docs/superpowers/specs/2026-09-11-copy-to-canvas-panels-design.md`.
    - **IFC (вкладка)**: snapbar `#snapbar` («📸 To Canvas» + «💾 To
      Assets») существовал только в embed-режиме — теперь CSS показывает
      его в ОБЕИХ режимах (в вкладке селектор моделей скрыт, он в шапке),
      обработчики подключаются до `if (EMBED)`, тост `embedToast` больше не
      гасится вне embed. Снимок — прежний renderSnapshot (прозрачный фон,
      контактная тень, кратно 64). Мост: **IFE v2** в `setup_ifcviewer.py`
      — компонент вкладки IFC захватывает `Je()` в `window.__devbimIfcCtx`
      при монтировании (как PDFE v2; раньше контекст держали только IFCV
      и PDFE/PDFV — из вкладки IFC мост падал «canvas context
      unavailable»). Миграция v1→v2 повторным запуском setup.
    - **Design Code**: сайт cross-origin — прочитать его iframe НЕЛЬЗЯ,
      картинку снимает Screen Capture API. Панель `#capbar` внизу (когда
      сайт открыт): «📷 Capture» → getDisplayMedia({video:
      {displaySurface:"browser"}, preferCurrentTab:true, selfBrowserSurface:
      "include"}) → кадр кропается по rect iframe `#site` в координатах
      вкладки (`rectInTop` — сумма смещений по цепочке same-origin iframe,
      масштаб videoWidth/top.innerWidth — DPR вкладки) → «заморозка»
      `#freeze` (canvas + selLayer): рамка фрагмента как в PDF (drag, бейдж
      «W × H», затемнение вне рамки, клик = вся область, Esc/✕ — назад),
      панель переключается в «Fragment: W × H px» + «🖼 To Canvas» +
      «💾 To Assets». Отправка — путь IFC/PDF: PNG → `/api/v1/images/upload`
      (general/user) → мост `__devbimIfc.toCanvas` (подложка + маска +
      кисть) / вкладка «Assets». ГРАБЛИ: (а) панель/тост прячутся
      (visibility) ДО захвата кадра, ждём 2 новых кадра (rVFC, фолбэк
      таймеры 180 мс, общий таймаут 3 с) — иначе они попадают в снимок;
      (б) отмена пикера = NotAllowedError/AbortError — тихо; (в) выбрана
      другая поверхность — видно в замороженном превью, Esc и повторить;
      (г) Permissions-Policy display-capture ('self') — iframe вьювера
      same-origin, allow-атрибут не нужен. Мост: **DCE v2** в
      `setup_designcode.py` (захват `__devbimIfcCtx`, миграция v1→v2);
      вкладки designcode/canvas не активны одновременно — глобаль не
      спорит с PDFE/IFE/IFCV/PDFV.
    - E2E 11.09 (Playwright; getDisplayMedia подменён canvas-стримом с
      контрольными цветами): кроп пиксельно точен (центр #7cc7ff — область
      сайта, не фон), рамка drag → «Fragment: 585 × 287 px», To Assets →
      201 user + тост + freeze закрыт; To Canvas из вкладки Design Code →
      приложение на «Холсте», растр 1170×706 + слой маски + кисть
      (DCE v2 live); IFC вкладка: snapbar display:flex, селектор скрыт,
      example.ifc → To Assets 201 user, To Canvas → «Холст», растр
      704×768 + маска + кисть (IFE v2 live); 0 ошибок консоли. Тестовые
      слои/картинки вычищены. Скриншоты:
      docs/designcode-{capture-selection,to-canvas-result}.png,
      docs/ifc-tab-to-canvas-result.png. Тесты: `tests/test_ifc_sections.py`
      (+test_snapbar_tab_mode), `tests/test_designcode.py` (панель + DCE v2
      + node --check скрипта страницы). Правка панелей —
      design_code/design_code_viewer.html + ifc/ifcviewer.html + повторный
      setup_*; откат бандлов — *.ifcviewer-bak / *.designcode-bak.
    - **ДОПОЛНЕНИЕ (11.09, после живого теста пользователя «Error: IFC:
      canvas context unavailable»)**: вкладка пользователя была открыта ДО
      деплоя — iframe вьюера обновился (панель видна), а внешний App-бандл
      остался старым (без DCE v2) → мост есть, контекста нет (та же грабля
      п.23: без F5). Сделан ФОЛБЭК `toCanvasViaBridge(dto)` во ВСЕХ трёх
      вьюерах (design_code/pdf/ifc): если `__devbimIfcCtx` пуст — скрипт
      `__devbimSendToCanvas` (создаётся `new parent.Function` — ИСПОЛНЯЕТСЯ
      В КОНТЕКСТЕ ПРИЛОЖЕНИЯ) поллит `__devbimCanvasBridge.getManager()`
      (есть во всех бандлах с 05.09), при необходимости переключает вкладку
      на «Холст» (`__devbimSwitchTab('canvas')`), ставит
      `__devbimIfcCtx = manager.stateApi.store` ({dispatch,getState} стора —
      ровно то, что читает мост) и вызывает `__devbimIfc.toCanvas(dto)`.
      ГРАБЛИ (почему именно parent.Function): первый вариант фолбэка с
      setInterval ВНУТРИ iframe терял вызов — при переключении вкладки наш
      iframe отсоединяется и ЕГО таймеры/промисы умирают (контекст
      успевали поставить смонтированные панели, но toCanvas не вызывался);
      колбэк родительского realm переживает detach. Быстрый путь (контекст
      уже есть) вызывает мост напрямую. E2E 11.09 (эмуляция старого бандла:
      `__devbimIfcCtx=null` до клика, менеджер не поднят): To Canvas из
      Design Code → сам переключил вкладку, добыл сторе, растр 1172×707 +
      маска + кисть (скриншот docs/designcode-stale-bundle-fallback.png);
      после F5 быстрый путь цел. Заодно починена идемпотентность
      `setup_pdfviewer.patch_index_bundle` (та же грабля, что п.20 у
      ifcviewer: точный поиск enum не находил бандл после добавления
      designcode — теперь regex по наличию "pdf" в enum).

35. **Кнопки «Prompt Assistant» и «3D Design» в правом углу баннера**
    (15.09; запрос пользователя: «добавь текст на кнопку улучшателя промтов,
    выровняй высоту с Generate, добавь кнопку 3D Design другого цвета,
    обе — группой в правом углу»). Спека не писалась (малый UI-патч по
    готовым паттернам).
    - **Патч App-бандла v2** (`patch_prompt_enhance_button`,
      миграция V1→V2 повторным запуском setup): вместо голубой кнопки ✨
      56×40px в слоте 60px у Generate в бандле остаётся только ХОСТ:
      глобал `window.__devbimPromptEnhance()` (ci.setPending + lb — тот же
      штатный флоу Prompt Expansion; фолбэк стора — менеджер холста
      `__devbimCanvasBridge.getManager().stateApi.store`, клик работает и
      до монтирования ряда Generate) и невидимый наблюдатель DevbimPEWatch
      на старом месте в ряду (при каждом рендере обновляет
      `__devbimPEStore` / `__devbimPEPending`). Слот 60px у Generate
      вернулся к стоковому пустому виду (заглушка V1 удалена).
    - **Виджет** `imagerouter/devbim_topright_buttons.js` →
      `dist/devbim-topright-buttons.js` + script в index.html (новая
      `deploy_topright_buttons()` в setup_imagerouter.py, бэкап
      `index.html.topright-bak`, идемпотентно; бандлы НЕ тронуты — после
      деплоя достаточно F5). Группа `#devbim-tr-btns` живёт в ПРАВОМ углу
      ЛЕВОЙ ПАНЕЛИ — в ряду жёлтой Generate (очереди), за Spacer'ом
      (поправка 15.09 по фидбеку пользователя: «правый угол не всего
      интерфейса, а левой панели»; первая версия была в баннере).
      Локале-независимый поиск ряда: жёлтая invokeYellow кнопка ~36px
      в верхней части панели (rgb-эвристика: R>180, G>140, B<110) →
      контейнер 200px → родительский ряд с .chakra-numberinput. Тик 500
      мс пере-вставляет группу при ремоунте панели (React вычищает её
      вместе с рядом) и прячет на вкладках без ряда (Workflows/IFC/PDF/
      Design Code). АДАПТИВНОСТЬ (по фидбеку пользователя 15.09: «при
      уменьшении панели кнопки пропадали»; доработка — «в деградированном
      виде оставить звёздочку и текст 3D»): fit(row) каждый тик считает
      свободное место (ширина ряда − контейнер Generate − gap) и при
      <240px переключает группу в класс devbim-tr-compact — кнопки 36×36
      без длинного текста: у ✨ остаётся ЗВЁЗДОЧКА (svg), у «3D Design» —
      короткая подпись «3D» (атрибут data-short выводится через ::after);
      min-width:14px/flex-shrink:1 — страховка от полного исчезновения
      (на практике панель dockview и так не уже ~408px — компактный вид
      помещается всегда). Расширение панели возвращает полный вид. Кнопка ✨
      «Prompt Assistant» (#38BDF8, клик → `__devbimPromptEnhance`,
      приглушается пока VLM работает по `__devbimPEPending`) и «3D
      Design» (#A78BFA, заглушка — тост «раздел в разработке»;
      функциональность — отдельная задача). Высота ОБЕИХ кнопок 36px =
      Generate (было 40px — «немного больше», по жалобе); шрифт 13px,
      паддинг 10px — чтобы пара с текстом влезла в свободные ~250px
      ряда (панель 456px: 200 контейнер Generate + группа 229px).
      Тосты RU/EN по языку интерфейса (IndexedDB-поллинг, как у баннера).
    - E2E 15.09 (Playwright, живой сервер; после поправки размещения):
      группа в ряду Generate левой панели (правый край группы = правый
      край ряда, y=50 = Generate), высоты Generate/PE/3D = 36px; на
      «Холсте» группа на месте в ряду той вкладки, на IFC — скрыта,
      возврат на Generate — снова на месте; сжатие панели драгом sash
      dockview: 456px → полный вид, минимум панели ~408px → компактный
      вид (✨-звёздочка + «3D», 36×36, кнопки видимы),
      расширение → полный вид возвращается; старой кнопки в ряду
      Generate нет, клик «Prompt Assistant» запускает штатный оверлей
      (кнопка disabled на время работы VLM), результат учитывает картинку
      из вьювера, Discard закрывает без изменений промта; «3D Design» —
      тост. Скриншоты docs/topright-buttons-{final,compact}.png. Тесты:
      `tests/test_topright_buttons.py` (+ обновлён
      test_patch_prompt_enhance_button в tests/test_prompt_enhancer.py
      под v2). Отладка: `window.__devbimPromptEnhance` (function),
      `__devbimPEStore`, `__devbimPEPending`; DOM — `#devbim-tr-btns`
      (класс devbim-tr-compact = компактный вид: звёздочка + «3D»).
      Откат: восстановить `*.imagerouter-bak` App-бандл (или повторный
      setup после отката виджета), `index.html.topright-bak`, удалить
      `dist/devbim-topright-buttons.js`.

36. **Design Code: гвард локальных адресов + кнопка «↺ Default»** (15.09;
    жалоба пользователя «кнопка дизайн-код… работает как пдф вьювер»).
    ПРИЧИНА: вкладка — вьювер ПОСЛЕДНЕГО введённого адреса (localStorage
    `devbim:designcode:url` имеет приоритет над DESIGN_CODE_URL из .env), а
    там со времён тестов панели захвата (11.09, п.34) лежал
    `http://127.0.0.1:9090/pdfviewer.html` — вкладка честно открывала
    PDF-вьювер как «сайт». Кнопка/бандлы были исправны. Заодно выяснено:
    сам https://nw.dev-bim.com/ в тот день отдавал Cloudflare 530 (туннель
    не поднят) — внешняя проблема, не локальная.
    - **Гвард** `isLocalSiteUrl(url)` в design_code_viewer.html: петля
      (localhost/127.*/0.0.0.0/[::1]) и хост самого приложения
      (location.hostname) — не «сайт дизайн-кода». (а) В submit такой URL
      отклоняется ДО запроса с пояснением «This is a local app address…»;
      (б) на старте сохранённый локальный URL ВЫЧИЩАЕТСЯ из localStorage, и
      вкладка fallback-ит на DESIGN_CODE_URL (адрес по умолчанию). Роутер НЕ
      тронут (остаётся permits локальные URL — .env может задавать локальный
      default для разработки/тестов).
    - **«↺ Default»** в модалке (id btnDefault, видна когда сервер отдал
      default_url): заполняет поле адресом из DESIGN_CODE_URL и гасит
      ошибку. showGate теперь префиллит `savedUrl() || defaultUrl`.
    - Отладочный хук `window.__dc` ({openSite, showGate, isLocalSiteUrl}) —
      как __ifc/__pdf; полезен E2E, которым нужен не-локальный «сайт» без
      правки гварда (localStorage-инъекция теперь вычищается).
    - Деплой: setup_designcode.py (копия html; бандлы не менялись, рестарт
      сервера не нужен — только F5). Тесты: tests/test_designcode.py
      (+статические проверки и поведенческий node-тест isLocalSiteUrl на 7
      URL). E2E 15.09 (Playwright): подложен плохой localStorage → после
      перезагрузки поле = default; ввод pdfviewer.html → отклонён с
      сообщением (0 сетевых ошибок); Default → адрес восстановлен; вход с
      кодом → сайт открыт. Скриншот designcode-guard-fixed.jpeg (рядом с
      проектом, в docs не переносили).

37. **3D Design (фаза 1): генерация IFC по картинке — «Генплан»** (18.09,
    ветка `3d`; кнопка «3D Design» из п.35 превращена из заглушки в рабочий
    конвейер). Спека:
    `docs/superpowers/specs/2026-09-18-3d-design-ifc-generation-design.md`.
    - **Конвейер**: модалка в `imagerouter/devbim_topright_buttons.js`
      (плитки сценариев — «Генплан» активен, «Фасад»/«Интерьер» disabled
      с подсказкой «фаза 2–3»; превью источника с бейджем Холст/Галерея;
      textarea уточнений) → `POST /api/v1/threed/generate` {scenario,
      prompt, image dataURL} → VLM-аналитик (по SYSTEM_GENPLAN) строит
      строгий JSON-сцену (extract_json + 1 ретрай на невалидный) →
      validate_genplan (clamp координат в границы картинки, дефолты
      масштаба 0.5 м/px и высот этажей, этажность 1–30, битые
      секции/контекст выбрасываются с warnings → тост в модалке) →
      build_genplan: IFC4 с поэтажными IfcBuildingElementProxy-экструзиями,
      контекст-плиты IfcGeographicElement, pset DevBIM на IfcProject /
      SiteMassing на IfcBuilding / MassingElement на элемент, превью-PNG
      (обводки + этажность поверх исходника; упрощение против спеки —
      БЕЗ matplotlib-3D-превью, 3D-вид даёт вьювер) →
      `data/ifc/3D_plan_<stamp>.ifc` → виджет ставит localStorage
      `devbim:ifc:lastModel` + `__devbimSwitchTab('ifc')` → полная
      вкладка IFC автозагружает модель (раньше автозагрузка жила только
      в embed-панели п.13 — теперь и топ-уровневый `if (!EMBED)` в
      ifcviewer.html). Дальше штатный цикл: сечения, человек, 📸 To
      Canvas → ИИ-рендер.
    - **Файлы**: `threed/threed_router.py` (деплой `routers/threed.py`;
      POST /generate, GET/PUT /model), `threed/threed_scenarios.py`
      (SYSTEM_GENPLAN/extract_json/validate_genplan) и
      `threed/threed_build.py` (build_genplan) — деплой as-is;
      `setup_threed.py` (идемпотентен, бэкап `api_app.py.threed-bak`,
      гейты: сперва imagerouter и designcode); админ-секция «3D-генерация
      — модель аналитики» (`#threedsec`) в `imagerouter/imagerouter.html`;
      тесты `tests/test_threed.py` (9 функций, plain asserts).
    - **Модель-аналитик** (менеджер за шестерёнкой): цепочка
      `data/imagerouter_threed_model.json` → `.env THREED_MODEL` →
      дефолт `openai/gpt-6-astra`; PUT /api/v1/threed/model валидирует
      по каталогу /v3/models (вход image, выход text — СВОЙ запрос:
      существующий GET /imagerouter/models фильтрует output=image и VLM
      не отдаёт); смена без F5 — модель читается при каждой генерации.
    - **ГРАБЛИ**: (1) /v3/models отвечает ГОЛЫМ JSON-списком, а не
      {"data":[…]} — парсер принимает ОБЕ формы; слепое .get("data")
      молча оставляло список VLM пустым и отключало PUT-валидацию
      (фикс 2b909cd). (2) Дамп диагностики — `root_path/ifc/
      _threed_last.json` (рядом с IFC: out_dir в _generate_impl —
      ifc-каталог), НЕ в data/. (3) E2E-баги виджета ловит только
      рантайм: open3D вызывал refresh3D вместо refresh3DSource —
      ReferenceError, статика/node --check слепы (2497de7);
      canvasComposite обязан читать canvas-стейт ЧЕРЕЗ .present
      (redux-undo, ключ «canvas» нижнего регистра) и PER-TYPE entities:
      `state.canvas.present.rasterLayers.entities` /
      `controlLayers.entities` — плоского present.entities НЕТ
      (ded1841, 5ea07b0); эталон-паттерн — canvasState() в
      devbim_mask_toggle.js / devbim_cut_tool.js. (4) siteauth гейтит и
      /api/v1/threed/* — curl-проверки требуют cookie devbim_auth (вход —
      как п.17: POST /auth/login). (5) Синтетическую схему VLM разбирает
      ~10 с, реальные генпланы дольше — запрос синхронный (сервер 180 с /
      фронт 300 с), модалка крутит таймер, не паниковать раньше таймаута.
    - **Отладка**: `data/ifc/_threed_last.json` (последняя генерация),
      `window.__devbimPEStore` (стейт приложения: canvas/gallery), хук
      `__ifc` в iframe вьювера, превью `data/ifc/3D_plan_*_preview.png`.
      Скриншоты E2E: docs/3d-design-modal.png, docs/3d-design-ifc-result.png.
    - **Деплой**: setup_threed.py; порядок после force-reinstall: rebrand
      → imagerouter → ifcviewer → pdfviewer → designcode → **threed** →
      siteauth. Зависимости: ifcopenshell 0.8.5 + shapely 2.1.2 (pip, в
      общий venv). Стоимость живой генерации ~$0.05–0.15 (Astra
      completion $50/M токенов); за E2E-сессию сделано 2 живые генерации.
      Фазы 2 (фасад) и 3 (интерьер) — планы отдельными документами.

38. **3D Design (фаза 2): сценарий «Фасад»** (19.09, ветка `3d`; план
    `docs/superpowers/plans/2026-09-19-3d-design-phase2-facade.md`, 7 задач).
    - **Конвейер** — та же модалка, но плитка «Фасад» АКТИВНА («Интерьер»
      осталась disabled «фаза 3»); placeholder промта меняется по сценарию
      (promptPhPlan/promptPhFacade, RU/EN). `POST /api/v1/threed/generate`
      {scenario:"facade"} → VLM по `SYSTEM_FACADE` (вход — фото/рендер ИЛИ
      чертёж; ВСЯ схема В МЕТРАХ; масштаб по размерным линиям или опорам:
      этаж ~3 м, окно ~1.5×1.5, дверь ~2.1, балкон ~3×1.2) →
      `validate_facade` (гейт ValueError: нет storeys/width_m/windows/
      floor_height; клампы 1–30 этажей; margin pre-clamp ДО FIT,
      FIT-сжатие окон по свободной ширине; skip-матрица → rows×cols;
      балконы вне диапазонов DROP с warnings; типо-гварды windows/colors/
      balconies) → `build_facade`: тома-этажи CONCEPTUAL_STOREY
      (width×depth×floor_height), окна CONCEPTUAL_WINDOW сеткой
      (w×0.12×h, центр y=depth/2 — передняя грань на 0.06 м ВПЕРЕДИ
      фасада; заподлицо делать НЕЛЬЗЯ: совпадающие грани не рендерятся
      и не кликаются, фикс 1429399), балконы-плиты CONCEPTUAL_BALCONY
      (этаж≥2, выступ d_m), цоколь CONCEPTUAL_PLINTH (+0.2 м), крыша —
      flat ИЛИ двускатная CONCEPTUAL_ROOF (3-точечный профиль,
      выдавливание depth с матрицей поворота локальная Y→Z), pset
      FacadeModel на IfcBuilding (Storeys/FloorHeight/WidthM/DepthM/
      Roof/RoofHeight/WindowsTotal/BalconiesCount/OrthoAssumption=True
      (перспектива принята за орто)/DepthAssumed=True), превью — чертёж фасада в метрах
      (стены/цоколь/окна/balcony-штриховка/крыша/штрих-линии этажей).
      Роутер: SCENARIOS={"plan","facade"}, ветвление промпт/валидатор/
      сборщик по сценарию; interior → 422 «в разработке».
    - **ГРАБЛИ**: (1) Свойство `textarea.placeholder` НЕ декодирует
      HTML-сущности: в TEXTS хранить чистые кавычки, экранировать
      (`replace(/"/g,'&quot;')`) только в точке интерполяции innerHTML
      (9347398). (2) В validate_facade margin pre-clamp обязан идти ДО
      FIT-сжатия: margin_x 5 при width 3 давал ОТРИЦАТЕЛЬНЫЕ w_m/h_m
      (e0e2c0d). (3) Клик по окну/балкону/цоколю в 3D-вьювере даёт
      «Стены · этаж N» / ничего — ИЗВЕСТНОЕ ОГРАНИЧЕНИЕ canvas-picking
      @thatopen на сгруппированных фрагментах; expressID и геометрия
      корректны (дерево выбирает те же элементы с полными props),
      стены/крыша кликаются. (4) E2E-методика: если MCP-браузера нет —
      `pip install playwright` + `launch_persistent_context(
      channel="chrome", headless=True)` работает (WebGL рендерит);
      props-панель ЧИСТИТЬ между кликами (wait ловит старый CONCEPTUAL_);
      «Вписать» сбрасывает орто-ориентацию; `orthoFacade()` выбирает
      грань по текущей позиции камеры — навести камеру вдоль нужной оси
      ДО вызова; VLM-анализатор скриншотов ГОЛЛЮЦИНИРУЕТ фасады —
      верить пиксельным проверкам (PIL-кроп блоба здания). (5) Тесты
      роутера импортируют venv-копии threed-модулей — после правок
      threed/* сперва setup_threed.py, потом тесты.

39. **Вкладка «Модели» на весь экран: ImageRouter без левого списка**
    (19.09; запрос пользователя «удали слева список, настройки ImageRouter
    — по всему экрану, видеть параметры/деньги, добавлять/удалять
    доступность»). Спека:
    `docs/superpowers/specs/2026-09-19-model-manager-fullscreen-design.md`.
    - **Патч вкладки** `patch_models_tab_fullscreen()` в setup_imagerouter.py
      (App-бандл, идемпотентен, бэкап тот же): компонент вкладки «models»
      `()=>o.jsxs(E,{layerStyle:"body",w:"full",h:"full",gap:"2",p:2,
      children:[ModelManager,ModelPane]})` заменён на голый iframe
      `/imagerouter.html` на 100%×100% (p:0). Родной список моделей
      (ModelManager: поиск/фильтр/«Основные»/корзины) больше НЕ рендерится.
      Regex не привязан к минифицированным именам; маркер «готово» —
      `JS_MODELS_TAB_DONE`. Патч InstallModels (JS_NEW_COMPONENT)
      сохранён: после fullscreen он мёртвый код, но нужен для цепочки
      идемпотентности на свежеустановленном бандле (patch_js сначала
      заменяет InstallModels, затем fullscreen перекрывает вкладку).
    - **imagerouter.html — полноэкранный layout**: шапка в 2 строки
      (статус ключа + баланс + ссылки; ввод ключа компактно), тело —
      grid из 4 колонок с независимой прокруткой: Каталог моделей /
      Генерация и правка / Апскейлинг / (3D-аналитика + тест-генерация).
      Цены теперь ВО ВСЕХ списках (main-список раньше был без цен; это
      админ-страница — решение 08.09 «без цен» касалось только
      пользовательских описаний в инъекции). Новое в строках: бейдж «Q»
      (поддержка quality), tooltip строки = полный дайджест (цены
      min/avg/max, входы, quality, размеры), кнопки «Все/Снять»
      (массовое добавление/снятие по текущему поиску; при state.main
      =null сначала разворачивается в весь каталог). Все id сохранены
      (test_threed.py проверяет `id="threedsec"`).
    - E2E 19.09 (Playwright MCP): вкладка без левого списка, iframe
      1880×1000 на весь экран, 4 колонки по ~496px, 144 модели каталога,
      91 апскейлер, 120 VLM, баланс/ключ в шапке, чекбокс/↑↓/Все/Снять
      работают, обрезки нет (scrollWidth==clientWidth). Скриншот
      docs/model-manager-fullscreen.png. Тесты: test_threed.py,
      test_main_models.py, test_upscale_cloud.py — OK.
    - **Артефакты**: `data/ifc/3D_facade_{20260919-173634,20260919-174856}.ifc`
      + превью; скриншоты `docs/3d-design-facade-{modal,result}.png`;
      тесты `tests/test_threed.py` (12 функций). Фаза 3 (интерьер) —
      план отдельным документом.

40. **3D Design (фаза 3): сценарий «Интерьер»** (19.09, ветка `3d`; план
    `docs/superpowers/plans/2026-09-19-3d-design-phase3-interior.md`,
    7 задач; все три сценария спеки закрыты).
    - **Конвейер** — плитка «Интерьер» активна (заглушек больше нет),
      placeholder по 3 сценариям (карта `{plan, facade, interior}` с
      фолбэком на plan). `POST /api/v1/threed/generate`
    {scenario:"interior"} → VLM по `SYSTEM_INTERIOR` (вход — 2D-план,
      НЕ фото интерьера; ЕДИНОЕ ПРАВИЛО: позиции в ПИКСЕЛЯХ, размеры/
      высоты в МЕТРАХ; опоры масштаба: дверь 0,9–1 м, кровать 2×1,6,
      унитаз 0,4; размерная линия точнее) → `validate_interior` (гейты:
      не-dict / нет outline+walls / пусто после чистки; дефолты scale
      0.01 м/px, wall_height 2.7; клампы толщин стен 0.05–0.6, проёмов,
      мебели; openings валидируются по ОЧИЩЕННОМУ списку стен; имя
      комнаты только str, иначе «Комната N»; типы комнат/мебели по
      whitelist → other) → `build_interior`: плита IfcSlab
      CONCEPTUAL_FLOOR по outline, стены IfcWall CONCEPTUAL_WALL
      сегментами с поворотом Rz и толщиной с плана, проёмы
      IfcBuildingElementProxy CONCEPTUAL_DOOR/WINDOW СКВОЗЬ стену
      (толщина+0.06 — урок фазы 2), комнаты IfcSpace CONCEPTUAL_ROOM с
      именами с плана + pset Room{Type}, мебель IfcFurnishingElement с
      ObjectType FURNITURE_<TYPE> и палитрой цветов типов (поворот
      −rot_deg — Y-флип инвертирует угол), pset InteriorModel на
      IfcBuilding, превью — чертёж плана в метрах.
    - **ГРАБЛИ**: (1) IfcSpace в ifcopenshell 0.8.5 НЕ имеет
      ContainedInStructure — `spatial.assign_container` на нём ПАДАЕТ;
      агрегировать в storey только `aggregate.assign_object`
      (IfcRelAggregates). (2) INTERIOR_SCALE_MAX=0.5 (не 0.1): мини-
      планы тестов масштаба ~0.25 м/px валидны. (3) Каталог tests/
      затеняется site-packages/tests — фокус-тесты запускать из
      каталога tests (`cd tests && python -c "import test_threed …"`).
    - **Артефакты**: `data/ifc/3D_interior_20260919-193010.ifc` + превью
      (живой smoke 20 с, warnings=[], VLM прочитал синтетический план
      идеально: 5 стен / 2 двери+окно / «Кухня»+«Спальня» / кровать+стол);
      скриншоты `docs/3d-design-interior-{modal,result}.png`; тесты
      `tests/test_threed.py` (16 функций). E2E без живой генерации —
      бюджет фазы (одна живая = smoke), автозагрузка через localStorage
      lastModel; UI-путь генерации идентичен фазе 2 (run3D не менялся).

41. **Компоновка левой панели: «Генерация» выше «Изображения», без Seed
    и бейджа базы; описание модели под селектором** (19.09; запрос
    пользователя по скриншоту с пометками: «поменять вкладки местами…
    убрать лишнюю кнопку (это из локальной разработки)… вкладку выбора
    модели сделать чуть более информативной… а ниже блок настроек
    (image), которые соответствуют выбранной модели»).
    - **Своп секций** (`patch_panel_layout()` в setup_imagerouter.py,
      App-бандл, 7 замен, идемпотентен по всем NEW-фрагментам): в
      ParametersPanelGenerate и ParametersPanelCanvas порядок
      [промпты, Изображение (Aoe/ise), Генерация (sM)] →
      [промпты, Генерация, Изображение]. «Лишняя кнопка "SD"» — бейдж
      базы фейковой модели в заголовке «Генерация»: бейджи были
      `[t.name, t.base]`, стали `[t.name]` (sdxl — техническое значение
      инъекции, пользователь видел его как «SD»). Строка Seed
      (`aw` = ParamSeed: Seed/Random/Shuffle Seed) убрана из аккордеонов
      «Изображение» обеих панелей (облачный API seed не использует), из
      бейджей аккордеона убрана пометка «Manual Seed» (селекторы lWe/
      mGe). Патч обязан идти ПОСЛЕ patch_left_panel — на свежем бандле
      список детей панелей ещё длинный и фрагментов свопа нет.
    - **Описание модели** (виджет `imagerouter/devbim_model_info.js` →
      `dist/devbim-model-info.js` + script в index.html —
      `deploy_model_info()`, бэкап `index.html.modelinfo-bak`, бандлы НЕ
      тронуты): под строкой «Модель» аккордеона «Генерация» блок 12px
      с description выбранной модели; ниже — секция «Изображение».
      Сервер (`imagerouter_router.py`, `_ir_fake_config` + новый
      `_ir_size_digest`): описание расширено «форматы PNG, JPEG, WebP» +
      дайджест размеров каталога (`parameters.size` → «до 3K
      (3136×1344)», при custom — «произвольный размер»); слово
      «редактирование» сохранено (гейт Generate-фолбэка), цены по-прежнему
      нет. ГРАБЛЯ: zod клиента выбрасывает description из стора
      (`st.params.model.description` === undefined) — виджет читает
      описание из `GET /api/v2/models/i/{key}` (тот же путь, что гейт
      фолбэка), ключ модели — из `__devbimPEStore` /
      `__devbimCanvasBridge`; кэш описаний, тик 500 мс (ремонты
      аккордеона React), для не-imagerouter моделей блок скрыт.
      Отладка: `window.__devbimModelInfo` ({key, text, clear}).
      E2E 19.09 (Playwright): порядок секций (Генерация top=357 выше
      Изображения), без «Seed»/«Shuffle» и без бейджа «sdxl», описание
      обновляется при смене модели (gpt-image-2.5-flare → до 2K
      (1536×1024); seedream-5.0-pro → до 3K (3136×1344) · произвольный
      размер); на «Холсте» — то же, «Опции Расширенные» целы; консоль
      чистая. Тесты: `tests/test_panel_layout.py`. Скриншот
      docs/panel-layout-model-info.png.

42. **3D Design (фаза 4): фиксы фасада + сценарий «Сцена» (camera
    mapping)** (19.09, ветка `3d`; план
    `docs/superpowers/plans/2026-09-19-3d-design-phase4-scene.md`, 11
    задач; спека `docs/superpowers/specs/2026-09-19-3d-design-scene-design.md`
    — база для «здания под новым углом» в ИИ-рендере, спека 3).
    - **Этап A — фиксы фасада** (жалобы 19.09 «балконы за габаритом» и
      «параллелепипед без окон»): (A1) `build_facade` ставит балконы по
      мировому центру `x_m − width/2` (x_m — «от левого края фасада», как
      в SYSTEM_FACADE; раньше cx=x_m — балконы висели справа от здания),
      превью рисует в том же фрейме; (A2) `validate_facade` клампит центр
      плиты в `[w_b/2, width−w_b/2]` с warning + NaN-гвард (дроп только
      при w_b>width — «Балконы сохраняем: VLM их увидела»; старый
      регресс-тест фазы 2 «x вне фасада → дроп» переписан под кламп);
      (A4) фасадная грань перенесена с IFC +Y на IFC **−Y** (окна
      cy=−d/2, балконы cy=−(d/2+d_b/2), двускатная крыша — выдавливание
      +Y от грани −Y): мировой трансформ вьювера (ifc −Y → world +Z,
      зонд 19.09) раньше разворачивал здание тылом к дефолтной камере
      fitModel. E2E: 23% тёмных пикселей остекления с дефолтного ракурса
      (порог 5%), скриншот docs/3d-facade-default-view.png.
    - **Этап B — сценарий «Сцена»**: плитка «🌇 Сцена» (четвёртая, все
      активны) + placeholder RU/EN. `POST /api/v1/threed/generate`
      {scenario:"scene"} → VLM по `SYSTEM_SCENE` (фото улицы: camera
      {azimuth_deg ±75 — 0 = фронтально с юга, «+» = восточнее;
      eye_height_m; dist_m}, 1–3 здания {main, x_m/y_m центра, фронт —
      сторона −Y, окна/балконы/цвета}, context деревья/машины/люди;
      якори масштаба: этаж 3 м, машина 4.5×1.8, дерево 5–8, человек
      1.7) → `validate_scene` (гейт ValueError; повторный main — здание
      отбрасывается с warning; >3 зданий — срез с warning; клампы
      камеры/зданий/деревьев; битый контекст — тихий drop) →
      `build_scene`: тома-этажи, окна фронта (cy=−d/2, имя «Окно Гл
      Э…») + боковины главного упрощённой сеткой
      side_cols=clamp(round((d−2·margin)/шаг_фронта),1,6) с «бок» в
      имени (глухие боковины рендер не достраивает — вывод зонда №3),
      балконы, цоколи, gable-крыши, деревья (ствол-бокс + крона-бокс = 2
      proxy/дерево), машины 4.5×1.8×1.4 с rot вокруг Z, люди
      0.5×0.3×1.7, земля-плита по габариту сцены +4 м; pset CameraHint
      на IfcProject (AzimuthDeg/EyeHeightM/DistM) + SceneModel на
      IfcBuilding; превью — план сверху с маркером камеры и направлением
      (камера ЮЖНЕЕ главного, az>0 восточнее; фронт = −Y, как в 3D).
      Ответ роутера несёт `camHint` (камера из чистой сцены).
    - **Камера вьювера после генерации**: виджет пишет
      `localStorage["devbim:ifc:camHint"]` (JSON подсказки) рядом с
      lastModel; `ifcviewer.html` после загрузки модели зовёт
      `applyCamHint()` вместо fitModel (фронт главного = world +Z, глаз
      `box.min.y + eye_height_m`, дистанция `max(dist_m, diag·0.35)`,
      «+»азимут = вправо/восток); подсказка ОДНОРАЗОВАЯ (removeItem —
      повторная загрузка модели возвращает обычный fitModel). E2E: глаз
      камеры −1.55 = box.min.y+1.7 ровно; скриншоты
      docs/3d-design-scene-{modal,plan,view}.png.
    - **ГРАБЛИ**: (1) `_properties` с Python float пишет IfcReal —
      get_psets возвращает float, ассерты на int проходят через `==`;
      (2) qwen-image-edit НЕ годится под спеку 3 (вывод зонда 19.09:
      нужна edit-модель nano-banana-класса, перенос камеры и материалов
      в зоне ±20–30° от точки съёмки); (3) маркер камеры в превью-плане
      обязан стоять ЮЖНЕЕ главного здания (−dist·cos(az)), иначе рисуется
      на тылу — знак в первой версии плана был перепутан; (4) счётчик
      CONCEPTUAL_TREE = 2 прокси на дерево (ствол+крона); фронт-окна в
      тестах фильтруются отсутствием «бок» в имени; (5) задачи 6–7
      плана (сборщик и превью) обязаны ехать одним коммитом: тест
      сборщика требует файл превью, который рисует превью-функция
      задачи 7.
    - Артефакты: `data/ifc/3D_scene_20260920-001646.ifc` + превью
      (живой smoke ~$0.05–0.15: az −38°, глаз 1.7 м, 39 м, warnings=
      [кламп roof_height 0→0.5]); тесты `tests/test_threed.py`
      (18 функций).

43. **3D Design: фикс «слит не тот источник» (stale S3.image при
    исключении в canvasComposite)** (20.09, ветка `3d`; жалоба
    «генерация из холста даёт совсем другой дом — как будто уходит
    дефолтное сообщение»; план
    `docs/superpowers/plans/2026-09-20-3d-canvas-source-fix.md`).
    - **Диагностика** (systematic-debugging): (1) прямой пробник
      `data/probe/_vlm_probe.py` — `_call_vlm(SYSTEM_FACADE)` с фото
      особого дома (Blue House Frome) вернул сцену, ТОЧНО совпадающую с
      фото (walls #bdb18a, 2 этажа, 3 окна) → сервер и модель
      НЕ при чём; (2) E2E-репродукция `data/probe/_e2e_canvas_ref.py`
      (Playwright, программная укладка слоя через
      `stateApi.addRasterLayer` — путь devbim_text_tool.js) поймала POST
      `/api/v1/threed/generate`: байты image ПОБАЙТОВО равны старой
      ВЫБРАННОЙ В ГАЛЕРЕЕ картинке (`08521737-….png`), а не фото с
      холста.
    - **Корень**: `canvasComposite()` (devbim_topright_buttons.js) не был
      защищён от исключений; при существующем, но ОТОРВАННОМ от DOM /
      нулевом Konva-стейдже `stage.toCanvas({width:0,height:0})` кидает
      `InvalidStateError` (drawImage на canvas 0×0). Исключение обрывало
      `refresh3DSource()` на середине: превью успевало затереться
      (`img.src=''`), бейдж оставался «—», но `S3.image` НЕ
      сбрасывался — и «Generate» молча слал КАРТИНКУ ПРОШЛОГО открытия
      модалки (обычно фолбэк-галерейную). Парный путь: открытие модалки
      на вкладке без менеджера канваса → composite null → тихий фолбэк
      `viewerImage()` (бейдж «Галерея» — замысел, но со stale
      превращался в ловушку).
    - **Фикс** (`imagerouter/devbim_topright_buttons.js`): всё тело
      `canvasComposite()` в try/catch → любой сбой = null; гвард
      `width()/height() > 0`; `refresh3DSource()` ставит
      `S3.image = null` ДО попытки композита и переживает любой сбой.
      Инвариант: превью-бейдж-POST всегда из одного `S3.image`,
      скрытых отправок больше нет. Деплой: `setup_imagerouter.py` (файл
      переписывается при каждом запуске); пользователю после фикса —
      Ctrl+F5 (script с defer кэшируется).
    - **Диагностика роутера** (`threed/threed_router.py`): дамп
      `data/ifc/_threed_last.json` дополнен `image {bytes, sha1, w, h}`
      (что РЕАЛЬНО ушло в VLM — sha1 ПОСЛЕ `_prepare_png`, т.е. картинки
      как её видела модель; сравнивать с файлами галереи/холста) и
      `vlm_head` (голова сырого ответа VLM, 300 символов). Деплой:
      `setup_threed.py`.
    - **Проверка**: E2E до фикса — POST(128037 байт) == gallery-файл,
      != фото холста (400683 байта), превью ПУСТОЕ; после фикса —
      POST == превью (170738 симв. dataURL), бейдж честный «Галерея»,
      генерация завершена; `tests/test_threed.py` — ALL OK; живая
      генерация прошла с новым дампом (scenario=plan по галерейному
      плану — VLM корректно прочитала именно её).
    - **ГРАБЛИ/заметки**: (1) в свежем профиле браузера (тесты) панель
      канваса dockview НЕ аттачится к DOM (dv-react-part оторван, стейдж
      0×0) — канвас-композит невозможен, теперь деградация честная
      («Галерея»/«—»); у пользователей с сохранённой раскладкой канвас
      монтируется нормально. (2) Фронт отправляет ровно то, что в
      превью модалки — при жалобах «не тот дом» смотреть бейдж
  Холст/Галерея и `_threed_last.json.image.sha1`. (3) Пробники
  оставить: `_vlm_probe.py` (живой VLM-тест картинки),
  `_e2e_canvas_ref.py` (репродукция источника).

44. **3D Design: VLM-верификация собранной модели (самопроверка, пилот
    паттерна MCP4IFC get_ifc_scene_overview)** (20.09, ветка `3d`; спека
    `docs/superpowers/specs/2026-09-20-3d-vlm-verify-design.md`, план
    `docs/superpowers/plans/2026-09-20-3d-vlm-verify.md`; источник идеи —
    Show2Instruct/ifc-bonsai-mcp, MIT: их get_ifc_scene_overview отдаёт LLM
    JSON-обзор модели для самопроверки).
    - **Конвейер**: после build_* — `threed_verify.scene_overview` (что
      ЗАДУМАНО: метры/счётчики из валидированной сцены, без пикселей) +
      `built_overview` (что РЕАЛЬНО в IFC: повторное чтение файла,
      подсчёт продуктов по ObjectType CONCEPTUAL_*/SITE_*/FURNITURE_*) →
      второй запрос той же VLM-модели с ИСХОДНОЙ картинкой и обзором
      (SYSTEM_VERIFY: ok=false только за реальные расхождения — этажность,
      сетка окон, тип крыши; глубина/±20%/цвета — терпи) → вердикт
      {"ok": bool, "issues": [до 8×160 симв]} → `res["verify"] =
      {overview, verdict}` + дамп `_threed_last.json.verify`.
    - **Инвариант**: верификация НИКОГДА не роняет генерацию — любой сбой
      (сеть/не-JSON/ok не bool) → verdict {"ok": None, "error": ...}.
      Выключатель: env `THREED_VERIFY` (0/false/no/off; по умолчанию ВКЛ)
      — вторая VLM-генерация = вторая трата (~$0.03–0.10 сверх анализа).
    - **Фронт**: done-тост получает суффикс « · ✓ VLM» / « · ⚠ issues»;
      ok=null — молча (диагностика только в дампе).
    - **Файлы**: `threed/threed_verify.py` (новый; деплой setup_threed.py
      добавлен в план копирования), `threed/threed_router.py`
      (_verify_enabled + блок после build), виджет
      `imagerouter/devbim_topright_buttons.js`; тесты
      `tests/test_threed_verify.py` (5 функций) + test_threed.py на
      уровне модуля ставит THREED_VERIFY=0 (моки считают вызовы — второй
      запрос ломал ассерт ретрая).
    - **Живой smoke** (vlm_test_house.png, facade, 26.6 с на два запроса):
      верификатор ПОЙМАЛ реальные ошибки первого прохода — «сетка окон
      1×3, на фото 2 ряда», «крыша gable, на фото вальмовая с башенкой»,
      «нет dormer»; built-подсчёт совпал со сценой (STOREY=2, WINDOW=4,
      PLINTH=1, ROOF=1). Пилот окупился на первом же прогоне.
    - **E2E полный круг** `tests/_e2e_3d_roundtrip.py` (20.09, по запросу
      «вход картинка → выход картинка из вьювера → сравни»): вход
      data/probe/vlm_test_house.png → живая генерация POST /generate (или
      `--ifc <имя>` — повторное использование готовой модели без траты) →
      Playwright (/ifcviewer.html, lastModel [+camHint для scene],
      `__ifc.capture()`) → пиксельный гейт + судья-VLM (та же модель, ДВЕ
      картинки в одном запросе, SYSTEM_JUDGE: score 0-100/match/issues,
      massing-упрощения терпимы). Артефакты: data/ifc/_roundtrip_view.png +
      _roundtrip_last.json (история score). Живой прогон: content 45.7%,
      score 35 (дважды стабильно) — судья режет баллы за фичи ВНЕ схемы
      фасада (вальмовая крыша с башенкой, dormer-окна, арочные окна,
      портал входа), это ограничения схемы, не конвейера; жёсткий пол
      score=25 («совсем не то здание»), пиксельный гейт — отклонение от
      ДОМИНАНТНОГО цвета фона (фон вьювера чёрный — проверка «не белый»
      из п.38 давала бессмысленные 100%).
    - **ГРАБЛИ**: (1) в venv есть сторонний пакет `tests`
      (site-packages/tests/__init__.py) — он ПЕРЕКРЫВАЕТ нашу папку tests
      как namespace-пакет: `from tests.test_threed import ...` НЕ работает,
      сэмплы в тестах грузить importlib'ом по пути файла. (2) skip-матрица
      окон в сцене фасада — паттерн НА ЭТАЖ (1×cols), а не на все этажи:
      в обзоре skipped_cells=1, а построено окон storeys×(cols−skip).
      (3) Тост вердикта заменяет предыдущий тост (одиночный слот) —
      issues видны в done-тосте, полный вердикт в _threed_last.json.
      (4) E2E импортирует задеплоенный роутер как `routers.threed` (файл
      threed_router.py деплоится под именем threed.py). (5) Низкий gable
      (1.5 м на 8 м здании, конёк вдоль глубины) с дефолтного fitModel
      читается судьёй как «плоская крыша» — вопрос ракурса, не геометрии
      (CONCEPTUAL_ROOF=1 в IFC есть); если судья занижает — крутить камеру
      на боковой фасад до orthoFacade.

45. **3D Design (фаза 5): «Фасад v2» — язык деталей + петля
    самокоррекции** (20.09, ветка `3d`; спека
    `docs/superpowers/specs/2026-09-20-3d-facade-v2-parts-loop-design.md`,
    план `docs/superpowers/plans/2026-09-20-3d-facade-v2-parts-loop.md`,
    6 задач).
    - **Схема v2** (`threed/threed_scenarios.py`: SYSTEM_FACADE +
      validate_facade; все новые поля опциональны — старые сцены v1
      проходят неизменно): `roof` flat/gable/hip/mansard,
      `windows.shape` rect/arched (профиль с полудугой, 10 точек),
      `dormers` (≤12, floor кламп 2..storeys), `chimneys` (≤6,
      коробка 0.6×0.6), `entrance` porch/portico, `towers` (≤4,
      тело box/цилиндр по этажам + крыша cone/pyramid/flat —
      тестовому дому нужна круглая, cylinder вошёл сразу) и
      **custom_parts** — грамматика примитивов box/prism(по профилю
      3..32 точки)/cylinder/cone, ≤60 шт, pos от центра фасада,
      rot_deg вокруг Z, цвет по палитре/своим #rrggbb.
    - **Геометрия** (`threed/threed_build.py`): hip/mansard-крыши,
      конусы, пирамиды, цилиндры — выпуклая оболочка точек через
      `scipy.spatial.ConvexHull` → `IfcPolygonalFaceSet`
      (IfcBuildingElementProxy, один меш = один продукт, НЕ
      сегментируем). ТРУБА обязана выходить НАД КОНЬКОМ скатной
      крыши: от своего этажа через все вышележащие до конька
      (+ roof_height) + 1.2 м. Дормер = коробка на фронте + панель
      остекления (как окна, −0.46 от грани). Новые ObjectType:
      CONCEPTUAL_DORMER/TOWER/CHIMNEY/ENTRANCE/CUSTOM — built_overview
      п.44 подхватил сам. Превью дорисовывает силуэты деталей
      (dormer/башни/трубы/вход) линиями.
    - **Петля самокоррекции** (`threed/threed_router.py`,
      `_generate_impl`; только facade): после сборки+verify — при
      СТРОГОМ `verdict.ok is False` с непустыми issues (ok=None/пустые
      issues итерацию НЕ запускают — платный повтор только ради
      конкретных коррекций) повторный анализ с блоком
      «CORRECTIONS from QA verification» → validate → build → verify.
      Победитель: rank=(ok=True, ответивший verify бьёт молчаливый ok=None,
      меньше issues), при равенстве —
      последняя попытка. Файлы попыток ≥2 — суффикс `_rN`
      (не перезаписывают друг друга), ПРОИГРАВШИЕ (IFC+превью)
      удаляются — в data/ifc остаётся только победитель. Сбой попытки
      ≥2 или verify не роняет генерацию (выход на лучшего). Ответ
      несёт `verify.iterations`, дамп `_threed_last.json` — полную
      `verify.history` (scene_summary/warnings/verdict по итерациям).
      Env: **THREED_VERIFY_ITERS** (0..2, дефолт 1 = один повтор;
      0 — петлю выключить) поверх THREED_VERIFY п.44 (выключатель
      верификации вообще).
    - **Файлы/тесты**: деплой `setup_threed.py` (4 файла: threed.py,
      threed_scenarios.py, threed_build.py, threed_verify.py — теперь
      и verify-модуль в плане копирования). Тесты:
      `tests/test_threed.py` (19 функций), новый
      `tests/test_threed_facade_v2.py` (10: клампы/дропы v2, сэмпл
      «вилла», custom_parts, петля ветвящимися моками),
      `tests/test_threed_verify.py` (5, п.44). Стоимость: база 2
      VLM-вызова, худший случай 4 (~$0.2–0.3); живой прогон —
      4 вызова / 85 с.
    - **Живой roundtrip** (`tests/_e2e_3d_roundtrip.py`, vlm_test_house):
      **score 35 → 43**, match=false; iterations=2 — петля СРАБОТАЛА:
      итерация 1 дала окна 1×2, verify поймал «image shows 2 rows»,
      итерация 2 с CORRECTIONS → окна 2×2, ok=True, победила
      (`3D_facade_20260920-142416_r2.ifc`, iter-1 файлы вычищены).
      Built победителя: DORMER=2, TOWER=2, CHIMNEY=2, ENTRANCE=2,
      CUSTOM=7, WINDOW=10, ROOF=1 — всё, что анализ запросил, схема
      построила. Цель спеки 55-60 НЕ достигнута — разбор issues судьи:
      (а) «башня не та» — анализ выдал ДВЕ прямоугольные башни вместо
      одной центральной круглой (схема умеет round+cone — не запрошено);
      (б) «дормеры пропали» — построены на фронте (DORMER=2), но с
      дефолтного ракурса fitModel судья их не зачёл; (в) «окна
      приземистые» — FIT сжал h_m 2.6→1.4 при этаже 4.2 м,
      `shape:"arched"` не запрошен; (г) «вход без фронтона» — вход
      построен как porch (ENTRANCE=2: крыльцо+дверь); portico-колонн
      и навеса нет — судья по сути прав, это качество анализа. ВЫВОД
      пилота: узкое место — качество
      АНАЛИЗА VLM (позиции/форма деталей), не выразительность схемы;
      конвейер и петля работают как задумано.
    - **ГРАБЛИ**: (1) trimesh из спеки НЕ понадобился — scipy уже был
      в venv, новая зависимость не вводилась. (2) Грани hull'а обязаны
      быть plain int (`list(map(int, ...))`): numpy int64 валит
      ShapeBuilder ValueError'ом. (3) Тесты роутера из дерева тянут
      VENV-копии модулей — после правок threed/* сперва setup_threed.py
      (в test_threed_facade_v2.py для дерева есть изолятор `_router()`,
      импортирующий threed.threed_router). (4) Счётчики продуктов:
      башня = 2 (тело+крыша-меш), dormer-стекло = CONCEPTUAL_WINDOW
      (коробка = CONCEPTUAL_DORMER), portico = 4 ENTRANCE (2 колонны +
      навес + дверь) — не удивляться цифрам в built_overview. (5)
      skip-матрица окон — паттерн ЭТАЖА (rows×cols), не всего фасада
      (п.44, грабля 2 — остаётся актуальной). Деплой: setup_threed.py
      + рестарт; data/ifc/_threed_last.json.verify.history — первый
      инструмент разбора «что думала петля».

46. **3D Design (фаза 6): сцена — мебель + люди на высоте + петля всех
    сценариев** (20.09, ветка `3d`; план
    `docs/superpowers/plans/2026-09-20-3d-scene-furniture-people-loop.md`,
    5 задач; кейс-триггер: фото вида с балкона — «человека на балконе
    нет»; разбор дампа показал: референс ДОХОДИЛ, VLM людей видел, но
    схема scene не умела их поднять с земли, мебели не существовало).
    - **Схема** (`threed/threed_scenarios.py`: SYSTEM_SCENE +
      validate_scene): `context.people[].z_m` — базовая высота над
      землёй (0=стоит на земле; балкон/терраса/крыша = уровень плиты
      (floor-1)*floor_height); `context.furniture[]` —
      bench/chair/lounger/table/sofa/umbrella/planter/other с
      дефолтами размеров по типу (SCENE_FURNITURE_TYPES; имя НЕ
      конфликтует с интерьерным FURNITURE_TYPES из validate_interior —
      грабля первой итерации), w/d 0.1..8, h 0.05..3.5, rot ±180,
      x/y ±150, z 0..90. Правила промпта требуют перечислять КАЖДЫЙ
      предмет мебели (включая балконные) и ставить z_m плиты.
    - **Сборка** (`threed/threed_build.py` build_scene): мебель —
      боксы CONCEPTUAL_FURNITURE (цвет furniture #a4703f, поворот
      вокруг Z как у машин), человек — низ фигуры на z_m; земля
      габаритится и по мебели; SceneModel + Furniture; превью
      дорисовывает мебель повёрнутыми прямоугольниками.
    - **Verify** (`threed/threed_verify.py`): scene_overview.context
      += furniture{type:count} и people_elevated (z_m>0.05);
      SYSTEM_VERIFY — context amounts теперь
      trees/cars/people/furniture.
    - **Петля самокоррекции — ВСЕ сценарии** (`threed/threed_router.py`
      _generate_impl): снят гейт «только facade» (max_iters общий);
      поведение/ранги/гейты те же (п.44-45): повтор только при строгом
      ok=False с непустыми issues. Раньше сцена теряла выпавшие VLM
      предметы без шанса на коррекцию.
    - **Файлы/тесты**: деплой setup_threed.py (4 файла без изменений
      плана копирования). `tests/test_threed.py` (20 функций:
      сэмпл сцены + человек на балконе z=3.1 + мебель, валидатор,
      сборка CONCEPTUAL_FURNITURE=3, SceneModel.Furniture,
      scene_overview мебели), `tests/test_threed_verify.py` (6:
      +test_generate_impl_scene_loop — петля сцены ok=False→
      CORRECTIONS→ok=True, победитель _r2).
    - **Живой прогон** (фото вида с балкона, 21:00,
      `data/ifc/3D_scene_20260920-210054.ifc`): итерация 1 сразу
      ok=True; built: PERSON=1 z=12.0, FURNITURE=3 (chair+table+
      other) z=12.0 — КРЕСЛО И ЧЕЛОВЕК НА БАЛКОНЕ ВЕРХНЕГО ЭТАЖА,
      overview: people_elevated=1, furniture chair/table/other.
      Verify больше НЕ пишет «Furniture: built none».
    - **ГРАБЛИ**: (1) test_threed.py на импорте ставит THREED_VERIFY=0
      («ретро-тесты без второй VLM-генерации») — тесты verify/петли
      живут в test_threed_verify.py (THREED_VERIFY=1); тест петли,
      положенный в test_threed.py, «не видит» ветку verify. (2) CLI-прогон
      _generate_impl пишет в `~/invokeai/ifc` (get_config().root_path без
      серверного конфига) — результат копируй в data/ifc руками. (3)
      Тесты роутера из дерева тянут VENV-копии threed-модулей (п.45
      грабля 3) — после правок threed/* сперва setup_threed.py.
    - **Задача 6 (камера на фокус сцены)**: живый кейс 21:08 — модель
      ПРАВИЛЬНАЯ (человек z=9.0 + кресло/столик на балконе 4 этажа
      главного здания), но пользователь «не видит человека и балкона»:
      applyCamHint отъезжал на max(dist_m, 0.35×диагонали) — сцена ~100 м
      → камера на 44 м, человек 1.7 м = пиксели. Фикс: роутер при
      people/furniture с z_m>0 кладёт в camHint.focus их центроид
      (IFC-метры); applyCamHint (ifc/ifcviewer.html) при focus наводится
      на БАЛКОН: view-координаты = IFC (x, z, -y) — маппинг проверен
      playwright-скриншотом, дистанция clamp(hint.dist_m, 6..60), глаз
      max(eye_height, focus_z+4) — сверху-под-углом плита раскрывается
      и дворовые деревья не перекрывают (при глазе focus_z+1.2 дерево
      перекрывало — подняли до +4). E2E (camHint живой генерации 21:08
      → reload → скриншот): балкон+человек+мебель в кадре крупно,
      ничего не перекрывает. Без focus — прежнее поведение (центр
      сцены). Тест: camHint.focus в test_generate_impl_scene.
    - **Задача 6b (камера «улетает» под землю)**: кейс 21.09 — сцена без
      elevated-объектов (нет focus) → старая ветка applyCamHint ставила
      глаз на `box.min.y + eye_height`. А web-ifc ИНОГДА дорисовывает из
      чистого IFC пару «мусорных» мешей ПОД землёй (у 3D_scene_20260921:
      три бокса на view-y -5.6..-2.2; двойная верификация ifcopenshell —
      в файле геометрии ниже -0.25 НЕТ; глубже в тайл-стример @thatopen
      не копали) → bbox.min.y = -4.85 → глаз -3.2 под землёй → «камера
      улетела». Фикс: `groundY = max(box.min.y, 0)` — глаз groundY+h,
      target.y подрезан `min(c.y, groundY+h+(box.max.y-groundY)*0.6)`;
      focus-ветка не задета (глаз всегда fz+4). Проверено в браузере обе
      ветки: без focus — глаз 1.7 м, вид двора с уровня глаз; с focus —
      прежний вид на балкон. ГРАБЛЯ: при живой проверке вьювера после
      рестарта — браузер может отдать КЭШ старой страницы: открывать
      /ifcviewer.html?<timestamp> (пользователю: Ctrl+F5 достаточно).

47. **Типы референсов для архитекторов + Weight в промте** (21.09, спека
    `docs/superpowers/specs/2026-09-21-reference-types-design.md`, скриншоты
    `docs/reference-block-*.png` — пометки пользователя, что убрать).
    Блок «Reference Image» в левой панели переработан под облачный пайплайн:
    - **Убраны настройки локальной разработки**: CLIP Vision Model
      (ViT-H/G/L) и Begin/End % — из карточки референса
      (RefImageSettingsContent, App-бандл; в ГРАФЕ дефолты остаются:
      clipVisionModel ViT-H обязателен — билдер ip_adapter для sdxl
      ассертит «ViT-H или ViT-G», beginEndStepPct [0,1]). Селектор
      несущей модели «ImageRouter (референс)» оставлен — без модели
      клиент выбрасывает референс из графа (п.7).
    - **«Режим» (Mode: Style and Composition / Style (Simple) / …) →
      «Тип референса»**: Основной / Дополнительный / 3D-ракурс / Окружение
      / Люди / Атмосфера / Предметы интерьера / Детали фасада / Генплан.
      Значение пишется в ШТАТНОЕ поле `method` узла ip_adapter — тип и
      вес путешествуют в граф без кастомных полей. Веса по умолчанию:
      main 1 / extra 0.2 / view3d 2 / остальные 0.5 (заданы пользователем
      для первых трёх); ВЫБОР ТИПА выставляет Weight на дефолт типа
      (патч колбэка в карточке; слайдер 0–2, фактическое значение уходит
      в граф). Новые референсы создаются типом «Основной» (дефолт
      конфига rS в index-бандле: method:"full"→"main"); zod-enum method
      (2 вхождения: схема узла + валидатор KJ) расширен девятью
      значениями. Региональные настройки (RegionalGuidanceIPAdapter
      SettingsContent) не тронуты — контроль-слои скрыты с 19.08.
    - **Промт** (`imagerouter_router.py`): реестр IR_REF_TYPES (лейбл /
      дефолтный вес / мини-промт — ПО-РУССКИ, как прежние
      PROMPT_REFERENCE_*_NOTE; они удалены). Промт = [пользовательский +
      Template — клиент объединяет сам, шаблон вставляет промт в
      {prompt} либо дописывает после] + блок референсов
      `_reference_prompt_block`: с исходником начинается «Первое
      изображение — исходник для редактирования», далее по каждому
      референсу «Изображение N — <тип> (вес W): <мини-промт>.» —
      нумерация = массив image[] edits-запроса; вес из ip_adapter.weight
      (0..2), отсутствует → дефолт типа; НЕИЗВЕСТНЫЙ тип (старые сессии
      full/style, референс от Generate-фолбэка) → «референс (общий):
      учитывай стиль и содержание этой картинки» (вес всё равно из узла).
      3D-ракурс несёт «…выстави всё строго как на схеме… формы и цвета
      самой схемы не используй, это только схема» — под сцены из
      IFC-вьювера (рамка кадра → «Use as Reference Image»).
    - **Диагностика**: `_extract_ir_info` собирает `ref_details`
      [{image,type,weight}] параллельно `references` (дедупликация —
      парами); лог enqueue `types=[main:1 view3d:2]`; метаданные
      результата `ref_details`.
    - **Деплой**: `patch_reference_types()` в setup_imagerouter.py (4
      замены App-бандл + 2 index-бандл, идемпотентно, маркер
      value:"view3d"). Тест: `tests/test_reference_types.py` (якоря в
      живых бандлах, патч на синтетике, ref_details, блок промта,
      согласованность весов JS↔Python). Живая проверка 21.09 (Playwright):
      карточка без CLIP Vision/Begin-End, 9 типов в селекторе, смена типа
      двигает Weight (3D-ракурс→2, Дополнительный→0.2); генерация
      nano-banana-2 с референсом: в графе ip_adapter {method:view3d,
      weight:2}, лог types=[view3d:2], HTTP 200, в метаданных картинки
      ref_details. Скриншот `docs/reference-types-card.png`. Ошибки
      консоли «Problem rehydrating/persisting state» — redux-persist,
      существовали ДО патча (логи .playwright-mcp от 18-20.09).

48. **Английский интерфейс + сокрытие провайдера** (21.09, вечер; запрос
    пользователя: «в интерфейсе не пиши ImageRouter — это секрет, куда я
    отправляю; можно нейтрально "отправить на генерацию"; интерфейс на
    английском, локализация — отдельным этапом»). Изменения:
    - **Роутер** (`imagerouter_router.py`): описания фейк-моделей на
      английском без провайдера — main: "Cloud image generation · ✏️
      editing · formats PNG, JPEG, WebP · up to 3K (…) · custom size",
      ip-adapter-фейк переименован «ImageRouter (референс)» → «Reference»,
      tile-ControlNet → «Tile ControlNet», апскейл → "Cloud image
      upscaling". ГРАБЛЯ: слово-гейт Generate-фолбэка теперь "editing"
      (было «редактирование») — меняется ОДНОВРЕМЕННО в описании (сервер) и
      в JS-гейте (миграция ниже); рассинхрон ломает фолбэк молча.
      Тикер прогресса: "Generating · модель · i/N · Xs" / "Upscaling · …"
      (было «ImageRouter · …»). ВСЕ пользовательские _IRClientError —
      английские нейтральные ("Generation failed: …", "No generation
      model selected", "Failed to load reference image", ключ не задан →
      "Generation service is not configured… contact your administrator");
      DELETE моделей: "Cloud models are provided via API…". Промт-примечания
      (маркер маски, блок референсов IR_REF_TYPES) — ОСТАЛИСЬ русскими:
      это инструкции МОДЕЛИ, не интерфейс (язык промтов на русском
      проверен живыми генерациями).
    - **Бандлы** (setup_imagerouter.py, миграции задеплоенного состояния
      идемпотентны повторным setup): селектор типов → "Reference Type" с
      Main/Additional/3D View/Environment/People/Atmosphere/Interior
      Items/Facade Details/Master Plan (JS_REF_METHOD_NEW_RU — источник
      миграции); гейт фолбэка → "editing" (JS_GEN_FALLBACK_V2_RU);
      пункт меню → "Model Manager" (children:"Менеджер моделей" → EN);
      панель Upscaling v3 — Width/Height/Quality/Upscale Mode/Output
      Format (JS_UP_SLIDER_V2_RU → v3, КБ-формат en-US "KB").
    - **Виджеты**: devbim-admin.js — диалог пароля по-английски
      (Administrator sign-in / Password / Cancel / Sign in / Checking…;
      ответ сервера admin-auth 401 → "Wrong password");
      prompt_enhancer.py — ошибки нейтральные английские (пустой промт →
      "Enter a prompt or attach a reference image").
    - **НЕ тронуто (сознательно)**: админская страница Менеджера моделей
      imagerouter.html — русский + брендинг ImageRouter (пароль админа,
      это инструмент владельца); 3D/IFC/PDF-вьюверы (там свои тексты,
      отдельная задача); метаданные картинок (ключ imagerouter_model —
      техническая диагностика); лог сервера [imagerouter].
    - Тесты: test_panel_layout/test_main_models — EN-ассерты (editing,
      без ImageRouter в описании); test_upscale_cloud — имя Tile
      ControlNet; test_prompt_enhancer — гейт editing; test_reference_types
      — следует константам. Живая проверка в браузере: карточка
      Reference Type/Main/Weight, меню Settings → Model Manager, вкладка
      Upscaling (Upscale Mode/Output Format/Width/Height/Quality,
      описания "Cloud image upscaling"), описание модели в аккордеоне
      Generation — всё английское, упоминаний провайдера в UI нет.
      Скриншот docs/reference-type-en-card.png. После деплоя — F5.
49. **Полоска вкладок холста: без Launchpad, Canvas — градиент, вьюверы
    справа** (21.09, поздний вечер; запрос пользователя по скриншоту).
    Новый `devbim_canvas_tabs.js` → `dist/devbim-canvas-tabs.js` +
    `<script defer>` в index.html (деплой — `rebrand_devbim.py`,
    `deploy_canvas_tabs()`, идемпотентен, паттерн devbim-banner). Скрипт
    вставляет `<style>` и MutationObserver-ом навешивает классы на
    `.dv-tab` полоски dockview-холста по тексту заголовка
    (devbim-tab-launchpad/canvas/imageviewer/ifcviewer/pdfviewer):
    - «Launchpad» скрыт (display:none; панель остаётся в layout —
      недоступна только кнопка; на вкладке «Запрос» тот же dockview,
      там тоже скрыт — сознательно, welcome дублирует вкладку);
    - «Canvas» — градиентная кнопка 135° #38BDF8→#0EA5E9→#6366F1,
      радиус 8, свечение, белый полужирный текст; неактивная — приглушена
      (filter), hover ярче;
    - вьюверы прижаты вправо: `:has()`-селекторы растягивают
      `.dv-scrollable`/`.dv-tabs-container` на всю ширину заголовка
      группы (`.dv-void-container` схлопнут), первая из вьюверов
      (Image Viewer) получает margin-inline-start:auto → Canvas в левом
      углу центрального окна, Image/IFC/PDF — у правого края.
    ГРАБЛИ: подпись вкладки рендерится React-ом ПОЗЖЕ dom-элемента
    `.dv-tab` — помечать `data-devbim-tag` можно только когда класс
    реально найден, иначе текст ещё пуст и вкладка навсегда остаётся
    без класса (первая версия так баговала). Проверка после деплоя — F5,
    вкладка Canvas: 4 видимые вкладки, PDF Viewer ровно у правого края.
    Откат: убрать `<script …devbim-canvas-tabs.js>` из index.html.
50. **Уборка локальных элементов UI: иконки в поле промта + Denoising
    Strength** (21.09, поздний вечер; пометки пользователя на скриншотах).
    `patch_remove_local_ui()` в setup_imagerouter.py (App-бандл,
    идемпотентно, бэкап *.imagerouter-bak): (а) из ВСЕХ полей промта
    (positive — Generate/Canvas один компонент, negative, SDXL-стили из
    старых сессий) убрана вертикальная оверлей-группа иконок: «добавить
    триггер» {x} (локальные LoRA/embeddings скрыты), SDXL-concat (бейдж
    технической базы sdxl фейков), ⚡ предпросмотр динамических промтов,
    +/− отрицательного промта (облако его не использует); (б) из панели
    слоёв холста убрана строка Denoising Strength (рядом с Opacity) —
    edits-запрос силу денойза не принимает, в граф уходит дефолт 0.75 и
    роутер его игнорирует (как steps/cfg, п.9). Скрыт только UI: в граф
    параметры по-прежнему ходят, компоненты в бандле остаются
    определёнными (мёртвый код). Тесты: `tests/test_ui_cleanup.py`
    (OLD-фрагменты отсутствуют в живом бандле), `tests/_e2e_ui_cleanup.py`
    (живой UI по aria-меткам, скриншоты docs/ui-cleanup-*.png). Откат:
    *.imagerouter-bak + повторный setup.
51. **Workflows: облачные ноды + белый список + облачные шаблоны** (22.09;
    спека/план `docs/superpowers/specs|plans/2026-09-22-workflows-cloud-nodes*`).
    Четыре инвокации в `imagerouter/devbim_cloud_nodes.py` (деплой
    `deploy_cloud_nodes` в setup_imagerouter.py, паттерн п.22):
    `devbim_generate`/`devbim_edit` (батч до 10 промтов, поле prompt
    одиночное + prompts коллекция — одиночный выход ко входу-коллекции в
    6.2 НЕ подключается, NodeInputError), `devbim_vlm` (Ask AI, до 4 картинок,
    модель PROMPT_ENHANCER_MODEL), `devbim_upscale` (режим 2x/4x/WxH,
    хелперы _pick_upscale_size/_upscale_prompt роутера). Выполняются
    РЕАЛЬНОЙ очередью (перехват enqueue_batch их не видит: model — строка),
    результаты сами падают в галерею (context.images.save, GENERAL).
    Дропдауны моделей — Literal с tuple(...) на ИМПОРТЕ модуля из файлов
    выбора админа (data/imagerouter_main_models.json — edit фильтруется по
    входу-image каталога; imagerouter_upscale.json); файла нет —
    DEFAULT_MAIN_MODELS/DEFAULT_UPSCALE_MODELS роутера; смена списка —
    рестарт сервера. Allowlist: `patch_nodes_allowlist` (config-slice
    index-бандла, 24 типа — включая iterate/collect: вопреки разведке спеки
    они в 6.2 ЕСТЬ, graph.py:258/279; iterate обязателен для цепочки
    collection→single). Шаблоны: 5 JSON в `imagerouter/cloud_workflows/`,
    `deploy_cloud_workflows` убирает стоковые (бэкап *.orig), БД дочищает
    _sync_default_workflows на старте. ГРАБЛИ: (а) field label/notes
    воркфлоу вместо Note-нод — формат Note-ноды фронтендовской zod не
    верифицировать локально; (б) якорь nodesAllowlist ровно один в
    index-бандле — проверять node-import; (в) пустой список админа у нод
    даёт дефолты (Literal не бывает пустым); (г) модель-значение в шаблонах
    НЕ задаётся (value опущен) — дефолт Literal = первый элемент списка
    админа, при открытии шаблона подбирается автоматически. Тесты:
    tests/test_cloud_nodes.py; E2E tests/_e2e_cloud_nodes.py.

52. **3D Design: фоновые задачи генерации — фикс 524 за Cloudflare-туннелем**
    (24.09, ветка `interior`; спека/план `docs/superpowers/{specs,plans}/
    2026-09-24-3d-async-jobs*`). Триггер: живой интерьер 24.09 занял 147 с
    (анализ ~100 с + verify ~40 с), Cloudflare-туннель рвёт ответы длиннее
    ~100 с → «HTTP 524» в модалке, при этом бэкенд УСПЕШНО дописывал IFC
    (модель «пропадала» — UI узнавал имя файла только из ответа POST).
    Лимит CF бесплатный, не настраивается; конвейер с петлёй самопроверки
    законно занимает 2–6 мин. Решение — job-API: `POST /api/v1/threed/
    generate` теперь мгновенно отвечает `{jobId, status:"queued"}`
    (быстрые отказы — битая dataURL — остаются синхронным 422), генерация
    крутится в daemon-потоке (`_run_job`: `Semaphore(1)` — одна VLM-
    генерация одновременно, остальные job'ы стоят в queued), `GET
    /api/v1/threed/jobs/{id}` → `{jobId, status, stage, scenario,
    elapsed_s[, result|error]}`; result = прежнее тело generate ({name,
    warnings[, camHint][, verify]}), error = прежний текст 422-detail.
    Этапы: `_generate_impl(..., progress=None)` зовёт progress
    ("analysis" перед VLM → "build" перед build_* → "verify" перед
    самопроверкой). Job store в памяти: `_jobs` + lock, последние
    JOBS_MAX=20, готовые старше JOBS_TTL_S=1800 чистятся при создании
    новой; рестарт сервера очередь обнуляет (IFC-артефакты переживают).
    Фронт `imagerouter/devbim_topright_buttons.js` (run3D): POST →
    jobId → поллинг 2,5 с со статус-строкой «⏳ N s · этап» (RU/EN:
    stageQueued/Analysis/Build/Verify, jobLost на 404 — «сервер
    перезапущен, модели во вкладке IFC»); ответ со старого бэка (есть
    name) по-прежнему принимается. ГРАБЛИ: (а) статус в ответе POST —
    константа "queued": поток мог перевести job в running ДО возврата
    response (гонка в тесте); (б) поллинг переживает закрытие модалки
    Esc — по done сам переключит вкладку IFC и тостнет; close3D чистит
    таймер/busy — finish3D идемпотентен; (в) после setup+рестарта
    вкладка браузера ОБЯЗАНА перезагрузиться (грабля п.23а). Тесты:
    tests/test_threed.py +4 (test_generate_job_flow / test_job_cleanup_
    ttl / test_get_job_404 / test_post_generate_shape — 23 функции).
    Смоук curl (бесплатно, без VLM): POST {scenario:"attic"} → jobId →
    поллинг отдаёт error «Сценарий … в разработке» (гейт внутри job),
    GET /jobs/nosuch → 404, битая dataURL → синхронный 422. E2E:
    модалка 4 сценария + консоль чистая (шум rehydrating — ядро).
    - **Учёт стоимости VLM** (24.09, вечер; запрос пользователя «не
    понимаю сколько денег уходит на планировку»): реальный `_call_vlm`
    пишет usage каждого вызова в `_usage_log` (`_record_usage`; моки
    тестов не пишут — обратная совместимость), этап тегируется
    `_usage_stage` (analysis/verify), стоимость — готовый `usage.cost`
    API или расчёт по тарифам каталога (`_call_cost_usd`: prompt/
    completion за токен + кэш-чтение; тарифы теперь лежат в
    `_vlm_list_cached` → GET /threed/model). Итог `_usage_summary()`
    (calls/tokens/cost_usd) попадает в результат (res["usage"] → тост
    «потрачено $X.XXXX» в finish3D виджета) и в дамп `_threed_last.json`
    (ключ usage). ГРАБЛИ: (а) тест test_model_choice_and_put оставляет
    выбор «x/vlm-2» в TMP — тесты с _generate_impl изолируют
    _model_store_path на несуществующий файл; (б) каталог недоступен →
    pricing {} → cost_usd нет, токены пишутся (деградация без падения).
    Тесты: test_usage_cost_and_record + test_widget_cost_toast (26
    функций). Баланс ImageRouter: GET /api/v1/imagerouter/credits
    (прокси /v1/credits) — 24.09 остаток $2.75; astra $10/$50 за 1M,
    sol $2/$10, luna $0.1/$0.5 → планировка ~$0.22/0.045/0.003.

53. **Фикс «генерация из канваса не видит фото с канваса — результат
    похож на референс»** (24.09, ветка `interior`; жалоба: канвас =
    скриншот 3D-интерьера из вьювера + референс реального интерьера,
    «накинь референс на мой 3д», а результат — картинка по референсу).
    - **Диагностика** (systematic-debugging, дамп `data/_ir_last_graph.json`
      + лог): картинка с канваса в запросе ЕСТЬ — edits JSON `image=[PNG
      clay-рендера, JPEG референса]`, HTTP 200; маска была ПОЛНОСТЬЮ
      белой (выделения нет → путь «правка всей картинки», без маркера).
      Пиксельно результат ближе к референсу (MAD 36 против 58). КОПИ-ТЕСТ
      на живом API (тот же вход, промт «верни изображение 1 без
      изменений»): модель вернула исходник (MAD 10.5/71.0) — канал
      доставки цел, виноват ПРОМТ. Корень: блок `_reference_prompt_block`
      не приказывал модели сохранять геометрию изображения 1, а заметка
      типа `extra` ссылалась на несуществующий «основной референс».
    - **Фикс** (`imagerouter_router.py`, чисто серверный — F5 не нужен):
      при has_init первая строка блока теперь «…сохрани его геометрию,
      ракурс, пропорции, расположение стен, проёмов и объектов СТРОГО без
      изменений — это основа сцены.», блок заканчивается гвардом
      «Референсы не копируй целиком и не меняй ракурс сцены: композиция
      и геометрия — строго с первого изображения.»; заметка `extra`
      переписана без «основного референса» («уточняй по ней детали,
      материалы и освещение, не перебивая остальные изображения»).
      Формулировки — из живой пробы-победителя (см. ниже), не из головы.
    - **Фикс-2, вшитые гварды окон и состава** (24.09, след живого прогона
      AI-палитры — джапанди-рендер `docs/3d-ai-palette-japandi-v2.png`,
      коммит e24b5a2; модель `3D_interior_20260924-180700.ifc`: 2 окна /
      4 двери / 23 мебели — обе окна в рендере удержаны): без прямого
      приказа редактирующие модели систематически клеят стекло НА
      сплошную стену («наклейка» вместо проёма). При has_init в блок
      теперь вшит абзац «ВАЖНО, ОКНА: … рисуй их сквозными: стекло
      ВНУТРИ проёма с рамой, за ним соседнее помещение; сплошную стену
      под стеклом не рисуй» (формулировка условная «если есть» —
      безопасна для кадров без окон), замыкающий гвард усилен «Ничего
      не добавляй, не убирай и не перемещай». Блок стал дописываться и
      БЕЗ референсов (исходник + текстовый промт стиля) — раньше гварды
      работали только при ip_adapter. Пользовательский промт теперь
      только про стиль. Деплой: setup_imagerouter.py + рестарт;
      тесты `tests/test_reference_types.py` (оконный гвард при
      исходнике / отсутствие без исходника / init-only без ролей) +
      main_models/upscale_cloud/panel_layout — OK.
    - **Проверка**: проба `data/probe/_probe_canvas_ref_edit.py`
      (copy|fix|user, ~$0.03/запуск): copy — модель видит канвас; fix —
      геометрия clay-рендера сохранена + материалы референса применены
      (вердикт VLM по скриншотам). Сквозной replay: POST точного дампа
      пользователя в enqueue_batch живого сервера после деплоя → HTTP
      200, `7c955d4a…png` — геометрия 3D-вида сохранена (две стены, два
      проёма, низкая камера), джапанди-материалы применены. Тесты:
      `tests/test_reference_types.py` (блок с has_init: приказ
      геометрии, гвард последней строкой, extra без «основного
      референса», без has_init гварда нет) + test_main_models /
      test_upscale_cloud / test_panel_layout — OK.
    - **ГРАБЛИ/заметки**: (а) MAD-метрика слепа для «материалы поверх
      геометрии» — фотореалистичный результат ВСЕГДА далёк от clay-рендера
      по пикселям; вердикт выносить по структуре сцены (VLM/глазами);
      (б) копи-тест — самый дешёвый способ отделить «канал доставки
      картинок» от «промт не удерживает модель»; (в) баланс на пробы
      24.09: ~$0.10 за 3 запроса (copy/fix/replay).

54. **Различимая палитра интерьера + режим «AI-палитра» во вьювере**
    (24.09, ветка `interior`; спека
    `docs/superpowers/specs/2026-09-24-interior-ai-palette-design.md`,
    план `docs/superpowers/plans/2026-09-24-interior-ai-palette.md`;
    мотивация: стены интерьера сливались в один цвет — ИИ-рендер по
    снимку не различал, где наружная стена, где перегородка, куда
    смотрит грань).
    - **Сборщик** (`threed/threed_build.py`): `INTERIOR_WALL_PALETTE`
      — тон ext/int × 4 сектора ориентации оси (X/45°/Y/135°, ось
      двунаправленная); `wall_palette_key(data, wall)` считает сектор
      по углу сегмента в метрах плана (Y-флип учтён); стиль стены
      `Wall{Ext|Int}{X|D45|Y|D135}`, имя «Стена 03 наружная С-Ю»
      (старый суффикс «нар.» ушёл); дверь — один стиль `Door`, окно —
      `Window` голубой #A8D4EA с `Transparency 0.55` (стиль — IfcSurfaceStyleRendering: web-ifc
      игнорирует Transparency на базовом IfcSurfaceStyleShading — окно рисовалось
      сплошным голубым); легенда
      `InteriorModel.ColorLegend` в pset + плашки-легенда в превью.
      Смежные перпендикулярные стены всегда в разных корзинах →
      всегда разного цвета.
    - **Вьювер** (`ifc/ifcviewer.html`, кнопка «🎨» в тулбаре):
      MeshBasicMaterial + onBeforeCompile — цвет грани по
      ГЕОМЕТРИЧЕСКОЙ нормали (dFdx/dFdy мировых координат, 6 корзин:
      оранж/жёлт/зелёный/голубой/белый/серый); меши-«оболочка»
      опознаются по hex материала из палитры сборщика (9 значений),
      наружные стены — тёмный вариант (×0.62), перегородки/пол —
      светлый; прозрачные (окна) и мебель/двери не перекрашиваются;
      чужие модели без совпадений красятся целиком светлым.
      Клиппинг-плоскости сечений копируются на подменённые материалы
      — сечения работают и в палитре. `aiEnsure` на update камеры
      (пересоздание мешей LOD), `aiApply` в loadIfc — палитра
      переживает смену модели; состояние в localStorage
      `devbim:ifc:aiPalette`, отладка
      `window.__ifc.palette.{enable,disable,state}`.
    - **Легенда в промт**: при снимке (📸/💾) к BIM-контексту в буфер
      дописывается `AI_PALETTE_LEGEND` (только когда палитра
      включена) — модель-рендер получает расшифровку цветов и приказ
      перерисовать поверхности реальными материалами с референсов,
      сохранив геометрию и направления граней.
    - **Проверка**: `tests/test_threed.py::test_interior_wall_palette`
      (разбор IFC через ifcopenshell: сектора, имена стилей, RGB по
      hex, Transparency 0.55, pset) — все функции OK;
      `tests/test_ifc_sections.py` (markup-ассерты + node --check +
      порядок объявления до слушателя камеры + деплой) — все OK.
      Живой E2E: модель загрузилась 2.4 с; `meshes:4` (3 группы стен
      + плита; двери/окна/мебель не тронуты by design); поворот
      камеры драгом палитру держит; сечение режет покрашенное; легенда
      едет в буфер только при включённой палитре (проверено
      перехватом clipboard); выключение возвращает исходные цвета.
      Скриншоты `docs/3d-ai-palette-{off,on,section,restored}.png`.
    - **ГРАБЛИ**: (а) TDZ — @thatopen СИНХРОННО стреляет camera-update
      во время `fragments.init()` (top-level await модуля): слушатель
      камеры, ссылающийся на `const aiPaletteState` из конца модуля,
      ронял всю инициализацию (`window.__ifc` не существовал, модель
      не грузилась, «модель не загружена» навсегда) — объявление
      обязано стоять ДО слушателя (регрессионный ассерт порядка в
      `test_ai_palette`); (б) диагональ-фикстура `[[0,0],[10,10]]` с
      учётом Y-флипа даёт сектор D135, а не D45 (формула и спека
      верны, ошибалась фикстура) — в тесте координаты
      `[[0,28],[10,18]]` (ЮЗ→СВ = +45°).
      (в) стили @thatopen докладываются на меши АСИНХРОННО после
      `fragments.core.update(true)` (и статуса «Модель загружена»):
      раннее включение палитры матчило hex-ы по плейсхолдерам →
      fallback красил всё светлым, а библиотека потом могла заменить
      материалы поверх подмены (устаревший aiOriginal вернул бы
      плейсхолдеры). Фикс: отложенный apply при загрузке (+1.5с),
      aiRestore возвращает оригинал ТОЛЬКО если подмена ещё действует,
      aiEnsure считает действующие подмены (не userData) и дожимает
      сходимость. Отдельный флейк web-ifc: ПЕРВЫЙ холодный парсинг
      иногда вообще теряет стили (меши по одному с рандомными
      приглушёнными цветами, у моделей DevBIM палитра уходит в
      fallback «чужой модели») — повторная загрузка файла чинит;
      это поведение библиотеки, не палитры.

55. **Настоящие проёмы в интерьерном сборщике** (24.09, ветка `interior`;
    спека `docs/superpowers/specs/2026-09-24-interior-real-openings-design.md`,
    план `docs/superpowers/plans/2026-09-24-interior-real-openings.md`;
    жалоба: «окна создались как IFCBUILDINGELEMENTPROXY, проёмы под них
    не создались, окна выехали за пределы помещения»).
    - **Диагностика** по `3D_interior_20260924-184114.ifc` (ifcopenshell:
      плейсменты+профили): проёмы были прокси-коробками НА сплошной стене
      (IfcOpeningElement/IfcRelVoidsElement не создавались — за стеклом
      не было дыры), и посадка не клампилась в сегмент: окно торчало за
      торец стены на 0,21 м, дверь стояла на «огрызке» 0,2 м под 90°
      (шире стены в 2,5 раза). Промах источника — VLM x_px/wall_idx;
      validate_scene клампит только размеры, не посадку.
    - **Фикс** (`threed/threed_build.py::build_interior`): проём в стене —
      `IfcOpeningElement` (box сквозь стену, толщина+0,02 для чистого
      булева) + `feature.add_feature` (IfcRelVoidsElement); заполнение —
      настоящий `IfcDoor`/`IfcWindow` (IfcRelFillsElement) тонким box
      ВНУТРИ проёма (глубина min(толщина−0,04; 0,08), без выступа за
      плоскости стены); стили Door/Window и ObjectType CONCEPTUAL_*
      сохранены. Кламп посадки: стена-носитель ≥ 0,6 м (огрызки проёмов
      не держат), ширина ≤ длина−0,1, центр — чтобы проём целиком в
      сегменте с полями 0,05 м, высота ≤ wall_height − sill − 0,05,
      ширина/высота < 0,3 → пропуск. Проёмы `wall_idx:"outline"` —
      прокси как раньше (у контура нет стены-носителя для булева).
      rbox: container=None / чужой color_key → без контейнера/стиля.
      `threed_verify._BUILT_CLASSES` += IfcDoor/IfcWindow (opening не
      считаем — это дыра, дубль с заполнением).
    - **Проверка**: `tests/test_threed.py` — test_build_interior и
      test_interior_wall_palette пересчитаны (в стенах IfcDoor/IfcWindow,
      на контуре дверь-прокси), новый `test_interior_real_openings`
      (voids/fills/openings счёт, кламп центра у торца: t=6,95 при
      стене 8 м, глубина стекла 0,08 < толщины 0,4, огрызок 0,32 м
      выбрасывает проём) — OK; test_threed_verify / test_threed_facade_v2
      — OK. Живой просмотр демо-модели во вьювере (2 окна, одно у торца):
      стены режутся насквозь (фон виден через проёмы), стекло внутри
      проёма, ничего не торчит, серых коробок- opening нет (web-ifc сам
      вычитает и не рисует их), дерево показывает IFCWINDOW×2/IFCDOOR —
      скриншот `docs/3d-interior-real-openings.png`. Деплой:
      setup_threed.py + рестарт.
    - **ГРАБЛИ**: (а) IfcOpeningElement НЕ должен попадать в spatial-
      контейнер — живёт только в IfcRelVoidsElement (rbox с
      container=None); (б) коробка проёма обязана выходить за плоскости
      стены (толщина+0,02) — заподлицо булево глитчит (тот же урок, что
      фаза 2 про совпадающие грани); (в) старые интерьерные IFC (до
      24.09 вечер) пересоберите — у них проёмы остаются прокси-наклейками.

56. **Tiered-конвейер 3D: контракт посадки кодом, per-stage модели,
    ремонт JSON, эскалация** (24.09, ветка `interior`; спека
    `docs/superpowers/specs/2026-09-24-threed-tiered-pipeline-design.md`,
    план `docs/superpowers/plans/2026-09-24-threed-tiered-pipeline.md`;
    мотивация: одна дорогая astra на всё (~$0.22/планировка), класс ошибок
    «посадка» ловился сборщиком молча после оплаты, а переход на дешёвую
    sol «в лоб» дал бы эхо-камеру — генератор и судья одна модель).
    - **Часть 1 — контракт посадки ДО сборки** (`threed/threed_scenarios.py`):
      константы п.55 вынесены в общие (`OPENING_MIN_HOST=0.6`,
      `OPENING_MARGIN=0.05`, `OPENING_MIN=0.3`; сборщик импортирует их —
      последний рубеж бит-в-бит, точные ассерты 6.95 в тестах п.55 живы).
      `validate_interior` теперь возвращает ТРИ корзины:
      `(scene, warnings, issues)` — нормализуемое кодом (кламп центра
      проёма в сегмент, ширина ≤ длина−0.1, высота ≤ wall_height−sill−0.05,
      перенос с огрызка <0.6 м на ближайшую стену ≥0.6 м в радиусе 1.5 м от
      его середины) правится на месте с warning'ами «посажен»; семантическое
      (мебель вне комнат — центр вне всех полигонов комнат/контура; комната
      не замкнута — покрытие контура стенами <60% при допуске
      thickness/2+0.15 м и шаге 0.3 м; проём без стены-носителя рядом —
      огрызок без подходящей стены, проём удаляется) — в `issues`.
      Проёмы `wall_idx:"outline"` не проверяются (нет носителя). Спека
      называла это «validate_scene (interior)» — реализовано в
      `validate_interior`: у уличной validate_scene проёмов нет.
    - **Части 2–3 — per-stage модели / ремонт / эскалация**
      (`threed/threed_router.py`): рульки `.env`
      `THREED_ANALYSIS/REPAIR/VERIFY/ESCALATION_MODEL` (дефолты
      astra/luna/astra/astra — id сверены с /v3/models; sol-повтор ремонта
      зашит). `THREED_MODEL` (env или file-store через PUT /api/v1/threed/
      model) — ПОЛНЫЙ override: все стадии на нём, эскалация выключена
      (analysis == escalation), поведение/стоимость как до п.56. **Ремонт**:
      только при непустых semantic issues (счастливый путь не платит),
      вход — сцена JSON + issues БЕЗ картинки (`_call_vlm` теперь принимает
      `image_url=None`), выход — strict-JSON; гейт = extract_json +
      повторная validate_interior; провал → ОДИН повтор на sol; не помогло
      → issues едут в CORRECTIONS следующей итерации. Сбой ремонта НЕ роняет
      попытку (warning, исходная сцена). **Эскалация**: после раунда
      (попытки 1..K, K=1+THREED_VERIFY_ITERS) при включённом verify и
      лучшем вердикте ok=False (или все ok=None) и analysis ≠ escalation →
      +1 финальная попытка `_r{K+1}` на эскалационной модели с полным
      накопленным CORRECTIONS (verify issues всех попыток + semantic issues
      контракта, пул с дедупом); verify попытки — всегда на своей модели
      (судья независим); пустой `THREED_ESCALATION_MODEL` = выключено.
      Победитель — по прежнему рейтингу, проигравшие файлы вычищены.
      Гейт повтора петли расширен: ok=False + (verify issues ИЛИ issues
      контракта). `_usage_stage`: analysis|repair|verify|escalation — в
      cost-дампах видно, какая стадия сколько съела; дамп `_threed_last.json`
      + ключ `stages` (4 модели), history-записи + `contract_issues`;
      GET /api/v1/threed/model + ключ `stages`. Прогресс-стадии фронта
      НЕ менялись (STAGE_KEYS в devbim_topright_buttons.js: ремонт/эскалация
      идут под «analysis», неизвестные ключи упали бы в «В очереди»).
    - **Проверка**: `tests/test_threed_tiered.py` (5, NEW: резолв stage-
      моделей/override/пустая эскалация; порядок analysis→repair→verify с
      image_url=None у ремонта и «ремонт не вызывается на чистой сцене»;
      гейт ремонта — мусор от luna → один повтор на sol → принят, оба
      кривые → issues в CORRECTIONS итерации 2; эскалация — раунд sol →
      _r3 на astra с полным пулом, verify всегда astra, проигравшие
      вычищены; отключение и полный override) + test_threed.py
      (test_validate_interior пересчитан под 3-tuple, новый
      test_interior_seating_contract — фикстуры кейсов п.55: окно за
      торцом → посажено с warning, огрызок → перенос/issue, мебель вне
      комнаты → issue, комната не замкнута → issue) — ALL OK;
      test_threed_verify / test_threed_facade_v2 — без правок, ALL OK
      (поведение при дефолтных настройках не изменилось: эскалация off,
      контракт на их фикстурах чист). Деплой setup_threed.py + рестарт;
      health-check: GET /api/v1/threed/model (с печенькой site-auth!) —
      200, `stages` {astra,luna,astra,astra}/default; /api/v1/ifc/list —
      200. A/B-приёмка дефолта analysis на sol (часть 4 спеки,
      `data/probe/_probe_threed_tier.py`) — ОТЛОЖЕНО до согласования
      пользователя; дефолт НЕ переключён.
    - **ГРАБЛИ**: (а) смена сигнатуры validate_interior (2→3-tuple)
      требует запуска setup_threed.py ДО test_threed.py — роутер дерева
      тянет VENV-копии сценариев (п.45-3), распаковка падает «cannot
      unpack»; новые tiered-тесты от этого свободны (изолятор `_router()`
      привязывает модули дерева). (б) Ремонт перезапускается в КАЖДОЙ
      попытке петли (анализ снова вернул битую сцену → снова issues →
      снова luna+sol) — это by design, в тесте гейта ожидается 2×2 вызова.
      (в) Стартовая валидация по каталогу — только analysis (+verify при
      включённом): валидировать все 4 стадии вверх нельзя, опечатка в
      чужой рульке (например THREED_REPAIR_MODEL при генплане) блокировала
      бы генерацию 422; ремонт/эскалация проверяются лениво, их сбой
      глушится гейтом ремонта / записью в history. (г) Health-check API
      без печеньки site-auth даёт 303 → /auth/login — печеньку собирайте
      `siteauth.site_auth._token(_site_password())` (COOKIE_NAME).
      Откат: убрать новые переменные из .env (перестают действовать),
      контракт посадки — чистая добавка до сборки (п.55 в сборщике
      остаётся), THREED_MODEL-override работает как раньше.
57. **Переход вьювер → канвас без маски, рамка 3:2 + fit** (25.09, ветка
    `interface`; жалоба: после «To Canvas» из вьюверов (IFC/PDF/Design
    Code — все через общий мост `window.__devbimIfc.toCanvas`)
    автоматически создавался слой «Маска перерисовки», а рамка канваса
    становилась «Free» с габаритами под пропорции снимка; нужно: маски НЕТ,
    рамка по умолчанию 3:2, картинка вписана в рамку).
    - **Корни**: (а) маску создавал сам мост V2 — он копировал кнопку
      «Редактировать» (`withInpaintMask:!0` + `tool.$tool.set("brush")`,
      п.13); (б) «Free» ставит экшен `bboxChangedFromCanvas` ВНУТРИ
      `sentImageToCanvas` — кладя снимок, тот ставит `bbox.rect` под
      пропорции картинки, а редьюсер при смене пропорций сбрасывает
      `aspectRatio.id` в `"Free"`. Никакой опции «оставить рамку» у
      `sentImageToCanvas` нет — ratio выставляется ПОСЛЕ укладки.
    - **Мост V3** (`setup_ifcviewer.py`, `JS_BRIDGE_V3`; миграции V1/V2 и
      ревизий V3 автозаменой при повторном запуске, идемпотентно):
      `withInpaintMask:!1`, кисть не трогаем; затем сырой экшен
      `{type:"canvas/bboxAspectRatioIdChanged",payload:{id:"3:2"}}` —
      СТРОКА типа стабильна между сборками (имя слайса canvas + ключ
      редьюсера), минифицированный action-крейтор (в этой сборке App —
      `r0e` = экспорт `mf` из index) использовать НЕ стали; редьюсер
      залочит 3:2 и пересчитает rect с той же площадью (кратно 8; 800×1000
      → bbox 1248×832). Затем слой вписывается последовательностью пункта
      «Fit to Bbox» меню слоя: `adapter.transformer.startTransform({silent:
      !0})` → `fitToBboxContain()` → `await applyTransform()` — applyTransform
      ЗАПЕКАЕТ вписанную картинку единственным image-объектом (800×1000 →
      666×832). generate-режим (`QCe`) — без изменений.
    - **ГРАБЛИ**: (а) fit нельзя звать, пока картинка не отрендерилась —
      адаптер слоя существует сразу, но `$pixelRect` трансформера 0×0,
      `fitToBboxContain` делит на `proxyRect.width()`=0 → scale=Infinity →
      applyTransform растеризует пустой прямоугольник (`replaceObjects:!0`)
      и СЛОЙ ТЕРЯЕТ объекты; мост ждёт (до 4 с) ненулевой
      `transformer.$pixelRect.get()` (ревизия 2, миграция `JS_V3_R1_WAIT_
      OLD`→`JS_V3_R2_WAIT_NEW`). (б) `$pixelRect` пересчитывается с
      ЗАДЕРЖКОЙ (~1 с после applyTransform) — в проверках источник истины
      объекты состояния (запечённый image w/h), не $pixelRect.
      (в) состояние канваса обёрнуто: `state.canvas.PRESENT` (хелпер
      `cs()` в мосту, см. п.16). (г) ошибка консоли «Problem
      rehydrating/persisting state» — преждесуществующая (старый
      persisted-стейт в профиле браузера), к мосту отношения не имеет.
    - Подсказки вьюверов обновлены (кнопки «To Canvas» IFC/PDF/Design
      Code + тосты): без обещаний маски, «3:2 frame». Нужна маска —
      виджет «Маска/Слой» сверху (п.16) добавляет слой руками.
    - **Проверка**: `tests/test_canvas_bridge_v3.py` (содержимое V3,
      миграции, node --check моста, тексты вьюверов) — ALL OK; живой E2E
      `tests/_e2e_bridge_v3.py` (Playwright, вход по SITE_PASSWORD, вкладка
      PDF держит `__devbimIfcCtx`, аплоад 800×1000 через
      /api/v1/images/upload, вызов моста): рамка 3:2 locked, rect
      1248×832=1.500, масок 0, слой 666×832 ≤ bbox, пропорции сохранены —
      E2E OK (скриншот `docs/bridge-v3-canvas.png`). Деплой:
      setup_ifcviewer.py (мост) + setup_pdfviewer.py/setup_designcode.py
      (тексты) + рестарт; парсинг App-бандла `node -e import(...)` —
      только рантайм «document is not defined».

58. **3D Design: детерминированные структурные проверки IFC** (25.09, ветка
    `3d_analysys`; спека
    `docs/superpowers/specs/2026-09-25-threed-structural-verify-design.md`).
    Дыра QA: вердикт п.44 — только VLM по счётчикам ObjectType; «тихий»
    слом сборки при правильных счётчиках не видел никто. Разведка MCP-
    сервисов (ifc-mcp/imants установлен в venv + зарегистрирован в ZCode
    воркспейсно, `.zcode/config.json`, сервер `ifcmcp`, stdio) показала
    класс ошибок на живом файле. Паттерны (не код): Daviidro/
    ifcopenshell-mcp `validate_ifc_model` (MIT), smartaec/ifcMCP
    `get_openings_on_wall` (Apache-2.0).
    - `threed_verify.structural_report(ifc_path)` — открывает готовый IFC,
      считает: проёмы без IfcRelVoidsElement (стены-носителя), проёмы без
      IfcRelFillsElement, IfcDoor/IfcWindow вне проёма, элементы без
      IfcRelContainedInSpatialStructure/IfcRelAggregates, безымянные
      продукты. IfcOpeningElement исключён (живёт в стене — by design);
      контейнер ЛЮБОГО уровня годится (дормеры/башни/цоколь фасада в
      building — валидный IFC; формулировка ifc-mcp «нет именно этажа =
      сирота» — НЕ наша). Фолбэк-прокси проёма (IfcBuildingElementProxy)
      проверкой door/window не задет. Миллисекунды, без VLM/зависимостей.
    - **Мягкий режим**: не влияет на вердикт/ранг/corr_pool (дефект
      сборщика — не материал CORRECTIONS для повторного АНАЛИЗА), считается
      ВСЕГДА (и при THREED_VERIFY=0), сбой -> `{"ok": null, "error"}`
      без влияния на генерацию.
    - Интеграция: `_run_attempt` -> `res_i["structural"]` (результат задачи
      + дамп `_threed_last.json` ключ `structural`), `_verify_attempt` ->
      `overview["structural"]`; `threed_verify.verify` при непустых issues
      добавляет в промпт блок «(C) machine-detected IFC build defects
      (deterministic ground truth)» — блоки (A)/(B) не тронуты.
    - **Проверка**: `tests/test_threed_verify.py` — 3 новых теста
      (здоровые interior+villa-v2: нули; сломанный файл: отрезаны
      Voids/Fills/Contained + стёрто имя — все счётчики ловят; блок (C)
      только при непустом structural) + роутерные ассерты (structural в
      res/overview/дампе, работает при THREED_VERIFY=0) — ALL OK;
      test_threed / test_threed_facade_v2 / test_threed_tiered — ALL OK.
      Деплой: setup_threed.py + рестарт; живая проверка — логин через гейт
      (POST /auth/login, кука) + GET /api/v1/threed/model.
    - ГРАБЛИ: (а) роутер дерева в тестах импортирует ЗАДЕПЛОЕННУЮ копию из
      venv (`invokeai.app.api.routers.threed_verify`) — новый символ без
      перезапуска setup_threed.py даёт AttributeError в тестах (уже было
      п.56, строка выше); (б) curl по API без куки гейта — пустой ответ/
      303, не «сервер лежит».

59. **«Редактировать» (Edit) в Image Viewer → холст: поведение V3** (26.09,
    ветка `3d_analysys`; продолжение п.57 — вьюверы IFC/PDF/Design Code
    перевели на V3, а переход из вьювера картинок остался нативным: слой
    «Маска перерисовки» + кисть + рамка «Free»). Кнопка «Редактировать» —
    хук `Ize` в App-бандле (компонент `ote`, экшн-бар просмотрщика):
    нативно `await _c({withInpaintMask:!0})` + `tool.$tool.set("brush")`.
    - Патч `patch_imageviewer_edit()` в `setup_ifcviewer.py`
      (`JS_EDIT_HOOK_OLD` → `JS_EDIT_HOOK_V3`, идемпотентно по точной
      строке): та же последовательность, что мост V3, но САМОСТОЯТЕЛЬНАЯ —
      store хук берёт сам (`Je()`), менеджер через `ru.get()` (`ru=De(null)`
      на верхнем уровне модуля, вызов в рантайме — TDZ нет), БЕЗ
      `__devbimIfcCtx` (кнопка доступна с любой вкладки, IFE/IFCV могут
      быть не смонтированы — мост при этом кидал бы «canvas context
      unavailable»). Порядок: focusPanel → `_c(withResize:!1,
      withInpaintMask:!1)` → экшен 3:2 → ожидание менеджера (до 2 с) и
      адаптера raster_layer с ненулевым `$pixelRect` (до 4 с) →
      `fitToBboxContain` + `applyTransform` → тост SENT_TO_CANVAS. Если
      менеджер не поднялся — fit МОЛЧА пропускается (картинка уже на
      холсте, тост честный); в отличие от моста, который кидает throw.
    - НЕ тронуты (сознательно): пункты «New Canvas From Image» в меню ⋮
      просмотрщика (4 варианта raster/control layer × resize,
      `withInpaintMask:!0`, хук `OU`) и дроп/аплоад на Launchpad (`Qte`) —
      это явные варианты с собственной семантикой, не «переход».
    - **Проверка**: `tests/test_canvas_bridge_v3.py` +3 теста (содержимое
      NEW/OLD, порядок focus→_c→3:2→fit, миграция+идемпотентность,
      node --check) — ВСЕ OK; смоук на стабах (полный async-путь,
      порядок вызовов focus,_c,dispatch,startTransform,fit,apply,toast,
      withInpaintMask=!1) — OK; test_ifc_sections / test_ifc_ai_render /
      test_mask_toggle — OK; повторный `setup_ifcviewer.py` — «уже V3,
      пропуск»; парсинг App-бандла `node -e import(...)` — только рантайм
      «document is not defined»; рестарт `launch/_restart_server.ps1`,
      сервер отвечает 303 (гейт). Живая проверка в браузере: открыть
      картинку во вьювере → «Редактировать» → холст: рамка 3:2 locked,
      слой вписан, масок 0, кисть не включена.

60. **Двухканальный ансамбль извлечения геометрии image→IFC (п.60)** (26.09,
    ветка `3d_analysys`; спека/план `docs/superpowers/2026-09-26-threed-
    geometry-ensemble*`; SDD Tasks 1–9 выполнены и отревьюены, финальное
    ревью ветки — Approved после фикс-батча 4798c6c. LIVE-хвост выполнен
    26.09 — итоговые метрики в «Живой хвост» ниже). Идея: «VLM выбирает
    семантику, код считает геометрию» — два независимых извлечения
    (A: параметрический JSON; B: grounding-боксы в пикселях / text-fallback
    на другой модели) → детерминированное compare → merge (согласованные
    float — среднее; спорные — ОДИН реферти-вызов; план/интерьер —
    компонентно, секции/комнаты целиком из A|B) → регуляризация по гейту
    согласия → прежние контракт/сборка/verify, где судья получает
    [оригинал, оверлей геометрии].
    - Модули (чистые: без invokeai.* вне try/except, без future-
      annotations): `threed/threed_ground.py` (IoU/normalize_boxes/
      validate_gt, probe_metrics/pick_model, SYSTEM_GROUND_*, конвертеры
      боксы→сцена facade/plan/interior — кластеры окон по центрам, якоря
      масштаба дверь 2.1 м/этаж 3 м/окно 1.5 м, МНК lsq_scale по parking
      2.5×5 + sport 17×34, стены интерьера = поглощение коллинеарных рёбер
      комнат + shapely-union outline, CONVERTERS), `threed/threed_ensemble.py`
      (compare/merge: фасад 7 полей — storeys Δ≥1, width 15%, floor_height
      10%, rows/cols Δ≥1, skip Δ≥2 клетки, entrance 0/1; plan 5 / interior 5;
      SYSTEM_REFEREE), `threed/threed_regular.py` (REGULAR_GATE=0.7, снап
      0.05 м, симметрия skip-строк ≤10%, RDP, orthogonalize — снап
      АБСОЛЮТНЫХ направлений + while-коллапс антипараллельных огрызков,
      снятие пересечений футпринтов shapely-difference, замыкание комнат
      buffer(0), кламп толщин 0.3–0.4 наружные / 0.1–0.15 перегородки).
    - Роутер: `_ensemble_pass` ПОСЛЕ валидаторов A, ДО контракта/ремонта;
      порядок стадий analysis → B → реферти (≤1) → регуляризация (гейт) →
      контракт/ремонт (interior) → сборка → verify[оригинал+оверлей].
      Бюджет THREED_MAX_CALLS_PER_ATTEMPT=6: счётчик в обёртке
      `_vlm_counted` (ВСЕ вызовы через неё; моки тестов заменяют _call_vlm
      целиком — счётчик в теле функции не считал бы), сброс в _run_attempt
      (эскалация = свой бюджет); при исчерпании пропускается verify
      (ok=None), НЕ анализ. Сбой любой части ансамбля — warning + работа
      с A. pset EnsembleAgreement в DevBIM (4 билдера), ключи
      dump/history/res["ensemble"], тег `ensemble` в _usage_stage (cost-
      дампы; фронт-стадии НЕ тронуты, JS не патчились).
    - env: THREED_ENSEMBLE (0/1, дефолт 1), THREED_ENSEMBLE_MODEL (дефолт
      DEFAULT_ENSEMBLE_MODEL="" → text-fallback на ремонт-модели; winner
      live-зонда впишется после прогона), THREED_REFEREE_MODEL (дефолт sol,
      полным override THREED_MODEL НЕ глушится — судья споров выше ярусом),
      THREED_MAX_CALLS_PER_ATTEMPT (6).
    - Оверлей verify (з.5): `render_overlay` (фасад — контур+сетка окон от
      pixel_hint бокса building прогона B, без B — фит 80% ширины по центру;
      план — полигоны секций; интерьер — стены + голубые точки проёмов);
      `facade_grid_boxes` — единый источник геометрии сетки и метрики
      «IoU оверлея по GT».
    - GT: фасад — ручная разметка (`data/probe/_gt_mark.py` — tkinter, или
      визуально с evidence `_gt_check.png`; 10 окон(вкл. белфри/нишу)+
      дверь+контур ДО НИЗА ДВЕРИ y2=460); plan/interior —
      детерминированный генератор `data/probe/_make_gt_images.py`
      (спортплощадка 68×136 px = 17×34 м — якорь МНК; перегенерация =
      точные боксы).
    - Грабли: (а) изолятор `_router()` в новых роутер-тестах ОБЯЗАТЕЛЕН
      (п.45-3/п.58а — связывает 6 модулей дерева в роутер дерева), деплой
      `setup_threed.py` ДО venv-импортирующих тестов; (б) ретро-тесты
      (test_threed/facade_v2/tiered/verify) гасят THREED_ENSEMBLE=0 НА
      ИМПОРТЕ — иначе моки _call_vlm ломаются лишним B-вызовом; (в) merge
      фасада: в disputed хранится нормализованный entrance (0,1), в сцену
      пишется ТОЛЬКО оригинал `_get(B,f)` (dict|None) — int ронял
      build_facade (Critical финального ревью); (г) orthogonalize: коллапс
      антипараллельных рёбер — while по накопленной сумме + откат секции к
      исходным точкам при невалидном полигоне (самопересечение роняло
      _metric_polygon); (д) ens_hint сбрасывается в начале _ensemble_pass
      (иначе устаревший bbox портил оверлей следующих попыток); (е)
      THREED_ENSEMBLE=0 выключает B/compare/merge/регуляризацию, НО
      оверлей-verify (2 картинки судье) и бюджет-гейты остаются — откат
      «в один клик» в смысле конвейера извлечения, не побайтово; (ж)
      ImageRouter отдаёт ошибки и с HTTP 200 (п.19) — статусу не верить;
      (з) `data/*` в gitignore — data/probe только через `git add -f`.
    - Тесты (после деплоя, ALL OK): test_threed_ground (9) /
      test_threed_ensemble (13) / test_threed_regular (8) / test_threed_ab
      (2) + ретро test_threed (28) / facade_v2 (11) / tiered (5) / verify
      (12); node-чек бандла — только рантайм-ошибка.
    - **Живой хвост — ВЫПОЛНЕН 26.09.2026 (кредиты пополнены; фактический
      расход ~$5.6 вместе с двумя пересериями после live-фиксов)**:
      1) baseline ДО любого рестарта: подтверждено дёшево ДО трат — порт
         9090 держал процесс со старта 12:29 (деплой venv 18:37), т.е.
         сервер в памяти pre-ensemble. 3 серии ×3 → merge
         `data/probe/_ab_baseline.json` (коммит 2ab4c4d на baseline-3d):
         facade median 38 (38/38/44), plan 90 (95/88/90), interior 96
         (96/96/95); structural 100%, contract_issues 0, ключа ensemble
         в дампах НЕТ (контроль пройден);
      2) live-зонд: WINNER `openai/gpt-6-sol`, mode=grounding (mean IoU
         0.788, recall 0.933, json_valid 1.0; astra 0.765 — кандидат-2;
         qwen3-vl 0.256/0.667 — провал) → вписан в спеку з.1b и
         `DEFAULT_ENSEMBLE_MODEL` (threed_router.py);
      3) рестарт + health (кука, /threed/model 200; первый вызов до 90 с —
         каталог VLM) + смоуки: facade 35/$0.27, plan 96/$0.076, interior
         96/$0.081; ensemble-ключ в дампе (mode/b_model/agree_rate),
         тег `ensemble` — в usage.calls дампа (в ir_server.log НЕ пишется,
         там только старт-баннер);
      4) первый A/B вскрыл ДВА конвертерных дефекта прогона B (тюнинг без
         отката архитектуры, все фиксы с регресс-тестами):
         - интерьер: union комнат с джиттерными боксами = MultiPolygon →
           `'MultiPolygon' object has no attribute 'exterior'` ронял ВЕСЬ
           прогон B (3/3 прогонов серии молча работали на A) → фикс:
           экстерьер крупнейшего полигона + снап координат комнат к
           кластерам (допуск 1.2% габарита) — общие рёбра совпадают,
           стены абсорбируются, outline цельный;
         - фасад: башенные/нишевые окна мешались в «главную сетку»
           (rows=3/cols=4/6 skip при истине 2×2) → фикс: фильтр окон
           <45% медианной площади + rows=ceil(полос/этажей) (схемная
           семантика «рядов В ЭТАЖЕ» — валидаторный FIT втискивает сетку
           в floor_height, старое margin_y съедало h_m до клампа 0.3) +
           кэп margin_y 35% этажа. Фасад 32 → 43;
         + диагностика: в ensemble-ключ дампа добавлены `disputed`
         (значения A/B) и `referee` (вердикты), в харнессе — ретрай
         судьи ×3 (ImageRouter флапает 503/upstream, иначе терялись
         оплаченные прогоны);
      5) ИТОГ A/B (серии ×3, судья gpt-6-astra; merge
         `data/probe/_ab_ensemble.json`): facade median **43** vs
         baseline 38 (Δ+5; таргет ≥51 не достигнут — якоря B на этом
         доме шумят: дверь с крыльцом −18% scale, контур с крышей
         завышает этаж; реферти корректно резолвит споры в A, поэтому
         agree_rate фасада честно низкий 0.429), plan **96** vs 90 (Δ+6 ✓,
         agree 1.0), interior **96** vs 96 (паритет — потолок судьи на
         синтетике: baseline уже 96/100, «baseline+5» недостижим),
         structural 100% у всех, contract_issues 0 у всех (сокращать
         нечего), cost ×baseline: 1.23×/1.44×/1.76× (≤2× ✓), бюджет ≤6
         вызовов 100%. Таблица — спека раздел 11 «Итог live-прогона»;
         candidates след. итерации: astra кандидат-2, REGULAR_GATE 0.4,
         якорь двери по верхней кромке. ОТКАТ НЕ ТРЕБУЕТСЯ: ансамбль
         включён по всем трём темам, фасад строго лучше baseline.
      Тесты после всех фиксов: ground 9 / ensemble 13 / regular 8 /
      ab 2 / ретро threed 28 / facade_v2 11 / tiered 5 / verify 12 —
      ALL OK (обновлены: rows-семантика в happy-path моке, скип-кейс,
      MultiPolygon-регрессия).
    - Откат: THREED_ENSEMBLE=0 одним ключом (грабля (е)); модули
      threed_ground/ensemble/regular остаются задеплоенными (не мешают).

61. **Многопользовательский режим SSO (devbim.com): вход через сайт, роли,
    личные воркспейсы** (01.10, ветка `feature/studio-sso`; спека
    `docs/superpowers/specs/2026-10-01-devbim-sso-workspaces-design.md`,
    план `docs/superpowers/plans/2026-10-01-devbim-sso-workspaces.md`;
    SDD-задачи 1–10). `STUDIO_AUTH_MODE=password|sso` — дефолт password,
    локальные компании (прежний режим SITE_PASSWORD) не тронуты. Sso:
    сайт devbim.com открывает студию в iframe `GET /auth/sso?t=<JWT HS256>`
    (подпись `STUDIO_JWT_SECRET`, окно exp ≤600 с, jti-анти-replay) →
    пользователь в overlay-БД `<root>/data/studio.sqlite` → кука
    `devbim_session` (HMAC, HttpOnly, SameSite=Lax, TTL
    `STUDIO_SESSION_TTL` 43200 c). Роли admin/user (email'ы devBIM →
    admin; вход по SITE_PASSWORD — всегда admin): админ-панель `/admin`
    (список, role-override, блокировка; экранирование email/имени против
    XSS), `GET /api/v1/studio/me`, `/auth/login` (фолбэк) и `/auth/logout`;
    роль/блокировка читаются из БД на каждом запросе — мгновенны.
    Изоляция: теги владения (upload/борды + ImageRouter-прокси: batch при
    enqueue, image после images.create), фильтрация списков
    картинок/бордов/очереди (`/api/v1/queue/{id}/list` и `list_all`),
    404 чужого, запись style_presets/workflows — 403 не-админу;
    destructive-гейты: DELETE images/uncategorized и пункты очереди
    (queue/{id}/i/{item}) — админу, board_images/batch — только свои
    борд+картинки; ошибка мутатора списков — fail-closed 502; IFC/PDF/3D —
    списки и доступ по владельцу (мидлварь
    инжектит `x-studio-user`), выбор модели 3D — админу; Model
    Manager/Настройки — гейт по роли (баннер: email пользователя + выход);
    сокеты — connect в комнату `user:<id>`, queue-события только
    владельцу (патч sockets.py).
    - Файлы: `siteauth/studio_store.py` (overlay-БД, env_or, JWT; деплой
      в `invokeai/app/api/routers/`), `siteauth/site_auth.py` (мидлварь),
      деплой — `setup_site_auth.py`; минт тестового JWT —
      `tools/mint_test_token.py` (секрет из .env/--secret, печатает токен
      и готовый URL `/auth/sso?t=`); Linux-лаунчер `launch/start_server.sh`
      (зеркало start_devbim.bat для хостинга devbim.com); ТЗ для
      разработчика сайта — `docs/INTEGRATION-devbim-com.md` (эндпоинт
      токена, iframe, DNS, postMessage('studio:expired')).
    - ГРАБЛИ: легаси-контент без владельца видит только админ (фильтр
      owner==uid, админ не фильтруется); списки очереди фильтруются по
      владельцу batch (`/api/v1/queue/{id}/list` и `list_all`), события —
      через комнаты `user:<id>`; нетегированные batch'и (локальные
      модели — вне облачного прокси) видны всем/уходят в общий эмит —
      допущение; в api_app.py SiteAuth добавляется ДО GZip (GZip
      снаружи — иначе _proxy_json видит gzip-байты и списки уходят
      нефильтрованными; порядок чинит сам setup_site_auth.py);
      CSP frame-ancestors (`STUDIO_FRAME_ANCESTORS`,
      дефолт devbim.com + localhost) — на другие домены студию не
      встраивать; при истёкшей сессии студия шлёт родителю
      `postMessage('studio:expired', '*')`.
    - Тесты: `tests/test_studio_store.py`, `tests/test_studio_auth.py`,
      `tests/test_studio_ownership.py`, `tests/test_studio_gzip.py`,
      `tests/test_studio_sockets.py` — plain asserts, печать OK.

```powershell
cd "C:\Users\Lenovo\Desktop\проект SOFT_2\Дизайн\InvokeAI\InvokeAI"
.\venv\Scripts\python.exe .\setup_imagerouter.py        # применить патчи
.\venv\Scripts\python.exe .\setup_ifcviewer.py          # вкладка IFC (идемпотентно)
.\venv\Scripts\python.exe .\setup_pdfviewer.py          # вкладка PDF (идемпотентно)
.\venv\Scripts\python.exe .\setup_designcode.py         # вкладка Design Code (идемпотентно)
.\venv\Scripts\python.exe .\setup_threed.py             # 3D Design (идемпотентно)
.\venv\Scripts\python.exe .\tests\test_designcode.py    # код доступа/URL + патчи
.\venv\Scripts\python.exe .\tests\test_threed.py        # 3D Design: сценарий/сборщик/роутер
.\venv\Scripts\python.exe .\tests\test_threed_verify.py # 3D Design: VLM-верификация + структурные проверки (п.58)
.\venv\Scripts\python.exe .\tests\test_threed_ground.py    # 3D Design: прогон B/IoU/конвертеры (п.60)
.\venv\Scripts\python.exe .\tests\test_threed_ensemble.py  # 3D Design: ансамбль compare/merge/роутер (п.60)
.\venv\Scripts\python.exe .\tests\test_threed_regular.py   # 3D Design: регуляризация снапы/симметрия/RDP (п.60)
.\venv\Scripts\python.exe .\tests\test_topright_buttons.py # кнопки Prompt Assistant / 3D Design
.\venv\Scripts\python.exe .\tests\test_mask_toggle.py   # тумблер Маска/Слой
.\venv\Scripts\python.exe .\tests\test_cut_tool.py      # ✂ вырезание по контуру
.\venv\Scripts\python.exe .\tests\test_text_tool.py    # T текстовый слой
.\venv\Scripts\python.exe .\tests\test_ifc_sections.py  # сечения + человек (IFC)
.\venv\Scripts\python.exe .\tests\test_ifc_ai_render.py # тень/контекст/камера (IFC)
.\venv\Scripts\python.exe .\tests\test_upscale_cloud.py # облачный апскейлинг
.\venv\Scripts\python.exe .\tests\test_panel_layout.py  # Генерация выше Изображения, без Seed, описание модели
.\venv\Scripts\python.exe .\tests\test_main_models.py   # выбор основных моделей
.\venv\Scripts\python.exe .\tests\test_reference_types.py # типы референсов + Weight в промте
# синтаксис module-скрипта вьювера после правок ifcviewer.html:
#   venv\Scripts\python.exe -c "import re,pathlib;s=pathlib.Path('ifc/ifcviewer.html').read_text(encoding='utf-8');pathlib.Path('ifc/_chk.mjs').write_text(re.search(r'<script type=\"module\">(.*?)</script>',s,re.S).group(1),encoding='utf-8')"
#   node --check ifc/_chk.mjs && del ifc\_chk.mjs
# проверить, что index-бандл парсится (после патчей навигации!):
node -e "import('file:///C:/Users/Lenovo/Desktop/проект SOFT_2/Дизайн/InvokeAI/InvokeAI/venv/Lib/site-packages/invokeai/frontend/web/dist/assets/index-BFW2ubNY.js').catch(e=>console.log(e.message))"
# перезапустить сервер (launch/_restart_server.ps1), затем:
# 1) GET http://127.0.0.1:9090/api/v2/models/ — модели imagerouter/ в списке
# 2) GET /api/v1/imagerouter/status — key_source:env; POST admin-auth — пароль
# 3) UI: Меню → Настройки → пароль → «Менеджер моделей» → вкладка ImageRouter
# 4) F5 — блокировка сбрасывается, вкладка models не восстанавливается
# 5) Canvas: выбрать edit-модель, фото+маску+промпт → Generate → галерея
# 6) IFC: GET /api/v1/ifc/list — модели; вкладка «IFC» в левой рейке:
#    открыть example.ifc/school.ifc с сервера, клик-выбор; «Сечения ▾»
#    (гориз./вертик. X/Z, скрытие плоскостей, слайдер/флип); «👤 ▾»
#    (постановка на перекрытие + «Вид от глаз» 1,7 м: WASD, V — вертикали);
#    «📷 ▾» (FOV, орто-фасад, рамка кадра); снимок — с контактной тенью,
#    BIM-контекст промта копируется в буфер; отладка — window.__ifc
#    внутри iframe (__ifc.person, __ifc.camera, __ifc.promptContext)
```

Откат интеграции: восстановить `*.imagerouter-bak`, удалить
`routers/imagerouter.py` и `dist/imagerouter.html` (детали в README).
