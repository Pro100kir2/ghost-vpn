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
import requests  # для работы с reCAPTCHA

app = Flask(__name__)

# Настройки для Flask-сессии
app.secret_key = os.urandom(24)
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_PERMANENT'] = False
app.config['SESSION_USE_SIGNER'] = True
Session(app)

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

# Декоратор для защиты маршрутов
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Доступ запрещен! Пожалуйста, авторизуйтесь.", "error")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Главная страница
@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')

# Страница регистрации
@app.route('/registration', methods=['GET'])
def registration_page():
    return render_template('registration.html')

# Обработка регистрации
@app.route('/register', methods=['POST'])
def register():
    data = request.form
    username = data.get('username')
    email = data.get('email')
    recaptcha_response = data.get('g-recaptcha-response')  # Получение ответа капчи

    # Проверка reCAPTCHA
    if not recaptcha_response:
        flash('Пожалуйста, подтвердите, что вы не робот.', 'error')
        return render_template('registration.html', username=username, email=email)

    recaptcha_secret = os.getenv('RECAPTCHA_SECRET_KEY', 'your-secret-key-here')
    recaptcha_verify_url = 'https://www.google.com/recaptcha/api/siteverify'

    try:
        response = requests.post(
            recaptcha_verify_url,
            data={'secret': recaptcha_secret, 'response': recaptcha_response}
        )
        result = response.json()
        if not result.get('success'):
            flash('Ошибка валидации reCAPTCHA. Попробуйте снова.', 'error')
            return render_template('registration.html', username=username, email=email)
    except Exception as e:
        flash(f'Ошибка связи с сервером reCAPTCHA: {str(e)}', 'error')
        return render_template('registration.html', username=username, email=email)

    public_key, private_key = generate_keys()
    unique_id = generate_unique_id()

    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        if is_username_taken(cur, username):
            flash('Пользователь с таким именем уже существует.', 'error')
            return render_template('registration.html', username=username, email=email)

        cur.execute('INSERT INTO users (id, username, email, public_key, private_key, time, status, trial_used) '
                    'VALUES (%s, %s, %s, %s, %s, %s, %s, %s)',
                    (unique_id, username, email, public_key, private_key, 30, 'inactive', False))  # Статус и пробный период
        conn.commit()
        cur.close()

        flash('Поздравляем с успешной регистрацией!', 'success')
        return render_template('new_user.html', message='Поздравляем с успешной регистрацией!', public_key=public_key, private_key=private_key)

    except Exception as e:
        if conn:
            conn.rollback()
        flash(f'Ошибка при добавлении пользователя: {str(e)}', 'error')
        return render_template('registration.html', username=username, email=email)
    finally:
        if conn:
            conn.close()

# Проверка, занят ли пользователь
def is_username_taken(cursor, username):
    cursor.execute("SELECT COUNT(*) FROM users WHERE username = %s", (username,))
    return cursor.fetchone()[0] > 0

# Маршрут для входа
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
                session.permanent = True
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

# Маршрут для профиля
@app.route('/my-home-profile')
@login_required
def my_home_profile():
    user_id = session['user_id']

    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT username, time, status, trial_used FROM users WHERE id = %s", (user_id,))
        user = cur.fetchone()

        if user:
            username, time_left, status, trial_used = user
            remaining_time = timedelta(days=time_left) if time_left > 0 else timedelta(days=0)
            time_remaining = f"{remaining_time.days // 30} мес {remaining_time.days % 30} дн" if time_left > 0 else "Подписка завершена"
            status = "Активен" if time_left > 0 else "Неактивен"

            return render_template('my-home-profile.html', username=username, time_remaining=time_remaining, status=status, trial_used=trial_used)
        else:
            flash("Пользователь не найден.", "error")
            return redirect(url_for('profile'))
    except Exception as e:
        flash(f'Ошибка при извлечении данных: {str(e)}', "error")
        return redirect(url_for('profile'))
    finally:
        if conn:
            conn.close()
# Маршрут для выхода
@app.route('/logout')
def logout():
    session.clear()
    flash("Вы успешно вышли из системы", "success")
    return redirect(url_for('index'))

# Маршруты с защитой
@app.route('/home')
@login_required
def home():
    return render_template('home.html')

@app.route('/profile')
@login_required
def profile():
    return render_template('profile.html')

@app.route('/tariff')
@login_required
def tariff():
    return render_template('tariff.html')

@app.route('/setting')
@login_required
def setting():
    return render_template('setting.html')

@app.route('/about')
def about():
    return render_template('about.html')
# Заголовки для предотвращения кэширования
@app.after_request
def add_no_cache_headers(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

if __name__ == '__main__':
    app.run(debug=True)