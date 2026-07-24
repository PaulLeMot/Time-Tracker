import os
import time
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

# Загружаем переменные из .env
load_dotenv()

BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")   # адрес вашего приложения
DATABASE_URL = os.getenv("DATABASE_URL")                    # postgresql+asyncpg://...

# Извлекаем параметры подключения из DATABASE_URL
def parse_db_url(url):
    # Простой парсинг для формата: postgresql+asyncpg://user:pass@host:port/dbname
    import re
    match = re.match(r'postgresql\+asyncpg://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)', url)
    if not match:
        raise ValueError("Не удалось распарсить DATABASE_URL")
    user, password, host, port, dbname = match.groups()
    return user, password, host, int(port), dbname

DB_USER, DB_PASS, DB_HOST, DB_PORT, DB_NAME = parse_db_url(DATABASE_URL)
if DB_HOST == 'db':
    DB_HOST = 'localhost'
def get_active_employees(limit=30):
    """Получить активных сотрудников из БД (username, password, id)"""
    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASS,
        dbname=DB_NAME
    )
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("""
        SELECT id, username, password
        FROM employees
        WHERE is_active = 1
        ORDER BY id
        LIMIT %s
    """, (limit,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [(row['username'], row['password']) for row in rows]

# === Настройки теста ===
CYCLES = 100                # количество циклов break_start → break_end
SLEEP_BETWEEN_ACTIONS = 1   # пауза между действиями (сек)
MAX_WORKERS = 10            # одновременно работающих сотрудников (подберите под свой ПК)


def login(username, password):
    session = requests.Session()
    resp = session.post(
        f"{BASE_URL}/api/auth/login",
        json={"username": username, "password": password}
    )
    if resp.status_code != 200:
        raise Exception(f"Ошибка логина {username}: {resp.text}")
    return session


def get_user_id(session):
    resp = session.get(f"{BASE_URL}/api/auth/profile")
    if resp.status_code != 200:
        raise Exception("Не удалось получить профиль")
    return resp.json()["id"]


def perform_action(session, user_id, action):
    resp = session.post(
        f"{BASE_URL}/api/timelog",
        json={"user_id": user_id, "action": action}
    )
    if resp.status_code != 200:
        raise Exception(f"Ошибка при {action}: {resp.text}")


def worker(username, password):
    try:
        session = login(username, password)
        user_id = get_user_id(session)
        print(f"[{username}] Начало работы (ID={user_id})")

        # Начать день
        perform_action(session, user_id, "start")
        time.sleep(SLEEP_BETWEEN_ACTIONS)

        # Цикл перерывов
        for i in range(CYCLES):
            perform_action(session, user_id, "break_start")
            time.sleep(SLEEP_BETWEEN_ACTIONS)

            perform_action(session, user_id, "break_end")
            time.sleep(SLEEP_BETWEEN_ACTIONS)

        # Завершить день
        perform_action(session, user_id, "end")
        print(f"[{username}] Завершён")

    except Exception as e:
        print(f"[{username}] ОШИБКА: {e}")


def main():
    print("Получение списка активных сотрудников из БД...")
    users = get_active_employees(limit=30)
    if not users:
        print("❌ В базе нет активных сотрудников!")
        return

    print(f"Найдено сотрудников: {len(users)}")
    print(f"Запуск теста: {CYCLES} циклов перерывов на каждого, пауза {SLEEP_BETWEEN_ACTIONS}с")
    print(f"Одновременных потоков: {MAX_WORKERS}")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(worker, u, p) for u, p in users]
        for future in as_completed(futures):
            future.result()  # пробрасываем исключения, если были

    print("✅ Тест завершён.")


if __name__ == "__main__":
    main()