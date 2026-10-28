# -*- coding: utf-8 -*-
"""C 层向量化闸门：用 AST 证明「以向量化为主，无逐样本 for 循环」这句口径。

教师版 W04 数的是字节码：

    loops = [nm for nm in TIME15 if any(op.opname == "FOR_ITER"
                                        for op in dis.get_instructions(FEATURES[nm][0]))]
    assert not loops, loops

本文件是同一件事的工程化版本（`vector_check` 走 AST，覆盖 for / while / 推导式），
并额外证明三件事，否则闸门就是空转：
  1. 扫描面真的覆盖到每个特征函数（漏扫 = 假绿）；
  2. 注入一段朴素逐样本写法，检查必须报警并**点名特征名**；
  3. 与 `dis` 的 FOR_ITER 计数逐函数相等（AST 口径 = 字节码口径）。
"""
import dis
import os

import pytest

from feat_factory import config as C
from feat_factory import core
from feat_factory import vector_check as V

CFG_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "rules.yaml")


@pytest.fixture(scope="module")
def scan():
    return V.scan(C.load_config(CFG_PATH))


# ------------------------------------------------------------------ 真实源码
def test_real_feature_functions_have_zero_per_sample_loops(scan):
    """12 个特征函数的逐样本 for/while/推导式必须为 0 处（C 层硬条件）。"""
    assert scan["enabled"] is True
    assert scan["violations"] == [], V.detail_lines(scan)
    assert scan["n_forbidden"] == 0
    assert scan["ok"] is True and scan["status"] == "pass"


def test_scan_face_covers_every_feature_producing_function(scan):
    """扫描面覆盖 Ctx 底座 + 谱工具 + 三个特征块 + 拼装 + 三个 extract 入口。"""
    expected = {"core.Ctx.__init__", "core.spectrum", "core._top3",
                "core.Ctx.amp_at", "core.Ctx.band_power", "core._time_feats",
                "core._freq_feats", "core._stat_feats", "core._stack",
                "core.extract_primary", "core.extract_derived", "core.extract"}
    assert set(scan["targets"]) == expected
    assert set(scan["scanned"]) == expected               # 名单里的都在源码里
    assert scan["missing_targets"] == []


def test_every_primary_feature_is_owned_by_a_scanned_function(scan):
    """每个主特征都归在某个被扫描的函数名下——否则违规时无从点名。"""
    covered = set()
    for dotted in scan["scanned"]:
        covered |= set(V.FUNC_FEATS.get(".".join(dotted.split(".")[1:]), []))
    assert set(core.PRIMARY_FEATS) <= covered
    assert set(core.DERIVED_FEATS) <= covered
    assert len(covered) == 35


def test_allowed_loops_iterate_the_feature_registry_not_samples(scan):
    """只允许"迭代特征名注册表"的循环，且必须逐条列出（次数=特征数，与样本量无关）。"""
    assert scan["n_registry"] == 2
    got = {(r["func"], r["kind"], r["iterable"]) for r in scan["registry_loops"]}
    assert got == {("core._stack", "for", "enumerate(cols)"),
                   ("core.extract_derived", "comprehension",
                    "enumerate(PRIMARY_FEATS)")}
    assert all(r["hits"] for r in scan["registry_loops"])  # 都命中了注册表名单


def test_ast_count_equals_dis_for_iter_count(scan):
    """AST 口径与教师版的字节码口径（dis 数 FOR_ITER）逐函数相等。"""
    per_func = {}
    for r in scan["registry_loops"] + scan["violations"]:
        per_func[r["func"]] = per_func.get(r["func"], 0) + 1
    for dotted in scan["targets"]:
        obj = core
        for part in dotted.split(".")[1:]:
            obj = getattr(obj, part)
        n_dis = sum(1 for op in dis.get_instructions(obj)
                    if op.opname == "FOR_ITER")
        assert n_dis == per_func.get(dotted, 0), dotted


# ------------------------------------------------------------------ 反证：闸门不空转
NAIVE = '''
def _time_feats(c):
    out = []
    for row in c.x:                      # 逐样本第 1 宗：for 迭代样本轴
        out.append(row.std())
    return out


def _stat_feats(c):
    return [float(r.mean()) for r in X]  # 逐样本第 2 宗：推导式迭代样本轴


def _freq_feats(c):
    i = 0
    while i < len(x):                    # 逐样本第 3 宗：while 计数器
        i += 1
    return []


def _stack(cols, k):
    M = []
    for j, v in enumerate(cols):         # 注册表级循环：允许
        M.append(v)
    return M
'''

TARGETS = ["core._time_feats", "core._stat_feats", "core._freq_feats",
           "core._stack"]


def test_injected_per_sample_loops_are_flagged_loudly():
    """把朴素逐样本写法喂给检查器：三处必须全被抓，且失败信息点名特征名。"""
    res = V.scan_text(NAIVE, TARGETS)
    assert res["ok"] is False and res["status"] == "violation"
    assert res["n_forbidden"] == 3 and res["n_registry"] == 1
    kinds = {v["func"]: v["kind"] for v in res["violations"]}
    assert kinds == {"core._time_feats": "for", "core._stat_feats":
                     "comprehension", "core._freq_feats": "while"}
    lines = V.detail_lines(res)
    text = "\n".join(lines)
    assert "mean" in text and "kurtosis" in text          # 时域 10 被点名
    assert "skewness" in text and "entropy" in text       # 统计 5 被点名
    assert "dom_freq" in text and "energy_ratio_high" in text   # 频域 15 被点名
    # 失败信息本体必须逐个点到 30 个特征名（不能用 pytest 改写后的 str：它会截断）
    for name in core.TIME_FEATS + core.STAT_FEATS + core.FREQ_FEATS:
        assert name in text, name
    # 闸门确实会拦：违规清单非空时这条断言必须炸
    assert lines, "违规点名清单不能为空"
    with pytest.raises(AssertionError):
        assert not res["violations"], lines


def test_unregistered_iterable_is_also_a_violation():
    """来路不明的迭代对象一律按违规处理（要放行得写进 config 的注册表名单）。"""
    src = "def _time_feats(c):\n    return [f(v) for v in something_else]\n"
    res = V.scan_text(src, ["core._time_feats"])
    assert res["n_forbidden"] == 1
    assert res["violations"][0]["reason"].startswith("迭代对象不在特征名注册表内")


def test_registry_allow_list_is_the_only_way_to_pass():
    """注册表名单是配置项：加进去就放行，拿掉就违规（改配置不改代码）。"""
    src = "def _stack(cols, k):\n    return [v for v in cols]\n"
    default = V.scan_text(src, ["core._stack"])
    assert default["ok"] is True and default["n_registry"] == 1
    strict = V.scan_text(src, ["core._stack"],
                         registry=["PRIMARY_FEATS", "names"])
    assert strict["ok"] is False and strict["n_forbidden"] == 1


def test_missing_target_is_reported_as_drift_not_pass():
    """config 里点名的函数在源码中不存在 ⇒ 判"配置与代码漂移"，不能算达标。"""
    res = V.scan_text("def a():\n    return 1\n", ["core._time_feats"])
    assert res["missing_targets"] == ["core._time_feats"]
    assert res["ok"] is False and res["status"] == "config_drift"
    assert "闸门不能空转" in V.detail_lines(res)[0]


# ------------------------------------------------------------------ 配置开关
def test_turning_the_gate_off_by_config_leaves_c_layer_unmet():
    """vectorization.enabled=false ⇒ 无证据可引，C 层直接判未达标（不是"跳过即通过"）。"""
    st = C.Settings.from_dict({"vectorization": {"enabled": False}})
    res = V.scan(st)
    assert res["enabled"] is False and res["ok"] is False
    assert res["status"] == "disabled"
    assert "已关闭" in V.summary_text(res)


def test_dropping_a_registry_name_from_config_flips_the_verdict():
    """把 cols 从注册表名单里拿掉：_stack 即被判逐样本循环，扫描结论翻成未达标。"""
    registry = list(C.DEFAULTS["vectorization"]["registry_names"])
    registry.remove("cols")
    st = C.Settings.from_dict({"vectorization": {"registry_names": registry}})
    res = V.scan(st)
    assert res["ok"] is False and res["n_forbidden"] == 1
    assert res["violations"][0]["func"] == "core._stack"
    assert "→ 未达标" in V.summary_text(res)
