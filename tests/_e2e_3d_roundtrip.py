# -*- coding: utf-8 -*-
"""E2E полный круг 3D Design: ВХОД-картинка -> генерация IFC -> рендер модели
во 3D-вьювере (Playwright) -> СРАВНЕНИЕ входа и выхода (судья-VLM + пиксели).

A/B-харнесс (п.60 з.7): серия прогонов одной конфигурации -> медианы.

Запуск (сервер поднят, ключ ImageRouter в .env):
    venv\\Scripts\\python.exe tests\\_e2e_3d_roundtrip.py
        (по умолчанию: 1 прогон, scenario=facade, DEFAULT_IMG)
    venv\\Scripts\\python.exe tests\\_e2e_3d_roundtrip.py \\
        --runs 3 --label baseline --scenario plan \\
        --image data\\probe\\gt_plan_synthetic.png \\
        --save data\\probe\\_ab_baseline_plan.json
    venv\\Scripts\\python.exe tests\\_e2e_3d_roundtrip.py --ifc 3D_facade_xxx.ifc
        (--ifc: не генерировать заново, а открыть готовую модель — без траты
         на анализ; скриншот и судья-VLM всё равно живые; 1 прогон)

Артефакты: data/ifc/_roundtrip_view.png (рендер вьювера последнего прогона),
файл --save (runs + summary). Уроки HANDOFF: пиксельным проверкам верить
БОЛЬШЕ, чем VLM-анализу скриншотов (п.38) — судья-VLM тут только Semant-оценка,
гейт — пиксельный.
"""
import base64
import io
import json
import re
import sys
import time
from pathlib import Path

import numpy as np
import requests
from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from invokeai.app.api.routers import threed as R, threed_scenarios  # venv-копии
from invokeai.app.api.routers.imagerouter import CHAT_COMPLETIONS_URL, _load_key

BASE = "http://127.0.0.1:9090"
DEFAULT_IMG = ROOT / "data" / "probe" / "vlm_test_house.png"

# пороги: рендер не пустой (модель видна на любом фоне) и судья видит хотя бы
# грубое совпадение massing. Пол 25, а не 60: у тестового дома есть фичи вне
# схемы фасада (вальмовая крыша, башенка, dormer-окна) — судья честно режет
# за них баллы; ниже 25 = совсем не то здание (ошибка конвейера).
MIN_CONTENT_FRACTION = 0.05
MIN_VLM_SCORE = 25

SYSTEM_JUDGE = """You are a 3D reconstruction QA judge. You get TWO images in order:
(1) the SOURCE photo the user submitted, (2) a RENDER of the 3D massing model
built from it (parametric IFC in a web viewer; simplified massing BY DESIGN:
no photorealism, flat colors, simplified surroundings). Judge how well the 3D
model reproduces the source building's key geometry: storey count and
proportions, window grid (rows x columns), roof type, balconies, overall
shape and orientation. Reply with STRICT JSON ONLY - no fences, no extra keys:
{"score": <int 0-100 overall geometric match>, "match": true|false,
 "issues": [<short concrete mismatches in English>]}

Rules:
- match=true when score >= 60 AND no critical mismatch (wrong storey count,
  wrong roof type, missing window row, building missing entirely).
- Tolerate (NOT issues): missing photorealism, texture/color shift, building
  depth guess, simplified context (trees/cars), camera angle difference.
"""


def _median(vals):
    """Медиана списка чисел; None для пустого (A/B-сводки, спека з.7)."""
    v = sorted(x for x in vals if x is not None)
    n = len(v)
    if not n:
        return None
    return v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2


def _summarize(runs):
    """N прогонов одной конфигурации -> медианы/доли для таблицы приёмки
    (спека, раздел 11). Прогон = dict из main()-цикла."""
    scores = [r.get("score") for r in runs]
    costs = [r.get("cost_usd") for r in runs]
    agrees = [r.get("agree_rate") for r in runs if r.get("agree_rate") is not None]
    ci = [r.get("contract_issues") for r in runs]
    st = [bool(r.get("structural_ok")) for r in runs]
    return {"n": len(runs),
            "median_score": _median(scores),
            "median_cost_usd": _median(costs),
            "structural_clean_rate": (round(sum(st) / len(st), 3)
                                      if st else None),
            "median_contract_issues": _median(ci),
            "agree_rate": (round(sum(agrees) / len(agrees), 3)
                           if agrees else None)}


def _site_password() -> str:
    m = re.search(r"^SITE_PASSWORD=(.+)$",
                  (ROOT / ".env").read_text(encoding="utf-8"), re.M)
    return (m.group(1) if m else "").strip().strip('"')


def _login_session() -> requests.Session:
    s = requests.Session()
    r = s.post(f"{BASE}/auth/login", data={"password": _site_password()},
               allow_redirects=False, timeout=15)
    assert r.status_code in (302, 303), f"login {r.status_code}"
    return s


def _generate(scenario: str, prompt: str, img_path: Path) -> dict:
    """Живая генерация POST /api/v1/threed/generate (2 VLM-вызова: анализ +
    верификация п.44). Роутер — фоновая задача: ответ {jobId}, результат
    ждём поллингом GET /jobs/{id} (result = прежний синхронный JSON:
    name/camHint/verify/usage/structural)."""
    dataurl = "data:image/png;base64," + base64.b64encode(img_path.read_bytes()).decode("ascii")
    cookies = {"devbim_auth": _login_session().cookies.get("devbim_auth")}
    t0 = time.time()
    r = requests.post(f"{BASE}/api/v1/threed/generate",
                      cookies=cookies,
                      json={"scenario": scenario, "prompt": prompt, "image": dataurl},
                      timeout=60)
    assert r.status_code == 200, f"generate {r.status_code}: {r.text[:300]}"
    job = r.json()["jobId"]
    while time.time() - t0 < 1800:  # очередь Semaphore(1) + минуты конвейера
        r = requests.get(f"{BASE}/api/v1/threed/jobs/{job}",
                         cookies=cookies, timeout=30)
        if r.status_code != 200:  # гейт/авторизация посреди серии — сразу
            raise RuntimeError(
                f"jobs GET {job} -> HTTP {r.status_code}: {r.text[:200]}")
        j = r.json()
        if j["status"] == "done":
            res = j["result"]
            break
        if j["status"] == "error":
            raise AssertionError(f"job error: {j.get('error')}")
        time.sleep(3)
    else:
        raise AssertionError("job не завершился за 30 минут")
    print(f"generate: {res['name']} за {time.time() - t0:.0f} s, "
          f"warnings={len(res.get('warnings') or [])}")
    v = (res.get("verify") or {}).get("verdict") or {}
    print(f"verify(п.44): ok={v.get('ok')} issues={v.get('issues') or v.get('error')}")
    return res


def _viewer_render(ifc_name: str, cam_hint: dict | None) -> Image.Image:
    """Вьювер грузит модель по lastModel (+camHint для scene) -> capture()."""
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            str(ROOT / "tests" / "_pw_e2e"), channel="chrome", headless=True,
            viewport={"width": 1280, "height": 860})
        try:
            ctx.add_cookies([{"name": "devbim_auth",
                              "value": _login_session().cookies.get("devbim_auth"),
                              "url": BASE}])
            page = ctx.new_page()
            page.goto(f"{BASE}/ifcviewer.html", wait_until="domcontentloaded")
            page.evaluate(
                f"localStorage.setItem('devbim:ifc:lastModel','{ifc_name}')" +
                (f";localStorage.setItem('devbim:ifc:camHint','{json.dumps(cam_hint)}')"
                 if cam_hint else ""))
            page.reload(wait_until="domcontentloaded")
            for _ in range(60):
                if page.evaluate("() => !!(window.__ifc && __ifc.model)"):
                    break
                time.sleep(1)
            else:
                raise SystemExit("модель не загрузилась во вьювере")
            page.wait_for_timeout(1500)
            data = page.evaluate("() => __ifc.capture()")
        finally:
            ctx.close()
    return Image.open(io.BytesIO(base64.b64decode(data.split(",", 1)[1]))).convert("RGBA")


def _content_fraction(im: Image.Image) -> float:
    """Доля содержательных пикселей: отклонение от ДОМИНАНТНОГО цвета фона
    (фон вьювера тёмный — проверка «не белый» из п.38 тут не работает)."""
    a = np.array(im)
    vis = a[..., 3] > 30
    px = a[vis][:, :3].astype(int)
    if not len(px):
        return 0.0
    q = (px // 16)  # квантование 16 -> доминанта фона
    keys, counts = np.unique(q, axis=0, return_counts=True)
    bg = keys[counts.argmax()] * 16 + 8
    return float((np.abs(px - bg).max(axis=1) > 25).mean())


def _judge(src_path: Path, render_path: Path) -> dict:
    """Судья-VLM: исходник + рендер -> {score, match, issues}. Строгий JSON."""
    def url(path: Path) -> str:
        return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode("ascii")
    key = _load_key()
    assert key, "нет IMAGEROUTER_API_KEY"
    model, _ = R._load_model_choice()
    content = [
        {"type": "text", "text": "Image 1 = SOURCE photo, image 2 = 3D viewer "
                                 "render of the model built from it. Score the "
                                 "geometric match. STRICT JSON only."},
        {"type": "image_url", "image_url": {"url": url(src_path)}},
        {"type": "image_url", "image_url": {"url": url(render_path)}},
    ]
    resp = requests.post(
        CHAT_COMPLETIONS_URL, headers={"Authorization": f"Bearer {key}"},
        json={"model": model,
              "messages": [{"role": "system", "content": SYSTEM_JUDGE},
                           {"role": "user", "content": content}],
              "max_tokens": 8000, "temperature": 0.2}, timeout=180)
    data = resp.json()
    text = ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    assert text.strip(), f"судья пуст: HTTP {resp.status_code} {str(data)[:200]}"
    verdict = threed_scenarios.extract_json(text)
    assert isinstance(verdict, dict) and "score" in verdict, f"не JSON: {text[:200]}"
    verdict.setdefault("match", verdict["score"] >= 60)
    verdict.setdefault("issues", [])
    verdict["model"] = model
    return verdict


def main() -> None:
    args = sys.argv[1:]
    ifc_arg = args[args.index("--ifc") + 1] if "--ifc" in args else None
    runs_n = int(args[args.index("--runs") + 1]) if "--runs" in args else 1
    label = args[args.index("--label") + 1] if "--label" in args else "adhoc"
    save = Path(args[args.index("--save") + 1]) if "--save" in args else None
    scenario = args[args.index("--scenario") + 1] if "--scenario" in args else "facade"
    img_arg = args[args.index("--image") + 1] if "--image" in args else None
    src_img = Path(img_arg) if img_arg else DEFAULT_IMG
    src = ROOT / "data" / "ifc" / "_roundtrip_src.png"
    Image.open(src_img).convert("RGB").save(src)

    runs = []

    def _flush() -> None:
        """Пишем файл --save после КАЖДОГО прогона: живой сбой в середине
        серии (сеть/модель) не теряет уже оплаченные прогоны. incomplete —
        маркер неполноты для шага merge (финальный флэш даёт False)."""
        save.parent.mkdir(parents=True, exist_ok=True)
        save.write_text(json.dumps(
            {"label": label, "scenario": scenario, "image": str(src_img),
             "incomplete": len(runs) < runs_n,
             "runs": runs, "summary": _summarize(runs)},
            ensure_ascii=False, indent=1), encoding="utf-8")

    for i in range(runs_n if not ifc_arg else 1):
        if ifc_arg:
            res = {"name": ifc_arg, "camHint": None, "verify": None}
        else:
            res = _generate(scenario, "ab harness run", src_img)
        # contract_issues/agree_rate живут в дампе сервера (history только
        # там; Semaphore(1) = дамп соответствует этому прогону)
        dump = {}
        try:
            dump = json.loads(
                (ROOT / "data" / "ifc" / "_threed_last.json")
                .read_text(encoding="utf-8"))
        except Exception:
            pass
        hist = (dump.get("verify") or {}).get("history") or []
        render = _viewer_render(res["name"], res.get("camHint"))
        view_path = ROOT / "data" / "ifc" / "_roundtrip_view.png"
        render.convert("RGB").save(view_path)
        frac = _content_fraction(render)
        assert frac > MIN_CONTENT_FRACTION, "рендер вьювера пуст"
        verdict = _judge(src, view_path)
        ens = res.get("ensemble") or dump.get("ensemble") or {}
        usage = res.get("usage") or {}
        runs.append({"name": res["name"], "score": int(verdict["score"]),
                     "match": bool(verdict["match"]),
                     "content_fraction": round(frac, 4),
                     "cost_usd": usage.get("cost_usd"),
                     "structural_ok": ((res.get("structural") or {})
                                       .get("ok")),
                     "contract_issues": (len(hist[-1].get("contract_issues")
                                             or []) if hist else 0),
                     "agree_rate": ens.get("agree_rate")})
        print(f"run {i + 1}/{runs_n}: score={verdict['score']} "
              f"cost={usage.get('cost_usd')}")
        if save:
            _flush()

    summary = _summarize(runs)
    print(f"[{label}] {scenario} {src_img.name}: median score "
          f"{summary['median_score']}, cost {summary['median_cost_usd']}")
    if save:
        _flush()
        print("сохранено:", save)


if __name__ == "__main__":
    main()
