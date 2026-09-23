/*
 * DevBIM — стилизация полоски вкладок dockview-холста:
 *  - вкладка «Launchpad» скрыта (панель остаётся в layout, кнопка не нужна);
 *  - вкладка «Canvas» — градиентная кнопка в цветах бренда;
 *  - вьюверы (Image Viewer / IFC Viewer / PDF Viewer) прижаты к правому краю
 *    полоски: Canvas — в левом углу центрального окна.
 * Деплой: rebrand_devbim.py -> dist/devbim-canvas-tabs.js + <script> в index.html.
 * Вкладки различаются по тексту заголовка (dockview не даёт им классов),
 * классы навешивает MutationObserver — DOM вкладок dockview пересоздаётся.
 */
(function () {
  'use strict';
  if (window.__devbimCanvasTabs) return;
  window.__devbimCanvasTabs = true;

  var TAGS = {
    'Launchpad': 'devbim-tab-launchpad',
    'Canvas': 'devbim-tab-canvas',
    'Image Viewer': 'devbim-tab-imageviewer',
    'IFC Viewer': 'devbim-tab-ifcviewer',
    'PDF Viewer': 'devbim-tab-pdfviewer'
  };

  var CSS = [
    /* Launchpad: скрыть кнопку */
    '.dv-tabs-container .dv-tab.devbim-tab-launchpad{display:none!important}',

    /* Растянуть полоску на всю ширину заголовка группы (только у холста) */
    '.dv-tabs-and-actions-container:has(.dv-tab.devbim-tab-canvas)>.dv-scrollable{flex:1 1 auto;min-width:0}',
    '.dv-tabs-and-actions-container:has(.dv-tab.devbim-tab-canvas)>.dv-void-container{flex:0 0 0px}',
    '.dv-tabs-and-actions-container:has(.dv-tab.devbim-tab-canvas) .dv-tabs-container{width:100%}',

    /* Первый из вьюверов отжимает всю группу вправо */
    '.dv-tabs-container .dv-tab.devbim-tab-imageviewer{margin-inline-start:auto}',

    /* Canvas — градиентная кнопка DevBIM */
    '.dv-tabs-container .dv-tab.devbim-tab-canvas{',
    '  margin:2px 6px 2px 8px!important;padding:0 14px!important;',
    '  border-radius:8px!important;border-top:2px solid transparent!important;',
    '  background:linear-gradient(135deg,#38BDF8 0%,#0EA5E9 45%,#6366F1 100%)!important;',
    '  box-shadow:0 2px 10px rgba(56,189,248,.35),inset 0 1px 0 rgba(255,255,255,.28);',
    '}',
    '.dv-tabs-container .dv-tab.devbim-tab-canvas p{color:#fff!important;font-weight:600!important}',
    '.dv-tabs-container .dv-tab.devbim-tab-canvas.dv-inactive-tab{filter:saturate(.7) brightness(.72)}',
    '.dv-tabs-container .dv-tab.devbim-tab-canvas:hover{filter:brightness(1.12)}',
    '.dv-tabs-container .dv-tab.devbim-tab-canvas.dv-active-tab{box-shadow:0 3px 14px rgba(56,189,248,.5),inset 0 1px 0 rgba(255,255,255,.28)}'
  ].join('\n');

  function tag() {
    var tabs = document.querySelectorAll('.dv-tabs-container .dv-tab:not([data-devbim-tag])');
    for (var i = 0; i < tabs.length; i++) {
      var t = tabs[i];
      var cls = TAGS[t.textContent.replace(/\s+/g, ' ').trim()];
      /* подпись рендерится React-ом позже самой вкладки: помечаем только
         когда класс найден, иначе следующий проход мутации вернётся к ней */
      if (cls) {
        t.classList.add(cls);
        t.setAttribute('data-devbim-tag', '1');
      }
    }
  }

  var style = document.createElement('style');
  style.id = 'devbim-canvas-tabs';
  style.textContent = CSS;
  (document.head || document.documentElement).appendChild(style);

  tag();
  new MutationObserver(tag).observe(document.body || document.documentElement, {
    childList: true,
    subtree: true
  });
})();
