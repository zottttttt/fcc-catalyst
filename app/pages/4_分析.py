# -*- coding: utf-8 -*-
"""
模型验证分析页面
利用训练时保存的结果文件，展示：
- 模型性能总览（R²、MAE、RMSE，XGB vs LGB 对比）
- 实际值 vs 预测值散点图 + 残差分析
- 特征重要性分析
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from pathlib import Path

from config import LOGS_DIR, PRIORITY_TARGETS, UNRELIABLE_TARGETS
from model_io import models_trained, load_meta

st.set_page_config(page_title="模型分析 | FCC 催化剂平台", layout="wide")
st.title("模型验证与分析")
st.markdown("查看测试集验证结果、特征重要性，评估模型可靠性。")

# ── 检查状态 ────────────────────────────────────────────
if not models_trained():
    st.error("尚未训练模型，请先前往「模型训练」页面完成训练。")
    st.stop()

logs_dir = Path(LOGS_DIR)
summary_file = logs_dir / "summary_xgb_vs_lgb.csv"

if not summary_file.exists():
    st.warning("未找到训练结果日志文件（logs/summary_xgb_vs_lgb.csv）。"
               "请在「模型训练」页面重新训练一次以生成日志文件。")
    st.stop()

# ── 辅助函数 ────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def load_summary():
    return pd.read_csv(str(summary_file), encoding="utf-8-sig")

@st.cache_data(show_spinner=False)
def load_result_csv(target_name: str) -> pd.DataFrame | None:
    path = logs_dir / f"result_{target_name}.csv"
    if path.exists():
        return pd.read_csv(str(path), encoding="utf-8-sig")
    return None

@st.cache_data(show_spinner=False)
def load_importance_csv(target_name: str) -> pd.DataFrame | None:
    path = logs_dir / f"importance_xgb_{target_name}.csv"
    if path.exists():
        return pd.read_csv(str(path), encoding="utf-8-sig")
    return None

def compute_metrics(actual, predicted):
    """从数组计算 R²、MAE、RMSE"""
    actual    = np.array(actual, dtype=float)
    predicted = np.array(predicted, dtype=float)
    mask = ~(np.isnan(actual) | np.isnan(predicted))
    actual, predicted = actual[mask], predicted[mask]
    if len(actual) < 2:
        return None, None, None
    ss_res = np.sum((actual - predicted) ** 2)
    ss_tot = np.sum((actual - np.mean(actual)) ** 2)
    r2   = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0
    mae  = float(np.mean(np.abs(actual - predicted)))
    rmse = float(np.sqrt(np.mean((actual - predicted) ** 2)))
    return round(r2, 4), round(mae, 4), round(rmse, 4)

# ── 加载数据 ────────────────────────────────────────────
meta     = load_meta()
summary  = load_summary()
r2_meta  = meta.get("r2", {})
mae_meta = meta.get("mae", {})

# 从 summary 获取列名（处理可能的列名差异）
col_map = {c: c for c in summary.columns}
target_col   = next((c for c in summary.columns if "目标" in c), summary.columns[0])
xgb_r2_col   = next((c for c in summary.columns if "XGB" in c and "R2" in c.upper()), None)
xgb_mae_col  = next((c for c in summary.columns if "XGB" in c and "MAE" in c.upper()), None)
xgb_rmse_col = next((c for c in summary.columns if "XGB" in c and "RMSE" in c.upper()), None)
lgb_r2_col   = next((c for c in summary.columns if "LGB" in c and "R2" in c.upper()), None)
lgb_mae_col  = next((c for c in summary.columns if "LGB" in c and "MAE" in c.upper()), None)
best_col     = next((c for c in summary.columns if "最佳" in c), None)

all_targets = summary[target_col].tolist()

# ═══════════════════════════════════════════════════════
tab1, tab2, tab3 = st.tabs(["模型性能总览", "实际 vs 预测分析", "特征重要性"])

# ══════════════════════════════════════════════════════
# TAB 1：模型性能总览
# ══════════════════════════════════════════════════════
with tab1:
    st.subheader("全目标模型性能汇总")

    # ─ 汇总表 ─
    rows = []
    for _, row in summary.iterrows():
        t    = row[target_col]
        flag = ("⚠️ 低可信" if t in UNRELIABLE_TARGETS else
                "⭐ 核心"   if t in PRIORITY_TARGETS else "")
        xgb_r2   = row.get(xgb_r2_col, None) if xgb_r2_col else None
        lgb_r2   = row.get(lgb_r2_col, None) if lgb_r2_col else None
        best     = row.get(best_col, "XGB") if best_col else "XGB"
        rows.append({
            "目标变量":  t,
            "XGB R²":   round(float(xgb_r2), 4) if xgb_r2 is not None else None,
            "XGB MAE":  round(float(row.get(xgb_mae_col, 0)), 4) if xgb_mae_col else None,
            "XGB RMSE": round(float(row.get(xgb_rmse_col, 0)), 4) if xgb_rmse_col else None,
            "LGB R²":   round(float(lgb_r2), 4) if lgb_r2 is not None else None,
            "LGB MAE":  round(float(row.get(lgb_mae_col, 0)), 4) if lgb_mae_col else None,
            "最佳模型":  best,
            "备注":      flag,
        })
    perf_df = pd.DataFrame(rows).sort_values("XGB R²", ascending=False)
    st.dataframe(perf_df, use_container_width=True, hide_index=True)

    # ─ 可信度分布 ─
    st.markdown("**模型可信度分类**")
    xgb_r2_vals = perf_df["XGB R²"].dropna()
    high   = (xgb_r2_vals >= 0.7).sum()
    medium = ((xgb_r2_vals >= 0.3) & (xgb_r2_vals < 0.7)).sum()
    low    = (xgb_r2_vals < 0.3).sum()
    c1, c2, c3 = st.columns(3)
    c1.metric("高可信 (R²≥0.7)", f"{high} 个目标", help="预测结果可直接用于决策")
    c2.metric("中等可信 (0.3≤R²<0.7)", f"{medium} 个目标", help="预测结果供参考")
    c3.metric("低可信 (R²<0.3)", f"{low} 个目标", help="预测误差较大，谨慎使用")

    # ─ XGB vs LGB R² 对比条形图 ─
    if xgb_r2_col and lgb_r2_col:
        st.subheader("XGBoost vs LightGBM R² 对比")
        fig = go.Figure()
        fig.add_trace(go.Bar(
            name="XGBoost",
            x=summary[target_col],
            y=summary[xgb_r2_col],
            marker_color="#2E74B5",
        ))
        fig.add_trace(go.Bar(
            name="LightGBM",
            x=summary[target_col],
            y=summary[lgb_r2_col],
            marker_color="#E87722",
            opacity=0.8,
        ))
        fig.add_hline(y=0.7, line_dash="dash", line_color="green",
                      annotation_text="R²=0.7（高可信线）")
        fig.add_hline(y=0.3, line_dash="dot", line_color="orange",
                      annotation_text="R²=0.3（低可信线）")
        fig.update_layout(
            barmode="group",
            title="各目标 XGB vs LGB R² 对比",
            xaxis_tickangle=-45,
            xaxis_title="目标变量",
            yaxis_title="R²",
            height=450,
            plot_bgcolor="white",
            legend=dict(orientation="h", y=1.05),
        )
        st.plotly_chart(fig, use_container_width=True)


# ══════════════════════════════════════════════════════
# TAB 2：实际 vs 预测分析
# ══════════════════════════════════════════════════════
with tab2:
    st.subheader("测试集实际值 vs 预测值对比")
    st.caption("显示20%测试集上的预测结果（~155个样本）")

    sel_target = st.selectbox(
        "选择目标变量",
        options=PRIORITY_TARGETS + [t for t in all_targets if t not in PRIORITY_TARGETS],
        key="tab2_target",
    )

    result_df = load_result_csv(sel_target)
    if result_df is None:
        st.warning(f"未找到 logs/result_{sel_target}.csv，请重新训练模型。")
    else:
        # 识别列名（支持新旧两种训练方式）
        actual_col   = next((c for c in result_df.columns if "实际" in c), result_df.columns[0])
        xgb_pred_col = next((c for c in result_df.columns if "XGB" in c), None)
        lgb_pred_col = next((c for c in result_df.columns if "LGB" in c), None)

        # 选择模型
        model_choice = st.radio(
            "查看模型", ["XGBoost", "LightGBM"] if lgb_pred_col else ["XGBoost"],
            horizontal=True, key="tab2_model",
        )
        pred_col = xgb_pred_col if model_choice == "XGBoost" else lgb_pred_col

        actual    = result_df[actual_col].values
        predicted = result_df[pred_col].values

        r2, mae, rmse = compute_metrics(actual, predicted)

        # ─ 指标卡片 ─
        mc1, mc2, mc3, mc4 = st.columns(4)
        mc1.metric("测试集样本数", len(actual))
        mc2.metric("R²", f"{r2:.4f}" if r2 is not None else "N/A",
                   help="越接近1越好")
        mc3.metric("MAE（平均绝对误差）", f"{mae:.4f}" if mae is not None else "N/A")
        mc4.metric("RMSE（均方根误差）", f"{rmse:.4f}" if rmse is not None else "N/A")

        col_left, col_right = st.columns(2)

        # ─ 散点图 ─
        with col_left:
            st.markdown(f"**实际值 vs {model_choice} 预测值**")
            lo = float(min(actual.min(), predicted.min()))
            hi = float(max(actual.max(), predicted.max()))
            margin = (hi - lo) * 0.05
            fig_scatter = go.Figure()
            fig_scatter.add_trace(go.Scatter(
                x=[lo - margin, hi + margin],
                y=[lo - margin, hi + margin],
                mode="lines", name="理想线（y=x）",
                line=dict(color="red", dash="dash", width=1.5),
            ))
            fig_scatter.add_trace(go.Scatter(
                x=actual, y=predicted,
                mode="markers", name=model_choice,
                marker=dict(color="#2E74B5", size=5, opacity=0.6),
                hovertemplate="实际: %{x:.3f}<br>预测: %{y:.3f}<extra></extra>",
            ))
            fig_scatter.update_layout(
                xaxis_title="实际值 (%)",
                yaxis_title="预测值 (%)",
                height=380,
                plot_bgcolor="white",
                showlegend=True,
                legend=dict(orientation="h", y=1.05),
            )
            st.plotly_chart(fig_scatter, use_container_width=True)

        # ─ 残差直方图 ─
        with col_right:
            st.markdown("**残差分布（预测值 − 实际值）**")
            residuals = predicted - actual
            fig_hist = px.histogram(
                x=residuals,
                nbins=30,
                title=f"残差分布（均值={np.mean(residuals):.3f}，标准差={np.std(residuals):.3f}）",
                labels={"x": "残差"},
                color_discrete_sequence=["#2E74B5"],
            )
            fig_hist.add_vline(x=0, line_dash="dash", line_color="red",
                               annotation_text="零误差线")
            fig_hist.update_layout(height=380, plot_bgcolor="white", showlegend=False)
            st.plotly_chart(fig_hist, use_container_width=True)

        # ─ 残差散点（检查系统性偏差）─
        with st.expander("查看残差随实际值变化（检测系统性偏差）"):
            fig_resid = go.Figure()
            fig_resid.add_trace(go.Scatter(
                x=actual, y=residuals,
                mode="markers",
                marker=dict(color="#2E74B5", size=4, opacity=0.6),
                hovertemplate="实际: %{x:.3f}<br>残差: %{y:.3f}<extra></extra>",
            ))
            fig_resid.add_hline(y=0, line_dash="dash", line_color="red")
            fig_resid.update_layout(
                xaxis_title="实际值 (%)",
                yaxis_title="残差 (预测 − 实际)",
                height=300,
                plot_bgcolor="white",
            )
            st.plotly_chart(fig_resid, use_container_width=True)
            st.caption("理想情况：点随机分布在零线两侧，无明显趋势。若有斜率说明存在系统性偏差。")


# ══════════════════════════════════════════════════════
# TAB 3：特征重要性分析
# ══════════════════════════════════════════════════════
with tab3:
    st.subheader("特征重要性分析")

    col_sel1, col_sel2 = st.columns(2)

    # ─ 单目标特征重要性 ─
    with col_sel1:
        imp_target = st.selectbox(
            "选择目标变量",
            options=PRIORITY_TARGETS + [t for t in all_targets if t not in PRIORITY_TARGETS],
            key="tab3_single",
        )
        imp_df = load_importance_csv(imp_target)
        if imp_df is not None:
            feat_col  = next((c for c in imp_df.columns if "特征" in c), imp_df.columns[0])
            score_col = next((c for c in imp_df.columns if "重要性" in c or "importance" in c.lower()),
                             imp_df.columns[1])
            imp_df = imp_df.rename(columns={feat_col: "特征", score_col: "XGB重要性"})

            top_n = st.slider("显示 Top N 特征", 5, min(20, len(imp_df)), 15, key="topn_single")
            top_df = imp_df.head(top_n).copy()

            fig_imp = px.bar(
                top_df, x="XGB重要性", y="特征", orientation="h",
                title=f"特征重要性 Top {top_n} — {imp_target}",
                color="XGB重要性",
                color_continuous_scale="Blues",
            )
            fig_imp.update_layout(
                yaxis=dict(autorange="reversed"),
                height=max(350, top_n * 22),
                showlegend=False,
                plot_bgcolor="white",
            )
            st.plotly_chart(fig_imp, use_container_width=True)
        else:
            st.warning(f"未找到 logs/importance_xgb_{imp_target}.csv")

    # ─ 多目标特征重要性热力图 ─
    with col_sel2:
        multi_targets = st.multiselect(
            "多目标特征重要性对比（选 2-4 个目标）",
            options=PRIORITY_TARGETS + [t for t in all_targets if t not in PRIORITY_TARGETS],
            default=PRIORITY_TARGETS[:4],
            max_selections=4,
            key="tab3_multi",
        )

        if len(multi_targets) >= 2:
            # 加载各目标的特征重要性
            all_imps = {}
            for t in multi_targets:
                df_t = load_importance_csv(t)
                if df_t is not None:
                    fc  = next((c for c in df_t.columns if "特征" in c), df_t.columns[0])
                    sc  = next((c for c in df_t.columns if "重要性" in c or "importance" in c.lower()),
                               df_t.columns[1])
                    all_imps[t] = dict(zip(df_t[fc], df_t[sc]))

            if len(all_imps) >= 2:
                # 取所有目标的 Top 10 特征（并集），按平均重要性排序
                all_feats = set()
                for imp in all_imps.values():
                    all_feats.update(list(imp.keys())[:10])

                feat_list = sorted(
                    all_feats,
                    key=lambda f: np.mean([imp.get(f, 0) for imp in all_imps.values()]),
                    reverse=True,
                )[:15]

                # 构建热力图矩阵
                heat_data = pd.DataFrame(
                    {t: [all_imps.get(t, {}).get(f, 0) for f in feat_list]
                     for t in all_imps},
                    index=feat_list,
                )
                fig_heat = px.imshow(
                    heat_data,
                    labels=dict(x="目标变量", y="特征", color="重要性"),
                    title="多目标特征重要性热力图（Top 15 特征）",
                    color_continuous_scale="Blues",
                    aspect="auto",
                )
                fig_heat.update_layout(height=max(350, len(feat_list) * 22))
                st.plotly_chart(fig_heat, use_container_width=True)
                st.caption("颜色越深代表该特征对该目标的影响越大")
            else:
                st.info("部分目标缺少特征重要性文件，请重新训练模型。")
        elif len(multi_targets) == 1:
            st.info("请再选择至少 1 个目标以显示对比热力图")
        else:
            st.info("请选择 2-4 个目标以显示对比热力图")

    # ─ 说明 ─
    st.divider()
    st.caption(
        "**特征重要性说明**：使用 XGBoost 的 gain（增益）指标，"
        "反映该特征在决策树分裂时带来的平均信息增益。"
        "T2_剂油比 和 T1_反应温度 通常是最重要的特征，"
        "其次是分子筛组成（FZ/Z系列）。"
    )
