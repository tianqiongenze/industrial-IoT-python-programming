# -*- coding: utf-8 -*-
"""A 层（师傅·进阶拓展）去冗余闸门：drop_redundant 的真实语义与硬恒等式。

工单 cell-0 的 A 层要求是"相关系数矩阵热力图：剔除 |r|>0.95 的冗余特征并说明取舍"，
本文件把这句话拆成可证伪的断言（此前该函数一行测试都没有）：
  1. 工厂确实产出 30 个主特征，名字与工单清单逐一对齐（波形域 15 = 时域 10 + 统计 5，
     频域 15），无重名；
  2. 冗余不是"统计巧合"而是**硬恒等式**：var=std²、rms²=mean²+var、
     kurtosis_excess=kurtosis−3 ⇒ 这些列的 |r| 必然是 1（或机器精度级贴近 1）；
  3. 阈值判定含等号（|r| ≥ threshold 即判冗余），边界值亲自验证；
  4. keep_idx 是**优先级顺序**：谁先入场谁当赢家，改顺序就改保留集（改配置即生效）；
  5. 剔除后 kept ∪ dropped 恰为候选集，且 kept 两两之间不再有任何 |r| ≥ 阈值 的对。
"""
import numpy as np
import pytest

from feat_factory import core


@pytest.fixture(scope="module")
def probe():
    """真实特征矩阵 + 相关矩阵 + 优先级清单（与流水线同一套代码，只是用 Fisher 代替 RF
    以避开训练开销；prio 只覆盖 30 个主特征，与 pipeline 的 order 同口径）。"""
    X, y = core.make_signals(n=200, length=512, fs=100.0, seed=7, f0=8.0)
    F, names = core.extract(X, fs=100.0, f0=8.0, harmonic=2.0, entropy_bins=16)
    R = core.corr_matrix(F)
    prio = list(np.argsort(-core.fisher_ratio(F[:, :30], y)))
    assert sorted(prio) == list(range(30))
    return {"X": X, "y": y, "F": F, "names": names, "R": R, "prio": prio}


# ------------------------------------------------------------------ 30 特征构成
def test_factory_output_has_exactly_30_primary_features_with_expected_names(probe):
    """extract() 的列 = PRIMARY(30) + DERIVED(5)，与工单清单逐名一致且无重复。"""
    F, names = probe["F"], probe["names"]
    assert names == core.PRIMARY_FEATS + core.DERIVED_FEATS
    assert len(names) == 35 and len(set(names)) == 35      # 无重名
    assert F.shape == (200, 35)
    assert core.extract(probe["X"], fs=100.0, with_derived=False)[1] \
        == core.PRIMARY_FEATS
    assert len(core.PRIMARY_FEATS) == 30
    assert core.extract_primary(probe["X"], fs=100.0).shape == (200, 30)
    assert np.isfinite(F).all()


def test_workbook_grouping_is_15_waveform_plus_15_frequency():
    """工单『时域 15 + 频域 15 = 30』口径：波形域 15 = 时域 10 + 统计 5（都只吃波形），
    频域 15 全部吃同一次 rfft；两组不重名，并集恰是 30 主特征。"""
    waveform = core.TIME_FEATS + core.STAT_FEATS
    assert len(core.TIME_FEATS) == 10 and len(core.STAT_FEATS) == 5
    assert len(waveform) == 15 and len(core.FREQ_FEATS) == 15
    assert set(waveform) & set(core.FREQ_FEATS) == set()
    assert sorted(waveform + core.FREQ_FEATS) == sorted(core.PRIMARY_FEATS)
    assert len(set(core.PRIMARY_FEATS)) == 30
    # 每个名字都在 META 注册表里有"公式/物理含义/单位/量程"四件套（五列规范）
    for n in core.PRIMARY_FEATS + core.DERIVED_FEATS:
        formula, meaning, unit, ref = core.META[n]
        assert formula and meaning and unit and ref


# ------------------------------------------------------------------ 硬恒等式
def test_hard_identities_hold_on_real_columns(probe):
    """恒等式两侧都由同一份特征矩阵算出：偏差必须是机器精度级，不是"差不多"。"""
    F, names = probe["F"], probe["names"]
    c = lambda n: F[:, names.index(n)]                     # noqa: E731
    eps = core.EPS
    assert np.abs(c("var") - c("std") ** 2).max() < 1e-10
    assert np.abs(c("rms") ** 2
                  - (c("mean") ** 2 + c("var"))).max() < 1e-10
    assert np.abs(c("kurtosis_excess") - (c("kurtosis") - 3.0)).max() == 0.0
    assert np.abs(c("crest") - c("peak") / (c("rms") + eps)).max() < 1e-10
    assert np.abs(c("shape_factor")
                  - c("rms") / (c("abs_mean") + eps)).max() < 1e-10
    assert np.abs(c("cv") - c("std") / (np.abs(c("mean")) + eps)).max() < 1e-10
    # Parseval：单边谱能量 ≈ 2×方差（去直流后），容差与教师版同用 5e-3
    assert np.abs(c("spec_energy") - 2.0 * c("var")).max() < 5e-3


def test_identity_devations_helper_agrees_with_manual_checks(probe):
    """core.identity_devations 是报告 D 层行的证据来源——它必须自己说真话。"""
    rows = core.identity_devations(probe["F"], probe["names"])
    tags = {t: (dev, tol, ok) for t, dev, tol, ok in rows}
    assert len(rows) == 7 and all(ok for _t, _d, _tol, ok in rows)
    assert tags["var=std²"][1] == core.IDENTITY_TOL
    assert tags["var=std²"][0] < 1e-10
    assert tags["rms²=mean²+var"][0] < 1e-10
    assert tags["kurtosis_excess=kurtosis−3"][0] == 0.0
    assert tags["spec_energy≈2·var(Parseval)"][1] == core.PARSEVAL_TOL
    with pytest.raises(core.FeatureError):                 # 缺列就报错，不静默放行
        core.identity_devations(probe["F"][:, :10], probe["names"][:10])


def test_unit_correlation_for_identical_columns(probe):
    """恒等 ⇒ |r|=1：kurtosis 与 kurtosis_excess 是平移关系，相关系数就是 1。"""
    names, R = probe["names"], probe["R"]
    i, j = names.index("kurtosis"), names.index("kurtosis_excess")
    assert abs(abs(R[i, j]) - 1.0) < 1e-9
    assert np.allclose(np.diag(R), 1.0)
    assert np.allclose(R, R.T)                              # 对称
    assert abs(R[names.index("var"), names.index("std")]) < 0.9995
    # var=std² 是**非线性**恒等：Pearson 只到 0.9988，够不上 |r|=1，但仍越过 0.95 冗余线
    assert abs(R[names.index("var"), names.index("std")]) > 0.95
    # 上三角里 |r| 严格等于 1（机器精度内）的对，只有这一对——报告点的就是它
    iu = np.triu_indices(30, 1)
    exact = [(names[a], names[b]) for a, b in zip(*iu)
             if abs(R[a, b]) >= 1.0 - 1e-12]
    assert exact == [("kurtosis", "kurtosis_excess")]


# ------------------------------------------------------------------ 剔除规则
def test_threshold_is_inclusive_at_the_boundary():
    """|r| ≥ 阈值 即判冗余（含等号）：差 1e-6 不过线，正好等于就过线。"""
    thr = 0.95
    R_at = np.array([[1.0, 0.95], [0.95, 1.0]])
    kept, dropped = core.drop_redundant(R_at, ["a", "b"], [0, 1], thr)
    assert kept == [0] and [d["feature"] for d in dropped] == ["b"]
    assert dropped[0]["kept"] == "a" and dropped[0]["abs_r"] == 0.95

    R_below = np.array([[1.0, 0.949999], [0.949999, 1.0]])
    kept2, dropped2 = core.drop_redundant(R_below, ["a", "b"], [0, 1], thr)
    assert kept2 == [0, 1] and dropped2 == []
    # 负相关同样按绝对值判冗余
    R_neg = np.array([[1.0, -0.99], [-0.99, 1.0]])
    kept3, dropped3 = core.drop_redundant(R_neg, ["a", "b"], [0, 1], thr)
    assert kept3 == [0] and dropped3[0]["abs_r"] == 0.99


def test_priority_order_decides_the_winner():
    """keep_idx 是优先级顺序：先入场者保留，后来者被记为冗余——顺序换，赢家就换。"""
    names = ["mean", "std", "var"]
    R = np.array([[1.0, 0.80, 0.80],
                  [0.80, 1.0, 0.99],
                  [0.80, 0.99, 1.0]])
    kept_a, dropped_a = core.drop_redundant(R, names, [0, 1, 2], 0.95)
    assert kept_a == [0, 1]
    assert [(d["feature"], d["kept"]) for d in dropped_a] == [("var", "std")]
    kept_b, dropped_b = core.drop_redundant(R, names, [2, 1, 0], 0.95)
    assert kept_b == [0, 2]        # var 先入场 ⇒ std 成了被剔的那个
    assert [(d["feature"], d["kept"]) for d in dropped_b] == [("std", "var")]
    # 重复下标只算一次：优先级 1,1,2,0 等价于 1,2,0 ⇒ std 先入场，var 被剔，mean 留下
    kept_c, dropped_c = core.drop_redundant(R, names, [1, 1, 2, 0], 0.95)
    assert kept_c == [0, 1] and len(dropped_c) == 1
    assert [(d["feature"], d["kept"]) for d in dropped_c] == [("var", "std")]
    # kept 升序返回（便于与清单对账），dropped 保持优先级顺序（便于讲解）
    assert kept_c == sorted(kept_c)


def test_pruning_partitions_candidates_and_leaves_no_redundant_pair(probe):
    """真实矩阵上：保留 + 剔除 = 候选全集，两者不相交，且保留集内不再有任何冗余对。"""
    names, R, prio = probe["names"], probe["R"], probe["prio"]
    thr = 0.95
    kept, dropped = core.drop_redundant(R, names, prio, thr)
    cand = set(prio)
    assert set(kept) | {names.index(d["feature"]) for d in dropped} == cand
    assert set(kept) & {names.index(d["feature"]) for d in dropped} == set()
    assert len(kept) + len(dropped) == len(cand)
    assert kept == sorted(kept)
    sub = np.abs(R[np.ix_(kept, kept)])
    iu = np.triu_indices(len(kept), 1)
    assert sub[iu].max() < thr                             # 保留集内零冗余对
    for d in dropped:                                      # 每条剔除都有赢家与证据
        assert d["kept"] in [names[i] for i in kept]
        assert d["abs_r"] >= thr - 5e-5
        assert set(d) == {"feature", "kept", "abs_r"}


def test_pruning_scope_is_primary_features_only(probe):
    """工单口径：30 主特征参与去冗余，5 衍生列由主特征组合而成，不重复剔。"""
    names, R = probe["names"], probe["R"]
    kept, dropped = core.drop_redundant(R, names, list(probe["prio"]), 0.95)
    involved = {names[i] for i in kept} | {d["feature"] for d in dropped}
    assert involved <= set(core.PRIMARY_FEATS)
    assert not involved & set(core.DERIVED_FEATS)


def test_exact_identity_pair_can_never_both_survive(probe):
    """|r|=1 的恒等对至多留一个（后入场者必被判冗余）。"""
    names, R = probe["names"], probe["R"]
    kept, _dropped = core.drop_redundant(R, names, list(probe["prio"]), 0.95)
    survivors = {names[i] for i in kept}
    iu = np.triu_indices(len(names), 1)
    pairs = [(names[a], names[b]) for a, b in zip(*iu) if abs(R[a, b]) >= 1 - 1e-12]
    assert pairs
    for a, b in pairs:
        assert len({a, b} & survivors) <= 1, (a, b)


def test_threshold_and_keep_rule_are_config_knobs(probe):
    """改配置不改代码：阈值抬到 0.99 少剔几个；keep=rank 时衍生列也参与、赢家改变。"""
    names, R, prio = probe["names"], probe["R"], probe["prio"]
    k95, d95 = core.drop_redundant(R, names, prio, 0.95)
    k99, d99 = core.drop_redundant(R, names, prio, 0.99)
    assert len(d99) < len(d95) and len(k99) > len(k95)
    k100, d100 = core.drop_redundant(R, names, prio, 1.0 + 1e-9)
    assert d100 == [] and k100 == sorted(prio)             # 全不过线 ⇒ 一个都不剔
    rank = list(range(len(names)))                         # 清单顺序 + 衍生列参与
    kr, dr = core.drop_redundant(R, names, rank, 0.95)
    assert len(dr) >= len(d95)                             # 候选更多 ⇒ 剔得不止同样多
    assert {names[i] for i in kr} != {names[i] for i in k95}
    assert {d["feature"] for d in dr} & set(core.DERIVED_FEATS)
