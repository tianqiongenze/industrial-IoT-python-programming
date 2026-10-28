# -*- coding: utf-8 -*-
"""[project.scripts] 入口回归测试：声明的 "模块:属性" 目标必须能解析为可调用对象。

背景：pyproject.toml 声明 p33_kpi_cockpit = "kpi_cockpit.cli:main"，而 cli.py 一度
并不存在（参数解析只在 run.py 里）——pip 安装出的 console script 会在启动瞬间崩溃。
本用例不安装也不执行入口，只从本仓库 pyproject.toml 定位目标、按模块名导入并
断言可调用。
"""
import importlib
import os
import re

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _script_targets():
    with open(os.path.join(ROOT, "pyproject.toml"), encoding="utf-8") as fh:
        text = fh.read()
    section = text.split("[project.scripts]", 1)[1].split("[", 1)[0]
    return re.findall(r'=\s*"([^"]+)"', section)


def test_pyproject_entry_point_resolves_to_callable():
    assert _script_targets() == ["kpi_cockpit.cli:main"]
    for target in _script_targets():
        mod_name, attr = target.split(":", 1)
        entry = getattr(importlib.import_module(mod_name), attr)
        assert callable(entry), target
