import os
import psycopg2
from urllib.parse import urlparse


# Функция для подключения к базе данных
def get_db_connection():
    # Получаем URL базы данных из переменной окружения
    db_url = os.environ.get('DATABASE_URL')
    if not db_url:
        raise ValueError("DATABASE_URL не задана в переменных окружения.")

    # Парсим URL, чтобы получить параметры подключения
    result = urlparse(db_url)

    # Устанавливаем соединение с базой данных
    return psycopg2.connect(
        dbname=result.path[1:],  # убираем начальный слэш
        user=result.username,
        password=result.password,
        host=result.hostname,
        port=result.port
    )


# Функция для получения и вывода списка зарегистрированных пользователей
def get_registered_users():
    conn = None
    try:
        # Подключаемся к базе данных
        conn = get_db_connection()
        cur = conn.cursor()

        # SQL-запрос для получения списка пользователей
        cur.execute("SELECT username, email, public_key FROM users")

        # Получаем все результаты запроса
        users = cur.fetchall()

        # Закрываем курсор
        cur.close()

        # Выводим список пользователей
        for user in users:
            print(f"Username: {user[0]}, Email: {user[1]}, Public Key: {user[2]}")

    except Exception as e:
        print(f"Ошибка при получении пользователей: {str(e)}")

    finally:
        # Закрываем соединение с базой данных
        if conn:
            conn.close()


# Запуск основной функции, если скрипт запускается как отдельная программа
if __name__ == "__main__":
    get_registered_users()
