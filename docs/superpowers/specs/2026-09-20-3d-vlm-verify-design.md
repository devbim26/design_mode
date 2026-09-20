# Спека: 3D Design — VLM-верификация собранной модели (пилот самопроверки)

Дата: 2026-09-20. Ветка `3d`. Идея из обзора MCP4IFC (Show2Instruct/ifc-bonsai-mcp,
MIT): их инструмент `get_ifc_scene_overview` возвращает JSON-обзор модели
(GUID, типы, свойства, габариты), который LLM использует для самопроверки.
Пилот переносит паттерн на наш конвейер: после сборки IFC — компактный обзор
«что задумано + что реально построено» → второй запрос VLM с исходной картинкой
→ строгий JSON-вердикт → ответ роутера и тост в модалке.

## Задача

Закрыть разрыв «VLM видит картинку один раз»: сейчас анализ идёт вслепую,
ошибки первого прохода (неверный этаж/сетки окон/крыша) доходят до пользователя
без контроля. Верификация — дешёвый цикл обратной связи без новых моделей.

## Конвейер (изменения жирным)

модалка → POST /api/v1/threed/generate → VLM-аналитик → validate_* →
build_* → **scene_overview + built_overview (подсчёт элементов из готового
IFC-файла)** → **второй VLM-запрос: картинка + обзор → вердикт
{ok, issues[]}** → ответ {name, warnings[, camHint][, **verify**]} →
**тост «✓ VLM» / «⚠ issues»**. Дамп `_threeed_last.json` расширяется
секцией verify.

## Дизайн

### threed/threed_verify.py (новый модуль)

1. `scene_overview(scenario, scene) -> dict` — семантический обзор ВАЛИДИРОВАННОЙ
   сцены (без пиксельных координат, только метры/счётчики):
   - facade: storeys, floor_height, width/depth, roof(+height), окна
     (rows×cols + w/h + сколько skip), балконы (счётчик + этажи), colors;
   - scene: camera, здания (main, габариты, этажи, крыша, окна, балконы,
     colors), счётчики деревьев/машин/людей;
   - plan: секции (id, use, floors), счётчики контекста по kind;
   - interior: стены/комнаты/проёмы (двери+окна)/мебель (счётчики), wall_height.
2. `built_overview(ifc_path) -> dict` — ЧЕСТНАЯ проверка сборщика: повторное
   чтение готового IFC (ifcopenshell.open), подсчёт продуктов по
   `ObjectType` с префиксом `CONCEPTUAL_*` (+ SITE_* у IfcGeographicElement,
   стены/плиты/спейсы интерьера). Ключи как в сборщике:
   CONCEPTUAL_STOREY/WINDOW/BALCONY/PLINTH/ROOF/TREE/CAR/PERSON/GROUND/WALL/
   FLOOR/ROOM/DOOR/MASS...
3. `SYSTEM_VERIFY` — системный промпт верификатора (EN, как остальные):
   роль QA, вход = картинка + (A) финальная спецификация + (B) фактически
   созданные элементы; ok=false только за реальные расхождения (этажность,
   пропавшие окна, не та крыша), НЕ за приближения massing-модели.
4. `verify(image_url, overview, call_vlm, model) -> dict` — формирует
   user-промт (обзор как JSON), зовёт `call_vlm(SYSTEM_VERIFY, ...)` ( тот же
   `_call_vlm` роутера — мокается в тестах ветвлением по system),
   `extract_json` → нормализация: {"ok": bool, "issues": [str до 8 по 120
   символов]}. Любой сбой (сеть/не-JSON/форма) → {"ok": None, "error": ...} —
   верификация НИКОГДА не роняет генерацию.

### Роутер (`threed_router.py`)

- Выключатель: env `THREED_VERIFY` (значения 0/false/no/off — выкл, по умолчанию
  ВКЛ). Считывается при каждой генерации (os.environ; .env грузится сервером).
- После build: `overview = {"scene": scene_overview(...), "built":
  built_overview(ifc_path)}`; вердикт; `res["verify"] = {"overview": overview,
  "verdict": verdict}`; дамп `_threed_last.json` получает `verify` (обзор +
  вердикт + голова сырого ответа).
- Стоимость: второй запрос ~$0.03–0.10 (gpt-6-astra, картинка ~1–2k токенов +
  reasoning) поверх ~$0.05–0.15 анализа; выкл — THREED_VERIFY=0 в .env.

### Фронтенд (`devbim_topright_buttons.js`)

`run3D()`: после успеха, при `j.verify.verdict`:
- ok=true → done-тост получает суффикс « · ✓ VLM»;
- ok=false → суффикс « · ⚠ » + issues (join '; ');
- ok=null (сбой) — молча (диагностика в дампе), UX не портим.
Языконезависимые символы, новых TEXTS не вводим.

### Деплой

`setup_threed.py`: в план копирования добавляется threed_verify.py →
routers/threed_verify.py. Идемпотентность сохраняется (сравнение байтов).

## Границы пилота

- Без автоправок сцены по issues (вердикт только сообщается).
- Без bbox-геометрии в обзоре (счётчики + параметры достаточно для QA-вопросов;
  геометрия — следующий шаг, если пилот окупится).
- Верификатор = та же модель, что анализатор (выбор в менеджере действует на
  оба запроса).

## Тесты (tests/test_threed_verify.py)

1. `test_scene_overview` — все 4 сценария по сэмплам: структура и значения.
2. `test_built_overview` — build_facade → counts (STOREY=5, WINDOW=15,
   BALCONY=2, PLINTH=1, ROOF=1); build_scene → TREE ×2 на дерево.
3. `test_verify_verdict_parse` — мок call_vlm: валидный JSON (в ```-заборе),
   мусор → ok=None+error, не-bool ok → нормализация.
4. `test_generate_impl_with_verify` — ветвящийся мок (analysis → сцена,
   verify → вердикт): res.verify.verdict.ok is True, дамп содержит verify;
   THREED_VERIFY=0 → ключа verify нет.
5. `test_verify_never_breaks` — verify-мок кидает исключение → генерация
   успешна, verdict.ok is None.
