# Журнал генераций в админ-панели — план реализации

**Goal:** В `/admin` видеть по каждому пользователю студии: потраченные ~$,
генерации (успех/ошибка), время генерации; журнал последних генераций
(время, тип, модель, статус, картинок, ~$, длительность, ошибка).

**Architecture:** Новая таблица `gen_log` в `studio.sqlite`
(`studio_store.log_generation/gen_stats/gen_log_list`); запись — в
`ImageRouterCanvasMiddleware` вокруг вызова перехваченного хендлера
enqueue_batch (видит успех/все ошибки/длительность/пользователя);
стоимость — оценка `pricing.average × картинок` из каталога IR.
Админ-панель `/admin` (`site_auth._ADMIN_PAGE`) — колонки, строка владельца,
`GET /admin/api/genlog`, модалка журнала.

**Tech Stack:** Python 3.11 (venv InvokeAI 6.2.0), sqlite3 (stdlib),
plain-assert тесты (`venv\Scripts\python.exe tests\test_userauth_genlog.py`).

**Спека:** `docs/superpowers/specs/2026-10-08-admin-genlog-design.md`

## Global Constraints

- Не править `venv/...` руками — деплой `setup_imagerouter.py` +
  `setup_site_auth.py`, рестарт `launch\_restart_server.ps1`.
- Тесты без сети: каталог/хендлеры мокаются; БД — во временной папке
  (`INVOKEAI_ROOT`).
- Существующие тесты (`test_userauth_admin.py`, `test_cloud_nodes.py`,
  `test_userauth_token.py`) проходят без правок.
- Ошибка записи журнала не ломает генерацию (глотается, stderr).

## Tasks

1. **studio_store.py** — таблица `gen_log` (init_db), `log_generation`
   (с пруном капа `GEN_LOG_CAP`, глобала — переопределяется в тестах),
   `gen_stats(user_id)`, `gen_log_list(user_id, limit)`.
2. **imagerouter_router.py** — `_gen_log` (безопасная обёртка),
   `_catalog_price(mid)`, `_gen_log_entry(studio_user, info, status,
   images, duration_s, error)` (kind/model из info, стоимость);
   в enqueue-ветке мидлвари: тайминг вокруг `to_thread(handler)`,
   запись ok (картинки из `result.item_ids`) / error (обе ветки except).
3. **site_auth.py** — `/admin/api/users` добавляет `gen` + `owner_gen`;
   `GET /admin/api/genlog` (query `user`, `limit`); `_ADMIN_PAGE`:
   колонки «Генерации», «~$», кнопка «Логи», строка владельца, итог,
   модалка журнала (fetch по кнопке).
4. **Тесты** `tests/test_userauth_genlog.py` — store (аггрегаты, прун,
   лимит), админ-API (гейты 401/403, ген-поля, genlog-фильтр), роутер
   (`_gen_log_entry`: ok с ценой/без, error; enqueue-ветка мидлвари с
   подменённым хендлером: 200→ok-запись, ошибка→error-запись).
5. **Деплой и проверка** — setup-скрипты, рестарт, тесты; живой смоук:
   ошибка (фиктивная модель) пишет error-запись, `/admin/api/genlog`
   отвечает; скриншот панели.
6. **HANDOFF.md** — п.67 (что/где/грабли: оценка ~, VLM/ноды — не-цель).
