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

## Проверка после изменений


```powershell
cd "C:\Users\Lenovo\Desktop\проект SOFT_2\Дизайн\InvokeAI\InvokeAI"
.\venv\Scripts\python.exe .\setup_imagerouter.py        # применить патчи
.\venv\Scripts\python.exe .\setup_ifcviewer.py          # вкладка IFC (идемпотентно)
.\venv\Scripts\python.exe .\setup_pdfviewer.py          # вкладка PDF (идемпотентно)
.\venv\Scripts\python.exe .\setup_designcode.py         # вкладка Design Code (идемпотентно)
.\venv\Scripts\python.exe .\tests\test_designcode.py    # код доступа/URL + патчи
.\venv\Scripts\python.exe .\tests\test_topright_buttons.py # кнопки Prompt Assistant / 3D Design
.\venv\Scripts\python.exe .\tests\test_mask_toggle.py   # тумблер Маска/Слой
.\venv\Scripts\python.exe .\tests\test_cut_tool.py      # ✂ вырезание по контуру
.\venv\Scripts\python.exe .\tests\test_text_tool.py    # T текстовый слой
.\venv\Scripts\python.exe .\tests\test_ifc_sections.py  # сечения + человек (IFC)
.\venv\Scripts\python.exe .\tests\test_ifc_ai_render.py # тень/контекст/камера (IFC)
.\venv\Scripts\python.exe .\tests\test_upscale_cloud.py # облачный апскейлинг
.\venv\Scripts\python.exe .\tests\test_main_models.py   # выбор основных моделей
# синтаксис module-скрипта вьювера после правок ifcviewer.html:
#   venv\Scripts\python.exe -c "import re,pathlib;s=pathlib.Path('ifc/ifcviewer.html').read_text(encoding='utf-8');pathlib.Path('ifc/_chk.mjs').write_text(re.search(r'<script type=\"module\">(.*?)</script>',s,re.S).group(1),encoding='utf-8')"
#   node --check ifc/_chk.mjs && del ifc\_chk.mjs
# проверить, что index-бандл парсится (после патчей навигации!):
node -e "import('file:///C:/Users/Lenovo/Desktop/проект SOFT_2/Дизайн/InvokeAI/InvokeAI/venv/Lib/site-packages/invokeai/frontend/web/dist/assets/index-BFW2ubNY.js').catch(e=>console.log(e.message))"
# перезапустить сервер (_restart_server.ps1), затем:
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
