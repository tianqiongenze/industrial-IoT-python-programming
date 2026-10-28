# -*- coding: utf-8 -*-
"""A层·可解释性 Top-k 与训练耗时隔离测试（工单 03-P6：F1+计时+可解释性三维评价）。

覆盖：Top-3 排序正确性（对 |coef_/importances_ 全量降序一致）、并列时
zlib.crc32 稳定定序（禁 PYTHONHASHSEED 随机的内置 hash）、k 超过特征数钳制、
列名契约校验、fit_ms 只进 timing_out 不进评估报告字典。
"""
import json
import zlib

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression

from ml_service import core, data


def _fit_lr(seed=3, n=120):
    X, y = data.make_synthetic(n, seed=seed)
    m = LogisticRegression(max_iter=2000, random_state=seed)
    m.fit(X, y)
    return m


def test_top3_ordered_by_abs_coef():
    """LR 取 coef_：Top-3 必须等于 |coef| 全量降序的前 3 名（排序正确性）。"""
    m = _fit_lr()
    r = core.top_features(m, data.FEATURE_NAMES, k=3)
    assert r["method"].startswith("coef_") and len(r["top"]) == 3
    vals = [t["abs_value"] for t in r["top"]]
    assert vals == sorted(vals, reverse=True)
    truth = sorted(np.abs(m.coef_[0]), reverse=True)[:3]
    assert all(abs(v - round(float(t), 6)) < 1e-9 for v, t in zip(vals, truth))
    names = [t["feature"] for t in r["top"]]
    assert all(nm in data.FEATURE_NAMES for nm in names)          # 列名来自真实契约
    assert [t["rank"] for t in r["top"]] == [1, 2, 3]


def test_top3_trees_use_feature_importances():
    X, y = data.make_synthetic(120, seed=5)
    m = RandomForestClassifier(n_estimators=50, random_state=5).fit(X, y)
    r = core.top_features(m, data.FEATURE_NAMES, k=3)
    assert r["method"] == "feature_importances_"
    vals = [t["abs_value"] for t in r["top"]]
    truth = sorted(np.asarray(m.feature_importances_), reverse=True)[:3]
    assert all(abs(v - round(float(t), 6)) < 1e-9 for v, t in zip(vals, truth))


def test_ties_broken_stably_by_crc32():
    """|值| 并列时按 zlib.crc32(特征名) 定序；重复调用与跨进程（PYTHONHASHSEED
    不同）结果一致——内置 hash() 随机化字符串，这里禁止使用。"""
    class _Fake:
        coef_ = np.array([[0.5, 0.5, -0.5, 0.1]])     # 三名并列 |0.5|
    names = ["delta", "alpha", "charlie", "bravo"]
    expected = sorted(["delta", "alpha", "charlie"],
                      key=lambda n: zlib.crc32(n.encode("utf-8")))
    r1 = core.top_features(_Fake(), names, k=4)
    assert [t["feature"] for t in r1["top"][:3]] == expected
    assert r1["top"][-1]["feature"] == "bravo"        # 非并列者排在并列组之后
    r2 = core.top_features(_Fake(), names, k=3)
    assert [t["feature"] for t in r2["top"]] == expected          # 重复调用一致


def test_k_clamped_to_number_of_features():
    m = _fit_lr()
    r = core.top_features(m, data.FEATURE_NAMES, k=99)            # k > 30 维
    assert r["k"] == 30 and len(r["top"]) == 30
    assert r["top"][-1]["rank"] == 30

    class _Two:
        coef_ = np.array([[0.4, -0.9]])
    r2 = core.top_features(_Two(), ["a", "b"], k=5)               # k 钳到 2 列
    assert r2["k"] == 2 and len(r2["top"]) == 2
    assert r2["top"][0]["feature"] == "b"                         # |−0.9| 更大


def test_name_count_mismatch_raises():
    class _Fake:
        coef_ = np.array([[0.1, 0.2]])
    try:
        core.top_features(_Fake(), data.FEATURE_NAMES, k=3)
        raise AssertionError("列名数与权重数不符必须抛 ValueError")
    except ValueError as exc:
        assert "列序契约" in str(exc)


def test_evaluate_explain_and_timing_isolation():
    """evaluate：四模型都带 Top-k 可解释清单；fit_ms 只进 timing_out，
    绝不出现在评估报告字典（即 result.json 的 evaluate 段）里。"""
    X, y = data.make_synthetic(200, seed=9)
    timing = {}
    _m, ev = core.evaluate(X, y, seed=9, cv_folds=3,
                           grid_n_estimators=[50], grid_max_depth=[4],
                           explain_topk=2, feature_names=data.FEATURE_NAMES,
                           timing_out=timing)
    for name in ("LR", "RF", "GBM", "RF-tuned"):
        ex = ev["comparison"][name]["explain"]
        assert ex["k"] == 2 and len(ex["top"]) == 2
        assert ex["n_features"] == 30
    assert set(timing) == {"LR", "RF", "GBM", "RF-tuned(grid)"}
    assert all(isinstance(v, float) and v > 0 for v in timing.values())
    assert "fit_ms" not in json.dumps(ev, ensure_ascii=False)
    assert ev["explain_topk"] == 2
    assert "FEATURE_NAMES" in ev["explain_feature_source"]
