# AGENTS.md — DevBIM Image Studio (InvokeAI)

Правила для агентных сессий, работающих с этим репозиторием.

## Что это

Локальный InvokeAI 6.2.0 (CPU) с ребрендингом DevBIM, облачной генерацией
ImageRouter, IFC-вьювером, PDF-вьювером, гейтом сайта по паролю и
мультитенантностью «экземпляр на компанию». Скрипты патчат пакет в
`venv/Lib/site-packages/invokeai/` — после
`pip install --force-reinstall invokeai==6.2.0` применять в порядке:
`rebrand_devbim.py` → `setup_imagerouter.py` → `setup_ifcviewer.py` →
`setup_pdfviewer.py` → `setup_site_auth.py`. Все — идемпотентны.

## Где что

- `siteauth/site_auth.py` — мидлварь входа (SITE_PASSWORD из .env,
  SITE_VALID_UNTIL — срок лицензии). Деплой: `setup_site_auth.py`.
- `imagerouter/` — посредник облачной генерации (перехват enqueue_batch).
- `ifc/` — IFC-вьювер и его роутер.
- `pdf/` — PDF-вьювер (вкладка «PDF») и его роутер.
- `company_manager.py`, `create_company.py`, `start_company.bat`,
  `stop_company.py`, `list_companies.py` — компании-лицензиаты
  (экземпляр на компанию, порты 9100+).
- `companies/<код>/` — данные компаний (.env, invokeai.yaml, CREDENTIALS.txt);
  в git НЕ входят.
- `docs/superpowers/specs|plans/` — спеки и планы (читать перед задачей).
- `HANDOFF.md` — подробный рабочий контекст и грабли. ЧИТАТЬ ПЕРВЫМ.

## Жёсткие правила

- Не править файлы в `venv/.../site-packages` руками — только через
  setup-скрипты в корне (иначе правки потеряются при переустановке).
- Не коммитить: `.env`, `companies.json`, `companies/*`, ключи API.
- После патчей JS-бандлов обязательно проверить парсинг:
  `node -e "import('file:///...index-*.js').catch(e=>console.log(e.message))"`
  — допустима только рантайм-ошибка, не SyntaxError.
- Сервер перезапускать `_restart_server.ps1` (WMI, отсоединённо);
  процессы из агентских сессий умирают вместе с сессией.
- `PYTHONUTF8=1` обязателен в любом bat (кириллица в yaml).
- Тесты: `venv\Scripts\python.exe tests\<имя>.py` (plain asserts, печать OK).
- Один общий venv на все компании; порты компаний 9100+ (9090 — базовый).

## Порядок работы над задачей

1. Прочитать HANDOFF.md (раздел «Что реализовано» и «грабли»).
2. Спека/план в `docs/superpowers/` обязательны для нетривиальных задач.
3. После изменений — проверка из раздела «Проверка после изменений»
   в HANDOFF.md + тесты из `tests/`.
