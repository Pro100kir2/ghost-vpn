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
from flask_mail import Mail, Message
from telegram import Bot

app = Flask(__name__)

# Настройки для Flask-сессии
app.secret_key = os.urandom(24)

# reCAPTCHA ключи
RECAPTCHA_SITE_KEY = "6LcHxYYqAAAAABYAG2B__k_6MIiLBY4yf5_cPym2"  # Публичный ключ
RECAPTCHA_SECRET_KEY = "6LcHxYYqAAAAAFz_b7SB4p52ayqL1ubsg9hWyjgx"  # Секретный ключ

# Настройки почтового сервера
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.environ.get('ghostvpnofficial@gmail.com')  # Ваш email
app.config['MAIL_PASSWORD'] = os.environ.get('060422kirill')  # Пароль от email
mail = Mail(app)

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

    # Соединение с базой данных
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Проверка уникальности имени пользователя
        if is_username_taken(cur, username):
            flash('Имя пользователя уже занято, выберите другое.', 'username_taken')
            return render_template('registration.html', username=username, email=email, recaptcha_site_key=RECAPTCHA_SITE_KEY)

        # Вставка данных в базу данных
        cur.execute('INSERT INTO users (id, username, email, public_key, private_key, time, trial_used) VALUES (%s, %s, %s, %s, %s, %s, %s)',
                    (unique_id, username, email, public_key, private_key, 0, False))
        conn.commit()

        # Уведомление пользователя и перенаправление в зависимости от способа регистрации
        if '@name_user_telegram' in username:
            session['confirmation_type'] = 'telegram'
            flash('Регистрация успешна! Проверьте Telegram для подтверждения.', 'success')
            return redirect(url_for('verify_telegram'))
        else:
            session['confirmation_type'] = 'email'
            flash('Регистрация успешна! Проверьте почту для подтверждения.', 'success')
            return redirect(url_for('verify_email'))

    except Exception as e:
        if conn:
            conn.rollback()
        flash(f'Ошибка при регистрации: {str(e)}', 'error')
        return render_template('registration.html', username=username, email=email, recaptcha_site_key=RECAPTCHA_SITE_KEY)
    finally:
        if conn:
            conn.close()

# Верификация email
@app.route('/verify-email', methods=['GET', 'POST'])
def verify_email():
    if request.method == 'POST':
        email = request.form['email']
        confirmation_code = random.randint(100000, 999999)  # Генерация случайного 6-значного кода
        session['confirmation_code'] = confirmation_code
        session['email'] = email

        send_confirmation_email(email, confirmation_code)
        return render_template('confirm_email.html')

    return render_template('confirm_email.html')

# Функция для отправки email с кодом подтверждения
def send_confirmation_email(recipient_email, confirmation_code):
    msg = Message('Код подтверждения',
                  sender=os.environ.get('EMAIL_USER'),
                  recipients=[recipient_email])
    msg.body = f'Ваш код подтверждения: {confirmation_code}'
    mail.send(msg)

# Проверка кода email
@app.route('/confirm-email', methods=['POST'])
def confirm_email():
    user_code = request.form['code']
    if int(user_code) == session.get('confirmation_code'):
        flash('Email подтвержден!', 'success')
        return redirect(url_for('login'))
    else:
        flash('Неверный код подтверждения!', 'error')
        return redirect(url_for('verify_email'))

# Верификация через Telegram
@app.route('/verify-telegram', methods=['GET', 'POST'])
def verify_telegram():
    if request.method == 'POST':
        chat_id = request.form['chat_id']  # Предполагаем, что chat_id приходит с формы
        confirmation_code = random.randint(100000, 999999)  # Генерация случайного кода
        session['confirmation_code'] = confirmation_code
        session['chat_id'] = chat_id

        send_confirmation_telegram(chat_id, confirmation_code)
        return render_template('confirm_telegram.html')

    return render_template('confirm_telegram.html')

# Функция для отправки кода через Telegram
def send_confirmation_telegram(chat_id, confirmation_code):
    bot = Bot(token=os.environ.get('TELEGRAM_TOKEN'))
    bot.send_message(chat_id=chat_id, text=f'Ваш код подтверждения: {confirmation_code}')

# Проверка кода Telegram
@app.route('/confirm-telegram', methods=['POST'])
def confirm_telegram():
    user_code = request.form['code']
    if int(user_code) == session.get('confirmation_code'):
        flash('Telegram аккаунт подтвержден!', 'success')
        return redirect(url_for('login'))
    else:
        flash('Неверный код подтверждения!', 'error')
        return redirect(url_for('verify_telegram'))

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
@app.route('/home', methods=['GET'])
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
@login_required
def about():
    return render_template('about.html')
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
            # Проверяем, что time >= 0, чтобы отобразить оставшееся время
            if time_left >= 0:
                # Рассчитываем оставшееся время как количество дней
                remaining_time = timedelta(days=time_left)
                status = "Активен" if remaining_time.days > 0 else "Неактивен"
                # Форматируем оставшееся время в формате "мес:дней"
                time_remaining = f"{remaining_time.days // 30} мес {remaining_time.days % 30} дн" if remaining_time.days > 0 else "Подписка завершена"
            else:
                # Если time < 0, то подписка завершена
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
# Заголовки для предотвращения кэширования
@app.after_request
def add_no_cache_headers(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

if __name__ == '__main__':
    app.run(debug=True)
