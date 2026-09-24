# -*- coding: utf-8 -*-
"""3D Design: генерация IFC по картинке (VLM ImageRouter) + выбор модели в менеджере.

Монтируется под /api:
    POST /api/v1/threed/generate  {scenario: plan|facade|interior|scene, prompt,
                                   image} -> {jobId, status} (фоновая задача)
    GET  /api/v1/threed/jobs/{id} {jobId, status, stage, elapsed_s[, result|error]}
    GET  /api/v1/threed/model     {model, source, vlms:[...]}
    PUT  /api/v1/threed/model     {model} -> {ok}

Модель-аналитик: data/imagerouter_threed_model.json -> .env THREED_MODEL ->
дефолт openai/gpt-6-astra. Список VLM — свой запрос к /v3/models с модальным
фильтром (существующий GET /imagerouter/models фильтрует output=image и VLM
не возвращает!). IFC пишется в root_path/ifc (список IFC-вьювера), диагностический
дамп — root_path/_threed_last.json.
Разворачивается в venv скриптом setup_threed.py.
"""
import base64
import io
import json
import os
import re
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

import requests
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

try:  # задеплоено в venv
    from invokeai.app.api.routers import threed_build, threed_scenarios, threed_verify
except ImportError:  # дерево проекта (тесты)
    from threed import threed_build, threed_scenarios, threed_verify

from invokeai.app.services.config.config_default import get_config

threed_router = APIRouter(prefix="/v1/threed", tags=["threed"])

DEFAULT_MODEL = "openai/gpt-6-astra"
SCENARIOS = {"plan", "facade", "interior", "scene"}
CHAT_TIMEOUT_S = 180
VLM_LIST_CACHE_S = 600
MAX_SIDE = 1536
MAX_TOKENS = 8000  # reasoning-модели тратят лимит до начала ответа (грабля п.22)
JOBS_MAX = 20      # храним последних N задач
JOBS_TTL_S = 1800  # готовые (done/error) живут 30 минут

_vlm_cache = {"ts": 0.0, "list": []}

# --- фоновые задачи (фикс 524: синхронный POST длиннее ~100 с рвёт
# Cloudflare-туннель, при этом бэкенд успевает дописать IFC — UI терял
# имя файла). Генерация уходит в daemon-поток, фронт поллит /jobs/{id}. ---
_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()
_gen_lock = threading.Semaphore(1)  # одна VLM-генерация одновременно


class GenerateBody(BaseModel):
    scenario: str = Field(min_length=1, max_length=32)
    prompt: str = Field(default="", max_length=4000)
    image: str = Field(min_length=32, max_length=20_000_000)  # dataURL PNG


class ModelBody(BaseModel):
    model: str = Field(min_length=3, max_length=128)


# --- per-company корень (…/data) и файлы ---
def _data_dir() -> Path:
    return Path(get_config().root_path)


def _ifc_dir() -> Path:
    d = _data_dir() / "ifc"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _model_store_path() -> Path:
    return _data_dir() / "imagerouter_threed_model.json"


def _env_threed_model() -> str | None:
    v = os.environ.get("THREED_MODEL")
    if v and v.strip():
        return v.strip()
    # .env проекта/компании (как design_code), без кэширования
    for cand in (_data_dir().parent / ".env", Path.cwd() / ".env"):
        try:
            if not cand.is_file():
                continue
            for line in cand.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("THREED_MODEL=") and line.partition("=")[2].strip():
                    return line.partition("=")[2].strip().strip('"').strip("'")
        except Exception:
            continue
    return None


def _load_model_choice() -> tuple[str, str]:
    p = _model_store_path()
    if p.is_file():
        try:
            m = json.loads(p.read_text(encoding="utf-8")).get("model")
            if isinstance(m, str) and m.strip():
                return m.strip(), "file"
        except Exception:
            pass
    env = _env_threed_model()
    if env:
        return env, "env"
    return DEFAULT_MODEL, "default"


def _save_model_choice(model: str) -> None:
    _model_store_path().write_text(
        json.dumps({"model": model}, ensure_ascii=False, indent=1), encoding="utf-8")


def _verify_enabled() -> bool:
    """VLM-самопроверка собранной модели: по умолчанию ВКЛ, .env THREED_VERIFY=
    0/false/no/off выключает (вторая VLM-генерация = вторая трата)."""
    return os.environ.get("THREED_VERIFY", "").strip().lower() not in (
        "0", "false", "no", "off")


def _verify_iters() -> int:
    """Доп. итерации петли самокоррекции (все сценарии): 0..2, дефолт 1."""
    try:
        return max(0, min(2, int(os.environ.get("THREED_VERIFY_ITERS", "1"))))
    except ValueError:
        return 1


def _vlm_list_cached() -> list[dict]:
    """VLM каталога (вход image, выход text), кэш VLM_LIST_CACHE_S."""
    now = time.time()
    if _vlm_cache["list"] and now - _vlm_cache["ts"] < VLM_LIST_CACHE_S:
        return _vlm_cache["list"]
    try:
        resp = requests.get(
            "https://api.imagerouter.io/v3/models",
            params={"input_modalities": "image", "output_modalities": "text",
                    "limit": 500},
            timeout=30)
        data = resp.json() if resp.status_code == 200 else []
        # /v3/models отдаёт голый список (как в imagerouter.py); dict{"data":[…]}
        # оставлен как запасной вариант
        items = data.get("data", []) if isinstance(data, dict) else \
            (data if isinstance(data, list) else [])
    except Exception:
        items = []
    out = []
    for m in items:
        arch = m.get("architecture") or {}
        if "image" in (arch.get("input_modalities") or []) and \
                "text" in (arch.get("output_modalities") or []):
            out.append({"id": m.get("id", "")})
    _vlm_cache.update(ts=now, list=out)
    return out


def _validate_model_in_list(model: str) -> None:
    ids = [m["id"] for m in _vlm_list_cached()]
    if ids and model not in ids:
        raise ValueError(f"Модель {model} не VLM или отсутствует в каталоге")


# --- подготовка картинки и вызов VLM ---
def _prepare_png(dataurl: str):
    from PIL import Image
    raw = base64.b64decode(dataurl.split(",", 1)[-1])
    img = Image.open(io.BytesIO(raw)).convert("RGBA")
    if img.width > MAX_SIDE or img.height > MAX_SIDE:
        img.thumbnail((MAX_SIDE, MAX_SIDE))
    bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
    return Image.alpha_composite(bg, img).convert("RGB")


def _to_dataurl(pil) -> str:
    buf = io.BytesIO()
    pil.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def _call_vlm(system: str, prompt: str, image_url: str, model: str) -> str:
    """Запрос в ImageRouter chat completions (паттерн prompt_enhancer.call_vlm).
    Возвращает СЫРОЙ ответ (разбор JSON — на вызывающем)."""
    from invokeai.app.api.routers.imagerouter import CHAT_COMPLETIONS_URL, _load_key

    key = _load_key()
    if not key:
        raise ValueError("API-ключ ImageRouter не задан (.env: IMAGEROUTER_API_KEY)")
    content = [{"type": "text", "text": prompt or "No user prompt; analyze the image."},
               {"type": "image_url", "image_url": {"url": image_url}}]
    resp = requests.post(
        CHAT_COMPLETIONS_URL,
        headers={"Authorization": f"Bearer {key}"},
        json={"model": model,
              "messages": [{"role": "system", "content": system},
                           {"role": "user", "content": content}],
              "max_tokens": MAX_TOKENS, "temperature": 0.2},
        timeout=CHAT_TIMEOUT_S)
    try:
        data = resp.json()
    except ValueError:
        data = None
    msg = None
    if isinstance(data, dict):
        err = data.get("error")
        if isinstance(err, dict):
            msg = err.get("message")
        elif isinstance(err, str):
            msg = err
    if resp.status_code >= 400 or msg:
        raise ValueError(f"ImageRouter: {msg or f'HTTP {resp.status_code}'}")
    choices = data.get("choices") if isinstance(data, dict) else None
    text = ((choices[0].get("message") or {}).get("content") or "") if choices else ""
    if not text.strip():
        raise ValueError("VLM вернула пустой ответ (попробуйте другую модель в менеджере)")
    return text


def _generate_impl(scenario: str, prompt: str, image, out_dir: Path | None = None,
                   progress=None) -> dict:
    """Без HTTP: анализ -> сцена -> IFC + превью (+ петля самокоррекции всех
    сценариев, задача 5 п.44/п.46: вердикт ок=False с issues -> повторный
    анализ с CORRECTIONS -> пересборка -> повторный verify; победитель по
    ok/числу issues; сбои верификации и попыток >= 2 генерацию не роняют —
    выход на лучшего). progress(stage) опционально уведомляет о этапе
    ("analysis" | "build" | "verify") для статуса фоновой задачи.
    Raises ValueError (роутер даст 422)."""
    if scenario not in SCENARIOS:
        raise ValueError(f"Сценарий «{scenario}» в разработке (доступны: plan, facade, interior, scene)")
    model, source = _load_model_choice()
    try:
        _validate_model_in_list(model)
    except ValueError:
        raise ValueError(f"Модель 3D-анализа {model} недоступна (не VLM или нет в каталоге)")
    image_url = _to_dataurl(image)
    out_dir = Path(out_dir) if out_dir else _ifc_dir()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    system = (threed_scenarios.SYSTEM_SCENE if scenario == "scene"
              else threed_scenarios.SYSTEM_INTERIOR if scenario == "interior"
              else threed_scenarios.SYSTEM_FACADE if scenario == "facade"
              else threed_scenarios.SYSTEM_GENPLAN)

    def _attempt(user_prompt: str, attempt_no: int):
        """Анализ -> валидация -> сборка IFC+превью (одна попытка петли).
        Попытки >= 2 получают суффикс _rN — не перезаписывают друг друга."""
        scene = None
        last_err = ""
        raw_head = ""  # голова успешного сырого ответа VLM (диагностика дампа)
        if progress:
            progress("analysis")
        for try_no in (1, 2):  # один ретрай на невалидный JSON
            raw = _call_vlm(system,
                            user_prompt + ("\n(attempt 2: return ONLY the strict JSON)" if try_no == 2
                                           else ""),
                            image_url, model)
            scene = threed_scenarios.extract_json(raw)
            if scene is not None:
                raw_head = raw[:300]
                break
            last_err = raw[:200]
        if scene is None:
            raise ValueError(f"Модель не смогла описать сцену (не JSON): {last_err}")
        if scenario == "interior":
            scene, warnings = threed_scenarios.validate_interior(
                scene, image.width, image.height)
        elif scenario == "scene":
            scene, warnings = threed_scenarios.validate_scene(scene)
        elif scenario == "facade":
            scene, warnings = threed_scenarios.validate_facade(scene)
        else:
            scene, warnings = threed_scenarios.validate_genplan(
                scene, image.width, image.height)
        name = (f"3D_{scenario}_{stamp}.ifc" if attempt_no == 1
                else f"3D_{scenario}_{stamp}_r{attempt_no}.ifc")
        ifc_path = out_dir / name
        preview_path = out_dir / (Path(name).stem + "_preview.png")
        meta = {"Scenario": scenario, "Prompt": prompt, "Model": model, "Source": "3D Design"}
        if progress:
            progress("build")
        if scenario == "interior":
            threed_build.build_interior(scene, ifc_path, preview_path, meta)
        elif scenario == "scene":
            threed_build.build_scene(scene, ifc_path, preview_path, meta)
        elif scenario == "facade":
            threed_build.build_facade(scene, ifc_path, preview_path, meta)
        else:
            threed_build.build_genplan(scene, image, ifc_path, preview_path, meta)
        return scene, warnings, ifc_path, preview_path, raw_head

    def _verify_attempt(scene, ifc_path):
        """Самопроверка (пилот MCP4IFC-паттерна): обзор «задумано + построено»
        -> второй VLM-запрос с исходной картинкой -> вердикт {ok, issues}."""
        overview = {"scene": threed_verify.scene_overview(scenario, scene),
                    "built": threed_verify.built_overview(ifc_path)}
        return {"overview": overview,
                "verdict": threed_verify.verify(
                    image_url, overview, _call_vlm, model)}

    # петля самокоррекции — все сценарии (п.46: раньше только facade; сцена
    # с мебелью без повтора теряла выпавшие VLM предметы): ok is False с
    # непустыми issues -> повторный анализ с блоком CORRECTIONS; победитель —
    # ok=True, иначе меньше issues; тай-брейк — попытка, чей verify ОТВЕТИЛ
    # (ok=False), бьёт «молчаливую» (ok=None, сбой verify): у той нет ни
    # issues, ни обзора; при равенстве ранга — последняя попытка. Любой сбой
    # (верификации ИЛИ попытки >= 2) НЕ роняет генерацию: предупреждение в
    # history/дампе, выход на лучшего (п.44; C1/I2 ревью задачи 5).
    history = []
    best = None  # (rank, res_i, verify_payload, ifc_path, preview_path, raw_head)
    extra = ""
    max_iters = 1 + (_verify_iters() if _verify_enabled() else 0)
    attempt_files = []
    for attempt_no in range(1, max_iters + 1):
        try:
            scene, warnings, ifc_path, preview_path, raw_head = _attempt(
                prompt + extra, attempt_no)
        except Exception as e:
            if attempt_no == 1:
                raise  # первой попытки нет — генерации нечего отдавать (422)
            # C1 (ревью з.5): петля НИКОГДА не роняет генерацию — сбой
            # повтора (двойной мусор VLM/сеть/build) уходит предупреждением
            # в history, победителем остаётся лучшая выполненная попытка;
            # cleanup/dump ниже выполняются по общему выходу
            history.append({"attempt": attempt_no, "warnings": [],
                            "scene_summary": None,
                            "verdict": {"ok": None,
                                        "error": f"attempt failed: {e}"}})
            break
        attempt_files.append((ifc_path, preview_path))
        verify_payload = None
        if _verify_enabled():
            try:
                if progress:
                    progress("verify")
                verify_payload = _verify_attempt(scene, ifc_path)
            except Exception as e:
                verify_payload = {"overview": None,
                                  "verdict": {"ok": None, "error": str(e)}}
        v = (verify_payload or {}).get("verdict") or {}
        issues = v.get("issues") or []
        history.append({"attempt": attempt_no, "warnings": warnings,
                        "scene_summary": ((verify_payload or {}).get("overview")
                                          or {}).get("scene"),
                        "verdict": v})
        ok = v.get("ok")
        # 1) ok=True лучше остальных; 2) ответивший verify (ok=False) лучше
        # молчащего (ok=None): иначе (0,0)>(0,-1) и сбойная попытка перебивала
        # информативную; 3) меньше issues. Равенство — последняя попытка.
        rank = (1 if ok is True else 0, 0 if ok is None else 1, -len(issues))
        res_i = {"name": ifc_path.name, "warnings": warnings}
        if scenario == "scene":
            res_i["camHint"] = dict(scene["camera"])
            # фокус: центроид людей/мебели НА ВЫСОТЕ (балконный мотив фото) —
            # вьювер наводит камеру на них, а не на центр 100-метровой сцены
            elev = [it for it in scene["context"]["people"]
                    + scene["context"]["furniture"] if it.get("z_m", 0) > 0.05]
            if elev:
                res_i["camHint"]["focus"] = {
                    k: round(sum(it[k] for it in elev) / len(elev), 2)
                    for k in ("x_m", "y_m", "z_m")}
        if verify_payload is not None:
            res_i["verify"] = verify_payload
        if best is None or rank >= best[0]:
            best = (rank, res_i, verify_payload, ifc_path, preview_path, raw_head)
        if ok is True or attempt_no == max_iters:
            break
        if ok is not False or not issues:
            # I2 (ревью з.5): строгий гейт повтора — только ок=False с
            # непустыми issues; ok=None (сбой verify) и ок=False без issues
            # не дают коррекций, платная итерация не запускается
            break
        extra = ("\nCORRECTIONS from QA verification - fix these in your JSON:\n- "
                 + "\n- ".join(issues))
    _, res, verify_payload, ifc_path, preview_path, raw_head = best
    if verify_payload is not None:
        verify_payload["iterations"] = len(history)  # res["verify"] — победитель
    # проигравшие попытки (IFC+превью) удаляем: в out_dir остаётся только
    # победитель (файл финала = файл победителя, имя = имя его попытки)
    for p_ifc, p_prev in attempt_files:
        for p in (p_ifc, p_prev):
            if p not in (ifc_path, preview_path):
                try:
                    p.unlink(missing_ok=True)
                except OSError:
                    pass
    # что реально ушло в VLM (диагностика «не тот дом»: сравнить sha1 с файлом)
    import hashlib
    img_b64 = image_url.split(",", 1)[-1]
    try:
        img_sha1 = hashlib.sha1(base64.b64decode(img_b64)).hexdigest()
        img_bytes = len(img_b64) * 3 // 4
    except Exception:
        img_sha1, img_bytes = "?", 0
    dump_verify = None
    if verify_payload is not None:  # история итераций — только в дампе
        dump_verify = dict(verify_payload)
        dump_verify["history"] = history
    dump = {"ts": datetime.now().isoformat(), "scenario": scenario, "prompt": prompt,
            "model": model, "warnings": res["warnings"], "name": ifc_path.name,
            "image": {"bytes": img_bytes, "sha1": img_sha1,
                      "w": image.width, "h": image.height},
            "vlm_head": raw_head, "verify": dump_verify}
    try:
        (out_dir / "_threed_last.json").write_text(
            json.dumps(dump, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        pass
    return res


# --- фоновой выполнение (job-API) ---
def _job_new(scenario: str) -> dict:
    """Создать задачу; почистить готовые старше TTL и лишние по счёту
    (рестарт сервера очередь обнуляет — артефакты IFC переживают)."""
    now = time.time()
    with _jobs_lock:
        for jid in [k for k, v in _jobs.items()
                    if v["status"] in ("done", "error") and now - v["ts"] > JOBS_TTL_S]:
            del _jobs[jid]
        while len(_jobs) >= JOBS_MAX:
            del _jobs[next(iter(_jobs))]  # dict упорядочен — старейшая
        job = {"id": uuid.uuid4().hex[:12], "status": "queued", "stage": "",
               "scenario": scenario, "created": now, "ts": now,
               "result": None, "error": None}
        _jobs[job["id"]] = job
        return job


def _job_touch(job: dict, **kw) -> None:
    with _jobs_lock:
        job.update(kw)
        job["ts"] = time.time()


def _job_public(job: dict) -> dict:
    out = {"jobId": job["id"], "status": job["status"], "stage": job["stage"],
           "scenario": job["scenario"],
           "elapsed_s": round(max(0.0, time.time() - job["created"]), 1)}
    if job["status"] == "done":
        out["result"] = job["result"]
    elif job["status"] == "error":
        out["error"] = job["error"]
    return out


def _run_job(job: dict, prompt: str, image) -> None:
    """Тело фоновой задачи: семафор(1) строит VLM-очередь; ошибки любого
    рода — в job (error), не в HTTP."""
    with _gen_lock:
        _job_touch(job, status="running", stage="analysis")
        try:
            res = _generate_impl(
                job["scenario"], prompt, image,
                progress=lambda stage: _job_touch(job, stage=stage))
            _job_touch(job, status="done", stage="done", result=res)
        except ValueError as e:
            _job_touch(job, status="error", error=str(e))
        except Exception as e:  # сборщик/сеть — единый вид для модалки
            _job_touch(job, status="error", error=f"3D-генерация не удалась: {e}")


@threed_router.post("/generate")
def generate(body: GenerateBody) -> dict:
    """Фоновый запуск: конвейер (VLM-анализ + сборка + самопроверка) длится
    минуты и не вписывается в ~100-секундный лимит Cloudflare-туннеля —
    ответ мгновенный {jobId}, результат фронт забирает поллингом
    GET /jobs/{id}. Быстрый отказ (битая dataURL) — синхронно 422."""
    try:
        image = _prepare_png(body.image)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Некорректное изображение: {e}")
    job = _job_new(body.scenario)
    threading.Thread(target=_run_job, args=(job, body.prompt, image),
                     daemon=True, name=f"threed-{job['id']}").start()
    # статус фиксирован (не из job): поток мог уже перевести его в running
    return {"jobId": job["id"], "status": "queued"}


@threed_router.get("/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    with _jobs_lock:
        job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(
            status_code=404, detail="Задача не найдена (перезапуск сервера?)")
    return _job_public(job)


@threed_router.get("/model")
def get_model() -> dict:
    model, source = _load_model_choice()
    return {"model": model, "source": source, "vlms": _vlm_list_cached()}


@threed_router.put("/model")
def put_model(body: ModelBody) -> dict:
    try:
        _validate_model_in_list(body.model)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    _save_model_choice(body.model)
    return {"ok": True}
