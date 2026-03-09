# -*- coding: utf-8 -*-
"""
正向预测页面
输入催化剂配方和操作条件 → 预测 22 个产率目标
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import pandas as pd

from config import PRIORITY_TARGETS, UNRELIABLE_TARGETS, OIL_COL
from model_io import models_trained, load_all_models, load_meta, load_label_encoder
from utils.data_loader import load_training_data, get_feature_groups, get_data_bounds
from utils.feature_ui import render_comp_group, render_property_group, render_condition_group, build_predict_input
from utils.charts import prediction_bar_chart

st.set_page_config(page_title="产率预测 | FCC 催化剂平台", layout="wide")
st.title("FCC 催化剂产率预测")
st.markdown("输入催化剂配方和操作条件，预测22个产率指标。")

# ── 检查模型状态 ─────────────────────────────────────────
if not models_trained():
    st.error("尚未训练模型，请先前往「模型训练」页面完成训练。")
    st.stop()

# ── 加载模型和数据 ────────────────────────────────────────
@st.cache_resource(show_spinner="正在加载模型...")
def _load_models():
    return load_all_models()

models   = _load_models()
meta     = load_meta()
feature_order = meta.get("feature_order", [])
r2_dict  = meta.get("r2", {})

X_df, Y_df, le, oil_classes, feature_cols, target_cols = load_training_data()
groups = get_feature_groups(feature_order if feature_order else feature_cols)
bounds = get_data_bounds(X_df, feature_order if feature_order else feature_cols)

# ── 特征输入区（使用表单防止中途触发）────────────────────
with st.form("prediction_form"):
    st.subheader("输入催化剂配方参数")

    tab_m, tab_fm, tab_z, tab_fz, tab_l, tab_t = st.tabs([
        "基质 M", "功能基质 FM", "分子筛 Z", "功能分子筛 FZ", "理化性质 L", "操作条件"
    ])

    with tab_m:
        st.caption("基质原料（M系列）：未添加则留0")
        feat_m = render_comp_group("基质 M", groups.get("M", []), key_prefix="pred_")

    with tab_fm:
        st.caption("功能基质（FM系列）：未添加则留0")
        feat_fm = render_comp_group("功能基质 FM", groups.get("FM", []), key_prefix="pred_")

    with tab_z:
        st.caption("分子筛（Z系列）：未添加则留0")
        feat_z = render_comp_group("分子筛 Z", groups.get("Z", []), key_prefix="pred_")

    with tab_fz:
        st.caption("功能分子筛（FZ系列）：未添加则留0")
        feat_fz = render_comp_group("功能分子筛 FZ", groups.get("FZ", []), key_prefix="pred_")

    with tab_l:
        st.caption("催化剂理化性质测量值")
        feat_l = render_property_group(groups.get("L", []), bounds, key_prefix="pred_")

    with tab_t:
        st.caption("FCC 操作条件")
        feat_t = render_condition_group(groups.get("T", []), bounds, key_prefix="pred_")
        oil_sel = st.selectbox("原料油类型", oil_classes, key="pred_oil")

    submitted = st.form_submit_button(
        "开始预测", use_container_width=True, type="primary"
    )

# ── 预测结果 ─────────────────────────────────────────────
if submitted:
    all_feats = {**feat_m, **feat_fm, **feat_z, **feat_fz,
                 **feat_l, **feat_t, OIL_COL: oil_sel}

    use_order = feature_order if feature_order else feature_cols
    X_input = build_predict_input(all_feats, le, use_order)

    preds = {}
    for target, model in models.items():
        try:
            preds[target] = float(model.predict(X_input)[0])
        except Exception:
            preds[target] = 0.0

    st.divider()
    st.subheader("预测结果")

    # ─ 核心指标卡片 ─
    st.markdown("**核心产率指标**")
    card_cols = st.columns(len(PRIORITY_TARGETS))
    for i, t in enumerate(PRIORITY_TARGETS):
        if t in preds:
            r2 = r2_dict.get(t, 0)
            val = preds[t]
            delta_color = "normal"
            card_cols[i].metric(
                label=t,
                value=f"{val:.2f}%",
                help=f"模型 R² = {r2:.3f}{'（低可信）' if t in UNRELIABLE_TARGETS else ''}",
            )

    # ─ 全量条形图 ─
    # 按目标名称排序展示
    sorted_targets = PRIORITY_TARGETS + [t for t in target_cols if t not in PRIORITY_TARGETS]
    sorted_preds   = {t: preds[t] for t in sorted_targets if t in preds}

    fig = prediction_bar_chart(sorted_preds, r2_dict, UNRELIABLE_TARGETS)
    st.plotly_chart(fig, use_container_width=True)

    # ─ 详细表格 ─
    st.subheader("详细预测数据")
    rows = []
    for t in sorted_targets:
        if t not in preds:
            continue
        r2 = r2_dict.get(t, 0)
        flag = "⚠️ 低可信（R²<0）" if t in UNRELIABLE_TARGETS else (
               "⭐ 核心指标" if t in PRIORITY_TARGETS else "")
        rows.append({
            "目标变量": t,
            "预测产率 (%)": round(preds[t], 4),
            "模型 R²": round(r2, 3),
            "备注": flag,
        })
    result_df = pd.DataFrame(rows)
    st.dataframe(result_df, use_container_width=True, hide_index=True)

    # ─ 下载 ─
    csv = result_df.to_csv(index=False, encoding="utf-8-sig")
    st.download_button(
        "下载预测结果 CSV", csv,
        file_name="prediction_result.csv",
        mime="text/csv",
    )

    # 低可信提示
    if any(t in preds for t in UNRELIABLE_TARGETS):
        st.warning(
            f"⚠️ 注意：{', '.join(UNRELIABLE_TARGETS)} 等目标的模型 R² < 0，"
            "预测结果仅供参考，不建议用于决策。"
        )
