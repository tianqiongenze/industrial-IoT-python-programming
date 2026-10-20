# -*- coding: utf-8 -*-
import numpy as np
import pytest

from feat_factory import core


def test_feats_time_returns_13():
    x = np.arange(20, dtype=float)
    f = core.feats_time(x)
    assert len(f) == 13 and all(isinstance(v, float) for v in f)


def test_feats_freq_returns_4():
    x = np.sin(np.linspace(0, 8, 64))
    f = core.feats_freq(x)
    assert len(f) == 4


def test_make_window_kind():
    a = core.make_window("normal", 32, 1)
    b = core.make_window("abnormal", 32, 1)
    assert a.shape == b.shape == (32,)
    assert b.mean() > a.mean()


def test_feats_empty_raises():
    with pytest.raises(ValueError):
        core.feats_time([])


def test_feature_names_count():
    assert len(core.feature_names()) == 17
