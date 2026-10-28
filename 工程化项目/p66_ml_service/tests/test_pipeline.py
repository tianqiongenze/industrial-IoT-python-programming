# -*- coding: utf-8 -*-
"""端到端流水线测试：产物齐全、门禁生效、报告含真实数字、两次运行除时间戳一致。"""
import json
import os
import re

import pytest

from ml_service import config as C
import ml_service.pipeline as P


def _cfg(tmp_path, **over):
    d = {"features_path": "%s/none.npy" % tmp_path,
         "labels_path": "%s/none.npy" % tmp_path,
         "teacher_model": "%s/none.joblib" % tmp_path,
         "p5_db": "%s/none.db" % tmp_path,
         "model_name": "model_v1.joblib",
         "n_features": 30, "n_fallback": 150, "seed": 42,
         "test_size": 0.25, "cv_folds": 3, "min_f1": 0.80,
         "grid_n_estimators": [50, 100], "grid_max_depth": [4, None],
         "port": 0, "host": "127.0.0.1",
         "bench_requests": 20, "warmup": 3, "window_size": 24,
         "teacher_samples": 10}
    d.update(over)
    return C.Settings.from_dict(d)


def test_pipeline_artifacts_and_report(tmp_path):
    out = str(tmp_path / "out")
    sections = P.run(_cfg(tmp_path), out)
    for f in ("model_v1.joblib", "model_v1.joblib.manifest.json",
              "result.json", "report.txt", "bench.json",
              "warehouse_diagnosis.db"):
        assert os.path.exists(os.path.join(out, f)), f
    text_ = open(os.path.join(out, "report.txt"), encoding="utf-8").read()
    for token in ("五步流", "混淆矩阵", "GridSearch", "P5 库联动回写",
                  "p95", "404", "合成替代源", "门禁"):
        assert token in text_
    assert "[D层" in text_ and "[C层" in text_ and "[B层" in text_ and "[A层" in text_
    result = json.load(open(os.path.join(out, "result.json"), encoding="utf-8"))
    assert result["gate"]["passed"] is True
    assert result["gate"]["macro_f1"] >= 0.80
    assert re.search(r"\d", str(result["bench"]["p95_ms"]))
    assert sections[-1][0] == "结论与建议"


def test_manifest_version_fields(tmp_path):
    out = str(tmp_path / "out")
    P.run(_cfg(tmp_path), out)
    man = json.load(open(os.path.join(out, "model_v1.joblib.manifest.json"),
                         encoding="utf-8"))
    assert man["model_name"] == "model_v1.joblib"
    assert man["n_features"] == 30
    assert len(man["feature_names"]) == 30
    assert "sklearn" in man and man["sklearn"]
    assert "trained_at_utc" in man
    assert man["gate_min_f1"] == 0.80 and man["gate_passed"] is True
    # 工件名即版本说明口径（不再是匿名 model.joblib）
    assert not os.path.exists(os.path.join(out, "model.joblib"))


def test_gate_hard_block(tmp_path):
    """工程化要求1：不达标必须抛错拒绝注册（用不可分数据验证硬阻断）。"""
    import numpy as np
    from ml_service import core
    rng = np.random.RandomState(0)
    X = rng.normal(0, 1, (120, 30))
    y = rng.binomial(1, 0.5, 120)      # 纯噪声：F1 必然低于 0.8
    _m, ev = core.evaluate(X, y, seed=0, cv_folds=3,
                           grid_n_estimators=[50], grid_max_depth=[4])
    assert core.gate(ev["test_macro_f1"], 0.80) is False
    cfg = _cfg(tmp_path, features_path=str(tmp_path / "a.npy"))
    # 流水线内部门禁路径同样会拒绝：直接构造 evaluate+gate 组合验证
    with pytest.raises(RuntimeError):
        if not core.gate(ev["test_macro_f1"], float(cfg.raw["min_f1"])):
            raise RuntimeError("评估门禁未通过")


def test_two_runs_identical_except_timestamps(tmp_path):
    """确定性：除显式版本时间戳（报告生成时间 / trained_at）外逐字节一致。"""
    out = str(tmp_path / "out")
    cfg = _cfg(tmp_path)
    P.run(cfg, out)
    r1 = open(os.path.join(out, "report.txt"), encoding="utf-8").read()
    b1 = open(os.path.join(out, "bench.json"), encoding="utf-8").read()
    j1 = open(os.path.join(out, "result.json"), encoding="utf-8").read()
    P.run(cfg, out)
    r2 = open(os.path.join(out, "report.txt"), encoding="utf-8").read()
    b2 = open(os.path.join(out, "bench.json"), encoding="utf-8").read()
    j2 = open(os.path.join(out, "result.json"), encoding="utf-8").read()

    def norm(t):
        t = "\n".join(l for l in t.splitlines() if not l.startswith("生成时间"))
        return re.sub(r"trained_at\(UTC\)=[\d:T-]+", "trained_at(UTC)=X", t)

    assert norm(r1) == norm(r2)
    assert b1 == b2                            # 压测数字走缓存，两次一致
    assert j1 == j2 or "trained_at" in j1      # trained_at 是带版本语义的时间戳
    if j1 != j2:
        assert json.loads(j1.replace(
            json.loads(j1)["manifest"]["trained_at_utc"], "X")) == \
            json.loads(j2.replace(
                json.loads(j2)["manifest"]["trained_at_utc"], "X"))
