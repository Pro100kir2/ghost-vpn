import psycopg2

# Настройки подключения к базе данных
DB_NAME = 'ghostvpn'
DB_USER = 'pro100kir2'
DB_PASSWORD = '1234'
DB_HOST = 'localhost'
DB_PORT = '5432'  # Порт PostgreSQL


def clear_users_table():
    try:
        # Подключение к базе данных
        connection = psycopg2.connect(
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            host=DB_HOST,
            port=DB_PORT
        )
        cursor = connection.cursor()

        # Команда TRUNCATE для очистки таблицы
        cursor.execute("TRUNCATE TABLE users RESTART IDENTITY;")
        connection.commit()  # Подтверждаем изменения
        print("Таблица users успешно очищена.")

    except Exception as e:
        print(f"Ошибка при очистке таблицы: {str(e)}")

    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


# Вызов функции
clear_users_table()
