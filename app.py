from flask import Flask, request, render_template, redirect, url_for, session, jsonify, flash
import psycopg2
import os
import random
import string
import uuid
from urllib.parse import urlparse
from functools import wraps
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'

def generate_keys():
    public_key = ''.join(random.choices(string.ascii_lowercase + string.digits, k=12))
    private_key = ''.join(random.choices(string.ascii_lowercase + string.digits, k=24))
    return public_key, private_key

def generate_unique_id():
    return str(uuid.uuid4())

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
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')

@app.route('/registration', methods=['GET'])
def registration_page():
    return render_template('registration.html')

@app.route('/register', methods=['POST'])
def register():
    data = request.form
    username = data.get('username')
    email = data.get('email')

    public_key, private_key = generate_keys()
    unique_id = generate_unique_id()
    subscription_end = datetime.now() + timedelta(days=30)  # Добавляем 30 дней подписки

    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        if is_username_taken(cur, username):
            flash('Извините, но пользователь с таким именем уже есть, выберите другой.', 'username_taken')
            return render_template('registration.html', username=username, email=email)

        cur.execute('INSERT INTO users (id, username, email, public_key, private_key, subscription_end) VALUES (%s, %s, %s, %s, %s, %s)',
                    (unique_id, username, email, public_key, private_key, subscription_end))
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

def is_username_taken(cursor, username):
    cursor.execute("SELECT COUNT(*) FROM users WHERE username = %s", (username,))
    count = cursor.fetchone()[0]
    return count > 0

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


@app.route('/my-profile.html')
@login_required
def my_profile():
    user_id = session.get('user_id')

    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Извлечение данных пользователя
        cur.execute("""
            SELECT username, subscription_end FROM users 
            WHERE id = %s
        """, (user_id,))
        user_data = cur.fetchone()

        if not user_data:
            flash('Пользователь не найден.', 'error')
            return redirect(url_for('profile'))

        username = user_data[0]
        subscription_end = user_data[1]  # Предполагается, что subscription_end хранится как дата или строка

        # Логика определения времени и статуса
        from datetime import datetime

        current_date = datetime.now()
        if subscription_end:
            end_date = datetime.strptime(subscription_end, "%Y-%m-%d")  # Или другой формат даты
            remaining_days = (end_date - current_date).days
        else:
            remaining_days = 0

        subscription_status = "active" if remaining_days > 0 else "inactive"

        # Форматирование оставшегося времени
        formatted_time = f"{max(remaining_days, 0)} дн."

        return render_template('my-home-profile.html',
                               username=username,
                               subscription_time=formatted_time,
                               subscription_status=subscription_status)

    except Exception as e:
        flash(f'Ошибка при загрузке профиля: {str(e)}', 'error')
        return redirect(url_for('profile'))
    finally:
        if conn:
            conn.close()


if __name__ == '__main__':
    app.run(debug=True)
