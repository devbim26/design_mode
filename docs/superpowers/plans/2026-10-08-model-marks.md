# Пометки моделей (звёзды 1–5, мини-баннеры) — план реализации

**Goal:** В списке моделей генерации у каждой модели — звёзды 1–5
(сила в редактировании) и мини-баннеры (edit, вырезание фона, …);
значения редактируются владельцем в менеджере моделей.

**Architecture:** Хранение `data/data/imagerouter_model_marks.json`
(per-company) + дефолты в коде; инъекция полем `usage_info` в
`_ir_fake_config` (рендерится Picker'ом без патчей бандла); GET/PUT
`/api/v1/imagerouter/model-marks`; админ-секция в `imagerouter.html`;
цветные чипы и звёзды — в `devbim_model_info.js` (блок под селектором
+ раскраска поповера пикера).

**Tech Stack:** Python 3.11 (роутер FastAPI уже смонтирован), vanilla
JS в dist (деплой `setup_imagerouter.py`), plain-assert тесты
`venv\Scripts\python.exe tests\test_model_marks.py`.

**Спека:** `docs/superpowers/specs/2026-10-08-model-marks.md`

## Global Constraints

- Бандлы не патчим: usage_info рендерит сам пикер (Xte).
- description main-моделей не менять — гейт Generate-фолбэка ищет
  «editing».
- Деплой: `venv\Scripts\python.exe setup_imagerouter.py`, рестарт
  `launch\_restart_server.ps1`.
- Тесты без сети: каталог мокается, root_path — временная папка.

## Tasks

1. `imagerouter_router.py`: `_DEFAULT_BADGES`/`_DEFAULT_MARKS`,
   `_marks_store_path`/`_load_marks`/`_save_marks`,
   `_effective_marks()` (файл || дефолты), `_marks_usage_info(m)`;
   `usage_info` в `_ir_fake_config`; GET/PUT `/model-marks`.
2. `imagerouter/devbim_model_info.js`: звёзды + чипы в блоке описания;
   fetch `/api/v1/imagerouter/model-marks`; MutationObserver-раскраска
   поповера дропдауна (метки → чипы, звёзды → жёлтые).
3. `imagerouter/imagerouter.html`: секция «Звёзды и баннеры моделей»
   (поиск, select 0–5, чекбоксы, каталог баннеров, предпросмотр,
   сохранение).
4. `tests/test_model_marks.py`: дефолты/файл/валидация PUT/
   usage_info/через `_add_ir_models`.
5. Деплой + рестарт, E2E браузером (дропдаун, блок под селектором,
   админ-секция), HANDOFF.md.
