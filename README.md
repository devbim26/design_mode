# DevBIM Image Studio (на базе InvokeAI 6.2.0)

Локальная установка InvokeAI 6.2.0 в CPU-режиме (API + веб-интерфейс)
с ребрендингом под **DevBIM** («Dev» — чёрный, «BIM» — голубой `#38BDF8`,
ссылки — на `devbim.com`).

## Структура

| Путь | Назначение |
|---|---|
| `rebrand_devbim.py` | Скрипт ребрендинга: названия, ссылки, цвета, логотипы |
| `data/invokeai.yaml` | Конфиг сервера (host 127.0.0.1, port 9090, CPU, float32) |
| `docs/` | Скриншоты интерфейса после ребрендинга |

Остальное (`venv/`, `data/`, логи) — генерируется установкой и в git не входит.
Оригинальный фронтенд до ребрендинга сохранён в `dist_original_backup/`.

## Установка (с нуля)

```powershell
mkdir C:\InvokeAI; cd C:\InvokeAI
python -m venv venv                     # Python 3.11
.\venv\Scripts\python.exe -m pip install --upgrade pip
.\venv\Scripts\python.exe -m pip install "invokeai[cpu]" --use-pep517
```

Примечание: в InvokeAI 6.x утилита `invokeai-configure` удалена — структура
каталога `data/` создаётся автоматически при первом запуске `invokeai-web`.

## Конфигурация

`data/invokeai.yaml` обязан начинаться со станзы `schema_version: 4.0.2` —
без неё сервер не стартует. Секция `remote_api` (openai_api_key/base) в
InvokeAI не поддерживается и отвергается валидатором — не добавлять.

## Запуск

```powershell
cd C:\InvokeAI
$env:INVOKEAI_ROOT="C:\InvokeAI\data"
.\venv\Scripts\invokeai-web.exe
```

Веб-интерфейс и Swagger API: `http://127.0.0.1:9090` (`/docs`, `/api/v1/...`).

## Ребрендинг

Скрипт правит собранный фронтенд в `venv/Lib/site-packages/invokeai/frontend/web/dist`
и два файла бэкенда. Идемпотентен: после обновления пакета (`pip install -U invokeai`)
запустите его повторно:

```powershell
C:\InvokeAI\venv\Scripts\python.exe C:\InvokeAI\rebrand_devbim.py
```

Что делает:

- заголовок вкладки → `DevBIM`; баннер консоли → `DevBIM running on ...`;
- тексты интерфейса во всех 25 языках: `Invoke`/`InvokeAI` → `DevBIM`
  (значения локалей; ключи и технические идентификаторы не трогает);
- все внешние ссылки (docs, support, github, discord, youtube, баг-репорты)
  → `https://devbim.com`;
- цвета бренда: жёлтый `#E6FD13` → голубой `#38BDF8`; логотипы/фавиконы
  перегенерируются двухцветными (Dev — `#111111`, BIM — `#38BDF8`).

Откат: скопировать содержимое `dist_original_backup/` обратно в
`venv/Lib/site-packages/invokeai/frontend/web/dist` и восстановить
`*.devbim-bak` файлы бэкенда.

Модели Stable Diffusion не устанавливались (облегчённый режим): для генерации
добавьте модель через Model Manager или `/api/v1/models/install`.
