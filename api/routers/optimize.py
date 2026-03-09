# -*- coding: utf-8 -*-
"""
优化端点：POST /api/optimize（启动异步 Optuna 优化）
GET /api/optimize/{job_id}（轮询进度和结果）
"""

import uuid
import threading
import traceback
import numpy as np
import pandas as pd
from typing import Optional, List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api import deps
from app.config import OIL_COL, PRIORITY_TARGETS
from app.utils.optimizer import build_objective, build_search_cfg, run_optimization
from app.utils.data_loader import get_feature_groups
import optuna

optuna.logging.set_verbosity(optuna.logging.WARNING)
router = APIRouter()

# ── 优化任务内存存储 ──────────────────────────────────────
opt_jobs: dict = {}
# {job_id: {"status": str, "progress": int, "best_value": float,
#            "trials_log": [(trial_num, value)], "result": dict or None, "error": str}}


class ObjectiveItem(BaseModel):
    target: str
    direction: str   # "maximize" | "minimize"
    weight: float


class OptimizeRequest(BaseModel):
    objectives: List[ObjectiveItem]
    active_groups: List[str] = ["M", "FM", "Z", "FZ"]
    optimize_L: bool = False
    optimize_T: bool = False
    n_trials: int = 200
    seed: int = 42
    fixed_features: dict = {}   # {col: value} 固定特征


class OptimizeJobStatus(BaseModel):
    job_id: str
    status: str          # pending | running | done | error
    progress: int
    best_value: Optional[float] = None
    trials_log: Optional[list] = None
    result: Optional[dict] = None
    error: Optional[str] = None


def _run_optimization(job_id: str, req: OptimizeRequest):
    """后台线程：执行 Optuna 优化"""
    job = opt_jobs[job_id]
    try:
        job["status"] = "running"

        models       = deps.get_models()
        le           = deps.get_le()
        meta         = deps.get_meta()
        feature_cols = deps.get_feature_cols()
        groups       = deps.get_groups()
        bounds       = deps.get_bounds()

        if not models or not feature_cols:
            raise ValueError("模型未加载，请先训练模型")

        # 处理固定特征中的 oil 列（字符串 → 编码整数）
        fixed = dict(req.fixed_features)
        if OIL_COL in fixed and le is not None:
            oil_str = str(fixed[OIL_COL])
            if oil_str in le.classes_:
                fixed[OIL_COL] = int(le.transform([oil_str])[0])
            else:
                fixed[OIL_COL] = 0

        # 构建搜索配置
        search_cfg = build_search_cfg(
            feature_cols, groups,
            {"active_groups": req.active_groups,
             "optimize_L":    req.optimize_L,
             "optimize_T":    req.optimize_T},
        )

        objectives = [o.dict() for o in req.objectives]
        objective_fn = build_objective(models, objectives, fixed, feature_cols, search_cfg)

        study = optuna.create_study(
            direction="minimize",
            sampler=optuna.samplers.TPESampler(seed=int(req.seed)),
        )

        trials_log = []

        def progress_cb(i, total, best_val, log):
            job["progress"]   = int(i / total * 100)
            job["best_value"] = best_val
            job["trials_log"] = log[-50:]  # 只保留最近 50 条

        run_optimization(study, objective_fn, int(req.n_trials), progress_cb)

        # ── 整理最优结果 ──
        best_params = study.best_params
        best_value  = study.best_value

        # 用最优配方预测产率
        row = {}
        for col in feature_cols:
            val = best_params.get(col, fixed.get(col, 0.0))
            row[col] = float(val) if val is not None else 0.0
        X_best = pd.DataFrame([row])
        best_preds = {}
        for t_name, model in models.items():
            try:
                best_preds[t_name] = round(float(model.predict(X_best)[0]), 4)
            except Exception:
                best_preds[t_name] = 0.0

        # 反解 oil 编码
        best_display = {}
        for col, val in {**fixed, **best_params}.items():
            if col == OIL_COL and le is not None:
                try:
                    val = le.inverse_transform([int(val)])[0]
                except Exception:
                    pass
            best_display[col] = val

        job["status"]   = "done"
        job["progress"] = 100
        job["result"]   = {
            "best_value":      best_value,
            "best_params":     best_display,
            "best_preds":      best_preds,
            "n_trials":        len(study.trials),
            "priority_targets": PRIORITY_TARGETS,
        }

    except Exception as e:
        job["status"] = "error"
        job["error"]  = str(e) + "\n" + traceback.format_exc()


@router.post("/optimize")
def start_optimization(req: OptimizeRequest):
    """启动后台优化任务，返回 job_id"""
    if not deps.is_trained():
        raise HTTPException(status_code=503, detail="模型尚未训练")
    if not req.objectives:
        raise HTTPException(status_code=400, detail="请至少选择一个优化目标")

    job_id = str(uuid.uuid4())[:8]
    opt_jobs[job_id] = {
        "status": "pending", "progress": 0,
        "best_value": None, "trials_log": [],
        "result": None, "error": None,
    }
    thread = threading.Thread(target=_run_optimization, args=(job_id, req), daemon=True)
    thread.start()
    return {"job_id": job_id}


@router.get("/optimize/{job_id}", response_model=OptimizeJobStatus)
def get_optimize_status(job_id: str):
    """查询优化任务进度和结果"""
    if job_id not in opt_jobs:
        raise HTTPException(status_code=404, detail="优化任务不存在")
    job = opt_jobs[job_id]
    return OptimizeJobStatus(job_id=job_id, **job)
