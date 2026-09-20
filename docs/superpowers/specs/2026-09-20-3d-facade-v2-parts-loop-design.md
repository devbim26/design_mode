# Спека: 3D Design «Фасад v2» — язык деталей + петля самокоррекции

> **Статус: реализована 20.09 (ветка `3d`)** — схема v2 + custom_parts,
> меш-геометрия, петля verify→CORRECTIONS, тесты и живой roundtrip —
> см. HANDOFF п.45. Отступление от спеки: trimesh НЕ понадобился —
> выпуклые оболочки считает уже стоявший в venv scipy
> (`scipy.spatial.ConvexHull`), новая зависимость не вводилась. Живой
> roundtrip: score 35 → 43, петля сработала (окна 1×2 → 2×2, verify
> ok=True на итерации 2); остаточный разрыв — качество анализа VLM
> (позиции/форма деталей), не выразительность схемы.

Дата: 2026-09-20. Ветка `3d`. Продолжение п.44 (VLM-верификация): вердикт
научился ловить ошибки, но не чинит их, а схема фасада не может выразить
башенки/вальмовые крыши/dormer/порталы — roundtrip-судья даёт 35/100 на
тестовом доме. Цель — качество уровня MCP4IFC (LLM + Blender) БЕЗ Blender:
выразительность даёт грамматика деталей, геометрию — ifcopenshell+trimesh,
фидбек — веб-вьювер и вердикт п.44, замкнутый в петлю.

Решения брейншторма: гибрид (схема+грамматика+петля); в этом заходе только
сценарий «Фасад» (архитектура — сразу под переиспользование сценой).

## 1. Схема фасада v2 (SYSTEM_FACADE + validate_facade)

Новые поля (все опциональны; отсутствие = поведение v1, обратная
совместимость старых сцен/тестов):

- `roof`: `"flat" | "gable" | "hip" | "mansard"` (было 2) + `roof_height`
  (конёк для gable/hip, высота излома для mansard).
- `windows.shape`: `"rect" | "arched"` — арочные окна (профиль с дугой).
- `dormers`: `[{floor, x_m, w_m, h_m}]` — мансардные окна, максимум 12;
  floor клампится в 2..storeys (на первом этаже dormer смысла нет), центр
  x_m клампится в [w/2, width−w/2], размеры в диапазонах 0.6–4 м.
- `chimneys`: `[{x_m, floor}]` — трубы на крыше, максимум 6; коробка
  0.6×0.6, высота 1.2 м над крышей у позиции x_m; floor — от какого этажа
  растёт (по умолчанию последний), кламп 1..storeys.
- `entrance`: `{x_m, w_m, style: "porch" | "portico"} | null` — вход:
  porch = крыльцо-призма + дверь-панель, portico = две колонны-бокса +
  навес-призма; w_m 0.9–5, x_m кламп по фасаду.
- `towers`: `[{x_m, w_m, depth_m, floors, round: <bool, тело-цилиндр
  вместо бокса>, roof: "cone"|"pyramid"|"flat", roof_h_m}]` — башенки,
  максимум 4; floors кламп 1..30; x_m кламп: башня примыкает к фасаду
  (центр в [−width/2−w/2, width/2+w/2], т.е. может стоять чуть в side).
  Тестовому дому нужна круглая башня — cylinder входит сразу.
- `custom_parts`: массив примитивов грамматики, максимум 60:
  `{kind: "box" | "prism" | "cylinder" | "cone",
    size: [w, d, h],                      # метры, клампы 0.05..width
    profile: [[x, y], ...],               # только prism, 3..32 точки,
                                          # кламп |коорд| <= 30 м
    pos: [x, y, z],                       # от центра фасада: x вдоль
                                          # фасада, y от фронта вглубь,
                                          # z от земли; кламп |x|<=width,
                                          # |y|<=depth+10, 0<=z<=высота+15
    rot_deg: <yaw вокруг Z>,
    color: "#rrggbb" | "walls"|"roof"|"plinth"|"glazing"}`

Правила валидации — стиль v1: кламп с warning, дроп с warning, NaN-гварды,
типо-гварды. Валидатор возвращает чистую сцену v2.

## 2. Сборщик (build_facade v2)

- Hip/mansard крыша, конусы, пирамиды, цилиндры — через `trimesh`
  (новая зависимость, pip, чистый Python поверх numpy):
  hip = выпуклая оболочка 4 углов карниза + 2 концов конька (конёк
  укорочен на roof_height·(depth/width) с концов — стандартная вальма);
  mansard = hull с изломом (два уровня). Cone/cylinder — trimesh.creation.
- Меши → IFC4: `IfcPolygonalFaceSet` (грани hull'а уже полигоны) через
  ifcopenshell; фолбэк при отсутствии удобного API — ручной
  IfcTriangulatedFaceSet (деталь реализации, зафиксировать в плане).
- Дормеры: коробка + мини-двускат (профиль-треугольник) + панель
  остекления спереди (та же shape-логика окон). Башни: тело (box/цилиндр
  по этажам) + крыша cone/pyramid (mesh) + часы не рисуем (massing).
- Трубы: коробка на крыше. Вход: по style. Арочные окна: профиль окна —
  прямоугольник + полудуга (8 сегментов).
- Новые ObjectType: `CONCEPTUAL_DORMER, CONCEPTUAL_TOWER, CONCEPTUAL_CHIMNEY,
  CONCEPTUAL_ENTRANCE, CONCEPTUAL_CUSTOM` (крыша любого типа остаётся
  CONCEPTUAL_ROOF) — built_overview п.44 подхватит автоматически (считает
  по ObjectType). Цилиндр/конус одного элемента = один продукт (не
  сегментировать).
- Превью-чертёж: дорисовать силуэты dormer/башен/труб/входа линиями
  (упрощённо, как балконы штрихуются).

## 3. Петля самокоррекции (threed_router._generate_impl)

После сборки+verify: если `verdict.ok is False` и issues непусты и
`THREED_VERIFY_ITERS` > 0 (env, дефолт 1; 0 = выключить петлю) —
повторный АНАЛИЗ: `_call_vlm(SYSTEM_FACADE, prompt + блок
"CORRECTIONS from QA verification: <issues>", image)` → extract_json →
validate → build → verify ещё раз. Выбор победителя: ok=true строгий
приоритет, иначе меньше issues; при равенстве — последняя итерация.
Ответ: `res["verify"]` = вердикт победителя (+ поле `iterations`),
дамп `_threed_last.json` несёт историю обеих итераций (scenes summaries,
verdicts). UI не меняется (тост уже ест verdict). Стоимость: база 2
VLM-вызова, худший случай 4 (~$0.2–0.3).

Петля — только сценарий facade в этой фазе (гейт по scenario == "facade").

## 4. Тесты

Юнит (`tests/test_threed.py` расширение или `tests/test_threed_facade_v2.py`):
1. validate v2: клампы/дропы всех новых полей; битые детали; старая сцена
   v1 без новых полей проходит неизменно.
2. build v2: сэмпл «вилла» (hip + башенка cylinder+cone + 2 dormer +
   chimney + entrance portico + arched) — счётчики
   DORMER=2, TOWER=1, CHIMNEY=1, ENTRANCE=1, WINDOW по сетке; IFC
   открывается, schema IFC4; превью-файл есть.
3. custom_parts: prism по профилю → 1 продукт CONCEPTUAL_CUSTOM;
   переполнение (>60) — срез с warning.
4. Петля в `_generate_impl` (ветвящийся мок): анализ-1 без башни →
   verify issues → анализ-2 с башней → verify ok → ответ = итерация 2,
   `res["verify"]["verdict"]["ok"] is True`, дамп содержит 2 записи;
   THREED_VERIFY_ITERS=0 — петли нет (1 verify).
Живой: `_e2e_3d_roundtrip.py` на vlm_test_house.png — целевой ориентир
score ≥ 60 / match=true (фиксировать в _roundtrip_last.json; жёсткий пол
остаётся 25 — score судьи нестабилен, цель проверяем руками/историей).

## 5. Границы и риски

- trimesh: новая pip-зависимость (лёгкая, без нативных расширений сверх
  numpy) — записать в HANDOFF рядом с ifcopenshell/shapely.
- IfcPolygonalFaceSet во вьювере @thatopen: рендер мешей штатный (web-ifc
  читает IFC4-тесселяцию); риск = picking группированных фрагментов уже
  известен (п.38) — не блокер.
- VLM может злоупотреблять custom_parts (детали-мусор): лимит 60 + счёт в
  overview п.44 (судья увидит «60 кастомных частей» против фото).
- Время: худший случай генерации ~60–90 с (4 запроса) — в пределах
  таймаутов (сервер 180 с / фронт 300 с).

## 6. Файлы

`threed/threed_scenarios.py` (SYSTEM_FACADE, validate_facade),
`threed/threed_build.py` (build_facade + превью), `threed/threed_router.py`
(петля, env), `setup_threed.py` (без изменений — файлы те же), спека+план,
HANDOFF п.45. Модуль verify (п.44) не меняется.
