# ====================================================
# 0. アプリケーション開発に必要なライブラリの読み込み
# ====================================================
from flask import Flask, render_template, request, redirect, url_for, send_from_directory, flash, session
import os
from datetime import datetime
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
import pandas as pd
import joblib # 機械学習モデルの読み込み用
import numpy as np # 数値計算用

# ====================================================
# 1. アプリケーションの初期設定
# ====================================================

# Flaskアプリケーションのインスタンス作成
app = Flask(__name__)

# ユーザーセッション保護のためのSECRET_KEYを設定
app.config['SECRET_KEY'] = os.urandom(24).hex() 

# ファイルを保存するフォルダの設定
UPLOAD_FOLDER = 'uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# データベースファイルの定義
DATABASE = 'database.db'

# 機械学習モデルとスケーラーの読み込み
# アプリケーション起動時に一度だけ実行される
MODEL_DIR = 'trained_models'
GP_MODEL_PATH = os.path.join(MODEL_DIR, 'lgbm_gp_model.pkl')
GPP_MODEL_PATH = os.path.join(MODEL_DIR, 'lgbm_gpp_model.pkl')
SCALER_PATH = os.path.join(MODEL_DIR, 'scaler.pkl')

# モデルとスケーラーをグローバル変数として保持
# アプリケーション起動時に存在しない場合はエラーを出す
try:
    if not os.path.exists(GP_MODEL_PATH) or \
       not os.path.exists(GPP_MODEL_PATH) or \
       not os.path.exists(SCALER_PATH):
        raise FileNotFoundError("機械学習モデルまたはスケーラーファイルが見つかりません。'run.py'を実行してモデルを生成してください。")
        
    loaded_gp_model = joblib.load(GP_MODEL_PATH)
    loaded_gpp_model = joblib.load(GPP_MODEL_PATH)
    loaded_scaler = joblib.load(SCALER_PATH)
    print("機械学習モデルとスケーラーを正常に読み込みました。")
except FileNotFoundError as e:
    print(f"モデル読み込みエラー: {e}")
    loaded_gp_model = None
    loaded_gpp_model = None
    loaded_scaler = None
except Exception as e:
    print(f"モデル読み込み中に予期せぬエラーが発生しました: {e}")
    loaded_gp_model = None
    loaded_gpp_model = None
    loaded_scaler = None

# ====================================================
# 2. データベースの初期設定
# ====================================================

# アプリケーションとデータベースの接続
def get_db():
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    return db

# 実験データ用テーブル（experiments）の設定
def init_ex_db():
    with app.app_context():
        db = get_db()
        with open('schema.sql', 'r') as f:
            db.executescript(f.read())
        db.commit()

# ユーザー情報用テーブル（users）の設定
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

# 管理者登録
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


# ====================================================
# 3. ルーティング設定
# ====================================================

# ホームページの設定
@app.route('/')
def index():
    if session.get('logged_in'):
        return render_template('upload.html')
    else:
        flash('ログインが必要です。')
        return redirect(url_for('login'))

# ログインページの設定
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        db = get_db()
        user = db.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        db.close()

        if user and check_password_hash(user['password'], password):
            session['logged_in'] = True
            flash('ログインしました！')
            return redirect(url_for('index'))
        else:
            flash('ユーザー名またはパスワードが間違っています。')
    return render_template('login.html')

# ログアウト設定
@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    flash('ログアウトしました。')
    return redirect(url_for('login'))

# データ一覧ページの設定
@app.route('/data')
def data_list():

    if not session.get('logged_in'):
        flash('ログインが必要です。')
        return redirect(url_for('login'))
 
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

# ファイルダウンロード機能
@app.route('/download/<int:experiment_id>')
def download_file(experiment_id):
    # ログインチェック
    if not session.get('logged_in'):
        flash('ログインが必要です。')
        return redirect(url_for('login'))

    db = get_db()
    experiment = db.execute('SELECT file_name, file_path FROM experiments WHERE id = ?', (experiment_id,)).fetchone()
    db.close()

    if experiment:
        directory = os.path.dirname(experiment['file_path'])
        filename = os.path.basename(experiment['file_path'])
        
        absolute_upload_folder = os.path.abspath(app.config['UPLOAD_FOLDER'])
        absolute_filepath = os.path.abspath(experiment['file_path'])

        # ダウンロードするファイルがuploadsフォルダ内に存在するか安全性をチェック
        if os.path.commonpath([absolute_upload_folder, absolute_filepath]) == absolute_upload_folder:
            print(f"ダウンロードリクエスト: {filename} from {directory}")
            # 指定されたディレクトリからファイルを送信（as_attachment=Trueでダウンロードを強制）
            return send_from_directory(directory, filename, as_attachment=True)
        else:
            return "ファイルパスが不正です。", 400
    return "ファイルが見つかりません。", 404

# ファイルアップロード機能
@app.route('/upload', methods=['POST'])
def upload_file():
    # ログインチェック
    if not session.get('logged_in'):
        flash('ログインが必要です。')
        return redirect(url_for('login'))

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

# データ分析ページの設定
@app.route('/analyze', methods=['GET', 'POST'])
def analyze_data():
    if not session.get('logged_in'):
        flash('ログインが必要です。')
        return redirect(url_for('login'))

    # 機械学習モデルがロードされていない場合はエラーメッセージを表示
    if loaded_gp_model is None or loaded_gpp_model is None or loaded_scaler is None:
        flash("エラー: 機械学習モデルが読み込まれていません。管理者にお問い合わせください。", "error")
        return render_template('analyze.html', ml_error=True)

    prediction_results = {}
    analysis_result = {} # 既存のデータ結合表示用
    
    if request.method == 'POST':
        # --- ここから既存のデータ分析・結合ロジック ---
        # フォームからの入力を取得（既存の分析ページ機能）
        device_name = request.form.get('device_name', '')
        sample_name = request.form.get('sample_name', '')

        db = get_db()
        query = "SELECT * FROM experiments WHERE device_name LIKE ? AND sample_name LIKE ?"
        params = [f"%{device_name}%", f"%{sample_name}%"]
        
        experiments = db.execute(query, params).fetchall()
        db.close()
        
        all_data_frames = [] # 複数のデータフレームを一時的に格納するリスト
        
        if experiments:
            for exp in experiments:
                file_path = exp['file_path'] # データベースからファイルパスを取得
                try:
                    # ファイルの拡張子に基づいて読み込み方法を判断
                    if file_path.endswith('.xlsx'):
                        df = pd.read_excel(file_path)
                    elif file_path.endswith('.csv'):
                        try:
                            df = pd.read_csv(file_path, encoding='shift_jis')
                        except UnicodeDecodeError:
                            try:
                                df = pd.read_csv(file_path, encoding='cp932')
                            except UnicodeDecodeError:
                                df = pd.read_csv(file_path, encoding='utf-8')
                    else:
                        flash(f"未対応のファイル形式: {file_path}", "warning")
                        continue # 次のファイルへ

                    all_data_frames.append(df) # 読み込んだデータフレームをリストに追加

                except FileNotFoundError:
                    flash(f"エラー: ファイルが見つかりません - {file_path}", "error")
                except Exception as e:
                    flash(f"エラー: ファイル '{file_path}' の読み込み中に問題が発生しました - {e}", "error")
            
            # すべてのデータフレームを結合
            if all_data_frames:
                combined_df = pd.concat(all_data_frames, ignore_index=True)
                flash(f"すべてのファイルを結合しました。総データ件数: {len(combined_df)}", "success")

                # ここで結合されたcombined_dfを使った分析ロジックが続く
                # とりあえず、結合データの最初の5行と統計情報を表示してみる
                analysis_result = {
                    'message': 'データ結合が成功しました。',
                    'head': combined_df.head().to_html(classes='table table-striped'), # 最初の5行をHTMLテーブル形式で
                    'description': combined_df.describe().to_html(classes='table table-striped') # 統計情報をHTMLテーブル形式で
                }
            else:
                flash("条件に一致するファイルを読み込めませんでした。", "error")
                analysis_result = {'message': 'ファイル読み込み失敗'}
        else:
            flash("条件に一致する実験データが見つかりませんでした。", "error")
            analysis_result = {'message': 'データなし'}
        # --- ここまで既存のデータ分析・結合ロジック ---


        # --- ここから機械学習予測ロジックを追加 ---
        try:
            # フォームからZとomega_tau_eを取得
            input_z = float(request.form['predict_z_value'])
            input_omega = float(request.form['predict_omega_value'])

            # 入力値をnumpy配列に変換し、スケーリング
            # scalerは2つの特徴量 (Z, omega_tau_e) を期待するので、それに合わせた形状にする
            input_data = np.array([[input_z, input_omega]])
            scaled_input_data = loaded_scaler.transform(input_data)

            # モデルで予測
            predicted_gp_over_ge = loaded_gp_model.predict(scaled_input_data)[0]
            predicted_gpp_over_ge = loaded_gpp_model.predict(scaled_input_data)[0]

            prediction_results = {
                'input_z': input_z,
                'input_omega': input_omega,
                'predicted_gp_over_ge': f"{predicted_gp_over_ge:.4e}", # 指数表記で表示
                'predicted_gpp_over_ge': f"{predicted_gpp_over_ge:.4e}" # 指数表記で表示
            }

        except ValueError:
            flash("予測のためのZまたはOmegaの値が不正です。数値を入力してください。", "error")
        except Exception as e:
            flash(f"予測中にエラーが発生しました: {e}", "error")
        # --- ここまで機械学習予測ロジック ---

    # GETリクエストの場合、またはPOSTリクエスト後のレンダリング
    return render_template('analyze.html',
                           analysis_result=analysis_result,
                           prediction_results=prediction_results)

# ====================================================
# 4. アプリケーションの実行設定
# ====================================================

if __name__ == '__main__':
    if not os.path.exists(DATABASE):
        init_ex_db
    init_user_db()

    # add_admin_user('tto', '55341') 
  
    app.run(debug=True, host='0.0.0.0') 