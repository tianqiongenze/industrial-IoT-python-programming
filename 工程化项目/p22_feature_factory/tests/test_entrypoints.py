# -*- coding: utf-8 -*-
"""[project.scripts] 入口回归测试：声明的 "模块:属性" 目标必须能解析为可调用对象。

背景一：pyproject.toml 声明 p22_feature_factory = "feat_factory.cli:main"，而 cli.py
一度并不存在——pip 安装出的 console script 会在启动瞬间崩溃。
背景二：旧 run.py 的非 --quiet 路径把 pipeline.run 的返回值（dict）当列表索引
（sections[-1]），当场 KeyError: -1——入口修好后仍可能回归，故一并立闸。
本组用例不安装；对入口只做导入解析，对非 --quiet 路径用 tmp_path 输出目录真跑。
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
    assert _script_targets() == ["feat_factory.cli:main"]
    for target in _script_targets():
        mod_name, attr = target.split(":", 1)
        entry = getattr(importlib.import_module(mod_name), attr)
        assert callable(entry), target


def test_main_non_quiet_exits_zero(tmp_path, capsys):
    """不带 --quiet 的完整非静默路径：退出码 0 且打印末节结论（KeyError: -1 回归闸）。"""
    from feat_factory import cli
    assert cli.main(["--outdir", str(tmp_path)]) == 0
    printed = capsys.readouterr().out
    assert printed.strip(), "非 --quiet 路径应打印结论行"
    assert os.path.exists(os.path.join(str(tmp_path), "report.txt"))
