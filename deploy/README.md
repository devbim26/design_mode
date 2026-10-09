# DevBIM в Docker

Linux-контейнер amd64 с Python 3.11, InvokeAI 6.2.0 и CPU PyTorch.
Compose собирает локальный образ `acoustic/devbim-design:latest`.
На Windows нужен Docker Desktop с Linux containers / WSL2 и Docker Compose v2.
На Linux — Docker Engine и Compose v2. Python и Node.js на хосте не нужны.

## Первый запуск

Из PowerShell:

```powershell
cd "C:\Users\user\source\pythonRepos\DesignViktor\design_mode\deploy"
Copy-Item .env.example .env
docker run --rm python:3.11-slim-bookworm python -c "import secrets; print(secrets.token_hex(32))"
```

В `deploy/.env` задать:

- `SITE_PASSWORD` — собственный пароль владельца;
- `STUDIO_SESSION_SECRET` — полученный случайный секрет; сохранить его между обновлениями;
- `IMAGEROUTER_API_KEY` — ключ владельца для облачной генерации (можно оставить пустым для проверки интерфейса).

Затем:

```powershell
docker compose config --quiet
docker compose up -d --build
docker compose logs -f studio
```

Открыть http://localhost:9090. В режиме `users` email владельца оставить
пустым, пароль — `SITE_PASSWORD`. Панель пользователей: http://localhost:9090/admin.
Обычным пользователям администратор задаёт собственные ключи ImageRouter;
глобальный ключ для них не подставляется.

Из корня проекта те же команды запускаются с `-f deploy/compose.yaml`.
Файл `deploy/.env` подключается через `env_file`; значения `${...}` Compose
берёт из `.env` рядом с первым Compose-файлом, если явно не задан иной `--env-file`.
Для однозначного выбора можно использовать:

```powershell
docker compose --env-file deploy/.env -f deploy/compose.yaml up -d --build
```

При первом запуске возможны загрузки дополнительных ресурсов InvokeAI.
Сборке нужен доступ к PyPI, download.pytorch.org и Debian repositories;
генерации — к ImageRouter, скачиванию моделей/ресурсов — к HuggingFace.
GPU и локальная Stable Diffusion модель для облачного сценария не требуются.

## Что делает сборка

Все девять патчей выполняются в Dockerfile в установленном порядке,
`setup_navbar_labels.py` — последним. Скрипты используют один общий
`package_layout.py` для определения Windows/Linux `site-packages`.
`--no-env` запрещает создание `.env` при сборке; `--no-db-sync` исключает
синхронизацию пользовательской БД при установке пресетов.

Сборка проверяет наличие интеграций, компиляцию Python, синтаксис изменённых
JS-бандлов, новые тесты контейнерного запуска и существующие тесты входа,
пресетов и 3D.
Тест пресетов использует временную SQLite-базу: образ собирается до первого
запуска InvokeAI, поэтому рабочая БД в этот момент ещё не существует.
Node.js, исходники тестов и инструменты сборки остаются в build-стадии.
В runtime установлены необходимые нативные библиотеки, приложение работает
под UID/GID 10001. Исполняется один процесс InvokeAI, `exec` и Docker init
обеспечивают доставку сигналов и сбор дочерних процессов.

`requirements.txt` фиксирует основные зависимости и версии библиотек,
чувствительных к InvokeAI 6.2; полного lock-файла транзитивных зависимостей
пока нет. Linux-сборка и полная проверка интерфейса должны быть выполнены
на машине с доступным Docker перед серверным развёртыванием.

## Конфигурация

В `.env.example` перечислены настройки приложения, включая SSO, срок
лицензии, внешний Design Code, помощник промптов и 3D-конвейер.
Секреты не встраиваются в образ. `.env` исключён из git и build context.
Переменные окружения контейнера доступны администраторам Docker;
доступ к хосту и конфигурации должен быть ограничен.

| Переменная | Поведение |
|---|---|
| `STUDIO_AUTH_MODE` | `users` по умолчанию; также `password`, `sso` |
| `SITE_PASSWORD` | Обязательный пароль владельца |
| `STUDIO_SESSION_SECRET` | Обязательный секрет от 32 символов |
| `STUDIO_SESSION_TTL` | Срок сессии, по умолчанию 43200 секунд |
| `STUDIO_FRAME_ANCESTORS` | Разрешённые сайты для встраивания в iframe |
| `SITE_VALID_UNTIL` | Дата окончания лицензии; пусто — без срока |
| `IMAGEROUTER_API_KEY` | Глобальный ключ владельца; для UI необязателен |
| `ADMIN_PASSWORD` | Обязателен для менеджера моделей в режиме `password` |
| `STUDIO_JWT_SECRET` | В `sso` обязателен общий с сайтом секрет от 32 символов |
| `DESIGN_CODE_URL`, `DESIGN_CODE_ACCESS_CODE` | Внешний сайт дизайн-кода и код доступа |
| `PROMPT_ENHANCER_MODEL` | Необязательный ID модели помощника промптов |
| `THREED_MODEL` | Общий override модели стадий 3D |
| `THREED_*_MODEL` | Необязательные модели отдельных стадий и ансамбля |
| `THREED_VERIFY`, `THREED_VERIFY_ITERS` | Самопроверка и количество итераций |
| `THREED_ENSEMBLE`, `THREED_MAX_CALLS_PER_ATTEMPT` | Ансамбль и бюджет вызовов |
| `STUDIO_BIND_IP`, `STUDIO_PORT` | Адрес и порт публикации на хосте |

Закомментированные ID моделей не задаются: приложение использует свои
дефолты или сохранённый в админке выбор. Для платной генерации выбрать
модель из актуального каталога ImageRouter. Пустая активная переменная
`THREED_ESCALATION_MODEL` отключает эскалацию; не раскомментировать её
без необходимости. Сохранённый выбор моделей может иметь приоритет над env.

После изменения `deploy/.env` выполнить `docker compose up -d`:
Compose пересоздаст контейнер с новыми значениями. `docker compose restart`
не обновляет environment. Не помещать второй `.env` в `/data` или `/app`:
модули приложения могут отдавать ему приоритет над окружением; entrypoint
останавливается с объяснением при обнаружении такого файла.

## Данные и управление

Named volume `devbim_studio-data` подключён в `/data` и содержит всё:
пользователей `/data/data/studio.sqlite`, БД InvokeAI, галерею, IFC, PDF,
настройки моделей и кэш. Конфигурация `/data/invokeai.yaml` создаётся
при первом старте; существующий конфиг сохраняет остальные настройки,
а host/port/device/precision нормализуются для контейнера: `0.0.0.0`,
9090, cpu, float32. При переносе проверить абсолютные пути старого Windows-конфига.

CLI нужно передавать корень данных явно:

```powershell
docker compose exec studio python user_manager.py list --root /data
docker compose exec studio python user_manager.py add ivan@example.com --root /data
docker compose ps
docker compose down
```

`down` сохраняет volume. `down -v` удаляет данные и не используется
для обычного обновления. Статусы незавершённых 3D-задач живут в памяти
и теряются при рестарте; готовые IFC-файлы сохраняются.

## Перенос существующих данных и резервное копирование

Старый экземпляр остановить. Для согласованной копии SQLite переносить
всю папку `data`, включая журналы, а не только файл studio.sqlite.
Пароли и токены пользователей хранятся в этой БД; конфигурацию владельца
перенести из старого `.env` в `deploy/.env`.

После сборки можно скопировать старые данные в volume через остановленный
контейнер (команды выполнять из `deploy`, `../data` — исходная папка проекта):

```powershell
docker compose create studio
docker compose cp ../data/. studio:/data
docker compose run --rm --no-deps --user 0 --entrypoint python studio -c "import os; from pathlib import Path; p=Path('/data'); os.chown(p,10001,10001); [(os.chown(x,10001,10001)) for x in p.rglob('*') if not x.is_symlink()]"
docker compose up -d
```

Не смешивать этот импорт с уже заполненным volume другого экземпляра.
Если восстанавливается другой backup — использовать отдельный Compose project
с новым volume. При изменении имени проекта учесть, что имя volume меняется.

Backup в новый каталог:

```powershell
docker compose stop studio
docker compose cp studio:/data ./backup-data
docker compose start studio
```

Сохранить `deploy/.env` отдельно. Проверять восстановление на отдельном
экземпляре. Это также важно перед обновлением: откат образа не откатывает
миграции БД. Backup с персональными ключами пользователей требует такого
же ограничения доступа, как `.env`.

## Сервер

Использовать тот же образ и отдельную серверную `.env`. По умолчанию порт
доступен только на localhost хоста. Для прямого сетевого доступа поменять
`STUDIO_BIND_IP`; для постоянного публичного сервиса настроить HTTPS
через reverse proxy либо Cloudflare Tunnel.

Если cloudflared работает на хосте, origin — `http://localhost:9090`.
Если он в контейнере той же Compose-сети, origin — `http://studio:9090`.
Credentials существующего туннеля задаются отдельно; Windows-батники
запуска и туннеля в контейнере не используются.

Сначала один экземпляр приложения. Для отдельной компании — отдельный
Compose project с отдельными конфигурацией и volume. Реплики на общей БД
и перенос очереди задач требуют отдельной доработки.

Проверка перед публикацией: вход владельца/пользователя, изоляция данных,
IFC/PDF, снимок на холст, облачная генерация, 3D, пересоздание контейнера
без потери данных и восстановление backup. Healthcheck проверяет только
ответ страницы входа, а не доступность ImageRouter или стоимость генерации.
