# -*- coding: utf-8 -*-
"""
可复用特征输入 UI 组件
供预测页面和优化页面共用
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import pandas as pd


def render_comp_group(group_label: str, col_list: list, defaults: dict = None,
                      key_prefix: str = "") -> dict:
    """
    渲染一个配方组（M/FM/Z/FZ）的数值输入。
    空/0 表示该组分未添加。
    返回 {列名: 数值}
    """
    if not col_list:
        st.info(f"{group_label}：无可用列")
        return {}

    result = {}
    cols_per_row = 4
    rows = [col_list[i:i+cols_per_row] for i in range(0, len(col_list), cols_per_row)]

    for row_cols in rows:
        grid = st.columns(len(row_cols))
        for j, col_name in enumerate(row_cols):
            # 显示名：去掉前缀编号，只显示中文名
            parts = col_name.split("_", 1)
            display = parts[1] if len(parts) > 1 else col_name
            short   = f"{parts[0]}\n{display[:8]}" if len(display) > 8 else f"{parts[0]} {display}"
            default = float(defaults.get(col_name, 0.0)) if defaults else 0.0
            val = grid[j].number_input(
                short,
                min_value=0.0, max_value=100.0,
                value=default, step=1.0,
                key=f"{key_prefix}comp_{col_name}",
                help=col_name,
            )
            result[col_name] = val

    return result


def render_property_group(col_list: list, bounds: dict, defaults: dict = None,
                          key_prefix: str = "") -> dict:
    """
    渲染理化性质组（L特征）的数值输入。
    bounds: {列名: (min, max, median)}
    返回 {列名: 值或None}
    """
    if not col_list:
        return {}

    result = {}
    grid = st.columns(min(len(col_list), 4))
    for i, col_name in enumerate(col_list):
        parts = col_name.split("_", 1)
        display = parts[1] if len(parts) > 1 else col_name
        lo, hi, med = bounds.get(col_name, (0.0, 100.0, 0.0))
        default = float(defaults.get(col_name, med)) if defaults else med

        # 计算合理步长
        rng = hi - lo
        step = 0.01 if rng <= 1 else (0.1 if rng <= 10 else 1.0)

        val = grid[i % 4].number_input(
            display,
            min_value=float(lo),
            max_value=float(hi),
            value=float(default),
            step=step,
            format="%.3f" if step < 0.1 else "%.2f",
            key=f"{key_prefix}prop_{col_name}",
            help=f"{col_name}\n数据范围：[{lo:.3f}, {hi:.3f}]",
        )
        result[col_name] = val

    return result


def render_condition_group(t_cols: list, bounds: dict, defaults: dict = None,
                           key_prefix: str = "", disabled: bool = False) -> dict:
    """
    渲染操作条件组（T1/T2）
    """
    result = {}
    grid = st.columns(len(t_cols))
    for i, col_name in enumerate(t_cols):
        lo, hi, med = bounds.get(col_name, (400.0, 600.0, 500.0))
        default = float(defaults.get(col_name, med)) if defaults else med
        rng = hi - lo
        step = 1.0 if rng > 10 else 0.1
        val = grid[i].number_input(
            col_name,
            min_value=float(lo), max_value=float(hi),
            value=float(default), step=step,
            key=f"{key_prefix}cond_{col_name}",
            disabled=disabled,
        )
        result[col_name] = val
    return result


def build_predict_input(feat_values: dict, le, feature_order: list) -> pd.DataFrame:
    """
    将 UI 输入合并为模型可用的 1行 DataFrame。
    feat_values: {列名: 值}（oil 为字符串，其他为浮点）
    le: 已拟合的 LabelEncoder
    feature_order: 训练时的特征列顺序（来自 training_meta.json）
    """
    from config import OIL_COL
    row = {}
    for col in feature_order:
        if col == OIL_COL:
            oil_str = str(feat_values.get(col, "未知") or "未知")
            if oil_str in le.classes_:
                row[col] = int(le.transform([oil_str])[0])
            else:
                row[col] = int(le.transform(["未知"])[0]) if "未知" in le.classes_ else 0
        else:
            val = feat_values.get(col)
            row[col] = float(val) if val is not None else float("nan")
    return pd.DataFrame([row])
