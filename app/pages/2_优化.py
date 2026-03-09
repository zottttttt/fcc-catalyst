# -*- coding: utf-8 -*-
"""
反向设计页面（Bayesian 优化）
设定目标产率 + 权重 → Optuna 搜索最优催化剂配方
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import pandas as pd
import numpy as np
import optuna

from config import PRIORITY_TARGETS, UNRELIABLE_TARGETS, OIL_COL
from model_io import models_trained, load_all_models, load_meta, load_label_encoder
from utils.data_loader import load_training_data, get_feature_groups, get_data_bounds
from utils.feature_ui import render_condition_group, render_property_group, build_predict_input
from utils.charts import optimization_history_chart
from utils.optimizer import build_objective, build_search_cfg, run_optimization

st.set_page_config(page_title="反向设计 | FCC 催化剂平台", layout="wide")
st.title("FCC 催化剂反向设计")
st.markdown("设定目标产率，系统通过贝叶斯优化自动搜索最优催化剂配方。")

# ── 检查模型状态 ─────────────────────────────────────────
if not models_trained():
    st.error("尚未训练模型，请先前往「模型训练」页面完成训练。")
    st.stop()

# ── 加载模型和元数据 ──────────────────────────────────────
@st.cache_resource(show_spinner="正在加载模型...")
def _load_models():
    return load_all_models()

models       = _load_models()
meta         = load_meta()
feature_order = meta.get("feature_order", [])
r2_dict      = meta.get("r2", {})
target_cols  = meta.get("targets", list(models.keys()))

X_df, Y_df, le, oil_classes, feat_cols, _ = load_training_data()
use_order = feature_order if feature_order else feat_cols
groups    = get_feature_groups(use_order)
bounds    = get_data_bounds(X_df, use_order)

# ═══════════════════════════════════════════════════════════
# 步骤 1：设置优化目标
# ═══════════════════════════════════════════════════════════
st.subheader("第一步：设置优化目标")
st.caption("选择要优化的目标，设置方向（最大化/最小化）和权重（相对重要性）")

objectives = []
# 先显示核心目标，再显示其余
display_order = PRIORITY_TARGETS + [t for t in target_cols if t not in PRIORITY_TARGETS]

with st.expander("展开目标设置", expanded=True):
    header_cols = st.columns([3, 2, 3, 1])
    header_cols[0].markdown("**目标变量**")
    header_cols[1].markdown("**方向**")
    header_cols[2].markdown("**权重**")
    header_cols[3].markdown("**启用**")

    for t in display_order:
        if t not in target_cols:
            continue
        r2  = r2_dict.get(t, 0)
        bad = t in UNRELIABLE_TARGETS
        label = f"{t}  (R²={r2:.3f})" + ("  ⚠️" if bad else ("  ⭐" if t in PRIORITY_TARGETS else ""))

        c0, c1, c2, c3 = st.columns([3, 2, 3, 1])
        c0.markdown(f"{'🔴' if bad else '🟢'} {label}")
        direction = c1.selectbox("", ["最大化", "最小化"],
                                  key=f"opt_dir_{t}",
                                  label_visibility="collapsed")
        weight = c2.slider("", 0.0, 2.0, 0.0 if bad else 1.0, 0.1,
                            key=f"opt_w_{t}",
                            label_visibility="collapsed")
        enabled = c3.checkbox("", value=(t in PRIORITY_TARGETS and not bad),
                               key=f"opt_en_{t}",
                               label_visibility="collapsed")
        if enabled and weight > 0:
            objectives.append({
                "target":    t,
                "direction": "maximize" if direction == "最大化" else "minimize",
                "weight":    weight,
            })

if objectives:
    st.success(f"已选择 {len(objectives)} 个优化目标：" +
               "、".join(f"{o['target']}({'↑' if o['direction']=='maximize' else '↓'})" for o in objectives))
else:
    st.warning("请至少启用一个优化目标")

# ═══════════════════════════════════════════════════════════
# 步骤 2：搜索空间配置
# ═══════════════════════════════════════════════════════════
st.subheader("第二步：搜索空间配置")
st.caption("选择哪些特征参与优化，其余特征使用固定值")

col_a, col_b = st.columns(2)

with col_a:
    st.markdown("**配方特征组（参与优化）**")
    opt_M  = st.checkbox("基质 M",         value=True,  key="opt_grp_M")
    opt_FM = st.checkbox("功能基质 FM",    value=True,  key="opt_grp_FM")
    opt_Z  = st.checkbox("分子筛 Z",       value=True,  key="opt_grp_Z")
    opt_FZ = st.checkbox("功能分子筛 FZ",  value=True,  key="opt_grp_FZ")

with col_b:
    st.markdown("**其他特征**")
    opt_L = st.checkbox("同时优化理化性质 L", value=False, key="opt_grp_L")
    opt_T = st.checkbox("同时优化操作条件 T1/T2", value=False, key="opt_grp_T")

active_groups = []
if opt_M:  active_groups.append("M")
if opt_FM: active_groups.append("FM")
if opt_Z:  active_groups.append("Z")
if opt_FZ: active_groups.append("FZ")

# 固定值设置
st.markdown("**固定特征值（不参与优化的部分）**")
fix_col1, fix_col2, fix_col3 = st.columns(3)

fixed_features = {}

# 固定操作条件（若不优化T）
t_cols = groups.get("T", [])
if not opt_T and t_cols:
    t_defaults = {}
    for col in t_cols:
        lo, hi, med = bounds.get(col, (400.0, 600.0, 500.0))
        default = fix_col1.number_input(
            f"固定 {col}", float(lo), float(hi), float(med),
            key=f"fix_{col}", step=1.0 if hi-lo>10 else 0.1)
        fixed_features[col] = default

# 固定原料油
fixed_oil_str = fix_col2.selectbox("固定原料油类型", oil_classes, key="fix_oil")
if fixed_oil_str in le.classes_:
    fixed_features[OIL_COL] = int(le.transform([fixed_oil_str])[0])
else:
    fixed_features[OIL_COL] = 0

# 固定理化性质（若不优化L）
l_cols = groups.get("L", [])
if not opt_L and l_cols:
    st.markdown("**固定理化性质默认值（数据中位数）**")
    l_defaults = {}
    for col in l_cols:
        lo, hi, med = bounds.get(col, (0.0, 100.0, 0.0))
        fixed_features[col] = med

# ═══════════════════════════════════════════════════════════
# 步骤 3：运行参数
# ═══════════════════════════════════════════════════════════
st.subheader("第三步：运行参数")

run_col1, run_col2 = st.columns(2)
n_trials = run_col1.number_input(
    "优化试验次数", 50, 2000, 200, step=50,
    help="越多越精准，但耗时更长。推荐 200-500 次")
seed = run_col2.number_input("随机种子", 0, 9999, 42, help="固定种子保证可重复性")

# ═══════════════════════════════════════════════════════════
# 步骤 4：运行优化
# ═══════════════════════════════════════════════════════════
st.subheader("第四步：运行优化")

can_run = len(objectives) > 0 and len(active_groups) > 0
if not can_run:
    st.info("请完成前两步配置后再运行优化。")

run_btn = st.button(
    "开始贝叶斯优化", type="primary",
    use_container_width=True,
    disabled=not can_run,
)

if run_btn:
    search_cfg_input = {
        "active_groups": active_groups,
        "optimize_L":    opt_L,
        "optimize_T":    opt_T,
    }
    search_cfg = build_search_cfg(use_order, groups, search_cfg_input)

    objective_fn = build_objective(
        models, objectives, fixed_features, use_order, search_cfg
    )

    study = optuna.create_study(
        direction="minimize",
        sampler=optuna.samplers.TPESampler(seed=int(seed)),
    )

    # ─ 实时进度 UI ─
    prog_bar    = st.progress(0, text="准备开始...")
    status_txt  = st.empty()
    chart_holder = st.empty()

    trials_log = []

    def progress_cb(i, total, best_val, log):
        nonlocal trials_log
        trials_log = log
        pct = i / total
        best_str = f"{best_val:.4f}" if best_val is not None else "..."
        prog_bar.progress(pct, text=f"进度：{i}/{total}  |  当前最优目标值：{best_str}")
        status_txt.text(
            f"已完成 {i} 次试验，共 {total} 次 | "
            f"完成度：{pct*100:.0f}%"
        )
        # 每 20 次或最后一次更新图表
        if i % 20 == 0 or i == total:
            fig = optimization_history_chart(log)
            chart_holder.plotly_chart(fig, use_container_width=True)

    run_optimization(study, objective_fn, int(n_trials), progress_cb)

    prog_bar.progress(1.0, text="优化完成！")
    st.success(f"优化完成！共运行 {n_trials} 次试验。")

    # ─ 最优配方 ─
    best_params = study.best_params

    st.subheader("最优催化剂配方")
    st.caption(f"最优目标函数值：{study.best_value:.6f}")

    # 整理配方展示
    best_rows = []
    for col in use_order:
        val = best_params.get(col, fixed_features.get(col, 0.0))
        if col == OIL_COL:
            # 反解 LabelEncoder
            try:
                val_str = le.inverse_transform([int(val)])[0]
            except Exception:
                val_str = str(val)
            best_rows.append({"特征": col, "最优值": val_str, "单位": "类别"})
        else:
            if val is None or (isinstance(val, float) and np.isnan(val)):
                continue
            best_rows.append({"特征": col, "最优值": round(float(val), 4), "单位": "%/实测"})

    best_df = pd.DataFrame(best_rows)
    # 只展示非零配方特征
    comp_best = best_df[best_df["最优值"].apply(
        lambda x: isinstance(x, (int, float)) and float(x) > 0
        or isinstance(x, str)
    )]
    st.dataframe(comp_best, use_container_width=True, hide_index=True)

    # ─ 最优配方的产率预测 ─
    st.subheader("最优配方预测产率")
    best_feat = {}
    for col in use_order:
        val = best_params.get(col, fixed_features.get(col, 0.0))
        best_feat[col] = val

    # 将 oil 编码整数值放入 feat_values（已是整数）
    X_best = pd.DataFrame([{col: best_feat.get(col, 0.0) for col in use_order}])
    preds_best = {}
    for t_name, model in models.items():
        try:
            preds_best[t_name] = round(float(model.predict(X_best)[0]), 4)
        except Exception:
            preds_best[t_name] = 0.0

    # 高亮优化目标
    opt_targets = {o["target"] for o in objectives}
    pred_rows = []
    for t in display_order:
        if t not in preds_best:
            continue
        flag = "🎯 优化目标" if t in opt_targets else ""
        pred_rows.append({
            "目标变量": t,
            "预测产率 (%)": preds_best[t],
            "模型 R²": round(r2_dict.get(t, 0), 3),
            "备注": flag,
        })
    pred_df = pd.DataFrame(pred_rows)
    st.dataframe(pred_df, use_container_width=True, hide_index=True)

    # ─ 下载 ─
    col_dl1, col_dl2 = st.columns(2)
    csv_form = comp_best.to_csv(index=False, encoding="utf-8-sig")
    col_dl1.download_button(
        "下载最优配方 CSV", csv_form,
        file_name="optimal_formulation.csv", mime="text/csv",
    )
    csv_pred = pred_df.to_csv(index=False, encoding="utf-8-sig")
    col_dl2.download_button(
        "下载预测产率 CSV", csv_pred,
        file_name="optimal_predictions.csv", mime="text/csv",
    )
