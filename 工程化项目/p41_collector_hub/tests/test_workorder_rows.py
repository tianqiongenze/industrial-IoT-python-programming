# -*- coding: utf-8 -*-
"""工单 P4 验收表（及格/良好/优秀/超优）逐档取证：每条判定都必须被实测数字支撑。

课堂阶梯（D 跟做保底 / C 基础完成 / B 标准达成 / A 进阶拓展）与工单四档字母不同源，
工单「优秀(B)」在课堂上没有对应行，因此本文件专门证明它在本项目里被真实测到了：
零丢弃链路（重连上限抬到吞得下最严重故障）+ 延迟线 + core.py 无共享可变状态的 AST 扫描。
"""
import json
import os
import re

import pytest

from collector_hub import config as C
from collector_hub import core
from collector_hub import pipeline

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = os.path.join(HERE, "..", "config", "rules.yaml")
SRC = os.path.abspath(CFG).replace(os.path.join("config", "rules.yaml"),
                                   os.path.join("src", "collector_hub", "core.py"))
# 工单原文在项目外三级（课程仓库根/工单任务书/），项目被单独拷走时取不到 → 相关用例 skip
WO_FILE = os.path.abspath(os.path.join(
    HERE, "..", "..", "..", "工单任务书", "P4工单-多源工业数据采集系统.md"))
WO_ROW_RE = re.compile(r"^\|\s*(及格\(D\)|良好\(C\)|优秀\(B\)|超优\(A\))\s*\|\s*(.+?)\s*\|\s*$")


def _run(cfg, out_dir):
    pipeline.run(cfg, str(out_dir))
    data = json.loads(open(os.path.join(str(out_dir), "result.json"),
                           encoding="utf-8").read())
    text = open(os.path.join(str(out_dir), "report.txt"), encoding="utf-8").read()
    return data, text


def _flipped(tmp_path, replaces):
    """只改 rules.yaml 文本（不动一行代码）→ 判定随之翻转。"""
    raw = open(CFG, encoding="utf-8").read()
    for old, new in replaces:
        assert old in raw, old
        raw = raw.replace(old, new)
    path = os.path.join(str(tmp_path), "rules.yaml")
    open(path, "w", encoding="utf-8").write(raw)
    return C.load_config(path)


# ------------------------------------------------------------------ 四档全取证
def test_all_four_workorder_rows_are_adjudicated(tmp_path):
    data, text = _run(C.load_config(CFG), tmp_path)
    assert "[工单验收四档对照（及格/良好/优秀/超优）]" in text
    assert data["workorder_tiers"] == {"D": True, "C": True, "B": True, "A": True}
    for tag in ("工单及格(D)", "工单良好(C)", "工单优秀(B)", "工单超优(A)"):
        line = next(l for l in text.split("\n") if l.startswith(tag))
        assert line.rstrip().endswith("达标"), line
    assert "档位口径说明" in text      # 两套字母不同源这件事必须写在报告里


def _rows_from_workorder():
    """从工单 md 解析 {档位字母: (「及格(D)」整标签, 验收行原文)}。"""
    out = {}
    for line in open(WO_FILE, encoding="utf-8").read().splitlines():
        m = WO_ROW_RE.match(line.strip())
        if m:
            label = m.group(1)
            out[label[label.index("(") + 1]] = (label, m.group(2))
    return out


def test_workorder_rows_are_quoted_verbatim(tmp_path):
    """四行必须逐字复述工单原文：改一个字（哪怕只是加个空格）都会被拦下。"""
    if not os.path.exists(WO_FILE):
        pytest.skip("工单任务书不在仓库内的相对位置（项目被单独拷走时）")
    rows = _rows_from_workorder()
    assert sorted(rows) == ["A", "B", "C", "D"], rows
    _, text = _run(C.load_config(CFG), tmp_path)
    for label, row in rows.values():
        assert "工单%s「%s」" % (label, row) in text, (label, row)


def test_constants_match_the_work_order_file_itself(tmp_path):
    """报告行首只准来自 pipeline.WO_ROW/WO_PREFIX，而这两个常量必须等于工单原文。

    上一测只证明「报告里有这行」；本测证明常量本身没漂移——有人手改 WO_ROW
    （哪怕只是把 ≥99.5% 改成 99.5%）也会在这里被判，而不是靠报告文本蒙过去。
    """
    if not os.path.exists(WO_FILE):
        pytest.skip("工单任务书不在仓库内的相对位置（项目被单独拷走时不判）")
    rows = _rows_from_workorder()
    assert {k: v[1] for k, v in rows.items()} == dict(pipeline.WO_ROW)
    assert {k: "工单" + v[0] for k, v in rows.items()} == dict(pipeline.WO_PREFIX)
    _, text = _run(C.load_config(CFG), tmp_path)
    for letter in "DCBA":
        head = "%s「%s」" % (pipeline.WO_PREFIX[letter], pipeline.WO_ROW[letter])
        line = next(l for l in text.split("\n") if l.startswith(head))
        assert head == line[:len(head)], line


def test_d_row_proves_no_silent_loss(tmp_path):
    """及格(D)「无数据丢失」：靠零丢弃链路实测 成功==计划、丢弃==0，不靠话术。"""
    data, _ = _run(C.load_config(CFG), tmp_path)
    z = data["workorder_evidence"]["zero_link"]
    assert z["drop"] == 0 and z["rate"] == 100.0
    assert z["retry_limit"] >= max(f["fail_attempts"]
                                   for f in data["config_echo"]["faults"].values())
    assert data["apm"]["ok"] + data["apm"]["drop"] == data["planned"]
    assert data["identities"]["ok+drop==planned"] is True


def test_b_row_is_the_tier_the_classroom_ladder_missed(tmp_path):
    """优秀(B)「≥99.5%＋延迟<100ms＋线程安全」三项各自有数，且取最保守的链路。"""
    data, text = _run(C.load_config(CFG), tmp_path)
    ev = data["workorder_evidence"]
    assert ev["zero_link"]["rate"] >= ev["rate_strict_target"] == 99.5
    assert ev["zero_link"]["avg_ms"] < ev["latency_target_ms"] == 100.0
    assert ev["shared_mutable_globals"] == []
    assert ev["zero_link"]["avg_ms"] >= data["apm"]["avg_ms"]   # 保守：取重连最多的那条
    assert "工单优秀(B)" in text and "AST 扫描 core.py 模块级可变全局 0 个" in text


def test_module_mutable_globals_finds_real_shared_state():
    """AST 扫描本身要能抓到东西，否则「无共享可变状态」是空转出来的绿灯。"""
    assert pipeline._module_mutable_globals(SRC) == []
    tmp = os.path.join(os.path.dirname(SRC), "_probe_shared_state.py")
    open(tmp, "w", encoding="utf-8").write(
        "import collections\n"
        "COUNTS = {}\n"
        "NAMES: list = []\n"
        "STAGE = new_stats()\n"
        "LATENCY = 12.0\n"
        "TABLES = (1, 2)\n"
        "def f():\n"
        "    local = {}\n"
        "    return local\n")
    try:
        assert sorted(pipeline._module_mutable_globals(tmp)) == ["COUNTS", "NAMES", "STAGE"]
    finally:
        os.remove(tmp)


def test_docs_min_is_the_evidence_for_the_document_clause(tmp_path):
    data, _ = _run(C.load_config(CFG), tmp_path)
    assert data["workorder_evidence"]["docs_md"] >= 8
    root = os.path.join(os.path.dirname(os.path.abspath(CFG)), "..", "docs")
    names = sorted(f for f in os.listdir(root) if f.endswith(".md"))
    assert len(names) == data["workorder_evidence"]["docs_md"]


# ------------------------------------------------------------------ 只改配置即可翻档
def test_raising_the_pass_line_flips_workorder_d(tmp_path):
    cfg = _flipped(tmp_path, [("rate_pass_line: 95.0", "rate_pass_line: 99.9")])
    data, text = _run(cfg, tmp_path)
    assert data["workorder_tiers"]["D"] is False
    line = next(l for l in text.split("\n") if l.startswith("工单及格(D)"))
    assert "→ 未达标" in line and "97.22%" in line


def test_tightening_latency_or_strict_rate_flips_workorder_b(tmp_path):
    cfg = _flipped(tmp_path, [("latency_target_ms: 100.0", "latency_target_ms: 20.0")])
    data, text = _run(cfg, tmp_path)
    assert data["workorder_tiers"]["B"] is False
    assert "22.28ms/条 ≥ 20.00ms" in text

    cfg2 = _flipped(tmp_path, [("rate_strict_target: 99.5",
                               "rate_strict_target: 100.5")])
    data2, _ = _run(cfg2, tmp_path)
    assert data2["workorder_tiers"]["B"] is False


def test_demanding_one_more_doc_flips_workorder_d(tmp_path):
    cfg = _flipped(tmp_path, [("docs_min: 8", "docs_min: 99")])
    data, text = _run(cfg, tmp_path)
    assert data["workorder_tiers"]["D"] is False
    assert "有效过程文档 8 篇（≥99" in text


def test_workorder_and_classroom_ladders_are_independent_verdicts(tmp_path):
    """两套口径各判各的：把重连上限设成 0，课堂 C/B 与工单 C/D 应随即翻转，工单 B/A 不受累。"""
    cfg = _flipped(tmp_path, [("retry_limit: 3", "retry_limit: 0")])
    data, _ = _run(cfg, tmp_path)
    assert data["tiers"]["C"] is False        # 91.67% < 目标 95%
    assert data["tiers"]["B"] is False        # 没有重连，就没有「断线重连实测」
    assert data["workorder_tiers"]["C"] is False   # 同上（工单良好档也要求重连实测）
    assert data["workorder_tiers"]["D"] is False   # 默认链路 91.67% 过不了工单线 >95%
    assert data["workorder_tiers"]["B"] is True    # B 档取零丢弃链路，与默认配置无关
    assert data["workorder_tiers"]["A"] is True    # 计数自洽与是否重连无关
