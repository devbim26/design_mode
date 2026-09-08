# План: Облачный апскейлинг (спека 2026-09-08-cloud-upscaling-design.md)

1. `imagerouter/imagerouter_router.py`:
   - константы: `IR_UPSCALE_KEY_PREFIX`, `TILE_CONTROLNET_FAKE_*`, `DEFAULT_UPSCALE_MODELS`;
   - хранение выбора админа `<root>/data/imagerouter_upscale.json` + эндпоинты
     GET/PUT `/upscale-models`;
   - fake-конфиги: spandrel (type=`spandrel_image_to_image`, base=`any`) для
     выбранных моделей, tile-ControlNet (base=sdxl, «tile» в имени);
   - `_add_ir_models` + `GET /api/v2/models/i/{key}` обслуживают новые ключи,
     DELETE — 400;
   - `_extract_ir_info`: is_upscale / upscale_model_key / init_image / scale /
     creativity(1−denoising_start) / structure(control_weight) / board из любого узла;
   - `_pick_upscale_size`, `_upscale_prompt`, `_handle_upscale_generation`
     (события — через общие фабрики, вынесенные из canvas-обработчика);
   - мидлварь: ветка is_upscale в enqueue_batch (раньше основной).
2. `imagerouter/imagerouter.html`: секция «Апскейлинг» — чекбоксы моделей со
   входом-image, поиск, порядок (= модель по умолчанию первая), PUT на «Сохранить».
3. Тесты `tests/test_upscale_cloud.py` (инъекция, extraction, size, промпт,
   эндпоинты; fixtures графа — по структуре `sSe`/`cSt` из бандла).
4. Деплой `setup_imagerouter.py` (deploy_files уже копирует оба файла),
   рестарт `_restart_server.ps1`.
5. Проверка: GET /api/v2/models/ (spandrel-фейки + tile), PUT/GET upscale-models,
   живой edits-smoke по каждой модели из дефолта (~$0.02, список уточнить),
   UI Playwright: вкладка Upscaling без предупреждения, дропдаун = выбор админа,
   апскейл до галереи.
6. Документация: README (раздел Upscaling), HANDOFF (новый пункт).
