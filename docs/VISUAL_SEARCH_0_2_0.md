# Поиск изображений —0.2.0

Продолжение0.1.0 по поручению02.11.2026. Исходная main1ba70c8f. Единый reusable compute остаётся в TimeTracker; ОперКонтур содержит server adapter и доменные разрешения источников/состава. Новые административные UI/API доступны только admin. Смартфон→HTTPS8443 Linux→loopback gateway18983→TLS/HMAC Windows9443; браузер не получает управляющий ключ.

Schema2: immutable generation с hashes пяти массивов/metadata, current/previous atomic pointer; streaming digest/memmap writer, incremental features по source SHA/profile/views/model. До9 представлений на asset и12assets/SKU; unknown=whole. Cylinder overlap/projections только при явном full_wrap. Namespace фильтруется доtop48, optionalkind, код dedup, best view penalty.03, подтверждённые kitlinks без размножения признаков. Смена модели требует совместимого нового индекса и отдельного выпуска. Model facebook/dinov2-small revision ed25f3a31f01632728cabb09d1542f84ab7b0056, safetensors ae1e99fcefd534ed978cdeb8326f08030c96e28b7a81ffcbc98a857c84d14be1, Apache2.0.

Отдельный management HMAC key и peer allowlist, signedsubject audit. Bounded queue8jobs/1background slot, durablemetadata/cancel/resume/backoff, каталог заданий content-addressed; worker group2GiB/10%CPU, compute1.5GiB/torch2/OpenCV1, background1.5GiB/5% в той же группе. Admission5 измерен;429/503 штатные ограниченные ответы. Windows metadata replace/read используют bounded retries sharing/permission errors. Queryframes ни в job ни в index не пишутся; upload session bounded4x64features TTL90s +explicitclose. OS paging/WER остаётся границей гарантии, core disabled. No model network calls, locked local wheels.

Portal: optional kind; exactsquare canvas JPEG, pan/zoom/pinch/rotate, file/paste/nextshot, sessionkind scoped employee. Singlecard500 через authenticated gateway и проверенный public SKU allowlist, fallback250. Ручной/ШК singlecard500; pagination/coauthor/searchstaff/mark сохранены. Код маркировки не меняется.

Калибровка green>=.92+geometry по tuning maxwrong=.90399; не вероятность/гарантия. Heldout100ordinary100complex top1 baseline.99/.93→.99/.99; recall5complex1.0; falsegreen0,30unknownfalsegreen0. Strict single-SKUprecision5complex .433→.3625, расширение подтверждёнными комплектами требует оценки. Sourceexperiment18/72:views500=viewsOriginal1.0, поэтому500основной с explicitoriginal override/fallback. Полный индекс17483features/35021rows/24033namespaceSKU; исходные images не считать по сумме дубликатов namespace.

LoopbackAPI p95single.333s/2users.477/3users.667/5users1.089,errors0,cold3.57; не HTTPS/телефоны.19unitrealmodel PASS, syntheticbrowser exactcrop/320/optional/sessionkind PASS. Offline fullsearchrestore11998statefiles realmodel+top5+adminscope PASS,hashlockedlocalwheels,repeatprepare PASS. Физические телефоны/prelogin/чистаяОС отдельно NOT_RUN; полный изолированный PG restore подтверждён ниже. Детальные результаты и lifecycle адаптера: OperKontur docs/stages/B2_VISUAL_SEARCH_16_RESULT_HANDOFF.md.

Внедрение только из опубликованной main. Старый app CMD запускает migrate.py: не выполнять blindcontainerrestart/up. Сохранить env/DB/media, адресно reload HTTP worker с fresh PID/PPID;gateway можно пересоздать отдельно с read-only source/deps/private/image500, прежнимimageи security limits. Before nginx reload nginx-t. Windows отдельный release и сохранённый индекс/конфиги; откат installation pointer+previousindex+gatewayconfig, без потери новых бизнес-данных. Software/state TOOLS/SNAPSHOT восстанавливаются inertly; TLS/HMAC выдаются заново.


## Фактическое внедрение — 03.11.2026

Compute, gateway и portal assets опубликованы из main cf1bcc135a4633b7a2fa704472c00cde17d3d4d0. ОперКонтур 0.53.1 установлен из отдельного stage/B2 d4c3ab1aec77585d218e4b1e8e08945c1a48f571; CI успешен. Старый gateway и предыдущий индекс сохранены. Основная база и legacy container не перезапускались; маркировка не менялась. Строгий TLS Python 3.14 подтверждён после добавления AKI/SKI к сертификатам на прежних закрытых ключах.

Active index-1793648180382492400, previous index-1793646789298204100; настоящая автоиндексация завершилась. Joint index/designer/5 requests p95 1.145 s, ошибок 0; прирост задержки ОперКонтура 90.27 ms. Warm rollback/return 7.387/6.899 s, запросы без ошибок, private memory дерева максимум 1486 MiB. CPU максимум по окнам >=1 s 7.14%, среднее 5.47%; 100 ms пик 13.51%, поэтому строгий короткооконный предел 10% не утверждается.

Исправленная точная пара TOOLS/SNAPSHOT восстановлена в новую REAL_REHEARSAL: полный PostgreSQL, данные/схема/роли/ACL, свежие локальные зависимости приложения/поиска, модель/current index/known-query top5/admin namespace и повторный prepare PASS. Обязательный публичный distrust-policy PEM поставляемого Python включён; production trust/credentials отсутствуют. Новый тестовый PostgreSQL остановлен, рабочие службы не затронуты. Второй ПК/чистая ОС не проверены.

Остаются обычный employee HTTPS-вход и end-to-end фото, физические телефоны 100+30, физическое наблюдение до первого входа после уже выполненной настройки сетевых Password/Limited Boot-задач. Не выдавать административный/loopback smoke за employee HTTPS. Приложение не сохраняет кадры запроса; OS paging/WER не доказаны. Приёмка владельца открыта.

## Автозапуск Windows — 03.11.2026

03.11.2026 08:04 Europe/Astrakhan: владелец ввёл Windows-пароль только в штатном защищённом диалоге. Четыре существующие задачи Startup/VisualSearch/Images/Backup переведены на Password-logon с Limited; BootTrigger присутствует у всех, прежние действия/настройки/триггеры/владелец сохранены и сверены с XML-preimage. Временная неинтерактивная задача подтвердила обе БД, индекс, утверждённые оригиналы, SMB backup и существующий FTP secret. Пароль в файлы/чат/Git не записывался. HTTP/PostgreSQL/worker TLS READY; перезапусков служб или ПК не было. Физический запуск до первого входа остаётся NOT_RUN.

Первый Apply остановился до изменения задач: экспорт Windows опускал default RunLevel, прямое присваивание отсутствующему XML-полю завершилось ошибкой. Исправленный установщик создаёт отсутствующий узел через DOM, заранее проверяет все четыре XML штатным TaskDefinition-парсером, сохраняет preimages и идемпотентность преобразования; повторный Apply успешен. Это исправление установщика данного хоста, runtime-код и версия программы не менялись.
