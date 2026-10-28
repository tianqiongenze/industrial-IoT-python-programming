# -*- coding: utf-8 -*-
"""配置层测试：加载、默认值兜底、异常路径；rules.yaml 每个键都必须在代码中被读取。"""
import os

import pytest

from ml_service import config as C

CFG_TEXT = "seed: 11" + chr(10) + "flag: true" + chr(10) + 'name: "x"' + chr(10)

PROJECT_KEYS = {  # config/rules.yaml 的键 → 读取方（docs/03 追踪表同源）
    "features_path", "labels_path", "teacher_model", "p5_db", "model_name",
    "n_features", "n_fallback", "seed", "test_size", "cv_folds", "min_f1",
    "grid_n_estimators", "grid_max_depth", "port", "host",
    "bench_requests", "warmup", "window_size", "teacher_samples",
    "explain_topk",
}


def test_load_default_config():
    cfg = C.load_config(os.path.join(os.path.dirname(__file__), "..",
                                     "config", "rules.yaml"))
    assert set(cfg.raw.keys()) >= PROJECT_KEYS
    assert cfg.min_f1 == 0.80 and cfg.seed == 42
    assert cfg.port == 8899 and cfg.model_name == "model_v1.joblib"
    assert list(cfg.raw["grid_n_estimators"]) == [50, 100, 200]
    assert cfg.raw["grid_max_depth"][2] is None
    assert int(cfg.raw["explain_topk"]) == 3          # A层可解释性 Top-k 旋钮


def test_yaml_lite_basic():
    d = C.yaml_lite(CFG_TEXT)
    assert d.get("seed") == 11
    assert d.get("flag") is True
    assert d.get("name") == "x"


def test_yaml_lite_inline_list_and_null():
    d = C.yaml_lite("grid_max_depth: [4, 6, null]")
    assert d["grid_max_depth"] == [4, 6, None]


def test_missing_config_raises():
    with pytest.raises(FileNotFoundError):
        C.load_config("/no/such/rules.yaml")


def test_settings_defaults_fill():
    s = C.Settings.from_dict({})
    assert s.seed == 42 and s.min_f1 == 0.80
    assert s.raw["model_name"] == "model_v1.joblib"
    assert s.raw["p5_db"].endswith("warehouse.db")


def test_block_list_parsing():
    text = "items:" + chr(10) + "  - a" + chr(10) + "  - b" + chr(10)
    assert C.yaml_lite(text)["items"] == ["a", "b"]


def test_nested_dict_parsing():
    text = "outer:" + chr(10) + "  inner: 5" + chr(10)
    assert C.yaml_lite(text)["outer"]["inner"] == 5
