from flask import Flask, request, render_template, redirect, url_for, session, flash
import psycopg2
import os
import random
import string
import uuid
import requests  # Потребуется для reCAPTCHA и отправки сообщений в Telegram
from functools import wraps
from datetime import timedelta
from urllib.parse import urlparse

app = Flask(__name__)
app.secret_key = 'your_secret_key'

# Настройки для Flask-сессии
app.secret_key = os.urandom(24)

# reCAPTCHA ключи
RECAPTCHA_SITE_KEY = "6LcHxYYqAAAAABYAG2B__k_6MIiLBY4yf5_cPym2"
RECAPTCHA_SECRET_KEY = "6LcHxYYqAAAAAFz_b7SB4p52ayqL1ubsg9hWyjgx"

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
    response = requests.post(url, data=data, timeout=5)
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

def is_telegram_username_taken(cursor, telegram_username):
    cursor.execute('SELECT 1 FROM users WHERE telegram_username = %s', (telegram_username,))
    return cursor.fetchone() is not None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/registration', methods=['GET'])
def registration_page():
    return render_template('registration.html', recaptcha_site_key=RECAPTCHA_SITE_KEY)

# Функция для отправки сообщения через Telegram
def send_telegram_message(telegram_username, message):
    # Получаем токен бота
    bot_token = '7532462167:AAFrEoclnACi8qzPTRvZedM7r06BMYE0ep8'
    chat_id = telegram_username  # Используйте числовой chat_id вместо @username

    url = f'https://api.telegram.org/bot{bot_token}/sendMessage'
    params = {
        'chat_id': chat_id,
        'text': message
    }
    response = requests.post(url, data=params)
    return response.status_code == 200

# Исправленный маршрут регистрации
@app.route('/register', methods=['POST'])
def register():
    data = request.form
    username = data.get('username')
    telegram_username = data.get('telegram_username')
    recaptcha_response = data.get('g-recaptcha-response')

    # Проверка reCAPTCHA
    if not verify_recaptcha(recaptcha_response):
        flash('Пожалуйста, подтвердите, что вы не робот.', 'error')
        return redirect(url_for('registration_page'))

    # Если имя пользователя не начинается с "@", добавляем его
    if telegram_username and not telegram_username.startswith('@'):
        telegram_username = '@' + telegram_username

    # Генерация ключей и уникального ID
    public_key, private_key = generate_keys()
    unique_id = generate_unique_id()
    confirmation_code = ''.join(random.choices(string.digits, k=6))

    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Проверка на занятость имени пользователя
        if is_username_taken(cur, username):
            flash('Имя пользователя уже занято.', 'username_taken')
            return render_template('registration.html', username=username, telegram_username=telegram_username, recaptcha_site_key=RECAPTCHA_SITE_KEY)

        # Проверка на занятость Telegram username
        if is_telegram_username_taken(cur, telegram_username):
            flash('Этот Telegram username уже занят, пожалуйста, выберите другой.', 'telegram_taken')
            return render_template('registration.html', username=username, telegram_username=telegram_username, recaptcha_site_key=RECAPTCHA_SITE_KEY)

        # Вставка нового пользователя в базу данных
        cur.execute('INSERT INTO users (id, username, telegram_username, public_key, private_key, confirmation_code, confirmation_attempts, time, status) '
                    'VALUES (%s, %s, %s, %s, %s, %s, %s, 0, FALSE)',
                    (unique_id, username, telegram_username, public_key, private_key, confirmation_code, 3))
        conn.commit()

        # Отправка кода подтверждения через Telegram
        send_telegram_message(telegram_username, f'Ваш код подтверждения: {confirmation_code}')
        flash('Регистрация успешна! Проверьте Telegram для подтверждения.', 'success')
        return redirect(url_for('confirm_telegram'))
    except Exception as e:
        if conn:
            conn.rollback()
        flash(f'Ошибка при регистрации: {str(e)}', 'error')
        return render_template('registration.html', username=username, telegram_username=telegram_username, recaptcha_site_key=RECAPTCHA_SITE_KEY)
    finally:
        if conn:
            conn.close()
@app.route('/confirm', methods=['POST', 'GET'])
def confirm_telegram():
    if request.method == 'POST':
        code = request.form['confirmation_code']
        conn = None
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("SELECT id, confirmation_attempts FROM users WHERE confirmation_code = %s AND status = FALSE", (code,))
            user = cur.fetchone()

            if user:
                user_id, attempts = user
                cur.execute("UPDATE users SET status = TRUE, confirmation_code = NULL, confirmation_attempts = NULL WHERE id = %s", (user_id,))
                conn.commit()
                session['user_id'] = user_id
                return redirect(url_for('new_user'))
            else:
                cur.execute("UPDATE users SET confirmation_attempts = confirmation_attempts - 1 WHERE confirmation_code = %s AND status = FALSE", (code,))
                conn.commit()
                cur.execute("SELECT confirmation_attempts FROM users WHERE confirmation_code = %s", (code,))
                attempts_left = cur.fetchone()
                if attempts_left and attempts_left[0] <= 0:
                    flash('Код неверный. Попытки закончились.', 'error')
                    return redirect(url_for('registration_page'))
                else:
                    flash('Код неверный. Попробуйте снова.', 'error')
        except Exception as e:
            flash(f'Ошибка подтверждения: {str(e)}', 'error')
        finally:
            if conn:
                conn.close()
    return render_template('confirm_telegram.html')

@app.route('/new-user', methods=['GET'])
@login_required
def new_user():
    return render_template('new_user.html')
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

@app.route('/my-home-profile')
@login_required
def my_home_profile():
    user_id = session['user_id']
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT username, time, status FROM users WHERE id = %s", (user_id,))
        user = cur.fetchone()
        if user:
            username, time_left, status = user
            remaining_time = timedelta(days=time_left) if time_left > 0 else "Подписка завершена"
            status = "Активен" if time_left > 0 else "Неактивен"
            return render_template('my_home_profile.html', username=username, time_remaining=remaining_time, status=status)
        else:
            flash("Пользователь не найден.", "error")
            return redirect(url_for('profile'))
    except Exception as e:
        flash(f'Ошибка при загрузке профиля: {str(e)}', "error")
        return redirect(url_for('profile'))
    finally:
        if conn:
            conn.close()

@app.route('/tariff')
def tariff():
    return render_template('tariff.html')

@app.route('/profile')
@login_required
def profile():
    return render_template('profile.html')

@app.route('/setting')
@login_required
def setting():
    return render_template('setting.html')

@app.route('/about')
def about():
    return render_template('about.html')
@app.route('/privacy-policy')
def privacy_policy():
    return render_template('privacy-policy.html')
# Заголовки для предотвращения кэширования
@app.after_request
def add_no_cache_headers(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

if __name__ == '__main__':
    app.run(debug=True)
