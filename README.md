# ⏱️ TimeTracker — СКУД-система для малого бизнеса

Система учёта рабочего времени для малого предприятия: сотрудники отмечают приход и уход по QR-коду, руководство получает готовую отчётность без бумажных табелей.

[![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-336791?style=for-the-badge&logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Docker](https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://www.docker.com/)
[![JavaScript](https://img.shields.io/badge/JavaScript-F7DF1E?style=for-the-badge&logo=javascript&logoColor=black)](https://developer.mozilla.org/en-US/docs/Web/JavaScript)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](https://opensource.org/licenses/MIT)

---

## 📋 О проекте

**TimeTracker** — это система учёта рабочего времени (СКУД) для малого предприятия. Проект разработан по заказу реального бизнеса и уже **более месяца используется 30 сотрудниками ежедневно**.

Внедрение системы позволило:
- автоматизировать учёт прихода и ухода сотрудников;
- упростить формирование отчётности для руководства;
- исключить человеческий фактор при заполнении табелей.

> 💡 Проект полностью Open Source. Код доступен для изучения, использования и доработки.

---

## ✨ Функциональность

- **Отметка прихода/ухода** — сотрудники сканируют QR-код на брелке (или в приложении) для отметки времени.
- **Личный кабинет** — каждый сотрудник видит свою историю отметок.
- **Административная панель** — управление сотрудниками, просмотр отчётов, экспорт данных.
- **Обновления в реальном времени** — интерфейс обновляется через **Server-Sent Events (SSE)** без перезагрузки страницы.
- **Отчётность** — формирование табелей за любой период (день, неделя, месяц).
- **Разграничение прав** — администратор, руководитель, сотрудник.

---

## 🛠️ Технологический стек

| Компонент | Технология |
|-----------|------------|
| **Бэкенд** | FastAPI (Python) |
| **База данных** | PostgreSQL |
| **Фронтенд** | HTML / CSS / JavaScript (без фреймворков) |
| **Деплой** | Docker + Docker Compose |
| **ОС** | Развёрнуто внутри WSL (Windows Subsystem for Linux) |
| **Скрипты автоматизации** | Bash |
| **Обновления в реальном времени** | SSE (Server-Sent Events) |

---

## 🚀 Запуск проекта

### 1. Клонируйте репозиторий

```bash
git clone https://github.com/PaulLeMot/Time-Tracker.git
cd Time-Tracker
```

### 2. Настройте переменные окружения

Создайте файл `.env` на основе примера:

```bash
cp .env.example .env
```

Отредактируйте `.env`, указав свои пароли и часовой пояс:

```env
POSTGRES_USER=admin
POSTGRES_PASSWORD=your_secure_db_password
POSTGRES_DB=timetracker
DATABASE_URL=postgresql+asyncpg://admin:your_secure_db_password@db:5432/timetracker
ADMIN_PASSWORD=your_secure_admin_password
MONITOR_PASSWORD=your_secure_monitor_password
```

> ⚠️ **Важно:** замените все пароли на собственные, сложные.

### 3. Запустите приложение в Docker

```bash
docker-compose up -d
```

Приложение будет доступно по адресу: [http://localhost:8000](http://localhost:8000)

### 4. Войдите в систему

- **Администратор:** логин `admin`, пароль из `.env` (`ADMIN_PASSWORD`)
- **Монитор:** логин `monitor`, пароль из `.env` (`MONITOR_PASSWORD`)

---

## 🧪 Мои тесты и QA-процесс

Этот проект — не только разработка, но и полный цикл **ручного тестирования**, который я провёл как единственный QA-инженер:

- ✅ Составил **чек-листы** для всех пользовательских сценариев.
- ✅ Провёл **функциональное тестирование** всех модулей.
- ✅ Протестировал **граничные случаи**: некорректный ввод, дублирование отметок, большая нагрузка.
- ✅ Выполнил **регрессионное тестирование** после каждого исправления.
- ✅ Анализировал **логи ошибок** для поиска root-причин багов.
- ✅ Оптимизировал **SQL-запросы** (добавление индексов) для ускорения работы с базой.
- ✅ Оформил **баг-репорты** с шагами воспроизведения и скриншотами.

> 📌 Результат: стабильная работа системы с 30+ сотрудниками ежедневно без сбоев.

---

## 💾 Восстановление базы данных из дампа

Если вам нужно восстановить базу из резервной копии:

```bash
docker exec -i timetrek-db-1 psql -U admin timetracker < backups/filename.sql
```

---

## 🧭 Навигация по репозиторию

```
Time-Tracker/
├── app/                  # Бэкенд (FastAPI)
├── frontend/             # Фронтенд (HTML/CSS/JS)
├── docker-compose.yml    # Оркестрация контейнеров
├── .env.example          # Шаблон переменных окружения
├── backups/              # Дампы базы данных
└── README.md             # Этот файл
```

---

## 📝 Планы по развитию

- [ ] Telegram-бот для уведомлений об опозданиях.
- [ ] Экспорт отчётов в Excel/PDF.
- [ ] Поддержка нескольких предприятий (мультитенантность).
- [ ] Автоматизация тестирования (Pytest + Selenium).

---

## 🤝 Контакты

Автор: **Кузнецов Дмитрий**
Email: [paullemot@proton.me](mailto:paullemot@proton.me)
GitHub: [PaulLeMot](https://github.com/PaulLeMot)

По вопросам сотрудничества, стажировок или предложений по проекту — пишите!

---

## 📄 Лицензия

Этот проект распространяется под лицензией **MIT**. Подробнее — в файле [LICENSE](LICENSE).
