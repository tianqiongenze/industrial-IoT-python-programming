# -*- coding: utf-8 -*-
"""工单《P3》验收标准四行的**逐字对表**回归锁。

本目录其余测试判的是"每一档的证据是否成立"；本节只判一件事：
报告「分层达标」四行的行首必须等于 工单任务书/P3工单-产线KPI仪表盘与自动日报.md
验收标准表里的原文，一个字都不许改（连空格都不许）。线值一旦变化，
只能改 config/rules.yaml 并在箭头后的证据段回显，不得回写进"原文"。
"""
import os
import re

import pytest

from kpi_cockpit import config as C
from kpi_cockpit import pipeline

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CFG = os.path.join(HERE, "config", "rules.yaml")
WORK_ORDER_MD = os.path.join(HERE, "..", "..", "工单任务书",
                             "P3工单-产线KPI仪表盘与自动日报.md")
WO_ROW_RE = re.compile(r"^\|\s*(及格\(D\)|良好\(C\)|优秀\(B\)|超优\(A\))\s*"
                       r"\|\s*(.+?)\s*\|\s*$")


def _report_lines(out_dir):
    text = open(os.path.join(str(out_dir), "report.txt"),
                encoding="utf-8").read()
    return {letter: next(l for l in text.splitlines()
                         if l.startswith(pipeline.WO_LABEL[letter] + " "))
            for letter in "DCBA"}


def _workorder_rows():
    """从课程仓工单文件按行取验收标准四行原文；项目被单独拷走时跳过。"""
    if not os.path.exists(WORK_ORDER_MD):
        pytest.skip("工单任务书不在仓库相对位置，逐字对表无法执行")
    rows = {}
    for line in open(WORK_ORDER_MD, encoding="utf-8").read().splitlines():
        m = WO_ROW_RE.match(line)
        if m:
            rows[m.group(1)[m.group(1).index("(") + 1]] = m.group(2)
    return rows


def test_wo_row_constant_matches_the_work_order():
    rows = _workorder_rows()
    assert rows == dict(pipeline.WO_ROW), (rows, pipeline.WO_ROW)


def test_report_tier_lines_quote_the_work_order_verbatim(tmp_path):
    pipeline.run(C.load_config(CFG), str(tmp_path))
    rows = _workorder_rows()
    assert sorted(rows) == ["A", "B", "C", "D"], rows
    lines = _report_lines(tmp_path)
    for letter in "DCBA":
        assert lines[letter].startswith("%s %s → " % (pipeline.WO_LABEL[letter],
                                                      rows[letter])), lines[letter]
        assert lines[letter].count(rows[letter]) >= 1


def test_line_values_stay_out_of_the_original_text(tmp_path):
    """行首（箭头之前）必须恰好是「档位标签 + 工单原文」：抬线只能改 rules.yaml，
    预算秒数/断点上限这类 config 值不得混进"原文"里。"""
    pipeline.run(C.load_config(CFG), str(tmp_path))
    lines = _report_lines(tmp_path)
    for letter in "DCBA":
        head = lines[letter].split(" → ")[0]
        assert head == "%s %s" % (pipeline.WO_LABEL[letter],
                                 pipeline.WO_ROW[letter]), head
