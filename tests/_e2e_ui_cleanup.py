# -*- coding: utf-8 -*-
"""E2E уборки локальных элементов UI (21.09, п.50): в поле промта нет
оверлей-группы иконок (триггер {x} / SDXL-concat / динамические промты /
отрицательный промт), в панели слоёв холста нет строки Denoising Strength.
Запуск: venv\\Scripts\\python.exe tests\\_e2e_ui_cleanup.py (сервер на 9090).
"""
import re
import time
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs"

pw = (re.search(r"^SITE_PASSWORD=(.+)$", (ROOT / ".env").read_text(encoding="utf-8"),
                re.M) or [None, ""])[1].strip().strip('"')
s = requests.Session()
r = s.post("http://127.0.0.1:9090/auth/login", data={"password": pw},
           allow_redirects=False, timeout=15)
assert r.status_code in (302, 303), r.status_code

# aria-метки удалённых кнопок (EN-локаль; проверяем по всему приложению —
# региональные промпты скрыты вместе с контроль-слоями с 19.08)
GONE_LABELS = ("prompt trigger", "dynamic prompts", "negative prompt",
               "prompt and style", "trigger")

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(
        str(ROOT / "tests" / "_pw_e2e"), channel="chrome", headless=True,
        viewport={"width": 1600, "height": 900})
    ctx.add_cookies([{"name": "devbim_auth", "value": s.cookies.get("devbim_auth"),
                      "url": "http://127.0.0.1:9090"}])
    page = ctx.new_page()
    errors = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.goto("http://127.0.0.1:9090/", wait_until="domcontentloaded")
    page.wait_for_selector(".positive-prompt-textarea", timeout=60000)
    time.sleep(2)

    def count_gone_buttons() -> int:
        labels = page.eval_on_selector_all(
            "button[aria-label]", "els => els.map(e => e.getAttribute('aria-label'))")
        return sum(1 for x in labels if any(g in x.lower() for g in GONE_LABELS))

    def prompt_buttons() -> int:
        # кнопки внутри позиционированного контейнера поля промта — там жил
        # оверлей с иконками; соседние секции (Reference Image) снаружи
        return page.evaluate(
            """() => { const ta = document.querySelector('.positive-prompt-textarea');
                 if (!ta) return -1;
                 let box = ta.parentElement;
                 while (box && getComputedStyle(box).position !== 'relative')
                   box = box.parentElement;
                 return box ? box.querySelectorAll('button').length : -1; }""")

    n_gen = count_gone_buttons()
    pb_gen = prompt_buttons()
    print(f"Generate: кнопок-оверлеев промта по aria = {n_gen}, в контейнере промта = {pb_gen}")
    assert n_gen == 0, "остались кнопки триггеров/динамических промтов"
    assert pb_gen == 0, "в поле промта остались кнопки"
    page.screenshot(path=str(OUT / "ui-cleanup-generate.png"))

    # --- Canvas: правая панель без Denoising Strength, Opacity на месте ---
    # (в свежем профиле центр канваса не монтируется — п.43 грабля 1; панель
    # слоёв справа рендерится независимо, ждём её по строке Opacity)
    page.evaluate("window.__devbimSwitchTab && __devbimSwitchTab('canvas')")
    page.wait_for_function(
        "() => document.body.innerText.includes('Opacity')", timeout=30000)
    time.sleep(1)
    body = page.inner_text("body")
    assert "Denoising Strength" not in body, "строка Denoising Strength всё ещё в панели"
    assert "Opacity" in body, "строка Opacity пропала (должна остаться)"
    n_canvas = count_gone_buttons()
    pb_canvas = prompt_buttons()
    print(f"Canvas: кнопок-оверлеев промта по aria = {n_canvas}, в контейнере промта = {pb_canvas}")
    assert n_canvas == 0 and pb_canvas == 0, "на канвасе остались кнопки в поле промта"
    page.screenshot(path=str(OUT / "ui-cleanup-canvas.png"))

    known = ("rehydrat", "persist", "Non-Error promise rejection")
    unexpected = [e for e in errors if not any(k in e for k in known)]
    print("console errors:", len(errors), "неожидаемых:", len(unexpected))
    for e in unexpected[:5]:
        print("  !", e[:160])
    ctx.close()

print("OK: E2E уборка UI (иконки промта и Denoising Strength удалены)")
