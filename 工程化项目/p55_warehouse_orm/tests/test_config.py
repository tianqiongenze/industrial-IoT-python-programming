# -*- coding: utf-8 -*-
"""配置层测试：加载、默认值兜底、异常路径、每个键都被流水线读取。"""
import os

import pytest

from warehouse_orm import config as C

CFG_TEXT = "warn: 10" + chr(10) + "flag: true" + chr(10) + 'name: "x"' + chr(10)


def test_load_default_config():
    cfg = C.load_config(os.path.join(os.path.dirname(__file__), "..",
                                     "config", "rules.yaml"))
    assert cfg.warn < cfg.danger
    assert cfg.seed > 0
    assert str(cfg.raw["db_url"]).startswith("sqlite:///")
    assert int(cfg.raw["batch_size"]) == 100
    assert int(cfg.raw["topk"]) == 3


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
    assert s.warn == 4.5 and s.danger == 6.0 and s.topk == 3
    assert s.raw["db_url"] == "sqlite:///output/warehouse.db"
    assert s.raw["index_bench_rows"] == 20000


def test_block_list_parsing():
    text = "items:" + chr(10) + "  - a" + chr(10) + "  - b" + chr(10)
    assert C.yaml_lite(text)["items"] == ["a", "b"]


def test_nested_dict_parsing():
    text = "outer:" + chr(10) + "  inner: 5" + chr(10)
    assert C.yaml_lite(text)["outer"]["inner"] == 5


def test_rules_yaml_keys_match_defaults_exactly():
    """配置承诺"改配置不改代码"：rules.yaml 的键集必须与 DEFAULTS 一一对应，
    既不允许有代码读不到的野键，也不允许有只在代码里、配置里却看不见的暗键。"""
    here = os.path.dirname(os.path.abspath(__file__))
    keys = set()
    for line in open(os.path.join(here, "..", "config", "rules.yaml"),
                     encoding="utf-8"):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or ":" not in stripped:
            continue
        if line[:1] in (" ", "\t", "-"):        # 只取顶层键
            continue
        keys.add(stripped.split(":", 1)[0].strip())
    assert keys == set(C.DEFAULTS), (sorted(keys - set(C.DEFAULTS)),
                                     sorted(set(C.DEFAULTS) - keys))
    assert len(keys) == 15


def test_every_config_key_is_actually_read():
    """DEFAULTS 里每个键都必须在源码中被 cfg.raw 读取（防止装饰性配置）。"""
    here = os.path.dirname(os.path.abspath(__file__))
    src = open(os.path.join(here, "..", "run.py"), encoding="utf-8").read()
    for name in ("core.py", "pipeline.py", "models.py", "io_utils.py", "report.py"):
        src += open(os.path.join(here, "..", "src", "warehouse_orm", name),
                    encoding="utf-8").read()
    unread = [k for k in C.DEFAULTS
              if 'raw.get("%s"' % k not in src and 'raw["%s"]' % k not in src]
    assert unread == [], "配置键写了但代码没读: %s" % unread
