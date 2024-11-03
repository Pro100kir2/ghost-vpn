import os
import psycopg2
from urllib.parse import urlparse

# Обновленная функция подключения
def get_db_connection():
    # Читаем переменную окружения
    db_url = os.environ.get("DATABASE_URL")

    # Парсим URL для извлечения компонентов
    result = urlparse(db_url)

    # Извлекаем параметры для подключения
    db_name = result.path[1:]
    db_user = result.username
    db_password = result.password
    db_host = result.hostname
    db_port = result.port

    # Подключаемся к базе данных
    return psycopg2.connect(
        dbname=db_name,
        user=db_user,
        password=db_password,
        host=db_host,
        port=db_port
    )

