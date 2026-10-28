# -*- coding: utf-8 -*-
"""模板表/生成/自检的分层测试：正常（齐备）、边界（空依赖、幂等）、异常（野文件、坏内容）。"""
import ast
import os

import pytest

from proj_template import core


def test_file_templates_core_files_present():
    f = core.file_templates("proj", [])
    for k in ("README.md", ".gitignore", "src/__init__.py", "tests/__init__.py"):
        assert k in f


def test_file_templates_emits_all_tier_artifacts():
    """四层各自的实物文件都必须在生成表里（A 钩子、B 双清单、C venv/分支脚本、D 入口）。"""
    f = core.file_templates("proj", ["numpy>=1.21"])
    for k in (core.PRECOMMIT, core.DEV_REQ, core.RUNTIME_REQ, "pyproject.toml",
              core.VENV_SCRIPT, core.BRANCH_SCRIPT, "src/main.py", "src/utils.py",
              "config/settings.yaml", "tests/test_main.py", "run.py"):
        assert k in f, k
    assert f[core.PRECOMMIT].startswith("# A 层")


def test_file_templates_deps_written():
    f = core.file_templates("proj", ["numpy"])
    assert "numpy" in f[core.RUNTIME_REQ]


def test_file_templates_boundary_empty_lists_still_valid():
    f = core.file_templates("proj", [], dev_deps=[], lint_tools=[])
    assert core.dep_lines(f[core.RUNTIME_REQ]) == []
    assert core.hook_ids(f[core.PRECOMMIT]) == []
    assert "repos:" in f[core.PRECOMMIT]           # 空工具集也要产出语法合法的钩子文件


def test_pre_commit_text_follows_tools_and_entry_map():
    t = core.pre_commit_text(["flake8", "pylint", "mypy"])
    assert core.hook_ids(t) == ["flake8", "pylint", "mypy"]
    assert "entry: pylint src --fail-under=8.5" in t
    assert "entry: mypy ." in t                     # 表外工具退化为 "<tool> ."
    assert t.count("language: system") == 3


def test_requirements_dev_text_references_runtime_list():
    t = core.requirements_dev_text(["pytest>=8.0", "black>=23.0"])
    lines = core.dep_lines(t)
    assert lines[0] == "-r requirements.txt"
    assert core.pinned(lines) == (2, 2)


def test_requirements_dev_text_boundary_no_dev_deps():
    assert core.dep_lines(core.requirements_dev_text([])) == ["-r requirements.txt"]


def test_pyproject_text_declares_resolvable_entry_point():
    t = core.pyproject_text("pump-ops", ">=3.10")
    assert core.scripts_text(t) == ["src.main:main"]
    assert 'requires-python = ">=3.10"' in t


def test_gitignore_masks_venv(tmp_path):
    """C 层硬要求：venv 目录必须进 .gitignore（否则整份环境被提交）。"""
    f = core.file_templates("proj", [])
    assert "venv/" in f[".gitignore"].splitlines()
    assert ".venv/" in f[".gitignore"]


def test_scripts_text_only_lists_command_lines(tmp_path):
    f = core.file_templates("proj", ["numpy>=1.21"])
    venv, branch = f[core.VENV_SCRIPT], f[core.BRANCH_SCRIPT]
    assert "python -m venv venv" in venv and "pip install -r requirements.txt" in venv
    assert "git init" in venv and "git commit" in venv
    assert "git branch dev" in branch and "git checkout dev" in branch
    assert "--no-ff" in branch


def test_ensure_idempotent(tmp_path):
    f = core.file_templates("proj", ["pandas"])
    m1, k1 = core.ensure(str(tmp_path), f)
    m2, k2 = core.ensure(str(tmp_path), f)
    assert len(m1) == len(f) and not k1
    assert m2 == [] and len(k2) == len(f)


def test_ensure_overwrite_syncs_content_and_keeps_identical(tmp_path):
    root = str(tmp_path)
    f = core.file_templates("proj", ["pandas"])
    core.ensure(root, f)
    stale = os.path.join(root, core.RUNTIME_REQ)
    open(stale, "w", encoding="utf-8").write("# 学生手改\nnumpy\n")
    made, kept = core.ensure(root, f, overwrite=True)
    assert made == [core.RUNTIME_REQ] and len(kept) == len(f) - 1
    assert "pandas" in open(stale, encoding="utf-8").read()
    made2, kept2 = core.ensure(root, f, overwrite=True)     # 内容已一致 → 不再重写
    assert made2 == [] and len(kept2) == len(f)


def test_verify_passes_after_ensure(tmp_path):
    f = core.file_templates("proj", ["pandas"])
    core.ensure(str(tmp_path), f)
    rep = core.verify(str(tmp_path), f)
    assert rep["missing"] == [] and rep["junk"] == []
    assert rep["unexpected"] == [] and rep["empty_dirs"] == []


def test_verify_reports_missing_empty_dir_and_junk(tmp_path):
    f = core.file_templates("proj", [])
    core.ensure(str(tmp_path), f)
    os.remove(os.path.join(str(tmp_path), "src", "utils.py"))
    (tmp_path / "emptydir").mkdir()
    (tmp_path / "stray.txt").write_text("野文件", encoding="utf-8")
    (tmp_path / "src" / "bad.pyc").write_bytes(b"\x00")
    rep = core.verify(str(tmp_path), f)
    assert rep["missing"] == ["src/utils.py"]
    assert rep["empty_dirs"] == ["emptydir"]
    assert rep["junk"] == ["src/bad.pyc"] and rep["unexpected"] == ["stray.txt"]


def test_inventory_reports_sizes_and_none_for_missing(tmp_path):
    f = core.file_templates("proj", ["numpy>=1.21"])
    core.ensure(str(tmp_path), f)
    inv = core.inventory(str(tmp_path), f)
    assert set(inv) == set(f) and all(v is not None for v in inv.values())
    assert inv["README.md"] == len(f["README.md"].encode("utf-8"))
    os.remove(os.path.join(str(tmp_path), "README.md"))
    assert core.inventory(str(tmp_path), f)["README.md"] is None


def test_layer_facts_reads_generated_content(tmp_path):
    f = core.file_templates("pump-ops", ["numpy>=1.21"], dev_deps=["pytest>=8.0"])
    core.ensure(str(tmp_path), f)
    lay = core.layer_facts(str(tmp_path), f)
    assert lay["dirs_missing"] == [] and lay["dirs_present"] == 4
    assert lay["runtime_dep_pinned"] == lay["runtime_dep_total"] == 1
    assert lay["dev_dep_pinned"] == lay["dev_dep_total"] == 1
    assert lay["hook_declared"] == ["black", "flake8"]
    assert lay["entry_total"] == 1 and lay["entry_resolved"] == 1


def test_layer_gates_flip_when_a_required_fact_is_missing(tmp_path):
    f = core.file_templates("pump-ops", ["numpy>=1.21"], pre_commit=False)
    core.ensure(str(tmp_path), f)
    rep = core.verify(str(tmp_path), f)
    lay = core.layer_facts(str(tmp_path), f)
    tiers = core.layer_gates(lay, rep)
    assert tiers["A"] is False and tiers["D"] is True
    assert core.layer_gates(lay, {"missing": ["x"], "empty_dirs": [],
                                  "junk": [], "unexpected": []})["D"] is False


def test_pinned_and_dep_lines_ignore_comments():
    lines = core.dep_lines("# 注释\n\nnumpy>=1.21\npandas\n-r requirements.txt\n")
    assert lines == ["numpy>=1.21", "pandas", "-r requirements.txt"]
    assert core.pinned(lines) == (2, 1)


def test_main_template_is_valid_python():
    """生成的每个 .py 必须能被 AST 解析——语法不过关的骨架等于没生成。"""
    f = core.file_templates("proj", ["numpy>=1.21"])
    py = [rel for rel in f if rel.endswith(".py")]
    assert sorted(py) == ["run.py", "src/__init__.py", "src/main.py", "src/utils.py",
                          "tests/__init__.py", "tests/test_main.py"]
    for rel in py:
        ast.parse(f[rel])


def test_layer_facts_on_empty_dir_does_not_fake_evidence(tmp_path):
    """异常档：一个文件都没落盘时，事实表必须是全 0/False，闸门不能虚报达标。"""
    f = core.file_templates("proj", ["numpy>=1.21"])
    lay = core.layer_facts(str(tmp_path), f)
    rep = core.verify(str(tmp_path), f)
    assert lay["dirs_present"] == 0 and lay["entry_total"] == 0
    assert lay["hook_declared"] == [] and lay["runtime_dep_total"] == 0
    tiers = core.layer_gates(lay, rep)
    assert tiers == {"D": False, "C": False, "B": False, "A": False}
    with pytest.raises(OSError):
        core._read(os.path.join(str(tmp_path), "nope.txt"))
