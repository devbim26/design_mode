# -*- coding: utf-8 -*-
"""Тесты Prompt Enhancer: роутер (модель/URL), модуль инвокаций, патчи бандлов.

Запуск: venv\\Scripts\\python.exe tests\\test_prompt_enhancer.py
"""
import importlib.util
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _load_router():
    """imagerouter/ — не пакет; грузим imagerouter_router.py по пути."""
    spec = importlib.util.spec_from_file_location(
        "ir_router", ROOT / "imagerouter" / "imagerouter_router.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_router_enhancer_model():
    ir = _load_router()
    assert ir.CHAT_COMPLETIONS_URL == (
        "https://api.imagerouter.io/v1/openai/chat/completions"
    ), ir.CHAT_COMPLETIONS_URL
    assert ir.DEFAULT_ENHANCER_MODEL == "zai/glm-5.3-flash"
    old = os.environ.pop("PROMPT_ENHANCER_MODEL", None)
    old_done = ir._ENV_LOADED["done"]
    ir._ENV_LOADED["done"] = True  # иначе _ensure_env() догрузит проектный .env и вернёт vars
    try:
        assert ir._enhancer_model() == "zai/glm-5.3-flash"  # дефолт
        os.environ["PROMPT_ENHANCER_MODEL"] = "moonshot/kimi-k3"
        assert ir._enhancer_model() == "moonshot/kimi-k3"  # override
        os.environ["PROMPT_ENHANCER_MODEL"] = "   "
        assert ir._enhancer_model() == "zai/glm-5.3-flash"  # пусто -> дефолт
    finally:
        ir._ENV_LOADED["done"] = old_done
        if old is None:
            os.environ.pop("PROMPT_ENHANCER_MODEL", None)
        else:
            os.environ["PROMPT_ENHANCER_MODEL"] = old
    print("OK: роутер — URL чата и модель энхансера")


def _load_enhancer_mod():
    spec = importlib.util.spec_from_file_location(
        "devbim_prompt_enhancer", ROOT / "imagerouter" / "prompt_enhancer.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # стандартный паттерн spec-loader; регистрация нужна,
    # чтобы pydantic мог резолвить модуль динамически загруженных классов
    spec.loader.exec_module(mod)
    return mod


def test_sanitize():
    m = _load_enhancer_mod()
    assert m.sanitize("```json\n{\"p\": 1}\n```") == '{"p": 1}'
    assert m.sanitize('"quoted prompt"') == "quoted prompt"
    assert m.sanitize("  multiple   spaces\tand\ttabs  ") == "multiple spaces and tabs"
    assert m.sanitize("") == ""
    assert m.sanitize(None) == ""
    print("OK: sanitize")


def test_prepare_image():
    from PIL import Image

    m = _load_enhancer_mod()
    big = Image.new("RGBA", (3000, 1200), (255, 0, 0, 128))  # альфа + больше MAX_SIDE
    url = m.prepare_image(big)
    assert url.startswith("data:image/jpeg;base64,/")
    img = Image.open(__import__("io").BytesIO(__import__("base64").b64decode(url.split(",", 1)[1])))
    assert max(img.size) <= 1024
    assert img.mode == "RGB"
    px = img.getpixel((5, 5))
    # альфа=128 на белом: (255, ~127, ~127) — светлый красный; чёрная подложка дала бы (128,0,0)
    assert px[0] > 200 and 100 < px[1] < 160  # альфа склеена с белым, не с чёрным
    print("OK: prepare_image")


def test_build_body():
    m = _load_enhancer_mod()
    body = m.build_body("mm", m.SYSTEM_ENHANCE, "домик", ["data:image/jpeg;base64,QQ"])
    assert body["model"] == "mm"
    assert body["max_tokens"] == 1500 and body["temperature"] == 0.7
    sysmsg, usermsg = body["messages"]
    assert sysmsg["role"] == "system" and sysmsg["content"] == m.SYSTEM_ENHANCE
    kinds = [p["type"] for p in usermsg["content"]]
    assert kinds == ["text", "image_url"], kinds
    assert usermsg["content"][0]["text"] == "Draft prompt: домик"
    assert usermsg["content"][1]["image_url"]["url"].startswith("data:")
    empty = m.user_content("", [])
    assert empty[0]["text"] == "No draft prompt; use the attached reference images."
    print("OK: build_body / user_content")


def test_live_smoke():
    import json

    key_file = ROOT / "data" / "imagerouter.json"
    env_file = ROOT / ".env"
    key = None
    if key_file.exists():
        try:
            key = json.loads(key_file.read_text(encoding="utf-8")).get("api_key")
        except Exception:
            key = None
    if not key and env_file.exists():
        for line in env_file.read_text(encoding="utf-8-sig").splitlines():
            if line.startswith("IMAGEROUTER_API_KEY="):
                key = line.split("=", 1)[1].strip()
    if not key:
        print("SKIP: живой smoke — нет ключа ImageRouter")
        return
    m = _load_enhancer_mod()
    from PIL import Image

    img = Image.new("RGB", (64, 64), (200, 30, 30))
    text = m.call_vlm(
        m.SYSTEM_ENHANCE, "красный квадрат, сделать красиво", [m.prepare_image(img)],
        key=key, model="zai/glm-5.3-flash",
    )
    assert text and not text.startswith("```"), text
    assert len(text.split()) >= 10, text  # развёрнутый промт, не огрызок
    print("OK: живой smoke VLM ->", text[:80], "...")


import shutil
import tempfile

import setup_imagerouter as sir

# Минимальные фрагменты App-бандла, достаточные для якорей патчей
PE_FAKE = (
    'const m7="Generate",pne=u.memo(()=>{const e=FC(),t=qr(),n=T(K2);'
    'return o.jsxs(E,{pos:"relative",w:"200px",children:[o.jsx(hne,{}),'
    'o.jsx(mte,{prepend:t,children:o.jsxs(pe,{onClick:t?e.enqueueFront:e.enqueueBack,'
    'isLoading:e.isLoading||n,loadingText:m7,rightIcon:o.jsx(D1,{}),variant:"solid",'
    'colorScheme:"invokeYellow",size:"lg",w:"calc(100% - 60px)",'
    'children:[o.jsx("span",{children:m7}),o.jsx(mt,{})]})})]})});'
    'pne.displayName="InvokeQueueBackButton";'
)
REFS_FAKE = (
    'const yke=({state:e,imageDTO:t})=>{const n=sd(e);const s=["sdxl"].includes(n)?"tag_based":"sentence_based";'
    'if(t){const i=new Et(Q("claude-analyze-image-graph")),a=i.addNode({type:"claude_analyze_image",'
    'id:Q("claude_analyze_image"),model_architecture:s,image:ehe(t)});return{graph:i,outputNodeId:a.id}}'
    'else{const i=V2(e),a=new Et(Q("claude-expand-prompt-graph")),r=a.addNode({type:"claude_expand_prompt",'
    'id:Q("claude_expand_prompt"),model_architecture:s,prompt:i});return{graph:a,outputNodeId:r.id}}},'
    'lb=async e=>{const{dispatch:t,getState:n,imageDTO:s}=e,i=G0.get();if(!i)return;const{graph:a,outputNodeId:r}=yke({state:n(),imageDTO:s})},'
)
OVERLAY_FAKE = (
    'W$e=({expandedText:e})=>{const t=K(),n=T(V2),s=u.useCallback(()=>{t(nb(e)),ci.reset()},[t,e]),'
    'i=u.useCallback(()=>{const r=n,l=r?`${r}\\n${e}`:e;t(nb(l)),ci.reset()},[t,e,n]),'
    'a=u.useCallback(()=>{ci.reset()},[]);return o.jsxs(E,{pos:"absolute",inset:0,bg:"base.800",'
    'backdropFilter:"blur(8px)",zIndex:10,direction:"column",children:['
    'o.jsx(E,{flex:1,p:2,borderRadius:"md",overflowY:"auto",minH:0,children:'
    'o.jsxs(W,{fontSize:"sm",w:"full",pr:7,children:[o.jsx(Ue,{as:KC,boxSize:5,display:"inline",mr:2,'
    'color:"invokeYellow.500"}),e]})}),o.jsxs(E,{gap:2,p:1,justifyContent:"flex-end",pos:"absolute",'
    'bottom:0,right:0,flexDirection:"column",children:[o.jsxs(Fn,{orientation:"vertical",children:['
    'o.jsx($e,{label:"Replace",placement:"right",children:o.jsx(re,{onClick:s,icon:o.jsx(Wp,{}),'
    'colorScheme:"invokeGreen",size:"xs","aria-label":"Replace"})}),'
    'o.jsx($e,{label:"Insert",placement:"right",children:o.jsx(re,{onClick:i,icon:o.jsx(an,{}),'
    'colorScheme:"invokeBlue",size:"xs","aria-label":"Insert"})})]}),'
    'o.jsx($e,{label:"Discard",placement:"right",children:o.jsx(re,{onClick:a,icon:o.jsx(Yt,{}),'
    'colorScheme:"invokeRed",size:"xs","aria-label":"Discard"})})]})]})},'
    'Lne=u.memo(()=>{const{isSuccess:e,isPending:t}=ie(ci.$state)})'
)


def test_patch_prompt_enhance_button():
    with tempfile.TemporaryDirectory() as td:
        b = Path(td) / "App-fake.js"
        b.write_text(PE_FAKE, encoding="utf-8")
        assert sir.patch_prompt_enhance_button(b) is True
        assert sir.patch_prompt_enhance_button(b) is False  # идемпотентно
        s = b.read_text(encoding="utf-8")
        assert s.count("DevbimPEBtn") >= 2  # определение + использование
        assert s.count('const m7="Generate",pne=u.memo(') == 1  # якорь сохранён
        assert s.index("const DevbimPEBtn") < s.index('const m7="Generate"')
        assert s.count("o.jsx(DevbimPEBtn,{})") == 1
        assert (Path(td) / "App-fake.js.imagerouter-bak").exists()
    print("OK: патч кнопки Prompt Enhance идемпотентен")


def test_patch_generate_viewer_fallback():
    with tempfile.TemporaryDirectory() as td:
        b = Path(td) / "App-fake.js"
        b.write_text(PE_FAKE, encoding="utf-8")
        assert sir.patch_generate_viewer_fallback(b) is True
        assert sir.patch_generate_viewer_fallback(b) is False  # идемпотентно
        s = b.read_text(encoding="utf-8")
        assert s.count("__devbimGenFallback") == 2  # определение + вызов в onClick
        assert "n=T(K2),g=Je();" in s  # стор доступен в компоненте
        assert "__devbimGenFallback(g).finally" in s  # enqueue после фолбэка
        assert "(t?e.enqueueFront:e.enqueueBack)()" in s  # штатный enqueue сохранён
        assert s.count("const m7=") == 1  # якорь не задублирован
        assert (Path(td) / "App-fake.js.imagerouter-bak").exists()
    print("OK: патч Generate-фолбэка идемпотентен")


def test_gen_fallback_migration_v1_to_v2():
    """Бандл со сломанной V1 (DTO по 404-пути GET /images/{name}) мигрирует на V2."""
    with tempfile.TemporaryDirectory() as td:
        b = Path(td) / "App-fake.js"
        v1 = (
            PE_FAKE.replace('const m7="Generate",pne=u.memo(',
                             sir.JS_GEN_FALLBACK_V1 + 'const m7="Generate",pne=u.memo(', 1)
                   .replace("const e=FC(),t=qr(),n=T(K2);", sir.JS_GEN_HOOKS_NEW, 1)
                   .replace("onClick:t?e.enqueueFront:e.enqueueBack", sir.JS_GEN_ONCLICK_NEW, 1)
        )
        b.write_text(v1, encoding="utf-8")
        assert sir.patch_generate_viewer_fallback(b) is True  # миграция
        assert sir.patch_generate_viewer_fallback(b) is False
        s = b.read_text(encoding="utf-8")
        assert sir.JS_GEN_FALLBACK_V1 not in s
        assert sir.JS_GEN_FALLBACK in s
        assert "images_by_names" in s  # правильный DTO-эндпоинт
    print("OK: миграция Generate-фолбэка V1 -> V2")


def test_gen_fallback_helper_syntax():
    """Синтаксис JS-хелпера __devbimGenFallback валиден (node --check)."""
    import subprocess

    node = shutil.which("node")
    if not node:
        print("SKIP: node не найден")
        return
    f = Path(tempfile.mkdtemp()) / "gen_fallback.js"
    f.write_text(sir.JS_GEN_FALLBACK, encoding="utf-8")
    r = subprocess.run([node, "--check", str(f)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    # ключевые строки поведения
    src = sir.JS_GEN_FALLBACK
    assert "st.params.model.key" in src  # модель из params
    assert "редактирование" in src  # гейт: модель принимает картинки
    assert "gallery.selection" in src  # картинка из вьювера
    assert "images_by_names" in src and 'method:"POST"' in src  # DTO правильным эндпоинтом
    assert "E1(g.getState())" in src and "H0({overrides:{config:r}})" in src  # штатный add-reference
    print("OK: node --check __devbimGenFallback")


def test_patch_expand_graph_refs():
    with tempfile.TemporaryDirectory() as td:
        b = Path(td) / "App-fake.js"
        b.write_text(REFS_FAKE, encoding="utf-8")
        assert sir.patch_expand_graph_refs(b) is True
        assert sir.patch_expand_graph_refs(b) is False
        s = b.read_text(encoding="utf-8")
        assert "prompt:i,images:(function(st){" in s
        assert "image_name:x.ipAdapter.image.image_name" in s
        assert "c.present" in s  # redux-undo развёрнут
        assert "st.gallery.selection" in s  # фолбэк на картинку из вьювера
        assert s.count("claude_analyze_image") == 2  # ветка анализа не тронута
        assert (Path(td) / "App-fake.js.imagerouter-bak").exists()
    print("OK: патч референсов идемпотентен")


def _collector_src(patched_text):
    """Достаёт JS-коллектор (function(st){...}) из пропатченного бандла."""
    import re as _re

    m = _re.search(r"images:(\(function\(st\)\{.*?\}\))\(e\)", patched_text, _re.DOTALL)
    assert m, "коллектор не найден в бандле"
    return m.group(1)


def _run_collector_js(collector_src, states):
    """Прогоняет JS-коллектор в node на списке состояний; возвращает список результатов."""
    import json as _json
    import subprocess

    js = (
        "const fn = " + collector_src + ";\n"
        "const cases = " + _json.dumps(states) + ";\n"
        "console.log(JSON.stringify(cases.map(st => fn(st))));\n"
    )
    r = subprocess.run(["node", "-e", js], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return _json.loads(r.stdout)


def test_refs_collector_behavior():
    with tempfile.TemporaryDirectory() as td:
        b = Path(td) / "App-fake.js"
        b.write_text(REFS_FAKE, encoding="utf-8")
        sir.patch_expand_graph_refs(b)
        src = _collector_src(b.read_text(encoding="utf-8"))
        states = [
            {  # референсы приоритетнее галереи
                "canvas": {"present": {"referenceImages": {"entities": [
                    {"isEnabled": True, "ipAdapter": {"image": {"image_name": "ref1.png"}}}]}}},
                "gallery": {"selection": ["gal1.png"]},
            },
            {  # нет референсов -> фолбэк на выбор галереи (картинка во вьювере)
                "canvas": {"present": {"referenceImages": {"entities": []}}},
                "gallery": {"selection": ["gal1.png", "gal2.png"]},
            },
            {  # выключенный референс не считается -> фолбэк
                "canvas": {"present": {"referenceImages": {"entities": [
                    {"isEnabled": False, "ipAdapter": {"image": {"image_name": "r.png"}}}]}}},
                "gallery": {"selection": ["g.png"]},
            },
            {"canvas": {}, "gallery": {"selection": ["a", "b", "c", "d", "e", "f"]}},  # последние 4
            {"canvas": {}},   # пусто везде
            {},               # пустой стейт
            {"canvas": {"referenceImages": {"entities": []}},  # canvas без .present
             "gallery": {"selection": ["x.png"]}},
        ]
        out = _run_collector_js(src, states)
        assert out[0] == [{"image_name": "ref1.png"}], out[0]
        assert out[1] == [{"image_name": "gal1.png"}, {"image_name": "gal2.png"}], out[1]
        assert out[2] == [{"image_name": "g.png"}], out[2]
        assert out[3] == [{"image_name": "c"}, {"image_name": "d"}, {"image_name": "e"}, {"image_name": "f"}], out[3]
        assert out[4] == [] and out[5] == [], (out[4], out[5])
        assert out[6] == [{"image_name": "x.png"}], out[6]
    print("OK: коллектор — референсы приоритет, фолбэк на выбор галереи")


def test_refs_collector_migration_v1_to_v2():
    """Бандл, пропатченный V1-коллектором (без фолбэка галереи), мигрирует на V2."""
    with tempfile.TemporaryDirectory() as td:
        b = Path(td) / "App-fake.js"
        v1_bundle = REFS_FAKE.replace(
            "model_architecture:s,prompt:i});",
            "model_architecture:s,prompt:i," + sir.JS_REFS_COLLECTOR_V1 + "});",
        )
        b.write_text(v1_bundle, encoding="utf-8")
        assert sir.patch_expand_graph_refs(b) is True  # миграция
        assert sir.patch_expand_graph_refs(b) is False  # идемпотентно
        s = b.read_text(encoding="utf-8")
        assert sir.JS_REFS_COLLECTOR_V1 not in s
        assert sir.JS_REFS_COLLECTOR in s
        assert "st.gallery.selection" in s
        out = _run_collector_js(_collector_src(s), [{"gallery": {"selection": ["house.png"]}}])
        assert out == [[{"image_name": "house.png"}]], out
        # мигрированный путь: свежий якорь больше не встречается, только один узел
        assert s.count("claude_expand_prompt") == 2
    print("OK: миграция коллектора V1 -> V2")


def test_patch_expansion_overlay_edit():
    with tempfile.TemporaryDirectory() as td:
        b = Path(td) / "App-fake.js"
        b.write_text(OVERLAY_FAKE, encoding="utf-8")
        assert sir.patch_expansion_overlay_edit(b) is True
        assert sir.patch_expansion_overlay_edit(b) is False
        s = b.read_text(encoding="utf-8")
        # 3 вхождения: атрибут textarea + два querySelector в Replace/Insert
        assert s.count("data-devbim-enhanced") == 3, s.count("data-devbim-enhanced")
        assert "defaultValue:e" in s and "Lne=u.memo(" in s  # якорь-хвост сохранён
        assert (Path(td) / "App-fake.js.imagerouter-bak").exists()
    print("OK: патч оверлея идемпотентен")


def test_deploy_prompt_enhancer():
    with tempfile.TemporaryDirectory() as td:
        dst_dir = Path(td)
        # подменяем пути деплоя
        orig_dst = sir.PE_DST
        try:
            sir.PE_DST = dst_dir / "devbim_prompt_enhancer.py"
            assert sir.deploy_prompt_enhancer() is True
            assert sir.deploy_prompt_enhancer() is False  # повторно — пропуск
            text = sir.PE_DST.read_text(encoding="utf-8")
            assert 'claude_expand_prompt' in text and 'claude_analyze_image' in text
        finally:
            sir.PE_DST = orig_dst
    print("OK: деплой модуля инвокаций идемпотентен")


if __name__ == "__main__":
    test_router_enhancer_model()
    test_sanitize()
    test_prepare_image()
    test_build_body()
    test_live_smoke()
    test_patch_prompt_enhance_button()
    test_patch_generate_viewer_fallback()
    test_gen_fallback_migration_v1_to_v2()
    test_gen_fallback_helper_syntax()
    test_patch_expand_graph_refs()
    test_refs_collector_behavior()
    test_refs_collector_migration_v1_to_v2()
    test_patch_expansion_overlay_edit()
    test_deploy_prompt_enhancer()
