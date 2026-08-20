/* DevBIM: брендовый баннер над интерфейсом приложения.
 *
 * Подключается тегом <script src="/devbim-banner.js" defer> в index.html
 * (деплоит rebrand_devbim.py). Содержимое:
 *   - кликабельный логотип DevBIM -> страница регистрации (REG_URL, заглушка);
 *   - слоган справа; язык слогана следует за языком интерфейса приложения
 *     (срез system персистится redux-remember в IndexedDB «invoke» /
 *     «invoke-store», ключ «@@invokeai-system», поле language).
 *
 * Баннер — обычный блок перед #root; высота приложения (100dvh) компенсируется
 * в CSS ниже, поэтому интерфейс не уезжает вниз и не обрезается.
 */
(function () {
  'use strict';

  // Страница регистрации — заглушка, поменять здесь
  var REG_URL = 'https://devbim.com/register';

  var BANNER_H = '44px'; // высота баннера (и компенсации в #root)

  // --- слоган по языкам интерфейса (остальные -> en) ---
  var TEXTS = {
    ru: {
      tagline: 'Создавай реалистичные AI-рендеры интерьеров и фасадов зданий с высочайшей точностью…',
      signup: 'Регистрация'
    },
    en: {
      tagline: 'Create realistic AI renders of interiors and building facades with the highest precision…',
      signup: 'Sign up'
    }
  };

  // --- стили: тёмная полоса бренда над интерфейсом ---
  var CSS =
    ':root{--devbim-banner-h:' + BANNER_H + '}' +
    '#devbim-banner{display:flex;align-items:center;gap:12px;height:var(--devbim-banner-h);' +
    'padding:0 14px;background:#111111;border-bottom:1px solid #2b2f35;' +
    'font-family:Inter,\'Segoe UI\',system-ui,sans-serif;user-select:none}' +
    '#devbim-banner a.devbim-logo{display:flex;align-items:center;gap:8px;' +
    'text-decoration:none;white-space:nowrap;cursor:pointer}' +
    '#devbim-banner a.devbim-logo:hover{filter:brightness(1.15)}' +
    '#devbim-banner .devbim-word{font-size:15.5px;font-weight:700;letter-spacing:.3px}' +
    '#devbim-banner .devbim-word .dev{color:#f2f4f6}' +
    '#devbim-banner .devbim-word .bim{color:#38BDF8}' +
    '#devbim-banner .devbim-tagline{flex:1;min-width:0;font-size:12.5px;color:#aab3ba;' +
    'white-space:nowrap;overflow:hidden;text-overflow:ellipsis}' +
    '@media (max-width:640px){#devbim-banner .devbim-tagline{display:none}}' +
    /* приложение занимает 100dvh — сдвигаем и ужимаем под баннер */
    '#root{height:calc(100dvh - var(--devbim-banner-h))}' +
    '#invoke-app-wrapper{height:calc(100dvh - var(--devbim-banner-h))!important}';

  // --- разметка баннера ---
  var LOGO_SVG =
    '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">' +
    '<path d="M12 2 21 7v10l-9 5-9-5V7l9-5z" stroke="#38BDF8" stroke-width="1.7" stroke-linejoin="round"/>' +
    '<path d="M12 12 21 7M12 12v10M12 12 3 7" stroke="#38BDF8" stroke-width="1.7" stroke-linejoin="round"/></svg>';

  var lang = 'ru';   // до первого чтения настроек — русский
  var els = {};

  function texts() { return TEXTS[lang] || TEXTS.en; }

  function render() {
    var t = texts();
    els.tagline.textContent = t.tagline;
    els.link.title = t.signup;
    els.link.setAttribute('aria-label', 'DevBIM — ' + t.signup);
  }

  // --- язык интерфейса: IndexedDB «invoke» / «invoke-store» / «@@invokeai-system» ---
  function readLanguage(cb) {
    var req;
    try { req = indexedDB.open('invoke'); } catch (e) { cb(null); return; }
    req.onsuccess = function () {
      var db = req.result;
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
    };
    req.onerror = function () { cb(null); };
  }

  function pollLanguage() {
    readLanguage(function (l) {
      if (l && l !== lang) { lang = l; render(); }
    });
  }

  function init() {
    var st = document.createElement('style');
    st.textContent = CSS;
    document.head.appendChild(st);

    var banner = document.createElement('div');
    banner.id = 'devbim-banner';

    var link = document.createElement('a');
    link.className = 'devbim-logo';
    link.href = REG_URL;
    link.target = '_blank';
    link.rel = 'noopener';
    link.innerHTML = LOGO_SVG +
      '<span class="devbim-word"><span class="dev">Dev</span><span class="bim">BIM</span></span>';

    var tagline = document.createElement('span');
    tagline.className = 'devbim-tagline';

    banner.appendChild(link);
    banner.appendChild(tagline);

    var root = document.getElementById('root');
    root.parentNode.insertBefore(banner, root);

    els.link = link;
    els.tagline = tagline;
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
