# Спека: вкладка «Design Code» — вьювер сайта дизайн-кода (nw.dev-bim.com)

Дата: 2026-09-10. Запрос пользователя: «сделай ещё один вьювер по аналогии
с существующими — design_code вьювер, который будет открывать сайт по типу
https://nw.dev-bim.com/. Сайт установлен на этом компе, доступ через туннель.
Доступ сделать так: нажимаем на кнопку вьювера → модальное окно → ввести
URL сайта и код → открывается интерактивное окно с сайтом».

## Контекст

База дизайн-кода «Северный Берег» — статический сайт (проект
`North waterfront/`, сервер `serve_nw.py` :8020, Cloudflare-туннель
`nw.dev-bim.com`). В DevBIM Image Studio уже есть вкладки-вьюверы IFC и PDF
(кнопка в левой рейке, панель = iframe своей страницы из dist). Новый
вьювер показывает ВНЕШНИЙ сайт — пользователь вводит его адрес и код
доступа в модальном окне, после проверки кода сайт открывается в
интерактивном iframe.

## Решение

Всё по паттерну PDF-вьювера (п.18 HANDOFF), без интеграции с холстом:

1. **Вкладка «Design Code» в левой рейке** (после PDF, id `designcode`).
   Иконка — палитра Phosphor (fill), встраивается собственной функцией
   `DCI` тем же приёмом, что `RA`/`vx` (хелпер `ue` из бандла); label
   «Design Code». Панель вкладки — iframe `/design_code_viewer.html`
   (компонент `DCE` перед `const cue=u.memo(`, unregisterTab в cleanup).
   `designcode` добавляется в zod-enum activeTab (index-бандл).
2. **Страница `design_code/design_code_viewer.html`** (деплой в dist):
   - нет сохранённого URL ИЛИ сессия не разблокирована → модальное окно:
     «Site URL» (префилл из `default_url` сервера / последнего ввода) +
     «Access code» + кнопка Open; Enter — отправка;
   - POST `/api/v1/designcode/auth {url, code}`; 401 → сообщение
     «Wrong access code»; успех → iframe загружает сайт, URL — в
     localStorage `devbim:designcode:url`, разблокировка — в
     sessionStorage `devbim:designcode:unlocked` (до закрытия вкладки
     браузера, как админский гейт);
   - плавающий тулбар над iframe: «⟳ Reload», «↗ Open in new tab»,
     «⚙ Change site» (снова модалка), чип с текущим хостом;
   - если сайт запрещает встраивание (X-Frame-Options) — iframe пустой,
     рядом с чипом хоста подсказка «откройте ↗ в новой вкладке»;
   - язык — английский (базовый, как у PDF-вьювера, решение 05.09);
     RU-адаптация — отдельная задача.
3. **Роутер `design_code/design_code_router.py`** (деплой в
   `routers/design_code.py`, per-company .env как siteauth):
   - `GET /api/v1/designcode/auth` → `{protected: bool, default_url}` —
     protected = задан DESIGN_CODE_ACCESS_CODE; default_url =
     DESIGN_CODE_URL (префилл, опционально);
   - `POST /api/v1/designcode/auth` → проверка кода
     `hmac.compare_digest`, пауза 0.3 с + 401 при неверном (как
     admin-auth у imagerouter); URL обязан начинаться с http(s)://;
     DESIGN_CODE_ACCESS_CODE не задан → защита отключена, любой код
     принимается (зеркало admin-auth).
   Ключи читаются перечитыванием .env-файла на каждом вызове
   (`_env_candidates`/`_env_value` из siteauth): правка кода действует
   без перезапуска сервера; для компаний — свой `companies/<код>/.env`.
4. **`setup_designcode.py`** — идемпотентный, бэкапы `*.designcode-bak`:
   копирует роутер и страницу, патчит api_app.py (после pdf-роутера;
   гейт: pdf-патчи обязаны быть уже применены), App-бандл (кнопка в
   рейке после PDF: якорь `o.jsx(Ad,{tab:"pdf",...})`; панель в
   TabContent: якорь `e==="pdf"&&o.jsx(PDFE,{})`; вставка DCI+DCE перед
   `const cue=u.memo(`), index-бандл (enum). Порядок после
   force-reinstall: rebrand → imagerouter → ifcviewer → pdfviewer →
   **designcode** → siteauth.

## Что НЕ входит (кандидаты на продолжение)

- Мост «To Canvas» (снимок страницы сайта → холст) — сайт внешний
  cross-origin, содержимое недоступно; если понадобится — вырезание
  скриншотом руками.
- RU-локализация модалки, панель «Design Code» в dockview холста.
- Белый список хостов URL (сейчас — любой http(s), вьювер открывает то,
  что ввёл пользователь).

## Проверка

- `tests/test_designcode.py`: проверка кода (верный/неверный/выключен),
  валидация URL, protected/default_url.
- E2E (Playwright): вкладка в рейке → модалка → ввод URL локального
  сервера NW (:8020) и кода → сайт открыт в iframe; ↗ / ⟳ / ⚙ работают;
  F5 → без повторного ввода кода (sessionStorage).
- Бандлы после патча: `node -e "import('file:///...App-*.js')..."` —
  только runtime-ошибка, не SyntaxError.
