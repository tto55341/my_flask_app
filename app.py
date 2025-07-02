from flask import Flask, render_template, request, redirect, url_for, send_from_directory
import os
from datetime import datetime
import sqlite3

app = Flask(__name__)
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

@app.route('/')
def index():
    return render_template('upload.html')

@app.route('/data')
def data_list():
    db = get_db()
    # --- ここから修正（検索条件の取得とSQLクエリの変更） ---
    search_device = request.args.get('search_device', '') # 検索フォームから実験装置名を取得
    search_sample = request.args.get('search_sample', '') # 検索フォームからサンプル名を取得

    query = 'SELECT * FROM experiments WHERE 1=1' # 常にTrueの条件で開始
    params = []

    if search_device:
        query += ' AND device_name LIKE ?' # 実験装置名で絞り込み
        params.append(f'%{search_device}%') # 部分一致検索のため % を追加

    if search_sample:
        query += ' AND sample_name LIKE ?' # サンプル名で絞り込み
        params.append(f'%{search_sample}%') # 部分一致検索のため % を追加

    query += ' ORDER BY uploaded_at DESC' # 結果を新しいもの順に並び替え

    experiments = db.execute(query, params).fetchall()
    db.close()
    # --- ここまで修正 ---

    return render_template('data_list.html', 
                           experiments=experiments,
                           search_device=search_device, # 検索フォームに値を保持するため渡す
                           search_sample=search_sample) # 検索フォームに値を保持するため渡す

@app.route('/download/<int:experiment_id>')
def download_file(experiment_id):
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
        init_db()
    # 修正前: app.run(debug=True)
    # 修正後:
    app.run(debug=True, host='0.0.0.0') # ホストを '0.0.0.0' に変更