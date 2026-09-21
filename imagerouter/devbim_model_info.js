/* DevBIM: описание модели под селектором в аккордеоне «Генерация».
 *
 * Решение 19.09 (запрос «вкладку выбора модели сделать чуть более
 * информативной»): под строкой «Модель» показывается краткий текст
 * description выбранной облачной модели — возможности (генерация /
 * ✏️ редактирование), форматы файлов, максимальное разрешение (до NK).
 * Текст приходит с сервера в конфиге модели; ниже блока идёт секция
 * «Изображение» (патч patch_panel_layout: секции переставлены).
 *
 * Источник описания — GET /api/v2/models/i/{key} (тот же эндпоинт, что
 * использует гейт Generate-фолбэка: zod на клиенте выбрасывает
 * description из стора, поэтому читаем сырой JSON сами). Ключ текущей
 * модели — из стора приложения: window.__devbimPEStore (держится
 * свежим наблюдателем DevbimPEWatch) либо __devbimCanvasBridge.
 * Для не-imagerouter моделей (локальные) блок скрывается.
 *
 * Деплой: setup_imagerouter.py (deploy_model_info) — копия в
 * dist/devbim-model-info.js + <script defer> в index.html. Бандлы не
 * тронуты — после деплоя достаточно F5. Тик 500 мс пере-вставляет блок
 * при ремоунтах React (аккордеон пересобирается при смене вкладки) и
 * обновляет текст при смене модели. Отладка: window.__devbimModelInfo
 * ({key, text, clear()}). Откат: убрать script из index.html
 * (index.html.modelinfo-bak) и удалить dist/devbim-model-info.js.
 */
(function () {
  'use strict';

  var POLL_MS = 500;
  var CLASS_NAME = 'devbim-model-info';
  var ACCORDION_SELECTOR = '[data-testid="generation-accordion"]';

  var el = null;                          // вставленный блок
  var cache = Object.create(null);        // key -> description ("" — нет)
  var inflight = Object.create(null);     // key -> Promise<string>

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
    if (key.indexOf('imagerouter/') !== 0) {
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
    box.textContent = '';
    descFor(key).then(function (d) {
      // React мог пересобрать аккордеон за время запроса — не пишем в
      // отвязанный узел: на следующем тике будет новый блок
      if (!box.isConnected) return;
      if (box.__devbimKey !== key) return;
      if (d) {
        box.textContent = d;
        box.style.display = '';
      }
    });
  }

  setInterval(tick, POLL_MS);

  // Отладка: текущее состояние + сброс кэша описаний
  window.__devbimModelInfo = {
    get key() { return currentKey(); },
    get text() { return (el && el.isConnected && el.textContent) || ''; },
    clear: function () {
      cache = Object.create(null);
      if (el) { el.__devbimKey = null; }
    }
  };
})();
