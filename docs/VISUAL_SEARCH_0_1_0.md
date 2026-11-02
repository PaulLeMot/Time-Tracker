# Поиск рисунка по фото — кандидат 0.1.0

02.11.2026. **LOCAL_CANDIDATE; production не включён.**
ТЗ: передача OPERPORTAL_OLD_VISUAL_SEARCH_HANDOFF_20261102, включая решение08.
Начальная синхронизация clean main6555c9d; отдельно получен main9ace802 соавтора.
Его pagination/options/prefetch и красная линия сохранены. Рабочая копия соавтора
release11 не изменялась. Изменения нового режима — static/search.html,
static/visual-search.*, services/visual_search, адресные tests/lab и этот документ.

## Поведение и границы

Существующая страница изображений получает кнопку «По фото» после успешного
запроса capabilities. Без службы она скрыта. Вид обязателен и проверяется сервером
до отбора кандидатов. В отдельном окне: exact environment camera, рамка и ползунок
центральной обрезки, «Снимок», проверка кадра, «Найти», «Переснять», файл, закрытие.
Фронтальная камера отклоняется. Нет потока снимков на сервер и автоматического выбора.
Результаты содержат код, название, вид, изображение и пояснение силы сходства.
Все коды одного индексированного изображения сохраняются; страницы по30.
Отбор ограничен48 различными изображениями внутри вида; это не гарантия всех
семантически похожих рисунков в каталоге. Все найденные коды доступны через «Ещё».
Score — косинусное сходство, не вероятность. Подтверждение SIFT не гарантирует
правильность: общие рамки/шаблоны тоже дают совпавшие точки. Проверка человеком обязательна.

Обычная пагинация приостановлена на время окна; фильтры и предыдущая выдача
сохраняются. Закрытие/новый вид/пересъёмка/новый поиск/pagehide/hidden освобождают
камеру и запросы. Счётчики операций защищают от поздних ответов. Баркод, OCR,
mark.html, права и бизнес-модель не переписаны. ОперКонтур и Next UI не изменялись.
В legacy нет fc_ui adapter/check: использована адресная лаборатория; fc_ui NOT_RUN.

## Архитектура

```text
Телефон → HTTPS старого портала:8443 → отдельный loopback gateway:18983
        → TLS/HMAC → Windows host ОперКонтура 192.168.137.21:9443
        → отдельный прогретый compute process → metadata → карточки
```

Ни шлюз, ни модуль не импортируют legacy main, не открывают бизнес-БД и не запускают
его lifespan/миграции/планировщик. Шлюз проверяет текущую cookie через фиксированный
локальный /api/auth/profile, требует активного сотрудника и точный Origin для POST.
Cookie не передаётся модулю. Межсервисный HMAC связывает method/path/query/body,
subject, timestamp и одноразовый nonce; проверяется TLS chain/hostname. Секреты
индивидуальны для этой службы, вне Git; никакого verify=False или CORS для телефона.

API1: GET capabilities; POST search?product_type=... с raw JPEG/PNG/WebP;
GET results?cursor=...&offset=... . Курсор привязан к subject, живёт90с, только
metadata в RAM, максимум32 набора. Клиент не задаёт путь/URL/namespace/модель.
2MiB на тело,12MP, минимальная сторона32px, decode с EXIF, очередью не более3,
один вычислитель, дедлайн7с вычислительного запроса, UI abort8с. Непрочитанный
upload ограничен3с. Сломанный/зависший child завершается и прогревается заново;
IPC не блокирует event loop. Circuit breaker шлюза:3 отказа, пауза15с.
На Windows группа сервиса ограничена2GiB/10% CPU, child1.5GiB; PyTorch2 threads,
OpenCV1. Лимиты относятся только к новому процессу и наследуемым children.
На Linux для compute дополнительно нужен cgroup; Linux compute не принимался.

## Модель и данные

DINOv2 ViT-S/14,384 измерения, CPU; safetensors, local_files_only, без pickle весов,
torch.hub, CDN или runtime download. Конкретные revision/SHA256 — model-manifest.json.
Порядок: точное косинусное ранжирование в выбранном виде; SIFT/RANSAC — evidence.
Геометрический приоритет в ранжировании отклонён после полного benchmark:
общие рамки вытесняли правильные картинки. Preprocessing обеих сторон одинаков:
EXIF/RGB, letterbox224, фиксированная нормализация; версия vs1-dino224-sift256.
Ranking version cosine-sift-evidence-1 не меняет совместимость векторов.

Индексатор принимает только whitelist code/product_type/name/fandom и CODE.jpg.
Экспортёр export_timetracker.py делает явный SET TRANSACTION READ ONLY и rollback;
не является частью HTTP runtime. Источник read-only, зеркало только JPEG500.
SHA256 на сервере и локально совпали для11990 файлов/575386284 байт;416 форм
размеров, длинная сторона500.12542 JPEG в папке500;552 не связаны с товарами.
Все11990 товарных изображений декодируются, пропусков0,11989 уникальных file hashes.
Каталоги продуктов двух систем не объединялись: TimeTracker11990, ОперКонтур имеет
свой каталог и идентификаторы. Рабочие фото/метаданные/индекс не публикуются в Git.

Производные признаки кешируются по SHA256+preprocessing version. Кеш и current.json
пишутся атомарно, .npy читаются без pickle. Manifest проверяет модель/размерность/файлы.
Новый индекс прогревается в spare process, затем меняется под короткой блокировкой;
до готовности служба читает старый. Неверный pointer сохраняет прежнюю выдачу.
После отказа одного pointer автоматических бесконечных повторов нет: нужен новый
валидный pointer/поколение. Предыдущее поколение не удаляется, откат такой же тёплый.
Каталог обновляется отдельным разрешённым read-only export/rebuild, не по каждому
запросу. Индекс является снимком: изменения товаров после экспорта требуют обновления.

## Лицензии и автономная поставка

[DINOv2 model card](https://github.com/facebookresearch/dinov2/blob/main/MODEL_CARD.md),
[закреплённые веса](https://huggingface.co/facebook/dinov2-small/tree/ed25f3a31f01632728cabb09d1542f84ab7b0056):
Apache2.0. Transformers — Apache2.0, PyTorch — BSD3, OpenCV — Apache2.0.
Тексты/состав лицензий остальных wheel включены в поставку; THIRD_PARTY.json
сохраняет metadata и ссылки внутри wheels, включая bundled third-party notices.
Две отдельные hash-locked поставки: Windows CPython3.12 worker/tests и Linux
CPython3.11 gateway. Gateway не получает ML stack. Root requirements.txt не менялся.
Проверена новая установка Windows --no-index --require-hashes, затем cold start
с запретом внешнего connect/DNS и файловых записей, включая spawned child.
Включён переносимый CPython3.12.14 standard runtime с PSF LICENSE; установка
или регистрация системного Python не требуется. Linux installation/rehearsal NOT_RUN.
Демо распаковывать в короткий путь (например D:\VS01): длинные пути Windows
мешают установке C++ headers из CPU wheel PyTorch. Launcher проверяет это до установки.

## Проверки и измерения

Подробная квитанция с SHA и числами входит в локальный пакет RESULTS.json.
Hardware: Windows i9-13900KF,24 cores/32 logical,32GiB; CPU-only. Полный индекс11990.
Первое сравнение,100 синтетических перспектив/яркости/blur: SIFT recall@5=91%,
p95=2373мс; DINO100%,195мс; геометрия-first hybrid95%,320мс. Это не фотографии.
После выбора cosine rank другая100-картинная синтетическая выборка (offset50,
не пересекается с первой, более сильные затемнение/blur): recall@5=97%, p95=276мс.
30 синтетических отрицательных:25 none,5 weak,0 geometry-first suggestions.
Реальная held-out приёмка≥100 телефонных кадров и≥30 неизвестных НЕ выполнена.

Локальная API-цепочка с session stub и проверенным TLS, без внешней сети/записей:
100 warm: p50=363мс,p95=605мс,max1164мс;120 запросов/3 пользователя:p95=1300мс.
Повтор120/3 без упаковки:p95=1037мс,max1281мс. Cold ready3.87с, RSS группы max742MiB,
средний CPU6.51% host. После ещё240 запросов RSS≈761MiB; длительный soak не выполнен.
Это не телефонный e2e: capture/реальная LAN до gateway/
реальная сессия/отрисовка телефона ещё NOT_RUN.
100 безопасных GET каждого приложения: baseline p95 портал41.15мс,
ОперКонтур57.09мс; под3 users портал28.80мс, ОперКонтур143.37мс (+86.28мс).
Допуск max(10%,100мс) соблюдён. Уменьшение задержки портала не считается эффектом
оптимизации; системный фон не изолирован. Первый прогон с подготовкой пакета
сохранён отдельно, не скрыт. Долгий soak/нагрузка реальными сотрудниками NOT_RUN.

10 Python isolated tests PASS;12 resolver PASS;23 camera browser PASS;
34 layout PASS;13 pagination PASS. Photo browser: rear-only, mandatory type,
explicit upload/crop/file,55+ duplicate codes/pages, portrait/landscape, stale,
cancel/pagehide/retake PASS (Edge/Chromium fake media). Android/Яндекс/iPhone/
реальное разрешение камеры/фокус/блики/кривые поверхности NOT_RUN.
Fault lab:3 accepted+1 busy, subject isolation, crash recovery≈3.2с,
hung request≈7.1с, без orphan compute; verified TLS и offline guard PASS.
Index live switch/broken pointer/rollback:43 запроса, все200. Это SYNTHETIC.

## Privacy: открытый блокирующий пункт

В коде RAM-only raw body, нет UploadFile/multipart, temp query files, query logs,
БД, persistent browser storage или response cache. Python audit запрещал записи
по всему пути gateway+child во время cold/search/fault тестов. Anonymous pipes и
NUL sink не являются сохранением снимка. Веса и каталог только читаются.

Но ОС Windows использует pagefile (на проверке4864MiB, занято1099MiB).
**Гарантии, что память снимка не попадёт в OS-managed paging/diagnostic dumps,
нет.** Python audit этого не доказывает. Не отключались pagefile/WER глобально.
До production требуется либо подтверждённая изоляция без swap/dumps для этой
службы, либо отдельное явное разрешение владельца на точное исключение:
возможные OS-managed страницы памяти в pagefile при отсутствии сохранения
снимков приложением; согласовать retention/шифрование/backup и WER policy.
Без одного из этих решений production-запуск заблокирован. Также ещё не выполнена
проверка spool на настоящем Nginx; snippet исключает buffering и ограничивает
body2MiB, но production rehearsal/проверка tmpfs обязательны.

## Предлагаемый план внедрения — требуется отдельное согласование

1. Зафиксировать main SHA, сервер clean/HEAD, существующие PID/контейнеры/config hashes.
   Сохранить конфигурации/индексный pointer, проверить полный штатный backup по
   регламентам владельца, не читать секреты в отчёт. Проверить актуальные AGENTS
   обеих систем и свободный9443 на192.168.137.21. Текущий ОперКонтур dirty/ahead
   сохраняется; его репозиторий и runtime не переключать.
2. Закрыть privacy-блок выше. Репетиция с точным Nginx, tmpfs для всех его temp
   paths, core dumps off и без внешнего egress с сохранённой LAN. Самовольных
   изменений firewall/DNS/pagefile/WER/роутера нет.
3. На Windows отдельный private root D:\AI\VisualSearch с release/<SHA>, runtime,
   model RO, index generations RO, source JPEG500 RO/управляемое зеркало.
   Отдельная ограниченная учётная запись, ACL; межсервисный ключ не использовать
   от старой image-sync интеграции. TLS SAN192.168.137.21/согласованное имя,
   доверенный private CA на gateway, строгая проверка. Закрытый9443 разрешить
   только от192.168.137.105; не публиковать inference в интернет/всю LAN.
4. Включить только новую скрытую службу compute с2GiB/10% CPU, child1.5GiB;
   health/ready и проверка полного индекса до маршрутизации. Основной ОперКонтур,
   его HTTP/БД/REAL_MASTER/ACL/фоновые задачи не перезапускать.
5. На старом Linux выделенный gateway Python3.11,1 process/3 admission,
   loopback18983, лимиты1 CPU/256MiB, read-only code/config/CA, core0/tmpfs.
   Код брать из origin/main в отдельный release root вне watched legacy tree.
   Рекомендуется отдельный контейнер из проверенного локального Python3.11 image,
   --network host, bind127.0.0.1, cap-drop/no-new-privileges/read-only; точный image
   digest и Linux rehearsal ещё необходимо зафиксировать. БД/env legacy не монтировать.
6. В действующий HTTPS server добавить только deploy/visual-search.nginx.conf.example,
   nginx -t и согласованный reload proxy. Сохранить root302, timelog proxy_redirect,
   сертификат и старый HTTP. Флаг gateway enabled=false до защищённого smoke.
7. Отдельное согласованное окно для ff-update рабочего TimeTracker из main и UI.
   В репозитории появились .py, а legacy запущен --reload: Git pull может
   перезапустить app worker и его lifespan. Поэтому **не обещается static-only
   установка без restart** и нельзя сейчас делать pull на production bind mount.
   Заранее проверить read-only наличие startup admin/default settings, сохранить
   PID и согласовать контролируемый reload worker. Docker restart/compose up не
   выполнять автоматически: CMD запускает migrate.py. Если требуется менять CMD/
   lifecycle, это отдельное решение плана. Без разрешения на этот риск UI не ставить.
8. Безопасные GET/auth/error smoke, RAM/spool/offline/impact проверки обеих машин;
   включить enabled=true, обновить HTML-кеш браузера. Телефонная приёмка в HTTPS:
   Android Chrome/Яндекс и iPhone Safari, затем≥100 labelled фото/≥30 negatives,
   отдельные tuning/held-out; e2e n100 и3 users. При ухудшении сразу выключить флаг.

## Откат

Первое действие — enabled=false/остановка только нового gateway: обычные ручной/
barcode/OCR пути остаются. Удалить только новый Nginx location из сохранённого
конфига, nginx -t, согласованный reload. Выключить только новую Windows-службу
и её адресное firewall rule, не менять ОперКонтур. Для индекса атомарно вернуть
предыдущий current.json; тёплый rollback проверен в lab. UI/runtime изменения
отменять новым адресным коммитом в актуальном main после сверки соавторов;
не reset всего main. Сверить PID/HEAD/config hashes/безопасные GET и данные.
Данные, каталог, .env, volumes и старые поколения не удаляются. Production-откат
ещё NOT_RUN; локальный отказ/индексный rollback PASS.
