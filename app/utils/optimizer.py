# -*- coding: utf-8 -*-
"""
Optuna 贝叶斯优化核心模块
用于反向设计：给定目标产率约束，搜索最优催化剂配方
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
import optuna
from typing import Callable

optuna.logging.set_verbosity(optuna.logging.WARNING)


def build_objective(
    models: dict,
    objectives: list,
    fixed_features: dict,
    feature_order: list,
    search_cfg: dict,
) -> Callable:
    """
    构建 Optuna 目标函数（统一最小化方向）。

    参数：
    - models: {target_name: XGBRegressor}
    - objectives: [{"target": str, "direction": "maximize"|"minimize", "weight": float}, ...]
    - fixed_features: {列名: 值}（不参与优化的特征，如固定T1/T2/oil）
    - feature_order: 训练时的特征列顺序
    - search_cfg: {
        "active_groups": ["M","FM","Z","FZ"],  # 参与优化的配方组
        "optimize_L": bool,                     # 是否优化理化性质
        "optimize_T": bool,                     # 是否优化操作条件
        "l_bounds": {col: (lo,hi,step)},        # L列搜索边界
        "t_bounds": {col: (lo,hi,step)},        # T列搜索边界
        "comp_cols_by_group": {group: [cols]},  # 各组的列名
        "l_cols": [cols],                       # L列名
        "t_cols": [cols],                       # T列名
      }
    """
    active_groups       = search_cfg.get("active_groups", [])
    optimize_L          = search_cfg.get("optimize_L", False)
    optimize_T          = search_cfg.get("optimize_T", False)
    l_bounds            = search_cfg.get("l_bounds", {})
    t_bounds            = search_cfg.get("t_bounds", {})
    comp_cols_by_group  = search_cfg.get("comp_cols_by_group", {})
    l_cols              = search_cfg.get("l_cols", [])
    t_cols              = search_cfg.get("t_cols", [])

    def objective(trial):
        params = {}

        # 1. 配方特征（按激活组）
        for group in active_groups:
            for col in comp_cols_by_group.get(group, []):
                params[col] = trial.suggest_float(col, 0.0, 100.0, step=0.5)

        # 2. 理化性质
        if optimize_L:
            for col in l_cols:
                lo, hi, step = l_bounds.get(col, (0.0, 100.0, 1.0))
                params[col] = trial.suggest_float(col, lo, hi, step=step)
        else:
            for col in l_cols:
                params[col] = fixed_features.get(col, np.nan)

        # 3. 操作条件
        if optimize_T:
            for col in t_cols:
                lo, hi, step = t_bounds.get(col, (400.0, 600.0, 1.0))
                params[col] = trial.suggest_float(col, lo, hi, step=step)
        else:
            for col in t_cols:
                params[col] = fixed_features.get(col, 500.0 if "T1" in col else 6.0)

        # 4. 未参与优化的特征使用固定值
        for col in feature_order:
            if col not in params:
                params[col] = fixed_features.get(col, 0.0)

        # 5. 组合为 DataFrame（保证特征顺序）
        row = {}
        for col in feature_order:
            val = params.get(col)
            row[col] = float(val) if val is not None and not (
                isinstance(val, float) and np.isnan(val)) else np.nan
        X = pd.DataFrame([row])

        # 6. 计算加权目标函数（统一最小化）
        total_score = 0.0
        for obj in objectives:
            t_name    = obj["target"]
            direction = obj["direction"]
            weight    = float(obj["weight"])
            if t_name not in models or weight == 0:
                continue
            pred = float(models[t_name].predict(X)[0])
            # maximize → 取负号
            score = -pred if direction == "maximize" else pred
            total_score += weight * score

        return total_score

    return objective


def run_optimization(
    study: optuna.Study,
    objective: Callable,
    n_trials: int,
    progress_callback=None,
) -> optuna.Study:
    """
    逐步执行优化，支持 Streamlit 进度回调。
    progress_callback(trial_num, n_trials, best_value, trials_log)
    trials_log: [(trial_num, value), ...]
    """
    trials_log = []
    for i in range(n_trials):
        study.optimize(objective, n_trials=1, show_progress_bar=False)
        last = study.trials[-1]
        if last.value is not None:
            trials_log.append((last.number, last.value))
        if progress_callback:
            best_val = study.best_value if study.best_trial else None
            progress_callback(i + 1, n_trials, best_val, list(trials_log))
    return study


def build_search_cfg(feature_order: list, groups: dict, search_cfg_input: dict) -> dict:
    """
    从 UI 输入构建完整的 search_cfg 字典。
    groups: get_feature_groups() 的返回值 {组名: [列名]}
    search_cfg_input: UI 收集的配置
    """
    from config import PROPERTY_BOUNDS_BY_PREFIX, T_BOUNDS

    active_groups = search_cfg_input.get("active_groups", ["M", "FM", "Z", "FZ"])

    # 各组的列名
    comp_cols_by_group = {g: groups.get(g, []) for g in ["M", "FM", "Z", "FZ"]}

    l_cols = groups.get("L", [])
    t_cols = groups.get("T", [])

    # L列边界：按前缀匹配
    l_bounds = {}
    for col in l_cols:
        prefix = col.split("_")[0]
        l_bounds[col] = PROPERTY_BOUNDS_BY_PREFIX.get(prefix, (0.0, 100.0, 1.0))

    # T列边界
    t_bounds = {}
    for col in t_cols:
        t_bounds[col] = T_BOUNDS.get(col, (400.0, 600.0, 1.0))

    return {
        "active_groups":      active_groups,
        "optimize_L":         search_cfg_input.get("optimize_L", False),
        "optimize_T":         search_cfg_input.get("optimize_T", False),
        "l_bounds":           l_bounds,
        "t_bounds":           t_bounds,
        "comp_cols_by_group": comp_cols_by_group,
        "l_cols":             l_cols,
        "t_cols":             t_cols,
    }
