# -*- coding: utf-8 -*-
"""
Ребрендинг InvokeAI -> DevBIM (ссылки -> devbim.com).

Правит собранный фронтенд (venv/Lib/site-packages/invokeai/frontend/web/dist)
и пару строк бэкенда. Идемпотентен: повторный запуск ничего не меняет.
Первый запуск создаёт бэкап: dist_original_backup/ рядом со скриптом.
Восстановление: скопировать содержимое бэкапа обратно в dist.

Также деплоит брендовый баннер над интерфейсом (devbim_banner.js ->
dist/devbim-banner.js + <script> в index.html): логотип-ссылка на страницу
регистрации (заглушка) и слоган, следящий за языком интерфейса.

Пути определяются относительно расположения скрипта (проект переносим).
Запуск: venv\Scripts\python.exe rebrand_devbim.py
"""
import json
import re
import shutil
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
VENV = BASE / "venv"
DIST = VENV / "Lib" / "site-packages" / "invokeai" / "frontend" / "web" / "dist"
BACKUP = BASE / "dist_original_backup"
BACKEND_FILES = [
    VENV / "Lib" / "site-packages" / "invokeai" / "app" / "api_app.py",
    VENV / "Lib" / "site-packages" / "invokeai" / "backend" / "util" / "logging.py",
]
BRAND = "DevBIM"
SITE = "https://devbim.com"
# Цвета бренда: «Dev» — чёрный, «BIM» — голубой; акцент интерфейса — голубой
BLACK = "#111111"
ACCENT = "#38BDF8"
ACCENT_HEX_OLD = "E6FD13"  # бывший жёлтый Invoke

# --- URL-шаблоны: всё, что ведёт на домены Invoke, -> devbim.com ---
URL_REPLACEMENTS = [
    (re.compile(r'https?://invoke-ai\.github\.io/InvokeAI[^"\'`\\\s]*'), SITE),
    (re.compile(r'https?://github\.com/invoke-ai/InvokeAI/releases/tag/v\$\{[^}]*\}'), SITE),
    (re.compile(r'https?://github\.com/invoke-ai/InvokeAI'), SITE),
    (re.compile(r'https?://support\.invoke\.ai/[^"\'`\\\s]*'), SITE),
    (re.compile(r'https?://www\.invoke\.com/get-a-commercial-license-for-flux'), SITE),
    (re.compile(r'https?://www\.invoke\.com/?'), SITE),
    (re.compile(r'https?://invoke\.com/pricing'), SITE),
    (re.compile(r'https?://discord\.gg/ZmtBAhwWhy'), SITE),
    (re.compile(r'https?://(?:www\.)?youtube\.com/@invokeai[^\s"\'`\\]*'), SITE),
]

def sub_urls(text: str) -> str:
    for rx, repl in URL_REPLACEMENTS:
        text = rx.sub(repl, text)
    return text

def patch_index_html() -> int:
    f = DIST / "index.html"
    s = f.read_text(encoding="utf-8")
    n = s.count("<title>Invoke")
    s = s.replace("<title>Invoke - Community Edition</title>", f"<title>{BRAND}</title>")
    f.write_text(s, encoding="utf-8")
    return n

def patch_js_css() -> int:
    total = 0
    for f in DIST.glob("assets/*.js"):
        s = f.read_text(encoding="utf-8")
        orig = s
        s = sub_urls(s)
        # генератор ссылки баг-репорта: zst({user:"invoke-ai",repo:"InvokeAI",...}) -> repoUrl
        s = s.replace('{user:"invoke-ai",repo:"InvokeAI"', f'{{repoUrl:"{SITE}"')
        # подпись кнопки генерации
        s = s.replace('m7="Invoke"', f'm7="{BRAND}"')
        # инлайн-SVG-иконки бренда: жёлтый -> голубой (URL-кодированный #)
        s = s.replace(f"%23{ACCENT_HEX_OLD}", f"%23{ACCENT.lstrip('#')}")
        if s != orig:
            total += 1
            f.write_text(s, encoding="utf-8")
    for f in DIST.glob("assets/*.css"):
        s = sub_urls(f.read_text(encoding="utf-8"))
        f.write_text(s, encoding="utf-8")
    return total

def patch_locale_value(v: str) -> str:
    v = sub_urls(v)
    v = re.sub(r'invoke-ai\.github\.io/InvokeAI[^\s"<]*', 'devbim.com', v)
    v = re.sub(r'\b(?:www\.)?invoke\.com\b[^\s"<]*', 'devbim.com', v)
    v = re.sub(r'\b(?:www\.)?invoke\.ai\b[^\s"<]*', 'devbim.com', v)
    v = re.sub(r'\bInvokeAI\b', BRAND, v)
    v = re.sub(r'\bInvoke\b', BRAND, v)
    return v

def patch_locales() -> int:
    total = 0
    for f in DIST.glob("locales/*.json"):
        data = json.loads(f.read_text(encoding="utf-8"))

        def walk(o):
            if isinstance(o, dict):
                return {k: walk(v) for k, v in o.items()}
            if isinstance(o, list):
                return [walk(v) for v in o]
            if isinstance(o, str):
                return patch_locale_value(o)
            return o

        new = walk(data)
        f.write_text(json.dumps(new, ensure_ascii=False, indent=4) + "\n", encoding="utf-8")
        total += 1
    return total

def two_tone_text(txt: str, fs: float, x: float, y: float) -> str:
    """Текст с раскраской «Dev»/«D» чёрным и «BIM»/«B» голубым."""
    if txt == BRAND:
        spans = f'<tspan fill="{BLACK}">Dev</tspan><tspan fill="{ACCENT}">BIM</tspan>'
    elif txt == "DB":
        spans = f'<tspan fill="{BLACK}">D</tspan><tspan fill="{ACCENT}">B</tspan>'
    else:
        spans = f'<tspan fill="{BLACK}">{txt}</tspan>'
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="middle" dominant-baseline="central" '
        f'font-family="Arial, Helvetica, sans-serif" font-size="{fs:.1f}" font-weight="bold" '
        f'fill="{BLACK}">{spans}</text>'
    )

def make_svg(path: Path) -> None:
    """Генерирует SVG 'DevBIM' в размерах оригинального файла (Dev — чёрный, BIM — голубой)."""
    name = path.name
    s = path.read_text(encoding="utf-8")
    m = re.search(r'viewBox="0 0 (\d+(?:\.\d+)?) (\d+(?:\.\d+)?)"', s)
    if m:
        w, h = float(m.group(1)), float(m.group(2))
    else:
        w, h = 100.0, 100.0

    if "favicon" in name:
        if "alert" in name:
            bg, txt, fg = "#FF3B30", "D", "#FFFFFF"
            body = (
                f'<text x="{w/2:.1f}" y="{h/2:.1f}" text-anchor="middle" dominant-baseline="central" '
                f'font-family="Arial, Helvetica, sans-serif" font-size="{h*0.75:.1f}" font-weight="bold" '
                f'fill="{fg}">{txt}</text>'
            )
        else:
            bg = ACCENT
            body = two_tone_text("D", h * 0.75, w / 2, h / 2)
    elif "wordmark" in name or "tag" in name:
        bg = None
        body = two_tone_text(BRAND, h * 0.72, w / 2, h / 2)
    else:  # symbol / key / avatar — компактный монограммный знак
        bg = None
        body = two_tone_text("DB", h * 0.55, w / 2, h / 2)

    parts = [
        f'<svg width="{int(w)}" height="{int(h)}" viewBox="0 0 {int(w)} {int(h)}" '
        f'fill="none" xmlns="http://www.w3.org/2000/svg">',
    ]
    if bg:
        parts.append(f'<rect width="{int(w)}" height="{int(h)}" rx="{max(1, int(h/8))}" fill="{bg}"/>')
    parts.append(body)
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")

def make_png(path: Path) -> None:
    from PIL import Image, ImageDraw, ImageFont

    img = Image.open(path)
    size = max(img.size)
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=size // 8, fill=ACCENT)
    try:
        font = ImageFont.load_default(size=int(size * 0.7))
    except TypeError:
        font = ImageFont.load_default()
    d.text((size / 2, size / 2), "D", font=font, fill=(0, 0, 0, 255), anchor="mm")
    img.save(path)

def patch_images() -> int:
    total = 0
    for f in (DIST / "assets" / "images").glob("invoke-*.*"):
        if f.suffix == ".svg":
            make_svg(f)
        elif f.suffix == ".png":
            make_png(f)
        else:
            continue
        total += 1
    return total

def patch_backend() -> int:
    total = 0
    for f in BACKEND_FILES:
        if not f.exists():
            continue
        s = f.read_text(encoding="utf-8")
        bak = f.with_suffix(f.suffix + ".devbim-bak")
        if not bak.exists():
            shutil.copy2(f, bak)
        s2 = s.replace('msg = f"Invoke running on', f'msg = f"{BRAND} running on')
        s2 = s2.replace('name: str = "InvokeAI"', f'name: str = "{BRAND}"')
        if s2 != s:
            f.write_text(s2, encoding="utf-8")
            total += 1
    return total

def deploy_banner() -> bool:
    """Баннер «DevBIM — Design» над интерфейсом (devbim_banner.js):
    кликабельный логотип -> страница регистрации (заглушка), слоган справа,
    язык слогана следует за языком интерфейса приложения."""
    src = BASE / "devbim_banner.js"
    if not src.exists():
        print(f"ОШИБКА: не найден {src}")
        sys.exit(1)
    shutil.copy2(src, DIST / "devbim-banner.js")
    f = DIST / "index.html"
    s = f.read_text(encoding="utf-8")
    if "devbim-banner.js" in s:
        return False
    if "</head>" not in s:
        print("ОШИБКА: в index.html нет </head>")
        sys.exit(1)
    bak = f.with_suffix(".html.banner-bak")
    if not bak.exists():
        shutil.copy2(f, bak)
    tag = '  <script src="/devbim-banner.js" defer></script>\n</head>'
    f.write_text(s.replace("</head>", tag, 1), encoding="utf-8")
    return True

def main() -> None:
    if not DIST.exists():
        print(f"dist не найден: {DIST}")
        sys.exit(1)
    if not BACKUP.exists():
        shutil.copytree(DIST, BACKUP)
        print(f"Бэкап оригинала создан: {BACKUP}")
    print("index.html (title):", patch_index_html())
    print("JS/CSS файлов изменено:", patch_js_css())
    print("Локалей обновлено:", patch_locales())
    print("Логотипов заменено:", patch_images())
    print("Файлов бэкенда изменено:", patch_backend())
    print("Баннер DevBIM подключён:", deploy_banner())
    # Контроль: что осталось из брендовых упоминаний (ожидаются только технические)
    leftover = []
    for f in list(DIST.glob("assets/*.js")) + list(DIST.glob("locales/*.json")):
        s = f.read_text(encoding="utf-8")
        for m in re.findall(r'[\w./:#-]*invoke-ai[\w./:#-]*|[\w./:#-]*invoke\.com[\w./:#-]*|[\w./:#-]*invoke\.ai[\w./:#-]*', s, re.I):
            leftover.append(f"{f.name}: {m}")
    print("Остаточные упоминания доменов:", len(leftover))
    for x in sorted(set(leftover))[:10]:
        print("  ", x)

if __name__ == "__main__":
    main()
