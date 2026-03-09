# -*- coding: utf-8 -*-
"""
Plotly 图表封装模块
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import plotly.graph_objects as go
import plotly.express as px
import pandas as pd


def prediction_bar_chart(predictions: dict, r2_dict: dict,
                          unreliable: list = None) -> go.Figure:
    """
    预测结果水平条形图。颜色深浅反映 R² 可信度，低可信目标用橙色标注。
    """
    unreliable = unreliable or []
    targets = list(predictions.keys())
    values  = [predictions[t] for t in targets]
    r2s     = [r2_dict.get(t, 0) for t in targets]

    colors = []
    for t, r2 in zip(targets, r2s):
        if t in unreliable:
            colors.append("rgba(220,80,60,0.6)")
        else:
            alpha = max(0.3, min(1.0, r2))
            colors.append(f"rgba(46,116,181,{alpha:.2f})")

    fig = go.Figure(go.Bar(
        y=targets,
        x=values,
        orientation="h",
        marker_color=colors,
        text=[f"{v:.2f}%" for v in values],
        textposition="outside",
        hovertemplate=(
            "<b>%{y}</b><br>"
            "预测值: %{x:.4f}%<br>"
            "模型 R²: %{customdata:.3f}<extra></extra>"
        ),
        customdata=r2s,
    ))
    fig.update_layout(
        title="全部目标产率预测结果",
        xaxis_title="产率 (%)",
        yaxis_title="",
        yaxis=dict(autorange="reversed"),
        height=max(400, len(targets) * 25),
        margin=dict(l=180, r=80, t=50, b=40),
        plot_bgcolor="white",
        xaxis=dict(gridcolor="#eee"),
    )
    return fig


def optimization_history_chart(trials_values: list) -> go.Figure:
    """
    Optuna 优化历史曲线。
    trials_values: [(trial_num, value), ...]
    """
    if not trials_values:
        return go.Figure()

    nums   = [x[0] for x in trials_values]
    values = [x[1] for x in trials_values]

    # 计算历史最优（最小化方向）
    best_so_far = []
    cur_best = float("inf")
    for v in values:
        cur_best = min(cur_best, v)
        best_so_far.append(cur_best)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=nums, y=values,
        mode="markers", name="每次试验",
        marker=dict(color="lightblue", size=6), opacity=0.6,
    ))
    fig.add_trace(go.Scatter(
        x=nums, y=best_so_far,
        mode="lines", name="历史最优",
        line=dict(color="navy", width=2),
    ))
    fig.update_layout(
        title="优化进程",
        xaxis_title="试验次数",
        yaxis_title="目标函数值（越小越好）",
        height=350,
        plot_bgcolor="white",
        xaxis=dict(gridcolor="#eee"),
        yaxis=dict(gridcolor="#eee"),
    )
    return fig


def importance_bar_chart(importance_df: pd.DataFrame,
                          target_name: str = "") -> go.Figure:
    """
    特征重要性横向柱状图（Top 15）
    importance_df 需包含 '特征' 和 'XGB重要性' 两列
    """
    top = importance_df.head(15).copy()
    fig = px.bar(
        top, x="XGB重要性", y="特征", orientation="h",
        title=f"特征重要性 Top 15{' — ' + target_name if target_name else ''}",
        color="XGB重要性",
        color_continuous_scale="Blues",
    )
    fig.update_layout(
        yaxis=dict(autorange="reversed"),
        height=420,
        showlegend=False,
        plot_bgcolor="white",
    )
    return fig


def scatter_actual_vs_pred(actual: list, predicted: list,
                            target_name: str = "") -> go.Figure:
    """实际值 vs 预测值散点图"""
    fig = go.Figure()
    all_vals = actual + predicted
    lo, hi = min(all_vals), max(all_vals)
    # 对角线（完美预测）
    fig.add_trace(go.Scatter(
        x=[lo, hi], y=[lo, hi],
        mode="lines", name="理想线",
        line=dict(color="red", dash="dash"),
    ))
    fig.add_trace(go.Scatter(
        x=actual, y=predicted,
        mode="markers", name="预测点",
        marker=dict(color="steelblue", size=5, opacity=0.7),
    ))
    fig.update_layout(
        title=f"实际值 vs 预测值{' — ' + target_name if target_name else ''}",
        xaxis_title="实际值 (%)",
        yaxis_title="预测值 (%)",
        height=400,
        plot_bgcolor="white",
    )
    return fig
