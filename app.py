from flask import Flask, request, render_template, redirect, url_for, session, flash
from flask_session import Session
import psycopg2
import os
import random
import string
import uuid
from urllib.parse import urlparse
from functools import wraps
from datetime import datetime, timedelta
import requests  # Для работы с reCAPTCHA
from apscheduler.schedulers.background import BackgroundScheduler  # Планировщик задач


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
    telegram_name = data.get('telegram_name')  # Получение Telegram имени
    recaptcha_response = data.get('g-recaptcha-response')  # Получение ответа капчи

    # Проверка reCAPTCHA
    if not recaptcha_response:
        flash('Пожалуйста, подтвердите, что вы не робот.', 'error')
        return render_template('registration.html', username=username, telegram_name=telegram_name,
                               recaptcha_site_key=RECAPTCHA_SITE_KEY)

    recaptcha_secret = os.getenv('RECAPTCHA_SECRET_KEY', '6LcHxYYqAAAAAFz_b7SB4p52ayqL1ubsg9hWyjgx')
    recaptcha_verify_url = 'https://www.google.com/recaptcha/api/siteverify'

    try:
        response = requests.post(
            recaptcha_verify_url,
            data={'secret': recaptcha_secret, 'response': recaptcha_response}
        )
        result = response.json()
        if not result.get('success'):
            flash('Ошибка валидации reCAPTCHA. Попробуйте снова.', 'error')
            return render_template('registration.html', username=username, telegram_name=telegram_name,
                                   recaptcha_site_key=RECAPTCHA_SITE_KEY)
    except Exception as e:
        flash(f'Ошибка связи с сервером reCAPTCHA: {str(e)}', 'error')
        return render_template('registration.html', username=username, telegram_name=telegram_name,
                               recaptcha_site_key=RECAPTCHA_SITE_KEY)

    # Проверка и корректировка telegram_name
    if not telegram_name.startswith('@'):
        telegram_name = f"@{telegram_name}"  # Добавляем @ в начале имени

    public_key, private_key = generate_keys()
    unique_id = generate_unique_id()

    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        if is_username_taken(cur, username):
            flash('Пользователь с таким именем уже существует.', 'error')
            return render_template('registration.html', username=username, telegram_name=telegram_name,
                                   recaptcha_site_key=RECAPTCHA_SITE_KEY)

        if is_telegram_name_taken(cur, telegram_name):  # Дополнительная проверка уникальности
            flash('Пользователь с таким Telegram-именем уже существует.', 'error')
            return render_template('registration.html', username=username, telegram_name=telegram_name,
                                   recaptcha_site_key=RECAPTCHA_SITE_KEY)

        cur.execute('INSERT INTO users (id, username, telegram_name, public_key, private_key, time, status, trial_used) '
                    'VALUES (%s, %s, %s, %s, %s, %s, %s, %s)',
                    (unique_id, username, telegram_name, public_key, private_key, 30, 'inactive', False))  # Статус и пробный период
        conn.commit()
        cur.close()

        flash('Поздравляем с успешной регистрацией!', 'success')
        return render_template('new_user.html', message='Поздравляем с успешной регистрацией!', public_key=public_key, private_key=private_key)
    except Exception as e:
        if conn:
            conn.rollback()
        flash(f'Ошибка при регистрации: {str(e)}', 'error')
        return render_template('registration.html', username=username, telegram_name=telegram_name,
                               recaptcha_site_key=RECAPTCHA_SITE_KEY)
    finally:
        if conn:
            conn.close()

# Функция проверки занятости Telegram имени
def is_telegram_name_taken(cursor, telegram_name):
    cursor.execute('SELECT COUNT(*) FROM users WHERE telegram_name = %s', (telegram_name,))
    return cursor.fetchone()[0] > 0

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

# Функция добавления времени подписки
def add_subscription_time(user_id, days_to_add):
    """
    Добавляет указанное количество дней подписки пользователю.
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("""
            UPDATE users
            SET time = COALESCE(time, 0) + %s
            WHERE id = %s
        """, (days_to_add, user_id))

        conn.commit()
        cur.close()
    except Exception as e:
        if conn:
            conn.rollback()
        raise e
    finally:
        if conn:
            conn.close()

# Функция уменьшения времени подписки
def decrease_subscription_time():
    """
    Уменьшает количество дней подписки на 1 у всех пользователей с активной подпиской.
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Уменьшаем время подписки, но не допускаем отрицательных значений
        cur.execute("""
            UPDATE users
            SET time = GREATEST(time - 1, 0)
            WHERE time > 0
        """)

        conn.commit()
        cur.close()
    except Exception as e:
        if conn:
            conn.rollback()
        raise e
    finally:
        if conn:
            conn.close()

# Планировщик для уменьшения времени
def schedule_tasks():
    """
    Запускает планировщик задач для уменьшения времени подписки.
    """
    scheduler = BackgroundScheduler()
    scheduler.add_job(decrease_subscription_time, 'interval', days=1)
    scheduler.start()

# Обработка webhook от платежной системы
@app.route('/payment-webhook', methods=['POST'])
def payment_webhook():
    data = request.json  # Получаем данные от платежной системы

    try:
        user_id = data.get('user_id')  # Идентификатор пользователя
        amount = data.get('amount')  # Сумма платежа
        status = data.get('status')  # Статус платежа (успешный или нет)

        # Логика определения продолжительности тарифа
        if amount == 3:  # Предположим, 3 дня = 50 ₽
            days_to_add = 3
        elif amount == 350:  # Тариф на месяц = 200 ₽
            days_to_add = 30
        elif amount == 450:  # Тариф на месяц = 200 ₽
            days_to_add = 30
        elif amount == 750:  # Тариф на месяц = 200 ₽
            days_to_add = 30
        else:
            days_to_add = 0  # Неизвестный тариф

        # Если оплата успешна, начисляем дни
        if status == 'success' and days_to_add > 0:
            add_subscription_time(user_id, days_to_add)

        return "OK", 200
    except Exception as e:
        return f"Error: {str(e)}", 500
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
    schedule_tasks()  # Запуск планировщика
    app.run(debug=True)
