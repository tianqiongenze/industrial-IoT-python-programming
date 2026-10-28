# -*- coding: utf-8 -*-
"""数据层与五步流评估测试：真实 features.npy、维度校验、F1 门禁、混淆矩阵。"""
import os

import numpy as np
import pytest

from ml_service import core, data

COURSE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                           "..", "..", ".."))
FEATS = os.path.join(COURSE_ROOT, "features.npy")
LABELS = os.path.join(COURSE_ROOT, "labels.npy")


def test_real_dataset_is_30_dim():
    if not (os.path.exists(FEATS) and os.path.exists(LABELS)):
        pytest.skip("课程根 features.npy 不存在（场景：单项目检出）")
    X, y, names, note = data.load_dataset(FEATS, LABELS)
    assert X.shape == (200, 30)
    assert len(y) == 200 and set(np.unique(y)) == {0, 1}
    assert names == data.FEATURE_NAMES and len(names) == 30
    assert "真实数据" in note


def test_fallback_is_seeded_and_deterministic(tmp_path):
    X1, y1, _, note1 = data.load_dataset(str(tmp_path / "no1.npy"),
                                         str(tmp_path / "no2.npy"), seed=7)
    X2, y2, _, note2 = data.load_dataset(str(tmp_path / "no1.npy"),
                                         str(tmp_path / "no2.npy"), seed=7)
    assert np.array_equal(X1, X2) and np.array_equal(y1, y2)
    assert "合成替代源" in note1
    assert X1.shape[1] == 30


def test_validate_feature_names_contract():
    assert data.validate_feature_names(data.FEATURE_NAMES) == data.FEATURE_NAMES
    with pytest.raises(ValueError):
        data.validate_feature_names(["a"] * 29)       # 维数不符
    with pytest.raises(ValueError):
        data.validate_feature_names(["x"] * 30)       # 重复列名


@pytest.fixture(scope="module")
def trained():
    X, y = data.make_synthetic(300, seed=11)
    model, ev = core.evaluate(X, y, seed=11)
    return model, ev, X, y


def test_gate_f1_reaches_threshold(trained):
    """D层底线+C层验收：真实评估数字过 F1≥0.80 门禁（硬断言，非伪造）。"""
    _model, ev, _X, _y = trained
    assert ev["test_macro_f1"] >= 0.80
    assert core.gate(ev["test_macro_f1"], 0.80) is True
    assert core.gate(0.70, 0.80) is False


def test_evaluation_artifacts_complete(trained):
    _model, ev, _X, _y = trained
    assert {"LR", "RF", "GBM", "RF-tuned"} <= set(ev["comparison"])
    for name, c in ev["comparison"].items():
        assert 0.0 <= c["cv_mean"] <= 1.0 and c["cv_std"] >= 0.0
        assert 0.0 <= c["test_macro_f1"] <= 1.0
        assert 0.0 <= c["precision_wear"] <= 1.0 and 0.0 <= c["recall_wear"] <= 1.0
    cm = ev["confusion_matrix"]
    assert sum(sum(row) for row in cm) == ev["n_test"]
    assert ev["grid_search"]["best_params"]           # 调参留痕非空
    assert len(ev["grid_search"]["top5_mean_test"]) == 5
    assert ev["classification_report_text"].count("磨损") >= 1


def test_evaluate_on_real_data_passes_gate():
    if not os.path.exists(FEATS):
        pytest.skip("features.npy 不在课程根")
    X, y, _names, _note = data.load_dataset(FEATS, LABELS)
    _model, ev = core.evaluate(X, y, seed=42)
    assert ev["test_macro_f1"] >= 0.80


def test_predict_row_dimension_guard(trained):
    model, _ev, X, _y = trained
    pred, proba = core.predict_row(model, X[0], 30)
    assert pred in (0, 1) and 0.0 <= proba <= 1.0
    with pytest.raises(ValueError):
        core.predict_row(model, list(X[0])[:29], 30)  # 维度不符
    with pytest.raises(ValueError):
        bad = list(X[0])
        bad[3] = float("nan")
        core.predict_row(model, bad, 30)


def test_save_and_manifest_roundtrip(tmp_path, trained):
    model, ev, X, _y = trained
    manifest = {"model_name": "model_v1.joblib", "feature_names": data.FEATURE_NAMES,
                "n_features": 30}
    path = str(tmp_path / "model_v1.joblib")
    core.save_model(model, path, manifest)
    loaded = core.load_model(path)
    pred, _ = core.predict_row(loaded, X[0], 30)
    assert pred in (0, 1)
    with pytest.raises(FileNotFoundError):
        core.load_model(str(tmp_path / "nope.joblib"))
    with pytest.raises(ValueError):                    # 列序契约违例即拒存
        core.save_model(model, str(tmp_path / "m2.joblib"),
                        {"model_name": "m2", "feature_names": ["a"] * 29,
                         "n_features": 29})
