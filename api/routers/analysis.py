# -*- coding: utf-8 -*-
"""
分析端点：只读，返回已有日志文件的数据
GET /api/analysis/summary
GET /api/analysis/result/{target}
GET /api/analysis/importance/{target}
"""

import pandas as pd
from fastapi import APIRouter, HTTPException
from api import deps

router = APIRouter()


def _logs_dir():
    return deps.get_project_root() / "logs"


@router.get("/analysis/summary")
def get_summary():
    """返回 XGB vs LGB 汇总表"""
    path = _logs_dir() / "summary_xgb_vs_lgb.csv"
    if not path.exists():
        raise HTTPException(status_code=404, detail="汇总文件不存在，请先完成模型训练")
    df = pd.read_csv(str(path), encoding="utf-8-sig")
    return df.to_dict(orient="records")


@router.get("/analysis/result/{target}")
def get_result(target: str):
    """返回指定目标的测试集实际值 vs 预测值"""
    path = _logs_dir() / f"result_{target}.csv"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"结果文件不存在：result_{target}.csv")
    df = pd.read_csv(str(path), encoding="utf-8-sig")
    return df.to_dict(orient="list")  # {col: [values]}


@router.get("/analysis/importance/{target}")
def get_importance(target: str):
    """返回指定目标的特征重要性（XGBoost）"""
    path = _logs_dir() / f"importance_xgb_{target}.csv"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"特征重要性文件不存在：importance_xgb_{target}.csv")
    df = pd.read_csv(str(path), encoding="utf-8-sig")
    return df.to_dict(orient="records")  # [{特征: .., XGB重要性: ..}, ...]
