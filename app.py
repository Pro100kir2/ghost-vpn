from flask import Flask, request, render_template, redirect, url_for, session, jsonify, flash
import psycopg2
import os
import random
import string
import uuid
from urllib.parse import urlparse
from functools import wraps

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'default_secret_key')


# Функции для генерации ключей и ID
def generate_keys():
    public_key = ''.join(random.choices(string.ascii_lowercase + string.digits, k=12))
    private_key = ''.join(random.choices(string.ascii_lowercase + string.digits, k=24))
    return public_key, private_key


def generate_unique_id():
    return str(uuid.uuid4())


def get_db_connection():
    db_url = os.environ.get('DATABASE_URL')  # Используем DATABASE_URL для подключения
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
            return redirect(url_for('login_page'))
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


# Регистрация пользователя
@app.route('/register', methods=['POST'])
def register():
    data = request.form
    username = data.get('username')
    email = data.get('email')
    public_key, private_key = generate_keys()
    unique_id = generate_unique_id()

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        if is_username_taken(cur, username):
            flash('Пользователь с таким именем уже существует.', 'username_taken')
            return render_template('registration.html', username=username, email=email)

        cur.execute('INSERT INTO users (id, username, email, public_key, private_key) VALUES (%s, %s, %s, %s, %s)',
                    (unique_id, username, email, public_key, private_key))
        conn.commit()
        flash('Регистрация успешна!', 'success')
        return render_template('new_user.html', message='Регистрация успешна!', public_key=public_key,
                               private_key=private_key)
    except Exception as e:
        flash('Ошибка при регистрации.', 'error')
    finally:
        conn.close()


def is_username_taken(cursor, username):
    cursor.execute("SELECT COUNT(*) FROM users WHERE username = %s", (username,))
    return cursor.fetchone()[0] > 0


# Логин
@app.route('/login', methods=['GET', 'POST'])
def login_page():
    if request.method == 'POST':
        username = request.form['username']
        public_key = request.form['public_key']
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("SELECT id FROM users WHERE username = %s AND public_key = %s", (username, public_key))
            user = cur.fetchone()
            if user:
                session['user_id'] = user[0]
                return redirect(url_for('home'))
            flash("Неверное имя пользователя или ключ.", "error")
        except:
            flash('Ошибка при входе.', "error")
    return render_template('login.html')


@app.route('/home')
@login_required
def home():
    return render_template('home.html')


@app.route('/profile.html')
def profile():
    return render_template('profile.html')


@app.route('/tariff.html')
def tariff():
    return render_template('tariff.html')


@login_required
@app.route('/my-devise.html', methods=['GET', 'POST'])
def my_device():
    user_id = session['user_id']
    devices = get_user_devices(user_id)
    if request.method == 'POST':
        device_name = request.form.get('device_name')
        try:
            if request.form['action'] == 'add':
                add_device(user_id, device_name)
                flash('Устройство добавлено успешно', 'success')
            elif request.form['action'] == 'delete':
                delete_device(user_id, device_name)
                flash('Устройство удалено.', 'success')
        except Exception as e:
            flash('Ошибка при обновлении устройства.', 'error')
    return render_template('my-devise.html', devices=devices)


# Добавление устройства
@app.route('/add_device', methods=['POST'])
@login_required
def add_device_api():
    try:
        data = request.get_json()
        device_name = data.get('deviceName')
        user_id = session['user_id']

        # Добавление устройства в базу данных
        device_id = generate_unique_id()
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            'INSERT INTO devices (idu, name, active) VALUES (%s, %s, %s)',
            (user_id, device_name, True)
        )
        conn.commit()
        conn.close()

        # Возвращаем успешный ответ
        return jsonify({'idd': device_id, 'name': device_name, 'active': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 400


# Удаление устройства
@app.route('/delete_device', methods=['POST'])
@login_required
def delete_device_api():
    try:
        data = request.get_json()
        device_name = data.get('deviceName')
        user_id = session['user_id']

        # Удаление устройства из базы данных
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('DELETE FROM devices WHERE idu = %s AND name = %s', (user_id, device_name))
        conn.commit()
        conn.close()

        # Возвращаем успешный ответ
        return jsonify({'message': 'Устройство удалено.'})
    except Exception as e:
        return jsonify({'error': str(e)}), 400


def get_user_devices(user_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT name, active FROM devices WHERE idu = %s', (user_id,))
    devices = [{'name': row[0], 'active': row[1]} for row in cur.fetchall()]
    conn.close()
    return devices


if __name__ == '__main__':
    app.run(debug=True)
