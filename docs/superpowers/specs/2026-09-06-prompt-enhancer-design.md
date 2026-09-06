# Спека: Prompt Enhancer — улучшение промта через VLM ImageRouter

Дата: 2026-09-06. Ветка: `feature/pdf-viewer` (спека; реализация — отдельной веткой).
Статус: дизайн одобрен пользователем 06.09.2026.

## Цель

В левой панели (промпт-бокс вкладок Generate/Canvas) добавить «Prompt Enhancer»:
текущий промт пользователя **и приложенные изображения** (Reference Images) отправляются
не в генерацию картинки, а в vision-language-модель (текст+картинка → текст), которая
возвращает улучшенный вариант промта. Пользователь просматривает результат и применяет
его (Replace / Insert / Discard).

## Решения пользователя (06.09.2026)

1. **Язык улучшенного промта — всегда английский** (модели генерации и style-пресеты
   англоязычные; интерфейс остаётся локализованным).
2. **VLM по умолчанию — `zai/glm-5.3-flash`** (проверена живым запросом: точное чтение
   референса, ~$0.0002/вызов; prompt $0.1e-6, completion $0.25e-6 за токен).
   Override через `.env`: `PROMPT_ENHANCER_MODEL` (кандидаты пользователя:
   `deepseek/deepseek-v4-flash-vision-exp`, `moonshot/kimi-k3` — обе в каталоге,
   обе с входом-изображением; kimi-k3 ≈ в 50 раз дороже).
3. **Reference Images учитываются сразу** (фаза 1), одним дополнительным патчем
   App-бандла.

## Ключевой факт (разведка)

В InvokeAI 6.2.0 уже встроен весь UI этой функции — «Prompt Expansion»:
- жёлтая кнопка-искра в футере промпт-бокса (компонент `U$e`), меню:
  «Expand current prompt» / «Upload image for prompt generation»;
- дропзона: перетащить картинку на промпт-бокс → промт по картинке;
- пункт контекстного меню галереи «Use for prompt generation»;
- оверлей результата с кнопками **Replace / Insert / Discard** (`W$e`),
  спиннер во время работы, блокировка textarea, локализация 19 языков.

UI выключен флагом `allowPromptExpansion:false` (config-слайс, дефолт в index-бандле;
сервер это поле не присылает — дефолт живёт вечно) и зовёт серверные узлы
`claude_expand_prompt` / `claude_analyze_image`, которых на сервере НЕТ (Enterprise-
фича; в пакете не зарегистрированы). Клиентский флоу (`lb` → `wG`): строит граф
(`yke`), ставит его в реальную очередь (`enqueue_batch`, prepend), ждёт
`queue_item_status_changed` → `GET items/{id}` → `session.results[node].value`,
проверяя `type === "string_output"`.

## Подход (выбранный)

**Штатный UI + настоящие серверные инвокации.** Флаг включаем патчем бандла,
узлы подселяем реальными классами — очередь/события/отмена/прогресс работают
нативно, ничего не фейкается.

Отвергнутые альтернатативы:
- **Свой виджет** (паттерн тумблера «Маска/Слой»): дублирует существующий UX,
  DOM-хаки для чтения/записи промпта.
- **Перехват enqueue + синтетические события** (паттерн генерации картинок):
  пришлось бы подделывать SessionQueueItemDTO и события сокета — хрупко,
  преимуществ нет.
- **Локальный tiny-prompt-expander (ONNX)**: нет локальных моделей, слабое зрение,
  не архитектурная специфика.

## Архитектура

### 1. Сервер: новый модуль инвокаций

Новый файл в проекте: `imagerouter/prompt_enhancer.py`; деплой setup-скриптом в
`venv/Lib/site-packages/invokeai/app/invocations/devbim_prompt_enhancer.py`
(новый файл — ничего не патчится; пакет сам подхватывает: `app/invocations/__init__.py`
строит `__all__` из `*.py` каталога, `services/shared/graph.py` делает
`from invokeai.app.invocations import *` → декоратор `@invocation` регистрирует класс).

Две инвокации (имена типов — ровно те, что шлёт фронтенд):

```python
@invocation("claude_expand_prompt", title="Enhance Prompt (ImageRouter)", ...)
class EnhancePromptInvocation(BaseInvocation):
    prompt: str = InputField(default="")
    model_architecture: str = InputField(default="tag_based")  # фронтенд шлёт tag_based/sentence_based — принимаем, игнорируем (для nano-banana/GPT-image естественный язык лучше тегов)
    images: list[ImageField] = InputField(default=[])           # НАШЕ расширение (патч yke)

@invocation("claude_analyze_image", title="Analyze Image (ImageRouter)", ...)
class AnalyzeImageInvocation(BaseInvocation):
    image: ImageField
    model_architecture: str = InputField(default="tag_based")
```

`invoke(context)`:
1. Пусто и промт, и картинки → `ValueError("Введите промт или приложите изображение")`
   (элемент очереди честно падает → штатный тост «Prompt expansion failed»).
2. Загрузка картинок: `context.images.get_pil(image.image_name)`.
3. Подготовка: даунскейл до max 1024px по длинной стороне, альфа → белый фон,
   JPEG q85, b64 → `data:image/jpeg;base64,...`. Не более 4 изображений.
4. POST `https://api.imagerouter.io/v1/openai/chat/completions`
   (OpenAI-мультимодальный формат — проверено живым запросом 06.09).
   Ключ и модель — из `imagerouter_router` (ленивый импорт, единый источник):
   `_load_key()`, модель `PROMPT_ENHANCER_MODEL` из `.env`
   (по умолчанию `zai/glm-5.3-flash`).
5. Параметры: `max_tokens=1500`, `temperature=0.7`, таймаут 120 с.
6. Санитайзер результата: срезать markdown-ограждения/кавычки, схлопнуть пробелы,
   `strip()`.
7. Возврат `StringOutput(value=text)` (тип `string_output` — клиентский
   ассерт пройдёт).

Системный промт VLM (суть): «Ты — постановщик промтов для архитектурной
визуализации. На входе черновик (любой язык) и опциональные референсы.
Перепиши в ОДИН детальный английский промт для модели генерации изображений:
сохрани намерение и названные пользователем детали, добавь конкретику
(архитектура, материалы, освещение, камера, композиция, атмосфера), учти стиль
и содержание референсов, не противоречь им. Выведи ТОЛЬКО финальный промт,
без преамбул, кавычек и markdown. ~50–120 слов.»
Для analyze-image: «Опиши изображение как промт, по которому его можно
воссоздать» + те же правила вывода.

### 2. Клиент: три идемпотентных патча в `setup_imagerouter.py`

**`patch_prompt_expansion_flag()`** — index-бандл (искать по `index-*.js`):
- OLD: `allowPromptExpansion:!1` (проверено: ровно 1 вхождение)
- NEW: `allowPromptExpansion:!0`
- Идемпотентность: по наличию NEW. Бэкап `*.imagerouter-bak` (общий).
  Включает: кнопку ✨, дропзону, пункт меню галереи.

**`patch_expand_graph_refs()`** — App-бандл (искать по `displayName="TabContent"`):
- OLD (проверено: ровно 1 вхождение):
  `const i=V2(e),a=new Et(Q("claude-expand-prompt-graph")),r=a.addNode({type:"claude_expand_prompt",id:Q("claude_expand_prompt"),model_architecture:s,prompt:i});return{graph:a,outputNodeId:r.id}`
- NEW: то же, но в `addNode` добавляется `images:` + коллектор референсов из
  стейта `e` (первый аргумент `yke` — полный redux-стейт):
  `state.canvas.present.referenceImages.entities[].ipAdapter.image`
  (глобальные референсы; форма подтверждена парсером метаданных
  `referenceImages.entities → {id, ipAdapter, isEnabled}`);
  только `isEnabled !== false` и с непустым `image`; map → `{image_name}`;
  redux-undo разворачивается через `.present` (грабля тумблера, п.16 HANDOFF).
  Коллектор обёрнут try/catch → при любой ошибке `[]` (фича деградирует
  до промт-only, не ломая стоковый флоу).
- Идемпотентность: по наличию `images:` в NEW-фрагменте.

**`patch_expansion_overlay_edit()`** — App-бандл, редактируемый оверлей
результата (требование пользователя 06.09: «отредактировать → вставить»).
Штатный оверлей `W$e=({expandedText:e})` показывает результат СТАТИЧЕСКИМ
текстом (chakra Text) — правка до вставки невозможна. Патч переписывает
компонент (якорь `W$e=({expandedText:e})=>{` — проверено: ровно 1 вхождение;
заменяется тело компонента до `,Lne=u.memo(`):
- текст результата → **uncontrolled textarea** (chakra `Ns` — та же, что у
  промпт-бокса, `variant:"darkFilled"`, `defaultValue:e`, маркер
  `data-devbim-enhanced`) — React не контролирует значение после монтирования,
  пользователь свободно правит;
- обработчики Replace/Insert читают ТЕКУЩЕЕ значение из DOM
  (`document.querySelector("textarea[data-devbim-enhanced]").value`,
  fallback на исходный `e`) — вставляется отредактированный текст;
  Insert по-прежнему дописывает в конец основного промта через `\n`;
- кнопки/иконки/лейаут (Replace зелёная / Insert синяя / Discard красная)
  переиспользуются из заменяемого фрагмента (все идентификаторы в скоупе).
- Идемпотентность: по наличию `data-devbim-enhanced` в бандле.

Плюс `deploy_prompt_enhancer()`: копирование `imagerouter/prompt_enhancer.py` →
`invokeai/app/invocations/devbim_prompt_enhancer.py` (идемпотентно, перезапись).

Обязательная проверка после патчей: node-import обоих бандлов — допустима только
рантайм-ошибка (`document is not defined`), не SyntaxError.

### 3. Роутер (`imagerouter_router.py`)

Минимальные дополнения:
- const `CHAT_COMPLETIONS_URL = f"{IR_BASE}/v1/openai/chat/completions"`;
- `_enhancer_model()` → `.env` `PROMPT_ENHANCER_MODEL` (через существующий
  `_env_value`-паттерн перечитывания .env), дефолт `zai/glm-5.3-flash`;
- в `GET /status` добавить `prompt_enhancer_model` (видно в диагностике).

### 4. UX-потоки (все штатные, ничего своего)

- Промпт-бокс → ✨ → «Expand current prompt»: текущий промт (+референсы из
  патча yke) → VLM → оверлей (текст **редактируемый**) → правка при желании →
  Replace / Insert / Discard.
- Дроп картинки на промпт-бокс / «Upload image for prompt generation» /
  ПКМ по картинке галереи → «Use for prompt generation»: картинка → VLM →
  оверлей (редактируемый) → Replace/Insert.
- Во время работы textarea заблокирована, спиннер; ошибка — тост
  «Prompt expansion failed» (локализован).

## Обработка ошибок

- Нет ключа / VLM недоступна / пустой ответ → инвокация бросает исключение →
  элемент очереди `failed` → штатный тост. Текст исключения виден в деталях
  очереди.
- HTTP 200 с `{"error": {...}}` — разбирать `_api_error_message` (грабля
  ImageRouter).
- Пустой `content` (reasoning-модель тратит лимит на «размышления» до начала
  ответа — замечено на glm-5.3-flash при `max_tokens=300`: контент пуст при
  исчерпанных токенах): при `max_tokens=1500` запас достаточен (полный ответ
  в тесте 06.09 — 781 completion-токен); если `content` всё же пуст —
  чистая ошибка «модель вернула пустой ответ».

## Развёртка / откат / порядок

- После `pip install --force-reinstall invokeai==6.2.0` порядок не меняется:
  rebrand → imagerouter (теперь с 2 новыми патчами + деплой узла) → ifcviewer →
  pdfviewer → siteauth → style presets.
- Перезапуск сервера обязателен (новые инвокации регистрируются при старте).
  В браузере достаточно F5.
- Мультикомпанность: venv общий → узел доступен всем инстансам; модель и ключ
  — per-company `.env`.
- Откат: восстановить `*.imagerouter-bak` (оба бандла), удалить
  `invokeai/app/invocations/devbim_prompt_enhancer.py`, перезапустить.

## Тестирование

`tests/test_prompt_enhancer.py` (plain asserts, печать OK — конвенция проекта):
1. Деплой файла узла + `import invokeai.app.invocations.devbim_prompt_enhancer`
   → в реестре есть `claude_expand_prompt` и `claude_analyze_image`.
2. Чистые функции: подготовка картинки (даунскейл/фон/b64), санитайзер
   (ограждения/кавычки/пробелы), сборка тела запроса (модель из env,
   формат messages, лимит 4 картинки).
3. Живой smoke (ключ из data/.env): реальный вызов с маленькой картинкой →
   непустой английский текст (пропускать при отсутствии ключа).

Ручной E2E (Playwright, конвенция проекта):
- F5 → в промпт-боксе кнопка ✨ → «Expand current prompt» → спиннер →
  оверлей → отредактировать текст → Replace (в промпте отредактированная
  версия) и Insert (дописан в конец).
- Дроп картинки на промпт-бокс → оверлей с описанием.
- ПКМ по картинке галереи → «Use for prompt generation».
- Добавить Reference Image → улучшить → результат учитывает содержимое референса.
- Отмена во время работы (кнопка очереди) — элемент отменяется, оверлей
  закрывается по тосту ошибки.

## Известные грабли (учтены в дизайне)

- Якоря обоих патчей проверены на уникальность (по 1 вхождению) в текущих
  бандлах 6.2.0; после force-reinstall якоря те же (версия зафиксирована).
- Проверка парсинга бандлов после патчей обязательна (грабля «одна лишняя
  скобка ломает весь бандл»).
- Инвокация не должна импортировать роутер на уровне модуля (порядок
  инициализации) — только лениво внутри `invoke()`.
- `model_architecture` фронтенд шлёт всегда; поле обязано существовать в схеме
  узла, иначе валидация графа уронит элемент очереди.
- Максимум референсов — 4 (VLM-контекст и стоимость; остальное молча
  обрезается).

## Не делаем (YAGNI)

Выбор VLM в UI, учёт активного style-пресета в системном промте, стриминг,
история улучшений, отрицательный промт.
