# -*- coding: utf-8 -*-
"""规范度量器自身的测试：证明它是"真测量"而不是固定输出。

策略：往临时目录写一份**故意违规**的源码，检查器必须报出对应规则；
再写一份干净源码，必须 100% 通过。避免"分数永远 99%"的自证陷阱。
"""
from exercise_five import stylecheck

DIRTY = '"""坏例子"""\nimport os\n\n\ndef Bad_Name(x):\n%sreturn x  \n' % chr(9)
CLEAN = '"""好例子"""\n\n\ndef good_name(value):\n    """说明。"""\n' \
        '    return value\n'


def test_dirty_source_reports_expected_rules(tmp_path):
    """违规源码：必须命中缩进 Tab / 行尾空格 / 命名 / 缺 docstring。"""
    path = tmp_path / "dirty.py"
    path.write_text(DIRTY, encoding="utf-8")
    violations, _ = stylecheck.check_file(str(path))
    codes = {item[0] for item in violations}
    assert "E101" in codes and "W291" in codes and "C0103" in codes


def test_clean_source_scores_100(tmp_path):
    """干净源码：0 违规、100%（证明满分可达，分数不是编出来的）。"""
    path = tmp_path / "clean.py"
    path.write_text(CLEAN, encoding="utf-8")
    result = stylecheck.check_paths([str(path)])
    assert result["violations"] == [] and result["score"] == 100.0


def test_per_file_scores_are_reported(tmp_path):
    """逐文件得分明细：每文件 total/passed/score 齐备且加总=总体口径。"""
    (tmp_path / "clean.py").write_text(CLEAN, encoding="utf-8")
    (tmp_path / "dirty.py").write_text(DIRTY, encoding="utf-8")
    result = stylecheck.check_paths([str(tmp_path / "clean.py"),
                                     str(tmp_path / "dirty.py")])
    assert [row["file"].endswith(".py") for row in result["per_file"]]
    assert sum(row["total"] for row in result["per_file"]) == result["total"]
    assert sum(row["passed"] for row in result["per_file"]) == \
        result["passed"]
    scores = {row["file"]: row["score"] for row in result["per_file"]}
    assert any(s == 100.0 for s in scores.values())
    assert any(s < 100.0 for s in scores.values())


def test_long_line_detected(tmp_path):
    """极值档：超长行必须触发 E501（行长上限来自常量）。"""
    path = tmp_path / "long.py"
    path.write_text('"""长"""\nX = "%s"\n' % ("a" * 90), encoding="utf-8")
    violations, _ = stylecheck.check_file(str(path))
    assert any(item[0] == "E501" for item in violations)


def test_syntax_error_is_counted(tmp_path):
    """异常档：语法错误文件不崩溃，而是记为 E999。"""
    path = tmp_path / "broken.py"
    path.write_text("def (:\n", encoding="utf-8")
    violations, _ = stylecheck.check_file(str(path))
    assert any(item[0] == "E999" for item in violations)


def test_empty_path_list_scores_100_not_crash():
    """空输入档：无文件可查时返回 100% 且 checked_files=0（不虚报）。"""
    result = stylecheck.check_paths([])
    assert result["checked_files"] == 0 and result["score"] == 100.0


def test_shipped_project_measured_and_documented(project_root):
    """真实项目实测：得分/分类计数结构完整可进报告。"""
    result = stylecheck.summarize(project_root)
    assert result["checked_files"] >= 10
    for key in ("score", "total", "passed", "naming_violations",
                "missing_docstrings", "long_lines"):
        assert key in result


def test_tool_probe_is_honest(project_root):
    """工具探测必须给出真实可用性（装了才有版本号，没装写原因）。"""
    tools = stylecheck.probe()
    assert set(tools) == set(stylecheck.TOOLS)
    for name, info in tools.items():
        assert isinstance(info["available"], bool)
        if not info["available"]:
            assert info["reason"], name
        else:
            assert info["version"], name


def test_pylint_score_never_fabricated():
    """pylint 不可用时 score 必须是 None（绝不用百分比冒充 pylint）。"""
    result = stylecheck.pylint_score(["src"])
    if not result["available"]:
        assert result["score"] is None
        assert result["note"]
