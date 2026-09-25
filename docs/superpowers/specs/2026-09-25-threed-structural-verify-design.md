# Спека: детерминированные структурные проверки IFC в 3D Design (п.58)

Дата: 25.09.2026. Ветка: 3d_analysys.

## Контекст

Самопроверка 3D Design (п.44/п.46) сегодня — только VLM: картинка + обзор
«задумано (сцена) / построено (счётчики ObjectType)» → вердикт. Слепая зона:
если сборка сломалась тихо, а счётчики правильные, этого не видит никто.
Демо на живом файле из data/ifc (ifc-mcp find_orphans) подтвердило класс
ошибок реально существует. Источники паттернов: Daviidro/ifcopenshell-mcp
`validate_ifc_model` (MIT), smartaec/ifcMCP `get_openings_on_wall`
(Apache-2.0) — берём подход, не код.

## Решение

Новая функция `structural_report(ifc_path)` в `threed/threed_verify.py`:
открывает готовый IFC (ifcopenshell уже в venv) и считает детерминированные
проверки за миллисекунды, без новых зависимостей и сервисов:

1. **Проёмы без стены-носителя** — IfcOpeningElement без IfcRelVoidsElement.
2. **Проёмы без заполнения** — IfcOpeningElement без IfcRelFillsElement
   (информационное; сборщик создаёт проём и заполнение парой).
3. **Двери/окна вне проёма** — IfcDoor/IfcWindow без IfcRelFillsElement
   (фолбэк-прокси без проёма — IfcBuildingElementProxy, НЕ проверяется).
4. **Элементы без пространственной привязки** — физические продукты
   (proxy/geographic/wall/slab/space/furnishing/door/window) без
   IfcRelContainedInSpatialStructure и без IfcRelAggregates. IfcOpeningElement
   исключён (живёт в стене через VoidsElements — by design). Контейнер
   ЛЮБОГО уровня годится: дормеры/башни/цоколь фасада сидят в building —
   это валидный IFC, не сирота (уточнение к формулировке ifc-mcp
   «no_storey_no_aggregate»).
5. **Безымянные продукты** — пустой Name у тех же классов (счётчик).

Результат: `{"ok": bool, <счётчики>, "examples": [имена ≤5],
"issues": [строки ≤8]}`. Ноль находок → ok=True, issues=[].

## Режим — мягкий (решено при согласовании)

- Проверки **не меняют** вердикт VLM, ранг попыток и corr_pool (дефект
  сборщика нерелевантен для CORRECTIONS повторного АНАЛИЗА сцены).
- Работают **всегда**, даже при THREED_VERIFY=0 (бесплатные, без VLM).
- Сбой проверок не роняет генерацию: `{"ok": None, "error": …}`.

## Точки интеграции

- `threed_router._run_attempt`: после сборки — `structural_report`; в
  `res_i["structural"]` (результат задачи) и в дамп `_threed_last.json`
  (ключ `structural`).
- `threed_router._verify_attempt`: `overview["structural"] = issues` —
  уезжает в промпт верификатора и в res["verify"]["overview"].
- `threed_verify.verify`: при непустом structural к промпту добавляется
  блок «(C) machine-detected IFC build defects (ground truth)». Блоки
  (A)/(B) не меняются.

## Тесты (tests/test_threed_verify.py)

1. Здоровые модели: interior (настоящие проёмы, фикс 24.09) и facade v2
   (villa с дормерами/башнями — проверка «building-контейнер не сирота») —
   все счётчики 0, issues=[], ok=True.
2. Сломанный файл (из здорового отрезаны отношения + стёрто имя):
   openings_unhosted/unfilled, fillings_homeless, elements_uncontained,
   unnamed_products == 1; ok=False, issues непустые.
3. verify(): блок (C) попадает в промпт только при непустом structural.
4. Роутер: `res["structural"]` и `dump["structural"]` на месте;
   THREED_VERIFY=0 — structural всё равно считается.

## Деплой

`setup_threed.py` (общий venv = все компании), перезапуск
`launch\_restart_server.ps1`. Проверка после изменений — по HANDOFF.
