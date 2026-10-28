# -*- coding: utf-8 -*-
"""特征层测试：30 主特征（时域10 + 频域15 + 统计5）+ 5 衍生、信号合成、异常路径。

口径来源：工单 P2.2《NumPy特征工程：30维故障特征提取》特征清单
（时域10个 / 频域15个 / 统计5个；超优 A 层另加衍生特征 5 个）。
"""
import numpy as np
import pytest

from feat_factory import core


def _signals(n=16, length=128, seed=11):
    X, _ = core.make_signals(n=n, length=length, seed=seed)
    return X


def test_time_block_has_10_float_columns():
    """时域 10 列：全列式向量化后每列是长度 N 的 float 向量（工单「时域10个」）。"""
    X = _signals(n=24)
    F = core.extract_primary(X, fs=100.0)
    block = F[:, : len(core.TIME_FEATS)]
    assert len(core.TIME_FEATS) == 10
    assert block.shape == (24, 10)
    assert block.dtype == np.float64
    assert all(col.shape == (24,) and col.dtype == np.float64
               for col in F[:, :10].T)
    assert np.isfinite(block).all()


def test_freq_block_has_15_float_columns():
    """频域 15 列：紧接时域之后，全部来自同一次 FFT（工单「频域15个」）。"""
    X = _signals(n=24)
    F = core.extract_primary(X, fs=100.0)
    lo = len(core.TIME_FEATS)
    block = F[:, lo:lo + len(core.FREQ_FEATS)]
    assert len(core.FREQ_FEATS) == 15
    assert block.shape == (24, 15)
    assert block.dtype == np.float64
    assert np.isfinite(block).all()
    # 频率类列必须落在 [0, fs/2]（奈奎斯特）内，证明用的是单边谱
    for name in ("dom_freq", "peak2_freq", "peak3_freq", "spec_centroid"):
        col = F[:, core.PRIMARY_FEATS.index(name)]
        assert ((col >= 0.0) & (col <= 50.0)).all()


def test_make_signals_two_classes():
    """合成器一次给出两类窗口：形状一致、标签 0/1，磨损类在频域指纹上更强。"""
    n, length = 200, 256
    X, y = core.make_signals(n=n, length=length, fs=100.0, seed=42,
                             fault_ratio=0.5)
    assert X.shape == (n, length) and y.shape == (n,)
    assert sorted(set(y.tolist())) == [0, 1]
    assert int(y.sum()) == n // 2                       # 后半是磨损类
    F = core.extract_primary(X, fs=100.0)
    a16 = F[:, core.PRIMARY_FEATS.index("a16")]
    kurt = F[:, core.PRIMARY_FEATS.index("kurtosis")]
    assert a16[y == 1].mean() > a16[y == 0].mean()      # 二倍频指纹（US-02）
    assert kurt[y == 1].mean() > kurt[y == 0].mean()    # 峭度哨兵（B05）
    assert kurt[y == 0].mean() < 4.0                    # 正常类无冲击成分
    # 功率守恒口径：均值/均方根不是判别捷径，两类几乎同量级
    mean = F[:, core.PRIMARY_FEATS.index("mean")]
    assert abs(mean[y == 1].mean() - mean[y == 0].mean()) < 0.05
    rms = F[:, core.PRIMARY_FEATS.index("rms")]
    assert abs(rms[y == 1].mean() - rms[y == 0].mean()) < 0.05
    # 同种子必得同一矩阵（随机种子固定是工程军规）
    again, _ = core.make_signals(n=n, length=length, fs=100.0, seed=42,
                                 fault_ratio=0.5)
    assert np.array_equal(X, again)


def test_extract_rejects_bad_input():
    """空输入 / 窗口过短 / 含 NaN 一律 FeatureError（NaN 不许流进特征矩阵）。"""
    with pytest.raises(core.FeatureError):
        core.extract_primary([])
    with pytest.raises(core.FeatureError):
        core.extract_primary(np.zeros((0, 64)))
    with pytest.raises(core.FeatureError):
        core.extract_primary(np.ones((8, 4)))           # L<8：FFT 与矩都算不出
    with pytest.raises(core.FeatureError):
        core.extract_primary(np.full((8, 64), np.nan))
    with pytest.raises(core.FeatureError):
        core.make_signals(n=1, length=64)               # 单样本无法分层切分


def test_feature_names_dimension_is_30_primary_35_total():
    """特征名表：主特征 30（工单标题口径），加 5 衍生后 extract 返回 35。"""
    X = _signals(n=24)
    names_all = core.extract(X)[1]
    F_primary = core.extract_primary(X, fs=100.0)
    assert len(core.PRIMARY_FEATS) == 30
    assert len(core.TIME_FEATS) == 10 and len(core.FREQ_FEATS) == 15
    assert len(core.STAT_FEATS) == 5 and len(core.DERIVED_FEATS) == 5
    assert len(set(core.PRIMARY_FEATS)) == 30          # 无重名
    assert F_primary.shape == (24, 30)
    assert names_all == core.PRIMARY_FEATS + core.DERIVED_FEATS
    assert len(names_all) == 35
    assert core.extract(X, with_derived=False)[0].shape == (24, 30)
    # 特征字典五列规范（名称/公式/物理含义/单位/范围）逐条齐全
    rows = core.feature_dict_rows(names_all)
    assert len(rows) == 35
    assert all({"名称", "公式", "物理含义", "单位", "参考量程"} <= set(r) for r in rows)
    assert all(str(r["公式"]) and str(r["单位"]) for r in rows)
    assert all(r["实测范围"] == "" for r in rows)        # 缺省不给实测范围
