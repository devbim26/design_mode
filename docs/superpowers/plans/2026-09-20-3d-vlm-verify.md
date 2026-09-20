# План: 3D Design — VLM-верификация собранной модели

Спека: docs/superpowers/specs/2026-09-20-3d-vlm-verify-design.md.
Паттерн get_ifc_scene_overvier из MCP4IFC → наш конвейер 3D Design.

## Задачи

1. **threed/threed_verify.py** — новый модуль: scene_overview (4 сценария),
   built_overview (подсчёт CONCEPTUAL_* из готового IFC), SYSTEM_VERIFY,
   verify() с отказоустойчивым разбором {ok, issues}. Юнит-проверка вручную
   (python -c) на сэмплах из tests/test_threed.py.

2. **threed/threed_router.py** — интеграция: env THREED_VERIFY (0/false/no/off
   = выкл), после build — обзор + второй _call_vlm + вердикт в res["verify"]
   и в дамп _threed_last.json. Инвариант: любой сбой верификации не роняет
   генерацию (ok=None, error в вердикте).

3. **imagerouter/devbim_topright_buttons.js** — тост: «✓ VLM» / «⚠ issues»
   суффиксом к done-тосту; сбой — молча. node --check обязателен.

4. **setup_threed.py** — threed_verify.py в плане копирования.

5. **tests/test_threed_verify.py** — 5 тестов из спеки; прогон:
   venv\Scripts\python.exe tests\test_threed_verify.py и
   tests\test_threed.py (регресс, моки не ветвятся → verify деградирует
   в ok=None, тесты обязаны остаться зелёными).

6. **Деплой + живой smoke**: setup_threed.py → _restart_server.ps1 →
   вход (siteauth cookie) → POST /api/v1/threed/generate живой картинкой →
   проверить verify в ответе и _threed_last.json; node -e проверка бандла
   не нужна (патчим только свой JS, но node --check прогнать).

7. **HANDOFF.md** — п.44 (конвейер, файлы, грабли, стоимость, выключатель).

## Грабли (из HANDOFF, применять)

- Тесты роутера импортируют venv-копии → после правок threed/* сперва
  setup_threed.py, потом тесты (для живого smoke; юнит-тесты дерева —
  как обычно из корня).
- _threed_last.json лежит в out_dir (ifc-каталог), не в data/.
- siteauth гейтит /api/v1/threed/* — curl с cookie devbim_auth.
- VLM 5–30 с на запрос — smoke не паникует раньше 180 с.
- Пиксельным проверкам верить больше, чем VLM-анализу скриншотов.
