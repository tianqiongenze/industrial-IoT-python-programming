# -*- coding: utf-8 -*-
import pytest

from ml_service import core


def test_make_data_shape():
    X, y = core.make_data(200, 1)
    assert X.shape == (200, 5) and len(y) == 200


def test_train_returns_metrics():
    X, y = core.make_data(300, 2)
    m, mt = core.train(X, y)
    assert 0.0 <= mt["macro_f1"] <= 1.0 and mt["n_train"] + mt["n_test"] == 300


def test_gate_true_and_false():
    assert core.gate({"macro_f1": 0.85}, 0.80) is True
    assert core.gate({"macro_f1": 0.70}, 0.80) is False


def test_save_and_load_roundtrip(tmp_path):
    X, y = core.make_data(200, 3)
    m, _ = core.train(X, y)
    p = str(tmp_path / "m.joblib")
    core.save_model(m, p, {})
    assert core.predict_one(core.load_model(p), list(X[0])) in (0, 1)


def test_load_missing_model_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        core.load_model(str(tmp_path / "nope.joblib"))


def test_predict_one_returns_int():
    X, y = core.make_data(200, 3)
    m, _ = core.train(X, y)
    assert isinstance(core.predict_one(m, list(X[0])), int)
