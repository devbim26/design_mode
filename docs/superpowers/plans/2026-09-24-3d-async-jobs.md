# План: 3D Design — фоновые задачи генерации (фикс 524)

Спека: `docs/superpowers/specs/2026-09-24-3d-async-jobs-design.md`.
Ветка `interior`. Порядок задач строгий; тесты — plain asserts
(`venv\Scripts\python.exe tests\test_threed.py`), фокус-тесты — из
каталога tests (грабля п.40 HANDOFF: site-packages/tests затеняет).

## Задачи

1. **Бэк: job store + фоновый поток** (`threed/threed_router.py`)
   - импорт threading/uuid; константы JOBS_MAX=20, JOBS_TTL_S=1800,
     JOBS_POLL_SUPPORTED (для самопроверок не нужно — просто код);
   - `_jobs/_jobs_lock`, `_job_new(scenario) -> dict` с cleanup по
     возрасту/количеству, `_job_public(job) -> dict`;
   - `_generate_impl(..., progress=None)`: вызовы progress("analysis")
     в _attempt перед VLM, progress("build") перед build_*,
     progress("verify") перед _verify_attempt;
   - `_run_job(job_id, scenario, prompt, image)`: семафор(1),
     статусы queued→running→done/error, elapsed_s, try/except;
   - `POST /generate`: prepare+валидация (422 как раньше) → job →
     поток → `{jobId, status:"queued"}`;
   - `GET /jobs/{id}`: 404/публичный вид с result|error.
2. **Тесты job-механизма** (`tests/test_threed.py`)
   - test_generate_job_flow: мок VLM → _run_job напрямую → done,
     result.name, stage-последовательность analysis/build(/verify);
   - test_job_cleanup_ttl: устаревший done удаляется при новой job;
   - test_get_job_404: HTTPException у неизвестного id;
   - test_post_generate_shape: тело GenerateBody с мусорной
     dataURL-base64 остаётся синхронным 422 (job не создаётся);
     сценарий "attic" → job error с текстом гейта.
3. **Фронт: поллинг** (`imagerouter/devbim_topright_buttons.js`)
   - словарь t(): stageQueued/stageAnalysis/stageBuild/stageVerify/
     jobLost (RU+EN);
   - run3D: ветка jobId (поллинг 2.5 с, статус-строка с этапом,
     done → прежняя обработка результата; 404 → jobLost) и ветка
     старого синхронного ответа (name в ответе POST);
   - `node --check` виджета.
4. **Деплой + смоук**
   - `venv\Scripts\python.exe setup_threed.py`;
     `venv\Scripts\python.exe setup_imagerouter.py` (виджет);
   - рестарт `launch\_restart_server.ps1`;
   - смоук без VLM: cookie devbim_auth → POST {scenario:"attic",
     image:<минимальный PNG dataURL>} → jobId → поллинг до error
     («в разработке» — гейт), затем POST с битым base64 → 422 мимо
     job-API; GET /jobs/unknown → 404.
5. **E2E Playwright (краткий)**: модалка 3D → Generate (без источника
   → тост «нет источника», без трат) — только UI-независимость
   паттерна поллинга не проверяем живьём (бюджет: смоук = задача 4);
   скриншот статуса поллинга не обязателен.
   → По факту: если сервер жив и время позволяет — одна живая
   генерация НЕ выполняется (пользователь уже потратил сегодня).
6. **Документация**: HANDOFF п.47 (что/где/грабли: лимит CF ~100 с,
   job-API, семафор=1, рестарт теряет очередь), README раздел 3D —
   упоминание фоновых задач; коммит.
