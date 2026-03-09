# -*- coding: utf-8 -*-
"""
FCC 催化剂智能分析平台 — 主入口
启动命令：streamlit run app/main.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import streamlit as st

st.set_page_config(
    page_title="FCC 催化剂智能分析平台",
    page_icon="⚗️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("⚗️ FCC 催化剂智能分析平台")
st.markdown("---")

col1, col2 = st.columns([2, 1])

with col1:
    st.markdown("""
## 平台简介

本平台基于 **768 条 FCC 催化剂实验数据**，利用 **XGBoost 机器学习模型**，
提供两大核心功能：

### 功能导航

| 页面 | 功能 | 使用场景 |
|------|------|----------|
| **产率预测** | 输入催化剂配方 → 预测22个产率指标 | 已有配方，快速评估性能 |
| **反向设计** | 设定目标产率 → 推荐最优配方 | 目标驱动，寻找最优设计 |
| **模型训练** | 本地训练/更新 XGBoost 模型 | 首次使用或数据更新后 |
| **模型分析** | 测试集验证、特征重要性分析 | 训练后查看模型效果 |

---

### 快速开始

1. 首先前往 **「模型训练」** 页面，点击「开始训练」完成模型训练（约需 2-5 分钟）
2. 训练完成后，前往 **「产率预测」** 页面输入配方进行预测
3. 如需寻找最优配方，使用 **「反向设计」** 页面设置目标并运行优化
""")

with col2:
    st.markdown("""
## 数据概况

| 项目 | 数值 |
|------|------|
| 实验样本数 | 768 条 |
| 特征数量 | ~33 个 |
| 预测目标 | 22 个产率指标 |
| 核心模型 | XGBoost |
| 最优模型 R² | 0.92（干气） |

## 核心预测目标

- ⭐ **C4_汽油**（R²≈0.71）
- ⭐ **C9_转化率**（R²≈0.54）
- ⭐ **C3_液化气**（R²≈0.71）
- ⭐ **C1_焦炭**（R²≈0.68）
- ⭐ **C5_柴油**（R²≈0.60）
- ⭐ **C8_总液收**（R²≈0.75）
""")

# 模型状态提示
st.markdown("---")
try:
    from model_io import models_trained, load_meta
    if models_trained():
        meta = load_meta()
        train_time = meta.get("train_time", "未知")
        n_targets  = len(meta.get("targets", []))
        st.success(f"✅ 模型已就绪 | 训练时间：{train_time} | 覆盖 {n_targets} 个目标")
    else:
        st.warning("⚠️ 模型尚未训练。请前往左侧「模型训练」页面完成训练。")
except Exception as e:
    st.warning(f"⚠️ 模型状态检查失败：{e}，请前往「模型训练」页面。")
