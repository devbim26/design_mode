# Диагностика 06.09 (грабля шлюза): multipart edits доставляет модели только
# ПЕРВОЕ изображение (референсы терялись), JSON-массив data-URL — все.
# Сценарий: маркированная база-канвас + 2 референса (кирпич + штукатурка).
# Запуск: venv\Scripts\python.exe tests\_diag_edits_refs_json.py (живой API, ~$0.07)
# Результат-эталон: docs/diag-edits-refs-json-0609.png (стены = материалы референсов)
import importlib.util
import io
import sys

sys.path.insert(0, "imagerouter")
spec = importlib.util.spec_from_file_location("irr", "imagerouter/imagerouter_router.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

import requests
from PIL import Image

DATA = "data/outputs/images"
MID = "google/nano-banana-2"
PROMPT = "сдеоай фотореалистично ..  точно повторяя геометрию... добавь на стены материалы из приложения"
NOTE = (
    "\n\nПервое изображение — исходник для редактирования (зона правки выделена "
    "пурпурной заливкой и рамкой, отметки убери из результата). Остальные "
    "изображения — референсы материалов: точно примени их текстуры и цвета."
)


def durl_png(img):
    buf = io.BytesIO(); img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def durl_jpg(img, max_side=1024, quality=85):
    im = img.convert("RGB")
    if max(im.size) > max_side:
        im.thumbnail((max_side, max_side))
    buf = io.BytesIO(); im.save(buf, format="JPEG", quality=quality)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


init_full = Image.open(f"{DATA}/5b3c7210-fb75-4d4b-9546-c8ff50dc5d84.png")
mask_full = Image.open(f"{DATA}/1ae419b8-4357-439e-af17-29ac4feff5a6.png")
refs = [
    Image.open(f"{DATA}/eeaebd90-f13f-4688-b066-5d39302afc59.png"),
    Image.open(f"{DATA}/775e809d-a1f0-4956-857a-082ddb5324b8.png"),
]

zone_full = m._mask_edit_alpha(mask_full).point(lambda v: 255 - v)
alpha_full = init_full.convert("RGBA").getchannel("A")
content = alpha_full.point(lambda v: 255 if v > 8 else 0).getbbox()
zone_bbox = zone_full.point(lambda v: 255 if v >= 128 else 0).getbbox()
boxes = [b for b in (content, zone_bbox) if b]
pad = 8
bx0, by0 = max(0, min(b[0] for b in boxes) - pad), max(0, min(b[1] for b in boxes) - pad)
bx1, by1 = min(init_full.width, max(b[2] for b in boxes) + pad), min(init_full.height, max(b[3] for b in boxes) + pad)
ax0, ay0 = (bx0 // 64) * 64, (by0 // 64) * 64
ax1, ay1 = ((bx1 + 63) // 64) * 64, ((by1 + 63) // 64) * 64
if ax1 > init_full.width:
    ax0 = max(0, ax0 - (ax1 - init_full.width)); ax1 = init_full.width
if ay1 > init_full.height:
    ay0 = max(0, ay0 - (ay1 - init_full.height)); ay1 = init_full.height
edit_bbox = (ax0, ay0, ax1, ay1) if (ax1 - ax0) % 64 == 0 and (ay1 - ay0) % 64 == 0 else (bx0, by0, bx1, by1)
init_pil = init_full.crop(edit_bbox)
mask_pil = mask_full.crop(edit_bbox)
marked = m._draw_mask_marker(init_pil, mask_pil)

images = [durl_png(marked)] + [durl_jpg(r) for r in refs]
print("payload sizes (KB):", [len(s) // 1024 for s in images], "| total:", sum(len(s) for s in images) // 1024, "KB")
body = {"model": MID, "prompt": PROMPT + NOTE, "image": images}
key = m._load_key()
resp = requests.post(m.EDITS_URL, headers={"Authorization": f"Bearer {key}"}, json=body, timeout=300)
print("HTTP", resp.status_code)
out = resp.json()
if isinstance(out, dict) and out.get("data"):
    pil = m._item_to_pil(out["data"][0])
    if pil is None:
        print("FAIL: download None")
    else:
        pil.save("data/_repro_fix_png_mix.png")
        print("saved data/_repro_fix_png_mix.png", pil.size)
else:
    import json as _json
    print("ERROR body:", _json.dumps(out, ensure_ascii=False)[:600])
