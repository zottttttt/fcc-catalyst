# -*- coding: utf-8 -*-
"""
共享依赖与模型缓存
- 全局单例：避免每次请求重新加载 22 个 XGBoost 模型
- 不依赖 Streamlit，适用于 FastAPI 环境
- 路径通过 FCC_ROOT 环境变量配置（云端部署用），默认为项目根目录
"""

import os
import sys
import threading
from pathlib import Path
from typing import Optional

# ── 路径解析（支持本地 Windows + 云端 Linux）────────────
# FCC_ROOT 环境变量优先，其次用 server.py 所在目录
_this_file = Path(__file__).resolve()
_project_root = Path(os.environ.get("FCC_ROOT", str(_this_file.parent.parent)))

# 将项目根 + app/ 目录加入 Python 路径
sys.path.insert(0, str(_project_root))
sys.path.insert(0, str(_project_root / "app"))

# ── 延迟导入 ML 模块（路径设置后才能导入）────────────────
from pathlib import Path as _Path

# 覆盖 config 中的路径（关键：云端部署路径不同于本地 Windows）
import app.config as _cfg
_cfg.ROOT_DIR   = _project_root
_cfg.DATA_PATH  = _project_root / "ml_A_all.xlsx"
_cfg.MODELS_DIR = _project_root / "models"
_cfg.LOGS_DIR   = _project_root / "logs"

from app.model_io import (
    models_trained, load_all_models, load_label_encoder, load_meta,
)
from app.utils.data_loader import get_feature_groups, get_data_bounds

# ── 全局缓存（线程安全）──────────────────────────────────
_lock   = threading.Lock()
_models: dict = {}
_le     = None
_meta:  dict  = {}
_groups: dict = {}
_bounds: dict = {}
_oil_classes: list = []
_feature_cols: list = []
_initialized = False


def _initialize():
    """首次调用时加载所有模型和元数据（线程安全）"""
    global _models, _le, _meta, _groups, _bounds, _oil_classes, _feature_cols, _initialized

    with _lock:
        if _initialized:
            return
        if not models_trained():
            return  # 未训练，返回空（前端会提示）

        _meta        = load_meta()
        _models      = load_all_models()
        _le          = load_label_encoder()
        _feature_cols = _meta.get("feature_order", [])
        _groups      = get_feature_groups(_feature_cols)

        # 计算特征边界（用于前端表单范围限制）
        import pandas as pd
        from app.config import DATA_PATH, COMP_PREFIXES, OIL_COL
        from sklearn.preprocessing import LabelEncoder

        try:
            df = pd.read_excel(str(DATA_PATH), sheet_name="ML_data", engine="openpyxl")
            feat_cols   = [c for c in df.columns if not c.startswith("C")]
            X = df[feat_cols].copy()
            for col in feat_cols:
                if col.split("_")[0] in COMP_PREFIXES:
                    X[col] = X[col].fillna(0.0)
            le_tmp = LabelEncoder()
            X[OIL_COL] = X[OIL_COL].fillna("未知")
            _oil_classes = sorted(df[OIL_COL].dropna().unique().tolist())
            X[OIL_COL] = le_tmp.fit_transform(X[OIL_COL])
            _bounds = get_data_bounds(X, _feature_cols)
        except Exception:
            _bounds = {}

        _initialized = True


def invalidate_cache():
    """训练完成后调用，强制下次请求重新加载"""
    global _initialized
    with _lock:
        _initialized = False


def get_models() -> dict:
    _initialize()
    return _models


def get_le():
    _initialize()
    return _le


def get_meta() -> dict:
    _initialize()
    return _meta


def get_groups() -> dict:
    _initialize()
    return _groups


def get_bounds() -> dict:
    _initialize()
    return _bounds


def get_oil_classes() -> list:
    _initialize()
    return _oil_classes


def get_feature_cols() -> list:
    _initialize()
    return _feature_cols


def is_trained() -> bool:
    return models_trained()


def get_project_root() -> Path:
    return _project_root
