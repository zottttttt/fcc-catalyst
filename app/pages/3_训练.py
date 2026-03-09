# -*- coding: utf-8 -*-
"""
模型训练管理页面
- 展示当前模型状态（已训练/未训练、R² 表格）
- 支持参数配置，一键训练所有 XGBoost 模型
- 训练完成后保存模型和元数据
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import pandas as pd
import numpy as np
import json
from pathlib import Path
from datetime import datetime
from sklearn.model_selection import train_test_split
from sklearn.metrics import r2_score, mean_absolute_error
from sklearn.preprocessing import LabelEncoder
from xgboost import XGBRegressor

from config import DATA_PATH, MODELS_DIR, PRIORITY_TARGETS, UNRELIABLE_TARGETS, COMP_PREFIXES, OIL_COL
from model_io import load_meta, save_meta, save_label_encoder, models_trained

st.set_page_config(page_title="模型训练 | FCC 催化剂平台", layout="wide")
st.title("模型训练管理")
st.markdown("在此页面训练 XGBoost 模型。训练完成后，预测和优化功能将可用。")

# ── 当前模型状态 ─────────────────────────────────────────
st.subheader("当前模型状态")

if models_trained():
    meta = load_meta()
    train_time = meta.get("train_time", "未知")
    n_targets  = len(meta.get("targets", []))
    st.success(f"模型已就绪 | 训练时间：{train_time} | 覆盖目标：{n_targets} 个")

    r2_data = meta.get("r2", {})
    mae_data = meta.get("mae", {})
    if r2_data:
        rows = []
        for t, r2 in sorted(r2_data.items(), key=lambda x: -x[1]):
            flag = ""
            if t in UNRELIABLE_TARGETS:
                flag = "⚠️ 低可信"
            elif t in PRIORITY_TARGETS:
                flag = "⭐ 核心"
            rows.append({
                "目标变量": t,
                "R²": round(r2, 4),
                "MAE": round(mae_data.get(t, 0), 4),
                "备注": flag,
            })
        df_meta = pd.DataFrame(rows)
        st.dataframe(df_meta, use_container_width=True, hide_index=True)
else:
    st.warning("尚未训练模型，请点击下方「开始训练」按钮")

st.divider()

# ── 训练参数设置 ─────────────────────────────────────────
st.subheader("训练参数设置")

col1, col2, col3, col4 = st.columns(4)
n_est   = col1.number_input("n_estimators（树的数量）", 100, 1000, 300, step=50,
                             help="越大拟合能力越强，但训练越慢")
lr      = col2.number_input("learning_rate（学习率）", 0.01, 0.3, 0.05, step=0.01,
                             format="%.2f", help="建议配合 n_estimators 调节")
depth   = col3.number_input("max_depth（树深度）", 3, 10, 6,
                             help="越深越容易过拟合")
test_r  = col4.slider("测试集比例", 0.1, 0.3, 0.2, step=0.05,
                       help="用于评估模型泛化能力")

st.info(f"将训练数据文件：`{DATA_PATH}`")

# ── 训练按钮 ─────────────────────────────────────────────
st.divider()
train_btn = st.button("开始训练所有模型", type="primary", use_container_width=True)

if train_btn:
    Path(MODELS_DIR).mkdir(exist_ok=True)

    # ─ 加载数据 ─
    status = st.empty()
    prog   = st.progress(0, text="正在加载数据...")
    status.info("正在读取数据文件...")

    try:
        df = pd.read_excel(str(DATA_PATH), sheet_name="ML_data", engine="openpyxl")
    except Exception as e:
        st.error(f"读取数据失败：{e}")
        st.stop()

    status.info(f"数据加载完成：{df.shape[0]} 行 × {df.shape[1]} 列")

    # ─ 特征/目标分离（与 train_xgb_lgb.py 完全一致）─
    target_cols  = [c for c in df.columns if c.startswith("C")]
    feature_cols = [c for c in df.columns if not c.startswith("C")]
    X = df[feature_cols].copy()
    Y = df[target_cols].copy()

    # ─ 配方列 NaN → 0 ─
    for col in feature_cols:
        prefix = col.split("_")[0]
        if prefix in COMP_PREFIXES and col in X.columns:
            X[col] = X[col].fillna(0.0)

    # ─ LabelEncoder ─
    le = LabelEncoder()
    X[OIL_COL] = X[OIL_COL].fillna("未知")
    X[OIL_COL] = le.fit_transform(X[OIL_COL])
    save_label_encoder(le)

    # ─ 逐目标训练 ─
    r2_results, mae_results = {}, {}
    log_rows = []
    targets_to_train = PRIORITY_TARGETS + [c for c in target_cols if c not in PRIORITY_TARGETS]
    targets_in_data  = [t for t in targets_to_train if t in Y.columns]
    n_total = len(targets_in_data)

    log_box = st.empty()

    for i, target in enumerate(targets_in_data):
        pct = (i + 1) / n_total
        prog.progress(pct, text=f"训练中：{target}  ({i+1}/{n_total})")

        y = Y[target]
        valid = y.notna()
        X_use, y_use = X[valid], y[valid]

        if len(y_use) < 50:
            log_rows.append({"目标": target, "状态": "跳过（样本不足）",
                             "R²": "—", "MAE": "—", "样本数": len(y_use)})
            continue

        X_tr, X_te, y_tr, y_te = train_test_split(
            X_use, y_use, test_size=float(test_r), random_state=42)

        model = XGBRegressor(
            n_estimators=int(n_est),
            learning_rate=float(lr),
            max_depth=int(depth),
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42,
            n_jobs=-1,
            verbosity=0,
        )
        model.fit(X_tr, y_tr, eval_set=[(X_te, y_te)], verbose=False)

        y_pred = model.predict(X_te)
        r2  = float(r2_score(y_te, y_pred))
        mae = float(mean_absolute_error(y_te, y_pred))

        r2_results[target]  = round(r2,  4)
        mae_results[target] = round(mae, 4)

        model_path = str(Path(MODELS_DIR) / f"model_xgb_{target}.json")
        model.save_model(model_path)

        log_rows.append({
            "目标": target,
            "状态": "完成",
            "R²": round(r2, 4),
            "MAE": round(mae, 4),
            "样本数": len(y_use),
        })
        log_box.dataframe(pd.DataFrame(log_rows), use_container_width=True, hide_index=True)

    # ─ 保存元数据 ─
    meta = {
        "train_time":    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "n_estimators":  int(n_est),
        "learning_rate": float(lr),
        "max_depth":     int(depth),
        "test_size":     float(test_r),
        "targets":       targets_in_data,
        "r2":            r2_results,
        "mae":           mae_results,
        "feature_order": feature_cols,   # 关键：记录训练时的特征顺序
    }
    save_meta(meta)

    prog.progress(1.0, text="训练完成！")
    status.success(f"全部 {len(r2_results)} 个模型训练完成！模型已保存至 {MODELS_DIR}")

    # 刷新缓存（让预测/优化页面重新加载模型）
    st.cache_data.clear()
    st.cache_resource.clear()

    # ─ 汇总结果 ─
    result_df = pd.DataFrame(log_rows).sort_values("R²", ascending=False)
    st.subheader("训练结果汇总（按 R² 降序）")
    st.dataframe(result_df, use_container_width=True, hide_index=True)
