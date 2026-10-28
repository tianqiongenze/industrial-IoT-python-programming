# -*- coding: utf-8 -*-
"""配置层测试：真实 YAML 加载、归一化、兜底、异常与死配置告警。

对应 docs/04 用例 TC-F01~TC-F08（含空输入/极值/异常三档）。
"""
import os

import pytest

from exercise_five import config as C

CFG_TEXT = "warn: 10\nflag: true\nname: \"x\"\n"


def test_load_default_config(project_root, cfg):
    """正常档：真实 rules.yaml 可加载且阈值有序。"""
    assert cfg.warn < cfg.danger
    assert cfg.seed > 0
    assert os.path.exists(os.path.join(project_root, "config", "rules.yaml"))


def test_yaml_parser_is_reported(cfg):
    """可观测档：报告用的解析器名称必须真实记录。"""
    assert cfg.parser in ("PyYAML", "yaml_lite")


def test_device_ids_normalised_end_to_end(cfg):
    """核心回归：YAML 的 01/02/03 归一化为零填充字符串键。"""
    ids = [row["id"] for row in cfg.device_rows]
    assert ids == ["01", "02", "03"]
    assert cfg.device_key(cfg.devices["remove_id"]) == "02"
    assert cfg.device_key("02") == "02"


def test_settings_defaults_fill():
    """空输入档：空字典也能补齐完整结构。"""
    cfg = C.Settings.from_dict({})
    assert cfg.warn == 80.0 and cfg.topk == 3
    assert cfg.device_rows[0]["id"] == "01"
    assert any("空" in text for text in cfg.warnings)


def test_unknown_top_level_key_flagged_as_dead_config():
    """死配置档：未识别的顶层键必须进告警，不静默忽略。"""
    cfg = C.Settings.from_dict({"oops": 1, "warn": 10.0, "danger": 20.0})
    assert any("死配置" in text for text in cfg.warnings)


def test_pep8_band_defaults_and_shipped_values(project_root, cfg):
    """工单分层线：缺省回落 DEFAULTS（D 75 / B 85），出厂 rules.yaml 同值；
    题数线（D≥3/C≥4/B≥5）、命名线 90%、每题用例线 ≥1 同样双口径核对。"""
    default = C.Settings.from_dict({})
    assert default.pep8_pass_rate_d == 75.0
    assert default.pep8_pass_rate_b == 85.0
    assert (default.d_min_correct, default.c_min_correct,
            default.b_min_correct) == (3, 4, 5)
    assert default.naming_meaningful_rate == 90.0
    assert default.tests_per_question_min == 1
    assert cfg.pep8_pass_rate_d == 75.0 and cfg.pep8_pass_rate_b == 85.0
    assert (cfg.d_min_correct, cfg.c_min_correct, cfg.b_min_correct) \
        == (3, 4, 5)
    assert cfg.naming_meaningful_rate == 90.0
    assert cfg.tests_per_question_min == 1


@pytest.mark.parametrize("bad", [{"pep8_pass_rate_d": 90.0},
                                 {"pep8_pass_rate_d": -1.0},
                                 {"pep8_pass_rate_b": 120.0},
                                 {"naming_meaningful_rate": 101.0},
                                 {"d_min_correct": -1},
                                 {"tests_per_question_min": -2}])
def test_validate_rejects_bad_pep8_bands(bad):
    """异常档：D/B 线越界、D 线高于 B 线、命名线越界、题数/用例线为负，
    启动即拒绝（含中文原因）。"""
    with pytest.raises(ValueError):
        C.Settings.from_dict(bad)


@pytest.mark.parametrize("bad", [{"warn": 99.0, "danger": 50.0},
                                 {"topk": 0},
                                 {"meta": {"tier": "Z"}}])
def test_validate_rejects_bad_config(bad):
    """异常档：阈值顺序/topk/层级非法时启动即拒绝。"""
    with pytest.raises(ValueError):
        C.Settings.from_dict(bad)


def test_missing_config_raises(tmp_path):
    """异常档：配置文件不存在时抛带路径的 FileNotFoundError。"""
    with pytest.raises(FileNotFoundError) as exc:
        C.load_config(str(tmp_path / "no.yaml"))
    assert "no.yaml" in str(exc.value)


@pytest.mark.parametrize("text,expected", [
    (CFG_TEXT, {"warn": 10, "flag": True, "name": "x"}),
    ("items:\n  - a\n  - b\n", {"items": ["a", "b"]}),
    ("outer:\n  inner: 5\n", {"outer": {"inner": 5}}),
    ("devices:\n  - id: 01\n    name: 注塑机A\n",
     {"devices": [{"id": 1, "name": "注塑机A"}]}),
])
def test_yaml_lite_parses_subset(text, expected):
    """兜底解析器档：无 PyYAML 环境下四类结构都能解析。"""
    assert C.yaml_lite(text) == expected


def test_yaml_lite_matches_pyyaml_on_shipped_config(project_root):
    """一致性档：内置兜底解析器与 PyYAML 对真实配置结果一致。"""
    text = open(os.path.join(project_root, "config", "rules.yaml"),
                encoding="utf-8").read()
    lite = C.yaml_lite(text)
    try:
        import yaml
    except ImportError:                            # pragma: no cover
        pytest.skip("环境无 PyYAML，跳过一致性比对")
    assert lite == yaml.safe_load(text)


@pytest.mark.parametrize("value,width,expected",
                         [(1, 2, "01"), ("08", 2, "08"), (7, 4, "0007")])
def test_normalize_id_table(value, width, expected):
    """极值档：八进制陷阱（08）与不同宽度都归一正确。"""
    assert C.normalize_id(value, width) == expected


@pytest.mark.parametrize("bad", [None, "", 1.5, True])
def test_normalize_id_rejects_bad(bad):
    """异常档：None/空/浮点/布尔一律拒绝成为设备键。"""
    with pytest.raises(ValueError):
        C.normalize_id(bad)


def test_every_shipped_config_key_is_consumed(project_root, cfg):
    """配置卫生：rules.yaml 的顶层键必须全部被 Settings 结构识别。"""
    assert cfg.warnings == [] or all("空" in t for t in cfg.warnings)
    assert set(cfg.raw) >= {"warn", "danger", "topk", "pep8_pass_rate_d",
                            "pep8_pass_rate_b", "d_min_correct",
                            "c_min_correct", "b_min_correct",
                            "naming_meaningful_rate",
                            "tests_per_question_min", "temperature",
                            "quadratic", "devices", "plc", "reader", "meta"}
