from flask import Flask, render_template, request, redirect, url_for, send_from_directory, flash, session
import os
from datetime import datetime
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
# セッションで利用する秘密鍵（ランダムな文字列に設定してください）
# 本番環境では環境変数などから読み込むのが安全です
app.config['SECRET_KEY'] = os.urandom(24).hex() # これで正しいです

UPLOAD_FOLDER = 'uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

DATABASE = 'database.db'

def get_db():
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    return db

def init_db():
    with app.app_context():
        db = get_db()
        with open('schema.sql', 'r') as f:
            db.executescript(f.read())
        db.commit()

def init_user_db():
    with app.app_context():
        db = get_db()
        db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL
            );
        ''')
        db.commit()

def add_admin_user(username, password):
    with app.app_context():
        db = get_db()
        hashed_password = generate_password_hash(password)
        try:
            db.execute(
                'INSERT INTO users (username, password) VALUES (?, ?)',
                (username, hashed_password)
            )
            db.commit()
            print(f"ユーザー '{username}' が正常に登録されました。")
        except sqlite3.IntegrityError:
            print(f"ユーザー名 '{username}' は既に存在します。")
        db.close()


@app.route('/')
def index():
    return render_template('upload.html')

# --- ログイン関連のルートはここに追加します ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        db = get_db()
        user = db.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        db.close()

        if user and check_password_hash(user['password'], password):
            session['logged_in'] = True # セッションにログイン状態を記録
            flash('ログインしました！') # ユーザーへのメッセージ
            return redirect(url_for('data_list')) # ログイン後、データ一覧ページへリダイレクト
        else:
            flash('ユーザー名またはパスワードが間違っています。') # エラーメッセージ
    return render_template('login.html') # GETリクエストまたは認証失敗時にログインフォームを表示

@app.route('/logout')
def logout():
    session.pop('logged_in', None) # セッションからログイン状態を削除
    flash('ログアウトしました。')
    return redirect(url_for('login')) # ログアウト後、ログインページへリダイレクト
# --- ログイン関連のルートはここまで ---


@app.route('/data')
def data_list():
    # --- ログインチェックを有効化 ---
    if not session.get('logged_in'):
        flash('ログインが必要です。')
        return redirect(url_for('login'))
    # --- ここまで修正 ---

    db = get_db()
    search_device = request.args.get('search_device', '')
    search_sample = request.args.get('search_sample', '')

    query = 'SELECT * FROM experiments WHERE 1=1'
    params = []

    if search_device:
        query += ' AND device_name LIKE ?'
        params.append(f'%{search_device}%')

    if search_sample:
        query += ' AND sample_name LIKE ?'
        params.append(f'%{search_sample}%')

    query += ' ORDER BY uploaded_at DESC'

    experiments = db.execute(query, params).fetchall()
    db.close()

    return render_template('data_list.html', 
                           experiments=experiments,
                           search_device=search_device,
                           search_sample=search_sample)

@app.route('/download/<int:experiment_id>')
def download_file(experiment_id):
    # --- ログインチェックを有効化 ---
    if not session.get('logged_in'):
        flash('ログインが必要です。')
        return redirect(url_for('login'))
    # --- ここまで修正 ---

    db = get_db()
    experiment = db.execute('SELECT file_name, file_path FROM experiments WHERE id = ?', (experiment_id,)).fetchone()
    db.close()

    if experiment:
        directory = os.path.dirname(experiment['file_path'])
        filename = os.path.basename(experiment['file_path'])
        
        absolute_upload_folder = os.path.abspath(app.config['UPLOAD_FOLDER'])
        absolute_filepath = os.path.abspath(experiment['file_path'])

        if os.path.commonpath([absolute_upload_folder, absolute_filepath]) == absolute_upload_folder:
            print(f"ダウンロードリクエスト: {filename} from {directory}")
            return send_from_directory(directory, filename, as_attachment=True)
        else:
            return "ファイルパスが不正です。", 400
    return "ファイルが見つかりません。", 404

@app.route('/upload', methods=['POST'])
def upload_file():
    # --- ログインチェックを有効化 ---
    if not session.get('logged_in'):
        flash('ログインが必要です。')
        return redirect(url_for('login'))
    # --- ここまで修正 ---

    if request.method == 'POST':
        experiment_device = request.form['experiment_device']
        sample_name = request.form['sample_name']
        experiment_date_str = request.form['experiment_date']
        
        try:
            experiment_date = datetime.strptime(experiment_date_str, '%Y-%m-%d').date()
        except ValueError:
            return "日付の形式が正しくありません。YYYY-MM-DD形式で入力してください。", 400

        if 'file' not in request.files:
            return "ファイルが選択されていません。", 400
        file = request.files['file']

        if file.filename == '':
            return "ファイルが選択されていません。", 400

        if file:
            filename = file.filename
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)

            db = get_db()
            db.execute(
                'INSERT INTO experiments (device_name, sample_name, experiment_date, file_name, file_path) VALUES (?, ?, ?, ?, ?)',
                (experiment_device, sample_name, experiment_date, filename, filepath)
            )
            db.commit()
            db.close()

            print(f"ファイル名: {filename}")
            print(f"実験装置名: {experiment_device}")
            print(f"サンプル名: {sample_name}")
            print(f"日付: {experiment_date}")
            print(f"ファイルパス: {filepath}")
            print(f"データベースに保存しました。")

            return redirect(url_for('data_list'))
    return "アップロードエラー", 400

if __name__ == '__main__':
    if not os.path.exists(DATABASE):
        init_db() # 実験データ用DBの初期化
    
    init_user_db() # ユーザー用DBの初期化（usersテーブル作成）

    # 管理ユーザーを登録したい場合に一度だけ実行する
    # ユーザー名とパスワードをここに直接記述するのはセキュリティ上良くないですが、
    # 試作段階ではこのように手動で実行するのが最も簡単です。
    # 登録後は以下の2行をコメントアウトするか削除してください。
    # add_admin_user('tto', '55341') # あなたの好きなユーザー名とパスワードを設定
    # print("注意: 管理ユーザー登録スクリプトをコメントアウトするか削除してください。")

    app.run(debug=True, host='0.0.0.0') #公開設定の変更