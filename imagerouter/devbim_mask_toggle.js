// DevBIM — тумблер «Маска / Слой» на холсте InvokeAI.
// Показывает, каким слоем рисует кисть, и переключает слой одним кликом.
// Деплой: setup_imagerouter.py → dist/devbim-mask-toggle.js (+script в index.html).
// Мост: window.__devbimCanvasBridge.getManager() — патч App-бандла.
(function () {
  "use strict";

  var TICK_MS = 500;
  var ID = "devbim-mask-toggle";
  var STYLE = [
    "#" + ID + "{position:fixed;bottom:96px;left:50%;transform:translateX(-50%);",
    "z-index:1400;display:none;align-items:center;gap:2px;padding:4px;",
    "border-radius:999px;background:#0B0C0E;border:1px solid rgba(255,255,255,.08);",
    "box-shadow:0 4px 16px rgba(0,0,0,.4)}",
    "#" + ID + " button{display:flex;align-items:center;gap:6px;padding:6px 14px;",
    "border:0;border-radius:999px;background:transparent;color:rgba(255,255,255,.72);",
    "font-size:13px;line-height:1;cursor:pointer;font-family:inherit}",
    "#" + ID + " button:hover{background:rgba(255,255,255,.06);color:#fff}",
    "#" + ID + " button.active{background:rgba(56,189,248,.16);color:#38BDF8}",
    "#" + ID + " svg{width:14px;height:14px;flex:none}"
  ].join("");
  var ICON_MASK =
    '<svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="6.2" ' +
    'fill="none" stroke="currentColor" stroke-width="1.4"/><path ' +
    'd="M4.5 11.5 11 5M6.5 12.8 12.8 6.5" fill="none" stroke="currentColor" ' +
    'stroke-width="1.2"/></svg>';
  var ICON_LAYER =
    '<svg viewBox="0 0 16 16" aria-hidden="true"><rect x="3.5" y="3.5" width="9" ' +
    'height="9" rx="1.5" fill="none" stroke="currentColor" stroke-width="1.4"/></svg>';

  var root = null, btnMask = null, btnLayer = null;
  var subscribedStore = null, unsubscribe = null;

  function manager() {
    var b = window.__devbimCanvasBridge;
    if (!b) return null;
    try {
      var m = b.getManager();
      return m && m.stateApi && m.stateApi.store ? m : null;
    } catch (e) {
      return null;
    }
  }

  // Canvas-слайс обёрнут в redux-undo: актуальное состояние в .present.
  function canvasState(store) {
    var c = store.getState().canvas;
    return c && c.present ? c.present : c;
  }

  function render() {
    if (root) return;
    var st = document.createElement("style");
    st.textContent = STYLE;
    document.head.appendChild(st);
    root = document.createElement("div");
    root.id = ID;
    btnMask = document.createElement("button");
    btnMask.type = "button";
    btnMask.title = "Рисовать маской для правки (полосатая кисть)";
    btnMask.innerHTML = ICON_MASK + "<span>Маска</span>";
    btnMask.onclick = function () { activate("inpaint_mask"); };
    btnLayer = document.createElement("button");
    btnLayer.type = "button";
    btnLayer.title = "Рисовать цветом по картинке";
    btnLayer.innerHTML = ICON_LAYER + "<span>Слой</span>";
    btnLayer.onclick = function () { activate("raster_layer"); };
    root.appendChild(btnMask);
    root.appendChild(btnLayer);
    document.body.appendChild(root);
  }

  function activate(type) {
    var m = manager();
    if (!m) return;
    var store = m.stateApi.store;
    var cs = canvasState(store);
    var list = type === "inpaint_mask" ? cs.inpaintMasks.entities : cs.rasterLayers.entities;
    if (list.length > 0) {
      var last = list[list.length - 1];
      store.dispatch({
        type: "canvas/entitySelected",
        payload: { entityIdentifier: { id: last.id, type: type } }
      });
    } else if (type === "inpaint_mask") {
      m.stateApi.addInpaintMask({ isSelected: true });
    } else {
      m.stateApi.addRasterLayer({ isSelected: true });
    }
    sync();
  }

  function sync() {
    var m = manager();
    var tab = window.__devbimGetTab ? window.__devbimGetTab() : null;
    if (!m || tab !== "canvas") {
      if (root) root.style.display = "none";
      return;
    }
    if (!root) return;
    var sel = canvasState(m.stateApi.store).selectedEntityIdentifier;
    var t = sel && sel.type;
    btnMask.classList.toggle("active", t === "inpaint_mask");
    btnLayer.classList.toggle("active", t === "raster_layer");
    root.style.display = "flex";
  }

  function ensureSubscribed(m) {
    var store = m.stateApi.store;
    if (subscribedStore === store) return;
    if (unsubscribe) { try { unsubscribe(); } catch (e) {} }
    subscribedStore = store;
    unsubscribe = store.subscribe(sync);
  }

  function tick() {
    var m = manager();
    if (!m) {
      if (root) root.style.display = "none";
      return;
    }
    render();
    ensureSubscribed(m);
    sync();
  }

  function start() { setInterval(tick, TICK_MS); tick(); }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
})();
