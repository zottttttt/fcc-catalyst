# -*- coding: utf-8 -*-
"""
预测端点：POST /api/predict
输入：催化剂配方特征字典
输出：22 个产率目标的预测值
"""

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from api import deps
from app.config import OIL_COL, PRIORITY_TARGETS, UNRELIABLE_TARGETS

router = APIRouter()


class PredictRequest(BaseModel):
    features: dict  # {col_name: float 或 str（oil列）}


class PredictResponse(BaseModel):
    predictions: dict   # {target: float}
    r2: dict            # {target: float}
    priority_targets: list
    unreliable_targets: list


@router.post("/predict", response_model=PredictResponse)
def predict(req: PredictRequest):
    if not deps.is_trained():
        raise HTTPException(status_code=503, detail="模型尚未训练，请先在「模型训练」页面完成训练")

    models       = deps.get_models()
    le           = deps.get_le()
    meta         = deps.get_meta()
    feature_cols = deps.get_feature_cols()
    r2_dict      = meta.get("r2", {})

    if not feature_cols:
        raise HTTPException(status_code=503, detail="特征信息缺失，请重新训练模型")

    # 构建 1 行 DataFrame（特征顺序与训练时一致）
    row = {}
    for col in feature_cols:
        val = req.features.get(col)
        if col == OIL_COL:
            oil_str = str(val) if val is not None else "未知"
            if le is not None and hasattr(le, "classes_") and oil_str in le.classes_:
                row[col] = int(le.transform([oil_str])[0])
            else:
                row[col] = 0
        else:
            if val is None or val == "":
                row[col] = float("nan")
            else:
                try:
                    row[col] = float(val)
                except (ValueError, TypeError):
                    row[col] = float("nan")

    X = pd.DataFrame([row])

    predictions = {}
    for target, model in models.items():
        try:
            pred = float(model.predict(X)[0])
            predictions[target] = round(pred, 4)
        except Exception:
            predictions[target] = 0.0

    return PredictResponse(
        predictions=predictions,
        r2=r2_dict,
        priority_targets=PRIORITY_TARGETS,
        unreliable_targets=UNRELIABLE_TARGETS,
    )


@router.get("/status")
def get_status():
    """返回模型训练状态和基本元数据"""
    trained = deps.is_trained()
    if not trained:
        return {"trained": False}

    meta = deps.get_meta()
    return {
        "trained":    True,
        "train_time": meta.get("train_time", ""),
        "n_targets":  len(meta.get("targets", [])),
        "targets":    meta.get("targets", []),
        "r2":         meta.get("r2", {}),
        "mae":        meta.get("mae", {}),
        "params": {
            "n_estimators":  meta.get("n_estimators"),
            "learning_rate": meta.get("learning_rate"),
            "max_depth":     meta.get("max_depth"),
            "test_size":     meta.get("test_size"),
        },
    }


@router.get("/metadata")
def get_metadata():
    """返回特征分组、搜索边界、油种列表，用于前端表单动态构建"""
    if not deps.is_trained():
        return {"trained": False, "feature_cols": [], "groups": {}, "bounds": {}, "oil_classes": []}

    return {
        "trained":      True,
        "feature_cols": deps.get_feature_cols(),
        "groups":       deps.get_groups(),
        "bounds":       deps.get_bounds(),
        "oil_classes":  deps.get_oil_classes(),
        "priority_targets":   PRIORITY_TARGETS,
        "unreliable_targets": UNRELIABLE_TARGETS,
    }
