# Спека: нижняя панель «To Canvas / To Assets» в Design Code и IFC (11.09.2026)

Запрос пользователя: во вьюере «дизайн код» и в IFC-вьюере добавить панель
(внизу окна) копирования на холст или в ассеты — как сделано в PDF-вьюере
(плавающая панель внизу по центру: «Fragment: W × H px» + «🖼 To Canvas» +
«💾 To Assets»).

## IFC-вьюер (полноценная вкладка)

Панель `#snapbar` («📸 To Canvas» + «💾 To Assets») существовала только в
embed-режиме (панель «IFC Viewer» на холсте). Изменения в `ifcviewer.html`:

- CSS: `#snapbar` видим в ОБОИХ режимах; селектор моделей — только embed
  (`body:not(.embed) #snapbar select{display:none}`), в вкладке он есть в шапке;
- обработчики `btn-snap`/`btn-snap-assets` подключаются до `if (EMBED)`
  (работают везде);
- `embedToast` больше не гасится вне embed-режима (у действий панели тост
  важнее футера);
- снимок — прежний `renderSnapshot()` (прозрачный фон, контактная тень,
  рамка кадра, кратно 64), BIM-контекст копируется в буфер.

Мост: `__devbimIfc.toCanvas` требует `window.__devbimIfcCtx`, который раньше
держали только IFCV (embed-панель) и PDFE/PDFV. Новое: **IFE v2** в
`setup_ifcviewer.py` — компонент вкладки IFC захватывает `Je()` в
`__devbimIfcCtx` при монтировании (как PDFE v2). Вкладки ifc/canvas не
активны одновременно — за глобаль не спорят. Уже пропатченные бандлы
мигрируются v1→v2 повторным запуском setup (идемпотентно).

## Design Code: панель захвата фрагмента

Сайт внешний (cross-origin): прочитать содержимое его iframe НЕЛЬЗЯ, единственный
способ снять картинку — Screen Capture API. Нижняя панель `#capbar` (видна,
когда сайт открыт; скрывается на гейте):

1. **Live-режим**: подсказка + «📷 Capture» → `getDisplayMedia({video:
   {displaySurface:"browser"}, preferCurrentTab:true, selfBrowserSurface:
   "include"})` — пикер браузера, предвыбрана текущая вкладка. Панель и тост
   на время захвата ПРЯЧУТСЯ (visibility:hidden), ждём 2 новых кадра
   (requestVideoFrameCallback, фолбэк таймеры) — чтобы не попасть в кадр.
2. **Кроп кадра по области сайта**: прямоугольник iframe `#site` в координатах
   верхнего окна (`rectInTop` — сумма смещений по цепочке same-origin iframe),
   масштаб кадра `videoWidth / top.innerWidth` (DPR-масштаб вкладки).
3. **«Заморозка»**: кадр рисуется в `#freezeCanvas` оверлея `#freeze`
   (затемнение, padding снизу под панель). Поверх — `#selLayer` с рамкой
   фрагмента как в PDF (drag, бейдж «W × H», затемнение вне рамки
   box-shadow-трюком; клик/маленькая рамка = вся область; Esc/«✕» — назад к
   живому сайту).
4. Панель в режиме фрагмента: «Fragment: W × H px» + «🖼 To Canvas» +
   «💾 To Assets» + «✕». Отправка — тот же путь, что IFC/PDF: кроп → PNG →
   `POST /api/v1/images/upload` (multipart; category=general для холста,
   user для ассетов) → «To Canvas» через общий мост `__devbimIfc.toCanvas`
   (подложка + слой «Маска перерисовки» + кисть), «To Assets» — вкладка
   «Assets» галереи.

Мост: **DCE v2** в `setup_designcode.py` — компонент вкладки Design Code
захватывает `Je()` в `__devbimIfcCtx` (как PDFE/IFE v2), миграция v1→v2
повторным запуском.

Грабли, учтённые дизайном:
- перекрёстный запрет читать cross-origin iframe — только getDisplayMedia;
- «NotAllowedError/AbortError» (отмена пикера) — тихий выход;
- поддержка: нет `getDisplayMedia` (старые браузеры) → тост об ошибке;
- Permissions-Policy `display-capture` (allowlist 'self') — iframe вьювера
  same-origin, разрешено без allow-атрибута;
- выбранная НЕ та поверхность (другое окно) — пользователь видит это в
  замороженном превью и отменяет;
- кадр без requestVideoFrameCallback — таймерный фолбэк (180 мс × 2,
  общий таймаут 3 с).

Тесты: `tests/test_ifc_sections.py` (+`test_snapbar_tab_mode`),
`tests/test_designcode.py` (панель + DCE v2 + node --check скрипта страницы).

Отладка: в iframe Design Code — кнопки панели; в IFC вкладке — snapbar;
мост — `window.__devbimIfc` / `window.__devbimIfcCtx` в консоли приложения.

## Дополнение (11.09, после живого теста пользователя)

Ошибка «Error: IFC: canvas context unavailable» при «To Canvas» из Design
Code: вкладка пользователя была открыта ДО деплоя — iframe вьюера свежий
(панель видна), а App-бандл старый (без DCE v2) → мост есть, контекста нет.
Разово лечится F5. Чтобы работал и без перезагрузки — фолбэк
`toCanvasViaBridge(dto)` во всех трёх вьюерах (design_code/pdf/ifc):

- быстрый путь: `__devbimIfcCtx` есть → обычный вызов моста;
- фолбэк: скрипт `__devbimSendToCanvas`, созданный `new parent.Function`
  (исполнение в КОНТЕКСТЕ ПРИЛОЖЕНИЯ — таймеры/промисы отсоединённого
  iframe умирают при переключении вкладки, первый вариант фолбэка с
  setInterval в iframe из-за этого терял вызов toCanvas), поллит
  `__devbimCanvasBridge.getManager()` (есть во всех бандлах с 05.09),
  при необходимости переключает вкладку (`__devbimSwitchTab('canvas')`),
  ставит `__devbimIfcCtx = manager.stateApi.store` и вызывает
  `__devbimIfc.toCanvas(dto,false)`.

E2E эмуляции старого бандла (`__devbimIfcCtx=null`, менеджер не поднят):
To Canvas сам переключил вкладку, положил растр+маску и включил кисть.
Заодно: ожидание кадра захвата ужесточено (2 кадра или videoWidth на
таймауте 5 с), `setup_pdfviewer.patch_index_bundle` переведён на
regex-проверку enum (идемпотентность после добавления designcode).

