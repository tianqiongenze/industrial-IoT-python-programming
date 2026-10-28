# -*- coding: utf-8 -*-
"""A 层探测测试：报告只允许说"本机能否导入"，永远不许说"工具已运行"。

三档：正常（标准库/已知缺失包）、边界（空列表、全部命中）、异常（非法名、坏元数据）。
"""
import importlib.util

import pytest

from proj_template import env_probe


def test_probe_stdlib_is_installed():
    p = env_probe.probe("json")
    assert p["installed"] is True and p["desc"] == ""      # 未登记的工具没有说明文案


def test_probe_absent_tool_is_honestly_missing():
    p = env_probe.probe("definitely_not_installed_pkg_xyz")
    assert p["installed"] is False and p["version"] == ""
    assert p["desc"] == ""


def test_probe_declared_tool_carries_purpose_text():
    p = env_probe.probe("black")
    assert p["desc"] == env_probe.TOOLS["black"][1]
    assert set(p) == {"name", "installed", "version", "desc"}


@pytest.mark.parametrize("name", sorted(env_probe.TOOLS))
def test_probe_agrees_with_find_spec(name):
    """探测结论必须与 importlib 判定一致——既不虚报 installed，也不漏报。"""
    assert env_probe.probe(name)["installed"] is (importlib.util.find_spec(name) is not None)


def test_detect_is_sorted_and_covers_declared_tools():
    items = env_probe.detect()
    assert [x["name"] for x in items] == sorted(env_probe.TOOLS)
    assert all(set(x) == {"name", "installed", "version", "desc"} for x in items)


def test_detect_accepts_explicit_names_and_empty_list():
    assert env_probe.detect(["pytest"]) == [env_probe.probe("pytest")]
    assert env_probe.detect([]) == []
    assert env_probe.summary([]) == "本机可导入 0/0：无 ｜ 缺失 0 个：无"


def test_summary_counts_installed_and_missing():
    items = [{"name": "black", "installed": True, "version": "24.1.0", "desc": ""},
             {"name": "flake8", "installed": False, "version": "", "desc": ""},
             {"name": "pylint", "installed": False, "version": "", "desc": ""}]
    s = env_probe.summary(items)
    assert "本机可导入 1/3：black" in s and "缺失 2 个：flake8, pylint" in s
    assert "24.1.0" not in s                      # 摘要只报有无，版本留给 result.json


def test_hook_coverage_one_line_per_declared_hook():
    items = [env_probe.probe("black"), env_probe.probe("flake8")]
    lines = env_probe.hook_coverage(items, ["black", "flake8"])
    assert len(lines) == 2
    assert lines[0].startswith("black：钩子已声明=是，本机可导入=")
    for line in lines:
        assert "钩子已声明=是" in line


def test_hook_coverage_accepts_tool_absent_from_probe_list():
    lines = env_probe.hook_coverage([], ["mypy"])
    assert len(lines) == 1 and lines[0].startswith("mypy：")


def test_report_lines_never_claim_execution():
    items = env_probe.detect(["black", "flake8"])
    lines = env_probe.report_lines(items, ["black", "flake8"])
    text = "\n".join(lines)
    assert "本次运行未调用 black/flake8/pylint/pre-commit 任何命令" in text
    assert "钩子声明 2 个：black, flake8" in lines[0]
    for word in ("已通过", "格式化完成", "检查通过"):
        assert word not in text


def test_missing_and_usable_names_partition_the_probe_list():
    items = env_probe.detect()
    both = env_probe.usable_names(items) + env_probe.missing_names(items)
    assert sorted(both) == sorted(x["name"] for x in items)
    assert set(env_probe.usable_names(items)) & set(env_probe.missing_names(items)) == set()


def test_probe_tolerates_bad_distribution_metadata(monkeypatch):
    """发行元数据取不到时版本号留空，但 installed 结论不受影响（不误判为缺失）。"""
    def boom(_name):
        raise RuntimeError("元数据坏了")
    monkeypatch.setattr(env_probe.md, "version", boom)
    p = env_probe.probe("json")
    assert p["installed"] is True and p["version"] == ""
