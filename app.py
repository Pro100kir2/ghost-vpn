from flask import Flask, request, render_template, jsonify
import psycopg2
import os
import random
import string
from urllib.parse import urlparse

app = Flask(__name__)

# Функция для генерации ключей
def generate_keys():
    public_key = ''.join(random.choices(string.ascii_lowercase + string.digits, k=12))
    private_key = ''.join(random.choices(string.ascii_lowercase + string.digits, k=24))
    return public_key, private_key

# Функция для подключения к базе данных с использованием DATABASE_URL из переменных окружения
def get_db_connection():
    db_url = os.environ.get('DATABASE_URL')  # Получаем URL базы данных из переменных окружения
    result = urlparse(db_url)

    return psycopg2.connect(
        dbname=result.path[1:],
        user=result.username,
        password=result.password,
        host=result.hostname,
        port=result.port
    )

# Главная страница
@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')

# Страница регистрации
@app.route('/registration', methods=['GET'])
def registration_page():
    return render_template('registration.html')

# Обработчик регистрации
@app.route('/register', methods=['POST'])
def register():
    data = request.form
    username = data.get('username')
    email = data.get('email')

    public_key, private_key = generate_keys()

    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Проверка на уникальность имени пользователя
        if is_username_taken(cur, username):
            return jsonify({'error': 'Извините, но пользователь с таким именем уже есть, выберите другой.'}), 400

        # Вставка нового пользователя
        cur.execute('INSERT INTO users (username, email, public_key, private_key) VALUES (%s, %s, %s, %s)',
                    (username, email, public_key, private_key))
        conn.commit()  # Подтверждаем изменения
        cur.close()

        # Перенаправление на страницу с успешной регистрацией
        return render_template('new_user.html', message='Поздравляем с успешной регистрацией!', public_key=public_key, private_key=private_key)

    except Exception as e:
        # Обработка ошибок
        if conn:
            conn.rollback()
        return jsonify({'error': f'Ошибка при добавлении пользователя: {str(e)}'}), 400
    finally:
        if conn:
            conn.close()

# Функция для проверки, занято ли имя пользователя
def is_username_taken(cursor, username):
    cursor.execute("SELECT COUNT(*) FROM users WHERE username = %s", (username,))
    count = cursor.fetchone()[0]
    return count > 0  # Возвращает True, если имя пользователя занято

# Обработчик входа
@app.route('/login', methods=['GET', 'POST'])
def login_page():
    if request.method == 'POST':
        username = request.form['username']
        public_key = request.form['public_key']

        conn = None
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("SELECT * FROM users WHERE username = %s AND public_key = %s", (username, public_key))
            user = cur.fetchone()

            if user:
                return jsonify({'message': 'Вход успешен!'}), 200
            else:
                return jsonify({'error': 'Неверное имя пользователя или публичный ключ!'}), 400

        except Exception as e:
            return jsonify({'error': f'Ошибка при входе: {str(e)}'}), 400
        finally:
            if conn:
                conn.close()

    return render_template('login.html')

if __name__ == '__main__':
    app.run(debug=True)
