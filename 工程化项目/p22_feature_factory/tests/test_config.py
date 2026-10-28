# -*- coding: utf-8 -*-
"""配置层测试：加载、默认值兜底、异常路径。"""
import os

import pytest

from feat_factory import config as C

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
    """空配置也必须兜底出可运行口径：报警线是峭度线（工单 B05），非 mm/s 烈度线。"""
    s = C.Settings.from_dict({})
    assert s.warn == 4.0 and s.danger == 6.0           # 健康峭度≈3，破 4 预警 / 破 6 停机
    assert s.warn < s.danger
    assert s.topk == 6 and s.seed == 42
    assert s.get("features.primary") == 30 and s.get("features.derived") == 5
    assert s.get("signal.fs") == 100.0 and s.get("redundancy.corr_threshold") == 0.95


def test_block_list_parsing():
    text = "items:" + chr(10) + "  - a" + chr(10) + "  - b" + chr(10)
    assert C.yaml_lite(text)["items"] == ["a", "b"]


def test_nested_dict_parsing():
    text = "outer:" + chr(10) + "  inner: 5" + chr(10)
    assert C.yaml_lite(text)["outer"]["inner"] == 5


def test_outputs_list_is_independent_of_previous_run(tmp_path):
    """产物清单里的两个自指文件（report.txt / result.json）必须恒定出现。
    真实坑：清单原本按"磁盘上是否已存在"决定列不列 —— 首跑（报告还没生成）少两行，
    二次运行多两行，于是"二次运行逐字节一致"这条闸门永远过不了，除非先跑一次。"""
    from feat_factory import pipeline as P

    cfg = C.load_config(os.path.join(os.path.dirname(__file__), "..",
                                     "config", "rules.yaml"))
    clean = P.outputs_list({"cfg": cfg, "out_dir": str(tmp_path)})
    assert sum("本文件" in l for l in clean) == 2, clean
    (tmp_path / cfg.s("io.out_report")).write_text("残留", encoding="utf-8")
    (tmp_path / cfg.s("io.out_result_json")).write_text("{}" * 20, encoding="utf-8")
    assert P.outputs_list({"cfg": cfg, "out_dir": str(tmp_path)}) == clean
