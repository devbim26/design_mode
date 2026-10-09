# -*- coding: utf-8 -*-
"""
make_style_previews.py — маленькие превью (256 px) для style-пресетов.

Для каждого пресета из setup_style_presets.PRESETS подставляет демо-сюжет
вместо {prompt} и генерирует картинку через ImageRouter (ключ берётся из
.env, как у посредника). Результат — PNG 256 px в style_preset_images/
(имя файла = имя пресета). Устанавливаются в venv скриптом
setup_style_presets.py: для default-пресетов InvokeAI ищет превью по ИМЕНИ
в .../style_preset_images/default_style_preset_images/.

Модели: только бесплатные text-to-image, у каждой лимит 3 запроса/сутки,
поэтому сюжеты заранее распределены по пулу (не больше 3 на модель);
при отказе (429/5xx) скрипт переключается на следующую модель, в конце —
платный fallback Tongyi-MAI/Z-Image-Turbo (~0.0016 кредитов/картинка).

Запуск:  venv\\Scripts\\python.exe make_style_previews.py [--only-missing]
"""
from __future__ import annotations

import base64
import io
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import setup_style_presets as sp  # noqa: E402  (PRESETS — источник пресетов)

OUT_DIR = ROOT / "style_preset_images"
API = "https://api.imagerouter.io/v1/openai/images/generations"
SIZE = "512x512"          # «маленькие»: модели с size=custom принимают свободно
THUMB = 256               # размер превью (как make_thumbnail у InvokeAI)

# Пул: (модель, максимум запросов за прогон). Первая — платная
# Tongyi-MAI/Z-Image-Turbo: быстрая (3-4 с), дёшево (~0.0016 кредита),
# стабильная фотореалистичная архиз-картинка. У :free-моделей лимит
# 3 запроса/сутки и он, по опыту, исчерпывается мгновенно — только fallback.
MODEL_POOL = [
    ("Tongyi-MAI/Z-Image-Turbo", 99),
    ("qwen/qwen-image:free", 3),
    ("black-forest-labs/FLUX-1-schnell:free", 3),
    ("HiDream-ai/HiDream-I1-Fast:free", 3),
    ("stabilityai/sdxl-turbo:free", 3),
]

# Какая модель какой пресет рисует по умолчанию (индекс в MODEL_POOL)
ASSIGN = {
    "Facades — Neutral Daylight": 0,
    "Facades — Golden Hour": 0,
    "Facades — Blue Hour (Evening)": 0,
    "Facades — Frontal (Album Sheet)": 0,
    "Interiors — Daylight": 0,
    "Interiors — Evening Light": 0,
    "Interiors — Public Space": 0,
    "Master Plan — Aerial (Top-Down)": 0,
    "Master Plan — Bird's Eye (45°)": 0,
    "Master Plan — Orthographic (Album Sheet)": 0,
    "Facades — Re-render from 3D View": 0,
    "Interiors — Re-render from 3D View": 0,
}

# Демо-сюжеты: короткий типовой объект вместо {prompt}
DEMO_SUBJECTS = {
    "Facades — Neutral Daylight":
        "modern 9-storey residential building, red clinker brick facade "
        "with glass balconies",
    "Facades — Golden Hour":
        "contemporary mid-rise apartment building with a glass curtain "
        "wall and a natural stone base",
    "Facades — Blue Hour (Evening)":
        "modern residential complex entrance tower with warm lit windows",
    "Facades — Frontal (Album Sheet)":
        "modern 5-storey residential building, beige architectural "
        "concrete panels and large windows",
    "Interiors — Daylight":
        "scandinavian living room with oak flooring, a light grey sofa "
        "and large windows",
    "Interiors — Evening Light":
        "modern bedroom with warm pendant lamps and soft evening light",
    "Interiors — Public Space":
        "hotel lobby with a wooden reception desk and a lounge zone",
    "Master Plan — Aerial (Top-Down)":
        "residential quarter with inner courtyards, parking lots and "
        "playgrounds",
    "Master Plan — Bird's Eye (45°)":
        "modern residential neighborhood with a school building and a park",
    "Master Plan — Orthographic (Album Sheet)":
        "site plan of a residential complex with courtyards, driveways "
        "and parking",
    # ре-рендер по 3D-ракурсу: превью — обычный архиз-кадр демо-объекта
    # (темплейт ссылается на приложенные картинки, которых в txt2img нет)
    "Facades — Re-render from 3D View":
        "modern 6-storey residential building, dark brick and light metal "
        "panels, street with trees and pedestrians",
    "Interiors — Re-render from 3D View":
        "modern open-plan living room with kitchen island, warm wood and "
        "beige tones",
}


def _api_key() -> str:
    for line in (ROOT / ".env").read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if line.startswith("IMAGEROUTER_API_KEY="):
            return line.partition("=")[2].strip().strip('"').strip("'")
    raise SystemExit("IMAGEROUTER_API_KEY не найден в .env")


def generate(model: str, prompt: str, key: str) -> Image.Image:
    body = json.dumps({"model": model, "prompt": prompt, "size": SIZE}).encode()
    req = urllib.request.Request(
        API, data=body, method="POST",
        headers={"Authorization": "Bearer " + key,
                 "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=180) as r:
        data = json.load(r)["data"][0]
    if data.get("b64_json"):
        raw = base64.b64decode(data["b64_json"])
    else:
        with urllib.request.urlopen(data["url"], timeout=60) as r:
            raw = r.read()
    return Image.open(io.BytesIO(raw)).convert("RGB")


def save_thumb(img: Image.Image, preset_name: str) -> Path:
    img.thumbnail((THUMB, THUMB))  # как InvokeAI make_thumbnail: min-сторона
    out = OUT_DIR / (preset_name + ".png")
    img.save(out, format="PNG")
    return out


def main() -> None:
    only_missing = "--only-missing" in sys.argv
    OUT_DIR.mkdir(exist_ok=True)
    key = _api_key()
    left = {m: cap for m, cap in MODEL_POOL}
    ok, failed = 0, []

    for preset in sp.PRESETS:
        name = preset["name"]
        out = OUT_DIR / (name + ".png")
        if only_missing and out.is_file():
            print(f"пропуск (есть): {name}")
            continue
        prompt = preset["preset_data"]["positive_prompt"].replace(
            "{prompt}", DEMO_SUBJECTS[name])
        # порядок кандидатов: назначенная модель, потом остальные (free -> paid)
        order = list(range(len(MODEL_POOL)))
        order.remove(ASSIGN[name])
        order.insert(0, ASSIGN[name])
        done = False
        for idx in order:
            model = MODEL_POOL[idx][0]
            if left.get(model, 0) <= 0:
                continue
            t0 = time.time()
            try:
                img = generate(model, prompt, key)
            except urllib.error.HTTPError as e:
                print(f"  [{model}] HTTP {e.code}: {e.reason[:80]} — следующая модель")
                left[model] = 0  # лимит/отказ — больше не пробуем эту
                continue
            except Exception as e:  # noqa: BLE001
                print(f"  [{model}] {type(e).__name__}: {e} — следующая модель")
                continue
            left[model] -= 1
            path = save_thumb(img, name)
            ok += 1
            done = True
            print(f"ok [{model}] {name} -> {path.name} "
                  f"({time.time() - t0:.0f} с)")
            break
        if not done:
            failed.append(name)
            print(f"FAIL: {name}")

    print(f"\nготово: {ok}, неудач: {len(failed)}")
    if failed:
        print("не сгенерированы:", "; ".join(failed))
        raise SystemExit(1)
    print("Установка в venv: venv\\Scripts\\python.exe setup_style_presets.py")


if __name__ == "__main__":
    main()
