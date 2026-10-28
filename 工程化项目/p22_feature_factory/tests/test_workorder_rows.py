# -*- coding: utf-8 -*-
"""工单《P2.2 特征工程工厂》验收表（及格/良好/优秀/超优）逐档对照取证。

为什么要这一节：课堂阶梯（D 跟做保底 / C 基础完成 / B 标准达成 / A 进阶拓展）与
工单四档字母**错一档**——课堂 TIER_REQ["B"] 用的是「<100ms」，而那正是工单
良好(C) 的线；工单优秀(B)「<50ms；广播…；箱线图；文档完整」里的 50ms 在课堂
四行里一处都没出现，即"跑得比良好线还快一倍"这件事从来没有被判定过。
本节用同一条流水线的实测把工单四档逐条判掉，测不到的子项一律点名，不假判。
"""
import json
import os
import re

import pytest

from feat_factory import config as C
from feat_factory import pipeline as P

CFG_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "rules.yaml")
DOCS_DIR = os.path.join(os.path.dirname(__file__), "..", "docs")
# 课程仓的工单原文（项目被单独拷走时不存在，用例自动 skip）
WORK_ORDER_MD = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "..", "..",
    "工单任务书", "P2.2工单-NumPy故障特征提取系统.md"))
WO_ROW_RE = re.compile(r"^\|\s*(及格\(D\)|良好\(C\)|优秀\(B\)|超优\(A\))\s*"
                       r"\|\s*(.+?)\s*\|\s*$")
ROW_PREFIX = {"D": "工单及格(D)", "C": "工单良好(C)",
              "B": "工单优秀(B)", "A": "工单超优(A)"}


def _workorder_rows():
    """从工单文件按行取验收表四行原文——单一真源，不看代码里的副本。"""
    rows = {}
    for line in open(WORK_ORDER_MD, encoding="utf-8").read().splitlines():
        m = WO_ROW_RE.match(line)
        if m:
            rows[m.group(1)[m.group(1).index("(") + 1]] = m.group(2)
    return rows


def _write_cfg(tmp_path, overrides=()):
    text = open(CFG_PATH, encoding="utf-8").read()
    timing = os.path.join(str(tmp_path), "runtime", "timing.json").replace("\\", "/")
    text = text.replace('"../runtime/timing.json"', '"%s"' % timing)
    for old, new in overrides:
        assert old in text, old
        text = text.replace(old, new)
    path = os.path.join(str(tmp_path), "rules.yaml")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


def _run(tmp_path, overrides=(), name="wo"):
    out = os.path.join(str(tmp_path), name)
    cfg = C.load_config(_write_cfg(tmp_path, overrides))
    res = P.run(cfg, out_dir=out)
    data = json.loads(open(os.path.join(out, "result.json"),
                           encoding="utf-8").read())
    return out, data, res["text"]


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    return _run(tmp_path_factory.mktemp("wo"))


def _row(text, key):
    lines = [l for l in text.splitlines() if l.startswith(ROW_PREFIX[key])]
    assert len(lines) == 1, (key, lines)
    return lines[0]


# ------------------------------------------------------------------ 四档判定
def test_all_four_workorder_rows_are_adjudicated(built):
    """四档都必须在报告里有一行、在 result.json 里有一个布尔，且出厂配置下全过。"""
    _out, data, text = built
    assert set(data["workorder_tiers"]) == {"A", "B", "C", "D"}
    assert all(data["workorder_tiers"][k] is True for k in "ABCD")
    for k in "DCBA":
        row = _row(text, k)
        assert ("→ 达标" in row or "本节实测项 通过" in row), row
        assert any(ch.isdigit() for ch in row), row          # 每行都带实测数字


def test_rows_quote_the_work_order_verbatim(built):
    """档位口径只能照抄工单原文，代码与报告两处必须是同一个字符串常量。"""
    _out, data, text = built
    assert data["workorder_rows"] == dict(P.WO_ROW)
    assert P.WO_ROW["D"] == "30特征计算正确；向量化为主；标准化正确；PEP 8≥75%"
    assert P.WO_ROW["C"] == "1000样本<100ms；特征字典含物理含义"
    assert P.WO_ROW["B"] == "<50ms；广播运用充分；箱线图输出；文档完整"
    assert P.WO_ROW["A"] == "优秀+衍生特征5个+相关性特征选择(去冗余)"
    for k in "DCBA":
        assert "「%s」" % P.WO_ROW[k] in _row(text, k)


def test_constants_match_the_work_order_file_itself():
    """上一用例锁的是"代码↔报告同源"；本用例再锁"代码↔工单文件同源"：
    课程工单改了验收表而代码没跟着改，这里当场判红（工单文件不在相对位置则 skip）。"""
    if not os.path.exists(WORK_ORDER_MD):
        pytest.skip("工单任务书不在仓库内的相对位置（项目被单独拷走时不判）")
    rows = _workorder_rows()
    assert sorted(rows) == ["A", "B", "C", "D"], rows
    assert rows == dict(P.WO_ROW), (rows, P.WO_ROW)


def test_b_row_is_the_tier_the_classroom_ladder_never_measured(built):
    """工单优秀(B) 的 50ms 线在课堂四行原文里一次都没出现 ⇒ 本节是它的唯一取证处。"""
    _out, _data, text = built
    ladder = " ".join(P.TIER_REQ[k] for k in "DCBA")
    assert "50ms" not in ladder
    assert "50ms" in P.WO_ROW["B"]
    assert P.TIER_REQ["B"] == "<100ms+特征字典含物理含义"    # 课堂 B 层 = 工单良好(C)
    assert "≤ B 档线 50 ms" in _row(text, "B")


def test_workorder_and_classroom_ladders_are_independent_verdicts(built):
    """同一份实测：课堂阶梯判它的四行，工单阶梯判它的四档，二者不互相顶替。"""
    _out, data, _text = built
    assert data["tiers"] == data["workorder_tiers"]          # 出厂配置下巧合全过


# ------------------------------------------------------------------ 改配置即可翻档
def test_only_excellent_ms_change_fails_workorder_b_not_classroom_b(tmp_path):
    """只把 perf.excellent_ms 压到 0.001ms：课堂 B 层仍达标，工单优秀(B) 立刻未通过。"""
    _out, data, text = _run(tmp_path, [("excellent_ms: 50.0",
                                        "excellent_ms: 0.001")], name="exc")
    assert data["workorder_tiers"]["B"] is False
    assert data["tiers"]["B"] is True                        # 课堂线仍是 100ms
    assert "四级全达标" in data["grade"]
    assert "＞ B 档线 0.001 ms" in _row(text, "B")
    assert "≤ C 档线 100 ms" in _row(text, "C")              # 良好档不受影响


def test_superior_row_inherits_the_excellent_prefix(tmp_path):
    """工单超优行原文是"优秀+…"：压掉优秀档的 50ms 线，超优档随之翻，课堂 A 层不动。"""
    _out, data, text = _run(tmp_path, [("excellent_ms: 50.0",
                                        "excellent_ms: 0.001")], name="exc2")
    assert data["workorder_tiers"]["A"] is False             # 前置不成立
    assert data["tiers"]["A"] is True                        # 课堂 A 层不看 50ms
    assert data["workorder_tiers"]["D"] is True              # 及格档与耗时无关
    row = _row(text, "A")
    assert "前置优秀档=未达标" in row and "本节实测项 未通过" in row


def test_strict_identity_pairs_survive_any_threshold(tmp_path):
    """阈值抬到 0.9999 也还剩恒等对可剔 ⇒ 超优档仍成立，但行内数字必须与 JSON 同源。"""
    _out, data, text = _run(tmp_path, [("corr_threshold: 0.95",
                                        "corr_threshold: 0.9999")], name="hi")
    dropped = data["redundancy"]["dropped"]
    assert dropped, "恒等式对（|r|=1）在任何阈值下都应至少留一对可剔"
    assert all(round(d["abs_r"], 6) == 1.0 for d in dropped)  # 只剩严格恒等对
    assert len(dropped) < 11                                  # 比出厂阈值剔得少
    assert data["workorder_tiers"]["A"] is True
    row = _row(text, "A")
    assert "保留 %d + 剔除 %d = 主特征 %d" % (
        len(data["redundancy"]["kept"]), len(dropped),
        data["features"]["primary"]) in row


def test_ast_gate_off_fails_workorder_d_while_good_c_still_passes(tmp_path):
    """关掉 AST 向量化闸门：工单及格(D) 的"向量化为主"失去证据，但良好(C) 两项照测。"""
    _out, data, text = _run(tmp_path, [("enabled: true", "enabled: false")],
                            name="noast")
    assert data["workorder_tiers"]["D"] is False
    assert data["workorder_tiers"]["C"] is True
    assert data["tiers"]["D"] is True                        # 课堂 D 层不依赖该闸门
    row = _row(text, "D")
    assert "本节实测项 未通过" in row
    assert "向量化 AST 扫描" in row


# ------------------------------------------------------------------ 证据与红线
def test_docs_clause_counts_the_real_files_on_disk(built):
    """工单优秀(B) 的"文档完整"用 docs/ 的 .md 实数取证，报告与磁盘必须同一个数。"""
    _out, data, text = built
    real = len([f for f in os.listdir(DOCS_DIR) if f.endswith(".md")])
    assert data["workorder_evidence"]["docs_md"] == real >= 8
    assert "docs/ 过程文档 %d 篇" % real in _row(text, "B")


def test_unmeasured_items_are_named_never_judged(built):
    """测不到的子项只能在行内点名，并且不得让该行冒充"达标"——防止假判。"""
    _out, data, text = built
    for k in "DCBA":
        row = _row(text, k)
        items = data["workorder_unmeasured"][k]
        if not items:
            assert "未实测项" not in row, row
            assert row.rstrip().endswith("→ 达标"), row
            continue
        assert "未实测项：" in row, row
        for it in items:
            assert it in row, (k, it)
        assert "→ 达标" not in row, row                      # 有未测项就不给整档达标
    assert "标准化" in data["workorder_unmeasured"]["D"][0]
    assert "广播" in data["workorder_unmeasured"]["B"][0]


def test_workorder_rows_leak_no_wallclock(built):
    """四档行里出现的 ms 数字只能是配置阈值本身（100/50），不许是实测值。"""
    _out, data, text = built
    allowed = {"%g" % data["perf"]["target_ms"],
               "%g" % data["perf"]["excellent_ms"]}
    rows = "".join(_row(text, k) for k in "DCBA")
    assert set(re.findall(r"(\d+(?:\.\d+)?)\s*ms", rows)) <= allowed
    assert not re.search(r"\d+\.\d+\s*ms", rows)


def test_ladder_explains_the_letter_offset(built):
    """报告必须自己说清两套阶梯为什么字母不同，避免学生按字母跨表对号入座。"""
    _out, _data, text = built
    line = next(l for l in text.splitlines() if l.startswith("档位口径说明"))
    assert "课堂 C 层≈工单及格" in line and "工单优秀档只在本节取证" in line
