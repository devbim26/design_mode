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
 * window.__devbimPEPending. «3D Design» открывает модалку генерации 3D
 * (сценарий/источник/промт -> POST /api/v1/threed/generate -> {jobId} ->
 * поллинг GET /jobs/{id} с этапами (анализ/сборка/проверка) -> вкладка IFC;
 * сценарии: Site Plan (генплан), Facade (фасад — возвращён 05.10: после
 * удаления плитки фото фасада гоняли через Exterior/сцену, а она строит
 * генплан — кламп окон до 10 осей + выдуманный контекст, «приходит другое
 * здание»), Floor Plan (план квартиры, бэкенд-ключ interior — стены по
 * чертежу), Interior (interior3d — рендер/фото готового интерьера:
 * комната-бокс + мебель + люди + камера как на исходнике), Exterior
 * (сцена).
 * Фоновые задачи — фикс 524: конвейер 2–6 мин не влезает в ~100-секундный
 * лимит Cloudflare-туннеля на длинный HTTP-ответ.
 *
 * Тултипы кнопок (title при наведении) — по языку интерфейса (peTip/tdTip).
 * В модалке 3D — до 2 поясняющих фото с подписями (контент загружает
 * администратор в менеджере моделей: GET /api/v1/threed/modal-media).
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
      srcCanvas: 'Холст', srcViewer: 'Галерея',
      noSource: 'Положите картинку на Холст или выберите в галерее/вьювере',
      generate: 'Сгенерировать 3D', generating: 'Анализ модели…',
      done: 'Модель создана:', plan: 'Site Plan', facade: 'Facade',
      interior: 'Floor Plan',
      interior3d: 'Interior', scene: 'Exterior',
      pickScenario: 'Что генерируем?',
      promptPhPlan: 'Уточнения: «жилой 5 этажей, школа 3, масштаб 0.5 м/px»',
      promptPhFacade: 'Уточнения: «5 этажей, двускатная крыша, окна 4 в ряд, балконы со 2 этажа, глубина 14 м»',
      promptPhInterior: 'Уточнения: «высота стен 2.8, масштаб 0.01 м/px, стены по чертежу»',
      promptPhInterior3d: 'Уточнения: «гостиная 5×4 м, потолок 3 м, диван у северной стены, человек у окна»',
      promptPhScene: 'Уточнения: «2 дома: главный 7 этажей, второй 3 справа; деревья вдоль дороги; камера слева»',
      netErr: 'Ошибка сети/сервера',
      stageQueued: 'В очереди', stageAnalysis: 'Анализ картинки (VLM)',
      stageBuild: 'Сборка IFC-модели', stageVerify: 'Самопроверка VLM',
      jobLost: 'Задача потеряна (перезапуск сервера?) — готовые модели во вкладке IFC',
      spent: 'потрачено',
      needTab: 'Откройте вкладку Generate или Холст и повторите',
      // тултипы кнопок (title при наведении)
      peTip: 'Улучшение промта: ваш текст и картинка (если приложена) ' +
        'отправляются в специальную ИИ-модель — она перепишет промт ' +
        'подробнее и на английском для более качественной генерации. ' +
        'Результат можно отредактировать перед применением.',
      tdTip: 'Из вашей картинки строится 3D-модель сцены. Измените ракурс ' +
        'камеры в 3D-вьювере, затем верните изначальное фото — ИИ-рендер ' +
        'восстановит сцену с новым ракурсом.'
    },
    en: {
      soon: '3D Design — coming soon',
      srcCanvas: 'Canvas', srcViewer: 'Gallery',
      noSource: 'Put an image on the Canvas or select one in the viewer',
      generate: 'Generate 3D', generating: 'Analyzing the model…',
      done: 'Model created:', plan: 'Site Plan', facade: 'Facade',
      interior: 'Floor Plan',
      interior3d: 'Interior', scene: 'Exterior',
      pickScenario: 'What to generate?',
      promptPhPlan: 'Hints: "residential 5 floors, school 3, scale 0.5 m/px"',
      promptPhFacade: 'Hints: "5 storeys, gable roof, 4 windows per row, balconies from floor 2, depth 14 m"',
      promptPhInterior: 'Hints: "wall height 2.8, scale 0.01 m/px, walls as drawn"',
      promptPhInterior3d: 'Hints: "living room 5x4 m, ceiling 3 m, sofa at the north wall, person by the window"',
      promptPhScene: 'Hints: "2 houses: main 7 storeys, second 3 on the right; trees along the road; camera on the left"',
      netErr: 'Network/server error',
      stageQueued: 'Queued', stageAnalysis: 'Analyzing image (VLM)',
      stageBuild: 'Building IFC model', stageVerify: 'VLM self-check',
      jobLost: 'Job lost (server restart?) — finished models in the IFC tab',
      spent: 'spent',
      needTab: 'Open the Generate or Canvas tab and try again',
      // button tooltips (hover title)
      peTip: 'Prompt assistant: your text and image (if attached) are sent ' +
        'to a special AI model that rewrites the prompt in rich English ' +
        'detail for higher-quality generation. You can edit the result ' +
        'before applying it.',
      tdTip: 'Builds a 3D model of the scene from your image. Change the ' +
        'camera angle in the 3D viewer, then bring back the original ' +
        'photo — the AI render will restore the scene from the new angle.'
    }
  };
  var lang = 'en';   // до первого чтения настроек — английский (дефолт продукта)

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
    'z-index:2000;box-shadow:0 4px 16px rgba(0,0,0,.45);pointer-events:none}' +
    /* модалка 3D Design: сценарии, источник, промт, генерация */
    '#devbim-3d-modal{position:fixed;inset:0;background:rgba(0,0,0,.55);z-index:3000;' +
    'display:flex;align-items:center;justify-content:center}' +
    '.devbim-3d-card{width:400px;max-width:92vw;background:#1d2126;color:#e8ebee;' +
    'border:1px solid #2b2f35;border-radius:8px;padding:14px;display:flex;flex-direction:column;gap:10px;' +
    "font:500 13px/1.4 Inter,'Segoe UI',system-ui,sans-serif}" +
    '.devbim-3d-head{display:flex;justify-content:space-between;align-items:center}' +
    '.devbim-3d-x{background:none;border:none;color:#9aa3ad;font-size:15px;cursor:pointer}' +
    '.devbim-3d-tiles{display:flex;gap:8px}' +
    '.devbim-3d-tile{flex:1;display:flex;flex-direction:column;align-items:center;gap:4px;' +
    'padding:8px 4px;border:1px solid #2b2f35;border-radius:6px;background:#22262c;color:#e8ebee;' +
    'cursor:pointer;font:600 12px/1.2 inherit}' +
    '.devbim-3d-tile.on{border-color:#A78BFA;background:#2a2438}' +
    '.devbim-3d-tile:disabled{opacity:.45;cursor:default}' +
    '.devbim-3d-src{position:relative;border:1px dashed #2b2f35;border-radius:6px;overflow:hidden;' +
    'height:150px;display:flex;align-items:center;justify-content:center;background:#14161a}' +
    '.devbim-3d-src img{max-width:100%;max-height:100%;object-fit:contain}' +
    '.devbim-3d-badge{position:absolute;top:6px;left:6px;background:#000a;color:#cfd6dd;' +
    'border-radius:4px;padding:2px 7px;font-size:11px}' +
    '#devbim-3d-hint{color:#f0b429;font-size:12px}' +
    '#devbim-3d-prompt{background:#14161a;color:#e8ebee;border:1px solid #2b2f35;' +
    'border-radius:6px;padding:8px;resize:vertical;font:inherit}' +
    '#devbim-3d-go{height:36px;border:none;border-radius:4px;background:#A78BFA;color:#0B0C0E;' +
    'font:600 13px/1 inherit;cursor:pointer}' +
    '#devbim-3d-go:disabled{opacity:.55;cursor:default}' +
    '#devbim-3d-status{min-height:16px;font-size:12px;color:#9aa3ad}' +
    /* поясняющие фото (загружаются админом в менеджере моделей) */
    '.devbim-3d-photos{display:flex;gap:8px}' +
    '.devbim-3d-photos figure{flex:1;margin:0;min-width:0;' +
    'display:flex;flex-direction:column;gap:3px}' +
    '.devbim-3d-photos img{width:100%;height:64px;object-fit:cover;' +
    'display:block;border-radius:6px;border:1px solid #2b2f35;cursor:zoom-in}' +
    '.devbim-3d-photos figcaption{color:#9aa3ad;font-size:11px;line-height:1.25}';

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

    var pe = mkBtn('devbim-tr-pe', 'Prompt Assistant', SPARK_SVG, t().peTip);
    pe.addEventListener('click', function () {
      var fn = window.__devbimPromptEnhance;
      if (typeof fn !== 'function' || !fn()) toast(t().needTab);
    });

    var td = mkBtn('devbim-tr-3d', '3D Design', '', t().tdTip, '3D');
    td.addEventListener('click', function () { open3D(); });

    group.appendChild(pe);
    group.appendChild(td);
  }

  // Тултипы живут по языку интерфейса: обновляются вместе с lang.
  function applyTitles() {
    var pe = document.getElementById('devbim-tr-pe');
    var td = document.getElementById('devbim-tr-3d');
    if (pe) { pe.title = t().peTip; pe.setAttribute('aria-label', t().peTip); }
    if (td) { td.title = t().tdTip; td.setAttribute('aria-label', t().tdTip); }
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

  // --- язык интерфейса: IndexedDB «invoke» / «invoke-store» (как баннер).
  // ГРАБЛЯ 08.10: открывать БЕЗ создания — «голый» indexedDB.open('invoke')
  // на свежем профиле создаёт пустую базу v1 раньше приложения и убивает
  // персистентность redux-remember. Создание откатываем, без стора — null.
  function readLanguage(cb) {
    var req;
    try { req = indexedDB.open('invoke'); } catch (e) { cb(null); return; }
    req.onupgradeneeded = function (ev) {
      if (ev.oldVersion === 0) {
        try { req.transaction.abort(); } catch (e) { /* ничего */ }
      }
    };
    req.onsuccess = function () {
      var db = req.result;
      if (!db.objectStoreNames.contains('invoke-store')) { db.close(); cb(null); return; }
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
    req.onblocked = function () { cb(null); };
  }

  function pollLanguage() {
    readLanguage(function (l) {
      if (l && TEXTS[l] && l !== lang) { lang = l; applyTitles(); }
    });
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

  // ===================== 3D Design: модалка генерации =====================
  var S3 = { scenario: 'plan', image: null, source: '', busy: false, timer: null, escHandler: null };

  function close3D() {
    var m = document.getElementById('devbim-3d-modal');
    if (m) m.remove();
    if (S3.timer) { clearInterval(S3.timer); S3.timer = null; }
    if (S3.escHandler) { document.removeEventListener('keydown', S3.escHandler); S3.escHandler = null; }
    S3.busy = false;
  }

  // Композит холста (как в E2E п.30: stage.toCanvas). null = контента нет.
  // ГРАБЛЯ (fix 20.09): на оторванном/нулевом стейдже Konva toCanvas КИДАЕТ
  // InvalidStateError (drawImage width 0); исключение из composite убивало
  // refresh3DSource на полпути — превью пустое, а S3.image хранил СТАРУЮ
  // картинку и Generate молча слал её. Теперь любой сбой = null -> фолбэк.
  function canvasComposite() {
    try {
      var b = window.__devbimCanvasBridge;
      var m = b && b.getManager && b.getManager();
      if (!m || !m.stage || !m.stage.konva || !m.stage.konva.stage) return null;
      var st = m.stage.konva.stage;
      if (!(st.width() > 0) || !(st.height() > 0)) return null;
      var ents = null;
      try { var cState = window.__devbimPEStore.getState().canvas;
            var cPresent = cState && cState.present ? cState.present : cState;
            ents = (cPresent.entities || [])
              .concat((cPresent.rasterLayers && cPresent.rasterLayers.entities) || [])
              .concat((cPresent.controlLayers && cPresent.controlLayers.entities) || []); } catch (e) {}
      var has = false;
      (ents || []).forEach(function (en) {
        if ((en.type === 'raster_layer' || en.type === 'control_layer') &&
            (en.objects || []).length) has = true;
      });
      if (!has) return null;
      return st.toCanvas({ x: 0, y: 0, width: st.width(), height: st.height(),
                           pixelRatio: 1 }).toDataURL('image/png');
    } catch (e) { return null; }
  }

  // Выбранная во вьювере картинка (последняя из selection) -> dataURL.
  async function viewerImage() {
    var st = window.__devbimPEStore;
    if (!st) return null;
    var sel = (st.getState().gallery || {}).selection || [];
    var last = sel[sel.length - 1];
    if (!last) return null;
    var name = last.image_name || (typeof last === 'string' ? last : null);
    if (!name) return null;
    var r = await fetch('/api/v1/images/images_by_names', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ image_names: [name] }) });
    if (!r.ok) return null;
    var j = await r.json();
    var dto = (Array.isArray(j) ? j : (j.images || []))[0];
    if (!dto || !dto.image_url) return null;
    var ir = await fetch(dto.image_url);
    if (!ir.ok) return null;
    var blob = await ir.blob();
    return await new Promise(function (res) {
      var fr = new FileReader();
      fr.onload = function () { res(fr.result); };
      fr.readAsDataURL(blob);
    });
  }

  async function refresh3DSource() {
    var img = document.querySelector('#devbim-3d-modal .devbim-3d-src img');
    var badge = document.querySelector('#devbim-3d-modal .devbim-3d-badge');
    var hint = document.getElementById('devbim-3d-hint');
    if (img) img.src = '';
    // сброс ДО попытки: после сбоя composite здесь не должно оставаться
    // картинки из ПРОШЛОГО открытия модалки (иначе Generate молча шлёт её)
    S3.image = null;
    try { S3.image = canvasComposite(); } catch (e) { S3.image = null; }
    S3.source = t().srcCanvas;
    if (!S3.image) {
      try { S3.image = await viewerImage(); S3.source = t().srcViewer; } catch (e) {}
    }
    if (img) img.src = S3.image || '';
    if (badge) badge.textContent = S3.image ? S3.source : '—';
    if (hint) hint.style.display = S3.image ? 'none' : 'block';
  }

  function open3D() {
    close3D();
    var ov = document.createElement('div');
    ov.id = 'devbim-3d-modal';
    ov.innerHTML =
      '<div class="devbim-3d-card">' +
      '<div class="devbim-3d-head"><b>3D Design</b><button class="devbim-3d-x" aria-label="close">✕</button></div>' +
      '<div class="devbim-3d-tiles">' +
      '<button class="devbim-3d-tile" data-s="plan"><span>🗺</span>' + t().plan + '</button>' +
      '<button class="devbim-3d-tile" data-s="facade"><span>🏢</span>' + t().facade + '</button>' +
      '<button class="devbim-3d-tile" data-s="interior"><span>📐</span>' + t().interior + '</button>' +
      '<button class="devbim-3d-tile" data-s="interior3d"><span>🛋</span>' + t().interior3d + '</button>' +
      '<button class="devbim-3d-tile" data-s="scene"><span>🌇</span>' + t().scene + '</button>' +
      '</div>' +
      '<div class="devbim-3d-src"><img alt=""><span class="devbim-3d-badge">—</span></div>' +
      '<div class="devbim-3d-photos" id="devbim-3d-photos" style="display:none"></div>' +
      '<div id="devbim-3d-hint" style="display:none">' + t().noSource + '</div>' +
      '<textarea id="devbim-3d-prompt" rows="3" placeholder="' + t().promptPhPlan.replace(/"/g, '&quot;') + '"></textarea>' +
      '<button id="devbim-3d-go">' + t().generate + '</button>' +
      '<div id="devbim-3d-status"></div>' +
      '</div>';
    document.body.appendChild(ov);
    ov.addEventListener('click', function (e) { if (e.target === ov) close3D(); });
    ov.querySelector('.devbim-3d-x').addEventListener('click', close3D);
    ov.querySelectorAll('.devbim-3d-tile').forEach(function (b) {
      b.addEventListener('click', function () {
        S3.scenario = b.getAttribute('data-s');
        ov.querySelectorAll('.devbim-3d-tile').forEach(function (x) { x.classList.remove('on'); });
        b.classList.add('on');
        var ta = document.getElementById('devbim-3d-prompt');
        if (ta) {
          var ph = {plan: t().promptPhPlan, facade: t().promptPhFacade,
                    interior: t().promptPhInterior,
                    interior3d: t().promptPhInterior3d, scene: t().promptPhScene};
          ta.placeholder = ph[b.getAttribute('data-s')] || t().promptPhPlan;
        }
      });
    });
    ov.querySelector('.devbim-3d-tile').classList.add('on');
    document.getElementById('devbim-3d-go').addEventListener('click', run3D);
    S3.escHandler = function (e) { if (e.key === 'Escape') close3D(); };
    document.addEventListener('keydown', S3.escHandler);
    refresh3DSource();
    load3DPhotos();
  }

  // Поясняющие фото модалки: до 2 штук с подписями, контент задаёт
  // администратор в менеджере моделей (GET /api/v1/threed/modal-media).
  // Нет фото / ошибка сети — блок остаётся скрытым, модалка как была.
  function load3DPhotos() {
    fetch('/api/v1/threed/modal-media').then(function (r) {
      return r.ok ? r.json() : null;
    }).then(function (j) {
      var box = document.getElementById('devbim-3d-photos');
      if (!box || box.children.length) return;
      ((j && j.items) || []).slice(0, 2).forEach(function (it) {
        if (!it || !it.url) return;
        var fig = document.createElement('figure');
        var img = document.createElement('img');
        img.src = it.url;
        img.alt = it.caption || '';
        img.addEventListener('click', function () { window.open(it.url, '_blank'); });
        fig.appendChild(img);
        if (it.caption) {
          var cap = document.createElement('figcaption');
          cap.textContent = it.caption;
          fig.appendChild(cap);
        }
        box.appendChild(fig);
      });
      if (box.children.length) box.style.display = 'flex';
    }).catch(function () { /* без фото модалка не хуже */ });
  }

  var STAGE_KEYS = { analysis: 'stageAnalysis', build: 'stageBuild', verify: 'stageVerify' };

  async function run3D() {
    if (S3.busy || !S3.image) { if (!S3.image) toast(t().noSource); return; }
    var go = document.getElementById('devbim-3d-go');
    var stEl = document.getElementById('devbim-3d-status');
    S3.busy = true; go.disabled = true; go.textContent = t().generating;
    var t0 = Date.now();
    // этап фоновой задачи (S3.stage пишет поллинг) — иначе пустой счётчик секунд
    S3.stage = '';
    function stageLine() {
      var key = STAGE_KEYS[S3.stage];
      var label = key ? t()[key] : t().stageQueued;
      stEl.textContent = '⏳ ' + Math.round((Date.now() - t0) / 1000) + ' s · ' + label;
    }
    S3.timer = setInterval(stageLine, 500);
    function finish3D(j) {
      if (S3.timer) { clearInterval(S3.timer); S3.timer = null; }
      if (j.warnings && j.warnings.length) toast(j.warnings.join(' · '));
      try { localStorage.setItem('devbim:ifc:lastModel', j.name); } catch (e) {}
      if (j.camHint) { try { localStorage.setItem('devbim:ifc:camHint',
        JSON.stringify(j.camHint)); } catch (e) {} }
      close3D();
      if (window.__devbimSwitchTab) window.__devbimSwitchTab('ifc');
      // VLM-самопроверка собранной модели: ✓ / ⚠ issues; сбой (ok=null) — молча
      var vNote = '';
      if (j.verify && j.verify.verdict) {
        var v = j.verify.verdict;
        if (v.ok === true) vNote = ' · \u2713 VLM';
        else if (v.ok === false && v.issues && v.issues.length)
          vNote = ' · \u26A0 ' + v.issues.join('; ');
      }
      // фактическая стоимость VLM-запросов генерации (токены × тариф каталога)
      var cNote = '';
      if (j.usage && j.usage.cost_usd != null)
        cNote = ' · ' + t().spent + ' $' + j.usage.cost_usd;
      toast(t().done + ' ' + j.name + vNote + cNote);
    }
    function fail3D(msg) {
      S3.busy = false; go.disabled = false; go.textContent = t().generate;
      if (S3.timer) { clearInterval(S3.timer); S3.timer = null; }
      stEl.textContent = msg || t().netErr;
    }
    try {
      var r = await fetch('/api/v1/threed/generate', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scenario: S3.scenario,
                               prompt: (document.getElementById('devbim-3d-prompt').value || '').trim(),
                               image: S3.image })
      });
      var j = null; try { j = await r.json(); } catch (e) {}
      if (!r.ok) throw new Error((j && (j.detail || j.message)) || ('HTTP ' + r.status));
      if (j && j.name) { finish3D(j); return; }  // старый синхронный бэк
      if (!j || !j.jobId) throw new Error('нет jobId в ответе сервера');
      // Фоновая задача (фикс 524): конвейер длиннее ~100 с, туннель рвёт
      // длинный ответ — опрашиваем короткими GET, живём без лимита
      var jobId = j.jobId;
      for (;;) {
        await new Promise(function (res) { setTimeout(res, 2500); });
        var pr = await fetch('/api/v1/threed/jobs/' + jobId);
        if (pr.status === 404) { fail3D(t().jobLost); return; }
        var pj = null; try { pj = await pr.json(); } catch (e) {}
        if (!pr.ok || !pj)
          throw new Error((pj && (pj.detail || pj.error)) || ('HTTP ' + pr.status));
        S3.stage = pj.stage || '';
        stageLine();
        if (pj.status === 'done') { finish3D(pj.result || {}); return; }
        if (pj.status === 'error') { fail3D(pj.error); return; }
      }
    } catch (e) {
      fail3D((e && e.message) || t().netErr);
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
