# -*- coding: utf-8 -*-
"""
模型读写层：保存/加载 XGBoost 模型、LabelEncoder、训练元数据
"""

import json
import joblib
from pathlib import Path
from xgboost import XGBRegressor

# 延迟导入 config，避免循环依赖
def _get_paths():
    from config import MODELS_DIR
    models_dir = Path(MODELS_DIR)
    return (
        models_dir,
        models_dir / "training_meta.json",
        models_dir / "label_encoder.pkl",
    )


def models_trained() -> bool:
    """检查是否已完成训练（meta 文件存在即视为已训练）"""
    _, meta_file, _ = _get_paths()
    return meta_file.exists()


def load_meta() -> dict:
    """加载训练元数据"""
    _, meta_file, _ = _get_paths()
    if meta_file.exists():
        return json.loads(meta_file.read_text(encoding="utf-8"))
    return {}


def save_meta(meta: dict):
    """保存训练元数据"""
    models_dir, meta_file, _ = _get_paths()
    models_dir.mkdir(exist_ok=True)
    meta_file.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def load_model(target_name: str) -> XGBRegressor:
    """加载单个目标的 XGBoost 模型"""
    models_dir, _, _ = _get_paths()
    path = models_dir / f"model_xgb_{target_name}.json"
    m = XGBRegressor()
    m.load_model(str(path))
    return m


def load_all_models() -> dict:
    """批量加载所有目标模型，返回 {target: XGBRegressor}"""
    models_dir, _, _ = _get_paths()
    result = {}
    for path in models_dir.glob("model_xgb_*.json"):
        target = path.stem.replace("model_xgb_", "", 1)
        m = XGBRegressor()
        m.load_model(str(path))
        result[target] = m
    return result


def save_label_encoder(le):
    """保存 LabelEncoder"""
    models_dir, _, le_file = _get_paths()
    models_dir.mkdir(exist_ok=True)
    joblib.dump(le, le_file)


def load_label_encoder():
    """加载 LabelEncoder"""
    _, _, le_file = _get_paths()
    return joblib.load(le_file)
