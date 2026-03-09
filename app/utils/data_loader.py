# -*- coding: utf-8 -*-
"""
数据加载模块：读取 ml_A_all.xlsx，返回预处理后的特征和目标
使用 @st.cache_data 避免重复读取 Excel
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import streamlit as st
from sklearn.preprocessing import LabelEncoder
from config import DATA_PATH, COMP_PREFIXES, OIL_COL


def _get_col_prefix(col_name: str) -> str:
    """从列名中提取前缀，如 'M1-1_S-1土' → 'M1-1'"""
    return col_name.split("_")[0]


def is_comp_col(col_name: str) -> bool:
    """判断是否为配方类特征列（NaN→0）"""
    return _get_col_prefix(col_name) in COMP_PREFIXES


@st.cache_data(show_spinner="正在加载训练数据...")
def load_training_data():
    """
    读取 ml_A_all.xlsx，返回 (X_df, Y_df, le, oil_classes, feature_cols, target_cols)
    - X_df: 已预处理的特征 DataFrame（组成列NaN→0，oil已编码）
    - Y_df: 目标变量 DataFrame
    - le: 已拟合的 LabelEncoder（用于推理时编码）
    - oil_classes: 原料油类别列表
    - feature_cols: 特征列名列表（顺序与训练时一致）
    - target_cols: 目标列名列表
    """
    df = pd.read_excel(str(DATA_PATH), sheet_name="ML_data", engine="openpyxl")

    # 分离特征列和目标列（与 train_xgb_lgb.py 逻辑一致）
    target_cols  = [c for c in df.columns if c.startswith("C")]
    feature_cols = [c for c in df.columns if not c.startswith("C")]

    X = df[feature_cols].copy()
    Y = df[target_cols].copy()

    # 配方列 NaN → 0（未添加该组分 = 0，符合催化剂配方逻辑）
    for col in feature_cols:
        if is_comp_col(col) and col in X.columns:
            X[col] = X[col].fillna(0.0)

    # 编码原料油
    le = LabelEncoder()
    X[OIL_COL] = X[OIL_COL].fillna("未知")
    X[OIL_COL] = le.fit_transform(X[OIL_COL])

    oil_classes = le.classes_.tolist()
    return X, Y, le, oil_classes, feature_cols, target_cols


def get_feature_groups(feature_cols: list) -> dict:
    """
    将特征列按组分类，返回 {组名: [列名列表]}
    组名：M, FM, Z, FZ, L, T, oil
    """
    from config import GROUP_PREFIXES, L_PREFIXES, T_COLS, OIL_COL
    groups = {g: [] for g in ["M", "FM", "Z", "FZ", "L", "T", "oil"]}

    for col in feature_cols:
        if col == OIL_COL:
            groups["oil"].append(col)
        elif col in T_COLS:
            groups["T"].append(col)
        else:
            prefix = _get_col_prefix(col)
            matched = False
            for group_name, prefixes in GROUP_PREFIXES.items():
                if prefix in prefixes:
                    groups[group_name].append(col)
                    matched = True
                    break
            if not matched and prefix in L_PREFIXES:
                groups["L"].append(col)

    return groups


def get_data_bounds(X: pd.DataFrame, feature_cols: list) -> dict:
    """
    从训练数据中推导各特征的实际范围，用于 UI 输入限制
    返回 {列名: (min, max, median)}
    """
    bounds = {}
    for col in feature_cols:
        col_data = X[col].dropna()
        if len(col_data) == 0:
            bounds[col] = (0.0, 100.0, 0.0)
        else:
            bounds[col] = (
                float(col_data.min()),
                float(col_data.max()),
                float(col_data.median()),
            )
    return bounds
