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
from telegram import Bot

app = Flask(__name__)


# Функция для генерации случайного кода
def generate_confirmation_code():
    return str(random.randint(100000, 999999))


# Функция для отправки кода в Telegram
def send_confirmation_telegram(user_telegram_id, confirmation_code):
    bot = Bot(token=os.environ.get('TELEGRAM_BOT_TOKEN'))  # Токен вашего бота
    bot.send_message(chat_id=user_telegram_id, text=f"Ваш код подтверждения: {confirmation_code}")


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
    telegram_id = data.get('telegram_id')  # ID из Telegram
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
            return render_template('registration.html', username=username, email=email,
                                   recaptcha_site_key=RECAPTCHA_SITE_KEY)

        # Сохраняем пользователя, но не подтверждаем его
        cur.execute(
            'INSERT INTO users (id, username, email, public_key, private_key, time, trial_used) VALUES (%s, %s, %s, %s, %s, %s, %s )',
            (unique_id, username, email, public_key, private_key, 0, False, telegram_id))
        conn.commit()

        # Генерация и отправка кода в Telegram
        confirmation_code = generate_confirmation_code()
        session['confirmation_code'] = confirmation_code  # Сохраняем код в сессии
        send_confirmation_telegram(telegram_id, confirmation_code)

        flash('Регистрация успешна! Пожалуйста, введите код подтверждения, отправленный на ваш Telegram.', 'success')
        return redirect(url_for('confirm_telegram_page', user_id=unique_id))
    except Exception as e:
        if conn:
            conn.rollback()
        flash(f'Ошибка при регистрации: {str(e)}', 'error')
        return render_template('registration.html', username=username, email=email,
                               recaptcha_site_key=RECAPTCHA_SITE_KEY)
    finally:
        if conn:
            conn.close()


# Страница ввода кода подтверждения
@app.route('/confirm_telegram/<user_id>', methods=['GET', 'POST'])
def confirm_telegram_page(user_id):
    if request.method == 'POST':
        confirmation_code = request.form['confirmation_code']

        # Проверяем код из сессии
        if 'confirmation_code' not in session:
            flash('Сессия истекла, пожалуйста, попробуйте снова.', 'error')
            return redirect(url_for('registration_page'))

        stored_code = session['confirmation_code']
        if confirmation_code == stored_code:
            session.pop('confirmation_code')  # Убираем код из сессии после подтверждения
            flash('Ваш аккаунт успешно подтвержден!', 'success')
            return redirect(url_for('login'))
        else:
            flash('Неверный код подтверждения!', 'error')
            return render_template('confirm_telegram.html', user_id=user_id)

    return render_template('confirm_telegram.html', user_id=user_id)


# Страница входа
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


# Страница домашнего профиля
@app.route('/home', methods=['GET'])
@login_required
def home():
    return render_template('home.html')


# Страница профиля
@app.route('/profile')
@login_required
def profile():
    return render_template('profile.html')
@app.route('/tariff', methods=['GET'])
@login_required
def tariff():
    return render_template('tariff.html')
@app.route('/pay/<tariff_name>', methods=['GET'])
@login_required
def pay_tariff(tariff_name):
    user_id = session['user_id']
    days_to_add = 0
    # Логика, соответствующая тарифам
    if tariff_name == 'free-trial':
        days_to_add = 3
    elif tariff_name == 'single-month':
        days_to_add = 30
    elif tariff_name == 'more-vpn':
        days_to_add = 90
    elif tariff_name == 'usual':
        days_to_add = 180
    else:
        flash('Неизвестный тарифный план.', 'error')
        return redirect(url_for('tariff'))
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        # Обновляем время подписки
        cur.execute("UPDATE users SET time = time + %s WHERE id = %s", (days_to_add, user_id))
        conn.commit()
        cur.close()
        flash(f'Ваш тариф успешно обновлён: добавлено {days_to_add} дней!', 'success')
        return redirect(url_for('my_home_profile'))
    except Exception as e:
        if conn:
            conn.rollback()
        flash(f'Ошибка при обновлении тарифа: {str(e)}', 'error')
        return redirect(url_for('tariff'))
    finally:
        if conn:
            conn.close()
@app.route('/my-home-profile')
@login_required
def my_home_profile():
    user_id = session['user_id']
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        # Получаем имя пользователя, время подписки (time) и статус
        cur.execute("SELECT username, time, status FROM users WHERE id = %s", (user_id,))
        user = cur.fetchone()
        if user:
            username, time_left, status = user
            if time_left >= 0:
                remaining_time = timedelta(days=time_left)
                status = "Активен" if remaining_time.days > 0 else "Неактивен"
                time_remaining = f"{remaining_time.days // 30} мес {remaining_time.days % 30} дн" if remaining_time.days > 0 else "Подписка завершена"
            else:
                time_remaining = "Подписка завершена"
                status = "Неактивен"
            return render_template('my-home-profile.html', username=username, time_remaining=time_remaining, status=status)
        else:
            flash("Пользователь не найден.", "error")
            return redirect(url_for('profile'))
    except Exception as e:
        flash(f'Ошибка при извлечении данных: {str(e)}', "error")
        return redirect(url_for('profile'))
    finally:
        if conn:
            conn.close()

app.route('/setting')
@login_required
def setting():
    return render_template('setting')

# Заголовки для предотвращения кэширования
@app.after_request
def add_no_cache_headers(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response



if __name__ == '__main__':
    app.run(debug=True)
