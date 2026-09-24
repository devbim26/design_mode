# План: настоящие проёмы в интерьерном сборщике

Спека: docs/superpowers/specs/2026-09-24-interior-real-openings-design.md

1. `threed/threed_build.py::build_interior`
   - rbox: container=None → без spatial.assign_container; color_key не из
     fstyles → без style.assign (для IfcOpeningElement).
   - цикл стен: собирать wall_products (выровнен по индексам data["walls"]).
   - цикл проёмов: кламп (стена ≥ 0,6; ширина/центр/высота в габаритах;
     < 0,3 → пропуск); в стене — IfcOpeningElement (+0,02 сквозь) +
     feature.add_feature; заполнение IfcDoor/IfcWindow (глубина
     min(толщина−0,04; 0,08)) + feature.add_filling; на контуре —
     прокси как раньше.
2. `threed/threed_verify.py`: _BUILT_CLASSES += IfcDoor, IfcWindow.
3. `tests/test_threed.py`: пересчитать прокси в test_build_interior и
   test_interior_wall_palette; добавить test_interior_real_openings
   (счёт voids/fills, посадка в сегмент, глубина стекла, огрызок
   выбрасывается, кламп торца).
4. Прогнать: test_threed.py, test_threed_verify.py, test_threed_facade_v2.py.
5. Собрать тест-модель build_interior → data/ifc, открыть в IFC-вьювере
   (браузер), скриншот: стены с дырами, стекло внутри, габариты.
6. Деплой: setup_threed.py, рестарт launch/_restart_server.ps1,
   health-check. HANDOFF п.55.
