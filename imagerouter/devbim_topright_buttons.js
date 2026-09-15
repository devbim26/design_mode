/* DevBIM: кнопки «Prompt Assistant» (✨) и «3D Design» в правом углу ЛЕВОЙ
 * панели — в ряду жёлтой кнопки Generate (очередь).
 *
 * Деплой: setup_imagerouter.py (deploy_topright_buttons) — копия в
 * dist/devbim-topright-buttons.js + <script defer> в index.html.
 * Бандлы не тронуты — после деплоя достаточно F5.
 *
 * Клик «Prompt Assistant» вызывает window.__devbimPromptEnhance() — глобал
 * из патча App-бандла (patch_prompt_enhance_button v2): DevbimPEWatch в
 * ряду Generate держит window.__devbimPEStore свежим и пишет флаг занятости
 * window.__devbimPEPending. «3D Design» — заглушка (функциональность позже).
 *
 * Ряд очереди ищется локале-независимо: жёлтая (invokeYellow) кнопка
 * ~36px в верхней части панели → её контейнер 200px → родительский ряд
 * (flex, рядом chakra-numberinput — счётчик очереди). Группа вставляется
 * последним ребёнком ряда (за Spacer → правый край панели); тик 500 мс
 * пере-вставляет её при ремоунте панели и прячет, когда ряда нет
 * (вкладки Workflows/IFC/PDF/Design Code).
 *
 * АДАПТИВНОСТЬ (по запросу пользователя 15.09): места мало — кнопки
 * деградируют в компактный вид 36×36 без длинного текста: ✨ остаётся
 * звёздочка, у «3D Design» — короткая подпись «3D» (атрибут data-short
 * выводится через ::after); совсем мало — кнопки сжимаются до полосок
 * (min-width 14px), но НЕ исчезают. Полный вид (текст+иконка, ~235px)
 * возвращается при расширении панели.
 */
(function () {
  'use strict';

  var GROUP_ID = 'devbim-tr-btns';
  var POLL_MS = 500;
  var FULL_NEED = 240; // столько места нужно для полного вида (текст+иконки)

  // --- тексты вспомогательных сообщений по языку интерфейса (как баннер) ---
  var TEXTS = {
    ru: {
      soon: '3D Design — раздел в разработке',
      needTab: 'Откройте вкладку Generate или Холст и повторите'
    },
    en: {
      soon: '3D Design — coming soon',
      needTab: 'Open the Generate or Canvas tab and try again'
    }
  };
  var lang = 'ru';

  // --- стили: как chakra-кнопки приложения (высота Generate = 36px) ---
  var CSS =
    '#devbim-tr-btns{display:flex;gap:8px;flex-shrink:0;align-items:center}' +
    '.devbim-tr-btn{display:inline-flex;align-items:center;gap:6px;height:36px;padding:0 10px;' +
    'border:none;border-radius:4px;color:#0B0C0E;white-space:nowrap;cursor:pointer;flex-shrink:0;' +
    "font:600 13px/1 Inter,'Segoe UI',system-ui,sans-serif;" +
    'transition:filter .12s,opacity .12s}' +
    '.devbim-tr-btn:hover{filter:brightness(1.1)}' +
    '.devbim-tr-btn:active{filter:brightness(.94)}' +
    '.devbim-tr-btn:disabled{opacity:.55;cursor:default;filter:none}' +
    '.devbim-tr-btn svg{display:block;flex-shrink:0}' +
    '#devbim-tr-pe{background:#38BDF8}' +
    '#devbim-tr-3d{background:#A78BFA}' +
    /* компактный вид: без длинного текста — у ✨ звёздочка, у 3D короткая
       подпись из data-short; при жуткой тесноте сжимаются в полоски
       (min-width), но остаются в интерфейсе */
    '#devbim-tr-btns.devbim-tr-compact{gap:4px}' +
    '#devbim-tr-btns.devbim-tr-compact .devbim-tr-btn{width:36px;min-width:14px;padding:0;' +
    'justify-content:center;flex-shrink:1;overflow:hidden}' +
    '#devbim-tr-btns.devbim-tr-compact .devbim-tr-btn span{display:none}' +
    '#devbim-tr-btns.devbim-tr-compact .devbim-tr-btn[data-short]::after{content:attr(data-short)}' +
    '.devbim-tr-toast{position:fixed;left:50%;bottom:26px;transform:translateX(-50%);' +
    'background:#1d2126;color:#e8ebee;border:1px solid #2b2f35;border-radius:6px;' +
    'padding:9px 16px;font:500 13px/1.3 Inter,\'Segoe UI\',system-ui,sans-serif;' +
    'z-index:2000;box-shadow:0 4px 16px rgba(0,0,0,.45);pointer-events:none}';

  var SPARK_SVG =
    '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">' +
    '<path d="M12 1.7l2.1 8.2 8.2 2.1-8.2 2.1L12 22.3l-2.1-8.2-8.2-2.1 8.2-2.1L12 1.7z"/></svg>';

  var toastTimer = null;
  var group = null;

  function t() { return TEXTS[lang] || TEXTS.en; }

  function toast(msg) {
    var el = document.querySelector('.devbim-tr-toast');
    if (!el) {
      el = document.createElement('div');
      el.className = 'devbim-tr-toast';
      document.body.appendChild(el);
    }
    el.textContent = msg;
    el.style.opacity = '1';
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { el.style.opacity = '0'; }, 2600);
  }

  function mkBtn(id, label, svg, title, short) {
    var b = document.createElement('button');
    b.id = id;
    b.type = 'button';
    b.className = 'devbim-tr-btn';
    b.title = title || label;
    b.setAttribute('aria-label', title || label);
    if (short) b.setAttribute('data-short', short); // подпись компактного вида
    b.innerHTML = (svg || '') + '<span></span>';
    b.lastChild.textContent = label;
    return b;
  }

  function build() {
    group = document.createElement('div');
    group.id = GROUP_ID;

    var pe = mkBtn('devbim-tr-pe', 'Prompt Assistant', SPARK_SVG, 'Prompt Enhance');
    pe.addEventListener('click', function () {
      var fn = window.__devbimPromptEnhance;
      if (typeof fn !== 'function' || !fn()) toast(t().needTab);
    });

    var td = mkBtn('devbim-tr-3d', '3D Design', '', '3D Design', '3D');
    td.addEventListener('click', function () { toast(t().soon); });

    group.appendChild(pe);
    group.appendChild(td);
  }

  // Жёлтая кнопка Generate («Добавить в очередь» на холсте): invokeYellow —
  // насыщенный жёлтый в любой теме; высота ~36px, верх панели.
  function isYellow(b) {
    var m = getComputedStyle(b).backgroundColor.match(/(\d+),\s*(\d+),\s*(\d+)/);
    if (!m) return false;
    var R = +m[1], G = +m[2], B = +m[3];
    return R > 180 && G > 140 && B < 110 && R > B + 60;
  }

  // Ряд очереди левой панели: [контейнер 200px (счётчик + Generate), Spacer]
  function findQueueRow() {
    var btns = document.querySelectorAll('button');
    for (var i = 0; i < btns.length; i++) {
      var b = btns[i];
      var r = b.getBoundingClientRect();
      if (r.height < 30 || r.height > 42 || r.y > 220 || r.width < 40) continue;
      if (!isYellow(b)) continue;
      var pne = b.parentElement;
      var row = pne && pne.parentElement;
      if (!row || !row.querySelector('.chakra-numberinput')) continue;
      return row;
    }
    return null;
  }

  // Полный вид или компактные квадратики — по свободному месту в ряду.
  function fit(row) {
    var genBox = row.firstElementChild; // контейнер 200px (stepper + Generate)
    if (!genBox) return;
    var free = row.getBoundingClientRect().width
      - genBox.getBoundingClientRect().width - 6 /*gap ряда*/;
    group.classList.toggle('devbim-tr-compact', free < FULL_NEED);
  }

  function tick() {
    if (!group) build();
    var row = findQueueRow();
    if (row) {
      if (group.parentElement !== row) row.appendChild(group);
      group.style.display = '';
      fit(row);
      syncPending();
    } else if (group.parentElement) {
      group.style.display = 'none';
    }
  }

  // Занятость улучшения промта: пока VLM работает — кнопка приглушена.
  function syncPending() {
    var b = document.getElementById('devbim-tr-pe');
    if (!b) return;
    var busy = window.__devbimPEPending === true;
    b.disabled = busy || typeof window.__devbimPromptEnhance !== 'function';
    if (busy) b.setAttribute('aria-busy', 'true');
    else b.removeAttribute('aria-busy');
  }

  // --- язык интерфейса: IndexedDB «invoke» / «invoke-store» (как баннер) ---
  function readLanguage(cb) {
    var req;
    try { req = indexedDB.open('invoke'); } catch (e) { cb(null); return; }
    req.onsuccess = function () {
      var get;
      try {
        get = req.result.transaction('invoke-store', 'readonly')
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
    readLanguage(function (l) { if (l && TEXTS[l]) lang = l; });
  }

  function init() {
    var st = document.createElement('style');
    st.textContent = CSS;
    document.head.appendChild(st);
    tick();
    setInterval(tick, POLL_MS);
    pollLanguage();
    setInterval(pollLanguage, 2000);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
