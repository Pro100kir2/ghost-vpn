import os
import psycopg2
from urllib.parse import urlparse


# Функция для подключения к базе данных
def get_db_connection():
    db_url = os.environ.get('DATABASE_URL')
    if not db_url:
        raise ValueError("DATABASE_URL не задана в переменных окружения.")

    result = urlparse(db_url)
    return psycopg2.connect(
        dbname=result.path[1:],
        user=result.username,
        password=result.password,
        host=result.hostname,
        port=result.port
    )


# Функция для преобразования времени из секунд в формат ДД:ЧЧ:ММ
def format_time(seconds):
    days = seconds // (24 * 3600)
    hours = (seconds % (24 * 3600)) // 3600
    minutes = (seconds % 3600) // 60
    return f"{days:02}:{hours:02}:{minutes:02}"


# Обновляем функцию get_registered_users
def get_registered_users():
    conn = None
    try:
        # Подключаемся к базе данных
        conn = get_db_connection()
        cur = conn.cursor()

        # SQL-запрос для получения списка пользователей
        cur.execute("""
            SELECT 
                id, username, telegram_name, public_key, private_key, time, status, trial_used
            FROM users
        """)

        # Получаем все результаты запроса
        users = cur.fetchall()

        # Закрываем курсор
        cur.close()

        if users:
            for user in users:
                # Преобразуем дни из базы данных в секунды
                time_in_seconds = user[5] * 86400  # Переводим дни в секунды
                time_formatted = format_time(time_in_seconds)  # Преобразуем время в формат ДД:ЧЧ:ММ
                print(f"""
                ID: {user[0]}
                Username: {user[1]}
                Telegram Name: {user[2] or "N/A"}
                Public Key: {user[3] or "N/A"}
                Private Key: {user[4] or "N/A"}
                Time (remaining): {time_formatted}
                Status: {user[6]}
                Trial Used: {"Yes" if user[7] else "No"}
                """)
        else:
            print("Таблица пуста, в ней нет пользователей.")

    except Exception as e:
        print(f"Ошибка при получении пользователей: {str(e)}")

    finally:
        # Закрываем соединение с базой данных
        if conn:
            conn.close()


# Запуск основной функции
if __name__ == "__main__":
    get_registered_users()
