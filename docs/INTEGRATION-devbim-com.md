# Интеграция Image Studio в devbim.com — ТЗ для основного сервиса

Студия: https://studio.devbim.com (отдельный сервис, iframe внутри кабинета).

## 1. Эндпоинт токена (бэкенд devbim.com)

Выдаёт JWT для iframe-авторизации студии; доступен только авторизованному
(Google-сессия) пользователю.

- JWT HS256, секрет ≥32 символов — передаётся администратору студии вне канала
  и совпадает с `STUDIO_JWT_SECRET` в .env студии.
- Claims: `sub` (ID пользователя сайта, строка), `email`, `name` (опц.),
  `picture` (опц.), `role`: `"admin"|"user"` (email'ы devBIM → admin),
  `iat`, `exp` (= iat + ≤600 с, рекомендуем 300 с), `jti` (UUID, одноразовость).
- Рекомендуемое имя: `GET /api/studio-token` → `{"token": "...", "url": "https://studio.devbim.com"}`.

## 2. Страница кабинета `/designing/image-studio`

1. При открытии (и при перезагрузке iframe): fetch токена со своего бэкенда.
2. `iframe.src = "https://studio.devbim.com/auth/sso?t=" + token`.
3. Атрибуты: `allow="clipboard-write; fullscreen"`, `referrerpolicy="no-referrer"`,
   высота — во весь экран контента, `border: 0`.
4. Никаких своих куки студии не нужно — студия ставит свои (same-site: оба на devbim.com).

## 3. DNS

`studio.devbim.com` → сервер/туннель студии (CNAME; согласовать с администратором студии).

## 4. SHOULD: авто-обновление сессии

Студия при истёкшей сессии шлёт в родитель `postMessage('studio:expired', '*')`
и показывает страницу «войдите заново». Рекомендуется слушать событие и
перезагружать iframe с новым токеном:

    window.addEventListener('message', (e) => {
      if (e.data === 'studio:expired') reloadIframeWithFreshToken();
    });

## 5. Что НЕ надо делать

- Не встраивать студию на другие домены (CSP `frame-ancestors` это заблокирует).
- Не кэшировать токен дольше его `exp`; не логгировать URL с `?t=`.
- Не передавать токен третьим сторонам — он даёт вход в аккаунт пользователя.
