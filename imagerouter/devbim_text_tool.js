// DevBIM — «Текст» (T): текстовый слой на холсте InvokeAI.
// Кнопка T в вертикальной рейке инструментов открывает панель: текст
// (многострочно), цвет (пикер + hex), размер шрифта (px), гарнитура,
// жирность. «Добавить» рендерит текст в растр и кладёт НОВЫМ растровым
// слоем (одним диспатчем через overrides — путь sentImageToCanvas),
// «Применить» перерисовывает текст ВЫДЕЛЕННОГО текстового слоя.
// Настройки слоя живут в localStorage (ключ = id слоя — переживает F5 и
// bbox-растеризацию, у которой меняется лишь id объекта). Слой двигается
// (V) и масштабируется (B) штатными инструментами; перетаскивание —
// плавное (обёртка getPositionGridSize, свои текстовые слои = 1 px).
// Деплой: setup_imagerouter.py → dist/devbim-text-tool.js (+script в
// index.html). Мост: window.__devbimCanvasBridge.getManager().
(function () {
  "use strict";

  var TICK_MS = 500;
  var MAX_SIDE = 8192;    // предохранитель стороны растра текста
  var ID = "devbim-text";
  var PANEL_ID = "devbim-textbar";
  var TOAST_ID = "devbim-text-toast";
  var BTN_ID = "devbim-text-btn";
  var PREVIEW_ID = "devbim-text-preview";
  var LS_KEY = "devbimTextLayers";
  var OBJ_PREFIX = "image_devbimtext_";
  var REG_CAP = 500;

  var RU = (navigator.language || "").toLowerCase().indexOf("ru") === 0;
  var L = RU ? {
    btn: "Текст (T)",
    title: "Текст",
    placeholder: "Введите текст…",
    add: "Добавить",
    apply: "Применить",
    newLayer: "Новый слой",
    editHint: "Правится выделенный текстовый слой",
    hint: "Esc — закрыть · Ctrl+Enter — добавить/применить · размер — шрифтом или bbox (B)",
    done: "Текст — на новом слое",
    updated: "Текст обновлён",
    empty: "Введите текст",
    tooBig: "Слишком длинная строка (лимит 8192 px)",
    gone: "Слой исчез — правка отменена",
    err: "Ошибка текста: "
  } : {
    btn: "Text (T)",
    title: "Text",
    placeholder: "Type text…",
    add: "Add",
    apply: "Apply",
    newLayer: "New layer",
    editHint: "Editing the selected text layer",
    hint: "Esc — close · Ctrl+Enter — add/apply · size — font or bbox (B)",
    done: "Text placed on a new layer",
    updated: "Text updated",
    empty: "Enter some text",
    tooBig: "Line too long (limit 8192 px)",
    gone: "Layer is gone — edit cancelled",
    err: "Text error: "
  };

  var FONTS = [
    { id: "sans", css: 'Inter, "Segoe UI", system-ui, sans-serif' },
    { id: "serif", css: 'Georgia, "Times New Roman", serif' },
    { id: "mono", css: 'Consolas, "Courier New", monospace' }
  ];

  var ICON_TYPE =
    '<svg viewBox="0 0 24 24" width="1em" height="1em" fill="none" stroke="currentColor" stroke-width="2" ' +
    'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="4 7 4 4 20 4 20 7"/>' +
    '<line x1="9" y1="20" x2="15" y2="20"/><line x1="12" y1="4" x2="12" y2="20"/></svg>';
  var ICON_NO =
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" ' +
    'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><line x1="18" y1="6" x2="6" y2="18"/>' +
    '<line x1="6" y1="6" x2="18" y2="18"/></svg>';

  var STYLE = [
    "#" + PANEL_ID + "{position:fixed;bottom:142px;left:50%;transform:translateX(-50%);z-index:1400;",
    "display:none;flex-direction:column;gap:6px;padding:10px;width:360px;max-width:92vw;border-radius:12px;",
    "background:#0B0C0E;border:1px solid rgba(56,189,248,.35);box-shadow:0 4px 16px rgba(0,0,0,.45);",
    "font-family:Inter,system-ui,sans-serif;color:rgba(255,255,255,.85)}",
    "#" + PANEL_ID + " .head{display:flex;align-items:center;justify-content:space-between}",
    "#" + PANEL_ID + " .tag{display:flex;align-items:center;gap:6px;color:#38BDF8;font-size:13px}",
    "#" + PANEL_ID + " .tag svg{width:15px;height:15px;flex:none}",
    "#" + PANEL_ID + " .x{display:flex;align-items:center;justify-content:center;width:24px;height:24px;",
    "border:0;border-radius:6px;background:transparent;color:rgba(255,255,255,.6);cursor:pointer}",
    "#" + PANEL_ID + " .x:hover{background:rgba(255,255,255,.08);color:#fff}",
    "#" + PANEL_ID + " textarea{width:100%;box-sizing:border-box;resize:vertical;min-height:44px;max-height:160px;",
    "padding:6px 8px;border-radius:8px;border:1px solid rgba(255,255,255,.14);background:#14161A;",
    "color:#E6E8EC;font-size:13px;line-height:1.3;font-family:inherit;outline:none}",
    "#" + PANEL_ID + " textarea:focus{border-color:rgba(56,189,248,.6)}",
    "#" + PANEL_ID + " .row{display:flex;align-items:center;gap:6px}",
    "#" + PANEL_ID + " input,#" + PANEL_ID + " select{padding:3px 6px;border-radius:6px;",
    "border:1px solid rgba(255,255,255,.14);background:#14161A;color:#E6E8EC;font-size:12px;outline:none}",
    "#" + PANEL_ID + " input[type=color]{padding:1px 2px;width:34px;height:26px;cursor:pointer}",
    "#" + PANEL_ID + " .hex{width:76px;text-transform:lowercase}",
    "#" + PANEL_ID + " .sz{width:58px}",
    "#" + PANEL_ID + " select{cursor:pointer}",
    "#" + PANEL_ID + " .bold{display:flex;align-items:center;gap:3px;font-size:12px;cursor:pointer;",
    "user-select:none;font-weight:700}",
    "#" + PANEL_ID + " .main{display:flex;align-items:center;gap:6px}",
    "#" + PANEL_ID + " .btn{padding:5px 14px;border-radius:8px;border:0;cursor:pointer;font-size:13px;",
    "background:#38BDF8;color:#0B0C0E;font-weight:600}",
    "#" + PANEL_ID + " .btn:hover{background:#5cc8fa}",
    "#" + PANEL_ID + " .btn:disabled{opacity:.4;cursor:default}",
    "#" + PANEL_ID + " .btn2{padding:5px 10px;border-radius:8px;border:1px solid rgba(255,255,255,.18);",
    "cursor:pointer;font-size:12px;background:transparent;color:rgba(255,255,255,.75)}",
    "#" + PANEL_ID + " .btn2:hover{background:rgba(255,255,255,.08);color:#fff}",
    "#" + PANEL_ID + " .hint{padding:0 2px;color:rgba(255,255,255,.4);font-size:10.5px;line-height:1.35}",
    "#" + PANEL_ID + " .edit{color:#38BDF8;font-size:11px;padding:0 2px}",
    "#" + TOAST_ID + "{position:fixed;bottom:150px;left:50%;transform:translateX(-50%);z-index:1500;",
    "display:none;padding:10px 16px;border-radius:10px;background:#0B0C0E;color:rgba(255,255,255,.85);",
    "border:1px solid rgba(255,255,255,.12);font-size:13px;box-shadow:0 4px 16px rgba(0,0,0,.5);max-width:70vw}",
    "#" + PREVIEW_ID + "{position:fixed;z-index:1399;pointer-events:none;display:none;white-space:pre;",
    "line-height:1.25;border:1px dashed rgba(56,189,248,.55)}"
  ].join("");

  // ---------- состояние ----------
  var open = false, busy = false, editingId = null;
  var st = { text: "", color: "#ffffff", size: 64, family: "sans", bold: false };
  var metrics = { w: 0, h: 0, pad: 2, lineH: 0 };
  var panel = null, elText = null, elColor = null, elHex = null, elSize = null,
      elFont = null, elBold = null, elMain = null, elNew = null, elEdit = null;
  var rafId = 0, toastTimer = 0, subStore = null, subUnsub = null, gcCount = 0;
  var measCtx = null;

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

  // ГРАБЛЯ: кэш абсолютного трансформа stage может быть отравлен NaN
  // (проверено E2E 10.09: attrs чистые, getAbsoluteTransform() возвращает
  // NaN до следующего РЕАЛЬНОГО изменения атрибута). Зум приложения =
  // scale + position без поворота — считаем сами по атрибутам.
  function stageXform(m) {
    var st = m.stage.konva.stage;
    var s = st.scaleX(), x = st.x(), y = st.y();
    return { s: isFinite(s) && s ? s : 1, x: isFinite(x) ? x : 0, y: isFinite(y) ? y : 0 };
  }

  function toScreen(m, p) {
    var rect = stageEl(m).getBoundingClientRect();
    var t = stageXform(m);
    return { x: t.x + p.x * t.s + rect.left, y: t.y + p.y * t.s + rect.top };
  }

  function stageScale(m) {
    return stageXform(m).s;
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

  // ---------- реестр текстовых слоёв (localStorage, ключ = id слоя) ----------
  function registry() {
    try { return JSON.parse(localStorage.getItem(LS_KEY) || "{}") || {}; }
    catch (e) { return {}; }
  }

  function regSave(reg) {
    var keys = Object.keys(reg);
    if (keys.length > REG_CAP) {
      keys.sort();
      keys.slice(0, keys.length - REG_CAP).forEach(function (k) { delete reg[k]; });
    }
    try { localStorage.setItem(LS_KEY, JSON.stringify(reg)); } catch (e) { /* переполнение — не критично */ }
  }

  function regSet(layerId, entry) {
    var reg = registry();
    reg[layerId] = entry;
    regSave(reg);
  }

  function snapshot() {
    return { text: st.text, color: st.color, size: st.size, family: st.family, bold: !!st.bold };
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
    if (f.rail.querySelector("#" + BTN_ID)) return;
    var b = document.createElement("button");
    b.id = BTN_ID;
    b.type = "button";
    b.className = f.ref.className;
    b.setAttribute("aria-label", L.btn);
    b.title = L.btn;
    b.innerHTML = ICON_TYPE;
    b.onclick = function (e) { e.stopPropagation(); open ? closePanel() : openPanel(); };
    f.rail.appendChild(b);
    syncRailButton();
  }

  function railButton() { return document.getElementById(BTN_ID); }

  function syncRailButton() {
    var b = railButton();
    if (!b) return;
    if (open) {
      b.style.background = "rgb(71,177,230)";
      b.style.color = "rgb(22,24,29)";
    } else {
      b.style.background = "";
      b.style.color = "";
    }
  }

  // ---------- стиль / панель ----------
  function ensureStyle() {
    if (document.getElementById(ID + "-style")) return;
    var s = document.createElement("style");
    s.id = ID + "-style";
    s.textContent = STYLE;
    document.head.appendChild(s);
  }

  function familyCss() {
    for (var i = 0; i < FONTS.length; i++) if (FONTS[i].id === st.family) return FONTS[i].css;
    return FONTS[0].css;
  }

  function fontString() {
    return (st.bold ? "bold " : "") + st.size + "px " + familyCss();
  }

  function buildPanel() {
    if (panel) return;
    ensureStyle();
    panel = document.createElement("div");
    panel.id = PANEL_ID;

    var head = document.createElement("div");
    head.className = "head";
    var tag = document.createElement("span");
    tag.className = "tag";
    tag.innerHTML = ICON_TYPE;
    tag.appendChild(document.createTextNode(L.title));
    var x = document.createElement("button");
    x.type = "button";
    x.className = "x";
    x.title = "Esc";
    x.innerHTML = ICON_NO;
    x.onclick = function (e) { e.stopPropagation(); closePanel(); };
    head.appendChild(tag);
    head.appendChild(x);

    elText = document.createElement("textarea");
    elText.rows = 2;
    elText.placeholder = L.placeholder;
    elText.spellcheck = false;
    elText.addEventListener("input", function () { st.text = elText.value; onSettingsChanged(); });

    var row = document.createElement("div");
    row.className = "row";
    elColor = document.createElement("input");
    elColor.type = "color";
    elColor.title = "Color";
    elColor.value = st.color;
    elColor.addEventListener("input", function () {
      st.color = elColor.value;
      elHex.value = st.color;
    });
    elHex = document.createElement("input");
    elHex.type = "text";
    elHex.className = "hex";
    elHex.value = st.color;
    elHex.spellcheck = false;
    elHex.maxLength = 7;
    elHex.addEventListener("change", function () {
      var v = elHex.value.trim();
      if (/^#[0-9a-f]{6}$/i.test(v)) {
        st.color = v.toLowerCase();
      } else if (/^#[0-9a-f]{3}$/i.test(v)) {
        st.color = "#" + v.slice(1).split("").map(function (c) { return c + c; }).join("");
      }
      elHex.value = st.color;
      elColor.value = st.color;
    });
    elSize = document.createElement("input");
    elSize.type = "number";
    elSize.className = "sz";
    elSize.min = "8";
    elSize.max = "512";
    elSize.step = "1";
    elSize.value = String(st.size);
    elSize.title = "px";
    elSize.addEventListener("change", function () {
      var n = parseInt(elSize.value, 10);
      if (!isFinite(n)) n = st.size;
      st.size = Math.min(512, Math.max(8, n));
      elSize.value = String(st.size);
      onSettingsChanged();
    });
    elFont = document.createElement("select");
    FONTS.forEach(function (f) {
      var o = document.createElement("option");
      o.value = f.id;
      o.textContent = f.id === "sans" ? (RU ? "Без засечек" : "Sans")
        : f.id === "serif" ? (RU ? "С засечками" : "Serif")
        : (RU ? "Моно" : "Mono");
      elFont.appendChild(o);
    });
    elFont.value = st.family;
    elFont.addEventListener("change", function () { st.family = elFont.value; onSettingsChanged(); });
    var bl = document.createElement("label");
    bl.className = "bold";
    elBold = document.createElement("input");
    elBold.type = "checkbox";
    elBold.addEventListener("change", function () { st.bold = elBold.checked; onSettingsChanged(); });
    bl.appendChild(elBold);
    bl.appendChild(document.createTextNode("Ж"));
    row.appendChild(elColor);
    row.appendChild(elHex);
    row.appendChild(elSize);
    row.appendChild(elFont);
    row.appendChild(bl);

    var main = document.createElement("div");
    main.className = "main";
    elMain = document.createElement("button");
    elMain.type = "button";
    elMain.className = "btn";
    elMain.textContent = L.add;
    elMain.onclick = function (e) { e.stopPropagation(); editingId ? doApply() : doAdd(); };
    elNew = document.createElement("button");
    elNew.type = "button";
    elNew.className = "btn2";
    elNew.textContent = L.newLayer;
    elNew.onclick = function (e) { e.stopPropagation(); doAdd(); };
    main.appendChild(elMain);
    main.appendChild(elNew);

    elEdit = document.createElement("div");
    elEdit.className = "edit";
    elEdit.textContent = L.editHint;

    var hint = document.createElement("div");
    hint.className = "hint";
    hint.textContent = L.hint;

    panel.appendChild(head);
    panel.appendChild(elText);
    panel.appendChild(row);
    panel.appendChild(main);
    panel.appendChild(elEdit);
    panel.appendChild(hint);
    document.body.appendChild(panel);
  }

  function fillInputs() {
    elText.value = st.text;
    elColor.value = st.color;
    elHex.value = st.color;
    elSize.value = String(st.size);
    elFont.value = st.family;
    elBold.checked = !!st.bold;
    onSettingsChanged();
  }

  function syncPanel() {
    if (!panel) return;
    panel.style.display = open ? "flex" : "none";
    elMain.textContent = editingId ? L.apply : L.add;
    elMain.disabled = busy || !st.text.trim();
    elMain.textContent = busy ? "…" : elMain.textContent;
    elNew.style.display = editingId && !busy ? "" : "none";
    elEdit.style.display = editingId ? "" : "none";
  }

  // ---------- рендер текста ----------
  function ensureMeasCtx() {
    if (!measCtx) {
      var c = document.createElement("canvas");
      c.width = 8; c.height = 8;
      measCtx = c.getContext("2d");
    }
    return measCtx;
  }

  function measure() {
    var lines = st.text.split("\n");
    var lineH = st.size * 1.25;
    var pad = Math.max(2, Math.round(st.size * 0.12));
    var g = ensureMeasCtx();
    g.font = fontString();
    var w = 0;
    for (var i = 0; i < lines.length; i++) {
      var lw = g.measureText(lines[i]).width;
      if (lw > w) w = lw;
    }
    metrics = {
      w: Math.ceil(w) + pad * 2,
      h: Math.ceil(lines.length * lineH) + pad * 2,
      pad: pad,
      lineH: lineH
    };
    return metrics;
  }

  function onSettingsChanged() {
    measure();
    syncPanel();
  }

  // Konva показывает картинку объекта в НАТУРАЛЬНОМ размере (image.width/
  // height из DTO) — растр рендерим ровно в документных пикселях 1:1.
  function rasterize() {
    var m = measure();
    if (m.w > MAX_SIDE || m.h > MAX_SIDE) throw new Error(L.tooBig);
    var lines = st.text.split("\n");
    var cv = document.createElement("canvas");
    cv.width = m.w;
    cv.height = m.h;
    var g = cv.getContext("2d");
    g.font = fontString();
    g.fillStyle = st.color;
    g.textBaseline = "top";
    for (var i = 0; i < lines.length; i++) {
      g.fillText(lines[i], m.pad, m.pad + i * m.lineH);
    }
    return { canvas: cv, w: m.w, h: m.h };
  }

  function layerName() {
    var first = "";
    st.text.split("\n").forEach(function (ln) {
      if (!first && ln.trim()) first = ln.trim();
    });
    if (!first) first = "—";
    if (first.length > 24) first = first.slice(0, 24) + "…";
    return "T · " + first;
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
      id: OBJ_PREFIX + Math.random().toString(36).slice(2, 12),
      type: "image",
      image: { image_name: dto.image_name, width: dto.width, height: dto.height }
    };
  }

  // Куда встанет новый текст: центр видимой области канваса в координатах
  // документа (половина блока вычитается, clamp в границы документа).
  // При любых NaN — центр документа.
  function targetPosition(cs, w, h) {
    var m = manager();
    var doc = cs.document || {};
    var W = doc.width || 1536, H = doc.height || 1024;
    var pos = { x: Math.round((W - w) / 2), y: Math.round((H - h) / 2) };
    if (!m) return pos;
    var rect = stageEl(m).getBoundingClientRect();
    if (!rect.width || !rect.height) return pos;
    var t = stageXform(m);
    var p = { x: (rect.width / 2 - t.x) / t.s, y: (rect.height / 2 - t.y) / t.s };
    if (isFinite(p.x) && isFinite(p.y)) {
      pos = {
        x: Math.max(0, Math.min(Math.round(p.x - w / 2), Math.max(0, W - w))),
        y: Math.max(0, Math.min(Math.round(p.y - h / 2), Math.max(0, H - h)))
      };
    }
    return pos;
  }

  function findEntity(cs, layerId) {
    var ents = cs.rasterLayers.entities;
    for (var i = 0; i < ents.length; i++) if (ents[i].id === layerId) return ents[i];
    return null;
  }

  // ---------- добавить ----------
  function doAdd() {
    if (busy) return;
    if (!st.text.trim()) { toast(L.empty); return; }
    var m = manager();
    if (!m) return;
    var store = m.stateApi.store;
    busy = true;
    syncPanel();
    Promise.resolve().then(function () {
      var r = rasterize();
      return uploadCanvas(r.canvas, "devbim_text.png").then(function (dto) {
        var cs = canvasState(store);
        var pos = targetPosition(cs, r.w, r.h);
        // Один диспатч: объекты/позиция/имя — overrides (путь sentImageToCanvas)
        m.stateApi.addRasterLayer({
          isSelected: false,
          overrides: { name: layerName(), objects: [imageObject(dto)], position: pos }
        });
        var ents = canvasState(store).rasterLayers.entities;
        var newId = ents.length ? ents[ents.length - 1].id : null;
        if (!newId) throw new Error("layer not created");
        regSet(newId, snapshot());
      });
    }).then(function () {
      busy = false;
      syncPanel();
      toast(L.done);
    }).catch(function (err) {
      busy = false;
      syncPanel();
      toast(L.err + (err && err.message ? err.message : err), 4200);
    });
  }

  // ---------- применить (правка выделенного текстового слоя) ----------
  function doApply() {
    if (busy) return;
    if (!st.text.trim()) { toast(L.empty); return; }
    var m = manager();
    if (!m) return;
    var store = m.stateApi.store;
    var layer = editingId ? findEntity(canvasState(store), editingId) : null;
    if (!layer) {
      editingId = null;
      syncPanel();
      toast(L.gone);
      return;
    }
    busy = true;
    syncPanel();
    Promise.resolve().then(function () {
      var r = rasterize();
      return uploadCanvas(r.canvas, "devbim_text.png").then(function (dto) {
        var ent = { id: layer.id, type: "raster_layer" };
        store.dispatch({
          type: "canvas/entityRasterized",
          payload: {
            entityIdentifier: ent,
            imageObject: imageObject(dto),
            position: layer.position || { x: 0, y: 0 },
            replaceObjects: true,
            isSelected: false
          }
        });
        store.dispatch({
          type: "canvas/entityNameChanged",
          payload: { entityIdentifier: ent, name: layerName() }
        });
        regSet(layer.id, snapshot());
      });
    }).then(function () {
      busy = false;
      syncPanel();
      toast(L.updated);
    }).catch(function (err) {
      busy = false;
      syncPanel();
      toast(L.err + (err && err.message ? err.message : err), 4200);
    });
  }

  // ---------- цель правки: выделенный слой из реестра ----------
  function currentTarget() {
    var m = manager();
    if (!m) return null;
    var cs = canvasState(m.stateApi.store);
    var sel = cs.selectedEntityIdentifier;
    if (sel && sel.type === "raster_layer" && registry()[sel.id]) return sel.id;
    return null;
  }

  function syncEditTarget(force) {
    var t = currentTarget();
    if (!force && t === editingId) return;
    editingId = t;
    if (t) {
      var e = registry()[t];
      if (e) {
        st = {
          text: e.text || "",
          color: e.color || "#ffffff",
          size: e.size || 64,
          family: e.family || "sans",
          bold: !!e.bold
        };
        fillInputs();
      }
    }
    syncPanel();
  }

  // ---------- живое превью (только для НОВОГО текста) ----------
  function ensurePreview() {
    if (document.getElementById(PREVIEW_ID)) return;
    ensureStyle();
    var pv = document.createElement("div");
    pv.id = PREVIEW_ID;
    document.body.appendChild(pv);
  }

  function drawPreview() {
    var pv = document.getElementById(PREVIEW_ID);
    if (!pv) return;
    var m = manager();
    if (!m || editingId || busy || !st.text.trim()) {
      pv.style.display = "none";
      return;
    }
    var cs = canvasState(m.stateApi.store);
    var pos = targetPosition(cs, metrics.w, metrics.h);
    var s = toScreen(m, pos);
    var k = stageScale(m);
    pv.style.display = "block";
    pv.style.left = s.x + "px";
    pv.style.top = s.y + "px";
    pv.style.color = st.color;
    pv.style.font = (st.bold ? "bold " : "") + Math.max(1, st.size * k) + "px " + familyCss();
    pv.style.padding = Math.max(1, metrics.pad * k) + "px";
    pv.textContent = st.text;
  }

  function loop() {
    if (!open) return;
    drawPreview();
    rafId = requestAnimationFrame(loop);
  }

  // ---------- панель ----------
  function openPanel() {
    if (open) return;
    var m = manager();
    if (!m) return;
    buildPanel();
    ensurePreview();
    open = true;
    syncEditTarget(true);
    if (rafId) cancelAnimationFrame(rafId);
    rafId = requestAnimationFrame(loop);
    syncPanel();
    syncRailButton();
    setTimeout(function () { if (open && elText && !editingId) elText.focus(); }, 30);
  }

  function closePanel() {
    if (busy) return;
    open = false;
    editingId = null;
    if (rafId) { cancelAnimationFrame(rafId); rafId = 0; }
    var pv = document.getElementById(PREVIEW_ID);
    if (pv) pv.style.display = "none";
    syncPanel();
    syncRailButton();
  }

  // ---------- клавиатура ----------
  function onKeyDown(e) {
    if (!open) return;
    if (e.key === "Escape") {
      if (busy) return;
      e.preventDefault();
      e.stopPropagation();
      closePanel();
    } else if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
      e.preventDefault();
      e.stopPropagation();
      editingId ? doApply() : doAdd();
    }
  }

  // ---------- плавное перетаскивание текстовых слоёв ----------
  // Штатный snapToGrid (64 px) заставляет слой прыгать по сетке; пока
  // тащат НАШ текстовый слой — позиционная сетка 1 px. Обёртка цепочкой
  // после ✂-обёртки (её флаг __devbimSmooth не трогаем).
  function isOurLayer(entity) {
    if (registry()[entity.id]) return true;
    var objs = entity.objects;
    if (!objs) return false;
    for (var i = 0; i < objs.length; i++) {
      if (objs[i].type === "image" &&
        String(objs[i].id || "").indexOf(OBJ_PREFIX) === 0) return true;
    }
    return false;
  }

  function ourTextDragging(m) {
    try {
      var ents = canvasState(m.stateApi.store).rasterLayers.entities;
      for (var i = 0; i < ents.length; i++) {
        if (!isOurLayer(ents[i])) continue;
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
    if (api.__devbimTextSmooth) return;
    var orig = api.getPositionGridSize;
    api.getPositionGridSize = function () {
      try {
        if (ourTextDragging(manager())) return 1;
      } catch (e) { /* noop */ }
      return orig.apply(api, arguments);
    };
    api.__devbimTextSmooth = true;
  }

  // ---------- подписка на store (смена выделения → режим правки) ----------
  function ensureStoreSub() {
    var m = manager();
    if (!m) return;
    var store = m.stateApi.store;
    if (subStore === store) return;
    if (subUnsub) { try { subUnsub(); } catch (e) { /* noop */ } }
    subStore = store;
    subUnsub = store.subscribe(function () {
      if (open && !busy) syncEditTarget(false);
    });
  }

  // ---------- чистка реестра (удалённые слои) ----------
  function gcRegistry() {
    var m = manager();
    if (!m) return;
    var reg = registry();
    var keys = Object.keys(reg);
    if (!keys.length) return;
    var ents = canvasState(m.stateApi.store).rasterLayers.entities;
    var live = {};
    ents.forEach(function (e) { live[e.id] = 1; });
    var changed = false;
    keys.forEach(function (k) {
      if (!live[k]) { delete reg[k]; changed = true; }
    });
    if (changed) regSave(reg);
  }

  // ---------- тик ----------
  function canvasPanelActive() {
    return !!document.querySelector(".konvajs-content");
  }

  function tabOk() {
    return window.__devbimGetTab ? window.__devbimGetTab() === "canvas" : false;
  }

  function tick() {
    var m = manager();
    var panelActive = canvasPanelActive();
    if (m && panelActive && tabOk()) {
      ensureRailButton();
      ensureSmoothPatch();
      ensureStoreSub();
    } else if (railButton() && railButton().parentElement) {
      railButton().remove();
    }
    if (open && (!panelActive || !m)) {
      open = false; // рабочая область холста демонтирована
      editingId = null;
      if (rafId) { cancelAnimationFrame(rafId); rafId = 0; }
      var pv = document.getElementById(PREVIEW_ID);
      if (pv) pv.style.display = "none";
      syncPanel();
      syncRailButton();
    }
    if (m && !open && ++gcCount >= 20) { gcCount = 0; gcRegistry(); }
  }

  function start() {
    window.addEventListener("keydown", onKeyDown, true);
    setInterval(tick, TICK_MS);
    tick();
  }

  // отладка
  window.__devbimText = {
    state: function () {
      return { open: open, busy: busy, editingId: editingId, settings: snapshot(), metrics: metrics };
    },
    settings: function () { return snapshot(); },
    open: openPanel,
    close: closePanel,
    add: doAdd,
    apply: doApply,
    registry: registry
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
})();
