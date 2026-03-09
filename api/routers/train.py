# -*- coding: utf-8 -*-
"""
训练端点：POST /api/train（异步后台任务）
GET /api/train/{job_id}（轮询进度）
"""

import uuid
import threading
import traceback
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
import numpy as np
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sklearn.model_selection import train_test_split
from sklearn.metrics import r2_score, mean_absolute_error
from sklearn.preprocessing import LabelEncoder
from xgboost import XGBRegressor

from api import deps
from app.config import COMP_PREFIXES, OIL_COL, PRIORITY_TARGETS
from app.model_io import save_meta, save_label_encoder

router = APIRouter()

# ── 训练任务内存存储 ─────────────────────────────────────
train_jobs: dict = {}
# {job_id: {"status": "pending|running|done|error",
#            "progress": 0-100,
#            "current_target": str,
#            "results": [...],
#            "error": str or None}}


class TrainRequest(BaseModel):
    n_estimators: int = 300
    learning_rate: float = 0.05
    max_depth: int = 6
    test_size: float = 0.2


class TrainJobStatus(BaseModel):
    job_id: str
    status: str
    progress: int
    current_target: Optional[str] = None
    results: Optional[list] = None
    error: Optional[str] = None


def _run_training(job_id: str, params: TrainRequest):
    """后台线程：执行模型训练"""
    job = train_jobs[job_id]
    try:
        job["status"] = "running"
        root = deps.get_project_root()
        data_path  = root / "ml_A_all.xlsx"
        models_dir = root / "models"
        logs_dir   = root / "logs"
        models_dir.mkdir(exist_ok=True)
        logs_dir.mkdir(exist_ok=True)

        # 读取数据
        df = pd.read_excel(str(data_path), sheet_name="ML_data", engine="openpyxl")
        target_cols  = [c for c in df.columns if c.startswith("C")]
        feature_cols = [c for c in df.columns if not c.startswith("C")]
        X = df[feature_cols].copy()
        Y = df[target_cols].copy()

        # 配方列 NaN → 0
        for col in feature_cols:
            if col.split("_")[0] in COMP_PREFIXES:
                X[col] = X[col].fillna(0.0)

        # LabelEncoder
        le = LabelEncoder()
        X[OIL_COL] = X[OIL_COL].fillna("未知")
        X[OIL_COL] = le.fit_transform(X[OIL_COL])
        save_label_encoder(le)

        # 逐目标训练
        r2_results, mae_results = {}, {}
        results_log = []
        targets_order = PRIORITY_TARGETS + [c for c in target_cols if c not in PRIORITY_TARGETS]
        targets_in_data = [t for t in targets_order if t in Y.columns]
        n_total = len(targets_in_data)

        summary_rows = []

        for i, target in enumerate(targets_in_data):
            job["current_target"] = target
            job["progress"] = int((i / n_total) * 95)

            y = Y[target]
            valid = y.notna()
            X_use, y_use = X[valid], y[valid]
            if len(y_use) < 50:
                results_log.append({"target": target, "status": "skipped", "r2": None, "mae": None})
                continue

            X_tr, X_te, y_tr, y_te = train_test_split(
                X_use, y_use, test_size=float(params.test_size), random_state=42)

            model = XGBRegressor(
                n_estimators=int(params.n_estimators),
                learning_rate=float(params.learning_rate),
                max_depth=int(params.max_depth),
                subsample=0.8, colsample_bytree=0.8,
                random_state=42, n_jobs=-1, verbosity=0,
            )
            model.fit(X_tr, y_tr, eval_set=[(X_te, y_te)], verbose=False)

            y_pred = model.predict(X_te)
            r2  = float(r2_score(y_te, y_pred))
            mae = float(mean_absolute_error(y_te, y_pred))
            rmse = float(np.sqrt(np.mean((y_te.values - y_pred) ** 2)))

            r2_results[target]  = round(r2,  4)
            mae_results[target] = round(mae, 4)

            model_path = str(models_dir / f"model_xgb_{target}.json")
            model.save_model(model_path)

            # 保存预测结果 CSV（供分析页使用）
            pd.DataFrame({
                "实际值": y_te.values, "XGB预测值": y_pred,
            }).to_csv(str(logs_dir / f"result_{target}.csv"), index=False, encoding="utf-8-sig")

            # 保存特征重要性 CSV
            imp_df = pd.DataFrame({
                "特征": X_use.columns.tolist(),
                "XGB重要性": model.feature_importances_,
            }).sort_values("XGB重要性", ascending=False)
            imp_df.to_csv(str(logs_dir / f"importance_xgb_{target}.csv"), index=False, encoding="utf-8-sig")

            results_log.append({"target": target, "status": "done", "r2": r2_results[target], "mae": mae_results[target]})
            summary_rows.append({
                "目标变量": target, "样本数": len(y_use),
                "XGB_R2": round(r2, 4), "XGB_MAE": round(mae, 4), "XGB_RMSE": round(rmse, 4),
                "最佳模型": "XGB",
            })

        # 保存汇总 CSV
        pd.DataFrame(summary_rows).to_csv(
            str(logs_dir / "summary_xgb_vs_lgb.csv"), index=False, encoding="utf-8-sig")

        # 保存元数据
        meta = {
            "train_time":    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "n_estimators":  int(params.n_estimators),
            "learning_rate": float(params.learning_rate),
            "max_depth":     int(params.max_depth),
            "test_size":     float(params.test_size),
            "targets":       targets_in_data,
            "r2":            r2_results,
            "mae":           mae_results,
            "feature_order": feature_cols,
        }
        save_meta(meta)
        deps.invalidate_cache()  # 让下次请求重新加载新模型

        job["status"]   = "done"
        job["progress"] = 100
        job["results"]  = results_log

    except Exception as e:
        job["status"] = "error"
        job["error"]  = str(e) + "\n" + traceback.format_exc()


@router.post("/train")
def start_training(req: TrainRequest):
    """启动后台训练任务，返回 job_id"""
    job_id = str(uuid.uuid4())[:8]
    train_jobs[job_id] = {
        "status": "pending", "progress": 0,
        "current_target": None, "results": None, "error": None,
    }
    thread = threading.Thread(target=_run_training, args=(job_id, req), daemon=True)
    thread.start()
    return {"job_id": job_id}


@router.get("/train/{job_id}", response_model=TrainJobStatus)
def get_train_status(job_id: str):
    """查询训练任务进度"""
    if job_id not in train_jobs:
        raise HTTPException(status_code=404, detail="训练任务不存在")
    job = train_jobs[job_id]
    return TrainJobStatus(job_id=job_id, **job)
