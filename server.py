# -*- coding: utf-8 -*-
"""
FastAPI 主入口
启动：uvicorn server:app --host 0.0.0.0 --port 8000 --reload
"""

import os
import sys
import threading
from pathlib import Path

# 确保项目根目录在 Python 路径中
_root = Path(__file__).parent
sys.path.insert(0, str(_root))
sys.path.insert(0, str(_root / "app"))

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

from api.routers import predict, optimize, train, analysis

# ── 应用初始化 ────────────────────────────────────────────
app = FastAPI(
    title="FCC 催化剂智能分析平台",
    description="基于 XGBoost 的 FCC 催化剂产率预测与反向设计系统",
    version="1.0.0",
)

# CORS（允许前端调试时跨域请求）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 注册路由 ──────────────────────────────────────────────
app.include_router(predict.router,  prefix="/api", tags=["预测"])
app.include_router(optimize.router, prefix="/api", tags=["优化"])
app.include_router(train.router,    prefix="/api", tags=["训练"])
app.include_router(analysis.router, prefix="/api", tags=["分析"])

# ── 静态文件服务 ──────────────────────────────────────────
frontend_dir = _root / "frontend"
if frontend_dir.exists():
    app.mount("/static", StaticFiles(directory=str(frontend_dir)), name="static")


@app.get("/", include_in_schema=False)
def root():
    """服务前端 SPA 入口页面"""
    html_path = frontend_dir / "index.html"
    if html_path.exists():
        return FileResponse(str(html_path))
    return {"message": "FCC 催化剂平台 API 运行中", "docs": "/docs"}


@app.get("/health", include_in_schema=False)
def health():
    return {"status": "ok"}


# ── 启动时自动训练（若模型文件不存在）────────────────────
@app.on_event("startup")
def startup_event():
    from api import deps
    if not deps.is_trained():
        print("[启动] 未发现模型文件，尝试自动训练...")
        from api.routers.train import _run_training, train_jobs, TrainRequest
        import uuid
        job_id = "auto-" + str(uuid.uuid4())[:6]
        train_jobs[job_id] = {
            "status": "pending", "progress": 0,
            "current_target": None, "results": None, "error": None,
        }
        req = TrainRequest()  # 使用默认参数训练
        t = threading.Thread(target=_run_training, args=(job_id, req), daemon=True)
        t.start()
        print(f"[启动] 后台训练已启动，job_id={job_id}")
    else:
        print("[启动] 模型文件已就绪，跳过自动训练")
        # 预热模型缓存
        from api import deps
        deps.get_models()
        print(f"[启动] 已加载 {len(deps.get_models())} 个模型")
