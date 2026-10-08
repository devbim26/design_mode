# План: тултипы кнопок ✨/3D + улучшатель в менеджере + фото в 3D-модалке (08.10)

Запрос пользователя:
1. При наведении на кнопки «Prompt Assistant» (✨) и «3D Design» у Generate —
   понятные пояснения вместо «Prompt Enhance»/«3D Design».
   - ✨: ваш текст и картинка отправляются в специальную модель для более
     качественной генерации (проверено по коду: `claude_expand_prompt` шлёт
     промт + до 4 референсов в VLM ImageRouter — утверждение верно).
   - 3D: по кнопке строится 3D-модель сцены; ракурс камеры можно изменить,
     затем вернуть изначальное фото — ИИ-рендер восстановит сцену с новым
     ракурсом.
2. В менеджере моделей (imagerouter.html) для улучшателя промтов:
   - выбор модели VLM (как секция 3D `#threedsec`);
   - вывод улучшенного промта для редактирования (тест-зона: промт +
     опциональная картинка → редактируемый textarea с результатом).
3. В модалку 3D Design — до 2 поясняющих фото с подписями; фото и подписи
   загружаются через менеджер моделей.

## Задачи

1. **imagerouter/devbim_topright_buttons.js**
   - TEXTS ru/en: `peTip`, `tdTip`; тултипы (`title` + aria-label) живут
     по языку интерфейса (обновление в pollLanguage, как тосты).
   - Модалка 3D: блок `.devbim-3d-photos` (2 мини-фото + подписи) после
     превью источника; контент — GET /api/v1/threed/modal-media; пусто/ошибка
     → блок скрыт.
2. **imagerouter/imagerouter_router.py**
   - Цепочка модели энхансера: `data/imagerouter_prompt_model.json` →
     .env PROMPT_ENHANCER_MODEL → дефолт (паттерн threed). `_enhancer_model()`
     читает цепочку при каждом вызове (F5 не нужен).
   - GET/PUT `/api/v1/imagerouter/enhancer-model` {model, source, vlms} —
     список VLM своим запросом /v3/models (вход image, выход text; голый
     список ИЛИ {"data":[…]}); PUT валидирует по каталогу.
   - POST `/api/v1/imagerouter/enhance-test` {prompt, image?} → {prompt} —
     тот же SYSTEM_ENHANCE/call_vlm/prepare_image из развёрнутого модуля
     инвокций (ленивый импорт), глобальный ключ админа, выбранная модель.
3. **imagerouter/imagerouter.html** — две секции в sidecol:
   - `#pesec` «Улучшение промтов»: select+Save (как #threedsec) + тест-зона
     (textarea промта, file-картинка, «Улучшить», редактируемый результат,
     «Копировать»).
   - `#mediasec` «3D Design — фото в модалке»: 2 слота (загрузка файла →
     POST dataURL, подпись, удаление; подписи — PUT).
4. **threed/threed_router.py**
   - Хранилище: `<root>/imagerouter_threed_modal.json`
     ({items:[{slot:1|2, caption, file}]}) + `<root>/threed_modal/<slot>.jpg`
     (даунскейл до 1024, JPEG q85, белый фон — как prepare_image).
   - GET /modal-media → {items:[{slot, caption, url}]}; PUT /modal-media —
     подписи; POST/DELETE /modal-media/{slot}/image; GET
     /modal-media/{slot}/image — FileResponse (Cache-Control короткий).
5. **Тесты** `tests/test_enhancer_media.py`: цепочка модели (file→env→default),
   PUT-валидация, enhance-test со стабом модуля инвокций; media: POST 1×1 PNG →
   GET → PUT подписи → DELETE (get_config → tmp, без сети).
6. **Деплой/проверка**: setup_imagerouter.py + setup_threed.py (идемпотентны),
   рестарт `launch\_restart_server.ps1`, curl-проверки эндпоинтов через вход
   siteauth, node --check виджета. Бандлы НЕ трогаем — F5 достаточно.
7. **HANDOFF.md** — новый пункт.

Границы: промтовый оверлей в приложении уже редактируемый (textarea +
Replace/Insert) — не трогаем; владение/изоляция не нужны (контент
инстанс-уровня, менеджер только у админа).
