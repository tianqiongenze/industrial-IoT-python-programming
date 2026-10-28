# -*- coding: utf-8 -*-
"""分层工单闸门（D/C/B/A）测试：跑真实流水线，逐层拿出可证伪的证据，而不是只查文件名。

约定：这些测试**从不执行 git，也从不创建 venv**——C/B 层只校验生成文件的**内容**；
生成树一律落在 pytest 的 tmp_path，不污染 output/。
"""
import json
import os

from proj_template import config as C
from proj_template import core
from proj_template import pipeline

CFG = os.path.join(os.path.dirname(__file__), "..", "config", "rules.yaml")


def _run(cfg, out_dir):
    sections = pipeline.run(cfg, str(out_dir))
    data = json.loads(open(os.path.join(str(out_dir), "result.json"),
                           encoding="utf-8").read())
    text = open(os.path.join(str(out_dir), "report.txt"), encoding="utf-8").read()
    return data, text, sections


def _cfg(tmp_path, **overrides):
    """只改 rules.yaml 文本（不改代码）生成配置副本。"""
    raw = open(CFG, encoding="utf-8").read()
    for k, v in overrides.items():
        old = "%s: %s" % (k, _yaml_default(k))
        assert old in raw, "配置键漂移：%s" % old
        raw = raw.replace(old, "%s: %s" % (k, v))
    p = tmp_path / "rules.yaml"
    p.write_text(raw, encoding="utf-8")
    return C.load_config(str(p))


def _yaml_default(k):
    return {"emit_pre_commit": "true", "overwrite_existing": "true"}[k]


def test_d_layer_structure_files_and_entry_point(tmp_path):
    """D 层：跟做跑通 —— 15 个模板文件全落盘、四目录齐备、入口能解析。"""
    data, text, _ = _run(C.load_config(CFG), tmp_path)
    assert data["n_files"] == 15
    assert data["tiers"]["D"] is True
    assert data["layers"]["entry_total"] == 1 and data["layers"]["entry_resolved"] == 1
    assert data["layers"]["dirs_present"] == data["layers"]["dirs_total"] == 4
    assert data["verify"]["missing"] == [] and data["verify"]["junk"] == []
    assert "D层 跟做跑通" in text
    assert "模板 15 个文件已落盘" in text


def test_c_layer_venv_and_repo_are_real_artifacts(tmp_path):
    """C 层：venv/仓库不再是文档里的话术，而是 scripts/ 与 .gitignore 的真实内容。"""
    data, text, _ = _run(C.load_config(CFG), tmp_path)
    lay = data["layers"]
    assert lay["venv_cmd"] and lay["venv_pip_restore"] and lay["git_init"]
    assert lay["gitignore_venv"] is True
    sh = open(os.path.join(str(tmp_path), "skeleton", "scripts", "setup_venv.sh"),
              encoding="utf-8").read()
    for cmd in ("python -m venv venv", "source venv/bin/activate",
                "pip install -r requirements.txt", "git init"):
        assert cmd in sh, cmd
    assert "C层 venv+仓库" in text and "python -m venv venv=是" in text
    assert data["tiers"]["C"] is True


def test_b_layer_dependencies_restorable_and_branch_rules(tmp_path):
    """B 层：运行/开发双清单都钉下限，-r 引用不断链；dev 分支脚本含 --no-ff 合并。"""
    data, text, _ = _run(C.load_config(CFG), tmp_path)
    lay = data["layers"]
    assert (lay["runtime_dep_pinned"], lay["runtime_dep_total"]) == (2, 2)
    assert (lay["dev_dep_pinned"], lay["dev_dep_total"]) == (4, 4)
    assert lay["dev_ref_runtime"] is True
    branch = open(os.path.join(str(tmp_path), "skeleton", "scripts",
                               "git_dev_branch.sh"), encoding="utf-8").read()
    for cmd in ("git branch dev", "git checkout dev", "--no-ff"):
        assert cmd in branch, cmd
    assert "B层 依赖可还原+dev分支" in text and "--no-ff 合并=是" in text
    assert data["tiers"]["B"] is True


def test_a_layer_pre_commit_gate_file_declares_configured_tools(tmp_path):
    """A 层：钩子文件按配置逐工具生成；探测只报"能否导入"，不谎报已运行。"""
    data, text, _ = _run(C.load_config(CFG), tmp_path)
    lay = data["layers"]
    assert lay["hook_declared"] == ["black", "flake8"] and lay["hook_missing"] == []
    assert data["tiers"]["A"] is True
    pc = open(os.path.join(str(tmp_path), "skeleton", ".pre-commit-config.yaml"),
              encoding="utf-8").read()
    assert "repo: local" in pc and "entry: black ." in pc
    assert "flake8 src tests --max-line-length=100" in pc
    assert "A层 pre-commit 闸门" in text
    assert "本次运行未调用 black/flake8/pylint/pre-commit 任何命令" in text


def test_a_layer_gate_follows_lint_tools_config(tmp_path):
    """改配置不改代码：闸门工具换成 flake8+pylint，钩子文件与报告同步变化。"""
    raw = open(CFG, encoding="utf-8").read().replace(
        "lint_tools:\n  - black\n  - flake8", "lint_tools:\n  - flake8\n  - pylint")
    p = tmp_path / "rules.yaml"
    p.write_text(raw, encoding="utf-8")
    data, text, _ = _run(C.load_config(str(p)), tmp_path / "out")
    assert data["layers"]["hook_declared"] == ["flake8", "pylint"]
    assert data["tiers"]["A"] is True
    pc = open(os.path.join(str(tmp_path / "out"), "skeleton", ".pre-commit-config.yaml"),
              encoding="utf-8").read()
    assert "entry: pylint src --fail-under=8.5" in pc and "id: black" not in pc
    assert "声明钩子 2 个（flake8, pylint）" in text


def test_config_only_change_can_fail_layer_a(tmp_path):
    """emit_pre_commit: false → 钩子文件消失，A 层立刻判未达标（D/C/B 不受影响）。"""
    data, text, _ = _run(_cfg(tmp_path, emit_pre_commit="false"), tmp_path / "out")
    assert data["tiers"]["A"] is False
    assert data["layers"]["hook_declared"] == [] and data["layers"]["pre_commit_declared"] is False
    assert not os.path.exists(os.path.join(str(tmp_path / "out"), "skeleton",
                                           ".pre-commit-config.yaml"))
    assert "闸门文件 未达标" in text
    assert data["tiers"]["D"] is True and data["tiers"]["C"] is True and data["tiers"]["B"] is True


def test_config_only_change_can_fail_layer_b(tmp_path):
    """把运行依赖改成没钉下限的 numpy → B 层 2/2 变 1/2，闸门翻成未达标。"""
    raw = open(CFG, encoding="utf-8").read().replace("  - numpy>=1.21", "  - numpy")
    p = tmp_path / "rules.yaml"
    p.write_text(raw, encoding="utf-8")
    data, text, _ = _run(C.load_config(str(p)), tmp_path / "out")
    assert data["layers"]["runtime_dep_pinned"] == 1
    assert data["layers"]["runtime_dep_total"] == 2
    assert data["tiers"]["B"] is False
    assert "运行依赖 1/2 条钉版本下限" in text


def test_overwrite_off_keeps_hand_edit_but_still_gates_on_disk(tmp_path):
    """overwrite_existing: false → 手改的 .gitignore 不被覆盖，C 层随即如实判未达标。"""
    out = tmp_path / "out"
    pipeline.run(_cfg(tmp_path, overwrite_existing="false"), str(out))
    gi = os.path.join(str(out), "skeleton", ".gitignore")
    open(gi, "w", encoding="utf-8").write("__pycache__/\n")       # 模拟学生手改
    data, text, _ = _run(_cfg(tmp_path, overwrite_existing="false"), out)
    assert data["layers"]["gitignore_venv"] is False
    assert data["tiers"]["C"] is False and ".gitignore 屏蔽 venv/=否" in text
    data2, _, _ = _run(C.load_config(CFG), out)                   # 默认同步→修回
    assert data2["layers"]["gitignore_venv"] is True and data2["tiers"]["C"] is True


def test_report_and_json_agree_on_every_tier_line(tmp_path):
    data, text, sections = _run(C.load_config(CFG), tmp_path)
    panel = dict(sections)["分层达标"]
    assert panel == data["tier_lines"]
    for line in panel:
        assert line in text
    for tag in ("D层 跟做跑通", "C层 venv+仓库", "B层 依赖可还原+dev分支",
                "A层 pre-commit 闸门"):
        assert tag in text


def test_run_is_reproducible(tmp_path):
    """两次运行（含不同 PYTHONHASHSEED 的等价场景）：清单、事实、判定逐字节一致。"""
    a_dir, b_dir = tmp_path / "a", tmp_path / "b"
    pipeline.run(C.load_config(CFG), str(a_dir))
    pipeline.run(C.load_config(CFG), str(b_dir))
    ja = open(os.path.join(str(a_dir), "result.json"), encoding="utf-8").read()
    jb = open(os.path.join(str(b_dir), "result.json"), encoding="utf-8").read()
    assert ja == jb
    ra = open(os.path.join(str(a_dir), "report.txt"), encoding="utf-8").read().splitlines()
    rb = open(os.path.join(str(b_dir), "report.txt"), encoding="utf-8").read().splitlines()
    assert ra[1].startswith("生成时间:")                    # 唯一免比行
    assert ra[:1] + ra[2:] == rb[:1] + rb[2:]


def test_report_body_carries_no_extra_wall_clock_lines(tmp_path):
    """确定性闸门口径：整份报告只允许头部那一条"生成时间"，判定行一律不含墙钟字样。"""
    import re
    meas = re.compile(r"(生成时间|时间戳|实测耗时|实测|耗时|用时|trained_at|timing\.txt|墙钟)")
    _, text, _ = _run(C.load_config(CFG), tmp_path)
    hits = [l for l in text.splitlines() if meas.search(l)]
    assert len(hits) == 1 and hits[0].startswith("生成时间:")


def test_generated_project_entry_point_runs(tmp_path):
    """生成的骨架不是断裂脚手架：在项目根执行 run.py 与它自带的 pytest 都应成功。"""
    import subprocess
    import sys
    pipeline.run(C.load_config(CFG), str(tmp_path))
    root = os.path.join(str(tmp_path), "skeleton")
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    r1 = subprocess.run([sys.executable, "run.py"], cwd=root, capture_output=True,
                        env=env, timeout=120)
    assert r1.returncode == 0, r1.stderr.decode("utf-8", "ignore")
    assert b"src/main.py:main" in r1.stdout
    r2 = subprocess.run([sys.executable, "-m", "pytest", "-p", "no:cacheprovider"],
                        cwd=root, capture_output=True, env=env, timeout=300)
    assert r2.returncode == 0, r2.stdout.decode("utf-8", "ignore")
    assert b"3 passed" in r2.stdout
