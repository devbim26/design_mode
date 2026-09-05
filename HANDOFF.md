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
имагерос → ifcviewer. Запуск сервера: `start_devbim.bat`, перезапуск из
агентской сессии — `_restart_server.ps1` (WMI, отсоединённо).

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
  WMI (`_ir_server_hidden.bat`, лог — `ir_server.log`). Запущенные из
  агентских сессий фоновые процессы убиваются вместе с сессией —
  используйте WMI/`start_devbim.bat`.
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

## Проверка после изменений

```powershell
cd "C:\Users\Lenovo\Desktop\проект SOFT_2\Дизайн\InvokeAI\InvokeAI"
.\venv\Scripts\python.exe .\setup_imagerouter.py        # применить патчи
.\venv\Scripts\python.exe .\setup_ifcviewer.py          # вкладка IFC (идемпотентно)
.\venv\Scripts\python.exe .\setup_pdfviewer.py          # вкладка PDF (идемпотентно)
.\venv\Scripts\python.exe .\tests\test_mask_toggle.py   # тумблер Маска/Слой
# проверить, что index-бандл парсится (после патчей навигации!):
node -e "import('file:///C:/Users/Lenovo/Desktop/проект SOFT_2/Дизайн/InvokeAI/InvokeAI/venv/Lib/site-packages/invokeai/frontend/web/dist/assets/index-BFW2ubNY.js').catch(e=>console.log(e.message))"
# перезапустить сервер (_restart_server.ps1), затем:
# 1) GET http://127.0.0.1:9090/api/v2/models/ — модели imagerouter/ в списке
# 2) GET /api/v1/imagerouter/status — key_source:env; POST admin-auth — пароль
# 3) UI: Меню → Настройки → пароль → «Менеджер моделей» → вкладка ImageRouter
# 4) F5 — блокировка сбрасывается, вкладка models не восстанавливается
# 5) Canvas: выбрать edit-модель, фото+маску+промпт → Generate → галерея
# 6) IFC: GET /api/v1/ifc/list — модели; вкладка «IFC» в левой рейке:
#    открыть example.ifc/school.ifc с сервера, клик-выбор, «Сечение»;
#    отладка — window.__ifc внутри iframe
```

Откат интеграции: восстановить `*.imagerouter-bak`, удалить
`routers/imagerouter.py` и `dist/imagerouter.html` (детали в README).
