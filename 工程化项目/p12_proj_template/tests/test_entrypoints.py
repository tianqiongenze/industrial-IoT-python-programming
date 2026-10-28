# -*- coding: utf-8 -*-
"""A 层规范闸门的入口回归测试：[project.scripts] 声明的目标必须真能解析（断裂脚手架即缺陷）。

背景：本项目 pyproject.toml 曾声明 proj_template.cli:main 而 cli 模块根本不存在——
生成器"声明了却给不出"的脚手架，新人第一天就踩空。这里既不安装也不执行入口，
只用文件定位 + AST 判断"模块:属性"是否存在，因此永远不会碰 git / venv。
"""
import os

from proj_template import config as C
from proj_template import core
from proj_template import pipeline

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CFG = os.path.join(ROOT, "config", "rules.yaml")


def _read_own_pyproject():
    return core._read(os.path.join(ROOT, "pyproject.toml"))


def _scaffold(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "src" / "main.py").write_text(
        "import os\n"
        "def f():\n    return os\n"
        "class K:\n    pass\n"
        "VALUE = 1\n"
        "ANNOT: int = 2\n", encoding="utf-8")
    return str(tmp_path)


def test_project_own_scripts_target_resolves():
    """本仓库自己声明的 p12_proj_template = proj_template.cli:main 必须解析成功。"""
    assert core.scripts_text(_read_own_pyproject()) == ["proj_template.cli:main"]
    recs = core.resolve_scripts(ROOT, _read_own_pyproject(),
                                extra_bases=[os.path.join(ROOT, "src")])
    assert len(recs) == 1 and recs[0]["resolves"] is True, recs[0]
    assert recs[0]["file"].endswith("proj_template/cli.py")


def test_generated_project_scripts_targets_resolve(tmp_path):
    """生成树里每一个 [project.scripts] 目标都指向真实存在的模块属性。"""
    pipeline.run(C.load_config(CFG), str(tmp_path))
    root = os.path.join(str(tmp_path), "skeleton")
    recs = core.resolve_scripts(root, core._read(os.path.join(root, "pyproject.toml")))
    assert [r["target"] for r in recs] == ["src.main:main"]
    assert all(r["resolves"] for r in recs), recs
    assert recs[0]["file"] == "src/main.py"


def test_broken_target_is_reported_not_silently_passed(tmp_path):
    """异常档：模块不存在 / 属性不存在 / 写法非法，都必须显式判不解析并给原因。"""
    root = _scaffold(tmp_path)
    toml = ('[project.scripts]\n'
            'a = "src.nope:main"\n'
            'b = "src.main:not_there"\n'
            'c = "no-colon-module"\n')
    recs = core.resolve_scripts(root, toml)
    assert [r["resolves"] for r in recs] == [False, False, False]
    assert recs[0]["reason"] == "模块文件不存在"
    assert "未定义属性 not_there" in recs[1]["reason"]
    assert "目标写法非法" in recs[2]["reason"]


def test_scripts_text_ignores_other_toml_sections():
    toml = ('[project]\nname = "x"\n\n[project.scripts]\nx = "src.main:main"\n\n'
            '[tool.pytest.ini_options]\ntestpaths = ["tests"]\n')
    assert core.scripts_text(toml) == ["src.main:main"]


def test_defines_attr_covers_def_class_and_assignment(tmp_path):
    root = _scaffold(tmp_path)
    path = os.path.join(root, "src", "main.py")
    for attr in ("f", "K", "VALUE", "ANNOT"):
        assert core.defines_attr(path, attr) is True, attr
    assert core.defines_attr(path, "os") is False          # import 名不算顶层定义
    assert core.defines_attr(path, "nope") is False


def test_find_module_file_prefers_package_and_returns_empty_when_absent(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    assert core.find_module_file(str(tmp_path), "pkg").endswith(
        os.path.join("pkg", "__init__.py"))
    assert core.find_module_file(str(tmp_path), "missing.mod") == ""


def test_find_module_file_uses_extra_bases(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "deep.py").write_text("def main():\n    return 0\n", encoding="utf-8")
    got = core.find_module_file(str(tmp_path), "deep", extra_bases=[str(src)])
    assert got.endswith("deep.py")


def test_syntax_error_or_missing_file_is_not_resolvable(tmp_path):
    bad = tmp_path / "bad.py"
    bad.write_text("def (:\n", encoding="utf-8")
    assert core.defines_attr(str(bad), "x") is False
    assert core.defines_attr(str(tmp_path / "none.py"), "x") is False
