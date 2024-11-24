from flask import Flask, request, render_template, redirect, url_for, session, flash
import psycopg2
import os
import random
import string
import uuid
from urllib.parse import urlparse
from functools import wraps
from datetime import timedelta
import smtplib
from email.mime.text import MIMEText

app = Flask(__name__)

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
    response = requests.post(url, data=data)
    result = response.json()
    return result.get('success', False)

# Проверка уникальности имени пользователя
def is_username_taken(cursor, username):
    cursor.execute("SELECT COUNT(*) FROM users WHERE username = %s", (username,))
    count = cursor.fetchone()[0]
    return count > 0

# Отправка email
def send_email(to_email, subject, message):
    smtp_server = os.environ.get('SMTP_SERVER', 'smtp.gmail.com')
    smtp_port = int(os.environ.get('SMTP_PORT', 587))
    smtp_user = os.environ.get('SMTP_USER', 'your_email@gmail.com')
    smtp_password = os.environ.get('SMTP_PASSWORD', 'your_password')

    msg = MIMEText(message)
    msg['Subject'] = subject
    msg['From'] = smtp_user
    msg['To'] = to_email

    with smtplib.SMTP(smtp_server, smtp_port) as server:
        server.starttls()
        server.login(smtp_user, smtp_password)
        server.send_message(msg)

# Декоратор для защиты маршрутов
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Доступ запрещен! Пожалуйста, авторизуйтесь.", "error")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/registration', methods=['GET'])
def registration_page():
    return render_template('registration.html', recaptcha_site_key=RECAPTCHA_SITE_KEY)

@app.route('/register', methods=['POST'])
def register():
    data = request.form
    username = data.get('username')
    email = data.get('email')
    recaptcha_response = data.get('g-recaptcha-response')

    if not verify_recaptcha(recaptcha_response):
        flash('Пожалуйста, подтвердите, что вы не робот.', 'error')
        return redirect(url_for('registration_page'))

    public_key, private_key = generate_keys()
    unique_id = generate_unique_id()
    confirmation_code = ''.join(random.choices(string.digits, k=6))

    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        if is_username_taken(cur, username):
            flash('Имя пользователя уже занято.', 'username_taken')
            return render_template('registration.html', username=username, email=email, recaptcha_site_key=RECAPTCHA_SITE_KEY)

        cur.execute('INSERT INTO users (id, username, email, public_key, private_key, confirmation_code, confirmation_attempts, time, status) '
                    'VALUES (%s, %s, %s, %s, %s, %s, %s, 0, FALSE)',
                    (unique_id, username, email, public_key, private_key, confirmation_code, 3))
        conn.commit()

        send_email(email, 'Код подтверждения GhostVPN', f'Ваш код подтверждения: {confirmation_code}')
        flash('Регистрация успешна! Проверьте почту для подтверждения.', 'success')
        return redirect(url_for('confirm_telegram'))
    except Exception as e:
        if conn:
            conn.rollback()
        flash(f'Ошибка при регистрации: {str(e)}', 'error')
        return render_template('registration.html', username=username, email=email, recaptcha_site_key=RECAPTCHA_SITE_KEY)
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
@login_required
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
