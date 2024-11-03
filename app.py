from flask import Flask, request, render_template, redirect, url_for, session, jsonify
import psycopg2
import os
import random
import string
from urllib.parse import urlparse
from functools import wraps

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'

def generate_keys():
    public_key = ''.join(random.choices(string.ascii_lowercase + string.digits, k=12))
    private_key = ''.join(random.choices(string.ascii_lowercase + string.digits, k=24))
    return public_key, private_key

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

    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        if is_username_taken(cur, username):
            return jsonify({'error': 'Извините, но пользователь с таким именем уже есть, выберите другой.'}), 400

        cur.execute('INSERT INTO users (username, email, public_key, private_key) VALUES (%s, %s, %s, %s)',
                    (username, email, public_key, private_key))
        conn.commit()
        cur.close()

        return render_template('new_user.html', message='Поздравляем с успешной регистрацией!', public_key=public_key, private_key=private_key)

    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'error': f'Ошибка при добавлении пользователя: {str(e)}'}), 400
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
                return jsonify({'error': 'Неверное имя пользователя или публичный ключ!'}), 400

        except Exception as e:
            return jsonify({'error': f'Ошибка при входе: {str(e)}'}), 400
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
