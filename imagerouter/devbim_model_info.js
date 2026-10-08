/* DevBIM: описание модели под селектором + пометки (звёзды/баннеры).
 *
 * Часть 1 (решение 19.09): под строкой «Модель» показывается краткий текст
 * description выбранной облачной модели — возможности (генерация /
 * ✏️ редактирование), форматы файлов, максимальное разрешение (до NK).
 * Источник — GET /api/v2/models/i/{key} (сырой JSON: zod на клиенте
 * выбрасывает description из стора). Ключ текущей модели — из стора
 * приложения: window.__devbimPEStore либо __devbimCanvasBridge.
 * Для не-imagerouter моделей (локальные) блок скрывается.
 *
 * Часть 2 (решение 08.10, «звёзды 1–5 и мини-баннеры»): в блоке над
 * описанием — звёзды (сила модели в правке) и цветные чипы-баннеры;
 * в открытом дропдауне списка моделей та же строка (usage_info, серый
 * текст из конфига) раскрашивается: звёзды золотом, метки баннеров —
 * чипами цветов каталога. Источник цветов/подписей —
 * GET /api/v1/imagerouter/model-marks (менеджер моделей, per-company).
 * Раскраска дропдауна — best-effort поверх React (замена текстового
 * узла своего формата; без JS строка остаётся читаемым серым текстом).
 *
 * Деплой: setup_imagerouter.py (deploy_model_info) — копия в
 * dist/devbim-model-info.js + <script defer> в index.html. Бандлы не
 * тронуты — после деплоя достаточно F5. Тик 500 мс пере-вставляет блок
 * при ремоунтах React и обновляет при смене модели. Отладка:
 * window.__devbimModelInfo ({key, text, marks, clear(), refreshMarks()}).
 * Откат: убрать script из index.html (index.html.modelinfo-bak) и
 * удалить dist/devbim-model-info.js.
 */
(function () {
  'use strict';

  var POLL_MS = 500;
  var CLASS_NAME = 'devbim-model-info';
  var ACCORDION_SELECTOR = '[data-testid="generation-accordion"]';
  var IR_PREFIX = 'imagerouter/';
  var STARS_COLOR = '#ecc94b';

  var el = null;                          // вставленный блок
  var cache = Object.create(null);        // key -> description ("" — нет)
  var inflight = Object.create(null);     // key -> Promise<string>
  var marksData = null;                   // {badges, marks} из /model-marks
  var marksPromise = null;
  var decorateTimer = null;

  function getStore() {
    try {
      if (window.__devbimPEStore && typeof window.__devbimPEStore.getState === 'function') {
        return window.__devbimPEStore;
      }
    } catch (e) { /* ещё не выставлен */ }
    try {
      var b = window.__devbimCanvasBridge;
      if (b && typeof b.getManager === 'function') {
        var m = b.getManager();
        if (m && m.stateApi && m.stateApi.store) return m.stateApi.store;
      }
    } catch (e) { /* менеджер ещё не поднят */ }
    return null;
  }

  function currentKey() {
    var st = getStore();
    if (!st) return null;
    try {
      var mk = st.getState().params.model;
      return (mk && mk.key) || null;
    } catch (e) {
      return null;
    }
  }

  function descFor(key) {
    if (key in cache) return Promise.resolve(cache[key]);
    if (inflight[key]) return inflight[key];
    if (key.indexOf(IR_PREFIX) !== 0) {
      // Локальные модели — описания в этом UI не показываем
      cache[key] = '';
      return Promise.resolve('');
    }
    inflight[key] = fetch('/api/v2/models/i/' + encodeURIComponent(key))
      .then(function (r) { return r.json(); })
      .then(function (cfg) {
        var d = (cfg && typeof cfg.description === 'string') ? cfg.description : '';
        cache[key] = d;
        delete inflight[key];
        return d;
      })
      .catch(function () {
        cache[key] = '';
        delete inflight[key];
        return '';
      });
    return inflight[key];
  }

  // --- пометки (звёзды/баннеры) ------------------------------------------

  function fetchMarks() {
    if (marksPromise) return marksPromise;
    marksPromise = fetch('/api/v1/imagerouter/model-marks')
      .then(function (r) { return r.json(); })
      .then(function (d) {
        marksData = (d && d.badges && d.marks) ? d : null;
        return marksData;
      })
      .catch(function () { return null; });
    return marksPromise;
  }

  // пометки модели по ключу конфига: {stars, badges:[{label,color,title}]}
  function marksForKey(key) {
    if (!marksData || !key || key.indexOf(IR_PREFIX) !== 0) return null;
    var id = key.slice(IR_PREFIX.length);
    var mk = marksData.marks[id];
    if (!mk) return null;
    var out = [];
    for (var i = 0; i < (mk.badges || []).length; i++) {
      var b = marksData.badges[mk.badges[i]];
      if (b) out.push(b);
    }
    return { stars: mk.stars || 0, badges: out };
  }

  function starsSpan(stars, fontSize) {
    var s = document.createElement('span');
    s.textContent = new Array(stars + 1).join('★') + new Array(6 - stars).join('☆');
    s.style.cssText = 'color:' + STARS_COLOR + ';letter-spacing:.12em;font-size:' +
      (fontSize || 13) + 'px;line-height:1;vertical-align:middle;';
    s.setAttribute('aria-label', stars + ' из 5');
    return s;
  }

  function chipSpan(b) {
    var s = document.createElement('span');
    s.textContent = b.label;
    s.style.cssText = 'display:inline-block;padding:0 6px;border-radius:4px;background:' +
      (b.color || '#4a5568') + ';color:#fff;font-size:10px;font-weight:700;' +
      'letter-spacing:.04em;line-height:16px;vertical-align:middle;white-space:nowrap;';
    if (b.title) s.title = b.title;
    return s;
  }

  // строка пометок (звёзды + чипы); null — пометок нет
  function marksRowNode(mk) {
    if (!mk || (mk.stars <= 0 && !mk.badges.length)) return null;
    var row = document.createElement('div');
    row.style.cssText = 'display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin-bottom:4px;';
    if (mk.stars > 0) row.appendChild(starsSpan(mk.stars, 13));
    for (var i = 0; i < mk.badges.length; i++) row.appendChild(chipSpan(mk.badges[i]));
    return row;
  }

  // --- раскраска строки usage_info в открытом дропдауне -------------------
  //
  // Формат строки (сервер, _marks_usage_info): «★★★★☆ · EDIT · BG CUT»,
  // звёзд может не быть (тогда все токены — метки баннеров). Находим
  // <p class="extra-info"> с таким текстом и заменяем содержимое на
  // окрашенные узлы; описание модели (тоже extra-info) не трогаем —
  // его текст не совпадает с грамматикой пометок.

  function decorateExtraInfo() {
    if (!marksData) return;
    var labels = Object.create(null);
    for (var k in marksData.badges) labels[marksData.badges[k].label] = marksData.badges[k];
    var nodes = document.querySelectorAll('.extra-info');
    for (var i = 0; i < nodes.length; i++) {
      var p = nodes[i];
      if (p.getAttribute('data-devbim-marks')) continue;
      var t = (p.textContent || '').trim();
      if (!t) continue;
      var tokens = t.split(' · ');
      var stars = 0;
      var start = 0;
      if (/^[★☆]{1,5}$/.test(tokens[0])) {
        stars = (tokens[0].match(/★/g) || []).length;
        start = 1;
      }
      if (start >= tokens.length && stars <= 0) continue;   // только текст без баннеров
      var badges = [];
      var ok = true;
      for (var j = start; j < tokens.length; j++) {
        if (!labels[tokens[j]]) { ok = false; break; }
        badges.push(labels[tokens[j]]);
      }
      if (!ok) continue;                                    // не наша строка (например, description)
      p.setAttribute('data-devbim-marks', '1');
      p.style.fontStyle = 'normal';
      while (p.firstChild) p.removeChild(p.firstChild);
      if (stars > 0) p.appendChild(starsSpan(stars, 12));
      for (var n = 0; n < badges.length; n++) {
        if (p.childNodes.length) p.appendChild(document.createTextNode(' · '));
        p.appendChild(chipSpan(badges[n]));
      }
    }
  }

  function scheduleDecorate() {
    if (decorateTimer || !marksData) return;
    decorateTimer = setTimeout(function () {
      decorateTimer = null;
      decorateExtraInfo();
    }, 120);
  }

  // --- блок под селектором -------------------------------------------------

  function ensureAttached(acc) {
    // Внутри аккордеона — колонка (gap:4, flexDir:column) с рядом «Модель»;
    // блок описания добавляем последним ребёнком колонки (под селектором).
    var col = acc.firstElementChild;
    if (!col) return null;
    if (el && el.isConnected && el.parentElement === col) return el;
    if (el && el.isConnected) el.remove();
    el = document.createElement('div');
    el.className = CLASS_NAME;
    el.style.cssText =
      'font-size:12px;line-height:1.5;letter-spacing:.01em;color:#8a929f;' +
      'white-space:normal;overflow-wrap:break-word;';
    el.style.display = 'none';
    col.appendChild(el);
    return el;
  }

  function renderBox(box, key) {
    var mk = marksForKey(key);
    var row = marksRowNode(mk);
    box.textContent = '';
    if (row) box.appendChild(row);
    if (box.childNodes.length) box.style.display = '';
    descFor(key).then(function (d) {
      // React мог пересобрать аккордеон за время запроса — не пишем в
      // отвязанный узел: на следующем тике будет новый блок
      if (!box.isConnected) return;
      if (box.__devbimKey !== key) return;
      if (d) {
        box.appendChild(document.createTextNode(d));
        box.style.display = '';
      } else if (!box.childNodes.length) {
        box.style.display = 'none';
      }
    });
  }

  function tick() {
    var acc = document.querySelector(ACCORDION_SELECTOR);
    if (!acc) {
      if (el && el.isConnected) el.remove();
      return;
    }
    var key = currentKey();
    if (!key) return;
    var box = ensureAttached(acc);
    if (!box) return;
    if (box.__devbimKey === key) return; // уже настроен для этой модели
    box.__devbimKey = key;
    box.style.display = 'none';
    renderBox(box, key);
  }

  fetchMarks().then(function () {
    if (marksData) {
      decorateExtraInfo();
      if (document.body) {
        new MutationObserver(scheduleDecorate).observe(document.body, { childList: true, subtree: true });
      }
    }
  });

  setInterval(tick, POLL_MS);

  // Отладка: текущее состояние + сброс кэшей
  window.__devbimModelInfo = {
    get key() { return currentKey(); },
    get text() { return (el && el.isConnected && el.textContent) || ''; },
    get marks() { return marksForKey(currentKey()); },
    clear: function () {
      cache = Object.create(null);
      if (el) { el.__devbimKey = null; }
    },
    refreshMarks: function () {
      marksPromise = null;
      if (el) { el.__devbimKey = null; }
      var decorated = document.querySelectorAll('[data-devbim-marks]');
      for (var i = 0; i < decorated.length; i++) decorated[i].removeAttribute('data-devbim-marks');
      return fetchMarks().then(decorateExtraInfo);
    }
  };
})();
