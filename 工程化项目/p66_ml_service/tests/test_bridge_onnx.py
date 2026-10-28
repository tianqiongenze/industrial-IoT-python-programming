# -*- coding: utf-8 -*-
"""B层 P5 联动回写 + A层 ONNX 探测测试。"""
import os
import sqlite3

import pytest

from ml_service import bridge, data


@pytest.fixture(scope="module")
def model():
    from ml_service import core
    X, y = data.make_synthetic(200, seed=9)
    m, _ev = core.evaluate(X, y, seed=9)
    return m


def test_features_from_window_shape_and_order():
    vals = [3.2, 3.5, 4.1, 2.9, 3.8, 4.4, 3.0, 3.6] * 4
    feats = bridge.features_from_window(vals, fs=1.0)
    assert len(feats) == data.N_DIM
    assert all(isinstance(v, float) for v in feats)
    # 同一输入两次输出一致（确定性）
    assert feats == bridge.features_from_window(vals, fs=1.0)


def test_run_link_with_stand_in_db(model, tmp_path):
    out_copy = str(tmp_path / "warehouse_diagnosis.db")
    res = bridge.run_link(model, str(tmp_path / "absent-p5.db"), out_copy,
                          window=32, seed=7)
    assert "替代库" in res["origin"]
    assert res["diagnosed_records"] == len(res["devices"])
    assert res["devices"] and all(d["prediction"] in (0, 1) for d in res["devices"])
    assert res["feature_order_check"]["aligned"] is True
    con = sqlite3.connect(out_copy)
    try:
        rows = con.execute("SELECT id, diagnosis, diagnosis_proba, diagnosis_note "
                           "FROM records WHERE diagnosis IS NOT NULL").fetchall()
        assert rows and all(r[3] == "P6联动回写" for r in rows)
    finally:
        con.close()


def test_run_link_with_real_p5_db(model, tmp_path):
    real = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..",
                                        "p55_warehouse_orm", "output", "warehouse.db"))
    if not os.path.exists(real):
        pytest.skip("P5 项目尚未产出 warehouse.db（先跑 ../p55_warehouse_orm/run.py）")
    res = bridge.run_link(model, real, str(tmp_path / "diag.db"), window=32, seed=7)
    assert "P5 真实仓库" in res["origin"]
    assert res["diagnosed_records"] >= 3       # 至少 3 台设备各回写一条新记录


def test_onnx_export_probe_reports_truthfully(model, tmp_path):
    from ml_service import onnx_export
    import numpy as np
    res = onnx_export.export_and_compare(model, str(tmp_path / "m.onnx"),
                                         np.zeros((4, 30)))
    assert "available" in res
    if not res["available"]:
        assert "skl2onnx" in res["reason"]      # 离线环境：如实报告，不伪造数字
        assert not os.path.exists(str(tmp_path / "m.onnx"))
