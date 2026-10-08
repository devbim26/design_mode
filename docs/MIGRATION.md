# Переезд DevBIM Image Studio на другой сервер

Чек-лист переноса системы с одного Windows-сервера на другой.
Рабочий контекст — `HANDOFF.md`, порядок запуска — `launch/START-HERE.txt`.

## Что переносится, а что пересоздаётся

| Переносится вручную | Почему |
|---|---|
| `data\` целиком (~2.8 ГБ) | БД пользователей `data\data\studio.sqlite`, файлы IFC/PDF по пользователям (`data\ifc\<слаг>\`, `data\pdf\<слаг>\`), галерея `outputs\`, локальные модели `models\`, конфиг `invokeai.yaml` |
| `.env` корня | Секреты (в git не входит): `IMAGEROUTER_API_KEY`, `ADMIN_PASSWORD`, `SITE_PASSWORD`, `DESIGN_CODE_ACCESS_CODE`, `DESIGN_CODE_URL`, `STUDIO_AUTH_MODE`, `STUDIO_SESSION_TTL`, `STUDIO_FRAME_ANCESTORS`, `STUDIO_SESSION_SECRET` |
| `%USERPROFILE%\.cloudflared\` | Туннель design.dev-bim.com: `cert.pem`, `config-design.yml`, credentials-JSON туннелей, `cloudflared.exe` |
| `companies.json` + `companies\` | Только если созданы компании-лицензиаты (на 07.10.2026 — пусто, `[]`) |

Пересоздаётся на новом сервере (не переносить): `venv\` (пути зашиты),
`.git` (клонируется заново), `logs\`, `__pycache__`.

## Требования к новому серверу

- Windows 10/11 x64, ~15 ГБ свободного места;
- Python **3.11.x** (на старом — 3.11.9), Node.js **22.x** (сборка ассетов
  IFC-вьювера, проверка JS-бандлов), Git;
- порт 9090 свободен (компании — 9100+);
- исходящий HTTPS: PyPI, api.imagerouter.io, Cloudflare, HuggingFace
  (если `data\models\` не переносится и модели будут качаться заново).

## Порядок действий

### Старый сервер

1. Убедиться, что всё закоммичено и запушено:
   `git status` — чисто; запушить ветки `main` и `user_control`
   в `origin` (https://github.com/devbim26/design_mode.git).
2. Остановить систему: `launch\stop-system-design.bat`
   (threed-джобы живут в памяти — их статусы при переезде теряются,
   готовые IFC-файлы остаются).
3. Выгрузить данные (пример, флешка/сеть — `D:`):
   ```
   robocopy data D:\devbim-migration\data /E
   copy .env D:\devbim-migration\
   robocopy "%USERPROFILE%\.cloudflared" D:\devbim-migration\cloudflared /E
   ```

### Новый сервер

4. Клонировать репозиторий и встать на рабочую ветку:
   ```
   git clone https://github.com/devbim26/design_mode.git InvokeAI
   cd InvokeAI && git switch user_control
   ```
5. Создать venv и поставить зависимости (версии — как на старом сервере):
   ```
   py -3.11 -m venv venv
   venv\Scripts\pip install invokeai==6.2.0 ifcopenshell==0.8.5 matplotlib==3.11.1
   ```
   (torch 2.7.1 CPU, numpy 1.26.4, pillow 12.3.0 подтянутся по зависимостям;
   при расхождении свериться со старым сервером: `pip freeze`.)
6. Вернуть данные: `data\`, `.env` — в корень клона;
   `.cloudflared` — в `%USERPROFILE%`.
7. Применить патчи к пакету в venv (идемпотентны, порядок обязателен):
   ```
   venv\Scripts\python rebrand_devbim.py
   venv\Scripts\python setup_imagerouter.py
   venv\Scripts\python setup_ifcviewer.py
   venv\Scripts\python setup_pdfviewer.py
   venv\Scripts\python setup_designcode.py
   venv\Scripts\python setup_threed.py
   venv\Scripts\python setup_site_auth.py
   venv\Scripts\python setup_style_presets.py
   ```
8. Смоук-проверка перед стартом:
   ```
   venv\Scripts\python tests\test_threed.py
   venv\Scripts\python tests\test_userauth_login.py
   ```
   (полный набор — все `tests\test_*.py`, 40 файлов, все зелёные.)
9. Поднять туннель и систему:
   ```
   launch\start-system-design.bat
   launch\status-design.bat
   ```
   Проверить в браузере: http://127.0.0.1:9090 — вход (режим users),
   вкладки IFC / PDF / Design Code / 3D Design, галерея со старыми
   картинками, список старых IFC-файлов.
10. Убедиться, что публичный адрес design.dev-bim.com отвечает уже с
    НОВОГО сервера (DNS туннеля), и только потом выключать старый.

## Грабли

- **`PYTHONUTF8=1` обязателен** в любом bat (кириллица в yaml) — во всех
  `launch\*.bat` уже стоит; в своих скриптах не забыть.
- **БД студии физически в `data\data\studio.sqlite`** (quirk `db_path`:
  INVOKEAI_ROOT=data → data/data); файл `data\studio.sqlite` в корне —
  пустой огрызок, не перепутать при выборочном копировании.
- **Пустой `STUDIO_SESSION_SECRET` → вход запрещён** (fail-closed):
  переносить `.env` целиком; если секрет потерян — `setup_site_auth.py`
  сгенерирует новый, но все сессии пользователей слетят (перелогинятся).
- **`.env` в cloudflare-туннеле может терминироваться в http** — кука
  сессии без `Secure`, это учтено; ничего не «чинить».
- **Пользователь без своего токена ImageRouter** не генерит (так
  задумано, кредиты владельца не тратятся): после переезда раздать
  токены или заполнить через `/admin`.
- **Не править `venv\...\site-packages` руками** — только setup-скриптами
  (после любого `pip install --force-reinstall invokeai==6.2.0` —
  прогнать весь пункт 7 заново).
- **После патчей JS-бандлов** проверить парсинг:
  `node -e "import('file:///...index-*.js').catch(e=>console.log(e.message))"`
  — допустима только рантайм-ошибка, не SyntaxError.
- Старый сервер держать выключенным после переключения: два живых
  экземпляра на одном туннеле = расхождение БД пользователей.

## Восстановление при неполной переноске (опыт переезда 2026-10-07)

- **Нет `config-design.yml` / credentials-JSON туннеля design** — не беда:
  аккаунт Cloudflare авторизован `cert.pem`. Восстановление (схема
  docx-gen/credits):
  ```
  cloudflared tunnel token design   # base64 {a,t,s}
  # -> записать как ~/.cloudflared/<UUID>.json
  #    {"AccountTag":a,"TunnelID":t,"TunnelSecret":s}
  # -> пересоздать config-design.yml (tunnel/credentials-file/ingress
  #    design.dev-bim.com -> http://localhost:9090, catch-all 404)
  ```
  UUID туннеля: `cloudflared tunnel list`. DNS-запись уже существовала
  (проксированная, наружу видны только A/AAAA Cloudflare) и указывала
  на нужный UUID — проверяется сквозным запросом https://design.dev-bim.com
  после подъёма (303/200 = цепочка жива), API-ключ не нужен.
- **Туннель nw (nw.dev-bim.com, сайт «Северный Берег», репозиторий
  `..\North waterfront`)** — 2026-10-08: credentials восстановлены
  токеном, но живой коннектор старого сервера перехватывал весь
  трафик (502) — туннель ЗАМЕНЁН на nw2 (`a9cd9760-…`),
  DNS перепривязан `--overwrite-dns`; старый `257dd934-…` удалить
  после выключения старого сервера. Origin-порт **8030** (8020 на
  этом сервере занят Drawings Analyzer). Фоновый перезапуск:
  `_restart_nw.ps1` в корне того репо. Подробности и грабли (в т.ч.
  подмена имени туннеля дефолтным config.yml — использовать UUID) —
  `docs/MIGRATION.md` в репозитории North waterfront.
- **Установщик python.org виснет при тихой установке из агентской сессии**
  (процессы живы, CPU ~0, каталог не создаётся). Рабочий вариант:
  `winget install --id Python.Python.3.11 --version 3.11.9 --source winget
  --scope user --silent --accept-package-agreements --accept-source-agreements`.
- **Точный состав пакетов старого venv** собирается из dist-info до удаления
  venv (Name/Version из METADATA каждого `*.dist-info` → requirements) —
  ставится без дрейфа версий.
