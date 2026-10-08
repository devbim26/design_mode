# План: подписи под пиктограммами левой рейки + поясняющие тултипы

Спека: `docs/superpowers/specs/2026-10-08-navbar-labels-design.md`.

## Шаги

1. `setup_navbar_labels.py` (новый, корень):
   - `JS_AD_OLD` — точное текущее определение `Ad` (count==1);
     `JS_AD_NEW` — карта `DBLT` + новое определение (маркер идемпотентности
     `DBLT=`);
   - `JS_WORKFLOWS_OLD` — `a&&o.jsx(Ad,{tab:"workflows",…}),` (count==1,
     вырезание);
   - бэкап `*.navbarlabels-bak`, печать по шагам, `sys.exit(1)` на
     несовпадении якорей.
2. Запуск: `venv\Scripts\python.exe setup_navbar_labels.py`.
3. Проверка парсинга: `node -e "import('file:///…/App-*.js').catch(…)"`
   — допустима только рантайм-ошибка (см. AGENTS.md).
4. Рестарт `launch\_restart_server.ps1`, E2E в браузере:
   - подписи под всеми шестью кнопками; активная — жёлтая;
   - ховер: тултип с пояснением справа от кнопки;
   - Workflows отсутствует;
   - клик по подписи переключает вкладку; скриншот в `docs/`.
5. HANDOFF.md (новый пункт + порядок скриптов), AGENTS.md (порядок
   скриптов + строка «Где что»).

## Откат

Восстановить `App-*.js` из `App-*.js.navbarlabels-bak` (или
force-reinstall + все setup-скрипты, кроме navbar_labels) и рестарт.
