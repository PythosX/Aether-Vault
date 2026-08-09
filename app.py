import os
import sqlite3
import requests
from urllib.parse import urlparse
from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'aethervault_fallback_secret')

BOT_TOKEN = os.getenv('BOT_TOKEN')
CHANNEL_ID = os.getenv('TELEGRAM_CHANNEL_ID')
DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///aethervault.db')

def get_db_connection():
    if DATABASE_URL.startswith("postgres://") or DATABASE_URL.startswith("postgresql://"):
        import psycopg2
        url = DATABASE_URL.replace("postgres://", "postgresql://", 1)
        conn = psycopg2.connect(url)
        return conn, "postgres"
    else:
        db_path = DATABASE_URL.replace("sqlite:///", "")
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn, "sqlite"

def init_db():
    conn, db_type = get_db_connection()
    c = conn.cursor()
    if db_type == "postgres":
        c.execute('''CREATE TABLE IF NOT EXISTS users 
                     (id SERIAL PRIMARY KEY, username VARCHAR(255) UNIQUE NOT NULL, password TEXT NOT NULL)''')
        c.execute('''CREATE TABLE IF NOT EXISTS files 
                     (id SERIAL PRIMARY KEY, user_id INTEGER REFERENCES users(id), file_id TEXT NOT NULL, file_name TEXT NOT NULL)''')
    else:
        c.execute('''CREATE TABLE IF NOT EXISTS users 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL, password TEXT NOT NULL)''')
        c.execute('''CREATE TABLE IF NOT EXISTS files 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, file_id TEXT NOT NULL, file_name TEXT NOT NULL)''')
    conn.commit()
    conn.close()

init_db()

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username'].strip().lower()
        password = request.form['password']
        hashed = generate_password_hash(password)
        
        try:
            conn, db_type = get_db_connection()
            c = conn.cursor()
            if db_type == "postgres":
                c.execute("INSERT INTO users (username, password) VALUES (%s, %s)", (username, hashed))
            else:
                c.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, hashed))
            conn.commit()
            conn.close()
            flash('Account created successfully! You can now log in.')
            return redirect(url_for('login'))
        except Exception as e:
            flash('Username already registered or invalid input.')
            
    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username'].strip().lower()
        password = request.form['password']
        
        conn, db_type = get_db_connection()
        c = conn.cursor()
        if db_type == "postgres":
            c.execute("SELECT id, username, password FROM users WHERE username = %s", (username,))
            user = c.fetchone()
            if user:
                user = {'id': user[0], 'username': user[1], 'password': user[2]}
        else:
            c.execute("SELECT * FROM users WHERE username = ?", (username,))
            user = c.fetchone()
        conn.close()

        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            return redirect(url_for('dashboard'))
        flash('Invalid credentials. Please check your username and password.')
        
    return render_template('login.html')

@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user_id = session['user_id']
    if request.method == 'POST':
        file = request.files.get('file')
        if file and file.filename != '':
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument"
            response = requests.post(url, data={'chat_id': CHANNEL_ID}, files={'document': (file.filename, file.stream)})
            res_data = response.json()
            
            if res_data.get('ok'):
                tg_file_id = res_data['result']['document']['file_id']
                conn, db_type = get_db_connection()
                c = conn.cursor()
                if db_type == "postgres":
                    c.execute("INSERT INTO files (user_id, file_id, file_name) VALUES (%s, %s, %s)",
                              (user_id, tg_file_id, file.filename))
                else:
                    c.execute("INSERT INTO files (user_id, file_id, file_name) VALUES (?, ?, ?)",
                              (user_id, tg_file_id, file.filename))
                conn.commit()
                conn.close()
                flash('File securely vaulted to Telegram Cloud!')
            else:
                flash('Telegram storage error. Check Bot credentials.')

    conn, db_type = get_db_connection()
    c = conn.cursor()
    if db_type == "postgres":
        c.execute("SELECT id, file_id, file_name FROM files WHERE user_id = %s", (user_id,))
        raw_files = c.fetchall()
        user_files = [{'id': f[0], 'file_id': f[1], 'file_name': f[2]} for f in raw_files]
    else:
        c.execute("SELECT * FROM files WHERE user_id = ?", (user_id,))
        user_files = c.fetchall()
    conn.close()
    
    return render_template('dashboard.html', files=user_files, username=session['username'])

@app.route('/download/<file_id>')
def download(file_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    get_path_url = f"https://api.telegram.org/bot{BOT_TOKEN}/getFile?file_id={file_id}"
    res = requests.get(get_path_url).json()
    if res.get('ok'):
        file_path = res['result']['file_path']
        download_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
        return redirect(download_url)
    
    flash('Unable to process download request.')
    return redirect(url_for('dashboard'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True, port=5000)

