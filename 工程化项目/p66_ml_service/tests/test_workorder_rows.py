# -*- coding: utf-8 -*-
"""工单《P6 故障诊断模型与边缘部署》验收表（及格/良好/优秀/超优）逐档对照取证。

为什么要这一节：课堂阶梯（D 示例跑通 / C F1≥0.80 并保存 / B 对比+调参+联动 /
A 三维评价）与工单四档字母错一档且覆盖面不同——工单及格要的「推理服务可调通」、
优秀要的「服务异常处理(404/参数错)」、超优要的「ONNX导出或版本对比实验」，
在课堂四行里一次都没判过。本节用真实 HTTP 探针 + 服务端逐条延迟记录 +
教师包版本对比把这些补齐，测不到的（P7 立项书、生产 ASGI 中间件）点名不判。
"""
import json
import os
import re

import pytest

from ml_service import config as C
import ml_service.pipeline as P

ROW_PREFIX = {"D": "工单及格(D)", "C": "工单良好(C)",
              "B": "工单优秀(B)", "A": "工单超优(A)"}

# 课程仓的工单原文（项目被单独拷走时不存在，用例自动 skip）
WORK_ORDER_MD = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "..", "..",
    "工单任务书", "P6工单-故障诊断模型与边缘部署.md"))
WO_ROW_RE = re.compile(r"^\|\s*(及格\(D\)|良好\(C\)|优秀\(B\)|超优\(A\))\s*"
                       r"\|\s*(.+?)\s*\|\s*$")

# 工单任务书/P6工单-故障诊断模型与边缘部署.md「## 验收标准」四行原文
WORK_ORDER = {
    "D": "诊断模型F1≥0.80并保存；推理服务可调通",
    "C": "接入数据库联动；延迟记录完整",
    "B": "模型对比+调参记录；服务异常处理(404/参数错)",
    "A": "优秀+ONNX导出或版本对比实验；P7综合项目立项书",
}


def _workorder_rows():
    """从工单文件按行取验收表四行原文——单一真源，不看代码里的副本。"""
    rows = {}
    for line in open(WORK_ORDER_MD, encoding="utf-8").read().splitlines():
        m = WO_ROW_RE.match(line)
        if m:
            rows[m.group(1)[m.group(1).index("(") + 1]] = m.group(2)
    return rows

_CFG = """
features_path: {tmp}/none.npy
labels_path: {tmp}/none.npy
teacher_model: ../../model_v1.joblib
p5_db: {tmp}/none.db
model_name: model_v1.joblib
n_features: 30
n_fallback: 120
seed: 42
test_size: 0.25
cv_folds: 3
min_f1: 0.80
grid_n_estimators: [50]
grid_max_depth: [4]
port: 0
host: "127.0.0.1"
bench_requests: 60
warmup: 2
window_size: 24
teacher_samples: 10
explain_topk: 3
min_latency_records: 50
{probes}
"""


def _write_cfg(tmp_path, overrides=(), probes=""):
    text = _CFG.format(tmp=str(tmp_path), probes=probes)
    for old, new in overrides:
        assert old in text, old
        text = text.replace(old, new)
    path = os.path.join(str(tmp_path), "rules.yaml")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


def _run(tmp_path, name="wo", overrides=(), probes=""):
    out = os.path.join(str(tmp_path), name)
    cfg = C.load_config(_write_cfg(tmp_path, overrides, probes))
    sections = P.run(cfg, out)
    data = json.loads(open(os.path.join(out, "result.json"),
                           encoding="utf-8").read())
    text = open(os.path.join(out, "report.txt"), encoding="utf-8").read()
    return out, data, text, sections


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    return _run(tmp_path_factory.mktemp("wo"))


def _row(text, key):
    lines = [l for l in text.splitlines() if l.startswith(ROW_PREFIX[key])]
    assert len(lines) == 1, (key, lines)
    return lines[0]


# ------------------------------------------------------------------ 四档判定
def test_all_four_workorder_rows_are_adjudicated(built):
    """四档必须各有报告一行 + result.json 一个布尔，出厂口径下实测项全过。"""
    _out, data, text, sections = built
    assert set(data["workorder_tiers"]) == {"A", "B", "C", "D"}
    assert all(data["workorder_tiers"][k] is True for k in "ABCD")
    sec = [k for k in dict(sections) if "工单验收四档对照" in k]
    assert len(sec) == 1, list(sections)
    for k in "DCBA":
        row = _row(text, k)
        assert "本节实测项 通过" in row, row
        assert re.search(r"\d", row), row


def test_rows_quote_the_p6_work_order_verbatim(built):
    """档位口径只能照抄工单原文；代码常量、result.json、报告三处必须同源。"""
    _out, data, text, _ = built
    assert P.WO_ROW == WORK_ORDER
    assert data["workorder_rows"] == dict(WORK_ORDER)
    for k in "DCBA":
        assert "「%s」" % WORK_ORDER[k] in _row(text, k)


def test_constants_match_the_work_order_file_itself():
    """上一用例锁的是"代码↔报告同源"；本用例再锁"代码↔工单文件同源"：
    课程工单改了验收表而代码没跟着改，这里当场判红（工单文件不在相对位置则 skip）。"""
    if not os.path.exists(WORK_ORDER_MD):
        pytest.skip("工单任务书不在仓库内的相对位置（项目被单独拷走时不判）")
    rows = _workorder_rows()
    assert sorted(rows) == ["A", "B", "C", "D"], rows
    assert rows == WORK_ORDER, (rows, WORK_ORDER)


def test_orphaned_work_order_clauses_now_have_evidence(built):
    """工单独有的三条（可调通/404参数错/版本对比）只在对照节取证，课堂四行测不到。"""
    _out, data, text, _ = built
    classroom = [l for l in text.splitlines() if re.match(r"^[DCBA]层 ", l)]
    assert len(classroom) == 4
    joined = "".join(classroom)
    for token in ("404", "可调通", "版本对比"):
        assert token not in joined, token          # 课堂阶梯确实没判过
        assert token in "".join(_row(text, k) for k in "DCBA"), token
    ev = data["workorder_evidence"]
    assert ev["codes_seen"] == [200, 400, 404]     # 三类分支真打过
    assert ev["error_cases_ok"] == 6               # 4 条 400 + 2 条 404
    assert ev["version_compared"] >= 10            # 超优档的版本对比样本量


def test_latency_records_are_two_sided(built):
    """「延迟记录完整」不是口号：客户端发送数=服务端记录数，计时条数达标才算。"""
    _out, data, text, _ = built
    ev, b = data["workorder_evidence"], data["bench"]
    assert b["requests_sent"] == b["server_recorded"] == b["warmup"] + b["n_requests"]
    assert b["client_timed"] == b["n_requests"] == 60
    assert ev["latency_records_match"] is True
    assert ev["latency_client_timed"] >= ev["min_latency_records"]
    assert "服务端 stats 同步记录 %d 条（两边条数相等=True）" % b["server_recorded"] \
        in _row(text, "C")


# ------------------------------------------------------------------ 改配置即可翻档
def test_d_row_fails_when_service_probe_removed(tmp_path):
    """及格档的「推理服务可调通」靠探针取证：探针清单里拿掉两个 200 档就翻红。"""
    _out, data, text, _ = _run(
        tmp_path, "d_probe",
        probes=('error_probes: [predict_non_json, predict_missing_features, '
                'predict_wrong_dim, predict_nan, unknown_get, unknown_post]'))
    assert data["workorder_tiers"]["D"] is False
    assert data["workorder_tiers"]["B"] is True     # 错误分支仍全测到
    assert "/health 与 /predict 均 200" in _row(text, "D")
    assert "本节实测项 有未通过项" in _row(text, "D")


def test_d_row_fails_when_artifact_is_not_a_saved_joblib(tmp_path):
    """只把 model_name 的扩展名改掉：及格档「并保存」的取证即刻不成立。"""
    _out, data, text, _ = _run(tmp_path, "d_name",
                               overrides=[("model_name: model_v1.joblib",
                                           "model_name: model_v1.pkl")])
    assert data["workorder_tiers"]["D"] is False
    assert "model_v1.pkl" in _row(text, "D")


def test_c_row_fails_when_latency_record_floor_raised(tmp_path):
    """良好档只判「记录是否完整」：把下限抬到不可能达到的条数，本档翻红而其他档不动。"""
    _out, data, text, _ = _run(tmp_path, "c_floor",
                               overrides=[("min_latency_records: 50",
                                           "min_latency_records: 5000")])
    assert data["workorder_tiers"]["C"] is False
    assert all(data["workorder_tiers"][k] is True for k in "DBA")
    assert "≥ 阈值 5000" in _row(text, "C")
    assert "本节实测项 有未通过项" in _row(text, "C")


def test_error_probe_list_drives_superior_row_together(tmp_path):
    """优秀档是超优档的前置（工单原文"优秀+…"）：清空错误探针 ⇒ 两档一起翻。"""
    _out, data, text, _ = _run(tmp_path, "b_probe",
                               probes="error_probes: [health_get, predict_ok]")
    assert data["workorder_evidence"]["error_probes"] == 2
    assert data["workorder_tiers"]["B"] is False
    assert data["workorder_tiers"]["A"] is False     # 前置不成立
    assert data["workorder_tiers"]["D"] is True      # 可调通仍成立
    assert "前置优秀档=未通过" in _row(text, "A")
    assert "400/404 类 0/0 条" in _row(text, "B")


def test_workorder_and_classroom_ladders_are_independent(tmp_path):
    """同一份实测两套判定：工单良好翻红时课堂四级仍按自己的口径全绿。"""
    _out, data, _text, _ = _run(tmp_path, "indep",
                               overrides=[("min_latency_records: 50",
                                           "min_latency_records: 5000")])
    assert all(data["tiers"][k] is True for k in "ABCD")
    assert data["workorder_tiers"]["C"] is False


# ------------------------------------------------------------------ 不假判红线
def test_unmeasured_items_are_named_not_judged(built):
    """测不到的子项只能在行内点名；有未测项的行不得写整档"→ 达标"。"""
    _out, data, text, _ = built
    for k in "DCBA":
        row = _row(text, k)
        items = data["workorder_unmeasured"][k]
        assert items, (k, "四档都有跨工程/跨工具的子项，必须逐个点名")
        assert "未实测项：" in row, row
        for it in items:
            assert it in row, (k, it)
        assert "→ 达标" not in row, row
    assert "P7 综合项目立项书" in data["workorder_unmeasured"]["A"][0]


def test_ladder_explains_the_letter_offset(built):
    """报告必须自己说清两套阶梯为何字母不同，避免学生按字母跨表对号入座。"""
    _out, _data, text, _ = built
    line = next(l for l in text.splitlines() if l.startswith("档位口径说明"))
    assert "课堂 C 层≈工单及格" in line
    assert "服务异常处理(404/参数错)" in line


def test_onnx_absence_is_reported_not_faked(built):
    """离线环境没有 skl2onnx：超优档如实报告 ONNX 不可得，改用"或"的另一支取证。"""
    _out, data, text, _ = built
    assert data["onnx"]["available"] is False
    assert "ONNX 导出=不可得" in _row(text, "A")
    assert data["workorder_evidence"]["version_compared"] > 0
    assert "一致 %d 条" % data["workorder_evidence"]["version_agreement"] \
        in _row(text, "A")
