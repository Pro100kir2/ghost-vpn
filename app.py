from flask import Flask, request, render_template, redirect, url_for, session, flash
import psycopg2
import os
import random
import string
import uuid
from urllib.parse import urlparse
from functools import wraps
from datetime import datetime, timedelta
from flask_session import Session
import requests

app = Flask(__name__)

# Настройки для Flask-сессии
app.secret_key = os.urandom(24)

# reCAPTCHA ключи
RECAPTCHA_SITE_KEY = "6LcHxYYqAAAAABYAG2B__k_6MIiLBY4yf5_cPym2"  # Публичный ключ
RECAPTCHA_SECRET_KEY = "6LcHxYYqAAAAAFz_b7SB4p52ayqL1ubsg9hWyjgx"  # Секретный ключ

# Генерация публичного и приватного ключей
def generate_keys():
    public_key = ''.join(random.choices(string.ascii_lowercase + string.digits, k=12))
    private_key = ''.join(random.choices(string.ascii_lowercase + string.digits, k=24))
    return public_key, private_key

# Генерация уникального ID
def generate_unique_id():
    return str(uuid.uuid4())

# Соединение с базой данных
def get_db_connection():
    db_url = os.environ.get('DATABASE_URL')
    result = urlparse(db_url)
    return psycopg2.connect(
        dbname=result.path[1:],
        user=result.username,
        password=result.password,
        host=result.hostname,
        port=result.port
    )

# Проверка reCAPTCHA
def verify_recaptcha(response_token):
    url = "https://www.google.com/recaptcha/api/siteverify"
    data = {'secret': RECAPTCHA_SECRET_KEY, 'response': response_token}
    response = requests.post(url, data=data)
    result = response.json()
    return result.get('success', False)

# Проверка уникальности имени пользователя
def is_username_taken(cursor, username):
    cursor.execute("SELECT COUNT(*) FROM users WHERE username = %s", (username,))
    count = cursor.fetchone()[0]
    return count > 0

# Декоратор для защиты маршрутов
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Доступ запрещен! Пожалуйста, авторизуйтесь.", "error")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Маршрут для главной страницы
@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')

# Маршрут для страницы регистрации
@app.route('/registration', methods=['GET'])
def registration_page():
    return render_template('registration.html', recaptcha_site_key=RECAPTCHA_SITE_KEY)

# Обработка регистрации
@app.route('/register', methods=['POST'])
def register():
    data = request.form
    username = data.get('username')
    email = data.get('email')
    recaptcha_response = data.get('g-recaptcha-response')

    # Проверяем reCAPTCHA
    if not verify_recaptcha(recaptcha_response):
        flash('Пожалуйста, подтвердите, что вы не робот.', 'error')
        return redirect(url_for('registration_page'))

    public_key, private_key = generate_keys()
    unique_id = generate_unique_id()

    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        if is_username_taken(cur, username):
            flash('Имя пользователя уже занято, выберите другое.', 'username_taken')
            return render_template('registration.html', username=username, email=email, recaptcha_site_key=RECAPTCHA_SITE_KEY)

        cur.execute('INSERT INTO users (id, username, email, public_key, private_key, time, trial_used) VALUES (%s, %s, %s, %s, %s, %s, %s)',
                    (unique_id, username, email, public_key, private_key, 0, False))
        conn.commit()

        flash('Регистрация успешна! Проверьте почту для подтверждения.', 'success')
        return redirect(url_for('login'))
    except Exception as e:
        if conn:
            conn.rollback()
        flash(f'Ошибка при регистрации: {str(e)}', 'error')
        return render_template('registration.html', username=username, email=email, recaptcha_site_key=RECAPTCHA_SITE_KEY)
    finally:
        if conn:
            conn.close()

# Маршрут для страницы входа
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        public_key = request.form['public_key']

        conn = None
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("SELECT id FROM users WHERE username = %s AND public_key = %s", (username, public_key))
            user = cur.fetchone()

            if user:
                session['user_id'] = user[0]
                return redirect(url_for('home'))
            else:
                flash("Неверное имя пользователя или публичный ключ!", "error")
                return redirect(url_for('login'))
        except Exception as e:
            flash(f'Ошибка при входе: {str(e)}', "error")
            return redirect(url_for('login'))
        finally:
            if conn:
                conn.close()
    return render_template('login.html')

# Заголовки для предотвращения кэширования
@app.after_request
def add_no_cache_headers(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

if __name__ == '__main__':
    app.run(debug=True)