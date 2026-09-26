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
Tiered-конвейер (п.56): THREED_MODEL — ПОЛНЫЙ override всех стадий; иначе
поэтапные рульки .env THREED_ANALYSIS/REPAIR/VERIFY/ESCALATION_MODEL
(дефолты astra/luna/astra/astra; пустая эскалация = выключена). Ремонт JSON
идёт без картинки, эскалация — одна финальная попытка при провале раунда.
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
    from invokeai.app.api.routers import (
        threed_build, threed_scenarios, threed_verify,
        threed_ground, threed_ensemble, threed_regular)
except ImportError:  # дерево проекта (тесты)
    from threed import (
        threed_build, threed_scenarios, threed_verify,
        threed_ground, threed_ensemble, threed_regular)

from invokeai.app.services.config.config_default import get_config

threed_router = APIRouter(prefix="/v1/threed", tags=["threed"])

DEFAULT_MODEL = "openai/gpt-6-astra"
# tiered-конвейер (п.56): дешёвые ярусы каталога; тарифы за 1M токенов
# astra $10/$50, sol $2/$10, luna $0.1/$0.5 — id сверены с /v3/models 24.09
DEFAULT_REPAIR_MODEL = "openai/gpt-6-luna"
REPAIR_RETRY_MODEL = "openai/gpt-6-sol"
SCENARIOS = {"plan", "facade", "interior", "scene"}
CHAT_TIMEOUT_S = 180
VLM_LIST_CACHE_S = 600
MAX_SIDE = 1536
MAX_TOKENS = 8000  # reasoning-модели тратят лимит до начала ответа (грабля п.22)
JOBS_MAX = 20      # храним последних N задач
JOBS_TTL_S = 1800  # готовые (done/error) живут 30 минут

# per-stage модели: THREED_<STAGE>_MODEL (env) -> дефолт; THREED_MODEL
# (env/file-store) глушит всё — поведение как до п.56
STAGES = ("analysis", "repair", "verify", "escalation")
STAGE_ENV = {"analysis": "THREED_ANALYSIS_MODEL", "repair": "THREED_REPAIR_MODEL",
             "verify": "THREED_VERIFY_MODEL", "escalation": "THREED_ESCALATION_MODEL"}
STAGE_DEFAULTS = {"analysis": DEFAULT_MODEL, "repair": DEFAULT_REPAIR_MODEL,
                  "verify": DEFAULT_MODEL, "escalation": DEFAULT_MODEL}

_vlm_cache = {"ts": 0.0, "list": []}

# --- учёт стоимости VLM-вызовов (реальные вызовы only; моки тестов сюда
# не попадают). Один семафор _gen_lock = одна генерация => один лог. ---
_usage_log: list[dict] = []   # токены/цена каждого вызова текущей генерации
_usage_stage = ["analysis"]   # тег этапа: analysis | repair | verify | escalation

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


def _env_threed_var(name: str) -> str | None:
    """Значение THREED*-переменной: os.environ -> .env проекта/компании
    (как design_code), без кэширования. None = не задана; '' = задана
    пустой (для эскалации — «выключено»)."""
    v = os.environ.get(name)
    if v is not None:
        return v.strip()
    for cand in (_data_dir().parent / ".env", Path.cwd() / ".env"):
        try:
            if not cand.is_file():
                continue
            for line in cand.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith(name + "="):
                    return line.partition("=")[2].strip().strip('"').strip("'")
        except Exception:
            continue
    return None


def _env_threed_model() -> str | None:
    v = _env_threed_var("THREED_MODEL")
    return v if v else None


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


def _stage_model(stage: str) -> tuple[str, str]:
    """Модель стадии конвейера -> (model, source). Полный override THREED_MODEL
    (file-store PUT /model или env) глушит per-stage: все стадии на одной
    модели, поведение как до п.56. Иначе env THREED_<STAGE>_MODEL -> дефолт.
    Эскалация: пустое значение = выключено -> ("", "off")."""
    if stage not in STAGE_ENV:
        raise ValueError(f"Неизвестная стадия: {stage}")
    m, src = _load_model_choice()
    if src in ("file", "env"):
        return m, src
    v = _env_threed_var(STAGE_ENV[stage])
    if v:
        return v, "env:stage"
    if v == "" and stage == "escalation":
        return "", "off"
    return STAGE_DEFAULTS[stage], "default"


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


# --- двухканальный ансамбль (п.60): прогон B + compare/merge + реферти ---
DEFAULT_ENSEMBLE_MODEL = ""  # winner зонда з.1b (Task 3 шаг 7); "" -> text-B
REFEREE_MODEL_DEFAULT = REPAIR_RETRY_MODEL  # sol — ярус выше luna-ремонта


def _ensemble_enabled() -> bool:
    """Двухканальный режим (темы facade/plan/interior): .env THREED_ENSEMBLE=
    0/false/no/off выключает; дефолт ВКЛ (спека з.6)."""
    v = _env_threed_var("THREED_ENSEMBLE")
    return (v if v is not None else "1").strip().lower() not in (
        "0", "false", "no", "off")


def _ensemble_b_model() -> str:
    """Модель прогона B: env THREED_ENSEMBLE_MODEL -> константа зонда.
    "" -> text-fallback на ремонт-модели (спека з.1b)."""
    v = _env_threed_var("THREED_ENSEMBLE_MODEL")
    if v:
        return v
    return DEFAULT_ENSEMBLE_MODEL


def _referee_model() -> str:
    """Модель арбитра споров. ВАЖНО: полным override THREED_MODEL НЕ глушится
    (спека з.3 «отдельное значение, не luna») — судья споров всегда выше
    ярусом, иначе эхо-камера."""
    return _env_threed_var("THREED_REFEREE_MODEL") or REFEREE_MODEL_DEFAULT


def _max_calls() -> int:
    """Лимит VLM-вызовов на ОДНУ попытку (analysis+B+repair+referee+verify;
    спека з.6; эскалация — своя попытка, свой бюджет)."""
    try:
        return max(2, min(20, int(_env_threed_var("THREED_MAX_CALLS_PER_ATTEMPT")
                                  or 6)))
    except ValueError:
        return 6


_attempt_calls = [0]  # счётчик вызовов текущей попытки (сброс в _run_attempt)


def _budget_left() -> bool:
    return _attempt_calls[0] < _max_calls()


def _vlm_counted(system: str, prompt: str, image_url: "str | list[str] | None",
                 model: str) -> str:
    """_call_vlm под бюджетом попытки (п.60 з.6). Счётчик живёт ЗДЕСЬ, а не
    в теле _call_vlm: роутерные тесты подменяют R._call_vlm целиком —
    замоканные вызовы тоже обязаны платить бюджет (иначе лимит не видит B/
    реферти и verify уходит за границу). Все вызовы конвейера (analysis/
    B/repair/referee/verify) идут только через эту обёртку."""
    _attempt_calls[0] += 1  # бюджет попытки (п.60 з.6): считаем всё
    return _call_vlm(system, prompt, image_url, model)


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
            # pricing (за токен, строки вида "10.0e-6") — расчёт стоимости
            out.append({"id": m.get("id", ""), "pricing": m.get("pricing") or {}})
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


def _call_vlm(system: str, prompt: str, image_url: "str | list[str] | None",
              model: str) -> str:
    """Запрос в ImageRouter chat completions (паттерн prompt_enhancer.call_vlm).
    image_url=None — text-only вызов (ремонт JSON п.56: числовая/семантическая
    правка, зрение не нужно). Возвращает СЫРОЙ ответ (разбор — на вызывающем).
    Бюджет попытки считает обёртка _vlm_counted — вызывать только через неё."""
    from invokeai.app.api.routers.imagerouter import CHAT_COMPLETIONS_URL, _load_key

    key = _load_key()
    if not key:
        raise ValueError("API-ключ ImageRouter не задан (.env: IMAGEROUTER_API_KEY)")
    content = [{"type": "text", "text": prompt or "No user prompt; analyze the image."}]
    urls = image_url if isinstance(image_url, list) else ([image_url] if image_url else [])
    for u in urls:
        content.append({"type": "image_url", "image_url": {"url": u}})
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
    _record_usage(model, data)
    return text


# --- учёт стоимости (см. блок _usage_log выше) ---
def _pricing_for(model: str) -> dict:
    for m in _vlm_list_cached():
        if m.get("id") == model:
            return m.get("pricing") or {}
    return {}


def _call_cost_usd(model: str, usage: dict) -> float | None:
    """Стоимость вызова, $: готовый cost из usage (если API даёт) иначе
    тариф каталога — prompt/completion за токен, кэш-чтение дешевле.
    None = данных нет (мок VLM, каталог недоступен, нулевая цена)."""
    if not isinstance(usage, dict):
        return None
    if usage.get("cost") not in (None, ""):
        try:
            return float(usage["cost"])
        except (TypeError, ValueError):
            pass
    pr = _pricing_for(model)
    if not pr:
        return None
    try:
        p_in = float(usage.get("prompt_tokens") or 0)
        p_out = float(usage.get("completion_tokens") or 0)
        cached = 0.0
        det = usage.get("prompt_tokens_details")
        if isinstance(det, dict):
            cached = float(det.get("cached_tokens") or 0)
        cost = (p_in - cached) * float(pr.get("prompt") or 0) \
            + p_out * float(pr.get("completion") or 0) \
            + cached * float(pr.get("input_cache_read") or 0)
        return cost if cost > 0 else None
    except (TypeError, ValueError):
        return None


def _record_usage(model: str, data) -> None:
    """Токены/стоимость ВЫПОЛНЕННОГО VLM-вызова -> _usage_log (очищается
    в начале _generate_impl). Этап ставится в точке вызова (_usage_stage)."""
    u = data.get("usage") if isinstance(data, dict) else None
    if not isinstance(u, dict):
        return
    entry = {"stage": _usage_stage[0], "model": model,
             "tokens_in": u.get("prompt_tokens"),
             "tokens_out": u.get("completion_tokens")}
    cost = _call_cost_usd(model, u)
    if cost is not None:
        entry["cost_usd"] = round(cost, 6)
    _usage_log.append(entry)


def _usage_summary() -> dict:
    """Итог генерации для ответа/дампа: вызовы, суммы токенов, цена."""
    if not _usage_log:
        return {}
    calls = [dict(e) for e in _usage_log]
    costs = [e["cost_usd"] for e in calls if "cost_usd" in e]
    out = {"calls": calls,
           "tokens": {"in": sum(e.get("tokens_in") or 0 for e in calls),
                      "out": sum(e.get("tokens_out") or 0 for e in calls)}}
    if costs:
        out["cost_usd"] = round(sum(costs), 4)
    return out


def _repair_scene(scene, issues, img_w, img_h):
    """JSON-ремонт семантических issues контракта — БЕЗ картинки (п.56:
    числовая/семантическая правка, зрение не нужно). Ремонт-модель ->
    гейт (extract_json + validate_interior) -> при провале один повтор на
    sol. Возвращает (fixed_scene | None, warnings, issues_left): None —
    ремонт не удался, вызывающий оставляет исходную сцену, issues едут в
    CORRECTIONS следующей итерации/эскалации (как сегодня)."""
    repair_model = _stage_model("repair")[0]
    prompt = ("Scene JSON:\n" + json.dumps(scene, ensure_ascii=False)
              + "\n\nIssues to fix:\n- " + "\n- ".join(issues)
              + "\n\nReturn the corrected FULL scene JSON.")
    for model in (repair_model, REPAIR_RETRY_MODEL):
        _usage_stage[0] = "repair"
        raw = _vlm_counted(threed_scenarios.SYSTEM_REPAIR, prompt, None, model)
        fixed = threed_scenarios.extract_json(raw)
        if fixed is None:
            continue
        try:
            fixed_scene, wns, left = threed_scenarios.validate_interior(
                fixed, img_w, img_h)
        except ValueError:
            continue
        wns.append(f"контракт: {len(issues)} issues -> ремонт {model} -> "
                   f"осталось {len(left)}")
        return fixed_scene, wns, left
    return None, [f"контракт: ремонт не помог ({repair_model} и "
                  f"{REPAIR_RETRY_MODEL}) — issues едут в CORRECTIONS"], \
        list(issues)


def _generate_impl(scenario: str, prompt: str, image, out_dir: Path | None = None,
                   progress=None) -> dict:
    """Без HTTP: анализ -> сцена -> IFC + превью (+ петля самокоррекции всех
    сценариев, задача 5 п.44/п.46: вердикт ок=False с issues -> повторный
    анализ с CORRECTIONS -> пересборка -> повторный verify; победитель по
    ok/числу issues; сбои верификации и попыток >= 2 генерацию не роняют —
    выход на лучшего). Tiered-надстройка п.56: контракт посадки до сборки
    (validate_interior -> issues) с text-only ремонтом, per-stage модели,
    после раунда — ОДНА эскалационная попытка при провале. progress(stage)
    опционально уведомляет о этапе ("analysis" | "build" | "verify"; ремонт
    и эскалация идут под "analysis") для статуса фоновой задачи.
    Raises ValueError (роутер даст 422)."""
    if scenario not in SCENARIOS:
        raise ValueError(f"Сценарий «{scenario}» в разработке (доступны: plan, facade, interior, scene)")
    _usage_log.clear()
    model, source = _stage_model("analysis")
    stage_models = {st: _stage_model(st)[0] for st in STAGES}
    # вверх проверяем только модели, которые генерация ТОЧНО использует:
    # analysis всегда, verify при включённой верификации. Ремонт/эскалация —
    # лениво (случайный сценарий не блокируется опечаткой в чужой рульке;
    # их сбой глушится гейтом ремонта / записью в history, не 422)
    for st in (("analysis",) + (("verify",) if _verify_enabled() else ())):
        try:
            _validate_model_in_list(stage_models[st])
        except ValueError:
            raise ValueError(
                f"Модель стадии {st} ({stage_models[st]}) недоступна "
                f"(не VLM или нет в каталоге; рулька {STAGE_ENV[st]})")
    image_url = _to_dataurl(image)
    out_dir = Path(out_dir) if out_dir else _ifc_dir()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    system = (threed_scenarios.SYSTEM_SCENE if scenario == "scene"
              else threed_scenarios.SYSTEM_INTERIOR if scenario == "interior"
              else threed_scenarios.SYSTEM_FACADE if scenario == "facade"
              else threed_scenarios.SYSTEM_GENPLAN)

    ens_hint = [None]  # пиксельный bbox здания из B (якорь оверлея фасада)

    def _ensemble_pass(user_prompt, scene):
        """Двухканальный режим (п.60): B (grounding|text) -> compare ->
        merge (реферти по спорам, <=1 вызов) -> регуляризация по гейту.
        ЛЮБОЙ сбой — warning + исходная A (не хуже текущего поведения)."""
        # I1 (финальное ревью): якорь попытки N не должен переживать попытку
        # N+1 — оверлей verify следующей попытки не заякоривается на бокс B
        # предыдущей (и не остаётся после B без building)
        ens_hint[0] = None
        if not _ensemble_enabled():
            return scene, None, []
        wns = []
        b_model = _ensemble_b_model()
        info = {"mode": "grounding" if b_model else "text",
                "b_model": b_model or _stage_model("repair")[0],
                "agree_rate": None, "disputed_fields": [], "pixel_hint": None}
        if not _budget_left():
            wns.append("ансамбль: прогон B пропущен — лимит VLM-вызовов попытки")
            return scene, None, wns
        try:
            _usage_stage[0] = "ensemble"
            if b_model:
                payload, b_wns = threed_ground.run_ground_pass(
                    scenario, image_url, b_model, _vlm_counted)
                wns += b_wns
                if payload is None:
                    return scene, None, wns
                raw_b = threed_ground.CONVERTERS[scenario](
                    payload, image.width, image.height)[0]
                if scenario == "facade":  # якорь оверлея — бокс building
                    ens_hint[0] = threed_ground.facade_pixel_hint(
                        payload, image.width, image.height)
                    info["pixel_hint"] = ens_hint[0]
            else:
                raw_b, b_wns = threed_ground.run_text_pass(
                    scenario, user_prompt, image_url, info["b_model"], _vlm_counted)
                wns += b_wns
                if raw_b is None:
                    return scene, None, wns
            if not raw_b:
                wns.append("ансамбль: сцена B пуста — работаем с A")
                return scene, None, wns
            try:
                if scenario == "facade":
                    b_scene, _ = threed_scenarios.validate_facade(dict(raw_b))
                elif scenario == "plan":
                    b_scene, _ = threed_scenarios.validate_genplan(
                        dict(raw_b), image.width, image.height)
                else:
                    b_scene, _, _ = threed_scenarios.validate_interior(
                        dict(raw_b), image.width, image.height)
            except ValueError as e:
                wns.append(f"ансамбль: сцена B невалидна ({e}) — работаем с A")
                return scene, None, wns
            cmp = threed_ensemble.compare_scenes(scenario, scene, b_scene)

            def referee(fields):
                body = {f: {"A": cmp["disputed"][f][0],
                            "B": cmp["disputed"][f][1]} for f in fields}
                raw = _vlm_counted(
                    threed_ensemble.SYSTEM_REFEREE,
                    "Image = the source the fields were extracted from.\n"
                    "Disputed fields of two independent extractions:\n"
                    + json.dumps(body, ensure_ascii=False)
                    + "\nFor EACH field pick the value better matching the "
                      "image. STRICT JSON only.", image_url, _referee_model())
                return threed_scenarios.extract_json(raw)

            _usage_stage[0] = "ensemble"
            # I2 (финальное ревью): решение о реферти фиксируем ДО merge —
            # успешно отработавший реферти, занявший последний слот бюджета,
            # не должен рождать ложный «реферти за бюджетом»
            referee_pass = bool(cmp["disputed"]) and _budget_left()
            scene, confidence, m_wns = threed_ensemble.merge_scenes(
                scenario, scene, b_scene, cmp,
                referee=referee if referee_pass else None)
            wns += m_wns
            if cmp["disputed"] and not referee_pass:
                wns.append("ансамбль: реферти за бюджетом — спорные из A")
            info["agree_rate"] = confidence["agree_rate"]
            info["disputed_fields"] = confidence["disputed_fields"]
            if confidence["agree_rate"] >= threed_regular.REGULAR_GATE:
                scene = threed_regular.regularize(scenario, scene,
                                                  confidence, wns)
            else:
                wns.append("regularization skipped: low ensemble agreement")
        except Exception as e:
            wns.append(f"ансамбль: сбой прогона B ({e}) — работаем с A")
            return scene, None, wns
        return scene, info, wns

    def _attempt(user_prompt: str, attempt_no: int, model_override=None,
                 stage: str = "analysis"):
        """Анализ -> валидация (+ контракт посадки и ремонт п.56) -> сборка
        IFC+превью (одна попытка петли). Попытки >= 2 получают суффикс _rN —
        не перезаписывают друг друга; эскалационная попытка приходит с
        model_override и stage="escalation"."""
        a_model = model_override or model
        scene = None
        last_err = ""
        raw_head = ""  # голова успешного сырого ответа VLM (диагностика дампа)
        if progress:
            progress("analysis")
        _usage_stage[0] = stage
        for try_no in (1, 2):  # один ретрай на невалидный JSON
            raw = _vlm_counted(system,
                               user_prompt + ("\n(attempt 2: return ONLY the strict JSON)" if try_no == 2
                                              else ""),
                               image_url, a_model)
            scene = threed_scenarios.extract_json(raw)
            if scene is not None:
                raw_head = raw[:300]
                break
            last_err = raw[:200]
        if scene is None:
            raise ValueError(f"Модель не смогла описать сцену (не JSON): {last_err}")
        contract_issues = []
        if scenario == "interior":
            scene, warnings, contract_issues = threed_scenarios.validate_interior(
                scene, image.width, image.height)
        elif scenario == "scene":
            scene, warnings = threed_scenarios.validate_scene(scene)
        elif scenario == "facade":
            scene, warnings = threed_scenarios.validate_facade(scene)
        else:
            scene, warnings = threed_scenarios.validate_genplan(
                scene, image.width, image.height)
        ensemble_info = None
        if scenario in ("facade", "plan", "interior"):
            scene, ensemble_info, ens_wns = _ensemble_pass(user_prompt, scene)
            warnings += ens_wns
            if scenario == "interior" and ensemble_info:
                # merge мог заменить комнаты/стены — перепосадить проёмы
                # константами п.55 (общий импорт, не дублировать)
                threed_scenarios._seat_openings(scene, warnings, contract_issues)
        if scenario == "interior" and contract_issues:
            try:  # ремонт ПОСЛЕ merge (порядок стадий спеки з.6)
                if not _budget_left():
                    raise ValueError("лимит VLM-вызовов попытки")
                fixed, rep_wns, contract_issues = _repair_scene(
                    scene, contract_issues, image.width, image.height)
            except Exception as e:  # сеть/ключ/бюджет — ремонт не роняет попытку
                rep_wns = [f"контракт: ремонт не удался ({e})"]
            else:
                if fixed is not None:
                    scene = fixed
            warnings = list(warnings) + rep_wns
        name = (f"3D_{scenario}_{stamp}.ifc" if attempt_no == 1
                else f"3D_{scenario}_{stamp}_r{attempt_no}.ifc")
        ifc_path = out_dir / name
        preview_path = out_dir / (Path(name).stem + "_preview.png")
        meta = {"Scenario": scenario, "Prompt": prompt, "Model": a_model,
                "Source": "3D Design"}
        if ensemble_info and ensemble_info.get("agree_rate") is not None:
            meta["EnsembleAgreement"] = json.dumps(
                {"agree_rate": ensemble_info["agree_rate"],
                 "disputed_fields": ensemble_info["disputed_fields"],
                 "mode": ensemble_info["mode"]}, ensure_ascii=False)
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
        return scene, warnings, ifc_path, preview_path, raw_head, \
            contract_issues, ensemble_info

    def _verify_attempt(scene, ifc_path, structural, ensemble_info=None):
        """Самопроверка (пилот MCP4IFC-паттерна): обзор «задумано + построено»
        -> второй VLM-запрос с исходной картинкой -> вердикт {ok, issues}.
        Судья всегда на THREED_VERIFY_MODEL (>= sol по ярусу — эхо-камера
        исключена конструктивно). structural (п.58) — машинные дефекты сборки
        отдельным блоком (C): верификатор получает их как ground truth.
        Оверлей з.5: судья получает [оригинал, оверлей сцены-победителя
        ДО сборки] (пиксельный якорь — бокс building прогона B)."""
        if not _budget_left():
            raise ValueError("verify: лимит VLM-вызовов попытки")
        _usage_stage[0] = "verify"
        overlay_url = None
        try:
            ov = threed_verify.render_overlay(
                scenario, scene, image, pixel_hint=ens_hint[0])
            overlay_url = _to_dataurl(ov)
        except Exception:
            pass  # оверлей не критичен: судья увидит хотя бы оригинал
        overview = {"scene": threed_verify.scene_overview(scenario, scene),
                    "built": threed_verify.built_overview(ifc_path),
                    "structural": (structural or {}).get("issues") or []}
        return {"overview": overview, "ensemble": ensemble_info,
                "verdict": threed_verify.verify(
                    image_url, overview, _vlm_counted, stage_models["verify"],
                    overlay_url=overlay_url)}

    # петля самокоррекции — все сценарии (п.46: раньше только facade; сцена
    # с мебелью без повтора теряла выпавшие VLM предметы): ok is False с
    # непустыми issues (verify ИЛИ контракта п.56) -> повторный анализ с
    # блоком CORRECTIONS; победитель — ok=True, иначе меньше issues;
    # тай-брейк — попытка, чей verify ОТВЕТИЛ (ok=False), бьёт «молчаливую»
    # (ok=None, сбой verify): у той нет ни issues, ни обзора; при равенстве
    # ранга — последняя попытка. Любой сбой (верификации ИЛИ попытки >= 2)
    # НЕ роняет генерацию: предупреждение в history/дампе, выход на лучшего
    # (п.44; C1/I2 ревью задачи 5).
    history = []
    best = None  # (rank, res_i, verify_payload, ifc_path, preview_path, raw_head)
    corr_pool = []  # накопленные коррекции: verify issues + issues контракта

    def _add_corr(items):
        for it in items:
            if it and it not in corr_pool:
                corr_pool.append(it)

    def _run_attempt(user_prompt, attempt_no, a_model, stage):
        """Попытка целиком: анализ -> контракт/ремонт -> сборка -> verify ->
        history/ранг/победитель. None = сбой попытки >= 2 (ушёл в history),
        иначе (ok, verify-issues, оставшиеся issues контракта)."""
        _attempt_calls[0] = 0  # бюджет попытки (п.60 з.6): своя — свой лимит
        nonlocal best
        try:
            scene, warnings, ifc_path, preview_path, raw_head, c_issues, \
                ens_info = _attempt(user_prompt, attempt_no,
                                    model_override=a_model, stage=stage)
        except Exception as e:
            if attempt_no == 1:
                raise  # первой попытки нет — генерации нечего отдавать (422)
            # C1 (ревью з.5): петля НИКОГДА не роняет генерацию — сбой
            # повтора (двойной мусор VLM/сеть/build) уходит предупреждением
            # в history, победителем остаётся лучшая выполненная попытка;
            # cleanup/dump ниже выполняются по общему выходу
            history.append({"attempt": attempt_no, "warnings": [],
                            "contract_issues": [],
                            "scene_summary": None,
                            "verdict": {"ok": None,
                                        "error": f"attempt failed: {e}"},
                            "ensemble": None})  # ключ есть и у сбойных попыток
            return None
        attempt_files.append((ifc_path, preview_path))
        # п.58: структурные проверки собранного IFC — всегда (бесплатные,
        # без VLM-запросов; при выключенном THREED_VERIFY тоже считаются).
        # Мягкий режим: не влияет на ранг/corr_pool — дефект сборщика не
        # материал для CORRECTIONS повторного анализа сцены
        try:
            structural = threed_verify.structural_report(ifc_path)
        except Exception as e:
            structural = {"ok": None, "issues": [], "error": str(e)}
        verify_payload = None
        if _verify_enabled():
            try:
                if progress:
                    progress("verify")
                verify_payload = _verify_attempt(scene, ifc_path, structural,
                                                 ensemble_info=ens_info)
            except Exception as e:
                verify_payload = {"overview": None,
                                  "verdict": {"ok": None, "error": str(e)}}
        v = (verify_payload or {}).get("verdict") or {}
        issues = v.get("issues") or []
        history.append({"attempt": attempt_no, "warnings": warnings,
                        "contract_issues": c_issues,
                        "scene_summary": ((verify_payload or {}).get("overview")
                                          or {}).get("scene"),
                        "verdict": v, "ensemble": ens_info})
        _add_corr(issues)
        _add_corr(c_issues)
        ok = v.get("ok")
        # 1) ok=True лучше остальных; 2) ответивший verify (ok=False) лучше
        # молчащего (ok=None): иначе (0,0)>(0,-1) и сбойная попытка перебивала
        # информативную; 3) меньше issues. Равенство — последняя попытка.
        rank = (1 if ok is True else 0, 0 if ok is None else 1, -len(issues))
        res_i = {"name": ifc_path.name, "warnings": warnings,
                 "structural": structural}
        if ens_info is not None:
            res_i["ensemble"] = ens_info
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
        return ok, issues, c_issues

    corr_header = "\nCORRECTIONS from QA verification - fix these in your JSON:\n- "
    max_iters = 1 + (_verify_iters() if _verify_enabled() else 0)
    attempt_files = []
    extra = ""
    for attempt_no in range(1, max_iters + 1):
        r = _run_attempt(prompt + extra, attempt_no, model, "analysis")
        if r is None:
            break
        ok, issues, c_issues = r
        if ok is True or attempt_no == max_iters:
            break
        corr_items = issues + [i for i in c_issues if i not in issues]
        if ok is not False or not corr_items:
            # I2 (ревью з.5): строгий гейт повтора — только ок=False с
            # непустыми коррекциями (verify или контракта); ok=None (сбой
            # verify) и ок=False без материала не запускают платную итерацию
            break
        extra = corr_header + "\n- ".join(corr_items)

    # эскалация (п.56, часть 3): раунд попыток на analysis-модели доказал
    # провал — лучший вердикт ок=False (или verify ни разу не ответил) — и
    # эскалационная модель ДРУГАЯ (дороже) -> ОДНА финальная попытка с полным
    # накопленным CORRECTIONS (verify issues всех попыток + semantic issues
    # контракта). Пустой THREED_ESCALATION_MODEL / verify выключен / полный
    # override THREED_MODEL (analysis == escalation) -> эскалации нет.
    esc_model = stage_models["escalation"] if _verify_enabled() else ""
    best_ok = ((best[2] or {}).get("verdict") or {}).get("ok") if best else None
    if esc_model and esc_model != model and best_ok is not True:
        esc_prompt = prompt + (corr_header + "\n- ".join(corr_pool)
                               if corr_pool else "")
        _run_attempt(esc_prompt, max_iters + 1, esc_model, "escalation")
    _, res, verify_payload, ifc_path, preview_path, raw_head = best
    usage_sum = _usage_summary()
    if usage_sum:
        res["usage"] = usage_sum  # фронт: тост «потрачено $X»
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
            "stages": stage_models,
            "ensemble": res.get("ensemble"),
            "image": {"bytes": img_bytes, "sha1": img_sha1,
                      "w": image.width, "h": image.height},
            "vlm_head": raw_head, "usage": usage_sum, "verify": dump_verify,
            "structural": res.get("structural")}
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
    # stages (п.56): (model, source) каждой стадии конвейера — наблюдаемость
    # tiered-рулек; фронт по-прежнему читает model/source/vlms
    stages = {s: _stage_model(s) for s in STAGES}
    return {"model": model, "source": source, "vlms": _vlm_list_cached(),
            "stages": stages}


@threed_router.put("/model")
def put_model(body: ModelBody) -> dict:
    try:
        _validate_model_in_list(body.model)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    _save_model_choice(body.model)
    return {"ok": True}
