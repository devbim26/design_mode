# Спека: Облачный апскейлинг (вкладка Upscaling через ImageRouter)

Дата: 2026-09-08. Ветка: `main`. Статус: к реализации (запрос пользователя
08.09: «настрой upscaling… сделай так, чтобы в меню пользователя выводились
модели, которые администратор выбрал для апскейлинга»).

## Цель

Вкладка «Upscaling» (unified upscale, InvokeAI 6.2) сейчас нерабочая: все
модели облачные, а вкладка требует локальные Tile ControlNet + spandrel
(ESRGAN) и локальный прогон Multi-Diffusion. Нужно:

1. Вкладка работает целиком через ImageRouter (как остальная генерация):
   пользователь загружает картинку, выбирает «Upscale Model» из списка,
   задаёт Scale (2/4/8)/Creativity/Structure → результат в галерее.
2. Дропдаун «Upscale Model» показывает ТОЛЬКО модели, выбранные
   администратором (галочка «доступно пользователям для апскейлинга»).
3. Администратор управляет списком в существующей админ-зоне
   (Менеджер моделей → вкладка ImageRouter), без правок JS-бандлов.

## Разведка (ключевые факты)

**1. Граф вкладки** (`sSe` в App-бандле): `spandrel_image_to_image_autoscale`
(поля `image_to_image_model` — модель апскейла, `image` — исходник, `scale`)
→ `unsharp_mask` → `i2l` → `tiled_multi_diffusion_denoise_latents` (main
sd-1/sdxl + `denoising_start` = f(creativity)) → `l2i` (board). Условный узел
`controlnet` с `control_model` = tile ControlNet, `control_weight` =
f(structure). Enqueue — общий `POST /api/v1/queue/{q}/enqueue_batch`.

**2. Требования UI** (баннер `_Ke` / автоселекты):
- main model с base `sd-1`/`sdxl` — фейки ImageRouter уже base=sdxl ✓;
- tile ControlNet: type=`controlnet`, base = base главной модели, «tile» в
  имени — автоселект эффектом в `_Ke` (ищет `name.toLowerCase().includes("tile")`);
- Upscale Model: дропдаун = все модели type=`spandrel_image_to_image`
  (предикат `RI`, хук `djt=Pn(RI)`), автоселект первого (`sIt`).
- Quick-action «Upscale» из контекстного меню картинки
  (`upscaling/postProcessingRequested`, `cSt`): adhoc-граф с ОДНИМ узлом
  `spandrel_image_to_image` (без main-модели в графе вовсе).

**3. Каталог ImageRouter** содержит специализированные апскейлеры со входом
image: `prunaai/P-Image-Upscale` (~$0.005, sizes 2048²/2896²),
`jingyunliang/swinir-2x` (~$0.0045), `philz1337x/clarity-2x` (~$0.0038),
`stabilityai/latent-2x` (~$0.0038), `csslc/ccsr-2x` (~$0.0083),
`bria/enhance` (~$0.04); всего с входом-image 89 моделей (вкл.
nano-banana-2, flux-kontext и пр. — тоже годятся как «апскейл + улучшение»).
Правки идут JSON-телом на `/v1/openai/images/edits` (паттерн из п.26 HANDOFF).

**4. Конфликт ключей**: одна и та же облачная модель (напр. nano-banana-2)
может быть и главной (type=main), и моделью апскейла (type=spandrel…), а
`GET /api/v2/models/i/{key}` отдаёт один конфиг на ключ → фейкам апскейла
нужен СВОЙ префикс ключей.

## Дизайн

### Модели (инъекция в `GET /api/v2/models/`)

- Новый префикс `imagerouter-upscale/<model_id>` — fake-конфиг
  type=`spandrel_image_to_image`, base=`any`, name = последний сегмент id,
  description = «Облачный апскейл ImageRouter · ~$Цена/img». Инъектируются
  ТОЛЬКО модели из админ-списка (см. ниже). Автоселект клиента выберет
  первый — алфавитный порядок списка админа задаёт модель по умолчанию.
- Фейковый tile-ControlNet `imagerouter/tile-controlnet`: type=`controlnet`,
  base=`sdxl`, name=`Tile ControlNet (ImageRouter)` — инъектируется всегда;
  снимает вторую половину предупреждения; в графе остаётся декорацией
  (граф не исполняется локально). Слои ControlNet в канвасе скрыты (п.15
  HANDOFF), других потребителей type=controlnet в UI нет.
- `GET /api/v2/models/i/{key}`: для префикса `imagerouter-upscale/` —
  spandrel-конфиг по id из каталога; `imagerouter/tile-controlnet` —
  спец-кейс (как ip-adapter-fake). DELETE для обоих — 400, как у остальных.

### Админ-список моделей

- Хранение: `<INVOKEAI_ROOT>/data/imagerouter_upscale.json` —
  `{"models": ["<id1>", ...]}` (per-company, как imagerouter.json).
- Дефолт при отсутствии файла (в коде): 6 специализированных апскейлеров
  (см. разведку §3, без bria/enhance — заметно дороже). Файл создаётся
  при первом сохранении из UI.
- Эндпоинты (в imagerouter_router): `GET /api/v1/imagerouter/upscale-models`
  → `{"models":[...]}` (+ признаки из каталога: цена, вход-image);
  `PUT` — сохранить список (валидация: модель есть в каталоге и принимает
  image на вход; невалидные id отсеиваются с предупреждением в ответе).

### Админ-UI (`imagerouter/imagerouter.html`, деплой уже есть в deploy_files)

Новая секция «Апскейлинг — модели для пользователей»: чекбокс-список моделей
каталога СО входом-image (поиск по названию, цена, пометка бесплатности),
кнопка «Сохранить» (PUT), индикатор текущего выбора. Список и каталог
кэшируются на странице; после сохранения — подсказка «пользователям нужно
обновить страницу (F5)».

### Перехват генерации (`imagerouter_router.py`)

- `_extract_ir_info` расширяется: узлы `spandrel_image_to_image(_autoscale)`
  → `is_upscale=True`, `upscale_model_key` (из `image_to_image_model.key`,
  префикс `imagerouter-upscale/`), `init_image` (из `image`), `scale`
  (поле узла; в adhoc-графе нет → 2), `board_id` — из `board`-поля ЛЮБОГО
  узла (l2i, не save_image). Проверка is_upscale идёт РАНЬШЕ обычной
  (в графе вкладки есть и main-модель с префиксом `imagerouter/`).
- `_handle_upscale_generation(queue_id, payload)` (по образцу canvas-обработчика;
  общие хелперы событий выносятся на уровень модуля):
  - прогресс/статус — те же события (`BatchEnqueued`, `InvocationStarted`,
    тикер `invocation_progress`, `completed/failed`, `_INFLIGHT`);
  - исходник — `services.images.get_pil_image(init_image)`;
  - размер: `_pick_upscale_size(mid, w, h, scale)` — цель `w*scale × h*scale`
    со снапом к 64; если у модели явный список sizes — ближайший ≥ цели
    (иначе максимальный); без списка — кап каждой стороны 2048;
  - промпт (EN, серверный): «Upscale ~Nx. Increase resolution, sharpen and
    refine fine details. Keep composition, geometry, colors and content
    exactly the same. Do not add, remove or alter objects.» + мягкие
    поправки по creativity/structure (denoising_start>0.2 → разрешение на
    творческие детали; control_weight>0.55 → жёсткое сохранение структуры);
  - вызов: JSON `POST /v1/openai/images/edits` `{"model", "prompt",
    "image":[data-URL PNG], "size"?}`;
  - `_is_echo` НЕ применяется (легитимный результат апскейлера похож на
    вход после даунскейла — ложное срабатывание);
  - сохранение в галерею с метаданными: `generation_mode:
    "imagerouter-upscale"`, `imagerouter_model`, `upscale_scale`,
    `source_image`, фактический размер результата;
  - runs — как у canvas (последовательные вызовы).
- Ошибки — через `_ir_error_body` (422, текст в тосте UI).

### Что НЕ трогаем

- JS-бандлы НЕ патчатся: вкладка Upscaling штатная, её селекторы читают
  общий `/api/v2/models/` (инъекция мидлварью). Слайдеры Structure/
  Creativity/Tile Size/Tile Overlap остаются как есть (работают как
  «регуляторы» промпта, tile-параметры игнорируются облаком).
- Обычная генерация канваса не меняется.

## Тесты (`tests/test_upscale_cloud.py`, plain asserts)

1. Инъекция: `_add_ir_models` добавляет spandrel-фейки только из
   админ-списка + tile-controlnet; ключи/типы/base верны.
2. `_extract_ir_info` на реалистичном графе вкладки (fixtures по дампу
   бандла): is_upscale, модель, scale, исходник, board; adhoc-граф
   quick-action (scale=2, без main).
3. `_pick_upscale_size`: явные sizes (ближайший ≥/максимальный), custom
   (snap64+кап 2048), отсутствие списка.
4. Промпт-билдер: базовая формула + пороги creativity/structure.
5. PUT/GET upscale-models (валидация, файл, дефолт при отсутствии).
6. Живой smoke (опционально, ~$0.02): edits-запрос с P-Image-Upscale
   на маленькой картинке — приходит увеличенный результат.

## Проверка после изменений

`setup_imagerouter.py` → рестарт `_restart_server.ps1` → GET
`/api/v2/models/` (есть spandrel-фейки и tile-controlnet) → PUT/GET
upscale-models → UI (F5): вкладка Upscaling без предупреждения, в дропдауне
— выбранные админом модели; апскейл картинки → результат в галерее; в
контекстном меню картинки «Upscale» (quick-action) — тоже облачный.

## Грабли, учтённые дизайном

- Два префикса ключей (`imagerouter/` main, `imagerouter-upscale/` spandrel)
  — иначе конфликт `GET /api/v2/models/i/{key}` для одной модели в двух
  ролях.
- RTK-кэш моделей живёт до F5 — смена админ-списка требует обновления
  страницы у пользователя (подсказка в UI админа).
- `_is_echo` отключён для апскейла (иначе честный апскейл ловится как «эхо»).
- Идентификация is_upscale — по типу spandrel-узла, НЕ по наличию main-
  модели (adhoc-граф quick-action main-модели не содержит).
- Fallback каталога: при недоступности api.imagerouter.io инъекция просто
  ничего не добавит (кэш 10 мин), ошибки UI не будет.
