# -*- coding: utf-8 -*-
"""数据层：优先读课程链 P2.2 真实产物 features.npy/labels.npy（30维×200样本），
缺失时自动降级为「带种子的合成替代源」并打印声明——工单避坑：训练/推理特征
顺序必须一致，列序由 FEATURE_NAMES 契约锁定。
"""
import os

import numpy as np

N_DIM = 30
LABELS = {0: "正常", 1: "磨损"}

# 30 维特征名（与 P2.2/Jupyter W04 教师版特征字典的列序一致，顺序即契约）
FEATURE_NAMES = [
    "mean", "std", "max", "ptp", "rms", "var", "abs_mean", "crest",
    "kurtosis", "clearance", "skewness", "cv", "shape_factor",
    "impulse_factor", "zero_crossing_rate", "dom_freq", "f2", "f3",
    "spec_energy", "spec_centroid", "spec_var", "bandwidth",
    "half_power_bw", "energy_ratio_0_20hz", "spec_rolloff", "rms_freq",
    "spectral_flatness", "spectral_skewness", "spectral_kurtosis", "entropy",
]


def validate_feature_names(names):
    """feature_names 顺序校验：维数=30、无重复；违约即抛错（训练与推理共用）。"""
    names = list(names)
    if len(names) != N_DIM:
        raise ValueError("特征维数 %d ≠ %d，与训练契约不符" % (len(names), N_DIM))
    if len(set(names)) != N_DIM:
        raise ValueError("特征名存在重复，列序契约不可靠")
    return names


def make_synthetic(n=200, seed=42):
    """确定性合成替代源：30维（磨损类时域+频域前段整体抬升），0/1 分层。"""
    rng = np.random.RandomState(seed)
    X = rng.normal(0.0, 1.0, (n, N_DIM))
    y = rng.binomial(1, 0.5, n)
    X[y == 1, 1:9] += rng.uniform(0.9, 1.7)
    return X, y


def load_dataset(features_path, labels_path, seed=42, n_fallback=200):
    """加载数据集，返回 (X, y, feature_names, source_note)。

    source_note 必须打印并写入报告：真实数据/合成替代，二选一不含糊。
    """
    if os.path.exists(features_path) and os.path.exists(labels_path):
        X = np.load(features_path)
        y = np.load(labels_path)
        if X.ndim != 2 or X.shape[1] != N_DIM:
            raise ValueError("features.npy 形状 %s 不符合 30 维契约" % (X.shape,))
        note = "真实数据：P2.2 产物 %s（%d×%d）" % (
            os.path.basename(features_path), X.shape[0], X.shape[1])
    else:
        X, y = make_synthetic(n_fallback, seed)
        note = ("合成替代源：features.npy 缺失，seed=%d 确定性生成（%d×%d）——"
                "报告与答辩口径须注明" % (seed, X.shape[0], X.shape[1]))
    names = validate_feature_names(FEATURE_NAMES)
    return X, y.astype(int), names, note
