from flask import Flask, request, render_template, redirect, url_for, session, jsonify, flash
import psycopg2
import os
import random
import string
import uuid
from urllib.parse import urlparse
from functools import wraps

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
            return redirect(url_for('login_page'))
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

    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        if is_username_taken(cur, username):
            flash('Извините, но пользователь с таким именем уже есть, выберите другой.', 'username_taken')
            # Передаем введенные данные обратно в шаблон
            return render_template('registration.html', username=username, email=email)

        cur.execute('INSERT INTO users (id, username, email, public_key, private_key) VALUES (%s, %s, %s, %s, %s)',
                    (unique_id, username, email, public_key, private_key))
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
def login_page():
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
                return redirect(url_for('login_page'))
        except Exception as e:
            flash(f'Ошибка при входе: {str(e)}', "error")
            return redirect(url_for('login_page'))
        finally:
            if conn:
                conn.close()
    return render_template('login.html')

@app.route('/home')
@login_required
def home():
    return render_template('home.html')

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect(url_for('login_page'))

if __name__ == '__main__':
    app.run(debug=True)