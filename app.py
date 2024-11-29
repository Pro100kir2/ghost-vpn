from flask import Flask, request, render_template, redirect, url_for, session, flash
import psycopg2
import os
import random
import string
import uuid
import requests
from functools import wraps
from datetime import timedelta , datetime
from urllib.parse import urlparse


app = Flask(__name__)
app.secret_key = os.urandom(24)

# reCAPTCHA ключи
RECAPTCHA_SITE_KEY = "6LcHxYYqAAAAABYAG2B__k_6MIiLBY4yf5_cPym2"
RECAPTCHA_SECRET_KEY = "6LcHxYYqAAAAAFz_b7SB4p52ayqL1ubsg9hWyjgx"

# Генерация ключей
def generate_keys():
    public_key = ''.join(random.choices(string.ascii_lowercase + string.digits, k=12))
    private_key = ''.join(random.choices(string.ascii_lowercase + string.digits, k=24))
    return public_key, private_key

# Генерация уникального ID
def generate_unique_id():
    return str(uuid.uuid4())

# Подключение к базе данных
def get_db_connection():
    db_url = os.environ.get('DATABASE_URL')
    result = urlparse(db_url)
    try:
        conn = psycopg2.connect(
            dbname=result.path[1:],
            user=result.username,
            password=result.password,
            host=result.hostname,
            port=result.port
        )
        return conn
    except Exception as e:
        print(f"Ошибка при подключении к базе данных: {e}")
        return None

# Проверка reCAPTCHA
def verify_recaptcha(response_token):
    url = "https://www.google.com/recaptcha/api/siteverify"
    data = {'secret': RECAPTCHA_SECRET_KEY, 'response': response_token}
    response = requests.post(url, data=data, timeout=5)
    result = response.json()
    return result.get('success', False)

# Проверка занятости имени пользователя
def is_username_taken(cursor, username):
    cursor.execute("SELECT COUNT(*) FROM users WHERE username = %s", (username,))
    count = cursor.fetchone()[0]
    return count > 0

# Проверка занятости Telegram username
def is_telegram_username_taken(cursor, telegram_username):
    cursor.execute('SELECT 1 FROM users WHERE telegram_username = %s', (telegram_username,))
    return cursor.fetchone() is not None

# Декоратор для проверки входа
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Доступ запрещен! Пожалуйста, авторизуйтесь.", "error")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Отправка сообщения в Telegram
def send_telegram_message(telegram_username, message):
    bot_token = '7532462167:AAFrEoclnACi8qzPTRvZedM7r06BMYE0ep8'
    chat_id = telegram_username  # Используйте числовой chat_id вместо @username

    url = f'https://api.telegram.org/bot{bot_token}/sendMessage'
    params = {
        'chat_id': chat_id,
        'text': message
    }
    response = requests.post(url, data=params)
    return response.status_code == 200

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/registration', methods=['GET'])
def registration_page():
    return render_template('registration.html', recaptcha_site_key=RECAPTCHA_SITE_KEY)


# Маршрут регистрации
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

    # Форматирование Telegram username
    if telegram_username and not telegram_username.startswith('@'):
        telegram_username = '@' + telegram_username

    # Генерация уникального ID и ключей
    public_key, private_key = generate_keys()
    unique_id = generate_unique_id()

    # Генерация кода подтверждения
    confirmation_code = ''.join(random.choices(string.digits, k=6))

    # Устанавливаем срок действия кода (например, 10 минут)
    expiration_time = datetime.now() + timedelta(minutes=10)

    # Подключение к базе данных
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()

            # Проверка на занятость имени пользователя
            if is_username_taken(cur, username):
                flash('Имя пользователя уже занято.', 'username_taken')
                return render_template('registration.html', username=username, telegram_username=telegram_username)

            # Проверка на занятость Telegram username
            if is_telegram_username_taken(cur, telegram_username):
                flash('Этот Telegram username уже занят, пожалуйста, выберите другой.', 'telegram_taken')
                return render_template('registration.html', username=username, telegram_username=telegram_username)

            # Сохраняем данные регистрации в сессии
            session['registration_data'] = {
                'id': unique_id,
                'username': username,
                'telegram_username': telegram_username,
                'public_key': public_key,
                'private_key': private_key,
                'confirmation_code': confirmation_code,
                'expiration_time': expiration_time,
                'attempts': 0
            }

            # Отправляем код подтверждения в Telegram
            send_telegram_message(telegram_username, f'Ваш код подтверждения: {confirmation_code}')
            flash('Код подтверждения отправлен. Проверьте Telegram.', 'success')
            return redirect(url_for('confirm_telegram'))
        except Exception as e:
            flash(f'Ошибка при регистрации: {str(e)}', 'error')
            return redirect(url_for('registration_page'))
        finally:
            conn.close()
    else:
        flash("Не удалось подключиться к базе данных.", "error")
        return redirect(url_for('registration_page'))
@app.route('/confirm', methods=['POST', 'GET'])
def confirm_telegram():
    if request.method == 'POST':
        code = request.form['confirmation_code']

        # Проверка данных в сессии
        if 'registration_data' not in session:
            flash("Данные регистрации не найдены. Попробуйте зарегистрироваться снова.", "error")
            return redirect(url_for('registration_page'))

        registration_data = session['registration_data']

        # Проверка на истечение срока действия кода
        if datetime.now() > registration_data['expiration_time']:
            flash("Ваш код истек. Пожалуйста, запросите новый.", "error")
            session.pop('registration_data', None)
            return redirect(url_for('registration_page'))

        # Проверка кода и попыток
        if code == registration_data['confirmation_code']:
            conn = get_db_connection()
            if conn:
                try:
                    cur = conn.cursor()

                    # Вставка данных пользователя в базу данных
                    cur.execute(
                        'INSERT INTO users (id, username, telegram_username, public_key, private_key, confirmation_code, confirmation_attempts, time, status) '
                        'VALUES (%s, %s, %s, %s, %s, NULL, NULL, 0, TRUE)',
                        (registration_data['id'], registration_data['username'], registration_data['telegram_username'],
                         registration_data['public_key'], registration_data['private_key'])
                    )
                    conn.commit()

                    # Успешная регистрация
                    session.pop('registration_data', None)
                    session['user_id'] = registration_data['id']
                    flash('Регистрация завершена успешно!', 'success')
                    return redirect(url_for('new_user'))
                except Exception as e:
                    flash(f'Ошибка при подтверждении: {str(e)}', 'error')
                finally:
                    conn.close()
            else:
                flash("Не удалось подключиться к базе данных для подтверждения.", "error")
        else:
            # Неверный код подтверждения
            registration_data['attempts'] += 1
            if registration_data['attempts'] >= 3:
                flash("Вы исчерпали количество попыток. Попробуйте позже.", "error")
                session.pop('registration_data', None)
                return redirect(url_for('registration_page'))
            else:
                flash('Код неверный. Попробуйте снова.', 'error')

        # Сохраняем данные сессии после каждой попытки
        session['registration_data'] = registration_data

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

        conn = get_db_connection()
        if conn:
            try:
                cur = conn.cursor()
                cur.execute("SELECT id FROM users WHERE username = %s AND public_key = %s", (username, public_key))
                user = cur.fetchone()

                if user:
                    session['user_id'] = user[0]
                    return redirect(url_for('profile'))
                else:
                    flash("Неверное имя пользователя или публичный ключ!", "error")
            except Exception as e:
                flash(f'Ошибка при входе: {str(e)}', "error")
            finally:
                conn.close()
        else:
            flash("Не удалось подключиться к базе данных при входе.", "error")
    return render_template('login.html')

@app.route('/tariff')
def tariff():
    return render_template('tariff.html')

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

@app.route('/profile')
@login_required
def profile():
    return render_template('profile.html')


@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    user_id = session['user_id']

    if request.method == 'POST':
        new_username = clean_input(request.form.get('username'))
        new_telegram_username = clean_input(request.form.get('telegram_username'))
        new_public_key = clean_input(request.form.get('public_key'))
        private_key = clean_input(request.form.get('private_key'))
        action = request.form.get('action')

        conn = get_db_connection()
        if conn:
            try:
                cur = conn.cursor()

                # Проверка текущего private_key
                cur.execute("SELECT private_key FROM users WHERE id = %s", (user_id,))
                user = cur.fetchone()

                if user and private_key == user[0]:
                    if action == 'update':
                        update_query = """
                            UPDATE users
                            SET 
                                username = COALESCE(NULLIF(%s, ''), username),
                                telegram_username = COALESCE(NULLIF(%s, ''), telegram_username),
                                public_key = COALESCE(NULLIF(%s, ''), public_key)
                            WHERE id = %s
                        """
                        print(f"SQL to execute: {cur.mogrify(update_query, (new_username, new_telegram_username, new_public_key, user_id))}")
                        cur.execute(update_query, (new_username, new_telegram_username, new_public_key, user_id))
                        conn.commit()

                        if cur.rowcount > 0:
                            flash("Данные успешно обновлены.", "success")
                        else:
                            flash("Данные не были изменены. Проверьте вводимые значения.", "error")

                    elif action == 'delete':
                        cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
                        conn.commit()
                        session.pop('user_id', None)
                        flash("Учетная запись удалена.", "success")
                        return redirect(url_for('index'))

                else:
                    flash("Неверный private_key. Попробуйте снова.", "error")
            except Exception as e:
                flash(f"Ошибка: {e}", "error")
            finally:
                conn.close()
        else:
            flash("Ошибка подключения к базе данных.", "error")

    return render_template('settings.html')

 # Рендерим страницу настроек
@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/privacy-policy')
def privacy_policy():
    return render_template('privacy-policy.html')

@app.after_request
def add_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "script-src 'self' https://www.google.com https://www.gstatic.com; "
        "frame-src https://www.google.com; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:;"
    )
    return response

@app.errorhandler(404)
def page_not_found():
    flash("Страница не найдена!", "error")
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_server_error():
    flash("Произошла ошибка сервера. Попробуйте позже.", "error")
    return render_template('500.html'), 500

# Главный вход
if __name__ == '__main__':
    app.run(debug=True)

