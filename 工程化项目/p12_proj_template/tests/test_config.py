# -*- coding: utf-8 -*-
"""配置层测试：加载、默认值兜底、异常路径。"""
import os

import pytest

from proj_template import config as C

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


def test_template_knobs_loaded_from_rules_yaml():
    """生成参数全部来自 rules.yaml（改配置不改代码）：清单/开关都能读到。"""
    cfg = C.load_config(os.path.join(os.path.dirname(__file__), "..",
                                     "config", "rules.yaml"))
    assert cfg.raw["project_name"] == "pump-ops"
    assert cfg.raw["deps"] == ["numpy>=1.21", "pandas>=1.5"]
    assert cfg.raw["lint_tools"] == ["black", "flake8"]
    assert cfg.raw["emit_pre_commit"] is True and cfg.raw["overwrite_existing"] is True


def test_template_knobs_fall_back_to_defaults_when_absent():
    """边界：配置文件里没写的键走 DEFAULTS，且不会把闸门开关误判成关闭。"""
    s = C.Settings.from_dict({"project_name": "x"})
    assert s.raw["lint_tools"] == ["black", "flake8"]
    assert s.raw["dev_deps"] and s.raw["emit_pre_commit"] is True
    assert s.raw["project_name"] == "x"


def test_yaml_parses_boolean_and_list_items():
    d = C.yaml_lite("emit_pre_commit: false" + chr(10) + "lint_tools:" + chr(10)
                    + "  - flake8" + chr(10) + "  - pylint" + chr(10))
    assert d["emit_pre_commit"] is False
    assert d["lint_tools"] == ["flake8", "pylint"]


def test_version_pinned_spec_survives_parsing():
    """异常防护：'>=3.10' 与 'black>=23.0' 必须按字符串读回，不能被当成数字。"""
    d = C.yaml_lite('python_version: ">=3.10"' + chr(10) + "dev_deps:" + chr(10)
                    + "  - black>=23.0" + chr(10))
    assert d["python_version"] == ">=3.10"
    assert d["dev_deps"] == ["black>=23.0"]
