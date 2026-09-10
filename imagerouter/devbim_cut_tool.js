// DevBIM — «Вырезать по контуру» (✂) на холсте InvokeAI.
// Кнопка-ножницы в вертикальной рейке инструментов: клики по канвасу
// ставят точки замкнутой полилинии, «Подтвердить»/Enter/Ctrl+C кладут
// вырезанный кусок картинки новым растровым слоем ПОВЕРХ текущего
// (исходник НЕ меняется — подложка остаётся с оригиналом; слой-кусок не
// выделяется, чтобы не было рамки выделения). Ctrl+V — вставить копию
// последнего кусочка ещё раз. «Отменить»/Esc — выход без изменений.
// Деплой: setup_imagerouter.py → dist/devbim-cut-tool.js (+script в index.html).
// Мост: window.__devbimCanvasBridge.getManager() — патч App-бандла.
(function () {
  "use strict";

  var TICK_MS = 500;
  var CLOSE_PX = 14;      // радиус «замкнуть контур» у первой точки (экран)
  var ID = "devbim-cut";
  var BAR_ID = "devbim-cutbar";
  var TOAST_ID = "devbim-cut-toast";
  var BTN_ID = "devbim-cut-btn";
  var OV_ID = "devbim-cut-overlay";
  var MAX_SIDE = 16000;   // предохранитель размера канваса растеризации

  var RU = (navigator.language || "").toLowerCase().indexOf("ru") === 0;
  var L = RU ? {
    btn: "Вырезать по контуру (✂)",
    hint: "ЛКМ — точки · ПКМ — убрать точку · клик у 1-й точки — замкнуть · Ctrl+C / Enter — вырезать · Esc — отмена",
    confirm: "Подтвердить",
    cancel: "Отменить",
    noLayer: "На холсте нет растрового слоя с картинкой",
    done: "Кусочек — на новом слое поверх, оригинал цел · Ctrl+V — вставить ещё раз",
    pasted: "Вставлена копия кусочка (новый слой)",
    error: "Ошибка вырезания: ",
    few: "Нужно минимум 3 точки"
  } : {
    btn: "Cut out by contour (scissors)",
    hint: "Click — points · right-click — undo point · click near 1st point — close · Ctrl+C / Enter — cut · Esc — cancel",
    confirm: "Confirm",
    cancel: "Cancel",
    noLayer: "No raster layer with an image on the canvas",
    done: "Piece on a new layer above, original intact · Ctrl+V — paste again",
    pasted: "Piece copy pasted (new layer)",
    error: "Cut error: ",
    few: "At least 3 points required"
  };

  var ICON_SCISSORS =
    '<svg viewBox="0 0 24 24" width="1em" height="1em" fill="none" stroke="currentColor" stroke-width="2" ' +
    'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="6" cy="6" r="3"/>' +
    '<circle cx="6" cy="18" r="3"/><line x1="20" y1="4" x2="8.12" y2="15.88"/>' +
    '<line x1="14.47" y1="14.48" x2="20" y2="20"/><line x1="8.12" y1="8.12" x2="12" y2="12"/></svg>';
  var ICON_OK =
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" ' +
    'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="20 6 9 17 4 12"/></svg>';
  var ICON_NO =
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" ' +
    'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><line x1="18" y1="6" x2="6" y2="18"/>' +
    '<line x1="6" y1="6" x2="18" y2="18"/></svg>';

  var STYLE = [
    "#" + BAR_ID + "{position:fixed;bottom:142px;left:50%;transform:translateX(-50%);",
    "z-index:1400;display:none;align-items:center;gap:4px;padding:4px;border-radius:12px;",
    "background:#0B0C0E;border:1px solid rgba(56,189,248,.35);box-shadow:0 4px 16px rgba(0,0,0,.45)}",
    "#" + BAR_ID + " button{display:flex;align-items:center;justify-content:center;width:32px;height:32px;",
    "border:0;border-radius:8px;background:transparent;color:rgba(255,255,255,.72);cursor:pointer}",
    "#" + BAR_ID + " button:hover{background:rgba(255,255,255,.08);color:#fff}",
    "#" + BAR_ID + " .ok:hover{background:rgba(56,189,248,.2);color:#38BDF8}",
    "#" + BAR_ID + " .ok:disabled{opacity:.35;cursor:default;background:transparent;color:rgba(255,255,255,.72)}",
    "#" + BAR_ID + " .tag{display:flex;align-items:center;gap:6px;padding:0 8px;color:#38BDF8;font-size:13px}",
    "#" + BAR_ID + " svg{width:15px;height:15px;flex:none}",
    "#" + BAR_ID + " .hint{max-width:340px;padding:0 10px 0 6px;color:rgba(255,255,255,.45);font-size:11px;line-height:1.3}",
    "#" + TOAST_ID + "{position:fixed;bottom:150px;left:50%;transform:translateX(-50%);z-index:1500;",
    "display:none;padding:10px 16px;border-radius:10px;background:#0B0C0E;color:rgba(255,255,255,.85);",
    "border:1px solid rgba(255,255,255,.12);font-size:13px;box-shadow:0 4px 16px rgba(0,0,0,.5);max-width:70vw}",
    "#" + OV_ID + "{position:fixed;z-index:1399;pointer-events:none;overflow:hidden}",
    "#" + OV_ID + " svg{width:100%;height:100%;display:block}",
    // Пока активны ножницы, прочие кнопки-инструменты выглядят неактивными
    // (цвета — как у штатных неактивных кнопок рейки), сама ✂ — активной.
    "body.devbim-cut-mode .devbim-cut-rail button:not(#" + BTN_ID + "){",
    "background:rgb(138,146,163)!important;color:rgb(22,24,29)!important}"
  ].join("");

  // ---------- состояние режима ----------
  var mode = { active: false, points: [], closed: false, busy: false, hover: null };
  // «Буфер» последнего вырезания: Ctrl+V вставляет копию кусочка.
  var lastCut = null, pasteCount = 0, pasteBusy = false;
  var bar = null, btnOk = null, btnCancel = null, overlay = null, svg = null;
  var rafId = 0, toastTimer = 0, savedCursor = null;

  function manager() {
    var b = window.__devbimCanvasBridge;
    if (!b) return null;
    try {
      var m = b.getManager();
      return m && m.stateApi && m.stateApi.store && m.stage && m.stage.konva && m.stage.konva.stage ? m : null;
    } catch (e) { return null; }
  }

  // Canvas-слайс обёрнут в redux-undo: актуальное состояние в .present.
  function canvasState(store) {
    var c = store.getState().canvas;
    return c && c.present ? c.present : c;
  }

  function stageEl(m) { return m.stage.konva.stage.container(); }

  // ---------- координаты экран <-> документ ----------
  function toDoc(ev) {
    var m = manager();
    if (!m) return null;
    var el = stageEl(m), rect = el.getBoundingClientRect();
    var inv = m.stage.konva.stage.getAbsoluteTransform().copy().invert();
    return inv.point({ x: ev.clientX - rect.left, y: ev.clientY - rect.top });
  }

  function toScreen(p) {
    var m = manager();
    if (!m) return null;
    var el = stageEl(m), rect = el.getBoundingClientRect();
    var q = m.stage.konva.stage.getAbsoluteTransform().point({ x: p.x, y: p.y });
    return { x: q.x + rect.left, y: q.y + rect.top };
  }

  // ---------- тост ----------
  function toast(msg, ms) {
    var t = document.getElementById(TOAST_ID);
    if (!t) {
      ensureStyle();
      t = document.createElement("div");
      t.id = TOAST_ID;
      document.body.appendChild(t);
    }
    t.textContent = msg;
    t.style.display = "block";
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { t.style.display = "none"; }, ms || 2600);
  }

  // ---------- кнопка в рейке инструментов ----------
  function findRail() {
    var groups = document.querySelectorAll("div.chakra-button__group");
    for (var i = 0; i < groups.length; i++) {
      var btns = groups[i].querySelectorAll("button[aria-label]");
      var hasB = false, hasE = false, ref = null;
      for (var j = 0; j < btns.length; j++) {
        var a = btns[j].getAttribute("aria-label") || "";
        if (/\(B\)\s*$/.test(a)) hasB = true;
        if (/\(E\)\s*$/.test(a)) hasE = true;
        if (!ref) ref = btns[j];
      }
      if (hasB && hasE) return { rail: groups[i], ref: ref };
    }
    return null;
  }

  function ensureRailButton() {
    var f = findRail();
    if (!f) return;
    f.rail.classList.add("devbim-cut-rail");
    if (f.rail.querySelector("#" + BTN_ID)) return;
    var b = document.createElement("button");
    b.id = BTN_ID;
    b.type = "button";
    b.className = f.ref.className;
    b.setAttribute("aria-label", L.btn);
    b.title = L.btn;
    b.innerHTML = ICON_SCISSORS;
    b.onclick = function (e) { e.stopPropagation(); toggleMode(); };
    f.rail.appendChild(b);
    syncRailButton();
  }

  function railButton() { return document.getElementById(BTN_ID); }

  function syncRailButton() {
    var b = railButton();
    if (!b) return;
    // активное состояние — как у штатной активной кнопки-инструмента
    if (mode.active) {
      b.style.background = "rgb(71,177,230)";
      b.style.color = "rgb(22,24,29)";
    } else {
      b.style.background = "";
      b.style.color = "";
    }
  }

  // ---------- панель режима ----------
  function ensureStyle() {
    if (document.getElementById(ID + "-style")) return;
    var st = document.createElement("style");
    st.id = ID + "-style";
    st.textContent = STYLE;
    document.head.appendChild(st);
  }

  function buildBar() {
    if (bar) return;
    ensureStyle();
    bar = document.createElement("div");
    bar.id = BAR_ID;
    var tag = document.createElement("span");
    tag.className = "tag";
    tag.innerHTML = ICON_SCISSORS;
    tag.appendChild(document.createTextNode(RU ? "Контур" : "Contour"));
    btnOk = document.createElement("button");
    btnOk.type = "button";
    btnOk.className = "ok";
    btnOk.title = L.confirm;
    btnOk.innerHTML = ICON_OK;
    btnOk.onclick = function (e) { e.stopPropagation(); confirmCut(); };
    btnCancel = document.createElement("button");
    btnCancel.type = "button";
    btnCancel.title = L.cancel;
    btnCancel.innerHTML = ICON_NO;
    btnCancel.onclick = function (e) { e.stopPropagation(); cancelMode(); };
    var hint = document.createElement("span");
    hint.className = "hint";
    hint.textContent = L.hint;
    bar.appendChild(tag);
    bar.appendChild(btnOk);
    bar.appendChild(btnCancel);
    bar.appendChild(hint);
    document.body.appendChild(bar);
  }

  function syncBar() {
    if (!bar) return;
    bar.style.display = mode.active ? "flex" : "none";
    if (btnOk) {
      btnOk.disabled = !mode.active || mode.busy || mode.points.length < 3;
      btnOk.innerHTML = mode.busy ? "…" : ICON_OK;
    }
  }

  // ---------- оверлей-превью ----------
  function buildOverlay() {
    if (overlay) return;
    overlay = document.createElement("div");
    overlay.id = OV_ID;
    svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    overlay.appendChild(svg);
    document.body.appendChild(overlay);
  }

  function drawOverlay() {
    if (!mode.active || !overlay) return;
    var m = manager();
    if (!m) return;
    var rect = stageEl(m).getBoundingClientRect();
    overlay.style.left = rect.left + "px";
    overlay.style.top = rect.top + "px";
    overlay.style.width = rect.width + "px";
    overlay.style.height = rect.height + "px";
    var NS = "http://www.w3.org/2000/svg";
    var parts = [];
    var pts = mode.points.map(function (p) {
      var s = toScreen(p);
      return s ? (s.x - rect.left) + "," + (s.y - rect.top) : null;
    }).filter(Boolean);
    if (pts.length) {
      if (pts.length >= 3) {
        parts.push('<polygon points="' + pts.join(" ") + '" fill="rgba(56,189,248,' + (mode.closed ? 0.2 : 0.12) + ')"/>');
      }
      parts.push('<polyline points="' + pts.join(" ") + (mode.closed ? " " + pts[0] : "") +
        '" fill="none" stroke="#38BDF8" stroke-width="1.5"/>');
      if (!mode.closed && mode.hover) {
        var h = toScreen(mode.hover);
        if (h) {
          parts.push('<line x1="' + pts[pts.length - 1].split(",")[0] + '" y1="' + pts[pts.length - 1].split(",")[1] +
            '" x2="' + (h.x - rect.left) + '" y2="' + (h.y - rect.top) +
            '" stroke="#38BDF8" stroke-width="1" stroke-dasharray="4 3"/>');
        }
      }
      for (var i = 0; i < pts.length; i++) {
        var c = pts[i].split(",");
        parts.push('<circle cx="' + c[0] + '" cy="' + c[1] + '" r="' + (i === 0 ? 4.5 : 3.5) +
          '" fill="' + (i === 0 ? "#fff" : "#38BDF8") + '" stroke="#0B0C0E" stroke-width="1"/>');
      }
    }
    svg.innerHTML = parts.join("");
  }

  function loop() {
    if (!mode.active) return;
    drawOverlay();
    rafId = requestAnimationFrame(loop);
  }

  // ---------- события ----------
  function overCanvas(e) {
    var m = manager();
    if (!m) return false;
    var el = stageEl(m);
    return e.target && el.contains(e.target);
  }

  function onPointerDown(e) {
    if (!mode.active || mode.busy || e.button !== 0 || !overCanvas(e)) return;
    e.preventDefault();
    e.stopPropagation();
    if (mode.closed) return;
    var m = manager();
    if (!m) return;
    var el = stageEl(m), rect = el.getBoundingClientRect();
    // клик у первой точки — замкнуть контур
    if (mode.points.length >= 3) {
      var s = toScreen(mode.points[0]);
      if (s && Math.hypot(e.clientX - s.x, e.clientY - s.y) <= CLOSE_PX) {
        mode.closed = true;
        syncBar();
        return;
      }
    }
    var p = toDoc(e);
    if (!p) return;
    mode.points.push({ x: p.x, y: p.y });
    syncBar();
  }

  function onPointerMove(e) {
    if (!mode.active) return;
    mode.hover = toDoc(e);
  }

  function onContextMenu(e) {
    if (!mode.active || !overCanvas(e)) return;
    e.preventDefault();
    e.stopPropagation();
    if (!mode.busy && mode.points.length) {
      if (mode.closed) { mode.closed = false; }
      mode.points.pop();
      syncBar();
    }
  }

  function onDblClick(e) {
    if (!mode.active || !overCanvas(e)) return;
    e.preventDefault();
    e.stopPropagation();
  }

  // Клик по ДРУГОМУ инструменту рейки при активных ножницах — завершает
  // режим (кнопка-ножница гаснет, инструмент включается штатно).
  function onRailOtherTool(e) {
    if (!mode.active) return;
    var rail = document.querySelector(".devbim-cut-rail");
    if (!rail || !rail.contains(e.target)) return;
    if (e.target.closest && e.target.closest("#" + BTN_ID)) return;
    cancelMode();
  }

  function onKeyDown(e) {
    if (!mode.active) return;
    var isCopy = (e.ctrlKey || e.metaKey) && (e.key === "c" || e.key === "C");
    if (e.key === "Enter" || isCopy) {
      e.preventDefault();
      e.stopPropagation();
      confirmCut();
    } else if (e.key === "Escape") {
      e.preventDefault();
      e.stopPropagation();
      cancelMode();
    }
  }

  // Глобальный Ctrl+V: вставка копии последнего вырезанного кусочка.
  // Перехват только когда есть что вставить и открыт холст; в полях ввода
  // (промт и т.п.) не мешаем ни ОС, ни приложению.
  function onGlobalKeyDown(e) {
    if (!(e.ctrlKey || e.metaKey) || (e.key !== "v" && e.key !== "V")) return;
    if (!lastCut || pasteBusy) return;
    var t = e.target;
    if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable)) return;
    if (!window.__devbimGetTab || window.__devbimGetTab() !== "canvas") return;
    if (!canvasPanelActive() || !manager()) return;
    e.preventDefault();
    e.stopPropagation();
    pastePiece();
  }

  var eventsBound = false;
  function bindEvents() {
    if (eventsBound) return;
    eventsBound = true;
    document.addEventListener("pointerdown", onPointerDown, true);
    document.addEventListener("pointerdown", onRailOtherTool, true);
    window.addEventListener("pointermove", onPointerMove, true);
    document.addEventListener("contextmenu", onContextMenu, true);
    document.addEventListener("dblclick", onDblClick, true);
    window.addEventListener("keydown", onKeyDown, true);
    window.addEventListener("keydown", onGlobalKeyDown, true);
  }

  // ---------- режим ----------
  function canvasPanelActive() {
    return !!document.querySelector(".konvajs-content");
  }

  function tabOk() {
    return window.__devbimGetTab ? window.__devbimGetTab() === "canvas" : false;
  }

  function enterMode() {
    var m = manager();
    if (!m || mode.active) return;
    mode.active = true;
    mode.points = [];
    mode.closed = false;
    mode.busy = false;
    mode.hover = null;
    buildBar();
    buildOverlay();
    overlay.style.display = "block";
    document.body.classList.add("devbim-cut-mode");
    var el = stageEl(m);
    savedCursor = el.style.cursor;
    el.style.cursor = "crosshair";
    bindEvents();
    syncBar();
    syncRailButton();
    loop();
  }

  function exitMode() {
    mode.active = false;
    mode.busy = false;
    mode.points = [];
    mode.closed = false;
    document.body.classList.remove("devbim-cut-mode");
    if (rafId) { cancelAnimationFrame(rafId); rafId = 0; }
    if (overlay) { overlay.style.display = "none"; svg.innerHTML = ""; }
    var m = manager();
    if (m) { var el = stageEl(m); if (el && savedCursor !== null) el.style.cursor = savedCursor; }
    savedCursor = null;
    syncBar();
    syncRailButton();
  }

  function toggleMode() {
    if (mode.active) { cancelMode(); } else { enterMode(); }
  }

  function cancelMode() {
    if (mode.busy) return;
    exitMode();
  }

  // ---------- вырезание ----------
  function resolveLayer(cs) {
    var ents = cs.rasterLayers.entities;
    var sel = cs.selectedEntityIdentifier;
    var i, layer = null;
    if (sel && sel.type === "raster_layer") {
      for (i = 0; i < ents.length; i++) if (ents[i].id === sel.id) layer = ents[i];
    }
    if (!layer || !(layer.objects || []).length) {
      layer = null;
      for (i = ents.length - 1; i >= 0; i--) {
        if ((ents[i].objects || []).length) { layer = ents[i]; break; }
      }
    }
    return layer;
  }

  function uploadCanvas(cv, name) {
    return new Promise(function (resolve, reject) {
      cv.toBlob(function (blob) {
        if (!blob) { reject(new Error("toBlob failed")); return; }
        var fd = new FormData();
        fd.append("file", new File([blob], name, { type: "image/png" }));
        // ГРАБЛЯ 6.2: image_category/is_intermediate — параметры QUERY, не поля формы.
        fetch("/api/v1/images/upload?image_category=other&is_intermediate=true&silent=true",
          { method: "POST", body: fd })
          .then(function (r) { return r.json(); })
          .then(function (dto) {
            if (dto && dto.image_name) resolve(dto);
            else reject(new Error(JSON.stringify(dto).slice(0, 160)));
          })
          .catch(reject);
      }, "image/png");
    });
  }

  function imageObject(dto) {
    return {
      id: "image_devbimcut_" + Math.random().toString(36).slice(2, 12),
      type: "image",
      image: { image_name: dto.image_name, width: dto.width, height: dto.height }
    };
  }

  // ---------- плавное перемещение кусочков ----------
  // Штатно настройки холста включают «привязку к сетке» (snapToGrid:
  // 64 px, с Ctrl — 8 px) — слой-кусочек при перетаскивании «прыгает».
  // Кусочки опознаём по префиксу id объекта (живёт в состоянии канваса,
  // переживает F5); пока тащат кусочек — сетка позиционирования = 1 px.
  function isOurPiece(entity) {
    var objs = entity && entity.objects;
    if (!objs) return false;
    for (var i = 0; i < objs.length; i++) {
      if (objs[i].type === "image" &&
        String(objs[i].id || "").indexOf("image_devbimcut_") === 0) return true;
    }
    return false;
  }

  function ourPieceDragging(m) {
    try {
      var ents = canvasState(m.stateApi.store).rasterLayers.entities;
      for (var i = 0; i < ents.length; i++) {
        if (!isOurPiece(ents[i])) continue;
        var a = m.getAdapter({ id: ents[i].id, type: "raster_layer" });
        var pr = a && a.transformer && a.transformer.konva && a.transformer.konva.proxyRect;
        if (pr && pr.isDragging && pr.isDragging()) return true;
      }
    } catch (e) { /* состояние недоступно — просто штатная сетка */ }
    return false;
  }

  function ensureSmoothPatch() {
    var m = manager();
    if (!m || !m.stateApi || !m.stateApi.getPositionGridSize) return;
    var api = m.stateApi;
    if (api.__devbimSmooth) return;
    var orig = api.getPositionGridSize;
    api.getPositionGridSize = function () {
      try {
        if (ourPieceDragging(manager())) return 1;
      } catch (e) { /* noop */ }
      return orig.apply(api, arguments);
    };
    api.__devbimSmooth = true;
  }

  function polyPath(g, poly, off) {
    g.beginPath();
    for (var i = 0; i < poly.length; i++) {
      var x = poly[i].x - off.x, y = poly[i].y - off.y;
      if (i) g.lineTo(x, y); else g.moveTo(x, y);
    }
    g.closePath();
  }

  function confirmCut() {
    if (!mode.active || mode.busy) return;
    if (mode.points.length < 3) { toast(L.few); return; }
    var m = manager();
    if (!m) return;
    var store = m.stateApi.store;
    var cs = canvasState(store);
    var layer = resolveLayer(cs);
    if (!layer) { toast(L.noLayer); exitMode(); return; }
    mode.busy = true;
    syncBar();
    doCut(m, store, layer).then(function () {
      mode.busy = false;
      exitMode();
      toast(L.done);
    }).catch(function (err) {
      mode.busy = false;
      exitMode();
      toast(L.error + (err && err.message ? err.message : err), 4200);
    });
  }

  function doCut(m, store, layer) {
    var cs = canvasState(store);
    var adapter = m.getAdapter({ id: layer.id, type: "raster_layer" });
    if (!adapter || !adapter.renderer || !adapter.renderer.getCanvas) {
      return Promise.reject(new Error("adapter/renderer unavailable"));
    }
    var pos = layer.position || { x: 0, y: 0 };
    var polyO = mode.points.map(function (p) { return { x: p.x - pos.x, y: p.y - pos.y }; });
    var bb = { x0: Infinity, y0: Infinity, x1: -Infinity, y1: -Infinity };
    polyO.forEach(function (p) {
      bb.x0 = Math.min(bb.x0, p.x); bb.y0 = Math.min(bb.y0, p.y);
      bb.x1 = Math.max(bb.x1, p.x); bb.y1 = Math.max(bb.y1, p.y);
    });
    var doc = cs.document || {};
    var W = doc.width || 512, H = doc.height || 512;
    // область растеризации: документ ∪ bbox полигона ∪ фактические границы
    // содержимого группы (координаты объектов)
    var rx = Math.min(0, Math.floor(bb.x0)), ry = Math.min(0, Math.floor(bb.y0));
    var rx1 = Math.max(W, Math.ceil(bb.x1)), ry1 = Math.max(H, Math.ceil(bb.y1));
    try {
      var g = adapter.renderer.konva.objectGroup;
      if (g && g.getClientRect) {
        var cr = g.getClientRect({ relativeTo: g });
        if (cr && isFinite(cr.x + cr.y + cr.width + cr.height) && cr.width > 0 && cr.height > 0) {
          rx = Math.min(rx, Math.floor(cr.x));
          ry = Math.min(ry, Math.floor(cr.y));
          rx1 = Math.max(rx1, Math.ceil(cr.x + cr.width));
          ry1 = Math.max(ry1, Math.ceil(cr.y + cr.height));
        }
      }
    } catch (e) { /* необязательная оптимизация полноты */ }
    if (rx1 - rx > MAX_SIDE) { rx1 = rx + MAX_SIDE; }
    if (ry1 - ry > MAX_SIDE) { ry1 = ry + MAX_SIDE; }
    var rw = Math.max(1, rx1 - rx), rh = Math.max(1, ry1 - ry);

    var full = adapter.renderer.getCanvas({ rect: { x: rx, y: ry, width: rw, height: rh } });
    if (!full) return Promise.reject(new Error("getCanvas failed"));

    // кусок: bbox полигона, всё вне полигона — прозрачно.
    // ИСХОДНИК НЕ МЕНЯЕТСЯ: подложка остаётся с оригинальным изображением.
    var px0 = Math.floor(bb.x0), py0 = Math.floor(bb.y0);
    var pw = Math.max(1, Math.ceil(bb.x1) - px0), ph = Math.max(1, Math.ceil(bb.y1) - py0);
    var piece = document.createElement("canvas");
    piece.width = pw; piece.height = ph;
    var pg = piece.getContext("2d");
    pg.drawImage(full, px0 - rx, py0 - ry, pw, ph, 0, 0, pw, ph);
    pg.globalCompositeOperation = "destination-in";
    polyPath(pg, polyO, { x: px0, y: py0 });
    pg.fill();

    var beforeIds = {};
    (canvasState(store).rasterLayers.entities || []).forEach(function (e) { beforeIds[e.id] = 1; });

    return uploadCanvas(piece, "devbim_cut_piece.png").then(function (pieceDto) {
      // новый слой (добавляется последним = поверх всех); НЕ выделяем —
      // иначе вокруг кусочка появится рамка выделения
      m.stateApi.addRasterLayer({ isSelected: false });
      return waitForNewLayer(store, beforeIds, 60).then(function (newId) {
        var posOut = { x: px0 + pos.x, y: py0 + pos.y };
        store.dispatch({
          type: "canvas/entityRasterized",
          payload: {
            entityIdentifier: { id: newId, type: "raster_layer" },
            imageObject: imageObject(pieceDto),
            position: posOut,
            replaceObjects: true,
            isSelected: false
          }
        });
        lastCut = { dto: pieceDto, position: posOut };
        pasteCount = 0;
      });
    });
  }

  // Ctrl+V: копия последнего вырезанного кусочка новым слоем (со сдвигом,
  // чтобы повторные вставки были видны).
  function pastePiece() {
    if (!lastCut || pasteBusy) return;
    var m = manager();
    if (!m) return;
    pasteBusy = true;
    var store = m.stateApi.store;
    var beforeIds = {};
    (canvasState(store).rasterLayers.entities || []).forEach(function (e) { beforeIds[e.id] = 1; });
    m.stateApi.addRasterLayer({ isSelected: false });
    waitForNewLayer(store, beforeIds, 60).then(function (newId) {
      pasteCount++;
      store.dispatch({
        type: "canvas/entityRasterized",
        payload: {
          entityIdentifier: { id: newId, type: "raster_layer" },
          imageObject: imageObject(lastCut.dto),
          position: { x: lastCut.position.x + 24 * pasteCount, y: lastCut.position.y + 24 * pasteCount },
          replaceObjects: true,
          isSelected: false
        }
      });
      pasteBusy = false;
      toast(L.pasted);
    }).catch(function (err) {
      pasteBusy = false;
      toast(L.error + (err && err.message ? err.message : err), 4200);
    });
  }

  function waitForNewLayer(store, beforeIds, tries) {
    return new Promise(function (resolve, reject) {
      var n = 0;
      (function poll() {
        var ents = canvasState(store).rasterLayers.entities;
        for (var i = 0; i < ents.length; i++) {
          if (!beforeIds[ents[i].id]) { resolve(ents[i].id); return; }
        }
        if (++n >= tries) { reject(new Error("new layer not created")); return; }
        setTimeout(poll, 50);
      })();
    });
  }

  // ---------- тик ----------
  function tick() {
    var m = manager();
    var panel = canvasPanelActive();
    if (m && panel && tabOk()) {
      ensureRailButton();
      ensureSmoothPatch(); // плавный драг кусочков (патч на менеджера)
    } else if (railButton() && railButton().parentElement) {
      railButton().remove();
    }
    if (mode.active && (!panel || !m)) {
      exitMode(); // панель холста демонтирована — режим не имеет смысла
    }
    if (mode.active) syncBar();
  }

  function start() {
    bindEvents(); // глобальный Ctrl+V (вставка) работает и вне режима
    setInterval(tick, TICK_MS);
    tick();
  }

  // отладка
  window.__devbimCut = {
    state: function () { return { active: mode.active, points: mode.points.slice(), closed: mode.closed, busy: mode.busy }; },
    cancel: cancelMode,
    confirm: confirmCut,
    paste: pastePiece,
    clipboard: function () { return lastCut ? { position: lastCut.position, image: lastCut.dto.image_name, w: lastCut.dto.width, h: lastCut.dto.height } : null; }
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
})();
