# -*- coding: utf-8 -*-
"""
FCC 催化剂产率预测 - XGBoost + LightGBM 双模型对比
项目结构：
  /nesi/project/uoa04367/PROJECT-04367/FCC-AI/
  ├── data/ml_A_all.xlsx  <- 输入数据
  ├── logs/                        <- 日志、图片、CSV 输出
  ├── models/                      <- 模型文件输出
  ├── src/train_xgb_lgb.py         <- 本脚本
  └── venv/                        <- Python 虚拟环境
"""

# ── 导入库 ──────────────────────────────────────────────
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path
from sklearn.model_selection import train_test_split
from sklearn.metrics import r2_score, mean_absolute_error
from sklearn.preprocessing import LabelEncoder
from xgboost import XGBRegressor
from lightgbm import LGBMRegressor

# ── 路径配置 ─────────────────────────────────────────────
ROOT       = Path(__file__).resolve().parent.parent
DATA_DIR   = ROOT / "data"
LOGS_DIR   = ROOT / "logs"
MODELS_DIR = ROOT / "models"
LOGS_DIR.mkdir(exist_ok=True)
MODELS_DIR.mkdir(exist_ok=True)

# ── 1. 读取数据 ──────────────────────────────────────────
print("=" * 60)
print("FCC 催化剂产率预测 - XGBoost + LightGBM 双模型")
print("=" * 60)
df = pd.read_excel(DATA_DIR / "ml_A_all.xlsx", sheet_name="ML_data")
print(f"数据维度: {df.shape[0]} 行 x {df.shape[1]} 列")

# ── 2. 分离特征和目标 ────────────────────────────────────
target_cols  = [c for c in df.columns if c.startswith("C")]
feature_cols = [c for c in df.columns if not c.startswith("C")]
X = df[feature_cols].copy()
Y = df[target_cols].copy()
print(f"特征: {len(feature_cols)} 列  |  目标: {len(target_cols)} 列")

# ── 3. 编码原料油 ────────────────────────────────────────
le = LabelEncoder()
X["oil_原料油"] = X["oil_原料油"].fillna("未知")
X["oil_原料油"] = le.fit_transform(X["oil_原料油"])

# ── 4. 循环训练每个目标 ──────────────────────────────────
summary = []

# 优先训练这些核心目标
priority = ["C4_汽油", "C9_转化率", "C3_液化气",
            "C1_焦炭", "C5_柴油",   "C8_总液收"]
all_targets = priority + [c for c in target_cols if c not in priority]

for target_name in all_targets:
    print(f"\n--- 训练目标: {target_name} ---")

    y = Y[target_name]
    valid = y.notna()
    X_use, y_use = X[valid], y[valid]

    if len(y_use) < 50:
        print(f"  样本不足 ({len(y_use)})，跳过")
        continue

    X_train, X_test, y_train, y_test = train_test_split(
        X_use, y_use, test_size=0.2, random_state=42)

    # ── XGBoost ──────────────────────────────────────────
    xgb = XGBRegressor(
        n_estimators=300, learning_rate=0.05, max_depth=6,
        subsample=0.8, colsample_bytree=0.8,
        random_state=42, n_jobs=-1, verbosity=0)
    xgb.fit(X_train, y_train,
            eval_set=[(X_test, y_test)], verbose=False)
    y_xgb    = xgb.predict(X_test)
    r2_xgb   = r2_score(y_test, y_xgb)
    mae_xgb  = mean_absolute_error(y_test, y_xgb)
    rmse_xgb = float(np.sqrt(np.mean((y_test - y_xgb) ** 2)))
    print(f"  XGB  R2={r2_xgb:.4f}  MAE={mae_xgb:.4f}  RMSE={rmse_xgb:.4f}")

    # ── LightGBM ─────────────────────────────────────────
    lgb = LGBMRegressor(
        n_estimators=300, learning_rate=0.05, max_depth=6,
        subsample=0.8, colsample_bytree=0.8,
        random_state=42, n_jobs=-1, verbose=-1)
    lgb.fit(X_train, y_train)
    y_lgb    = lgb.predict(X_test)
    r2_lgb   = r2_score(y_test, y_lgb)
    mae_lgb  = mean_absolute_error(y_test, y_lgb)
    rmse_lgb = float(np.sqrt(np.mean((y_test - y_lgb) ** 2)))
    print(f"  LGB  R2={r2_lgb:.4f}  MAE={mae_lgb:.4f}  RMSE={rmse_lgb:.4f}")

    best = "XGB" if r2_xgb >= r2_lgb else "LGB"
    print(f"  最佳模型: {best}")

    # 保存模型
    xgb.save_model(MODELS_DIR / f"model_xgb_{target_name}.json")
    lgb.booster_.save_model(str(MODELS_DIR / f"model_lgb_{target_name}.txt"))

    # 保存预测结果
    pd.DataFrame({
        "实际值":    y_test.values,
        "XGB预测值": y_xgb,
        "LGB预测值": y_lgb,
    }).to_csv(LOGS_DIR / f"result_{target_name}.csv", index=False)

    # 特征重要性（XGB）
    imp_xgb = pd.DataFrame({
        "特征":      X_use.columns.tolist(),
        "XGB重要性": xgb.feature_importances_,
    }).sort_values("XGB重要性", ascending=False)
    imp_xgb.to_csv(LOGS_DIR / f"importance_xgb_{target_name}.csv", index=False)

    # 特征重要性（LGB）
    imp_lgb = pd.DataFrame({
        "特征":      X_use.columns.tolist(),
        "LGB重要性": lgb.feature_importances_,
    }).sort_values("LGB重要性", ascending=False)
    imp_lgb.to_csv(LOGS_DIR / f"importance_lgb_{target_name}.csv", index=False)

    # 重点目标：XGB vs LGB 双图对比
    if target_name in priority:
        fig, axes = plt.subplots(1, 2, figsize=(18, 7))
        for ax, imp, label, color in zip(
            axes,
            [imp_xgb.rename(columns={"XGB重要性": "重要性"}),
             imp_lgb.rename(columns={"LGB重要性": "重要性"})],
            ["XGBoost", "LightGBM"],
            ["#2E74B5", "#E87722"],
        ):
            top = imp.head(15)
            ax.barh(top["特征"][::-1], top["重要性"][::-1], color=color)
            ax.set_xlabel("重要性得分")
            ax.set_title(f"{target_name} - {label} Top15 特征重要性")
        plt.tight_layout()
        plt.savefig(LOGS_DIR / f"importance_{target_name}.png", dpi=150)
        plt.close()

    summary.append({
        "目标变量":   target_name,
        "样本数":     len(y_use),
        "XGB_R2":     round(r2_xgb,  4),
        "XGB_MAE":    round(mae_xgb,  4),
        "XGB_RMSE":   round(rmse_xgb, 4),
        "LGB_R2":     round(r2_lgb,  4),
        "LGB_MAE":    round(mae_lgb,  4),
        "LGB_RMSE":   round(rmse_lgb, 4),
        "最佳模型":   best,
    })

# ── 5. 汇总结果 ──────────────────────────────────────────
summary_df = pd.DataFrame(summary)
summary_df.to_csv(LOGS_DIR / "summary_xgb_vs_lgb.csv", index=False)

print("\n" + "=" * 60)
print("全部完成！")
print(f"  模型文件 -> {MODELS_DIR}")
print(f"  图片/CSV -> {LOGS_DIR}")
print("\nXGBoost vs LightGBM 汇总：")
print(summary_df.to_string(index=False))
