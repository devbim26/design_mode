# План: PDF-вьювер (вкладка «PDF»)

Спека: `docs/superpowers/specs/2026-09-05-pdf-viewer-design.md`.
Ветка `feature/pdf-viewer` от `feature/ifc-viewer`. Всё в стиле
`ifc/` + `setup_ifcviewer.py` (идемпотентно, бэкапы `*.pdfviewer-bak`).

## Шаги

1. Ассеты: `pdf/assets/pdf.min.mjs` + `pdf.worker.min.mjs` (PDF.js 5.4.149,
   cdnjs) — ✅ скачаны.
2. `pdf/pdf_router.py` — копия паттерна `ifc_router.py`
   (`/v1/pdf/list|upload|file/{name}` DELETE, `.pdf` только, 500 МБ,
   хранилище `root_path/pdf`).
3. `pdf/pdfviewer.html` — страница вьювера (header, сайдбар «Страницы/
   Оглавление», вьюпорт с зумом/поворотом/навигацией, рамка, action bar
   «На холст»/«В ассеты», footer; localStorage-автовосстановление).
4. `setup_pdfviewer.py` — деплой (роутер + страница + ассеты → `dist/pdf/`),
   патч `api_app.py`, патчи App-бандла (кнопка `vx`-иконка, TabContent,
   компонент `PDFE`), патч index-бандла (enum + "pdf"); гейт на
   `__devbimIfc`.
5. `tests/test_pdf_router.py` — plain asserts по `_safe_path`/расширениям.
6. Применить и проверить: setup ×2 → node-import обоих бандлов →
   `_restart_server.ps1` → curl list/upload/file/DELETE →
   сгенерировать тестовый PDF (PIL, многостраничный) → GUI-проверка
   Playwright-ом (обе кнопки) → скриншоты.
7. Документация: README (раздел «PDF-вьювер»), HANDOFF (п. 16), AGENTS.md
   (порядок скриптов). Коммит.

## Откат

Восстановить `*.pdfviewer-bak`, удалить `routers/pdf.py`, `dist/pdfviewer.html`,
`dist/pdf/`.
