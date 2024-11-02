import psycopg2
from psycopg2.extras import RealDictCursor  # Удобный способ получать результаты как словари JSON


# Настройка подключения к базе данных PostgreSQL
def get_db_connection():
    return psycopg2.connect(
        dbname="ghostvpn",
        user="pro100kir2",
        password="1234",
        host="localhost",
        port="5432"  # Порт PostgreSQL
    )

# Функция для получения списка всех зарегистрированных пользователей
def get_all_users():
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # Выполняем SQL-запрос для получения всех данных из таблицы users
        cur.execute("SELECT id, username, email, public_key , private_key FROM users;")
        users = cur.fetchall()  # Извлекаем все записи

        # Выводим каждого пользователя
        if users:
            for user in users:
                print(f"ID: {user['id']}, Name: {user['username']}, Password: {user['public_key']}, Gmail: {user['email']}")
        else:
            print("Таблица 'users' пуста.")

        cur.close()
    except Exception as e:
        print(f"Ошибка при выполнении запроса: {e}")
    finally:
        if conn:
            conn.close()


# Вызов функции для отображения пользователей
if __name__ == '__main__':
    get_all_users()
