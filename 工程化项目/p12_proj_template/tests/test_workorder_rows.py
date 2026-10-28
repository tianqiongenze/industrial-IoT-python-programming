# -*- coding: utf-8 -*-
"""工单《P1.2》验收标准四行（及格/良好/优秀/超优）的对照取证测试。

约定与本目录其他测试一致：这些测试**从不执行 git，也从不创建 venv**；
本节判的是 core.WO_ROW 四行原文，与 tests/test_tier_gates.py 判的课堂四档各判各的。
生成树一律落在 pytest 的 tmp_path，不污染 output/。
"""
import json
import os
import re
import sys

from proj_template import config as C
from proj_template import core
from proj_template import pipeline

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = os.path.join(HERE, "..", "config", "rules.yaml")
WORK_ORDER_MD = os.path.join(HERE, "..", "..", "..",
                             "工单任务书", "P1.2工单-标准Python工程模板.md")
SECTION = "工单验收四档对照（及格/良好/优秀/超优）"


def _run(cfg, out_dir):
    sections = pipeline.run(cfg, str(out_dir))
    out = str(out_dir)
    data = json.loads(open(os.path.join(out, "result.json"),
                           encoding="utf-8").read())
    text = open(os.path.join(out, "report.txt"), encoding="utf-8").read()
    return data, text, sections


def _cfg(tmp_path, *pairs, **flags):
    """只改 rules.yaml 文本（不改代码）：pairs 是逐字替换，flags 是标量开关。"""
    raw = open(CFG, encoding="utf-8").read()
    for old, new in pairs:
        assert old in raw, "配置键漂移：%s" % old
        raw = raw.replace(old, new)
    for k, v in flags.items():
        old = "%s: %s" % (k, _yaml_default(k))
        assert old in raw, "配置键漂移：%s" % old
        raw = raw.replace(old, "%s: %s" % (k, v))
    p = os.path.join(str(tmp_path), "rules.yaml")
    open(p, "w", encoding="utf-8").write(raw)
    return C.load_config(p)


def _yaml_default(k):
    return {"emit_pre_commit": "true", "overwrite_existing": "true"}[k]


def _row(text, key):
    tag = {"D": "及格", "C": "良好", "B": "优秀", "A": "超优"}[key]
    return next(l for l in text.splitlines() if l.startswith("工单%s(%s)「" % (tag, key)))


def test_all_four_workorder_rows_pass_and_carry_real_numbers(tmp_path):
    data, text, sections = _run(C.load_config(CFG), tmp_path)
    assert set(data["workorder_tiers"]) == {"D", "C", "B", "A"}
    assert all(data["workorder_tiers"][k] is True for k in "DCBA")
    assert dict(sections)[SECTION] == data["workorder_lines"]
    for line in data["workorder_lines"]:
        assert line in text
    for key in "DCBA":
        assert re.search(r"\d", _row(text, key))


def test_rows_quote_the_work_order_verbatim(tmp_path):
    """原文单一口径：WO_ROW 必须与 工单任务书/P1.2*.md 的验收标准行逐字相同。"""
    data, text, _ = _run(C.load_config(CFG), tmp_path)
    assert data["workorder_rows"] == dict(core.WO_ROW)
    for key in "DCBA":
        assert core.WO_ROW[key] in _row(text, key)
    if not os.path.exists(WORK_ORDER_MD):
        return                                     # 项目被单独拷走时不误伤
    md = open(WORK_ORDER_MD, encoding="utf-8").read()
    for key in "DCBA":
        assert core.WO_ROW[key] in md              # 逐字出现在工单文件的验收标准表里


def test_skeleton_smoke_actually_runs_the_generated_tests(tmp_path):
    """工单良好(C)『pytest通过』的最近似证据：进程内真加载生成骨架并调用它的 test_ 函数。"""
    data, text, _ = _run(C.load_config(CFG), tmp_path)
    smoke = data["workorder_evidence"]["skeleton_smoke"]
    assert smoke["error"] == "" and smoke["imported"] is True
    assert smoke["entry_returned"] == 0 and smoke["entry_spoke"] is True
    assert sorted(smoke["tests_passed"]) == ["test_convert",
                                             "test_convert_boundary_zero", "test_main_runs"]
    assert smoke["tests_failed"] == []
    lay = data["layers"]
    assert lay["generated_tests"] == len(smoke["tests_passed"]) == 3
    assert lay["pytest_cfg_declared"] is True
    assert "自带 test_ 函数 3 个通过 3 个失败 0 个" in _row(text, "C")


def test_smoke_leaves_no_import_or_bytecode_trace(tmp_path):
    out = str(tmp_path)
    before_path, before_dwb = list(sys.path), sys.dont_write_bytecode
    _run(C.load_config(CFG), out)
    assert sys.path == before_path and sys.dont_write_bytecode == before_dwb
    for key in core.SKEL_MODULES:                  # 生成骨架的模块名不留痕
        if key in sys.modules:
            assert not str(getattr(sys.modules[key], "__file__", "")).startswith(
                os.path.join(out, "skeleton"))
    pyc = [os.path.join(r, f) for r, _d, fs in os.walk(os.path.join(out, "skeleton"))
           for f in fs if f.endswith(".pyc") or r.endswith("__pycache__")]
    assert pyc == []


def test_hand_broken_generated_test_flips_workorder_c_only(tmp_path):
    """闸门可证伪：手改生成骨架里一条断言（不同步覆盖）→ 工单良好(C) 判未达标，课堂四档不动。"""
    cfg = _cfg(tmp_path, overwrite_existing="false")
    _run(cfg, tmp_path / "out")
    tp = os.path.join(str(tmp_path / "out"), "skeleton", "tests", "test_main.py")
    broken = open(tp, encoding="utf-8").read().replace("== 212", "== 999")
    assert broken != open(tp, encoding="utf-8").read()
    open(tp, "w", encoding="utf-8").write(broken)
    data, text, _ = _run(cfg, tmp_path / "out")
    assert data["workorder_tiers"]["C"] is False
    assert "自带 test_ 函数 3 个通过 2 个失败 1 个" in _row(text, "C")
    assert "→ 未达标" in _row(text, "C")
    assert all(data["tiers"][k] is True for k in "DCBA")   # 课堂闸门不看生成物内容
    for line in data["tier_lines"]:
        assert "未达标" not in line and "未通过" not in line


def test_pylint_in_lint_tools_turns_the_fail_under_note_into_evidence(tmp_path):
    """改配置不改代码：lint_tools 加 pylint → --fail-under=8.5 的 entry 落进钩子文件，
    工单提交物要求的评分截图从『未取证』清单里消失。"""
    data, text, _ = _run(_cfg(tmp_path, ("lint_tools:\n  - black\n  - flake8",
                                         "lint_tools:\n  - black\n  - flake8\n  - pylint")),
                         tmp_path / "out")
    assert data["layers"]["fail_under_declared"] is True
    assert "--fail-under 评分 entry 已声明=是" in _row(text, "C")
    assert "pylint" not in json.dumps(data["workorder_unmeasured"], ensure_ascii=False)
    pc = open(os.path.join(str(tmp_path / "out"), "skeleton", ".pre-commit-config.yaml"),
              encoding="utf-8").read()
    assert "entry: pylint src --fail-under=8.5" in pc


def test_unpinned_runtime_dep_fails_workorder_b_and_drops_a_with_it(tmp_path):
    """超优行原文是『优秀+…』：B 档前置塌了，A 档必须跟着塌，不许单独判通过。"""
    data, text, _ = _run(_cfg(tmp_path, ("  - numpy>=1.21", "  - numpy")), tmp_path / "out")
    assert data["workorder_tiers"]["B"] is False
    assert data["workorder_tiers"]["A"] is False
    assert data["workorder_tiers"]["D"] is True and data["workorder_tiers"]["C"] is True
    assert "工单优秀(B) 档前置=不成立" in _row(text, "A")
    assert "运行依赖 1/2 条钉下限" in _row(text, "B")


def test_duplicate_dev_requirement_breaks_restorable_claim(tmp_path):
    """开发清单里重复声明运行依赖（-r 已经带进 numpy）→ 『requirements完整』判未达标。"""
    data, _text, _ = _run(_cfg(tmp_path, ("dev_deps:\n  - pytest>=8.0",
                                   "dev_deps:\n  - numpy>=1.21\n  - pytest>=8.0")),
                          tmp_path / "out")
    assert data["layers"]["dep_dupes"] == ["numpy"]
    assert data["workorder_tiers"]["B"] is False


def test_no_pre_commit_file_fails_workorder_c_and_a_but_keeps_d_b(tmp_path):
    data, text, _ = _run(_cfg(tmp_path, emit_pre_commit="false"), tmp_path / "out")
    assert data["workorder_tiers"]["C"] is False and data["workorder_tiers"]["A"] is False
    assert data["workorder_tiers"]["D"] is True and data["workorder_tiers"]["B"] is True
    assert "检查工具配置：0 个钩子全部带 entry（0/0，无）" in _row(text, "C")
    assert data["tiers"]["D"] is True and data["tiers"]["B"] is True


def test_empty_readme_fails_workorder_d_only(tmp_path):
    """工单及格行点名 README，课堂 D 行只查文件在不在：清空 README 正文后两节判定分道。

    （删除文件翻不了闸门——ensure() 对缺失文件一律补写，overwrite 只管内容同步。）
    """
    cfg = _cfg(tmp_path, overwrite_existing="false")
    _run(cfg, tmp_path / "out")
    rp = os.path.join(str(tmp_path / "out"), "skeleton", "README.md")
    open(rp, "w", encoding="utf-8").write("")
    data, text, _ = _run(cfg, tmp_path / "out")
    assert data["workorder_tiers"]["D"] is False
    assert "→ 未达标" in _row(text, "D")
    assert "README.md 已落盘 0 字节且首行为一级标题=否" in _row(text, "D")
    assert all(data["workorder_tiers"][k] is True for k in "CBA")
    assert data["workorder_evidence"]["readme_bytes"] == 0
    assert all(data["tiers"][k] is True for k in "DCBA")     # 课堂 D 只数目录与缺失数
    data2, _, _ = _run(C.load_config(CFG), tmp_path / "out")  # 默认同步→补回正文
    assert data2["workorder_tiers"]["D"] is True


def test_classroom_ladder_never_measures_the_good_c_clauses(tmp_path):
    """课程口径缺口的正面证据：课堂四条分层行里既没有 pytest 通过，也没有检查工具配置生效。"""
    data, text, _ = _run(C.load_config(CFG), tmp_path)
    joined = "".join(data["tier_lines"])
    for needle in ("pytest", "testpaths", "检查工具配置生效"):
        assert needle not in joined
    assert "检查工具配置" in _row(text, "C")       # 由工单对照节补上这条门禁


def test_unmeasured_items_are_named_and_block_the_praise_word(tmp_path):
    data, text, _ = _run(C.load_config(CFG), tmp_path)
    ext = data["workorder_unmeasured"]
    assert set(ext) == {"D", "C", "B", "A"} and all(len(v) > 0 for v in ext.values())
    for key in "DCBA":
        row = _row(text, key)
        if ext[key] and data["workorder_tiers"][key]:
            assert "→ 达标" not in row and "→ 本节取证项 通过" in row
    tail = [l for l in text.splitlines() if l.startswith("    未取证项")]
    assert len(tail) == sum(1 for k in "DCBA" if ext[k])
    assert "未取证子项合计 %d 条" % sum(len(v) for v in ext.values()) in text


def test_ci_branch_is_reported_absent_not_faked(tmp_path):
    data, text, _ = _run(C.load_config(CFG), tmp_path)
    assert data["workorder_evidence"]["ci_workflows"] == []
    row = _row(text, "A")
    assert ".github/workflows 下 CI 文件 0 个" in row
    assert "→ 本节取证项 通过" in row               # 走工单原文的『或 pre-commit 钩子』一支
    ext = json.dumps(data["workorder_unmeasured"], ensure_ascii=False)
    assert "GitHub Actions CI 未产出" in ext and "工单原文是『CI 或 pre-commit 钩子』" in ext


def test_workorder_section_carries_no_wallclock(tmp_path):
    """确定性红线：对照节只报计数与布尔，不出现毫秒/秒级耗时，也不出现『实测』字样。"""
    _data, text, _ = _run(C.load_config(CFG), tmp_path)
    body = text[text.index(SECTION):]
    body = body[:body.index("[分层达标]")]
    assert not re.search(r"\d+(\.\d+)?\s*(ms|毫秒|秒|s)\b", body)
    assert "实测" not in body and "耗时" not in body and "trained_at" not in body
