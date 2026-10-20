# -*- coding: utf-8 -*-
"""配置层测试：加载、默认值兜底、异常路径。"""
import os

import pytest

from warehouse_orm import config as C

CFG_TEXT = "warn: 10" + chr(10) + "flag: true" + chr(10) + 'name: "x"' + chr(10)


def test_load_default_config():
    cfg = C.load_config(os.path.join(os.path.dirname(__file__), "..",
                                     "config", "rules.yaml"))
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
    assert s.warn == 80.0 and s.topk == 2


def test_block_list_parsing():
    text = "items:" + chr(10) + "  - a" + chr(10) + "  - b" + chr(10)
    assert C.yaml_lite(text)["items"] == ["a", "b"]


def test_nested_dict_parsing():
    text = "outer:" + chr(10) + "  inner: 5" + chr(10)
    assert C.yaml_lite(text)["outer"]["inner"] == 5
