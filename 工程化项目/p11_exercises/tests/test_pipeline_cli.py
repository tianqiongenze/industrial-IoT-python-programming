# -*- coding: utf-8 -*-
"""端到端测试：pipeline 产物、报告逐题判定、两次运行字节级一致、CLI 旗标、
工单四档（及格D/良好C/优秀B/超优A）真实运行判定与"只改配置即可翻档"的可证伪。

对应 NF-1 可复现（docs/01 §5）与 docs/05 运行手册里的全部命令。
写出报告/JSON 都落在 pytest 的 tmp_path 沙箱，不污染仓库 output/。
"""
import os
import re
import subprocess
import sys

import pytest

from exercise_five import config, io_utils, pipeline, selfcheck

RUN = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(
    __file__))), "run.py")


def _sandbox(tmp_path, project_root):
    """构造隔离沙箱：配置指向真实 rules.yaml，输出写进 tmp_path。"""
    out_dir = tmp_path / "output"
    root = tmp_path / "project"
    (root / "docs").mkdir(parents=True)
    (root / "src").mkdir(parents=True)
    cfg = config.load_config(os.path.join(project_root, "config",
                                          "rules.yaml"))
    return cfg, str(out_dir), str(root)


def test_pipeline_writes_report_with_per_question_verdicts(tmp_path,
                                                           project_root):
    """报告必须逐题给出 PASS/FAIL 五行（工单验收要能一眼看到五题）。"""
    cfg, out_dir, root = _sandbox(tmp_path, project_root)
    pipeline.run(cfg, out_dir=out_dir, root=root)
    text = open(os.path.join(out_dir, "report.txt"), encoding="utf-8").read()
    for number in ("题1", "题2", "题3", "题4", "题5"):
        assert "%s: PASS" % number in text, number
    assert "pylint 评分：不可用" in text or "pylint 实测评分" in text


def test_pipeline_result_json_shape(tmp_path, project_root):
    """result.json 是答辩取数入口：五题+分层+规范+笔记四类键齐备。"""
    cfg, out_dir, root = _sandbox(tmp_path, project_root)
    pipeline.run(cfg, out_dir=out_dir, root=root)
    data = io_utils.read_json(os.path.join(out_dir, "result.json"))
    assert set(data["exercises"]) == {"题1", "题2", "题3", "题4", "题5"}
    assert set(data["tier_gates"]["tier_pass"]) == {"D", "C", "B", "A"}
    assert data["style"]["score"] >= 85.0
    assert data["notes"]["verified_entries"] >= 10
    assert all(v["available"] is not None for v in data["tools"].values())


def test_pipeline_generates_notes_into_docs(tmp_path, project_root):
    """迁移笔记作为项目生成的交付物落到 docs/09（不在 output/ 之外乱写）。"""
    cfg, out_dir, root = _sandbox(tmp_path, project_root)
    pipeline.run(cfg, out_dir=out_dir, root=root)
    path = os.path.join(root, "docs", "09-C转Python迁移笔记.md")
    assert os.path.exists(path)
    text = open(path, encoding="utf-8").read()
    assert text.count("\n| ") >= 10 and "决策矩阵" in text


def test_two_runs_are_identical(tmp_path, project_root):
    """确定性：连续两次运行 output/ 全部文件字节一致。"""
    cfg, out_dir, root = _sandbox(tmp_path, project_root)
    pipeline.run(cfg, out_dir=out_dir, root=root)
    first = {name: open(os.path.join(out_dir, name), "rb").read()
             for name in ("report.txt", "result.json")}
    pipeline.run(cfg, out_dir=out_dir, root=root)
    second = {name: open(os.path.join(out_dir, name), "rb").read()
              for name in ("report.txt", "result.json")}
    assert first == second


@pytest.mark.parametrize("extra", [[], ["--quiet"], ["--tier", "B"],
                                   ["--no-notes"], ["--list-tools"],
                                   ["--help"]])
def test_cli_flags_exit_zero(extra, tmp_path, project_root):
    """run.py 的全部文档化旗标都要退出码 0。"""
    out_dir = tmp_path / "out"
    root = tmp_path / "proj"
    (root / "docs").mkdir(parents=True)
    cmd = [sys.executable, RUN, "--outdir", str(out_dir), "--root", str(root)]
    cmd += extra
    done = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    assert done.returncode == 0, done.stderr
    if extra not in (["--help"], ["--list-tools"]):
        assert out_dir.exists()


def test_cli_bad_config_is_reported(tmp_path):
    """异常档：阈值顺序颠倒的配置要让 CLI 以非 0 退出并给出原因。"""
    path = tmp_path / "bad.yaml"
    path.write_text("warn: 99.0\ndanger: 10.0\n", encoding="utf-8")
    done = subprocess.run([sys.executable, RUN, "--config", str(path),
                           "--outdir", str(tmp_path / "out"),
                           "--root", str(tmp_path / "proj")],
                          capture_output=True, text=True, timeout=120)
    assert done.returncode != 0
    assert "阈值顺序颠倒" in (done.stderr + done.stdout)


SHIPPED_RULES = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "config", "rules.yaml")


def _flipped_config(tmp_path, key, value, project_root):
    """只改配置不改代码：复制出厂 rules.yaml，把某一个线值换掉后重载。"""
    text = open(SHIPPED_RULES, encoding="utf-8").read()
    pattern = r"^%s: .*$" % key
    assert re.search(pattern, text, re.M), "出厂配置缺键 %s" % key
    new_text, hits = re.subn(pattern, "%s: %s" % (key, value), text, count=1,
                             flags=re.M)
    assert hits == 1
    path = tmp_path / ("flip_%s.yaml" % key)
    path.write_text(new_text, encoding="utf-8")
    cfg = config.load_config(str(path))
    assert getattr(cfg, key) == value
    return cfg


def _real_run(tmp_path, project_root, cfg=None, want_notes=False):
    """真实项目根跑一遍流水线（报告/JSON 写 tmp），返回 result + 报告正文。"""
    cfg = cfg or config.load_config(SHIPPED_RULES)
    out_dir = str(tmp_path / "output")
    pipeline.run(cfg, out_dir=out_dir, root=project_root,
                 want_notes=want_notes)
    result = io_utils.read_json(os.path.join(out_dir, "result.json"))
    text = open(os.path.join(out_dir, "report.txt"), encoding="utf-8").read()
    return result, text


def test_tiers_block_covers_four_work_order_letters_plus_floor(tmp_path,
                                                              project_root):
    """result.json 的 tiers 必须正好覆盖工单四档 + 不占字母的保底组。"""
    result, _text = _real_run(tmp_path, project_root)
    tiers = result["tiers"]
    assert set(tiers) == {"D", "C", "B", "A", selfcheck.FLOOR}
    assert [tiers[t]["name"] for t in selfcheck.TIER_ORDER] \
        == ["及格", "良好", "优秀", "超优"]
    for tier in selfcheck.TIER_ORDER:
        assert set(tiers[tier]) == {"name", "criterion", "summary", "verdict"}
    assert tiers[selfcheck.FLOOR]["counts_for_work_order"] is False
    assert result["tier_gates"]["tier_pass"].get(selfcheck.FLOOR) is None


def test_shipped_run_adjudicates_all_four_tiers_pass(tmp_path, project_root):
    """出厂真实运行：四档逐档判定均为"达标"，且重渲染的笔记字节不变。"""
    notes_path = os.path.join(project_root, "docs",
                              "09-C转Python迁移笔记.md")
    before = open(notes_path, "rb").read()
    result, _text = _real_run(tmp_path, project_root, want_notes=True)
    for tier in selfcheck.TIER_ORDER:
        info = result["tiers"][tier]
        assert info["verdict"] == "达标", info
        assert result["tier_gates"]["tier_pass"][tier] is True
    assert result["tiers"][selfcheck.FLOOR]["verdict"] == "达标"
    # 仓库基线里的生成物与生成器一致（测试不引入任何漂移）
    assert open(notes_path, "rb").read() == before


@pytest.mark.parametrize("tier,keyword", [
    ("D", "≥3题正确运行；PEP 8≥75%；有基础注释"),
    ("C", "4题；命名有意义"),
    ("B", "5题全对；PEP 8≥85%；结构清晰"),
    ("A", "优秀+每题附测试用例与《迁移笔记》"),
])
def test_tier_criterion_text_is_work_order_wording(tmp_path, project_root,
                                                   tier, keyword):
    """档位口径回显：criterion 必须是工单 P1.1「验收标准」四行原文（逐字）。"""
    result, _text = _real_run(tmp_path, project_root)
    assert result["tiers"][tier]["criterion"] == keyword


def test_workorder_rows_are_quoted_verbatim(tmp_path, project_root):
    """直接对表工单文件：四行原文逐字进报告，改一个字（哪怕只加空格）都会红。"""
    wo = os.path.abspath(os.path.join(
        os.path.dirname(__file__), "..", "..", "..",
        "工单任务书", "P1.1工单-Python基础练习五题.md"))
    if not os.path.exists(wo):
        pytest.skip("工单任务书不在仓库内的相对位置（项目被单独拷走时）")
    rows = {}
    for line in open(wo, encoding="utf-8").read().splitlines():
        m = re.match(r"^\|\s*(及格\(D\)|良好\(C\)|优秀\(B\)|超优\(A\))\s*\|"
                     r"\s*(.+?)\s*\|\s*$", line.strip())
        if m:
            rows[m.group(1)] = m.group(2)
    assert len(rows) == 4, rows
    result, text = _real_run(tmp_path, project_root)
    for label, row in rows.items():
        tier = label.split("(")[1][:-1]
        assert result["tiers"][tier]["criterion"] == row, label
        assert row in text, (label, row)


def test_report_lines_and_result_json_tiers_agree(tmp_path, project_root):
    """报告与 JSON 同源：四档 + 保底的汇总行逐字出现在 report.txt 里。"""
    result, text = _real_run(tmp_path, project_root)
    for tier in selfcheck.TIER_ORDER:
        info = result["tiers"][tier]
        assert info["summary"] in text, (tier, info["summary"])
        assert info["criterion"] in text, tier
        head = "【%s · %s层】达标=%s" % (tier, info["name"], info["verdict"])
        assert head in text, head
        for gate in result["tier_gates"]["gates"]:
            if gate["tier"] == tier:
                assert gate["item"] in text, gate["item"]
    floor = result["tiers"][selfcheck.FLOOR]
    assert floor["summary"] in text
    assert floor["counts_for_work_order"] is False


@pytest.mark.parametrize("key,value,broken,others", [
    ("d_min_correct", 6, ["D"], ["C", "B"]),
    ("c_min_correct", 6, ["C"], ["D", "B"]),
    ("b_min_correct", 6, ["B"], ["D", "C"]),
])
def test_config_only_change_flips_that_tier(tmp_path, project_root, key,
                                            value, broken, others):
    """只改 rules.yaml 的一根线（不动任何代码）→ 对应工单档判"未达标"，
    更低档不受影响；本轮 want_notes=False，故超优(A) 恒判不过（不虚构）。"""
    cfg = _flipped_config(tmp_path, key, value, project_root)
    result, text = _real_run(tmp_path, project_root, cfg=cfg)
    for tier in broken:
        info = result["tiers"][tier]
        assert info["verdict"] == "未达标", info
        assert result["tier_gates"]["tier_pass"][tier] is False
        head = "【%s · %s层】达标=未达标" % (tier, info["name"])
        assert head in text, head
    for tier in others:
        assert result["tiers"][tier]["verdict"] == "达标", result["tiers"][tier]
    assert result["tiers"]["A"]["verdict"] == "未达标"
    if key == "b_min_correct":
        chain = [g for g in result["tier_gates"]["gates"]
                 if g["tier"] == "A" and "优秀(B)层达标" in g["item"]]
        assert len(chain) == 1 and chain[0]["ok"] is False
    if key == "d_min_correct":
        line = [g for g in result["tier_gates"]["gates"]
                if g["tier"] == "D" and "及格线 ≥6 题" in g["item"]]
        assert len(line) == 1 and line[0]["ok"] is False
    if key == "c_min_correct":
        assert result["tiers"]["C"]["summary"].count("线 ≥6") == 1


def test_config_only_change_moves_lines_echoed_in_report(tmp_path,
                                                         project_root):
    """百分比线同样"只改配置"可移动：证据行回显的线值随 rules.yaml 变化
    （出厂实测 PEP 8 与命名合格率均为 100.0%，故线抬到 100.0 仍判达标；
    低于线的可证伪性在 test_tier_d/test_tier_c 的脏样例里锁定）。"""
    cfg = _flipped_config(tmp_path, "pep8_pass_rate_b", 100.0, project_root)
    result, text = _real_run(tmp_path, project_root, cfg=cfg)
    assert result["tiers"]["B"]["verdict"] == "达标"
    assert "≥ B 层线 100.0%" in text
    # 工单原文不跟着线值漂：D 档 criterion 仍是 75%，线值只出现在证据段
    assert result["tiers"]["D"]["criterion"] == "≥3题正确运行；PEP 8≥75%；有基础注释"
    assert "≥ 75.0%" in result["tiers"]["D"]["summary"]
    cfg2 = _flipped_config(tmp_path, "naming_meaningful_rate", 100.0,
                           project_root)
    result2, text2 = _real_run(tmp_path, project_root, cfg=cfg2)
    assert result2["tiers"]["C"]["verdict"] == "达标"
    assert "≥ 命名线 100.0%" in text2


def test_line_order_guard_rejects_impossible_band(project_root, tmp_path):
    """配置守护：把及格(D) 线抬到高于优秀(B) 线属于口径颠倒，加载即拒绝。"""
    text = open(SHIPPED_RULES, encoding="utf-8").read()
    bad = text.replace("pep8_pass_rate_d: 75.0", "pep8_pass_rate_d: 92.0")
    path = tmp_path / "inverted.yaml"
    path.write_text(bad, encoding="utf-8")
    with pytest.raises(ValueError) as exc:
        config.load_config(str(path))
    assert "PEP 8 分层线顺序颠倒" in str(exc.value)


def test_no_notes_run_adjudicates_superior_tier_fail(tmp_path, project_root):
    """--no-notes 诚实口径：笔记相关项判不过，超优(A) 未达标（不虚构）。"""
    cfg, out_dir, root = _sandbox(tmp_path, project_root)
    pipeline.run(cfg, out_dir=out_dir, root=root, want_notes=False)
    result = io_utils.read_json(os.path.join(out_dir, "result.json"))
    assert result["tiers"]["A"]["verdict"] == "未达标"
    assert result["notes"]["exists"] is False
