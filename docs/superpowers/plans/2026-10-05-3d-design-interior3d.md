# План: 3D Design — сценарий «Interior» (interior3d)

Спека: `docs/superpowers/specs/2026-10-05-3d-design-interior3d-design.md`.
Стиль — фаза 4 («Сцена»): сценарий без ансамбля, camHint → вьювер.

## Задачи

1. **Сценарий** (`threed/threed_scenarios.py`): `SYSTEM_INTERIOR3D`
   (room-frame контракт), `INTERIOR3D_FURNITURE_TYPES` (палитра дефолтов),
   `validate_interior3d` (гейты/клампы по спеке, `(scene, warnings)`).
2. **Сборщик** (`threed/threed_build.py`): `build_interior3d` (пол/потолок/
   4 стены/проёмы/мебель/люди, pset CameraHint Mode="interior" + RoomModel)
   и `_draw_interior3d_preview` (план + маркер камеры). Один коммит с
   превью-функцией (урок фазы 4-5: тест сборщика требует файл превью).
3. **Роутер** (`threed/threed_router.py`): `interior3d` в SCENARIOS,
   диспетчеры system/validate/build, camHint ответа (mode/eye/target/yaw).
4. **Verify** (`threed/threed_verify.py`): ветка `scene_overview` для
   interior3d.
5. **Вьювер** (`ifc/ifcviewer.html`): ветка mode="interior" в
   `applyCamHint` (глаз/цель напрямую, world=(x, z, −y)).
6. **Фронтенд** (`imagerouter/devbim_topright_buttons.js`): 4-я плитка
   «Interior» 🛋 data-s="interior3d", «Floor Plan» → 📐, placeholder'ы
   RU/EN, ключ в `ph`-карте.
7. **Тесты** (`tests/test_threed.py`): валидатор (ок/битые/клампы),
   сборщик (IFC пишется, классы/pset/превью), роутер (SCENARIOS,
   camHint формата), overview. Деплой: `setup_threed.py` → тесты →
   `setup_ifcviewer.py` → `setup_imagerouter.py` → `node --check`.

## Проверка

- `venv\Scripts\python.exe tests\test_threed.py` (все, включая новые).
- `node --check` виджета; `tests/test_topright_buttons.py`.
- Живой smoke (по бюджету): генерация по рендеру интерьера, дамп
  `data/ifc/_threed_last.json`, камера вьювера = глаз из camHint.
