/* DevBIM: админский доступ к «Менеджеру моделей» и шестерёнке «Настройки».
 *
 * Подключается тегом <script src="/devbim-admin.js" defer> в index.html
 * (патчит setup_imagerouter.py). Сотрудничает с патчами бандла:
 *   - switchToTab("models") при заблокированном доступе вызывает
 *     window.__devbimGuardModels() вместо переключения вкладки;
 *   - в меню (группа «Настройки») добавлен пункт «Model Manager»,
 *     клик по которому вызывает window.__devbimOpenModels().
 *
 * Доступ по роли сессии студии (GET /api/v1/studio/me, режимы users/sso):
 *   - role=admin  — шестерёнка «Настройки» и «Model Manager» открываются
 *                   СРАЗУ, без пароля (админ уже вошёл своей учёткой);
 *   - role=user   — пункты «Настройки» и «Model Manager» СКРЫТЫ из меню
 *                   (MutationObserver прячет их при каждом открытии меню),
 *                   клик по ним через обходные пути — алерт «только админ»;
 *   - password-режим (компании, /me отдаёт 404) — прежняя логика: пароль
 *     ADMIN_PASSWORD из .env через POST /api/v1/imagerouter/admin-auth,
 *     разблокировка до перезагрузки страницы.
 */
(function () {
  'use strict';

  // «Настройки» во всех локалях интерфейса (ключ common.settingsLabel) —
  // по этому тексту ловим клик по шестерёнке в меню.
  var SETTINGS_LABELS = [
    'Ajustes', 'Asetukset', 'Configurações', 'Cài Đặt', 'Einstellungen',
    'Impostazioni', 'Instellingen', 'Inställningar', 'Paramètres', 'Settings',
    'Seçenekler', 'Ustawienia', 'Налаштування', 'Настройки',
    'הגדרות', 'إعدادات', '設定', '设置', '설정'
  ];

  var AUTH_URL = '/api/v1/imagerouter/admin-auth';

  // --- роль сессии студии из /api/v1/studio/me (режимы users и sso) ---
  var studioRole = null;  // 'admin' | 'user' | null (password-режим или ошибка)
  var roleTries = 0;

  // Пункты меню, скрытые у role=user: шестерёнка «Настройки» и «Model Manager».
  var HIDDEN_ITEMS = ['Model Manager'];

  function applyRole(role) {
    studioRole = role;
    if (role === 'admin') {
      // админ уже аутентифицирован сессией студии — пароль не спрашиваем
      unlocked = true;
      window.__devbimUnlocked = true;
    } else if (role === 'user') {
      hideAdminMenuItems();
      if (!hideObserver) {
        hideObserver = new MutationObserver(hideAdminMenuItems);
        hideObserver.observe(document.body, { childList: true, subtree: true });
      }
    }
  }

  function warmRole() {
    fetch('/api/v1/studio/me', { credentials: 'same-origin' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) {
        var role = (d && (d.mode === 'users' || d.mode === 'sso')) ? d.role : null;
        if (!role && roleTries < 3) { roleTries++; setTimeout(warmRole, 1500); return; }
        applyRole(role);
      })
      .catch(function () {
        if (roleTries < 3) { roleTries++; setTimeout(warmRole, 1500); }
      });
  }

  // --- скрытие пунктов меню у role=user ------------------------------------
  // Меню рендерится лениво (при открытии), поэтому прячем по MutationObserver.
  // Прячем сам пункт [role=menuitem] и его обёртку, если в ней один пункт
  // (шестерёнка «Настройки» обёрнута в компонент с модалкой).
  function hideAdminMenuItems() {
    if (studioRole !== 'user') return;
    var items = document.querySelectorAll('[role="menuitem"]');
    for (var i = 0; i < items.length; i++) {
      var el = items[i];
      if (el.getAttribute('data-devbim-admin-hidden')) continue;
      var txt = (el.textContent || '').replace(/\s+/g, ' ').trim();
      if (SETTINGS_LABELS.indexOf(txt) === -1 && HIDDEN_ITEMS.indexOf(txt) === -1) continue;
      el.setAttribute('data-devbim-admin-hidden', '1');
      var node = el;
      var p = node.parentElement;
      if (p && p.querySelectorAll('[role="menuitem"]').length === 1) node = p;
      node.style.display = 'none';
    }
  }

  var hideObserver = null;

  var unlocked = false;      // разблокировка действует до перезагрузки страницы
  var protectedCache = null; // настроен ли ADMIN_PASSWORD (кэш ответа сервера)
  var bypassClick = false;   // программный «повторный» клик после разблокировки

  // --- стили модального окна (тёмная тема DevBIM, акцент #38BDF8) ---
  var CSS =
    '.devbim-admin-overlay{position:fixed;inset:0;background:rgba(0,0,0,.62);' +
    'display:flex;align-items:center;justify-content:center;z-index:999999;' +
    'font-family:Inter,\'Segoe UI\',system-ui,sans-serif}' +
    '.devbim-admin-card{width:360px;max-width:calc(100vw - 32px);background:#161616;' +
    'border:1px solid #2f2f2f;border-radius:12px;padding:26px 24px 22px;' +
    'box-shadow:0 18px 50px rgba(0,0,0,.55);color:#e8e8e8}' +
    '.devbim-admin-title{font-size:17px;font-weight:600;margin:0 0 6px}' +
    '.devbim-admin-sub{font-size:13px;color:#9a9a9a;margin:0 0 16px;line-height:1.45}' +
    '.devbim-admin-input{width:100%;box-sizing:border-box;background:#0d0d0d;' +
    'border:1px solid #3a3a3a;border-radius:8px;color:#f2f2f2;font-size:14px;' +
    'padding:10px 12px;outline:none}' +
    '.devbim-admin-input:focus{border-color:#38BDF8}' +
    '.devbim-admin-err{color:#f87171;font-size:12.5px;min-height:17px;margin:8px 0 2px}' +
    '.devbim-admin-row{display:flex;gap:10px;justify-content:flex-end;margin-top:14px}' +
    '.devbim-admin-btn{border:none;border-radius:8px;font-size:14px;padding:9px 16px;' +
    'cursor:pointer;font-weight:500}' +
    '.devbim-admin-cancel{background:transparent;color:#b9b9b9;border:1px solid #3a3a3a}' +
    '.devbim-admin-cancel:hover{background:#222}' +
    '.devbim-admin-ok{background:#38BDF8;color:#0b1520}' +
    '.devbim-admin-ok:hover{background:#5cc5fa}' +
    '.devbim-admin-ok:disabled{opacity:.6;cursor:default}' +
    '.devbim-admin-notice{position:fixed;left:50%;bottom:26px;transform:translateX(-50%);' +
    'background:#1c1c1c;border:1px solid #3a3a3a;color:#e8e8e8;padding:10px 18px;' +
    'border-radius:8px;font-size:13px;z-index:999999;white-space:nowrap;' +
    'box-shadow:0 8px 30px rgba(0,0,0,.5)}';

  function injectStyles() {
    var st = document.createElement('style');
    st.textContent = CSS;
    document.head.appendChild(st);
  }

  // --- проверка пароля на сервере ---
  function isProtected(cb) {
    if (protectedCache !== null) { cb(protectedCache); return; }
    fetch(AUTH_URL)
      .then(function (r) { return r.ok ? r.json() : { protected: true }; })
      .then(function (d) { protectedCache = !!d.protected; cb(protectedCache); })
      .catch(function () { protectedCache = true; cb(true); });
  }

  function verifyPassword(password, onOk, onFail) {
    fetch(AUTH_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password: password })
    }).then(function (r) {
      if (r.ok) { onOk(); }
      else { r.json().catch(function () { return {}; }).then(function (d) {
        onFail((d && d.detail) || 'Wrong password');
      }); }
    }).catch(function () { onFail('Server unavailable'); });
  }

  // --- модальное окно ввода пароля ---
  function askPassword(onSuccess) {
    var prev = document.querySelector('.devbim-admin-overlay');
    if (prev) prev.remove();

    var overlay = document.createElement('div');
    overlay.className = 'devbim-admin-overlay';

    var card = document.createElement('div');
    card.className = 'devbim-admin-card';

    var title = document.createElement('h3');
    title.className = 'devbim-admin-title';
    title.textContent = 'Administrator sign-in';

    var sub = document.createElement('p');
    sub.className = 'devbim-admin-sub';
    sub.textContent = 'Enter the administrator password to open protected sections (Model Manager).';

    var input = document.createElement('input');
    input.type = 'password';
    input.className = 'devbim-admin-input';
    input.placeholder = 'Password';
    input.autocomplete = 'current-password';

    var err = document.createElement('div');
    err.className = 'devbim-admin-err';

    var row = document.createElement('div');
    row.className = 'devbim-admin-row';

    var btnCancel = document.createElement('button');
    btnCancel.type = 'button';
    btnCancel.className = 'devbim-admin-btn devbim-admin-cancel';
    btnCancel.textContent = 'Cancel';

    var btnOk = document.createElement('button');
    btnOk.type = 'button';
    btnOk.className = 'devbim-admin-btn devbim-admin-ok';
    btnOk.textContent = 'Sign in';

    row.appendChild(btnCancel);
    row.appendChild(btnOk);
    card.appendChild(title);
    card.appendChild(sub);
    card.appendChild(input);
    card.appendChild(err);
    card.appendChild(row);
    overlay.appendChild(card);
    document.body.appendChild(overlay);
    setTimeout(function () { input.focus(); }, 30);

    function close() { overlay.remove(); }
    function submit() {
      var val = input.value;
      if (!val) { input.focus(); return; }
      btnOk.disabled = true;
      btnOk.textContent = 'Checking…';
      err.textContent = '';
      verifyPassword(val, function () {
        unlocked = true;
        window.__devbimUnlocked = true;
        close();
        onSuccess();
      }, function (msg) {
        btnOk.disabled = false;
        btnOk.textContent = 'Sign in';
        err.textContent = msg;
        input.select();
      });
    }

    btnOk.addEventListener('click', submit);
    input.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') { e.preventDefault(); submit(); }
    });
    btnCancel.addEventListener('click', close);
    overlay.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') { e.preventDefault(); close(); }
    });

    // Глотаем указательные события, чтобы открытое меню под оверлеем не
    // закрылось как «клик мимо» — после ввода пароля мы «нажимаем» его пункт ещё раз.
    ['mousedown', 'pointerdown', 'touchstart'].forEach(function (type) {
      overlay.addEventListener(type, function (e) { e.stopPropagation(); });
    });
  }

  // Ненавязчивое уведомление вместо блокирующего alert(): гейт может
  // сработать в фоне при загрузке страницы (восстановление вкладки «models»
  // из localStorage) — alert() в этот момент замораживал ВСЁ приложение.
  function notifyBlocked() {
    var prev = document.querySelector('.devbim-admin-notice');
    if (prev) prev.remove();
    var n = document.createElement('div');
    n.className = 'devbim-admin-notice';
    n.textContent = 'Model Manager и настройки доступны только администратору';
    document.body.appendChild(n);
    setTimeout(function () { n.remove(); }, 2600);
  }

  function ensureUnlocked(onSuccess) {
    if (studioRole === 'admin') { unlocked = true; window.__devbimUnlocked = true; onSuccess(); return; }
    if (studioRole === 'user') { notifyBlocked(); return; }
    isProtected(function (on) {
      if (!on || unlocked) { if (on) window.__devbimUnlocked = true; onSuccess(); return; }
      askPassword(onSuccess);
    });
  }

  function switchTab(name) {
    if (typeof window.__devbimSwitchTab === 'function') window.__devbimSwitchTab(name);
  }

  // закрыть висящее меню (клик «мимо» на уровне документа)
  function dismissMenus() {
    try {
      document.body.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
      document.body.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
    } catch (e) { /* ничего */ }
  }

  // охрана switchToTab("models") из бандла (кнопки в UI вне меню)
  window.__devbimGuardModels = function () {
    ensureUnlocked(function () {
      switchTab('models');
      dismissMenus();
    });
  };
  // пункт меню «Менеджер моделей» (добавляется патчем бандла)
  window.__devbimOpenModels = window.__devbimGuardModels;

  // --- шестерёнка: клик по пункту «Настройки» требует пароля ---
  document.addEventListener('click', function (ev) {
    if (bypassClick || unlocked) return;
    var target = ev.target;
    var el = target && target.closest ? target.closest('[role="menuitem"]') : null;
    if (!el) return;
    var txt = (el.textContent || '').replace(/\s+/g, ' ').trim();
    if (SETTINGS_LABELS.indexOf(txt) === -1) return;
    if (protectedCache === false && studioRole !== 'user') return; // защиты нет и не юзер студии — пропускаем
    // блокируем клик сразу (статус защиты узнаем асинхронно)
    ev.stopPropagation();
    ev.preventDefault();
    isProtected(function () {
      ensureUnlocked(function () {
        // открываем настройки повторным «нажатием» того же пункта меню
        bypassClick = true;
        try { el.click(); } catch (e) { /* меню могло закрыться — не критично */ }
        bypassClick = false;
      });
    });
  }, true);

  // --- если после перезагрузки страницы восстановилась вкладка «Модели» —
  //     возвращаем пользователя на генерацию, пока не введён пароль ---
  var attempts = 0;
  var poll = setInterval(function () {
    attempts++;
    if (typeof window.__devbimGetTab === 'function') {
      clearInterval(poll);
      if (!unlocked && window.__devbimGetTab() === 'models') switchTab('generate');
    } else if (attempts > 120) {
      clearInterval(poll);
    }
  }, 500);

  injectStyles();
  isProtected(function () {}); // прогрев кэша статуса защиты
  warmRole(); // прогрев кэша роли студии
})();
