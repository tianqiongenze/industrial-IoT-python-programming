# -*- coding: utf-8 -*-
"""配置层测试：加载、默认值兜底、异常路径。"""
import os

import pytest

from pd_clean import config as C

RULES_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "rules.yaml")
CFG_TEXT = "warn: 10" + chr(10) + "flag: true" + chr(10) + 'name: "x"' + chr(10)


def test_load_default_config():
    cfg = C.load_config(RULES_PATH)
    assert cfg.warn < cfg.danger
    assert cfg.seed > 0


def test_yaml_lite_basic():
    d = C.yaml_lite(CFG_TEXT)
    assert d.get("warn") == 10
    assert d.get("flag") is True
    assert d.get("name") == "x"


def test_missing_config_raises():
    with pytest.raises(FileNotFoundError):
        C.load_config("/no/such/rules.yaml")


def test_settings_defaults_fill():
    s = C.Settings.from_dict({})
    assert s.warn == 80.0 and s.topk == 3
    assert s.danger == 95.0 and s.unit == "c"
    assert s.seed == 7 and s.get("pipeline.iqr_k") == 1.5
    assert s.get("quality.gates") == {"pass": 85, "good": 88, "excellent": 90}


def test_rules_yaml_matches_builtin_defaults():
    cfg = C.load_config(RULES_PATH)
    for key in ("warn", "danger", "unit", "seed", "topk"):
        assert cfg.raw[key] == C.DEFAULTS[key], key


def test_reversed_temp_threshold_raises():
    with pytest.raises(C.ConfigError):
        C.Settings.from_dict({"pipeline": {"temp_min": 130.0}})


def test_warn_above_danger_raises():
    with pytest.raises(C.ConfigError):
        C.Settings.from_dict({"warn": 99.0, "danger": 95.0})


def test_block_list_parsing():
    text = "items:" + chr(10) + "  - a" + chr(10) + "  - b" + chr(10)
    assert C.yaml_lite(text)["items"] == ["a", "b"]


def test_nested_dict_parsing():
    text = "outer:" + chr(10) + "  inner: 5" + chr(10)
    assert C.yaml_lite(text)["outer"]["inner"] == 5
