/* DevBIM: брендовый баннер над интерфейсом приложения.
 *
 * Подключается тегом <script src="/devbim-banner.js" defer> в index.html
 * (деплоит rebrand_devbim.py). Содержимое:
 *   - кликабельная эмблема «devBIM - Design» -> сайт devbim.com
 *     (SITE_URL);
 *   - слоган справа; язык слогана следует за языком интерфейса приложения
 *     (срез system персистится redux-remember в IndexedDB «invoke» /
 *     «invoke-store», ключ «@@invokeai-system», поле language);
 *   - переключатель языка EN|RU: диспатчит system/languageChanged в стор
 *     приложения (глобал window.__devbimPEStore из патча App-бандла,
 *     фолбэк — мост холста / прямая запись в IndexedDB);
 *   - SSO/users: email пользователя + «Выйти» (локализуется).
 *
 * Дефолт языка — английский (как у приложения: system.language='en');
 * русский показывается, только когда он выбран в настройках/переключателе.
 *
 * Баннер — обычный блок перед #root; высота приложения (100dvh) компенсируется
 * в CSS ниже, поэтому интерфейс не уезжает вниз и не обрезается.
 */
(function () {
  'use strict';

  // Куда ведёт эмблема — поменять здесь
  var SITE_URL = 'https://devbim.com';

  var BANNER_H = '44px'; // высота баннера (и компенсации в #root)

  // --- слоган по языкам интерфейса (остальные -> en) ---
  var TEXTS = {
    ru: {
      tagline: 'Создавай реалистичные AI-рендеры интерьеров и фасадов зданий с высочайшей точностью…',
      site: 'Сайт DevBIM',
      logout: 'Выйти'
    },
    en: {
      tagline: 'Create realistic AI renders of interiors and building facades with the highest precision…',
      site: 'DevBIM website',
      logout: 'Log out'
    }
  };

  // --- стили: тёмная полоса бренда над интерфейсом ---
  var CSS =
    ':root{--devbim-banner-h:' + BANNER_H + '}' +
    '#devbim-banner{display:flex;align-items:center;gap:12px;height:var(--devbim-banner-h);' +
    'padding:0 14px;background:#111111;border-bottom:1px solid #2b2f35;' +
    'font-family:Inter,\'Segoe UI\',system-ui,sans-serif;user-select:none}' +
    '#devbim-banner a.devbim-logo{display:flex;align-items:center;' +
    'text-decoration:none;white-space:nowrap;cursor:pointer}' +
    '#devbim-banner a.devbim-logo:hover{filter:brightness(1.15)}' +
    '#devbim-banner .devbim-word{font-size:15.5px;font-weight:700;letter-spacing:.3px}' +
    '#devbim-banner .devbim-word .dev{color:#f2f4f6}' +
    '#devbim-banner .devbim-word .bim{color:#38BDF8}' +
    '#devbim-banner .devbim-word .design{color:#f2f4f6;font-weight:600}' +
    '#devbim-banner .devbim-tagline{flex:1;min-width:0;font-size:12.5px;color:#aab3ba;' +
    'white-space:nowrap;overflow:hidden;text-overflow:ellipsis}' +
    '#devbim-banner .devbim-lang{display:flex;align-items:center;border:1px solid #2b2f35;' +
    'border-radius:6px;overflow:hidden;white-space:nowrap}' +
    '#devbim-banner .devbim-lang button{background:transparent;color:#aab3ba;border:0;' +
    'padding:3px 10px;font-size:11.5px;font-weight:600;cursor:pointer;line-height:1.4}' +
    '#devbim-banner .devbim-lang button+button{border-left:1px solid #2b2f35}' +
    '#devbim-banner .devbim-lang button[data-active="1"]{background:#38BDF8;color:#06121C}' +
    '#devbim-banner .devbim-lang button:not([data-active="1"]):hover{color:#e6eaf2}' +
    '#devbim-banner .devbim-user{display:flex;align-items:center;gap:10px;white-space:nowrap;' +
    'font-size:12.5px;color:#E6EAF2}' +
    '#devbim-banner .devbim-user button{background:#38BDF8;color:#06121C;border:0;border-radius:6px;' +
    'padding:4px 10px;font-size:12px;font-weight:600;cursor:pointer}' +
    '#devbim-banner .devbim-user button:hover{background:#5CC9FA}' +
    '@media (max-width:640px){#devbim-banner .devbim-tagline{display:none}}' +
    /* приложение занимает 100dvh — сдвигаем и ужимаем под баннер */
    '#root{height:calc(100dvh - var(--devbim-banner-h))}' +
    '#invoke-app-wrapper{height:calc(100dvh - var(--devbim-banner-h))!important}';

  // --- эмблема «devBIM - Design» (без иконки: чистый текстовый вордмарк) ---

  var lang = 'en';   // до первого чтения настроек — английский (дефолт продукта)
  var els = {};

  function texts() { return TEXTS[lang] || TEXTS.en; }

  function render() {
    var t = texts();
    els.tagline.textContent = t.tagline;
    els.link.title = t.site;
    els.link.setAttribute('aria-label', t.site);
    if (els.out) els.out.textContent = t.logout;
    if (els.swEn) els.swEn.setAttribute('data-active', lang === 'en' ? '1' : '0');
    if (els.swRu) els.swRu.setAttribute('data-active', lang === 'ru' ? '1' : '0');
  }

  // --- язык интерфейса: IndexedDB «invoke» / «invoke-store» / «@@invokeai-system» ---
  // ВАЖНО (грабля 08.10): открывать базу БЕЗ создания. Простой
  // indexedDB.open('invoke') на свежем профиле браузера создаёт пустую
  // базу версии 1 РАНЬШЕ приложения — и redux-remember навсегда теряет
  // хранилище (upgrade при равной версии не выполняется). Поэтому при
  // создании базы откатываем транзакцию, а без стора «invoke-store»
  // просто читаем null (язык возьмётся после загрузки приложения).
  function openInvoke(cb) {
    var req;
    try { req = indexedDB.open('invoke'); } catch (e) { cb(null); return; }
    req.onupgradeneeded = function (ev) {
      if (ev.oldVersion === 0) {          // базу создаём мы — не надо
        try { req.transaction.abort(); } catch (e) { /* ничего */ }
      }
    };
    req.onsuccess = function () {
      var db = req.result;
      if (!db.objectStoreNames.contains('invoke-store')) {
        db.close();
        cb(null);
        return;
      }
      cb(db);
    };
    req.onerror = function () { cb(null); };
    req.onblocked = function () { cb(null); };
  }

  function readLanguage(cb) {
    openInvoke(function (db) {
      if (!db) { cb(null); return; }
      var get;
      try {
        get = db.transaction('invoke-store', 'readonly')
          .objectStore('invoke-store').get('@@invokeai-system');
      } catch (e) { cb(null); return; }
      get.onsuccess = function () {
        try { cb(JSON.parse(get.result).language || null); }
        catch (e) { cb(null); }
      };
      get.onerror = function () { cb(null); };
    });
  }

  // фолбэк переключателя, когда стор ещё не готов: пишем язык прямо в
  // persisted-стейт — приложение подхватит его при следующей загрузке
  function writeLanguage(l) {
    openInvoke(function (db) {
      if (!db) return;
      var os;
      try { os = db.transaction('invoke-store', 'readwrite').objectStore('invoke-store'); }
      catch (e) { return; }
      var get = os.get('@@invokeai-system');
      get.onsuccess = function () {
        if (!get.result) return;
        try {
          var doc = JSON.parse(get.result);
          doc.language = l;
          os.put(JSON.stringify(doc), '@@invokeai-system');
        } catch (e) { /* не критично */ }
      };
    });
  }

  // сменить язык интерфейса приложения: диспатч в редакс-стор приложения
  // (глобал держит патч DevbimPEWatch в App-бандле; там же, где очередь)
  function appStore() {
    if (window.__devbimPEStore && window.__devbimPEStore.dispatch) {
      return window.__devbimPEStore;
    }
    try {
      var m = window.__devbimCanvasBridge && window.__devbimCanvasBridge.getManager();
      if (m && m.stateApi && m.stateApi.store && m.stateApi.store.dispatch) {
        return m.stateApi.store;
      }
    } catch (e) { /* моста нет — не страшно */ }
    return null;
  }

  function setLanguage(l) {
    if (!TEXTS[l]) return;
    lang = l;
    render();
    var st = appStore();
    if (st) {
      try {
        // App слушает system.language и зовёт i18n.changeLanguage —
        // интерфейс переводится сразу; redux-remember сам персистит выбор
        st.dispatch({ type: 'system/languageChanged', payload: l });
        return;
      } catch (e) { /* ниже — фолбэк */ }
    }
    writeLanguage(l);
  }

  function pollLanguage() {
    readLanguage(function (l) {
      if (l && l !== lang) { lang = l; render(); }
    });
  }

  // --- SSO/users: email пользователя + «Выйти»/«Log out» ---
  function loadUser(banner) {
    fetch('/api/v1/studio/me', { credentials: 'same-origin' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) {
        if (!d || (d.mode !== 'sso' && d.mode !== 'users') || !d.user_id) return;
        var chip = document.createElement('span');
        chip.className = 'devbim-user';
        var who = document.createElement('span');
        who.textContent = d.email || d.name || d.user_id;
        if (d.role === 'admin') who.textContent += ' · admin';
        var out = document.createElement('button');
        out.type = 'button';
        out.textContent = texts().logout;
        out.onclick = function () { location.href = '/auth/logout'; };
        chip.appendChild(who);
        chip.appendChild(out);
        banner.appendChild(chip);
        els.out = out;
      })
      .catch(function () { /* без панели — не страшно */ });
  }

  function init() {
    var st = document.createElement('style');
    st.textContent = CSS;
    document.head.appendChild(st);

    var banner = document.createElement('div');
    banner.id = 'devbim-banner';

    var link = document.createElement('a');
    link.className = 'devbim-logo';
    link.href = SITE_URL;
    link.target = '_blank';
    link.rel = 'noopener';
    link.innerHTML =
      '<span class="devbim-word"><span class="dev">dev</span><span class="bim">BIM</span>' +
      '<span class="design"> - Design</span></span>';

    var tagline = document.createElement('span');
    tagline.className = 'devbim-tagline';

    // --- переключатель языка интерфейса EN|RU ---
    var sw = document.createElement('div');
    sw.className = 'devbim-lang';
    var mk = function (code, label) {
      var b = document.createElement('button');
      b.type = 'button';
      b.textContent = label;
      b.setAttribute('data-active', '0');
      b.onclick = function () { setLanguage(code); };
      sw.appendChild(b);
      return b;
    };
    var swEn = mk('en', 'EN');
    var swRu = mk('ru', 'RU');

    banner.appendChild(link);
    banner.appendChild(tagline);
    banner.appendChild(sw);
    loadUser(banner);

    var root = document.getElementById('root');
    root.parentNode.insertBefore(banner, root);

    els.link = link;
    els.tagline = tagline;
    els.swEn = swEn;
    els.swRu = swRu;
    render();

    pollLanguage();
    setInterval(pollLanguage, 1000);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
