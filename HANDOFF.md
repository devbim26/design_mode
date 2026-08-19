# Хэндофф: DevBIM / InvokeAI + интеграция ImageRouter

Дата: 19.08.2026. Последний коммит: `12aafef` («ImageRouter: облачные модели
и редактирование прямо в Canvas»). Подробная пользовательская документация —
в `README.md` (разделы «ImageRouter» и «Диагностика»); здесь — рабочий
контекст для продолжения разработки.

## Проект в двух словах

Локальная установка InvokeAI 6.2.0 (CPU, порт 9090) с ребрендингом DevBIM
(`rebrand_devbim.py`) и интеграцией облачных моделей ImageRouter
(`setup_imagerouter.py`). Оба скрипта правят пакет в
`venv/Lib/site-packages/invokeai/` — после `pip install --force-reinstall
invokeai==6.2.0` их нужно запускать повторно (сначала ребрендинг, потом
имагерос). Запуск сервера: `start_devbim.bat` или напрямую (см. README).

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
- **queue_id из пути** = `path.split("/")[4]` (не [3]!). События сокетов
  шлём через `ApiDependencies.invoker.services.events.dispatch(...)` —
  работает из любого потока, комната = queue_id («default»).
- **API сервисов**: `images.get_pil_image(name)` (не get_pil),
  `ImageCategory.GENERAL` (не IMAGE), `ResourceOrigin.INTERNAL`.
- **Мидлварь** (`ImageRouterCanvasMiddleware`, чистый ASGI) регистрируется
  в `api_app.py` ДО `add_middleware(CORS/GZip)` — иначе видит gzip-ответ
  и не может дописать модели в JSON.
- **ImageRouter API**: `GET /v3/models` — публичный (без ключа);
  проверка ключа `POST /v1/auth/test`; баланс `GET /v1/credits`;
  генерация/правка `POST /v1/openai/images/{generations,edits}`
  (правка — multipart `image`, `mask`, `image[]`).

## Текущее состояние

- Сервер запущен (фоновой задачей) на `http://127.0.0.1:9090`, продакшн-URL.
- **API-ключ НЕ задан** — файл `data/imagerouter.json` удалялся при чистке
  тестовых артефактов; пользователь вводит ключ на вкладке ImageRouter.
- Каталог моделей кэшируется на сервере 10 мин (`_ir_models_cache`).
- Диагностический дамп последнего перехваченного графа:
  `data/_ir_last_graph.json` (удобно для разбора «что ушло»).

## Что НЕ сделано (кандидаты на продолжение)

- **Референсные изображения** (Reference Image / IP-ассеты) не передаются —
  API поддерживает несколько входных картинок (`image[]`).
- `quality` с канваса не используется (только size); steps/cfg/scheduler
  облачными моделями игнорируются.
- Несколько картинок (runs) генерируются последовательными вызовами —
  параметр `n` у API отсутствует.
- Удаление imagerouter-модели из списка моделей возвращает 400 с пояснением
  (это каталог API, не файлы) — можно сделать «скрытие» с состоянием.
- `_handle_canvas_generation` синхронный: кнопка Generate крутится весь
  запрос (до ~5 мин таймаута); при желании — фоновая генерация с событиями.

## Проверка после изменений

```powershell
cd "C:\Users\Lenovo\Desktop\проект SOFT_2\Дизайн\InvokeAI\InvokeAI"
.\venv\Scripts\python.exe .\setup_imagerouter.py        # применить патчи
.\venv\Scripts\python.exe .\imagerouter\_test_extract.py # тест извлечения графа
# перезапустить сервер, затем:
# 1) GET http://127.0.0.1:9090/api/v2/models/ — модели imagerouter/ в списке
# 2) вкладка ImageRouter в Model Manager, ключ, каталог
# 3) Canvas: выбрать edit-модель, фото+маска+промпт → Generate → галерея
```

Откат интеграции: восстановить `*.imagerouter-bak`, удалить
`routers/imagerouter.py` и `dist/imagerouter.html` (детали в README).
