# -*- coding: utf-8 -*-
"""E2E облачных нод Workflows (22.09): регистрация нод в openapi, allowlist
меню Add Node, открытие шаблона Facade Variants, ЖИВАЯ генерация через
реальную очередь (~$0.01), регрессия перехвата канваса (репост последнего
дампа графа) и чистота консоли.
Запуск (сервер на 9090, после setup + рестарта):
  PYTHONUTF8=1 venv/Scripts/python.exe tests/_e2e_cloud_nodes.py

Отступления от брифа (UI-зонд, селекторы/поллинг подогнаны под реальность):
1. edges: [] вместо edges: {} — в 6.2.0 Graph.edges имеет тип list[Edge]
   (services/shared/graph.py:346), пустой dict даёт 422.
2. Поллинг очереди — точечный GET /api/v1/queue/default/i/{item_id} по
   item_ids из ответа enqueue (вместо /list?limit=1): /list курсорный и
   сортирован priority DESC, item_id ASC — items[0] это САМЫЙ СТАРЫЙ
   элемент, на очереди с историей это ложный «completed» без ожидания.
3. Галерея: фиксируем имя последней картинки ДО генерации и требуем
   новую после — привязка метаданных cloud-generate к этому запуску.
4. enqueue_batch в 6.2.0 отдаёт 200 (не 202; посредник тоже шлёт 200) —
   статуса недостаточно, чтобы отличить перехват от провала в локальную
   очередь, поэтому перехват подтверждаем СИГНАТУРОЙ посредника:
   item_ids из одних нулей (routers/imagerouter.py:1967 синтезирует
   [0]*len(saved); реальная очередь отдаёт возрастающие позитивные id).
5. Список картинок: ключ "items", не "images"; метаданные — отдельный
   эндпоинт GET /api/v1/images/i/{name}/metadata (у images_by_names
   метаданных нет).
6. Браузер: после вкладки Workflows нужен вход в редактор («Create a
   new Workflow») и центральная вкладка «Workflow Editor» — без неё
   канвас не смонтирован; Add Node — button[aria-label="Add Node"]
   (текстовой кнопки «Add Node» в 6.2.0 нет); библиотека — кнопка
   «Choose Workflow from Library», после выбора шаблона — диалог
   «Load workflow?» → кнопка Load, и ПОВТОРНЫЙ клик «Workflow Editor»
   (после загрузки шаблона центр сбрасывается на «Image Viewer»).
7. Меню Add Node ждём по [cmdk-root] (wait_for_selector), а не sleep:
   до клика элемента в DOM нет, после — контейнер меню с cmdk-item
   (подтверждено UI-зондом .superpowers/sdd/probe-addnode.py); allowlist
   и запрещённые ноды проверяем по тексту МЕНЮ ([cmdk-root]), а не body.
"""
import json
import re
import time
from pathlib import Path

import requests
from playwright.sync_api import TimeoutError as PwTimeoutError
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs"
BASE = "http://127.0.0.1:9090"

pw = (re.search(r"^SITE_PASSWORD=(.+)$", (ROOT / ".env").read_text(encoding="utf-8"),
                re.M) or [None, ""])[1].strip().strip('"')
s = requests.Session()
r = s.post(f"{BASE}/auth/login", data={"password": pw}, allow_redirects=False, timeout=15)
assert r.status_code in (302, 303), r.status_code
COOKIE = s.cookies.get("devbim_auth")
assert COOKIE

# --- 1. ноды зарегистрированы: openapi содержит devbim_* ---
oa = s.get(f"{BASE}/openapi.json", timeout=30).json()
schemas = oa.get("components", {}).get("schemas", {})
types = set()
for sch in schemas.values():
    t = (sch.get("properties") or {}).get("type", {})
    c = t.get("const") or (t.get("enum") or [None])[0]
    if c:
        types.add(c)
for t in ("devbim_generate", "devbim_edit", "devbim_vlm", "devbim_upscale"):
    assert t in types, f"нет ноды {t} в openapi — сервер перезапущен без деплоя?"
print("OK: openapi содержит devbim_*")

# --- 2. регрессия инъекции моделей (перехват не сломан allowlist-патчем) ---
models = s.get(f"{BASE}/api/v2/models/", timeout=60).json()
keys = {m.get("key") for m in models.get("models", [])}
assert any(str(k).startswith("imagerouter/") for k in keys), "инъекция моделей исчезла"
print("OK: /api/v2/models содержит imagerouter-модели (регрессия инъекции)")

# --- 3. ЖИВАЯ генерация облачной нодой через РЕАЛЬНУЮ очередь (~$0.01) ---
def newest_image_name() -> str:
    # 6.2.0: список картинок отдаёт {"items": [...]} (не "images")
    lst = s.get(f"{BASE}/api/v1/images/?offset=0&limit=1&order=desc", timeout=15).json()
    return (lst.get("items") or [{}])[0].get("image_name") or ""


before = newest_image_name()
gen_graph = {
    "batch": {
        "origin": "workflows",
        "destination": "workflows",
        "runs": 1,
        "graph": {
            "id": "e2e-cloud-gen",
            "nodes": {
                "gen": {
                    "id": "gen",
                    "type": "devbim_generate",
                    "prompt": "small test house, simple sketch, white background",
                }
            },
            "edges": [],
        },
    },
    "prepend": False,
}
r = s.post(f"{BASE}/api/v1/queue/default/enqueue_batch", json=gen_graph, timeout=30)
assert r.status_code in (200, 202), (r.status_code, r.text[:300])  # 6.2.0 отдаёт 200
item_ids = r.json().get("item_ids") or []
assert item_ids, r.text[:300]
deadline = time.time() + 360
done = False
while time.time() < deadline:
    for iid in item_ids:
        item = s.get(f"{BASE}/api/v1/queue/default/i/{iid}", timeout=15).json()
        if item.get("status") in ("completed", "failed", "canceled"):
            assert item["status"] == "completed", f"очередь: {item['status']} {item.get('error')}"
            done = True
    if done:
        break
    time.sleep(3)
assert done, "генерация не завершилась за 6 минут"
name = newest_image_name()
assert name and name != before, "в галерее нет новой картинки"
meta = s.get(f"{BASE}/api/v1/images/i/{name}/metadata", timeout=15).json()  # metadata — отдельный эндпоинт
mode = (meta or {}).get("generation_mode")
assert mode == "cloud-generate", f"метаданные: {mode!r} (ожидалось cloud-generate)"
print("OK: живая генерация devbim_generate через реальную очередь, результат в галерее")

# --- 4. регрессия перехвата канваса: репост последнего дампа графа (~$0.01-0.07) ---
dump = ROOT / "data" / "_ir_last_graph.json"
if dump.exists():
    batch = json.loads(dump.read_text(encoding="utf-8"))
    if isinstance(batch, dict) and "batch" in batch:
        r = s.post(f"{BASE}/api/v1/queue/default/enqueue_batch", json=batch, timeout=300)
        assert r.status_code in (200, 202), (r.status_code, r.text[:300])  # посредник шлёт 200
        # Сигнатура перехвата: посредник синтезирует item_ids из нулей
        # (imagerouter.py:1967: [0] * len(saved)); реальная очередь отдаёт
        # возрастающие позитивные id. Одного статуса мало — оба пути 200.
        ir_ids = r.json().get("item_ids") or []
        assert ir_ids and all(i == 0 for i in ir_ids), \
            f"канвас-граф НЕ перехвачен (ушёл в локальную очередь): item_ids={ir_ids[:5]}"
        print("OK: канвас-граф принят перехватом (item_ids все 0 — сигнатура посредника)")
    else:
        print("SKIP: дампа-графа нет (структура)")
else:
    print("SKIP: data/_ir_last_graph.json отсутствует — регрессию снять вручную с холста")

# --- 5. браузер: allowlist в меню Add Node + шаблон Facade Variants ---
with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(
        str(ROOT / "tests" / "_pw_e2e_fresh"), channel="chrome", headless=True,
        viewport={"width": 1600, "height": 900})
    ctx.add_cookies([{"name": "devbim_auth", "value": COOKIE, "url": BASE}])
    page = ctx.new_page()
    errors = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.goto(BASE + "/", wait_until="domcontentloaded")
    page.wait_for_selector(".positive-prompt-textarea", timeout=60000)
    time.sleep(2)

    # вкладка Workflows (левая рейка, EN-локаль)
    wf = page.get_by_role("button", name=re.compile("workflows", re.I))
    if not wf.count():
        wf = page.get_by_text("Workflows", exact=False)
    wf.first.click(timeout=15000)
    time.sleep(3)
    page.screenshot(path=str(OUT / "workflows-cloud-tab.png"))

    # редактор: «Create a new Workflow» + центральная вкладка «Workflow Editor»
    # (без неё канвас react-flow не смонтирован и кнопки Add Node нет)
    page.get_by_role("button", name=re.compile("Create a new Workflow", re.I)).first.click(timeout=15000)
    time.sleep(2)
    page.get_by_text("Workflow Editor", exact=True).first.click(timeout=15000)
    time.sleep(2)

    # меню Add Node: только разрешённые ноды. Ждём само меню (контейнер
    # cmdk — до клика его в DOM нет, зонд probe-addnode.py), читаем текст
    # МЕНЮ, а не body — иначе чек проходит впустую по тексту страницы
    add = page.locator("button[aria-label='Add Node']")
    assert add.count(), "кнопка Add Node не найдена на холсте (см. workflows-cloud-tab.png)"
    add.first.click(timeout=15000)
    page.wait_for_selector("[cmdk-root]", timeout=15000)  # меню реально открыто
    menu_text = page.locator("[cmdk-root]").inner_text()
    assert "Generate Image" in menu_text or "Devbim" in menu_text or "devbim" in menu_text.lower(), \
        "меню Add Node не показывает облачные ноды (см. workflows-cloud-addnode.png)"
    for gone in ("Denoise Latents", "Compel Prompt", "Model Loader"):
        assert gone not in menu_text, f"запрещённая нода в меню: {gone}"
    page.screenshot(path=str(OUT / "workflows-cloud-addnode.png"))  # ДО Escape — как улика при фейле
    page.keyboard.press("Escape")
    print("OK: Add Node — облачные ноды есть, локальной диффузии нет")

    # библиотека: открыть шаблон Facade Variants
    page.get_by_role("button", name=re.compile("Choose Workflow from Library", re.I)).first.click(timeout=15000)
    time.sleep(2)
    lib = page.get_by_text("Facade Variants", exact=False)
    assert lib.count(), "шаблон Facade Variants не найден в библиотеке (см. скриншот вкладки)"
    lib.first.click(timeout=15000)
    # диалог «Load workflow? … unsaved changes» — подтверждаем (может
    # появляться с задержкой, ждём именно его, а не «sleep(1)»)
    try:
        page.wait_for_selector("text=Load workflow", timeout=10000)
        page.get_by_role("button", name="Load", exact=True).first.click(timeout=15000)
    except PwTimeoutError:
        pass  # диалог не появился — шаблон загрузился сразу
    time.sleep(2)
    # после загрузки шаблона центр переключается на «Image Viewer» —
    # возвращаем «Workflow Editor», иначе канвас не смонтирован
    page.get_by_text("Workflow Editor", exact=True).first.click(timeout=15000)
    page.wait_for_selector(".react-flow__node", timeout=30000)
    time.sleep(2)
    assert page.locator(".react-flow__node").count() >= 2, "узлы шаблона не отрисованы"
    page.screenshot(path=str(OUT / "workflows-cloud-template.png"))
    print("OK: шаблон Facade Variants открылся, узлы на холсте")

    # favicon-404 и redux-remember rehydration — предсуществующий шум
    # (грабли прошлых сессий); фейл только на НОВЫХ ошибках
    real_errors = [e for e in errors if "favicon" not in e.lower()
                   and "rehydrating state" not in e and "persisting state" not in e]
    assert not real_errors, f"ошибки консоли: {real_errors[:3]}"
    ctx.close()

print("E2E OK — все проверки пройдены")
