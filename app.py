from flask import Flask, request, render_template, redirect, url_for, jsonify
import psycopg2
import random
import string

app = Flask(__name__)

# Настройки подключения к базе данных
DB_NAME = 'ghostvpn'
DB_USER = 'pro100kir2'
DB_PASSWORD = '1234'
DB_HOST = 'localhost'

def generate_keys():
    public_key = ''.join(random.choices(string.ascii_lowercase + string.digits, k=12))
    private_key = ''.join(random.choices(string.ascii_lowercase + string.digits, k=24))
    return public_key, private_key

def get_db_connection():
    return psycopg2.connect(dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD, host=DB_HOST)

@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')

@app.route('/registration', methods=['GET'])
def registration_page():
    return render_template('registration.html')  # Обратите внимание на добавление .html

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

        # Проверка на уникальность имени пользователя
        if is_username_taken(cur, username):
            return jsonify({'error': 'Извините, но пользователь с таким именем уже есть, выберите другой.'}), 400

        # Вставка нового пользователя
        cur.execute("INSERT INTO users (username, email, public_key, private_key) VALUES (%s, %s, %s, %s)",
                    (username, email, public_key, private_key))
        conn.commit()  # Подтверждаем изменения
        cur.close()

        # Перенаправление на страницу с успешной регистрацией
        return render_template('new_user.html', message='Поздравляем с успешной регистрацией!', public_key=public_key, private_key=private_key)

    except Exception as e:
        # Обработка других ошибок
        if conn:
            conn.rollback()
        return jsonify({'error': f'Ошибка при добавлении пользователя: {str(e)}'}), 400
    finally:
        if conn:
            conn.close()

def is_username_taken(cursor, username):
    cursor.execute("SELECT COUNT(*) FROM users WHERE username = %s", (username,))
    count = cursor.fetchone()[0]
    return count > 0  # Возвращает True, если имя пользователя занято

@app.route('/login', methods=['GET', 'POST'])
def login_page():
    if request.method == 'POST':
        username = request.form['username']
        public_key = request.form['public_key']

        conn = None
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("SELECT * FROM users WHERE username = %s AND public_key = %s", (username, public_key))
            user = cur.fetchone()

            if user:
                return jsonify({'message': 'Вход успешен!'}), 200
            else:
                return jsonify({'error': 'Неверное имя пользователя или публичный ключ!'}), 400

        except Exception as e:
            return jsonify({'error': f'Ошибка при входе: {str(e)}'}), 400
        finally:
            if conn:
                conn.close()

    return render_template('login.html')  # Убедитесь, что этот шаблон также существует

if __name__ == '__main__':
    app.run(debug=True)
