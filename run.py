# ====================================================
# 0. ライブラリのインポート
# ====================================================
import pandas as pd
import numpy as np
import lightgbm as lgb
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler # オプションでスケーリングを試すため
from sklearn.metrics import r2_score, mean_squared_error
import joblib # モデルの保存・読み込み用
import os

# ====================================================
# 1. データの読み込み
# ====================================================
print("--- ステップ1: データの読み込み ---")
data_path = 'generated_data/learning_data_Z_1_to_100.csv'

if not os.path.exists(data_path):
    print(f"エラー: データファイルが見つかりません。'{data_path}'が存在することを確認してください。")
    exit()

df = pd.read_csv(data_path)
print(f"データセットを読み込みました。総データ件数: {len(df)}")
print("データセットの最初の5行:")
print(df.head())
print("-" * 30)

# ====================================================
# 2. データの前処理 (特徴量とターゲットの定義)
# ====================================================
print("--- ステップ2: データの前処理 ---")
# 特徴量 (X): Z と omega_tau_e
X = df[['Z', 'omega_tau_e']]
# ターゲット (y): Gp_over_Ge と Gpp_over_Ge
y_gp = df['Gp_over_Ge']
y_gpp = df['Gpp_over_Ge']

print(f"特徴量Xの形状: {X.shape}")
print(f"ターゲットy_gpの形状: {y_gp.shape}")
print(f"ターゲットy_gppの形状: {y_gpp.shape}")
print("-" * 30)

# オプション: 特徴量のスケーリング
# LightGBMはスケーリングなしでも動作しますが、ここでは標準的な前処理として適用します。
# スケーラー自体も予測時に必要なので保存します。
scaler = StandardScaler()
X_scaled = scaler.fit_transform(X) # Xをスケーリングし、numpy配列になる
X_scaled_df = pd.DataFrame(X_scaled, columns=X.columns) # 後続のためにDataFrameに戻す
print("特徴量をStandardScalerでスケーリングしました。")
print("スケーリング後の特徴量の最初の5行:")
print(X_scaled_df.head())
print("-" * 30)


# ====================================================
# 3. 訓練データとテストデータへの分割
# ====================================================
print("--- ステップ3: 訓練データとテストデータへの分割 ---")
# スケーリングした特徴量 X_scaled_df を使用
X_train, X_test, y_gp_train, y_gp_test, y_gpp_train, y_gpp_test = train_test_split(
    X_scaled_df, y_gp, y_gpp, test_size=0.2, random_state=42 # 20%をテストデータに
)

print(f"訓練データの件数: {len(X_train)}")
print(f"テストデータの件数: {len(X_test)}")
print("-" * 30)

# ====================================================
# 4. LightGBMモデルの訓練
# ====================================================
print("--- ステップ4: LightGBMモデルの訓練 ---")

# Gp_over_Ge 用モデルの訓練
print("Gp_over_Ge (貯蔵弾性率) 予測モデルを訓練中...")
model_gp = lgb.LGBMRegressor(random_state=42, n_estimators=1000, learning_rate=0.05, num_leaves=31) # ハイパーパラメータを少し調整
model_gp.fit(X_train, y_gp_train)
print("Gp_over_Ge 予測モデルの訓練が完了しました。")

# Gpp_over_Ge 用モデルの訓練
print("Gpp_over_Ge (損失弾性率) 予測モデルを訓練中...")
model_gpp = lgb.LGBMRegressor(random_state=42, n_estimators=1000, learning_rate=0.05, num_leaves=31) # 同様のハイパーパラメータ
model_gpp.fit(X_train, y_gpp_train)
print("Gpp_over_Ge 予測モデルの訓練が完了しました。")
print("-" * 30)

# ====================================================
# 5. モデルの評価
# ====================================================
print("--- ステップ5: モデルの評価 ---")

# Gp_over_Ge モデルの評価
y_gp_pred = model_gp.predict(X_test)
r2_gp = r2_score(y_gp_test, y_gp_pred)
rmse_gp = np.sqrt(mean_squared_error(y_gp_test, y_gp_pred))
print(f"Gp_over_Ge モデルの評価:")
print(f"  R2スコア: {r2_gp:.4f}")
print(f"  RMSE: {rmse_gp:.4e}") # 指数表記で表示

# Gpp_over_Ge モデルの評価
y_gpp_pred = model_gpp.predict(X_test)
r2_gpp = r2_score(y_gpp_test, y_gpp_pred)
rmse_gpp = np.sqrt(mean_squared_error(y_gpp_test, y_gpp_pred))
print(f"Gpp_over_Ge モデルの評価:")
print(f"  R2スコア: {r2_gpp:.4f}")
print(f"  RMSE: {rmse_gpp:.4e}") # 指数表記で表示
print("-" * 30)

# ====================================================
# 6. 訓練済みモデルとスケーラーの保存
# ====================================================
print("--- ステップ6: 訓練済みモデルとスケーラーの保存 ---")
model_output_dir = 'trained_models'
if not os.path.exists(model_output_dir):
    os.makedirs(model_output_dir)

# Gpモデルの保存
joblib.dump(model_gp, os.path.join(model_output_dir, 'lgbm_gp_model.pkl'))
print(f"Gp予測モデルを '{os.path.join(model_output_dir, 'lgbm_gp_model.pkl')}' に保存しました。")

# Gppモデルの保存
joblib.dump(model_gpp, os.path.join(model_output_dir, 'lgbm_gpp_model.pkl'))
print(f"Gpp予測モデルを '{os.path.join(model_output_dir, 'lgbm_gpp_model.pkl')}' に保存しました。")

# スケーラーの保存 (予測時にも同じスケーラーを使うため)
joblib.dump(scaler, os.path.join(model_output_dir, 'scaler.pkl'))
print(f"StandardScalerを '{os.path.join(model_output_dir, 'scaler.pkl')}' に保存しました。")
print("-" * 30)

print("\n--- 機械学習モデルの構築と保存が完了しました！ ---")
print(f"訓練済みモデルとスケーラーは '{model_output_dir}' フォルダに保存されています。")