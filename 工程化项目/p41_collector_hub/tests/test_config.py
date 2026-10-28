# -*- coding: utf-8 -*-
"""配置层测试：加载、默认值兜底、异常路径、文档-配置对齐。"""
import os
import re

import pytest

from collector_hub import config as C

CFG_TEXT = "warn: 10" + chr(10) + "flag: true" + chr(10) + 'name: "x"' + chr(10)
CFG_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "rules.yaml")


def test_load_default_config():
    cfg = C.load_config(CFG_PATH)
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


def test_shipped_rules_declare_three_sources_and_faults():
    cfg = C.load_config(CFG_PATH)
    assert [s["id"] for s in cfg.raw["sources"]] == ["PLC1", "PLC2", "PLC3"]
    assert all(float(s["scale"]) > 0 and float(s["latency_ms"]) > 0
               for s in cfg.raw["sources"])
    assert int(cfg.raw["retry_limit"]) > 0 and float(cfg.raw["rate_target"]) >= 95.0
    assert {f["id"] for f in cfg.raw["faults"]} <= {"PLC1", "PLC2", "PLC3"}
    assert cfg.items == cfg.raw["sources"]      # 数据源清单即流水线输入


def test_yaml_lite_fallback_parses_shipped_rules_identically():
    """零依赖兜底解析器必须与 PyYAML 对同一份 rules.yaml 得出相同结果。"""
    yaml = pytest.importorskip("yaml")
    text = open(CFG_PATH, encoding="utf-8").read()
    assert C.yaml_lite(text) == yaml.safe_load(text)


DOCS05 = os.path.join(os.path.dirname(CFG_PATH), "..", "docs",
                      "05-运行手册.md")


def test_docs05_param_table_matches_rules_yaml_keys_and_defaults():
    """运行手册 §3 参数表与 config/rules.yaml 逐字对齐：键不多不少、默认值同值。

    这条口径写在验收标准里，此前只靠人肉核对——工单的 4 条判定线
    （rate_pass_line/rate_strict_target/latency_target_ms/docs_min）加进配置时，
    文档整整漏了一轮，就是这里补的闸。
    """
    raw = C.yaml_lite(open(CFG_PATH, encoding="utf-8").read())
    scalar = {k: v for k, v in raw.items() if not isinstance(v, list)}
    section = open(DOCS05, encoding="utf-8").read().split(
        "## 3. 配置说明", 1)[1].split("\n## ", 1)[0]
    rows = {}
    for line in section.splitlines():
        m = re.match(r"^\|\s*([A-Za-z_]\w*)\s*\|[^|]*\|\s*([^|]*?)\s*\|$", line)
        if m:
            rows[m.group(1)] = m.group(2)
    assert set(rows) == set(scalar), (
        "配置有键没写进文档 %s｜文档写了不存在的键 %s"
        % (sorted(set(scalar) - set(rows)), sorted(set(rows) - set(scalar))))
    for key in sorted(rows):
        want = str(scalar[key])
        got = rows[key].strip("`")
        assert got in (want, '"%s"' % want), (key, got, want)
