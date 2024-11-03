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


# Функция для удаления пользователя по ID
def delete_user_by_id(user_id):
    conn = None
    try:
        # Подключаемся к базе данных
        conn = get_db_connection()
        cur = conn.cursor()

        # Удаляем запись по ID
        cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
        conn.commit()  # Подтверждаем изменения
        cur.close()

        print(f"Пользователь с ID {user_id} был успешно удален.")

    except Exception as e:
        print(f"Ошибка при удалении пользователя: {str(e)}")

    finally:
        if conn:
            conn.close()


# Запросить ID для удаления
if __name__ == "__main__":
    user_id = input("Введите ID пользователя для удаления: ")
    delete_user_by_id(user_id)
