# Дизайн: вкладка Workflows — облачные ноды вместо локальной диффузии

Дата: 2026-09-22. Запрос пользователя: в левой панели есть кнопка Workflows
(редактор нод и связей), но ноды рассчитаны на локальную разработку; оставить
только полезные ноды и адаптировать вкладку под облачных провайдеров.
Аудитория — архитекторы компаний-лицензиатов (решение пользователя).
Подход (утверждён): **A — свои облачные ноды + штатный nodesAllowlist**.

## Разведка (факты, на которых стоит дизайн)

- **Библиотека нод строится из openapi-схемы** (`GET /openapi.json` → эффект
  `getOpenAPISchema.matchFulfilled` в index-бандле): шаблоны нод собирает
  функция `VCt(schema, nodesAllowlist, nodesDenylist)` и кладёт в стор `iw`.
  Механизм allow/denylist — ШТАТНЫЙ, но в OSS ничем не наполняется
  (`nodesAllowlist:void 0` в config-slice). Правка одной строки бандла задаёт
  список — фильтрация действует на меню «Add Node», поиск и cmdk.
- **Шаблоны нод читает только редактор Workflows** (валидация «missing
  template» — при открытии workflow-файла). Билдеры графов Generate/Canvas/
  Upscaling строят узлы как плоские объекты и от шаблонов НЕ зависят —
  allowlist их не затрагивает. Перехват посредника (`_extract_ir_info`) тоже
  не затронут: он ищет узлы с ключами моделей `imagerouter/...` и spandrel.
- **Свои инвокации регистрируются пакетом автоматически** (паттерн п.22:
  `devbim_prompt_enhancer.py`, ноды `claude_expand_prompt` /
  `claude_analyze_image` ходят в облако из `invoke()` и выполняются через
  РЕАЛЬНУЮ очередь). ГРАБЛЯ из п.22: `from __future__ import annotations` в
  модуле инвокаций ВАЛИТ СЕРВЕР — запрещён.
- **Шаблоны библиотеки workflows сидируются из папки**
  `invokeai/app/services/workflow_records/default_workflows/` (14 стоковых
  JSON: SD/FLUX/CogView/ESRGAN) синхронизацией `_sync_default_workflows` при
  старте сервера — замена папки = замена библиотеки (паттерн пресетов стиля).
- В 6.2 НЕТ нод Collect/Iterate; батчи линейного UI живут в системе очереди.
  Для редактора батч делаем внутри ноды: список промтов → N вызовов API.

## Компоненты

Все изменения — в `setup_imagerouter.py` (идемпотентно, бэкапы
`*.imagerouter-bak` / `<file>.bak` по образцу). Новых секций в админ-UI не
нужно: списки моделей уже выбираются админом (п.27–28).

### 1. `imagerouter/devbim_cloud_nodes.py` → `invokeai/app/invocations/devbim_cloud_nodes.py`

Четыре инвокации, категория `cloud`, интерфейс английский, без упоминания
провайдера (п.48). Общие правила: `use_cache=False`; таймаут API 300 с;
ошибки — `ValueError` с английским нейтральным текстом (элемент очереди
честно падает, штатный тост); ключ/модель читаются лениво из задеплоенного
роутера (`_load_key` и пр. — единый источник .env).

| Нода (type) | Title | Поля | Выход |
|---|---|---|---|
| `devbim_generate` | Generate Image | `prompts: list[str]` (строка = промт, N строк = батч; кап **10**), `model` (дропдаун), `width`,`height` (1024, snap64), `output_format: Literal["png","jpeg","webp"]` | `images: list[ImageField]` |
| `devbim_edit` | Edit Image | `image: ImageField` (исходник), `references: list[ImageField]` (общий блок-промт референсов, п.47), `prompts: list[str]` (кап 10), `model` (только вход-image), `width`,`height` (0 = размер исходника, snap64), `output_format` | `images: list[ImageField]` |
| `devbim_vlm` | Ask AI | `images: list[ImageField]` (до 4), `question: str` | `StringOutput` |
| `devbim_upscale` | Upscale Image | `image: ImageField`, `model` (дропдаун апскейлеров), `mode: str` («2x»/«4x»/«WxH», валидация сервером, хелпер `_upscale_request_params`) | `image: ImageField` |

- **Модель-дропдауны** — `Literal` из файлов выбора админа, читаемых на
  ИМПОРТЕ модуля (старт сервера): `data/imagerouter_main_models.json` (для
  generate/edit, edit дополнительно фильтруется по входу-image из каталога),
  `data/imagerouter_upscale.json` (для upscale). Цепочка путей: env
  `INVOKEAI_ROOT` → `cwd/data` → `cwd`; файла нет — дефолтные константы
  роутера (`DEFAULT_*`). Первый элемент списка = дефолт ноды. Смена списка
  админом подхватывается ПЕРЕЗАПУСКом сервера (openapi-схема строится на
  старте); запуск ноды с устаревшей моделью → ошибка со списком доступных.
- **Результаты generate/edit сохраняют в галерею сами** внутри `invoke()`
  (`context.images.save`, как перехватчик канваса) — Save-нода не обязательна;
  имя/борда из полей не нужны в v1.
- **Generate** зовёт `generations` (без референсов — в v1 у Generate их нет,
  референсы — у Edit); **Edit** — `edits` JSON-массивом `image=[data-URL,...]`
  (исходник первым, референсы дальше, JPEG 1024/q85 — паттерн п.26/47),
  промт дополняется блоком референсов (роль «reference», вес 0.5).
- **Upscale** — edits-запрос с серверным промтом из режима (паттерн
  `_upscale_prompt`); проверка эха НЕ применяется (п.27).
- **Ask AI** — chat/completions модели PROMPT_ENHANCER_MODEL (переопределение
  .env, без новой админ-секции), MAX_IMAGES=4, ответ без санитайзинга промта
  (вопрос произвольный).

### 2. `patch_nodes_allowlist()` — index-бандл, config-slice

Одна замена: `nodesAllowlist:void 0,nodesDenylist:void 0` →
`nodesAllowlist:[<список>],nodesDenylist:void 0`. Идемпотентность — по
наличию массива (маркер `nodesAllowlist:["devbim_generate"`). Бэкап общий
`*.imagerouter-bak`. После патча — обязательный node-import чек.

**Белый список (~22):**

| Группа | Типы |
|---|---|
| cloud (новые) | `devbim_generate`, `devbim_edit`, `devbim_vlm`, `devbim_upscale` |
| AI (есть) | `claude_expand_prompt`, `claude_analyze_image` |
| промпты | `string`, `string_collection`, `dynamic_prompt`, `string_join`, `string_join_three`, `string_replace` |
| изображения | `image`, `image_collection`, `img_crop`, `img_resize`, `img_scale` |
| числа | `integer`, `float`, `rand_int`, `range` |
| сохранение | `save_image` |

Dynamic Prompt — локальная CPU-нода: раскрытие `{a|b}` работает без
wildcard-файлов; движок вариантов для архитектора («5 вариантов фасада»).
Note-нода редактора — чисто фронтендовая, allowlist её не касается.

### 3. Замена `default_workflows/` — облачные шаблоны

5 JSON-шаблонов (с Note-нодами, EN), заменяют 14 стоковых; серверная
`_sync_default_workflows` раздаёт их в БД при старте (как пресеты стилей):

1. **Cloud — Text to Image**: String Primitive → Generate Image.
2. **Cloud — Facade Variants**: Dynamic Prompt `{modern|classical} facade,
   {brick|plaster} walls, golden hour` → Generate Image.
3. **Cloud — Edit with References**: Image Primitive + Image Collection →
   Edit Image.
4. **Cloud — Analyze and Recreate**: Image Primitive → Ask AI
   («Describe this building as a detailed prompt») → prompts → Generate.
5. **Cloud — Generate and Upscale**: Generate Image → Upscale Image (2x).

Деплой: setup перезаписывает JSON-файлы в venv-папке (бэкап `.orig` рядом) и
удаляет стоковые. БД дочищает САМ СИНК СЕРВЕРА (проверено по коду
`workflow_records_sqlite.py`): default-воркфлои, которых нет в папке,
удаляются из `workflow_library` при старте («Deleting obsolete default
workflow»). Ограничения формата (валидатор): id шаблона обязан начинаться с
`default_`, `meta.category = "default"`.

## Выполнение и ошибки

- Invoke в редакторе → `enqueue_batch` → БЕЗ перехвата (в графе нет узлов с
  ключами `imagerouter/...`, поля model наших нод — строки, не ModelField) →
  реальная очередь → session processor исполняет узлы на CPU; облачные ноды
  делают API-вызовы. Нативная подсветка выполняемой ноды, нативный прогресс
  очереди; фейковый тикер не нужен.
- Отмена: между нодами — нативно; во время API-вызова запрос завершается,
  результат отбрасывается (задокументировать).
- Лимиты: ≤10 промтов на запуск ноды (ошибка «Batch limited to 10 images
  per run»); ≤4 референса/картинки Ask AI (лишние молча срезаются, как у
  Enhance Prompt).
- Ошибки — английские нейтральные («Generation failed: …», «Model X is not
  available. Available: …», «Generation service is not configured… contact
  your administrator»), формат `_IRClientError`-текстов п.48; в логе сервера
  — `[cloud-node] …` строки для диагностики.

## Риски и регрессии

- **КРИТИЧЕСКИЙ регрессионный тест**: после allowlist-патча Generate/Canvas/
  Upscaling работают как раньше (билдеры не читают шаблоны; покрыть живой
  генерацией канваса в E2E).
- Ранее сохранённые пользовательские workflow с локальными нодами → при
  открытии «missing template» (ожидаемо; у компаний локальных workflow нет).
- Смена списков админа → enum обновляется после рестарта сервера (подсказка
  в тексте секций Менеджера моделей, одна строка).
- Синтаксис патча бандлов — node-import чек после каждого патча (рутина
  HANDOFF).

## Тесты

- `tests/test_cloud_nodes.py`: деплой идемпотентен; enum строится из файла
  админа / дефолтов (запись во временную папку + патч путей); тела запросов
  generate/edit/upscale на моках requests; кап 10; snap64; EN-тексты ошибок;
  allowlist-патч: якорь в живом бандле + патч на синтетике; JSON шаблонов
  валидны (ноды из белого списка).
- E2E (Playwright): меню Add Node показывает ровно разрешённые ноды (нет
  denoise_latents/compel); открытие шаблона «Facade Variants» без ошибок;
  живая генерация 1–2 промта (~$0.01) — результат в галерее; РЕГРЕССИЯ:
  канвас-генерация с edit-моделью проходит через перехват как раньше;
  консоль чистая.
- Ручной чек-лист после деплоя: `setup_imagerouter.py` → node-import →
  `_restart_server.ps1` → F5 → вкладка Workflows.

## Откат

Восстановить `index-*.js.imagerouter-bak`, `default_workflows/*.orig`,
удалить `invokeai/app/invocations/devbim_cloud_nodes.py`, перезапустить
setup (патчи идемпотентны) и сервер.
